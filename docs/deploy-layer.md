# 部署层：进程隔离的边界、通信、故障恢复与验证

**日期**：2026-10-28
**对应代码**：`src/soapbot/plugins/supervisor.py`、`plugins/isolation.py`、`plugins/surfaces.py`、`security/posture.py`、`cli.py`、`deploy/`
**定位**：`plugin-isolation.md` 讲的是「插件为什么必须离开主进程」；本文讲的是**离开之后，这套东西到底靠什么守住，以及怎么证明它守住了**。

---

## 0. 先给可执行结论

```bash
soapbot doctor --strict     # 退出码 0 = 可对外；2 = 有 critical/high 未解决
```

这一条命令是本文所有承诺的**唯一可信入口**。它不只打印建议，而是构建真实的 `PluginManager`、检查隔离是否真的开启、密钥是否躺在环境变量里、控制面是否绑到了 `0.0.0.0`，然后给出退出码供 CI 做门禁。

之所以强调这一点：本项目此前的隔离能力**实现完整但从未被调用**——`IsolatedRunner` 存在了一整个迭代，`src/` 里零调用点。所有"第 2 层保证"当时都是文档而不是属性。现在的 `doctor` 与测试都从 `build_plugin_manager` 走，就是为了让这类"写好了没人用"的缺陷无处藏身。

---

## 1. 隔离边界：什么在内，什么在外

### 1.1 进程划分

```
┌───────────────────────── 宿主进程 (host) ─────────────────────────┐
│  Runtime / MemoryStore / DB / Adapter / AuditLog / CapabilityGuard │
│                                                                    │
│   Supervisor ── 持有每个插件的 stdin/stdout 管道，是唯一出入口      │
└───────────┬────────────────────────────────────┬───────────────────┘
            │  spawn(-I, 干净 env)               │  JSON 帧
    ┌───────▼────────┐                   ┌───────▼────────┐
    │ worker: echo   │                   │ worker: remind │   ← 各占一个进程
    │ Plugin 代码    │                   │ Plugin 代码    │
    │ ctx.* 代理对象 │                   │ ctx.* 代理对象 │
    └────────────────┘                   └────────────────┘
```

### 1.2 边界内外的确切清单

| 资源 | 插件进程 | 依据 |
|---|---|---|
| 插件自身代码 | ✅ 可访问 | 它自己的文件 |
| `MemoryStore` / DB 连接 | ❌ 不可触及 | 不在子进程地址空间 |
| `CapabilityGuard` | ❌ 不可触及 | 授权只在父进程执行 |
| `AuditLog` | ❌ 不可触及 | 审计在父进程写 |
| Adapter（QQ/OneBot 连接） | ❌ 不可触及 | 同上 |
| 其它插件的进程 | ❌ 不可触及 | 独立进程 + 独立管道 |
| 宿主内部模块 | ❌ 不可 `import` | 见 1.4 |
| 环境变量 | ⚠️ 仅 11 个白名单 | 见 1.5 |
| 文件系统 | ⚠️ 同 uid 可达 | 见 §5 残余风险 |
| 网络 | ⚠️ 同 uid 可达 | 见 §5 残余风险 |

### 1.3 授权与作用域为什么必须在父进程

这是整个设计的支点。对比两条路径：

```python
# 同进程（Wave 0~2）：插件能自己改判定
from soapbot.plugins import sandbox
sandbox.CapabilityGuard.check = lambda *a, **k: None   # 防护整体失效

# 子进程（现在）：不存在可改的对象
ctx.memory.recall("猫")   # 发一帧出去，等父进程裁决
```

关键在于**协议里没有"作用域"这个字段**。插件无法表达"读 999 群"，就像 `ctx.memory.recall()` 没有 `scope` 参数一样。若插件硬塞 `scope`，父进程**拒绝**而非忽略——忽略更糟：插件会以为自己读到了 999 群，然后基于空结果继续行动。

```python
# supervisor.py
forbidden = _FORBIDDEN_ARG_KEYS.intersection(raw_args)
if forbidden:
    raise SurfaceDeniedError("arguments may not be supplied by the plugin: ...")
```

### 1.4 子进程不能 `import soapbot`

子进程用 `python -I` 启动且不把 `src/` 放进 `sys.path`。但插件合法地写着 `from soapbot.plugins.base import Plugin`，直接禁止会让每个插件都要写两套代码。

解法是**只装一个极小的兼容包**（`_install_stubs`），提供 `Plugin` / `CallerContext` / `Role` 这些**纯数据类型与常量**。于是：

```python
import soapbot.memory.db   # ModuleNotFoundError  ← 正确：宿主内部
from soapbot.plugins.base import Plugin   # 正常  ← 公开 API
```

实测（`_probe_e2e_deploy.py`）：`isolation: host internals unimportable from the child — ModuleNotFoundError`。

> 维护约束：stub 里**只放类型和常量**。一旦它开始有行为，就变成了宿主 API 的第二份实现，两份实现必然漂移。

### 1.5 子进程环境变量：白名单而非黑名单

```python
env = sanitize_env(base=os.environ)   # 只保留 PATH/LANG/TZ/HOME 等 11 项
```

白名单的理由很实际：凭据类变量名是**开放集合**（`AWS_SECRET_ACCESS_KEY`、`HF_TOKEN`、`AZURE_CLIENT_SECRET`……），黑名单永远漏。白名单默认安全。

实测：子进程 `11 vars, leaks=[]`。

---

## 2. 通信机制

### 2.1 协议

长度前缀 + JSON，单向写、按 `cid` 关联：

```
parent → child : {"type":"boot", "plugin_dir":..., "api":{...}}   启动上下文
parent → child : {"type":"call", "cid":N, "handler":..., "caller":{...}, "args":[...]}
child  → parent: {"type":"ready", "ok":true, "commands":[...], "api":{...}}
child  → parent: {"type":"request", "cid":N, "surface":"memory.recall", "args":{...}}
parent → child : {"type":"reply", "cid":N, "ok":true, "value":...}
child  → parent: {"type":"log", "level":..., "message":...}
```

用管道而非 socket：管道天然继承、无端口可被同机其它进程连接、无监听面。

### 2.2 跨边界的错误语义

| 传出方向 | 传什么 | 为什么 |
|---|---|---|
| 子进程 → 父进程 | **只传异常类型名** | 插件异常文本由插件编写，可能含 API key。实测断言 `"sk-live" not in str(info.value)`，同时保留 `RuntimeError` 便于运维区分故障 |
| 父进程 → 子进程 | 授权拒绝传固定串 `"PermissionError"` | 不暴露规则细节 |
| 父进程日志 | 完整 traceback | 宿主自身 bug 必须可诊断，否则插件作者会去调试错误的一侧 |

### 2.3 协议健壮性

- 帧长上限 `MAX_FRAME_BYTES`，超限即杀——防止插件用超长帧撑爆宿主内存
- 子进程往 stdout 写垃圾（绕过 `_stdout` 直接写 `sys.stdout.buffer`）会被判定为协议破坏并终止，**不会**污染宿主解析
- 未注册的 handler 返回明确错误，不是静默超时

---

## 3. 故障恢复

### 3.1 三级策略

```
单次崩溃  → 指数退避重启（BASE 起，CAP 封顶）
窗口内多次崩溃 → 熔断打开，停止重启
运维介入  → reload 显式重置
```

熔断是必须的：一个每条消息都崩的插件，无限重启比不服务更贵。熔断后**不自动恢复**——坏插件应当保持下线，直到有人看它。

```python
# 实测日志
plugin demo crash-looped 4 times in 60s; circuit open, no further restarts
until an operator reloads it
```

### 3.2 存活判定：一个真实修复的坑

```python
# 曾经
return self._proc is not None and self._proc.returncode is None   # ← 不够
```

子进程 `os._exit()` 后，内核已回收，但事件循环尚未投递退出通知，`returncode` 仍为 `None`。后果是 Supervisor 把调用发往一根死管道，且健康报告显示"正常"。

现在以**读到 EOF 的那一刻**为准（`_dead` 标志），并 `await proc.wait()` 刷新状态：

```python
if self._dead:
    return False
return self._proc is not None and self._proc.returncode is None
```

### 3.3 资源限制（POSIX）

```python
resource.setrlimit(RLIMIT_AS,   256MB)   # 内存
resource.setrlimit(RLIMIT_CORE, 0)       # 禁 core dump（防密钥写入磁盘）
resource.setrlimit(RLIMIT_NPROC, 64)     # 防 fork 炸弹
```

超时用 `killpg` 杀**整个进程组**。此前只杀直接子进程，插件 spawn 的 20 个 helper 会存活并继续吃 CPU——"被隔离"的插件仍在烧机器。

---

## 4. 安全性验证方法

### 4.1 一条命令（推荐）

```bash
soapbot doctor            # 人读
soapbot doctor --json     # 机器读
soapbot doctor --strict   # CI 门禁：critical/high 未解决 → exit 2
```

实测输出：

```
[ok]   isolation.process  (critical)   process isolation enabled
[ok]   secrets.env        (high)       no secret-looking variables
[ok]   net.bind           (high)       control API bound to 127.0.0.1
[warn] fs.plugin_dir      (medium)     writable by the bot process
[warn] deploy.container   (medium)     not running in a container
verdict: PASS
```

### 4.2 门禁语义（一处已修复的真实缺陷）

`secrets.env` 原先返回 `WARN + HIGH`，而 `PostureReport.ok` 只统计 `Status.FAIL`。两个集合不相交，于是**主密钥躺在环境变量里时仍然 `verdict: PASS`、`--strict` 退出 0**——门禁恰好放行了它存在的理由。

修复后判定按**严重度优先**：

```python
return not any(
    f.severity in (Severity.CRITICAL, Severity.HIGH)
    and f.status not in (Status.PASS, Status.UNKNOWN)
    for f in self.findings
)
```

实测对照：

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 干净环境 | PASS / 0 | PASS / 0 |
| `SOAPBOT_MASTER_KEY` 在环境中 | **PASS / 0** ❌ | **FAIL / 2** ✅ |

### 4.3 端到端实证（`_probe_e2e_deploy.py`）

走真实生产路径 `build_plugin_manager → loader → supervisor`，7/7 通过：

```
[PASS] isolation: plugin runs in a separate OS process — host=10108 plugin=19684
[PASS] isolation: plugin code is absent from the host interpreter
[PASS] isolation: host internals unimportable from the child — ModuleNotFoundError
[PASS] secrets: child environment is a small allowlist — 11 vars, leaks=[]
[PASS] authz: ungranted memory_read is refused — WorkerCrashedError
[PASS] hostile: infinite loop is bounded — TimeoutError after 3.0s
[PASS] hostile: os._exit in a plugin does not kill the host
```

### 4.4 两处「门禁自相矛盾」（均已修复）

修复 4.2 之后立刻暴露了第二个问题，两者叠加才让门禁真正可信：

**问题一：正确的部署方式被判为违规。**
`_is_secret_env_name` 按子串匹配，`SOAPBOT_MASTER_KEY_FILE` 含 `MASTER_KEY`，于是被判为"环境里有密钥"——**而同一个 finding 的 remediation 恰恰写着"请改用 SOAPBOT_MASTER_KEY_FILE"**。运维照做后门禁变红，提示他去做已经做的事。

修复：`*_FILE` / `*_PATH` / `*_DIR` 后缀表示**位置**而非秘密，不计入。

**问题二：检查的不是真正在用的那个文件。**
posture 固定检查 `data/secret.key`，但推荐部署把密钥挂在 `SOAPBOT_MASTER_KEY_FILE` 指定的路径。结果既误报"key file not found"，又**从未检查真实密钥文件的权限**。

修复：`key_path = settings.master_key_file or (settings.data_dir / "secret.key")`。

实测对照（`doctor --strict`）：

| 密钥供给方式 | 判定 | 退出码 |
|---|---|---|
| `SOAPBOT_MASTER_KEY_FILE`（推荐） | PASS | 0 |
| `SOAPBOT_MASTER_KEY`（环境变量） | FAIL | 2 |

### 4.5 回归测试

| 文件 | 数量 | 守护什么 |
|---|---|---|
| `tests/test_deploy_isolation.py` | 23 | 边界、授权、密钥、干扰、恢复、协议 |
| `tests/test_posture.py` | 33 | 门禁语义（含上面三处缺陷） |
| 全量 | **522 passed, 3 skipped** | 无回归 |

其中最关键的一条：

```python
async def test_plugin_runs_in_a_separate_process_from_the_production_builder(tmp_path):
    """只直接测 runner 的测试，在隔离从未被调用的那个迭代里也会通过。"""
    manager = build_plugin_manager(plugins, allow_untrusted=True)   # 与 app 同一条路
    ...
    assert loaded.instance is None            # 结构证据
    assert view["pid"] != os.getpid()         # 行为证据
```

---

## 5. 干扰场景与应对矩阵

| 干扰 | 表现 | 应对 | 实测 |
|---|---|---|---|
| 死循环 | 永不返回 | 超时 → `killpg` | `TimeoutError after 3.0s` |
| `os._exit()` | 进程猝死 | 只杀死 worker，宿主存活 | 宿主 pid 不变 |
| fork 炸弹 / 遗留 helper | CPU 被吃满 | `RLIMIT_NPROC` + 杀进程组 | 组内全灭 |
| 内存炸弹 | OOM | `RLIMIT_AS = 256MB` | 分配失败即崩，宿主不受影响 |
| 反复崩溃 | 重启风暴 | 熔断，停止重启 | `circuit open` |
| 协议垃圾 | 解析错乱 | 帧长上限 + EOF 判定 | 杀进程 |
| 越权读记忆 | 跨群泄露 | 父进程授权 + 无 `scope` 字段 | `PermissionError` |
| 伪造身份 | 冒充他插件 | 身份 = 管道，不是 JSON 字段 | 拒绝 |
| 探测未暴露接口 | 攻击面扩展 | 白名单 `ALLOWED_SURFACES` | 拒绝 |
| 异常消息窃密 | 密钥回显 | 只回传类型名 | `sk-live` 未出现 |

---

## 6. 残余风险（诚实声明，不是遗漏）

同 uid 进程隔离**不能**阻止：文件系统读写、网络外连、读取同 uid 的其它进程内存、`ptrace`（若允许）。

这不是实现缺陷，是 OS 权限模型的边界。**闭环靠第 3 层**：

```yaml
# deploy/docker-compose.yml
read_only: true
cap_drop: [ALL]
security_opt: ["no-new-privileges:true"]
user: "10001:10001"
tmpfs: [/tmp]
```

> ⚠️ `deploy/` 下的 Dockerfile 与 compose **尚未在本机实测**（开发环境无 Docker）。配置依据是现行最佳实践，但请在你的目标环境先跑 `docker compose config` 与一次试启动再上生产。

另外两条已知限制：

1. **插件目录可写**（`fs.plugin_dir` warn）→ 被攻陷的插件可改写自身代码以持久化。生产应 `:ro` 挂载。
2. **`bind_caller` 可被恶意插件自行调用**（同进程场景）→ 这正是进程隔离要解决的问题；在隔离子进程中，`bind_caller` 不再有跨调用者提权的意义，因为每次调用都是新帧、caller 由父进程注入。

---

## 7. 部署清单

- [ ] `soapbot doctor --strict` 退出码为 0
- [ ] 密钥用 `SOAPBOT_MASTER_KEY_FILE`（文件），不用环境变量
- [ ] 控制面绑 `127.0.0.1`，前置鉴权反代
- [ ] 用 `deploy/docker-compose.yml`（只读根、drop caps、非 root）
- [ ] 插件目录只读挂载
- [ ] 一个数据目录只跑一个实例
- [ ] CI 里把 `doctor --strict` 作为部署前门禁

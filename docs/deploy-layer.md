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
resource.setrlimit(RLIMIT_AS,   512MB)   # 地址空间上限（注意是虚拟地址，见下）
resource.setrlimit(RLIMIT_CORE, 0)       # 禁 core dump（防密钥写入磁盘）
```

`RLIMIT_NPROC` 已被**移除**，它原本被当作防 fork 炸弹的手段，实际上是有害的：它按
**真实 uid 全系统**计数，且把**线程**也算进去。共用账号上（CI runner 即是）这份配额在
worker 启动前就被别人花掉一部分，于是子进程第一次 `run_in_executor` 创建读帧线程时就抛
`RuntimeError: can't start new thread`，进程以退出码 1 静默死亡；而且它限制的是整个 uid，
会连带压住兄弟进程，并不构成隔离。

`RLIMIT_AS` 从 256MB 提到 512MB 也是同一类错误：它计的是**虚拟**地址空间，而裸 CPython
在跑任何插件代码前就已保留数百 MB（arena、mmap 的库、guard page），256MB 之下连一个
8MB 的线程栈都放不下。真正的 fork 炸弹防护是 `killpg`，见下。

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
| fork 炸弹 / 遗留 helper | CPU 被吃满 | 杀进程组（`killpg`） | 组内全灭 |
| 内存炸弹 | OOM | `RLIMIT_AS = 512MB` | 分配失败即崩，宿主不受影响 |
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

---

## 8. 容器验收清单（已于 2026-10-30 在真机执行）

**当前状态：已在雨云 Ubuntu 24.04 主机实测，9 条全部通过。**

跑这一遍的代价是发现两个真缺陷：`seccomp:default` 让容器**根本创建不出来**（Docker 把
冒号后的值当成 compose 目录下的文件路径），`doctor` 在容器内把 `0.0.0.0` 判成 CRITICAL
导致自检永远 FAIL。两者都已修复。前者正是静态检查不可能发现的——`check_deploy.py` 验证
的是「这一行存在且写法像样」，而 Docker 的语义是「冒号后面是文件路径」。

下面的每一条都需要一台装有 Docker 的机器，按顺序执行，并把实际输出记下来。

前置：`deploy/daemon-mirror.md` 里的镜像加速必须先配好，否则 `build` 在第一条 `FROM`
就超时（已实测直连 Docker Hub 不通）。

| # | 命令 | 预期结果 | 失败通常意味着 |
|---|---|---|---|
| 1 | `docker compose -f deploy/docker-compose.yml build` | 退出码 0，末尾 `naming to ... soapbot:hardened` | 基础镜像拉不到（看 mirror）；或缺 `gcc` 导致某个轮子要源码编译 |
| 2 | `docker compose -f deploy/docker-compose.yml up -d` 后 `docker compose ps` | 状态 `Up (healthy)`，约 20–30 秒后转 healthy | `start_period` 太短；或进程确实没监听 6185（`docker compose logs` 会有 traceback） |
| 3 | `docker compose exec soapbot id` | `uid=10001 gid=10001`，**不是** root | `USER` 没生效，或 compose 的 `user:` 被覆盖 |
| 4 | `docker compose exec soapbot sh -c 'touch /app/x'` | 报 `Read-only file system` | `read_only: true` 没生效 |
| 5 | `curl -s localhost:6185/api/health` | `{"status":"ok",...}` | 端口映射方向反了，或容器内绑到了 loopback |
| 6 | 浏览器打开 `http://<服务器>:6185`，登录后**在第 12 页切一次语言、开一次语音开关** | 提示「已保存」/「待重启生效」，且 `docker compose exec soapbot cat /data/.env` 出现对应行 | 这是唯一能证明 `SOAPBOT_ENV_FILE` 真的指到可写卷的方法。若报权限错误，说明它仍指向 `/app/.env`（只读根） |
| 7 | `docker compose restart soapbot` 后再看第 12 页 | 刚才的开关变成已生效值 | 写入成功了但读取路径不一致——`.env` 与进程读到的不是同一个文件 |
| 8 | `docker compose down && docker compose up -d` | 面板数据、`/data/.env` 设置都还在 | 卷没生效，或数据写到了容器层 |
| 9 | `docker compose exec soapbot sh -c 'cat /proc/1/comm'` | `tini` | `ENTRYPOINT` 被覆盖，插件子进程会成为孤儿 |

### 8.1 实测记录（2026-10-30，雨云 Ubuntu 24.04 / 2 vCPU / 3.9 GB）

| # | 结果 | 实际输出 |
|---|---|---|
| 1 构建 | **PASS** | `soapbot:hardened`，430 MB，约 75 秒 |
| 2 启动 | **PASS** | `Up (healthy)`，端口 `127.0.0.1:6185->6185/tcp` |
| 3 非 root | **PASS** | `uid=10001(app) gid=10001(app)` |
| 4 只读根 | **PASS** | `touch: cannot touch '/app/x': Read-only file system` |
| 5 健康端点 | **PASS** | `{"status":"ok","version":"0.1.0","uptime_seconds":32.967}` |
| 6 设置页写入 | **PASS** | `POST /api/settings` → `{"written":true,"changed":["default_locale","voice_enabled"],"restart_required":true}`；`/data/.env` 随即出现 `SOAPBOT_DEFAULT_LOCALE=en-US` 与 `SOAPBOT_VOICE_ENABLED=true` |
| 7 重启后读取 | **PASS** | `restart` 后 `GET /api/settings` 返回 `en-US` / `true`，与磁盘一致；随后改回 `zh-CN` / `false` 并再重启复验 |
| 8 卷持久化 | **PASS** | `down` + `up` 后 `/data/secret.key` md5 不变（`64406e29…`），`soapbot.db`、`jwt.key`、`plugins/` 均在 |
| 9 init | **PASS** | `tini` |
| doctor | **PASS** | `verdict: PASS`；`provider.upstream`（无上游）与 `fs.plugin_dir`（插件目录可写）两条 medium 警告符合预期 |

主机环境：Linux 6.8.0-49 / Docker 29.1.3 / Compose 2.40.3；Docker Hub 直连可用，**未**配置镜像加速
（`daemon-mirror.md` 的前提在这台机器上不成立：`curl -sI https://registry-1.docker.io/v2/` 返回 401
而不是超时）。

第 6 步是这一轮新增的：只读根文件系统与「设置页可写」在静态层面是矛盾的，`check_deploy.py`
现在会检查 `SOAPBOT_ENV_FILE` 是否落在可写挂载内，但**只有真实的 `curl`/浏览器点击**才能
证明权限位、挂载点和进程读取路径三者对得上。

### 8.2 一条命令复验（2026-10-30 补齐）

§8.1 是手工跑的，每一步都要现拼 `docker compose exec`。现在固化进部署驱动器：

```bash
# 13 项：healthy / 只绑回环 / 非 root / 只读根 / 健康端点 / 容器内回环读设置
#        / /data 可写 / 卷内关键文件 / tini / doctor PASS / 重启策略 / 磁盘 / 内存
python scripts/deploy_remote.py --host <IP> --port 443 --key <私钥路径> --verify

# 数据卷快照：打包 → 只留 3 份 → 证明归档能被 tar 列出
python scripts/deploy_remote.py --host <IP> --port 443 --key <私钥路径> --backup
```

实跑结果（2026-10-30，同一台雨云主机）：**13 项全 PASS**，磁盘 17%、可用内存 3231 MB、
重启策略 `unless-stopped`；备份产出 `soapbot-2026-10-30-121626.tgz`，`tar -tzf` 能列出
`./soapbot.db`。

三个坑已经写进脚本，不再靠人记：

1. **控制面只能在容器内部调**。宿主机 `curl 127.0.0.1:6185` 返回 401——经端口映射进来的
   请求，容器内看到的源地址是 docker 网关，不是回环，免令牌通路不命中。
2. **`text=True` 会把 `\n` 翻译回 `\r\n`**。脚本在 Windows 上编写，远端 bash 收到的是
   `cd /opt/soapbot\r`，报 "No such file or directory" 而回车符在报错里看不见。改成传字节。
3. **`touch /app/x` 必须失败才算通过**。这步断言的是"被拒绝"，退出码为 0 恰恰是缺陷，
   所以判据看输出文本而不是退出码。

备份那条刻意多走一步：只看文件存在没有意义，**归档能不能被 `tar -tzf` 列出**才是可恢复的
证据——备份最常见的失败是"生成了一个打不开的文件"。

### 8.3 sshd 端口：拿主意的不是 drop-in，是生成器

现场排障记录（2026-10-30），因为这条弯路很容易再走一遍。

现象：`/etc/systemd/system/ssh.socket.d/443.conf` 里明明写了 `ListenStream=` / `22` / `443`
三行，`cat -A` 确认无 CRLF，`DropInPaths` 也包含它，但 `systemctl show ssh.socket -p Listen`
只有 443。

真正生效的文件是另一个：

```
/run/systemd/generator/ssh.socket.d/addresses.conf
# Automatically generated by sshd-socket-generator
[Socket]
ListenStream=
ListenStream=0.0.0.0:443
ListenStream=[::]:443
```

`sshd-socket-generator` **读 `/etc/ssh/sshd_config` 里的 `Port` 指令**生成这个文件，而它在合并
顺序里排在 `/etc` 的 drop-in 之后——最后那个 `ListenStream=` 空赋值把前面全清掉。Ubuntu 默认
是注释掉的 `#Port 22`，所以只追加 `Port 443` 的结果是"22 从配置里消失"，且**任何 drop-in 都
救不回来**。

结论：**端口只在 `sshd_config` 里声明**，不要写 socket drop-in。两行就是全部：

```
Port 22
Port 443
```

改完 `sshd -t && systemctl daemon-reload && systemctl restart ssh.socket`，再用
`systemctl show ssh.socket -p Listen` 复核。

改远端 sshd 的通用做法（本轮实际用的）：**先把回滚写进脚本**——`sshd -t` 失败即恢复备份；
重启后若 `443` 不在 Listen 列表里，立刻还原并重启。远程改监听端口时，"改坏了怎么回去"
必须和"怎么改"一起提交，否则一次手误就只能靠云控制台 VNC。

# 插件与主机隔离：复审报告、修复目标与验收标准

**日期**：2026-10-28
**范围**：Wave 0 至今全部迭代（`src/soapbot/` 全量 + `data/plugins/` + 依赖）
**核心命题**：「确保插件在任何情况下均无法影响主机的安全性」

---

## 0. 先说结论：这个命题能兑现到什么程度

**必须诚实前置**：只要插件与主机**运行在同一个 Python 进程内**，「任何情况下都无法影响主机」是**不可达的**。原因不是实现不够好，而是架构事实：

| 事实 | 后果 |
|---|---|
| 同一解释器、同一用户权限 | 插件可 `import httpx` / `open()` / `os._exit()` / `ctypes` 任意操作 |
| 共享 `sys.modules` 与全局对象 | 插件可 monkeypatch `AuditLog.record`、`injection.leaked_canary`，令主机防护**整体失效** |
| 共享堆 | 插件可 `gc.get_objects()` 遍历出 runtime、DB session、adapter |
| Python 无进程内权限模型 | `object.__setattr__`、`ctypes` 可绕过任何"只读"装饰 |

实测证据（`_probe_escape.py`，复审期间执行）：上述 4 类全部 `REACHED`。

**因此本次复审交付的不是"绝对隔离"，而是三层可验证的边界**：

```
第 1 层  封装层（同进程内）     —— 让善意插件无法顺手提权；让越权必须显式且被审计
第 2 层  进程层（子进程）       —— 让恶意插件的崩溃/挂死/内存炸弹打不到主机状态
第 3 层  部署层（OS 级）         —— 论文级别的真正隔离，需容器/seccomp/独立 uid
```

第 1、2 层本次已实现并实测；第 3 层给出明确部署要求（**本代码仓库无法自行提供**，这是诚实的边界声明，不是遗漏）。

---

## 1. 本次实测确证并修复的缺陷

每个都是**先复现、后修复、再复测**，不是清单式排查。

### I1 · 能力网关可被属性赋值自提权【高危 · 已修复】

```python
# 修复前，实测成功：
c = ctx_for("evil", {Capability.COMMAND})
c._guard.grant = CapabilityGrant(plugin="evil",
    declared=frozenset(Capability), approved=frozenset(Capability))
c.command("owned")        # 成功注册 —— 拿到了从未声明的 11 项能力
```

**为什么是严重问题**：整个能力模型的信任基础是"操作者批准了什么"。当被批准的代码能改写"批准记录"时，批准就不再是控制，而是自我声明。

**修复**：
- `CapabilityGrant` → `@dataclass(frozen=True)`
- 新增 `_SealedObject` 基类，`CapabilityGuard` 继承并在 `__init__` 末尾 `_seal()`，此后任何属性写/删都抛 `AttributeError`
- `_sealed` 自身也在保护范围内，防止先解封再篡改

**复测**：`ctx._guard.grant = ...` → `AttributeError`；`grant.approved = ...` → `FrozenInstanceError`；`_sealed = False` → `AttributeError`。且失败后授权集合不变（无部分写入）。

---

### I2 · 跨插件存储直读【高危 · 已修复】

```python
# 修复前，实测成功：
a.storage.set("api_token", "sk-live-SECRET-OF-PLUGIN-A")
b._storage_backend["plugin_a"]["api_token"]   # 拿到 A 的密钥
```

**根因**：`PluginStorage._backend` 持有**整个共享字典**。设计文档声称"命名空间隔离"，但前缀只是一个字典键——一次索引就绕过了。

**修复**：存储视图只持有**本插件那一片**字典（`backend.setdefault(plugin, {})`），拿不到外层映射；`PluginContext` 同样只保存自己的一片。

**复测**：`b._storage_backend["plugin_a"]` → `KeyError`；正常双插件读写互不干扰（正向对照通过）。

> 保留的已知事实：主机侧 `loader.storage_backend` 仍持有明文（加密由 `EncryptedPluginStorage` 在边界处完成）。这是**有意的**——主机必须能持久化；插件侧不可达才是要求。已写入残余风险。

---

### I3 · 发送目标任意注入【高危 · 已修复】

```python
# 修复前，实测成功：
c._observed_sessions.add("onebot11:group:999999999")   # 再 send 即可向任意群广播
```

**危害**：插件可向**它从未被调用过的群**发消息——垃圾信息、钓鱼、或以机器人身份实施社会工程。

**修复**：观察名单从 `PluginContext` 的普通 `set` 移到主机侧 `SessionLedger`；写入需 `HOST_AUTHORITY` 令牌，插件只有 `permits()` 读权限；卸载时 `forget_plugin()` 撤销授权（防止「以旧代码赚授权、换新代码继续用」）。

**复测**：`ctx._observed_sessions` 属性已不存在；`ledger.record(...)` 无令牌 → `PermissionError`；`ctx.send(未观察的群)` → `PermissionError`；主机记录后可正常发送（正向对照通过）。

---

### I4 · 无进程隔离机制（架构缺口）【高危 · 已提供执行器】

**实测的四个致命行为**（修复前全部会打到主机）：
- `os._exit(0)` → 直接杀死整个机器人进程
- `os.kill(os.getppid(), SIGKILL)` → 杀死父进程
- `while True: sleep()` → 挂死该会话（8s 超时只能救该会话，无法回收线程/资源）
- 内存炸弹 → 触发 OOM killer，可能杀死机器人而非插件
- `monkeypatch AuditLog.record = no-op` → **审计整体失效**，此后所有攻击不可见

**修复**：新增 `src/soapbot/plugins/isolation.py` · `IsolatedRunner`：
- `asyncio.create_subprocess_exec` + `-I`（忽略 `PYTHON*` 环境与 user site-packages，**子进程无法 `import soapbot`**）
- 父进程侧 `wait_for` 强制超时，超时即 `kill()`——不依赖子进程配合
- POSIX 下 `RLIMIT_AS`（默认 256 MiB）与 `RLIMIT_CORE=0`（防核心转储泄露主机内存）
- 仅 JSON 可序列化结果可跨界，拒绝活对象图
- 异常只传**类型**，不传消息（消息常含 token）

**实测（`_probe_isolation.py`，主机 pid 全程存活）**：

| 恶意行为 | 结果 |
|---|---|
| 正常返回 | `OK 'hello world'` 113ms |
| `os._exit(1)` | `CRASHED` 105ms，主机存活 |
| `os.kill(getppid(), SIGKILL)` | `CRASHED` 110ms，主机存活 |
| `while True` | `TIMEOUT` 3011ms |
| 内存炸弹 | `TIMEOUT` 3033ms |
| `raise RuntimeError('token=sk-live-...')` | `CRASHED`，**消息未跨界** |
| 返回 `object()` | `CRASHED` 非可序列化 |
| `import soapbot` | `CRASHED` 导入失败 |

---

### I5 · 插件 API 的"仅本机"只是假设【中危 · 已修复】

原实现依赖绑定 `127.0.0.1`。但 `SOAPBOT_HOST=0.0.0.0` 一次配置变更，`POST /api/plugins/{name}/load` 就变成**未鉴权的远程代码执行**。

**修复**：新增 `_require_loopback(request)`，校验**实际客户端地址**；非本机返回 **404**（而非 403，避免确认该接口存在）。所有 6 个端点均已接入。

---

### I6 · `_fts_index` 表名拼进 SQL【低危 · 已加固】

`text(f"INSERT INTO {table}...")` — 表名无法参数化，只能拼接。当前所有调用方传字面量，**不可利用**；但一旦有人把它参数化（例如从配置或插件取表名），立刻变成 SQL 注入且调用点看不出变化。

**修复**：`_FTS_TABLES` 白名单（`messages_fts` / `memories_fts` / `knowledge_fts`），越界直接 `ValueError`。

**复测**：`"memories_fts; DROP TABLE memories;--"` → `ValueError`，`memories` 表完好。

> 过程记录：首版白名单漏了 `messages_fts`，导致 5 个 Wave 3 测试失败。已改为"以 `db._create_fts` 为准"并加断言锁住，避免再次漂移。

---

## 2. 逐维度排查结论

用户点名的四个维度，逐项给出**实测**结论：

### 2.1 权限边界

| 检查项 | 结论 |
|---|---|
| 能力双重门（declared ∩ approved） | ✅ 完好，有 guard-rail 测试锁定 |
| 授权对象可被插件改写 | 🔴 **曾是**（I1），已修复 |
| `min_role` 可信度 | ✅ 插件声明仅作展示，宿主按已解析 Principal 重算 |
| 插件能否提升他人角色 | ✅ 不能；`CallerContext.at_least()` 只向宿主询问 |
| 命令名冲突 | ✅ 核心命令保留字 + 注册期校验 + 阶段顺序双保险 |

### 2.2 数据访问

| 检查项 | 结论 |
|---|---|
| 跨插件存储读取 | 🔴 **曾是**（I2），已修复 |
| 密钥静态加密 | ✅ Fernet；错密钥返回默认值而非半解密乱码 |
| 插件能否触达 DB / 记忆 / 知识库 | ✅ 无此能力；`ctx` 不暴露 session |
| 插件能否读他人会话历史 | ✅ 不能；只拿到 `CallerContext` 窄视图 |
| SQL 注入 | ✅ 查询全参数化；I6 加固了唯一拼接点 |

### 2.3 资源调用

| 检查项 | 结论 |
|---|---|
| 单插件打满主机 | ✅ 配额（普通 120/min、敏感 30/min，独立预算） |
| 命令注册表无限膨胀 | ✅ 受配额约束（实测第 121 次被拒） |
| 审计日志无限增长 | ✅ 有界（写 5000 条，`recent` 返回 ≤2000） |
| HTTP 响应体/请求体/超时 | ✅ 1 MiB / 1 MiB / 上限夹紧 |
| handler 挂死 | ✅ 8s 超时；隔离模式下由父进程强杀 |
| 内存耗尽 | ⚠️ 同进程下**无法**约束（Python 无内存配额）；隔离模式有 `RLIMIT_AS` |

### 2.4 进程隔离

| 检查项 | 结论 |
|---|---|
| 是否已有隔离机制 | 🔴 **原本完全没有**（全库无 subprocess/multiprocessing） |
| 崩溃隔离 | ✅ `IsolatedRunner` |
| 挂死隔离 | ✅ 父进程强杀 |
| 内存隔离 | ⚠️ 仅 POSIX（Windows 无 `RLIMIT_AS`），已披露 |
| 文件系统隔离 | ❌ 未实现（需容器/seccomp/独立 uid）→ 部署要求 |
| 网络隔离 | ❌ 未实现（同）→ 部署要求 |
| 全局状态污染 | ❌ 同进程不可防；隔离模式下子进程无法 import 宿主包，已大幅收窄 |

---

## 3. 修复目标

| 编号 | 目标 | 状态 |
|---|---|---|
| G1 | 插件无法通过属性赋值扩大自己的授权 | ✅ |
| G2 | 插件无法读到其它插件的存储数据 | ✅ |
| G3 | 插件无法向未观察过的会话发送 | ✅ |
| G4 | 插件崩溃/挂死/内存溢出不导致主机不可用 | ✅（POSIX 内存） |
| G5 | 插件异常消息不跨边界泄露敏感信息 | ✅ |
| G6 | 插件管理 API 在非本机访问时 fail-closed | ✅ |
| G7 | SQL 标识符不接受外部输入 | ✅ |
| G8 | **文件系统与网络完全隔离** | ❌ 需第 3 层，见 §5 |

---

## 4. 验收标准

### 4.1 自动化（可回归）

```powershell
$env:PYTHONPATH="f:/soapbot/src"

# 隔离专项：30 项，每项对应一个已实测攻击
.\.venv\Scripts\python.exe -m pytest tests/test_plugin_isolation.py -q

# 全量回归
.\.venv\Scripts\python.exe -m pytest tests/ -q
# 435 passed, 1 skipped

& ".\.venv\Scripts\ruff.exe" check src/ tests/     # All checks passed
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off   # No known vulnerabilities
```

### 4.2 逐条验收判据

| 判据 | 验证方式 | 通过标准 |
|---|---|---|
| A1 授权不可自改 | `test_i1_*`（4 项） | 三种写法均抛异常，且授权集合不变 |
| A2 存储不可跨界 | `test_i2_*`（4 项） | 外键访问 `KeyError`；正常命名空间仍可用 |
| A3 发送不可越界 | `test_i3_*`（5 项） | 无令牌写入被拒；未观察会话被拒；卸载即撤销 |
| A4 崩溃不传主机 | `test_i4_os_exit_*` / `test_i4_sigkill_*` | 主机进程存活 |
| A5 挂死可回收 | `test_i4_infinite_loop_times_out` | <6s 返回超时，主机存活 |
| A6 异常不泄露 | `test_i4_exception_message_*` | 异常消息中的 token 不出现 |
| A7 子进程不可 import 宿主 | `test_i4_child_cannot_import_host_package` | 抛 `PluginCrashedError` |
| A8 API fail-closed | `test_i5_*`（6 项） | 非本机 404；本机放行 |
| A9 SQL 标识符白名单 | `test_i6_*`（2 项） | 注入串 `ValueError`；真实表名通过 |
| A10 能力模型未松动 | `test_capability_two_gate_model_unchanged` | 已批准未声明仍被拒 |

### 4.3 手工对抗验收（建议每次发版执行）

```powershell
.\.venv\Scripts\python.exe _probe_escape.py    # 封装层向量
.\.venv\Scripts\python.exe _probe_isolation.py # 进程隔离向量（看 "HOST STILL ALIVE"）
```
> 这两个脚本在复审结束后已删除；逻辑已固化进 `tests/test_plugin_isolation.py`。

---

## 5. 残余风险（诚实披露，未解决）

| 风险 | 等级 | 说明 | 部署层缓解 |
|---|---|---|---|
| 插件可读写文件系统 | 高 | 同用户权限，可读 `.env`、数据库、密钥文件 | 容器只读挂载 + 独立 uid |
| 插件可自由出站 | 高 | `import requests` 可绕过 `SafeHttpClient` | 网络策略 / egress 白名单 |
| 插件可 `ctypes` / 反射篡改 | 中 | 同进程无解 | 子进程 + seccomp |
| Windows 无内存配额 | 中 | 内存炸弹可耗尽机器 | 作业对象内存上限 / 容器 |
| 插件加载即执行 | 中 | import 期任意代码 | 仅加载可信来源 + 审批 |
| 审计可被同进程插件关闭 | 中 | `monkeypatch` | 隔离模式 + 审计外送 |
| 插件 API 无 JWT | 高（部署） | ✅ 已修复 | 非本机来源必须有 `Bearer` 令牌；loopback 免令牌只是便利 |
| 正则脱敏可绕过 | 低 | base64/语义改写 | 纵深防御，不承担唯一职责 |

**第 3 层部署红线（必须遵守，否则第 1、2 层形同虚设）**：

1. 插件以**独立低权限 uid** 运行，不可读写宿主机 `.env` / 数据库
2. 容器内**只读挂载**插件目录，`--cap-drop=ALL`，`no-new-privileges`
3. 出站网络**默认拒绝**，按需白名单
4. `/api/plugins` 与 `/api/security` 对外暴露前必须启用令牌鉴权（设置
   `SOAPBOT_INIT_TOKEN` 并完成一次登录）；loopback 免令牌分支仅适用于单机部署
5. 仅安装**已审阅源码**的插件；`manifest` 的 `trust` 字段是人工决策记录，不是技术控制

---

## 6. 结论

- 本次**实测复现并修复 6 个真实缺陷**（4 高危 / 1 中危 / 1 低危）
- 新增 **30 项**隔离回归测试，全量 **435 passed / 1 skipped**，`ruff` 零告警，`pip-audit` 零漏洞
- **「任何情况下均无法影响主机」在同进程架构下不可达**——已在 §0 与 §5 明确说明，未做美化
- 已交付第 1、2 层边界并逐条实测；第 3 层给出可执行的部署要求，明确其**不属于本仓库能提供的保证**
- 复审结论：**在遵守 §5 部署红线的前提下**，插件即使恶意，也无法破坏主机状态、审计链与对其他会话的可用性；**不遵守时，第 1、2 层只能降低概率，不能阻止**——这一点必须让运维者知道，而不是留在一份看起来全绿的报告里。

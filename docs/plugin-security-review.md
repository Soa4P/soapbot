# 插件体系安全复审报告

**日期**：2026-10-28
**范围**：`src/soapbot/plugins/`（manifest / sandbox / context / loader / dispatch / base）、`src/soapbot/security/crypto.py`、`src/soapbot/api/plugins.py`、`data/plugins/`（3 个示例插件）、依赖清单
**方法**：逐行读实际实现 → 对每个可疑点写探针复现 → 确认可复现后才计为漏洞 → 修复 → 独立于测试套件的探针复核 → 全量回归

> 复审原则：**只记录复现出来的问题**。未复现的怀疑点归入第 6 节「已检查且确认无问题」，不虚报。

---

## 1. 结论摘要

| 等级 | 数量 | 状态 |
|---|---|---|
| 高危 | 4 | 全部已修复并复核 |
| 中危 | 3 | 全部已修复并复核 |
| 高危（依赖） | 1（130 项 advisory / 6 个包） | 已清零 |
| 中危（功能失效） | 1 | 已修复 |

- 新增复审回归测试 **75 项**（`tests/test_wave4_plugin_review.py`）
- 全量测试 **405 passed, 1 skipped**（跳过项为 Windows 符号链接用例）
- `ruff check` 零告警
- 依赖漏洞 **130 → 0**
- 独立探针复核：**ALL FIXES HOLD**

---

## 2. 高危问题（已修复）

### R1 · SSRF：云厂商元数据地址未被拦截

| 项 | 内容 |
|---|---|
| **等级** | 🔴 高危 |
| **位置** | `plugins/sandbox.py` · `_assert_ip_public` |
| **复现** | `assert_url_allowed("http://100.100.100.200/latest/meta-data/")` → 通过 |

**成因**：防护依赖 `ipaddress.IPv4Address.is_private`。该属性对大多数 IANA 特殊用途网段返回 True，但**不包含 `100.64.0.0/10`**（运营商级 NAT）。阿里云元数据服务正位于 **100.100.100.200**。同理 `100.64.0.1` 等内网地址也被放行。

**危害**：持 `http` 能力的插件可为攻击者取得实例的临时访问凭据（STS token），进而访问该机器有权访问的全部云资源。这是云环境中最常被利用的单点。

**修复**：增加显式 `_BLOCKED_NETWORKS` CIDR 列表（CGNAT、TEST-NET、benchmarking、IPv6 ULA/link-local/multicast、NAT64、6to4 等），并在最后要求 `addr.is_global` 为真——**fails closed**：未来 IANA 新增特殊网段时默认被拒，而不是默认放行。

> 为什么用 CIDR 而非更多 `is_xxx` 标志：那些标志的语义由 Python 版本决定，可能静默改变；写死的 CIDR 不会「恰好不再匹配」。

---

### R2 · SSRF：TOCTOU（预检后二次解析）

| 项 | 内容 |
|---|---|
| **等级** | 🔴 高危 |
| **位置** | `plugins/sandbox.py` · `SafeHttpClient.fetch` |
| **问题** | 校验流程为「解析 → 校验 → 把**域名**交给 httpx」。httpx 连接时会**再次解析**，攻击者用 DNS rebinding 让首次返回公网 IP、二次返回 127.0.0.1 |

**危害**：绕过全部解析层检查，直达内网或元数据服务。

**修复**：解析校验后**把连接目标钉死为已校验的 IP**（`_pin_url_to_ip`），同时显式设置 `Host` 头、并通过 `sni_hostname` 扩展保持 TLS 证书仍按原域名校验。这样二次解析根本不会发生。

> 若只 pin IP 不设 SNI，证书校验会拿 IP 去比对而失败；开发者此时最容易顺手关掉校验——那等于用一个更严重的问题换掉一个 SSRF。

---

### R3 · SSRF：非规范 IP 字面量绕过

| 项 | 内容 |
|---|---|
| **等级** | 🔴 高危 |
| **位置** | `plugins/sandbox.py` · `assert_url_allowed` |
| **复现** | `http://127.1/`、`http://2130706433/`、`http://0x7f.0.0.1/`、`http://0177.0.0.1/` |

**成因**：`ipaddress.ip_address()` 只接受规范写法。上述字符串在 Linux/glibc（以及部分 HTTP 客户端）中会被解析为 127.0.0.1，但 Python 拒绝解析，于是**字面量检查被跳过**；随后 `resolve_and_verify` 在 Windows 上直接失败（不可解析 → 抛错，恰好安全），但在解析成功的平台上就是真实绕过。

**修复**：新增 `_looks_like_ip_literal()`，凡纯数字 / 点分 / `0x` 十六进制构成的 host 一律拒绝，要求使用规范 IP 或域名。同时 `_assert_ip_public` 会解开 IPv4-in-IPv6（`::ffff:`、6to4、Teredo）后按 IPv4 规则复查——否则 `::ffff:169.254.169.254` 作为 IPv6 全局地址可通行。

---

### R4 · 审计日志泄露密钥

| 项 | 内容 |
|---|---|
| **等级** | 🔴 高危 |
| **位置** | `security/audit.py` · `AuditLog.record` |
| **复现** | `detail="GET https://api.example.com?token=sk-live-abcdefgh12345678"` → 原样存入并可从 `GET /api/security/audit` 取出 |

**危害**：审计流会推送到 WebUI 日志中心并落盘。插件把带凭据的 URL 写进 `detail`（这是最常见写法），等于**由负责记录安全事件的组件发布密钥**。且该数据会长期留在日志与前端内存中。

**修复**：在 `record()` 内统一脱敏 `detail`（`sk-*`、`Bearer *`、`key/token/secret/password=*`）并限长 500。放在 record 内而非各调用点，是因为「每个调用点都记得脱敏」这件事在代码增长后必然失守。

---

## 3. 中危问题（已修复）

### R5 · `load()` 的路径穿越仅靠巧合拦住

| 项 | 内容 |
|---|---|
| **等级** | 🟠 中危 |
| **位置** | `plugins/loader.py` · `PluginLoader.load` |

**现状**：`name` 来自 HTTP 路径参数，直接 `plugins_dir / name`。实测 `load("../outside_evil")` **被拦住**——但拦住它的是「manifest 里的 name 与路径名不一致」这条**无关检查**。

**危害**：这是「偶然安全」。一旦某个插件目录的 manifest 也写 `../outside`，或将来有人为了「宽松一点」删掉名称一致性检查，就会立刻变成从插件目录外执行任意代码。

**修复**：在拼接路径**之前**用 `^[a-z][a-z0-9_-]{1,40}$` 校验名称，并补充 symlink 检查与 `resolve()` containment 兜底（`load()` 可不经 `discover()` 直接被 API 调用）。

---

### R6 · 清单文本与插件输出允许 HTML/JS（存储型 XSS）

| 项 | 内容 |
|---|---|
| **等级** | 🟠 中危 |
| **位置** | `plugins/manifest.py` · `_clean_text`；`plugins/sandbox.py` · `scrub_plugin_output` |
| **复现** | `description: "<img src=x onerror=alert(1)>"` 被原样接受；插件返回 `<script>` 亦原样透出 |

**危害**：manifest 是**插件作者在审核之后仍可自由修改**的文件。若前端以 HTML/Markdown 渲染插件列表或调试台，即形成对**运营者管理面板**的存储型 XSS——受害者是权限最高的那个人。同一字符串还会进入日志、API 响应、未来导出。

**修复**：新增 `neutralise_markup()`，转义 `<`/`>` 使标记在任何渲染面（HTML、日志、导出、移动端）均为惰性文本；并额外 defang `javascript:`/`vbscript:`/`data:` 伪协议（HTML 转义挡不住 Markdown 链接语法）。

> 选择「转义」而非「删标签」：删标签会改变语义（`<b>` 消失、`<a href>` 变裸文本），且白名单需要持续跟进新标签。转义不改变可读性，也不需要维护白名单。

---

### R7 · `ctx.send` 因校验与其格式互斥而永久失效

| 项 | 内容 |
|---|---|
| **等级** | 🟠 中危（功能完全不可用） |
| **位置** | `plugins/context.py` · `send` |
| **复现** | `_STORAGE_KEY_RE.match("onebot11:group:123456")` → `None` |

**成因**：校验复用了**存储键**字符集（禁止 `:`），而 session_key 的真实格式就是 `adapter:scene:target`。结果 `ctx.send` 对**100% 的合法输入**抛异常。

**危害**：`send` 能力实际上从未可用。这类缺陷最危险的地方在于**它伪装成安全**——测试若只断言「非法输入被拒」会全部通过，没人发现合法输入也被拒。

**修复**：拆出独立 `_SESSION_KEY_RE`，接受真实格式并拒绝异常形态。同时保留「只能发给本插件观察过的会话」这条**真正的边界**：形状校验是廉价第一道门，观察名单才是限制可达范围的那道。

---

## 4. 依赖漏洞（已清零）

| 项 | 内容 |
|---|---|
| **等级** | 🔴 高危 |
| **工具** | `pip-audit`（实测，非估算） |
| **原始** | **130 项 advisory，涉及 6 个包** |

| 包 | 原版本 | 新版本 | 主要问题 |
|---|---|---|---|
| `starlette` | 0.41.x | 1.10.0 | multipart DoS、Range 头解析、静态文件路径处理等多个 |
| `cryptography` | 44.0.0 | 50.0.2 | OpenSSL 相关内存/解析问题 |
| `pillow` | 11.1.0 | 13.0.0 | 多个图像解析越界（Wave 2 GIF 抽帧直接依赖） |
| `python-multipart` | 0.0.20 | 0.0.32 | multipart 解析 DoS |
| `pyjwt` | 2.10.1 | 2.15.1 | 算法/声明校验绕过类问题 |
| `pytest` | 8.3.4 | 9.0.3 | 开发依赖 |

**处理过程与取舍**（值得记录，因为「升级以修漏洞」本身是有风险的操作）：

1. `fastapi 0.115.6` 约束 `starlette<0.42`，无法只升 starlette。故将 fastapi 升至 `0.162.0`（跨大版本），**当即验证**应用启动、`/api/health`、`/api/plugins`、`/api/security/*` 均正常。
2. 先升 `pytest 9.0.3` 时与 `pytest-asyncio 0.25` 冲突，测试基础设施不可用。判断：**为修开发依赖漏洞而破坏测试基础设施是净损失**，故回退；随后发现 `pytest-asyncio 1.4.1` 可与之共存，才一并升级。
3. 每次升级后立即全量回归（405 项）确认无破坏，最终 `pip-audit` 复扫 **0 漏洞**。

**验证**：`tests/test_wave4_plugin_review.py::test_review_no_known_dependency_vulnerabilities` 在 CI 中直接断言，未安装 pip-audit 时 **skip 而非 pass**（静默通过等于宣称了未做的检查）。

---

## 5. 功能缺陷（已修复）

### R8 · `on_notice` / `cron` 可注册但从未被分发

| 项 | 内容 |
|---|---|
| **等级** | 🟠 中危（静默失效） |
| **位置** | `plugins/dispatch.py` |

**问题**：`ctx.on_notice` / `ctx.cron` 能成功注册并返回，但没有任何代码调用它们。插件作者会认为功能正常，实际永不触发——**静默失败比报错更糟**。

**修复**：新增 `dispatch_notice()` 与 `PluginCronRunner`：

- notice 分发：单 hook 超时 2s、异常不影响其它插件、日志只记异常**类型**
- cron 执行：每次运行**成功也审计**（`cron:<name>`），因为无人值守的静默失败与「从未运行」在现象上无法区分；单个 job 失败不阻断其它
- cron 的 `CallerContext` 为匿名空会话——**不虚构一个真实用户身份**，否则 cron 就能借他人权限行动

调度本身交给调用方（APScheduler），避免自建 cron 匹配逻辑与调度器对「是否到期」产生两套判定。

---

## 6. 已检查且确认无问题的项

复审要求里点名的方向，逐项给出结论与依据：

### 6.1 SQL 注入
**无风险。** 插件层不拼接 SQL；全部查询走 SQLAlchemy 参数化。插件**无法**直接访问数据库连接——能力模型中没有 `db` 能力，`PluginContext` 也不暴露 session。插件只能通过 `ctx.storage`（键值，无 SQL）或宿主提供的窄接口。

### 6.2 命令注入
**无风险。** 全代码库无 `os.system` / `subprocess` / `shell=True` 调用；插件无法申请执行外部命令的能力（能力枚举里没有）。

### 6.3 反序列化
**已防护。** manifest 用 `yaml.safe_load`（非 `load`）。`test_yaml_python_object_tag_is_not_executed` 验证 `!!python/object/apply` 被拒而非执行。插件存储值强制 JSON 可序列化，不接受活对象。

### 6.4 权限与访问控制
**设计合理，已复检。** 三处加固复核通过：
- 命令/工具授权由**宿主**按已解析 `Principal` 重算，不采信插件的 `min_role` 声明
- 能力双重门（`declared ∩ approved`）未被本次修复削弱，有 guard-rail 测试锁定
- `send` 的可达范围同时受形状与观察名单约束

### 6.5 密钥存储
**良好。** `EncryptedPluginStorage` 用 Fernet 加密落库；命名空间隔离（同名键互不可见）；错密钥 `get()` 返回默认值而非半解密乱码（返回乱码更危险——调用方会当合法数据用）。

### 6.6 错误处理不泄露敏感信息
**已确认。** 三条路径分别验证：
- 插件命令异常：只回「命令执行失败」通用文案
- 工具异常：只回「工具执行失败」，不含异常类型
- API 加载失败：返回 `PluginLoadError`（宿主包装），插件自选异常类型不外泄；真实原因只进审计

### 6.7 日志合规
**已确认并加固。** 插件 hook 日志只记异常**类型**；审计 `detail` 已脱敏；插件失败日志不含插件消息正文。不记录完整消息内容（仅 `text[:500]` 用于 hook），不记录用户敏感字段。

### 6.8 输入长度与资源
**已确认。** 命令参数有数量/长度上限；tool 参数必须为 dict；HTTP 响应体 1 MiB 上限、body 1 MiB、超时上限；handler 8s 超时（防止一个插件挂住整个会话）。

---

## 7. 修复后复审验证

独立于测试套件的探针（`_recheck.py`，已删除，逻辑并入测试）：

```
--- literal URL check ---
  blocked  http://100.100.100.200/latest/meta-data/     ← R1
  blocked  http://2130706433/                            ← R3
  blocked  http://127.1/                                 ← R3
  blocked  http://[::ffff:169.254.169.254]/              ← R3
  allowed  https://api.example.com/v1                    ← 无假阳性
--- DNS resolution check ---
  blocked  169.254.169.254.nip.io                        ← R2
--- markup neutralisation ---
  ok  '<script>alert(1)</script>' -> '&lt;script&gt;...'
RESULT: ALL FIXES HOLD
```

测试命令：

```powershell
$env:PYTHONPATH="f:/soapbot/src"
.\.venv\Scripts\python.exe -m pytest tests/test_wave4_plugin_review.py -q   # 75 passed
.\.venv\Scripts\python.exe -m pytest tests/ -q                              # 405 passed, 1 skipped
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off              # No known vulnerabilities
.\\.venv\Scripts\ruff.exe check src/ tests/                                 # All checks passed
```

---

## 8. 剩余风险（诚实披露，未修复）

| 风险 | 等级 | 说明与建议 |
|---|---|---|
| 插件绕过 facade 直接 `import httpx` 出站 | 中 | 同进程内**无法**由应用层阻止。需 OS 级隔离（独立进程 + seccomp / 容器 / 网络策略） |
| 插件读取进程内其它密钥 | 中 | 同上，共享地址空间。缓解：密钥按插件派生、用完即弃 |
| 插件在 import 时执行代码 | 中 | 加载即执行，本质无法避免。靠「显式审批 + 只加载可信来源」控制 |
| 多轮渐进式诱导模型调用不利工具 | 中 | 工具侧有角色闸门，但**语义层**未覆盖（无法判定「这次调用是否正当」） |
| 插件管理 API 未鉴权 | **高（部署时）** | ✅ 已修复：非本机来源需签名令牌；loopback 免令牌仅为本地便利 |
| 正则类注入/脱敏必然可被绕过 | 低 | base64/rot13/语义改写等未覆盖。已作为纵深防御的一层，不承担唯一职责 |

**部署红线（修订）**：`/api/plugins` 与 `/api/security` 对外暴露时，必须已完成令牌鉴权
配置（`SOAPBOT_INIT_TOKEN` → `POST /api/auth/login`），并且不要保留可被他人读取的
`data/init_token.txt`。令牌为无状态 JWT：撤销 = 删除 `data/jwt.key` 后重启。

---

## 9. 给插件作者的强制约束（复审后明确）

1. **不要在插件里自行脱敏输出** —— 宿主统一处理，重复实现只会漏
2. **不要向用户展示 `ctx.storage` 里的值** —— 存密钥，不回显；需要确认时返回长度或指纹
3. **`min_role` 只是意图声明** —— 宿主的判定才是权威，不要依赖它做业务逻辑
4. **不要假设 `http` 能访问内网** —— 即使声明并获得授权，私网与元数据地址一律被拒
5. **manifest 文本会被转义** —— 不要在其中写 HTML，前端不会渲染成标签

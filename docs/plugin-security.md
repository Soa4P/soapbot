# 插件体系安全模型

> 本文回答：**第三方插件能否在加载、运行、输出任一环节越权、注入或泄露数据？**
> 结论见各节，验证见 `tests/test_wave4_plugin_*.py`（198 项）。
>
> **2026-10-28 已完成独立安全复审**，发现并修复 8 个真实缺陷（含 4 个高危 SSRF / 审计泄露问题）与 130 项依赖漏洞。详见 [`plugin-security-review.md`](./plugin-security-review.md)。

## 0. 先说清楚边界：这不是沙箱

插件**默认在自己的子进程里运行**（`builder.py` 的 `isolate=True`；同进程执行需要显式改成 `False`）。但这仍然**不是沙箱**：没有 seccomp、没有 namespace、没有文件系统或网络的系统级限制，子进程能做的事和宿主进程一样多——它带来的是可观测、可终止、可归因，不是权限边界。因此必须诚实地说明本文能保证什么、不能保证什么。

**能保证**（有测试）：

- 插件通过**公开 API** 能做的事，严格受能力声明 + 运营者授权双重约束
- 未声明/未授权的能力调用**抛异常**，不是静默忽略
- 插件输出在发往群聊前被脱敏、截断、canary 校验
- 插件出站 HTTP 受 SSRF 防护（私网、元数据服务、重定向、体积）
- 插件存储加密且命名空间隔离
- 加载/卸载/重载/拒绝全程审计，可归因到具体插件

**不能保证**（诚实披露）：

- 恶意插件 `import httpx` 自行发请求、`open()` 读文件、`subprocess` 起进程 —— 这些绕过 facade，**本层拦不住**
- 插件读到进程内存中其它密钥（同进程共享地址空间）

因此本层的真实价值不是"阻止恶意插件"，而是：**让善意插件难以犯错、让恶意插件的行为可观测可归因、让越权必须显式而非顺带**。独立进程这一半已经就位（`plugins/isolation.py` + `supervisor.py`，运行时由 `posture` 的 `isolation.process` 检查报告）；剩下的是 seccomp / 容器级限制，仍列在后续待办。

## 1. 双重能力门：声明 + 授权

```
manifest.capabilities          ← 插件声明（插件自己写的文件）
loader._approved[plugin]       ← 运营者授权（宿主自己的状态，落盘在 data/plugin-approvals.json）
effective = declared ∩ approved
```

**为什么要两道**：如果只有声明，插件改一行 manifest 就自我提权；如果只有授权，运营者会被诱导"全选批准"。交集语义下，插件新增能力必须回来重新审批。

**授权为什么必须落盘**：`_approved` 曾经只是内存字典，一旦如此，上面这套推理在重启后
全部失效——重启后没有任何插件持有授权，WebUI 却仍显示"已启用"。现在
`plugins/approvals.py::ApprovalStore` 以原子写入把批准记录持久化在 `data/` 下（不在
插件目录内，否则升级插件时会被一起替换），启动时 `load_approved()` 仅加载**有持久批准
记录**的插件。选择来源是"人做过的持续决定"，不是"目录存在"——未批准的目录仍被
`load()` 拒绝。

清单摘要漂移（批准之后 manifest 被改）**只报告不阻断**：`GET /api/plugins` 返回
`approval.manifest_changed`。阻断会让每次正常版本升级都变成手工重新批准，实际后果是
运维习惯性点过警告——这类"每次都响"的检查通常以被忽略告终。真正的硬约束仍是能力交集，
它不依赖这条提示。

对应测试：`test_undeclared_capability_is_denied`、`test_unapproved_capability_is_denied`、`test_plugin_added_in_manifest_after_approval_needs_reapproval`

后者对应真实攻击：插件先只声明 `command` 通过审核，随后把 manifest 改成加上 `http`/`memory_read`。因为授权记录独立于 manifest，新增能力在 `grant.effective` 中不存在。

## 2. 清单校验：所有流向文件系统与 import 机制的字段

| 字段 | 攻击 | 防护 |
|---|---|---|
| `name` | `../../etc/cron.d/evil` 路径穿越 | `^[a-z][a-z0-9_-]{1,40}$`，拒绝首数字/大写/斜杠/`..` |
| `entry` | `os:system`、`main:__class__` | `module:attr` 白名单正则 + dunder 拒绝 + 顶层模块黑名单 |
| YAML 标签 | `!!python/object/apply:os.system` | `yaml.safe_load`（不是 `load`） |
| `requires` | `pkg @ https://evil/x.tar.gz` | 拒绝 URL/VCS/`@`；依赖**只声明不安装** |
| `author` | `"x\n2026-01-01 INFO loaded"` 伪造日志行 | 拒绝控制字符 |
| 目录名 | 与 manifest name 不一致 → 存储命名空间串台 | 强制一致 |
| 符号链接 | 指向插件目录外 | `is_symlink()` 拒绝 |

**依赖不自动安装**是重点：`pip install` on load 会把"安装插件"变成"执行插件作者从 PyPI 挑的任意代码"，是供应链漏洞的另一种写法。

对应测试：`test_path_traversal_and_bad_names_are_rejected`（12 例）、`test_hostile_entry_points_are_rejected`（13 例）、`test_yaml_python_object_tag_is_not_executed`、`test_dependency_urls_and_injection_are_rejected`（6 例）

## 3. 命令与工具：宿主复核，不信任插件声明

```
插件声明 min_role=ADMIN
    ↓（仅用于 UI 展示意图）
宿主从 Principal 重算角色 → 决定准不准
```

**为什么翻转决策权**：如果宿主信任插件的 `min_role`，恶意插件只要写 `min_role=MEMBER` 就能把任何能力开放给所有人 —— 那等于插件在决定授权，正是能力模型要消除的东西。

插件**无法提权任何人**：它只能通过 `caller.at_least(role)` 让宿主比较宿主已解析出的角色。

核心命令名被保留（`forget`/`kb`/`recall`/`timeline`/`help`/`ping`）。静默覆盖 `/forget` 是安全回退伪装成功能特性，因此注册期即拒绝。

对应测试：`test_plugin_admin_command_denied_for_member`、`test_plugin_admin_command_allowed_for_admin`、`test_tool_invocation_requires_permission`、`test_core_command_names_cannot_be_taken`

## 4. 输出侧净化：插件的每一条回复都要过宿主

插件是数据的**出口**。它产出的一切都会展示给群成员，因此走与核心回复相同的规则：

1. `strip_invisible` — 去零宽/双向控制字符（用于走私指令或让日志看起来是别的内容）
2. `redact` + 密钥正则 — 插件把自己的配置回显到聊天时，不能因此发布运营者的 API key
3. 长度截断 — 与核心回复同一预算，插件没有更大的嗓门
4. `leaked_canary` — 命中即丢弃整条回复

第 4 条对应一类具体缺陷：插件把检索结果或模型输出**原样透传**，说明它没把不可信内容当数据处理。canary 是这种失误的探针。

对应测试：`test_plugin_output_masks_secrets`（3 例）、`test_plugin_output_strips_invisible_characters`、`test_plugin_output_is_length_capped`、`test_canary_in_plugin_output_is_detected`、`test_tool_result_is_scrubbed`

## 5. SSRF：有 HTTP 能力的插件是本机的网络代理

插件选择目标，用的是**机器人的网络位置**，而插件作者平时没有这个位置。因此：

| 目标 | 危害 |
|---|---|
| `169.254.169.254` | 云元数据 → 临时凭据 |
| `127.0.0.1:6185` | 本机未鉴权管理 API |
| `10/172.16/192.168` | 内网横向 |
| `metadata.google.internal` | GCP 元数据 |

防护要点：

- **字面量 + 解析结果双检**：主机名可解析到私网地址（DNS rebinding），所以 `resolve_and_verify` 检查**所有** A 记录，不只第一条
- **拒绝重定向**：`http://169.254.169.254/` 作为 302 目标会直接走过预检，因为只校验了首跳
- **`trust_env=False`**：忽略代理环境变量，否则 `HTTP_PROXY` 会绕过全部检查
- **URL 内凭据拒绝**：`http://allowed@169.254.169.254/` 是经典过滤器绕过
- **头部白名单**：`Host`/`Authorization`/`Cookie` 拒绝；未知头部**报错**而非静默丢弃（静默丢弃让插件以为设置了实际没设）
- **体积/超时上限**：插件把 10GB 流进内存，是对整个进程的 DoS

对应测试：`test_ssrf_targets_are_blocked`（13 例）、`test_public_urls_are_allowed`、`test_dns_answer_to_private_range_is_blocked`、`test_http_client_rejects_forbidden_headers`

## 6. 敏感数据：加密落库、命名空间隔离、审计脱敏

- **加密**：`EncryptedPluginStorage` 用 Fernet，存储边界即加密。数据库 dump / 备份 / `git add data/` 都拿不到明文
- **隔离**：两个插件都写 `token` 互不可见；键名无路径语义，`../other/secret` 无法表达
- **类型约束**：值必须 JSON 可序列化 —— 防止插件存入活对象引用，让后续代码信任它
- **审计脱敏**：键名含 `token`/`secret`/`key`/`password` 自动打码；插件的异常消息**只记类型不记内容**（插件控制的消息可能含凭据）

对应测试：`test_storage_is_encrypted_at_rest`、`test_storage_namespaces_are_isolated`、`test_storage_key_traversal_is_refused`（6 例）、`test_plugin_secret_never_appears_in_audit`、`test_encrypted_storage_roundtrip_with_wrong_key_fails`

最后一项值得单说：错密钥时 `get()` 返回默认值而非半解密乱码。返回乱码更危险 —— 调用方会当成合法数据。

## 7. 加载 / 重载 / 卸载：可控、可回滚、可归因

| 规则 | 为什么 |
|---|---|
| 发现 ≠ 加载 | 能写 `data/plugins` 的人否则等于下次重启即代码执行 |
| 未审批拒绝加载 | 同上 |
| `untrusted` + 敏感能力需显式 opt-in | "可发网络请求 + 读记忆"应当是深思后的决定 |
| 导入失败包装为 `PluginLoadError` | 否则调用方分不清"插件坏了"和"宿主坏了" |
| 先卸载再加载 | 反序会有两个实例同时注册同名命令、双份 cron 触发（对外发请求的插件会发两次） |
| 失败不回落旧版本 | 静默跑旧代码会掩盖"更新没生效"，包括试图修的漏洞 |
| teardown 抛异常仍卸载 | 留着半死的注册比泄漏句柄更糟 |
| rmtree 前校验路径containment | `name="../.."` + rmtree = 任意目录删除 |

对应测试：`test_plugin_is_not_loaded_without_approval`、`test_untrusted_plugin_with_sensitive_capability_is_refused`、`test_failed_setup_rolls_back_modules`、`test_removing_plugin_directory_cannot_escape_root`、`test_teardown_failure_still_unloads`、`test_failed_reload_leaves_plugin_unloaded`

## 8. 输入校验：双向

- **入站**：命令名正则、参数个数与长度上限、`session_key` 形状、tool 参数必须是 dict
- **出站**：见 §4

`send` 额外限制：只能发给**本进程内该插件实际被调用过的会话**。这挡住"插件向任意群广播" —— 群号是猜得出来的，观察记录猜不出来。

## 9. 审计与配额

- 敏感能力**成功也记录**：知道某插件在往外发数据，正是审计的意义
- 拒绝记录带插件名，可 `GET /api/plugins/{name}/errors` 归因排查
- 配额分离：普通操作与敏感操作各一套滑动窗口，避免互相挤占或补贴

对应测试：`test_sensitive_use_is_audited_on_success_too`、`test_capability_denial_is_audited`、`test_sensitive_quota_is_enforced`、`test_tool_denial_is_audited`

## 10. 验收对照（计划 A5）

| 要求 | 状态 | 证据 |
|---|---|---|
| 示例插件仅用公开 ctx API 新增命令即生效 | ✅ | `test_plugin_command_works_end_to_end` |
| 仅用公开 ctx API 新增工具 | ✅ | `test_tool_executes_for_authorised_caller` |
| 热重载后生效 | ✅ | `test_hot_reload_picks_up_new_command` |
| 禁用后彻底卸载 | ✅ | `test_unload_removes_commands_completely` |
| 不改进核心代码 | ✅ | 三个示例插件仅 import `soapbot.plugins.base/context` |

## 11. 运营者配置

```env
# 默认 false。开启等于"允许任意人写的代码在本进程内运行"，仅用于临时审查。
SOAPBOT_ALLOW_UNTRUSTED_PLUGINS=false
```

插件目录：`data/plugins/<name>/plugin.yaml`

批准流程（必须显式指定每个能力）：

```http
POST /api/plugins/echo/approve
{"capabilities": ["command", "tool"]}

POST /api/plugins/echo/load
```

## 12. 验证

```bash
$env:PYTHONPATH="f:/soapbot/src"
.\.venv\Scripts\python.exe -m pytest tests/test_wave4_plugins.py `
    tests/test_wave4_plugin_security.py tests/test_wave4_plugin_tools.py `
    tests/test_wave4_plugin_api.py -q
# 198 passed
```

全量：`435 passed, 1 skipped`（跳过项为 Windows 符号链接测试），`ruff check` 无告警，
`pip-audit` 无已知漏洞。

> **2026-10-28 第二轮复审（隔离专项）**：实测确证并修复 6 个缺陷——能力网关自提权、
> 跨插件存储直读、发送目标任意注入、插件 API 仅靠绑定地址、FTS 表名拼接、无进程隔离。
> 新增 `plugins/isolation.py`（子进程执行器）与 30 项隔离测试。
> 详见 [`plugin-isolation.md`](./plugin-isolation.md)。

## 13. 残余风险清单

| 风险 | 等级 | 状态 |
|---|---|---|
| 插件绕过 facade 直接 `import httpx` 出站 | 中 | ⚠️ 同进程无解，需 OS 级隔离 |
| 插件读取进程内其它密钥 | 中 | ⚠️ 同上 |
| 插件通过 `import` 副作用执行代码 | 中 | ⚠️ 加载即执行，只能靠审批 |
| 多轮诱导模型调用不利工具 | 中 | 宿主工具侧有角色闸门，但语义层未覆盖 |
| 插件管理 API 未鉴权 | 高（部署时） | ✅ 已修复：非本机来源必须有签名令牌（`soapbot.security.tokens`） |
| 插件密钥文件被同机读取 | 低 | 0600 权限；主密钥分离存储 |

**部署红线（已解除，条件见下）**：`/api/plugins` 与 `/api/security` 现在要求
`Authorization: Bearer <token>`。本机（loopback）仍可免令牌访问，这是给单机操作者
的便利，**不是**安全边界——反向代理会让远端请求看起来来自 loopback。因此对外暴露时：

1. 设置 `SOAPBOT_INIT_TOKEN`，用 `POST /api/auth/login` 换取令牌；
2. 不要把 `data/init_token.txt` 或 `SOAPBOT_INIT_TOKEN` 留在可被他人读取的位置；
3. 令牌是无状态 JWT，撤销只能换密钥（删除 `data/jwt.key` 并重启）。

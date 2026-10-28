# soapbot 交付就绪度评估

评估时间：2026-10-28
方式：代码静态核查 + 真实进程级端到端探针（mock OneBot 协议端 + mock OpenAI 端点 + 真实 `soapbot start`）+ 全新克隆模拟
基线：`691 passed / 3 skipped`、`ruff` 全绿、`vue-tsc` 通过、`vite build` 通过

> **状态更新（同日晚于本评估）**：本文件记录的是**修复前**的状态，保留原样作为
> 问题清单与证据，不随后续改动重写——一份事后被改写成「当时其实没这么糟」的评估
> 没有价值。
>
> 其中可修的部分已在本轮修复，逐条对照见 `CHANGELOG.md` 的 `[0.1.0]` 段：
>
> | 本文件指出的问题 | 当前状态 |
> |---|---|
> | 零 git 提交、缺 LICENSE/.env.example/CHANGELOG/CI | 已补（提交本身需仓库所有者执行） |
> | 示例插件在 `.gitignore` 内，全新克隆 5 失败 + 24 错误 | 已修：插件移入 `src/soapbot/examples/`；全新克隆 `718 passed / 3 skipped` |
> | QQ 官方适配器被 @ 永远不唤醒 | 已修：`split_leading_at` 补 AT 段 |
> | 私聊在任何配置下不可用 | 已修：`build_access_policy()` |
> | 插件工具链路三层断裂 | 已修：`AIRequest.tools` + `ModelStage` 工具循环 + 隔离模式工具分表 |
> | notice 无生产者 | 已修：适配器产出 + `emit` 放行 + 运行时分发 |
> | 审批不持久、重启全丢 | 已修：`ApprovalStore` + 启动自动加载 |
> | 群管只有声明没有实现 | 已修：四个动作 + 四个命令 + 权限与越权拦截 |
> | 知识库无写入路径 | 已修：`ingest_document` + 三个 API + 面板上传 |
> | 声明了 4 个未使用依赖 | 已移除 |
>
> **仍然成立的限制**（未修，且不应假装修了）：插件间不互相调用、无插件市场、无 MCP、
> 无 STT/TTS、无流式输出、无 i18n、QQ 官方群管受平台限制未实现。
> 当前能力矩阵以 `README.md` 的「能力矩阵」一节为准。

---

## 结论

**尚未构成一个完整可交付的项目。**

它是一个架构清晰、安全设计超出同类项目、**单链路可实际跑通**的框架，但存在 3 个「交付即失败」级缺陷、6 个「宣称已实现但实际不通」的功能断点。

| 问题 | 结论 |
|---|---|
| 是否构成完整可交付项目 | **否** — 零 git 提交；示例插件在 `.gitignore` 里；全新克隆 5 失败 + 24 错误（已实测） |
| 插件是否真正集成并协同工作 | **部分** — 命令链路实测通；工具链路三层断裂；notice 无生产者；插件间零互调；审批不持久 |
| QQ 群机器人功能是否完整可运行 | **OneBot 是，QQ 官方否** — OneBot 全链路实测 PASS；官方适配器被 @ 永远不唤醒（实测 `(False, '')`） |
| 是否遵循参考仓库结构 | **架构精神是，能力覆盖面否** — 分层真实对应 AstrBot；插件市场/MCP/工具调用/STT-TTS/流式/i18n/CI 全缺 |

---

## 一、可交付性 —— 否

### 1.1 阻断级：仓库从未提交，且不自包含

```
$ git rev-list --count HEAD
fatal: ambiguous argument 'HEAD': unknown revision
$ git status --porcelain -uall | wc -l
156
```

零提交、156 个未跟踪路径。更关键的是**示例插件放在 `data/`，而 `data/` 被 gitignore**：

```
$ git check-ignore -v data/plugins/echo/main.py
.gitignore:23:data/    data/plugins/echo/main.py
```

实测影响（复制 `src/ tests/ config/ pyproject.toml requirements.txt`，不含 `data/`）：

```
5 failed, 662 passed, 3 skipped, 24 errors
```

补回 `data/plugins` 后：`691 passed, 3 skipped`。

**唯一原因就是仓库里没有示例插件**。而这 4 个插件（admin/echo/help/remind）是插件子系统的唯一可运行示例，也是 6 个测试文件的 fixture 来源（`test_wave4_plugins`、`test_wave4_plugin_api`、`test_wave4_plugin_review`、`test_wave4_plugin_security`、`test_wave4_plugin_tools`、`test_plugin_isolation`）。

**判断**：当前工作目录能跑，但它不是「clone 下来就能跑」的项目。交付物 = 工作目录快照，不是仓库。

### 1.2 缺失的交付基础件

| 文件 | 状态 | 后果 |
|---|---|---|
| `LICENSE` | 缺失 | README 声明 MIT 但无许可文件 → 法律上默认保留所有权利 |
| `.env.example` | 缺失 | `.gitignore` 有 `!.env.example` 白名单，说明本应有 |
| `CHANGELOG.md` | 缺失 | 11 个 wave 无版本记录 |
| `.github/workflows/` | 缺失 | 691 个测试无 CI 执行点 |
| `Makefile` | 缺失 | 测试/构建/lint 散落在文档里 |

### 1.3 依赖声明与实际不符

```
structlog        -> 0 处引用
watchdog         -> 0 处引用
python-multipart -> 0 处引用
```

三个生产依赖零使用。不阻断交付，但说明依赖清单没跟着实现走过一遍。

---

## 二、插件是否真正集成并协同 —— 部分

按四条链路逐一实测。

### 2.1 命令链路：✅ 真实可用（已实测）

真实 TCP socket：mock OneBot 协议端 → 真实 uvicorn → HTTP API 审批并加载 `echo` → 推群消息 `/echo ...` → 收到回发。

```
[probe] soapbot 已连接到 mock 协议端
[probe] 收到回发: '插件手册可用'
RESULT: PASS
```

加载后命令表：

```
registered_commands: ["echo", "echo_text", "pladmin", "plsecret", "plughelp",
                      "purge-demo", "remember", "rules", "whereami", "whoami"]
```

`PluginCommandStage` 在 `CommandStage` 之后，核心命令名在 `validate_command_name` 保留，插件无法遮蔽 `/forget`。这条链路扎实。

### 2.2 工具调用链路：❌ 整条断裂（三个断点串联）

`manifest` 有 `tool` 能力、插件用 `@ctx.tool` 注册、`PluginToolRegistry` 有完整角色校验与输出消毒 —— 但三处同时断开：

**断点 1：隔离模式下工具表恒为空。**
默认 `isolate=True`。worker 里 `@ctx.tool` 只写 `self._commands` 并在 `_api` 打 `"kind":"tool"` 标记（`supervisor.py:287-293`）。宿主 `register_proxied_command` 只填 `context._commands`，`context._tools` 从不填充；而 `all_tools()` 遍历 `loaded.context.tools`（`loader.py:767`）。

实测（已加载 echo，它声明了 tool 能力）：

```
registered_tools: []
```

**断点 2：即使有工具，模型也拿不到。**
`PluginToolRegistry.available_for()` 在 `src/` 内零调用方（仅 `dispatch.py:308` 定义处）。唯一测试 `test_wave4_plugin_tools.py:47/50` 直接调注册表本身 —— 测的是注册表，不是链路。

**断点 3：即使拿到，也传不出去。**
`ChatRequest` 有 `tools` 字段、`openai_compat.py:51` 会塞进 payload，但 `AIRequest` 无 tools 字段，`ModelStage` 源码中 `"tools"` 出现 0 次，`AIEngine.respond()` 无 tool_calls 多轮循环。

**判断**：C6 承诺的「工具/function-calling 注册」是**一个三层完备、但没人接通的安全实现**。安全做得好（角色重校验、canary、scrub），可它就是跑不起来。这比没实现更危险 —— 文档让人以为有。

### 2.3 notice 链路：❌ 无生产者

`dispatch_notice` / `has_notice_hooks` / `ctx.on_notice` 都实现了，`Capability.NOTICE` 也在能力表里。但：

- `has_notice_hooks()` 零调用；`PluginManager.on_notice()` 零调用
- 适配器不产生 notice：`onebot11.py:323` 是 `if post_type != "message": return`（notice/request 全丢）；`qq_official` 只订阅 `public_messages`/`direct_message`

**判断**：`on_notice` 是死路。声明 `notice` 能力的插件，钩子永不触发。

### 2.4 插件间协同：❌ 不存在

- `PluginContext` 公开面**没有** `ctx.use()` / `get_plugin()` / `call_plugin()`
- `EventBus.subscribe()` 定义了但全项目**零调用**；只有 `runtime.py:142` 单向 `publish("message.processed")`
- 唯一公共通道是宿主：命令表合并（只给 UI 看）、消息钩子（只读/2s 超时/不可改写）

`help` 插件 docstring 把它写成设计：`ctx.commands` only returns what this plugin registered, so a plugin cannot use it to map other plugins' surfaces。

**判断**：这是**刻意的星型、无互调模型**。作为安全设计站得住（A 无法经 B 提权、无法枚举别人）。但作为「协同」不成立 —— 插件是彼此隔离的岛屿。若交付要求含协作，此项为零。

### 2.5 审批不持久：重启即全部丢失

`PluginLoader._approved` 是纯内存 dict（`loader.py:201`），无落盘。实测：

```
加载后:          ["admin","echo","help","remind"]
重启后 loaded:   []
重启后 approved: []
重启后 granted:  [("admin",[]),("echo",[]),("help",[]),("remind",[])]
```

且 `app.py:26` 明确「discovery-only: installed plugins are listed, never auto-loaded」。

**判断**：每次重启后必须逐个「审批 + 加载」。4 个 = 8 次点击，20 个 = 40 次。一个要人工重做全部配置才能恢复服务的系统，不是可运维的系统。

### 2.6 小结

| 链路 | 实现完整度 | 实际可用 |
|---|---|---|
| 命令 | 高 | ✅ 实测通过 |
| 消息钩子（只读） | 高 | ✅ 但只读，无法产生回复 |
| 定时任务 | 高（上轮修了 `expr` 忽略缺陷） | ⚠️ 需插件先被加载 |
| 工具调用 | 高（安全层）/ 零（接线） | ❌ 三层断裂 |
| notice | 高 / 零生产者 | ❌ 死路 |
| 插件互调 | 无 | ❌ 设计上不提供 |
| 跨重启状态 | 无 | ❌ 全部丢失 |
| 进程隔离 | 高，默认开启 | ✅ `doctor` 报 `isolation.process ok` |

---

## 三、QQ 群机器人是否完整可运行 —— OneBot 是，官方否

### 3.1 OneBot v11：✅ 实测可运行

真实 socket（非 TestClient）：

```
[probe] protocol端 ws://127.0.0.1:51731  llm 127.0.0.1:6391
[probe] soapbot 已连接到 mock 协议端
[probe] 收到回发: '收到，这是探针回复。'
[probe] RESULT: PASS
```

前置条件确实齐备：`adapters.yaml` 支持 forward/reverse，`app.py:153` 从文件构建 `ProviderRouter`，`build_runtime` 按配置装配，`runtime.start()` 逐个连接，调度器同时驱动插件 cron 与额度清扫。**这一段是本轮最有价值的成果。**

### 3.2 QQ 官方适配器：❌ 阻断级 —— 被 @ 永远无法唤醒

本轮新发现，比此前记录的任何问题都严重。

`qq_official.py:137` 在构造 `IncomingMessage` 前先 `_strip_at_prefix(content)` 抹掉 `<@!botid>`，然后只产生 `MessageSegment.text(...)`，**不产生 AT 段**。而 `WakePolicy.is_woken()`（`stages.py:122-133`）在群聊里先找 AT 段，找不到才看唤醒词：

```
official group '@bot 你好' -> (False, '')      ← 不唤醒
onebot11 group '@bot 你好' -> (True, 'at')     ← 唤醒
```

**后果**：QQ 官方群里，用户正常 @机器人 说话，机器人**完全不回应**。除非额外打出人格卡唤醒词（`soapbot`），或消息里恰好含 `/`。

该适配器在测试套件里**零覆盖**：

```
$ Select-String -Path tests/*.py -Pattern "qq_official"
（无结果）
```

`_strip_at_prefix` 无测试、`require_at_in_group` 与官方适配器的交互无测试。691 全绿掩盖了「官方渠道基本不可用」。

### 3.3 私聊：❌ 永久关闭，配置项是死的

`AccessPolicy` 说私聊默认拒绝、需 `private_allowlist` 或 `allow_all_private` 打开。`settings.allow_unknown_private` 从 `app.py:169` 传进 `build_runtime`……然后没有下文。实测：

```
private, allow_unknown=False -> (True, 'private_not_allowed')
private, allow_unknown=True  -> (True, 'private_not_allowed')   ← 开关无效
group                        -> (True, 'not_woken')
```

`build_runtime` 函数体中 `allow_unknown_private` 出现次数 = 1（参数声明本身），且 `config.py` **没有** `private_allowlist` 字段。**私聊在任何配置下都不可用**，`SOAPBOT_ALLOW_UNKNOWN_PRIVATE` 是不被读取的开关。

### 3.4 群管能力：❌ 只有声明，没有实现

`onebot11.py` 声明了 `MUTE/KICK/RECALL/FORWARD`，但：

```
set_group_ban / set_group_kick / delete_msg / send_group_forward_msg -> 0 处
```

`send()` 只做 `send_group_msg` / `send_private_msg`。计划 C1 写的「群管基础能力（禁言/撤回/合并转发按能力声明降级）」，实际是**只做了能力声明和降级框架，零具体操作**。

### 3.5 适配器无法热更新

`/api/adapters` 只读；全部写接口只有 `auth/login`、`auth/refresh`、`plugins/{name}/approve|load|reload|unload`。改 `adapters.yaml` 必须重启进程 —— 对「管理面板」而言，最常见的运维动作（换 QQ 号、改 ws 地址）需要中断服务。

### 3.6 功能矩阵

| 能力 | OneBot v11 | QQ 官方 |
|---|---|---|
| 连接/重连 | ✅（reverse 无 token 拒绝启动） | ⚠️ 未实测（botpy 可选依赖） |
| 群 @ 唤醒 | ✅ 实测 | ❌ **阻断** |
| 唤醒词 | ✅ | ✅（绕开 @ 的唯一办法） |
| 群聊回复 | ✅ 实测 | ⚠️ 代码完整，但先要过唤醒关 |
| 私聊 | ❌ 永久关闭 | ❌ 永久关闭 |
| 图片入站/出站 | ✅ / ✅ | ✅ / ⚠️ 降级为文本 |
| 群管 | ❌ 未实现 | ❌ 平台不支持 |
| 被动回复窗口 | — | ✅ `quota_hint` 有实现 |
| 流式输出 | ❌ Provider 有 `stream()`，`ModelStage` 从不调用 | 同左 |

---

## 四、是否遵循参考仓库结构与设计 —— 精神是，覆盖面否

参考仓库是 **AstrBot**（依据 `.codebuddy/plans/soapbot-qq-ai-bot_84279d40(未完成).md:3`：「仿 AstrBot 架构」）。

### 4.1 真实对应的部分（部分做得比参考更严谨）

| AstrBot | soapbot | 对应质量 |
|---|---|---|
| `astrbot/core/` 内核 | `core/` | 对应，阶段顺序写成「load-bearing」并解释原因 |
| 平台适配层 | `adapters/` + `core/adapter.py` | 对应，契约测试齐全 |
| Provider 抽象 | `providers/` | 部分（LLM+embed+vision，无 STT/TTS） |
| 消息/事件模型 | `core/message.py` | 对应，`session_key` 派生不可传参是更强约束 |
| 插件体系（Star） | `plugins/` | **超出**参考的安全强度 |
| `dashboard/` | `webui/` | 对应 |
| `cli/` | `cli.py` | 对应 |

分层解耦（M×N→M+N）、协议兼容优先、插件化、Agent 能力内建、安全与性能并行 —— AstrBot 的核心取舍 soapbot 都做了，且安全层明显更细（能力逐项授权、审批与发现分离、进程隔离默认开、SSRF/体积/重定向限制、审计脱敏、注入边界包裹）。

### 4.2 未对应的部分

| AstrBot 有 | soapbot | 影响 |
|---|---|---|
| 1000+ 插件 + 一键安装（市场） | 无市场、无安装、无更新 | 「插件化即生态」这条最核心特征缺失 |
| `builtin_stars/`（仓库内内置插件） | 示例插件在 `data/`（被 gitignore） | 连内置插件都不进仓库 |
| MCP 客户端 | 零（`mcp` 搜 0 处） | 「MCP 客户端预留」未做 |
| Agent Sandbox（代码/Shell 隔离执行） | 仅插件进程隔离 | 能力位不同 |
| STT / TTS | 零（`tts`/`edge_tts`/`stt` 各 0 处） | C9 全缺 |
| 流式输出 | Provider 有 `stream()`，管线与 WebUI 不调用 | 未做 |
| 运行时 i18n | 无 | — |
| `openspec/`、`AGENTS.md` | 无 | — |
| 多形态部署（Docker/k8s/Compose） | `deploy/`（read_only rootfs、cap_drop ALL、non-root） | 对应，但未实测（无 Docker） |
| 六语种 README | 单语 | — |

### 4.3 一个必须澄清的法律问题

AstrBot 是 **AGPL-3.0**，soapbot README 声明 **MIT**。

我逐文件看过 soapbot 代码：docstring 风格、注释语言、命名、错误信息都是原创（大量中文长注释解释「为什么这样设计」），未见逐行照搬，**看起来是 clean-room 的架构借鉴**。

但「仿 AstrBot 架构」写在计划里，README 却承诺 MIT。若后续有人往仓库补 AstrBot 片段，MIT 声明立刻变成许可冲突。建议 `LICENSE` 落地时同时写明「架构受 AstrBot 启发，未包含其代码」。

### 4.4 计划承诺 vs 实际交付（C1–C9）

来源：`.codebuddy/plans/soapbot-qq-ai-bot_b45fbfec(未完成).md` 的 `capability_matrix`。

| # | 能力 | 状态 | 依据 |
|---|---|---|---|
| C1 | QQ 群聊机器人 | ⚠️ 部分 | OneBot 通；官方 @ 断链；私聊永久关；群管未实现 |
| C2 | 多模型接入 | ✅ 基本完成 | 4 种 kind + router + 3 次失败冷却；stream 位有但未用 |
| C3 | 人格卡 | ✅ 完成 | YAML + 按群/按用户绑定 |
| C4 | 极致压缩上下文 | ✅ 完成 | `compressor.py` 分层 + 滚动摘要，有测试 |
| C5 | 可回溯记忆 | ⚠️ 部分 | 检索（RRF 混合/FTS5/向量）扎实；**知识库无写入路径** |
| C6 | 可扩展接口 | ⚠️ 部分 | manifest/能力/隔离真实；工具调用断裂；MCP 零；总线无订阅方 |
| C7 | 动图静图识别 | ✅ 完成 | `vision.py` 有 `n_frames` 采样 + 拼网格 |
| C8 | WebUI | ⚠️ 部分 | 6 个只读页 vs 计划 10 个 |
| C9 | 全功能附加 | ❌ 未做 | 流式未接、TTS 零、STT 零 |

**WebUI 实际**：`Overview / Runtime / Plugins / Security / Memory / Budget`（6 个）
**计划**：仪表盘、适配器、Provider、人格卡、插件、会话与记忆、知识库、日志中心、消息调试台、系统设置（10 个）

`/api/logs` 有接口无页面；知识库只有列表不能上传 —— 且 `add_document` 仅测试调用，意味着 **RAG 在部署里永远是空的**。「界面能看、功能不能用」。

---

## 五、B 站：实现最好，但两条触发链只做了一条

`bilibili/` 从空包变成 6 文件 869 行，wbi 签名有固定向量测试，短链只读 `Location` 不跟随，L3 明确拒绝而非静默降级，观后感标注「基于公开信息推断」。**质量是本轮最好的模块之一**。

但计划写的是「定时自主浏览 + 群内链接触发，两条链路」：

| 链路 | 状态 |
|---|---|
| `/bili <BV\|链接>` | ✅ 已接（`_cmd_bili` + `COMMAND_PERMISSIONS['bili']`） |
| 群内**自动**识链接 | ❌ 无（`BV1`/`b23.tv` 只出现在 `client.py` 解析逻辑，流水线无「出现链接即触发」阶段） |
| 定时自主浏览 | ❌ 无（`VideoWatcher` 只在命令路径被调用；`RuntimeScheduler` 无 bili 单元） |

---

## 六、差距清单（按优先级）

### P0 —— 不修则不能称为交付物

1. **仓库零提交 + 示例插件被 gitignore** → 全新克隆 5 失败 24 错误（已实测）。最小修法：把 `data/plugins` 移到 `examples/plugins/` 或 `builtin_plugins/`，改 6 个测试的 fixture 路径，`git add` 全部并提交。
2. **QQ 官方适配器 @ 唤醒断链** → 官方渠道基本不可用。修法：`_strip_at_prefix` 时同步产出 `MessageSegment.at(self_id)`，或给官方适配器注入 `WakePolicy(require_at_in_group=False)`，并补测试。
3. **`LICENSE` 缺失而 README 声明 MIT** → 法律上不可用。

### P1 —— 功能宣称与实现不符

4. **工具调用三层断裂** → 要么接通（隔离模式把 `kind=="tool"` 分流到 `_tools`；`AIRequest` 加 tools；`ModelStage` 加载 `available_for` 并做 tool_calls 循环），要么在 README/docs 里明确标注「未接通」。
5. **私聊永久关闭且开关无效** → 加 `private_allowlist` 配置项，把 `allow_unknown_private` 真正传进 `AccessPolicy`。
6. **插件审批不持久** → `_approved` 落盘到 `data/plugins_state.json`（0600），启动时读取并可选自动加载已批准插件。
7. **群管能力只有声明** → 要么实现 `/mute /recall /kick`，要么把 `MUTE/KICK/RECALL/FORWARD` 从 `_CAPABILITIES` 移除（当前是「声称支持但无实现」，比不支持更糟）。
8. **知识库无写入路径** → 加 `POST /api/knowledge` 或 CLI 导入；否则 RAG 功能为空。

### P2 —— 交付质量

9. `structlog`/`watchdog`/`python-multipart` 从依赖移除或真正使用。
10. 补 `.env.example`、`CHANGELOG.md`、CI workflow。
11. notice 链路：要么让适配器产生 notice 并接到 `on_notice`，要么删除 `Capability.NOTICE`。
12. B 站补「群内自动识链接」与「定时自主浏览」两条链，或在文档降级为「仅命令触发」。
13. WebUI 补 Provider/人格/知识库上传/日志页（当前 6/10）。

---

## 七、值得肯定的部分（避免评估失衡）

这不是一个「到处是坑」的项目，恰恰相反：

- **安全模型**是同类项目里少见的严谨：能力逐项授权（审批与 manifest 分离，插件改 manifest 加能力必须重新审批）、进程隔离默认开启（docstring 明确写了「上一轮隔离层是个没人调用的库」的教训）、SSRF 三重限制、审计日志脱敏（`sk-*`/`Bearer`/`token=` 正则遮蔽）、注入边界包裹、插件输出 canary 检测。
- **阶段顺序被当作契约**：`build_pipeline` 里 `dedup → guard → whitelist → wake → strip → sanitize → injection_screen → authorization → command → ...`，注释写明为什么 guard 在 whitelist 之前（先知道「谁」才能判断「在哪」）。
- **注释质量高于平均水平**：大量「为什么」而非「做什么」，且记录了被推翻的方案（例如 `StripWakeWordStage` 解释为什么不能剥掉 `/`：会把 `/budget` 变成 `budget`，让所有斜杠命令静默失效）。
- **B 站模块**：wbi 签名有固定向量测试、短链不跟随跳转、L3 显式拒绝而非静默降级、固定 UA 且写明理由（若轮换指纹，「L1 静默模式」的声明就是假的）。
- **OneBot 全链路真的能跑** —— 这是本轮最实的成果。

---

## 八、需要你决定的事

1. **QQ 官方适配器还要不要？** 若要，@ 唤醒必须修；若短期只用 OneBot，建议在 README 把官方标为「实验性/待验证」，而不是并列为一等公民。
2. **工具调用接不接？** 接通需要改 `AIRequest`/`ModelStage`/`AIEngine` 三处 + 隔离模式工具分流，工作量中等，但这是「Agent 能力」的核心；不接则应从 README 与 manifest 文档里删掉 tool 能力。
3. **插件协同要不要做？** 当前星型模型是安全选择。若需要 A 调 B，必须设计成「宿主中介的显式 API + 能力声明」，不能直接暴露 `loader`。
4. **交付形态**：如果目标是「可 clone 可部署」，P0 三项必须先做（尤其是示例插件出 gitignore + 首次 commit）。

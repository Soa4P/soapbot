# soapbot

QQ 群聊 AI 机器人框架。双 QQ 接入（OneBot v11 / QQ 官方开放平台）、多 Provider
故障转移、人格卡、上下文压缩、可回溯记忆、图片理解、B 站公开信息浏览与观后感、
额度审批工作流、进程隔离插件、群管命令、管理 API 与 Vue 3 控制台。

**不做什么**：不内置任何 QQ 协议逆向代码；不持有支付凭据、不调用支付 API、不自动扣款。

---

## 目录

- [30 秒理解它是什么](#30-秒理解它是什么)
- [快速开始](#快速开始)
- [参考来源与它们对成品的影响](#参考来源与它们对成品的影响)
- [项目结构与模块职责](#项目结构与模块职责)
- [一次消息的完整旅程](#一次消息的完整旅程)
- [配置清单](#配置清单)
- [依赖清单](#依赖清单)
- [运行与部署](#运行与部署)
- [插件系统](#插件系统)
- [群管命令](#群管命令)
- [能力矩阵](#能力矩阵)
- [安全默认值](#安全默认值)
- [常见问题](#常见问题)
- [免责声明](#免责声明)
- [许可证](#许可证)

---

## 30 秒理解它是什么

一个 QQ 群里的机器人。有人 @它 或说出唤醒词，它就用人格卡定义的语气回话；回话前
会检索本群历史、长期记忆和知识库；图片会被真实送进视觉模型；花钱的操作要先经人审批；
第三方代码作为插件运行在**独立进程**里，权限按能力逐项授予。

它不是「一个 Python 脚本调一次模型」。真正的骨架是**流水线**：每条消息经过一串
有序的 Stage，每一步都可能读取上下文、写入上下文，或者直接终止。

```text
dedup → guard → whitelist → wake → strip → sanitize
      → injection_screen → authorization → command → plugin_cmd → plugin_hook
      → persist → persona → recall → knowledge → model(+tools) → safety
      → reply → persist_reply → memory_write
```

顺序是**安全语义的一部分**，不是性能排序：`guard` 在建身份之前，白名单才能判断
「谁在哪儿说话」；`command`/`persist` 在所有准入之后，未授权用户永远碰不到数据库。
改顺序等于改安全模型，`core/builder.py` 的 `build_pipeline` 里有逐段说明。

---

## 快速开始

要求：Python **3.12+**。前端构建需要 Node 20+（仅当你修改面板时才需要）。

```bash
# 1. 安装
python -m venv .venv
# Linux / macOS
.venv/bin/python -m pip install -e ".[dev]"
# Windows
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 或者只想跑起来，不装开发工具：
# pip install -r requirements.txt
```

```bash
# 2. 配置（两个文件出厂都是空的，必须填）
cp .env.example .env
$EDITOR config/providers.yaml   # 至少一个模型端点，否则机器人不会回复
$EDITOR config/adapters.yaml    # 至少一个协议端，否则收不到任何消息
# 两个文件里都有注释掉的示例，取消注释并改成你的值。
```

### 3. 看界面（Windows 双击即可）

面板是 Web UI。三条路，按你手上有什么选一条：

| 双击 | 看到什么 | 前提 |
|---|---|---|
| **`start-panel.bat`** | **本机**的面板，自动建 venv、起服务、健康后自动开浏览器 | 只需这台机器有 Python 3.12 |
| **`open-remote-panel.bat`** | **服务器上**那个实例的面板（数据也是服务器的） | 需要私钥 `%USERPROFILE%\.ssh\soapbot_deploy` |
| `stop-panel.bat` | 关掉本机启的那个 | — |

`start-panel.bat` 会在窗口里打印首次登录令牌（`data\init_token.txt`），并自动打开
`http://127.0.0.1:6185`。任何一步失败都会停在窗口里说明原因，不会闪退。

服务器上的面板只绑 `127.0.0.1`（这是安全默认，不是缺陷）。`open-remote-panel.bat` 走 SSH
隧道把它映射到本机 `6185`，所以"看得见"和"不对公网暴露"可以同时成立。

```bash
# 命令行等价物（macOS / Linux / 服务器上）
python -m soapbot.cli start     # 或：soapbot start（可编辑安装后）
# → http://127.0.0.1:6185

# 没有浏览器？交互式配 Provider 与 QQ 接入，校验不过不写盘
python -m soapbot.cli setup
```

```bash
# 4. 首次登录
# 引导令牌写在 data/init_token.txt（权限 0600）。本机访问面板无需令牌；
# 远程访问必须先换取访问令牌：
curl -X POST http://127.0.0.1:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"init_token": "<文件中的值>"}'
```

```bash
# 5. 部署前自检（会检查绑定地址、主密钥来源、文件权限、插件隔离模式、上游端点配置等）
python -m soapbot.cli doctor
python -m soapbot.cli doctor --strict   # 高危项非零退出，可用于部署门禁
python -m soapbot.cli doctor --probe    # 额外发一次请求问每个 base_url 活不活（需要网络）
```

> `providers: []` 会显示成 `[warn] provider.upstream` 而不是一片安静：一个连不上任何模型
> 端点的进程，`doctor` 以前会打印 PASS。`--probe` **故意不带 API Key**——它把 401/403 当作
> 「服务器回答了」，这样调试日志里不会出现凭据。

> 面板产物已随包发布，`git clone` 后**不需要** `npm build` 就能打开控制台。

控制台共 12 页，编号是**稳定标识符**（电话里说「04 页」要一直指同一件事），只追加不重排：

| 页 | 内容 |
|---|---|
| 01 总览 | 进程/适配器/流水线三层状态 |
| 02 运行状态 | 运行时、调度器、启动错误 |
| 03 插件 | 批准/撤销/加载/卸载 |
| 04 安全审计 | 审计事件、拒绝记录、权限矩阵 |
| 05 记忆与知识库 | 会话、时间线、知识入库/删除 |
| 06 额度审批 | 账本与二次审批 |
| 07 模型与人格 | Provider 可视化编辑（diff 确认）+ 人格卡只读 |
| 08 运行日志 | 结构化日志 |
| 09 流水线追踪 | 20 个环节的拓扑、逐环节耗时、中止点、换序沙箱 |
| 10 运行指标 | 延迟分位、累计计数、结果分布（手写 SVG 图表） |
| 11 插件包安装 | 上传 zip 安装（**不等于批准**）、能力风险分级、装完引导到 03 页批准 |
| 12 系统设置 | 界面语言、回复语言、语音两个开关与音色、MCP 连接状态、运行时信息（含 schema 版本） |

---

## 参考来源与它们对成品的影响

这一节不是致谢名单，而是**溯源**：说清哪些设计来自外部，以及它们在代码里落在哪里。
便于审计者判断哪些是原创、哪些是遵循既有规范（若发现任何直接移植的代码，请以此节
为线索核对 `LICENSE` 中的声明）。

### 1. AstrBot — 分层取舍（架构参考，无代码复用）

- 来源：[AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot)，许可证 **AGPL-3.0**。
- 参考内容：把「平台适配 / 模型提供 / 消息处理 / 插件」切成互相不认识的四层，
  让新增一个平台或一个模型端点不触碰业务代码。
- 落到本项目的具体位置：
  - `core/adapter.py`（适配器契约）↔ `adapters/`（OneBot v11、QQ 官方、mock）
  - `providers/base.py`（四个能力槽 `chat`/`stream`/`vision`/`embed`）↔ `providers/`
  - `core/pipeline.py` + `core/stages.py`（本项目形态：有序 Stage 链，而非中间件栈）
  - `plugins/`（插件运行时，本项目额外做了进程隔离与逐能力授权）
- **版权边界**：本仓库未包含 AstrBot 代码，标识符、注释、实现均为原创。分层思想本身
  不受著作权保护，但这条界线必须写明——见 `LICENSE` 末尾的说明。
  如果将来引入其代码，MIT 声明不再成立，发行条款必须随之变更。

### 2. OneBot v11 协议 — 接入契约

- 来源：[OneBot 11 标准](https://github.com/botuniverse/onebot-11)。
- 影响：`adapters/onebot11.py` 的事件字段名（`post_type` / `message_type` /
  `notice_type` / `retcode` / `echo`）与动作名（`send_group_msg`、`delete_msg`、
  `set_group_ban`、`set_group_kick`、`get_group_list`）全部按该标准。
  这是「能接 NapCat / Lagrange / go-cqhttp」的原因。
- 本项目额外处理了标准未强制的两件事：`retcode` 的宽容取值（`0/1/None`，
  各家实现不一致），以及 `set_group_kick` 的 `reject_add_request` 键在部分实现中
  被忽略——代码注释里写明了为什么宁可显式发送而不是省略。

### 3. QQ 官方机器人开放平台 — 平台约束

- 来源：[QQ 机器人文档](https://bot.q.qq.com/wiki/)。
- 影响：`adapters/qq_official.py` 里写死的常量不是猜的，而是平台规则：
  主动推送 20 条/群/天、被动回复窗口 5 分钟、单群 5 条/秒。
  这些通过 `quota_hint` 暴露给限流层排队，而不是让发送直接失败。
- 影响还体现在范围裁剪上：**不支持 QQ 频道（guild）**，`MessageScene.CHANNEL`
  故意不存在，`Intents` 只申请群聊与私聊。

### 4. OpenAI Chat Completions 形状 — Provider 的公共子集

- 影响：`providers/openai_compat.py` 直接说 HTTP，不绑 SDK。`tools` /
  `tool_calls` / `image_url` parts 等字段按该形状收发，因此 DeepSeek、通义、
  Moonshot 以及绝大多数中转服务可共用一套实现。
- 已知取舍写进了 `ai/engine.py`：工具结果以**系统提示里的不可信数据块**回灌，而不是
  严格回显 assistant 的 `tool_calls` + `tool_call_id`，因为部分中转会丢弃或拒绝后者。

### 5. 经典检索与安全工程实践 — 无特定出处

- BM25 关键词检索 + 余弦向量检索双路融合（`memory/store.py`）：FTS5 提供关键词通道，
  numpy 暴力余弦提供语义通道，单路可用即降级而非失败。
- 提示注入防护（`security/injection.py`）：不可信内容打上 canary 边界标记，
  模型若在输出里复述 canary 则整条回复丢弃——这是「检测到即视为已失守」的思路，
  而非事后过滤关键词。

---

## 项目结构与模块职责

```text
soapbot/
├── src/soapbot/
│   ├── core/           # 编排层：消息模型、适配器契约、流水线、运行时、调度器
│   ├── adapters/       # 接入层：OneBot v11、QQ 官方、mock（测试用协议端）
│   ├── providers/      # 模型层：能力槽、OpenAI 兼容实现、故障转移路由
│   ├── ai/             # 智能层：人格卡、上下文压缩、视觉、引擎、AI Stage
│   ├── memory/         # 数据层：消息归档、三层记忆、知识库、检索、命令 Stage
│   ├── security/       # 防护层：主体与权限、审计、注入防护、密钥、令牌
│   ├── plugins/        # 扩展层：清单、沙箱、加载器、进程隔离、命令/工具分发
│   ├── budget/         # 可选：额度账本与二次审批
│   ├── bilibili/       # 可选：公开元数据、wbi 签名、观后感
│   ├── api/            # 对外：FastAPI 路由（鉴权 / 管理 / 插件 / B 站 / 安全 / 配置写入 / 流水线）
│   ├── examples/       # 随包发布的示例插件（不是内置功能，仍需批准）
│   └── webui/dist/     # 前端构建产物（随 wheel 发布）
├── webui/              # 前端源码（Vite + Vue 3 + TypeScript）
├── config/             # providers / adapters / personas（Provider 可经面板写入，需 diff 确认）
├── data/               # 可写卷：SQLite、日志、上传、插件目录、批准记录（gitignore）
├── deploy/             # install.sh（一键部署）、Dockerfile 与 docker-compose
├── docs/               # 设计记录、安全模型、交付评估
├── scripts/            # check_deps.py 等仓库工具
└── tests/              # pytest（1085 项通过 / 10 项跳过）
```

### 各模块的功能定位与实现要点

**`core/` — 编排层**

| 文件 | 功能定位 | 实现要点 |
|---|---|---|
| `message.py` | 跨平台统一消息模型 | `MessageSegment` 是最小单位（text/image/at/reply/face/record/file/forward）；`transport_authenticated` 默认 `True` 仅因为是进程内构造，网络适配器必须显式设置 |
| `adapter.py` | 适配器契约 + 能力协商 | 能力集声明式（`Capability`），不支持的分段在 `degrade()` 里降级为文字而不是让整条回复失败；群管动作有默认实现，声明了却没实现会返回明确失败而非 `AttributeError` |
| `pipeline.py` | Stage 链执行器 | `StageResult(halt=True, reason=...)` 终止并记录原因；`PipelineContext` 承载事件、适配器、回复、`extras` 与 token 用量 |
| `stages.py` | 准入类 Stage | `AccessPolicy`（群空=全开、私聊空=全关的不对称是有意的）、`WakePolicy`、`StripWakeWordStage`、`DedupStage`、`ReplyStage` |
| `builder.py` | 唯一装配点 | `build_pipeline` / `build_runtime` / `build_plugin_manager`。测试与生产走同一条装配路径，否则「测试通过」不说明部署可用 |
| `runtime.py` | 适配器 ↔ 流水线 | 按会话加锁保证同群串行；`NOTICE` 事件绕过流水线直接分发（通知不需要准入判断）；插件发消息只给 `session_key`，由运行时决定目标 |
| `scheduler.py` | 周期任务 | 插件 cron、过期额度清扫、保留位回收 |
| `config_files.py` | 配置加载 | YAML 严格解析，引用了未设置的 `env:` 变量时**启动失败**——带着空 key 运行会变成一串 401 并被归咎于上游 |

**`adapters/` — 接入层**

- `onebot11.py`：WebSocket 客户端 + 动作调用。事件覆盖 `message` / `notice` /
  `meta_event`；API 响应用 `echo` 关联 Future。**注意**：`emit` 用 `create_task`
  派发而不内联等待，否则 `send()` 等待回执时会与自己的读循环死锁。
- `qq_official.py`：群聊 + 私聊（C2C），无频道。`split_leading_at` 返回
  `(是否 @了机器人, 正文)`——只返回正文会导致「消息被正确 @ 却完全不应答」。
- `mock_onebot.py`：真实 socket 的模拟协议端，让端到端测试不必依赖外部程序。

**`providers/` — 模型层**

- `base.py`：`CapabilitySlot` 四槽（chat/stream/vision/embed）。一个 Provider 只声明
  自己真的实现的能力，路由据此选，而不是假设所有端点都能干所有事。
- `openai_compat.py`：httpx 直连，含 `tools` 与多模态 parts 序列化。
- `router.py`：按优先级故障转移 + 冷却窗口。失败一次的上游不会在下一秒被反复重试。

**`ai/` — 智能层**

- `persona.py`：人格卡加载、群/用户绑定解析、`build_system_prompt`。
- `compressor.py`：分层压缩（折叠轮次 → 摘要），保底 token 预算。
- `vision.py`：图片预处理与描述缓存（按内容哈希），历史重放不再重复付费。
- `engine.py`：把人格、历史、记忆、知识、图片编成一次请求；工具结果以不可信数据块
  回灌。
- `stages.py`：`PersonaStage` / `ModelStage`（含有界工具循环）/ `SafetyStage`
  （不可见字符清理、提示词泄漏标记、canary 复述检测、凭据脱敏、字数截断）。

**`memory/` — 数据层**

- `db.py`：SQLAlchemy 异步 + SQLite；向量以 BLOB 存储，numpy 暴力余弦——单群语料是
  几千行，不是几百万行，可用性优先于理论最优。
- `store.py`：`archive_message`（只追加）、`history`（带摘要拼接）、`recall`
  （FTS5 与向量双路融合 + RRF）、`KnowledgeBase`（`ingest_document` 覆盖语义）。
- `extractor.py` / `stages.py`：记忆抽取、`PersistStage`、`RecallStage`、
  `KnowledgeStage`、以及全部斜杠命令（含群管）。

**`security/` — 防护层**

- `principal.py`：`Role` / `Permission` / `AuthorityConfig`。权限表只从配置来，
  聊天内容不能增加权限。读与写、审批与查看、配置与群管都是**分开的**权限。
- `stages.py`：`GuardStage`（建身份）、`InjectionScreenStage`、`AuthorizationStage`。
- `injection.py`：不可信内容边界标记 + canary；记忆入库前 `vet_memory`。
- `audit.py`：有界环形审计日志，细节脱敏（插件异常只记类型，不记消息）。
- `crypto.py` / `tokens.py` / `files.py`：Fernet 主密钥、JWT、私密文件写入。

**`plugins/` — 扩展层**

- `manifest.py`：清单校验。名称/入口/依赖/能力全部是攻击者可控文本，逐项校验后才
  触碰文件系统与 import 机制。
- `sandbox.py`：`CapabilityGrant`（冻结）+ `CapabilityGuard`（密封）。冻结是因为
  「是否允许 HTTP」的答案不能在授权后被改；密封是因为 guard 若能写就等于自我提权。
- `loader.py`：发现 → 批准 → 加载三步分离；`load_approved()` 只加载**有持久批准记录**
  的插件。
- `approvals.py`：批准记录持久化（原子写入、单文件）。与清单分开存放，因为清单由插件
  作者写、批准由运维写——插件更新不能把自己的授权带过来。
- `supervisor.py` / `isolation.py` / `worker.py`：子进程隔离。宿主侧保留命令表，
  worker 只上报名字；否则 worker 可以注册 `/forget` 顶掉核心命令。
- `dispatch.py`：`PluginCommandStage`、`PluginMessageHookStage`、`PluginToolRegistry`、
  `dispatch_notice`、`PluginCronRunner`。工具可见性按角色**过滤**而非「列出再拒绝」。

**`budget/`、`bilibili/` — 可选能力**

- `budget/`：整数最小单位记账（浮点会让配额漂移）、保留位、二次审批（不能批准自己
  发起的申请）。
- `bilibili/`：L1 免签名 / L2 wbi 签名（有固定向量测试）/ L3 显式拒绝而非静默降级；
  短链不跟随跳转、固定 UA、限速。

**`api/` — 对外接口**

鉴权（`auth.py`）、管理只读视图 + 知识库写入（`admin.py`）、插件管理
（`plugins.py`）、B 站（`bilibili.py`）、安全审计（`security.py`）。
除知识库内容外，配置类写入一律不做——见 `admin.py` 模块注释里的取舍说明。

---

## 一次消息的完整旅程

以群里有个人 @机器人 说「这张图里是什么」为例：

1. `adapters/onebot11.py` 收到 WebSocket 帧，转成 `IncomingMessage`
   （AT 段 + 文字段 + 图片段），`emit` 派发。
2. `BotRuntime._on_event` 按 `session_key` 加锁，进入 `Pipeline`。
3. `DedupStage` 丢掉重复投递；`GuardStage` 解析出 `Principal`（角色只来自配置）。
4. `WhitelistStage` 判断这个群是否允许（空名单 = 全开）。
5. `WakeStage` 看到 AT 段指向自己 → 通过，记录 `wake_reason=at`。
6. `StripWakeWordStage` 去掉 AT 段与唤醒词；`SanitizeStage` 去控制字符。
7. `InjectionScreenStage` 检查越权指令；`AuthorizationStage` 确认能聊天。
8. `CommandStage` / 插件命令 / 插件钩子：不是命令，继续。
9. `PersistStage` 归档这条消息（模型调用失败也要留下，否则历史有洞）。
10. `PersonaStage` 按群 + 用户解析人格卡；`RecallStage` 检索记忆；
    `KnowledgeStage` 检索知识库——两者都以**不可信数据块**注入系统提示。
11. `ModelStage`：语音段先转写（转写文本**同样过注入筛查**——嘴说出来的不是可信输入），
    图片按内容哈希查缓存，未命中才调用视觉模型；随后带工具列表请求主模型；
    若模型要求调用工具，执行后把结果作为不可信数据块回灌，最多两轮。
    开了 `STREAM_REPLY` 且没有工具待调用时，改为边生成边按句发送。
12. `SafetyStage`：清理不可见字符、拦截提示词泄漏、检测 canary 复述、
    脱敏疑似凭据、按人格卡截断。
13. `ReplyStage` 通过适配器 `degrade()` 降级不支持的段落后发送；开了
    `VOICE_TTS_ENABLED` 时先合成为语音，失败或过长则回退为文本。
14. `PersistReplyStage` 归档回复；`MemoryWriteStage` 异步抽取值得记住的事实。

任何一步都可以 `StageResult(halt=True, reason="...")` 终止——终止原因会进指标和审计，
这是排查「机器人为什么不回我」的第一手材料。

---

## 配置清单

### 配置文件

| 文件 | 作用 | 缺失时 |
|---|---|---|
| `config/providers.yaml` | 模型端点与故障转移顺序 | 模型阶段禁用，机器人收消息但不回复 |
| `config/adapters.yaml` | QQ 协议端连接参数 | 不连接任何平台，只提供管理 API |
| `config/personas/*.yaml` | 人格卡 | 使用空系统提示（能回复，但没人格） |

密钥有三种写法：字面量、`env:VAR`、`enc:v1:...`（Fernet 密文）。
`env:` 指向的变量未设置时**启动失败**。

### 环境变量（前缀 `SOAPBOT_`，也可写入 `.env`）

完整模板见 [`.env.example`](.env.example)。

> `SOAPBOT_ENV_FILE` 改变进程读取哪个 `.env`（默认工作目录下的 `.env`）。它本身只能由
> 环境变量给出、不能写进 `.env`。**用 systemd 或容器部署时建议显式设置**：这类环境的工作
> 目录不是仓库根目录，相对路径的 `.env` 会指向一个没人读的位置，而第 12 页的保存按钮
> 会以为自己保存成功了。

要点：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `6185` | 绑定 `0.0.0.0` 会暴露管理 API，务必同时配置鉴权 |
| `DATA_DIR` | `./data` | 可写卷 |
| `CONFIG_DIR` | `<data>/config` | **运行期配置，可写**。面板从这里读写 |
| `CONFIG_TEMPLATE_DIR` | `./config` | 镜像自带的默认值，**只读**；文件缺失时复制到 `CONFIG_DIR`，已有文件永不覆盖 |
| `MASTER_KEY` / `MASTER_KEY_FILE` | 空（自动生成到 `data/master.key`） | 容器优先用文件：环境变量对 `docker inspect` 可见 |
| `OWNER_IDS` / `ADMIN_IDS` / `MEMBER_IDS` | 空 | **唯一**的权限来源，逗号分隔 |
| `GROUP_ALLOWLIST` / `GROUP_BLACKLIST` | 空 | 群准入。空名单 = 允许所有被拉进的群 |
| `PRIVATE_ALLOWLIST` | 空 | 私聊范围。**空 = 谁都不行**，不是谁都行 |
| `ALLOW_UNKNOWN_PRIVATE` | `false` | 「任何人都能私聊」的显式开关 |
| `ALLOW_UNTRUSTED_PLUGINS` | `false` | 允许 `trust: untrusted` 插件持有敏感能力 |
| `ENABLE_RUNTIME` | `true` | 关掉则只提供 HTTP API |
| `ENABLE_BUDGET` / `ENABLE_BILIBILI` | `false` | 可选能力，默认关闭 |
| `STREAM_REPLY` | `false` | 边生成边发。仅在适配器声明 `PROGRESSIVE` 时生效（目前只有 OneBot v11） |
| `VOICE_ENABLED` | `false` | 入站语音转写。需要 Provider 声明 `transcribe` 槽位 |
| `VOICE_TTS_ENABLED` / `VOICE_TTS_VOICE` | `false` / `zh-CN-XiaoxiaoNeural` | 回复转语音。需要 `pip install -e ".[voice]"` |
| `VOICE_ALLOW_HOSTS` | 空 | 允许下载音频的内网主机，逗号分隔。**同机部署 NapCat 必须配**，见下 |
| `VOICE_MAX_BYTES` / `VOICE_LANGUAGE` | `8388608` / `zh` | 单条音频上限与转写语言提示 |
| `DEFAULT_LOCALE` | `zh-CN` | 机器人**对群里说话**的语言（拒绝文案、语音标签）。不影响面板，面板按浏览器语言走；人格卡可用 `locale` 逐群覆盖 |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | `LOG_JSON=false` 便于人读终端 |

> 列表型变量支持三种写法：`123,456`、`123;456`、`["123","456"]`。
> 早期版本只接受 JSON，用逗号会以一条不说明正确语法的 `SettingsError` 启动失败。

> **`VOICE_ALLOW_HOSTS` 为什么必须显式配。** 音频 URL 由群成员给出，服务器带着自己的
> 网络位置去取，所以默认只允许公网地址（防 `169.254.169.254` 这类元数据端点）。但
> NapCat 从**它自己的 HTTP 端口**提供语音文件，同机部署下 `record.url` 就是
> `http://127.0.0.1:3000/...`——严格规则会把每一条语音都拒掉，而且是静默降级成
> `[语音]`。因此内网媒体端点要由运维在 `.env` 里指名：
>
> ```bash
> SOAPBOT_VOICE_ALLOW_HOSTS=127.0.0.1
> ```
>
> 默认留空是刻意的：让「信任一个内网地址」成为一次显式、可审计的决定，而不是藏在
> 代码里的隐含假设。白名单只豁免地址判定，不豁免协议——`file://` 仍然被拒。

---

## 依赖清单

运行时（`requirements.txt` 与 `pyproject.toml` 由 `make check-deps` 校验一致）：

| 依赖 | 用途 |
|---|---|
| `fastapi` + `uvicorn[standard]` | HTTP API 与控制台托管 |
| `pydantic` + `pydantic-settings` | 校验模型与配置解析 |
| `sqlalchemy[asyncio]` + `aiosqlite` | 异步 ORM 与 SQLite（含 FTS5） |
| `httpx` | 调用模型端点与 B 站 API |
| `websockets` | OneBot v11 的 WebSocket 客户端 |
| `pyyaml` | 配置与插件清单（用 `safe_load`） |
| `pillow` + `numpy` | 图片预处理；向量 BLOB 与余弦计算 |
| `pyjwt` | 控制台会话令牌 |
| `cryptography` | Fernet 加密 Provider 密钥 |
| `croniter` + `apscheduler` | 插件 cron 表达式与周期调度 |

可选与开发：

```bash
pip install -e ".[qq-official]"   # qq-botpy：仅 QQ 官方适配器需要
pip install -e ".[precision]"     # tiktoken：更精确的 token 计数
pip install -e ".[voice]"         # edge-tts：回复转语音（入站转写不需要它）
pip install -e ".[dev]"           # pytest / ruff / mypy / respx
```

> `structlog`、`watchdog`、`python-multipart` 已从依赖中移除：代码里没有任何引用。
> 依赖清单是审计面的一部分，留着它们会让评审者以为项目具备实际不存在的功能
> （结构化日志、热监听、multipart 上传）。插件上传改收原始请求体，因此不需要
> `python-multipart`。
>
> `edge-tts` 曾因「语音合成不存在」被一并移除。语音现在存在了，所以它回到了
> **可选** extra 里，而不是默认依赖：它是一个大多数部署永远不会调用的厂商网络
> 客户端，放进默认集只会让「pip install 就能跑」为单个功能变重。

---

## 运行与部署

### 本地

```bash
make install        # 建虚拟环境 + 装开发依赖
make run            # 先构建前端，再启动服务
make check          # lint + 配色 + 可访问性 + 测试断层 + test（与 CI 阻断项同一条命令）
make a11y           # 可访问性静态规则（按钮名称、点击目标可聚焦、img alt、对话框语义）
make gaps           # 测试断层扫描：无人引用的模块、文档里与看板不一致的数字
make typecheck      # mypy —— 当前基线非零，仅作参考，不阻断
make doctor         # 部署姿态检查
```

> **类型检查现状**：`mypy src` 目前报告 53 个错误，分布在 20 个文件，全部是既有问题。
> 因此 CI 把它放在独立的 `types` job 里（`continue-on-error`），只报告不阻断。
> 让它阻断会让首次推送就是红的，而让人们习惯红色徽章；按模块 `ignore_errors` 则会
> 把该文件里的下一个真实错误一并藏掉。降到 0 之后应当改为阻断。

不用 `make` 也可以，见[快速开始](#快速开始)。

### 双端安装（Windows / Linux / macOS，同一个安装器）

```bash
python scripts/bootstrap.py                       # 装到当前目录（或 --dir）
python scripts/bootstrap.py --autostart           # 开机/登录自动起来
python scripts/bootstrap.py --check               # 只体检已有安装
python scripts/bootstrap.py --dir D:\soapbot --port 6185
```

六个步骤两端一致：创建 venv → `pip install -e .` → 确认面板产物存在（缺 Node 时会明说）
→ 把数据目录/配置目录写成**绝对路径**写进 `.env` → 交给平台自己的进程管理者 →
轮询 `/api/health` 到通过 → 打印面板地址、取令牌的命令、下一步去第 07 页。幂等：再跑一次等于升级。

两端唯一真正不同的地方在最后一步：

| 平台 | 谁来托管进程 | `--autostart` 做什么 |
|---|---|---|
| Windows | 双击 `start-panel.bat`；或用 detached 进程后台起 | 注册计划任务 `soapbot-panel`（登录时启动） |
| Linux | systemd unit（有 root 时还会建 `soapbot` 系统账号并把服务跑成它，而不是 root）/ 用户级 unit（无 root，会提示 `loginctl enable-linger`） | 等价于 `systemctl enable --now` |
| 无 systemd | 明确告知：用 supervisor / openrc，或直接前台跑 | 不假装成功 |

已存在的同名 unit 若**不是**本安装器写的，一律不动（`--unit <名字>` 起第二份实例）——
覆盖别人的 unit 会把它指向新目录，而数据还留在原处。

完全没有 Linux 主机时也可一张命令：

```bash
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/install.sh | sudo bash
```

它只负责弄到 Python ≥ 3.12（22.04 上自动换 deadsnakes 的 3.12）并 clone，然后调用上面
**同一个** `bootstrap.py`——两处分叉的安装器正是第一版脚本 systemd-only 的成因。

> **Ubuntu 上已经在真机跑过（不是只看代码）**：雨云 Ubuntu 24.04、root 登录、全新目录
> `/opt/soapbot-test`、端口 6186：venv → `pip install -e .` → 配置 → `systemctl enable --now`
> → `/api/health` 报 ok → 面板 `index.html` 与 JS 资源均 200；`doctor` 以服务账号运行时
> `privilege.uid` 为 ok（uid 996）。三个真机失败点都是这样被抓到并修掉的：
> `python3` 存在但没有 `ensurepip`（Debian 把 `python3-venv` 拆出去了）、另一进程占用
> `dpkg` 锁、unit 缺省 `User=` 导致服务跑成 root、以及**配置目录被解析到模板目录**
> （模板里的 `SOAPBOT_CONFIG_DIR=./config` 是相对路径，systemd 的工作目录就是 checkout，
> 于是面板改的是随仓库发布的模板，而安装器每次 `git pull` 会把它改回去；`data/config`
> 甚至根本没被创建）。现在配置目录跟随数据目录，模板那行已改为注释说明原因；真机上验证过：
> 面板保存落在 `data/config/providers.yaml`（可写卷），随仓库的 `config/providers.yaml` 一行未动，
> 面板读回来就是刚写的那条。
>
> **仍未实测**：Docker 路径（本机无 `docker`）、非 Debian 系发行版、以及在已存数据的旧安装上升级。

> **首次运行没有 Provider 是刻意的**：模板 `config/providers.yaml` 是空的。一个引用了未设置环境变量的
> 模板，会让每一次全新安装都以 `references unset environment variable` 拒绝启动——什么都没配就已经看起来坏了。
> 在第 07 页加一个即可（那边有「测试」按钮能当场证明它答得上话）。

> **Linux 一侧仍未在真机跑过**：本机没有 Linux 主机，`install.sh` 只通过语法检查；
> 首次在服务器上运行请把输出整段发回，第一个真实失败点会被直接指出。

### Docker

```bash
cp .env.example .env      # 至少填 OWNER_IDS 与主密钥来源
docker compose -f deploy/docker-compose.yml up -d --build
```

镜像要点（详见 `docs/deploy-layer.md`）：非 root 用户、`data/` 为卷、`config/` 只读、
主密钥从文件挂载。部署前跑一次 `doctor --strict`。

容器里 `.env` 被显式指到 `/data/.env`（`SOAPBOT_ENV_FILE`）。根文件系统是只读的，
默认位置在 `/app`，第 12 页保存设置会直接失败——把它放在数据卷上，保存才能落盘并在重启
后生效。`scripts/check_deploy.py` 会静态校验这一条。

> **容器未经实测。** 本机无 `docker` 命令，`check_deploy.py` 只能证明配置文件里写了
> `read_only: true`，不能证明容器起得来。9 条验收命令与预期输出见
> [`docs/deploy-layer.md` §8](docs/deploy-layer.md)，需要在有 Docker 的机器上执行。

### 前端

```bash
cd webui
npm install
npm run dev       # 开发模式，代理到 127.0.0.1:6185
npm run build     # 产物写入 src/soapbot/webui/dist
```

产物缺失时后端不会崩溃，`GET /` 返回构建指引——这条是刻意的：容器里没有 npm，
一个「白屏 + 500」会让人以为是权限问题。

---

## 插件系统

### 三步分离

```text
发现（只读清单） → 批准（运维按能力逐项授予） → 加载（执行代码）
```

前两步不会执行任何东西。批准记录持久化在 `data/plugin-approvals.json`，**与清单分开
存放**：清单由插件作者写，批准由运维写，插件更新不能把自己的新能力带成已授权。
启动时会自动加载**已批准**的插件——「批准过」是一个持续有效的决定，不是一次点击。

### 示例插件

四个示例随包发布在 `src/soapbot/examples/plugins/`，用
`soapbot.examples.bundled_plugins_dir()` 取路径：

| 插件 | 演示什么 |
|---|---|
| `echo` | 命令 + 工具注册；`/echo` 与模型可调用的 `echo_text` |
| `help` | 读取其他插件注册的命令，生成帮助列表 |
| `admin` | 敏感能力（`storage`）与角色门槛 |
| `remind` | `cron` 定时任务 + 发消息 |

它们**不会被自动启用**。把它们复制到 `data/plugins/` 后在面板里批准即可：

```bash
cp -r src/soapbot/examples/plugins/* data/plugins/
```

### 最小插件

```yaml
# data/my-plugin/plugin.yaml
name: my-plugin
version: 1.0.0
description: 最小示例
entry: main:Plugin
trust: community
capabilities: [command]
```

```python
# data/my-plugin/main.py
class Plugin:
    def setup(self, ctx):
        @ctx.command("hello", description="打个招呼")
        async def hello(caller, args):
            return f"你好，{caller.display_name}"
```

清单 `capabilities` 必须声明才能注册对应 API：`command` / `tool` / `cron` /
`message` / `notice` / `http` / `memory` / `kb` / `send` / `storage`。
详见 `docs/wave3-plugin-api.md` 与 `docs/plugin-security.md`。

---

## 群管命令

需要 `MODERATE_GROUP` 权限（默认 ADMIN）**且**目标权限严格低于调用者。

| 命令 | 说明 |
|---|---|
| `/mute <QQ> [分钟]` | 禁言，默认 10 分钟，上限 30 天 |
| `/unmute <QQ>` | 解除禁言 |
| `/kick <QQ>` | 移出本群（不拉黑，可重新加入） |
| `/recall-msg <消息ID>` | 撤回，也可引用消息后直接发送 |

拒绝的情况：目标是自己、目标是机器人、目标权限不低于自己、QQ 号非法、非群聊。
`/recall-msg` 额外要求该消息**在本会话归档中存在**——协议端的删除接口只收裸消息 ID、
不带群号，因此「这条消息属于本群」只能由宿主自己的记录来证明。

> `/recall` 保留原义（检索记忆）。撤回命名为 `/recall-msg` 是为了不让既有部署的
> 习惯静默变成另一种行为。

其他核心命令：`/recall`、`/timeline`、`/forget`、`/kb`、`/help`、`/ping`，
开启后另有 `/budget`、`/bili`。

---

## 能力矩阵

如实标注，避免「文档说有、实际没有」。

| 能力 | 状态 | 说明 |
|---|---|---|
| OneBot v11 接入（群 + 私聊） | ✅ | 含撤回/禁言/踢人/群列表 |
| QQ 官方接入（群 + 私聊） | ✅ | 无频道；群管能力受平台限制未实现 |
| 多 Provider 故障转移 | ✅ | 优先级 + 冷却窗口 |
| 人格卡 / 群与用户绑定 | ✅ | |
| 上下文压缩 | ✅ | 折叠 + 摘要 |
| 长期记忆 + 知识库检索 | ✅ | FTS5 + 向量双路融合 |
| 知识库写入 | ✅ | 面板与 API 均可 |
| 图片理解 | ✅ | 含描述缓存 |
| 插件命令 / 工具调用 / notice / cron | ✅ | 两种加载模式均可用 |
| 插件进程隔离 | ✅ | 默认开启 |
| 插件批准持久化 + 启动自动加载 | ✅ | |
| 群管命令 | ✅ | |
| 额度审批 | ✅（默认关） | |
| B 站元数据与观后感 | ✅（默认关） | L3 登录态未实现 |
| 插件包安装 | ✅ | **上传 zip 即安装，不等于批准**——没有在线商店、没有搜索与评分。装完仍需 `approve` + `load` |
| MCP 客户端 | ✅（默认关） | `config/mcp.yaml` 声明式接入，工具作为独立来源注入模型调用，按 server 的 `min_role` 逐个授权；`GET /api/mcp` 报告每个 server 的工具数与错误 |
| MCP 面板编辑 | ✅ | 07 页可直接增删改：读取 → diff → 确认 → 写入，写入后热重载并逐 server 报告「N 个工具」或「启动失败·原因」。**仅 owner**——新增一台服务器等于开放一条子进程执行通道。`env` 只写不读：接口只回键名，diff 里显示 `redacted:` 指纹而不是值 |
| 语音 | ✅（默认关） | 入站转写（多 Provider 故障转移）+ 出站 edge-tts（需 `.[voice]`）。没有厂商凭据时以明确失败降级，不伪造结果 |
| 流式输出 | ✅（默认关） | `STREAM_REPLY=true` 且适配器声明 `PROGRESSIVE` 才生效——目前只有 OneBot v11 声明。工具调用轮次不流式。09 页可观察：首 token / 首句送达 / 整条回复三段耗时 + 实际发出的分句 |
| 多语言 | ✅ | 中文 / English，三条通道：机器人发到群里的话（`DEFAULT_LOCALE`，人格卡可逐群覆盖）、API `detail`（按 `Accept-Language`）、面板全 12 页含外壳与图表（按浏览器切换并持久化）。流水线阶段名与顺序约束由后端按请求语言输出，不在前端维护第二份文案。**日志与堆栈有意保持英文**：同一事件在不同语言下变成不同字符串，会让 `grep` 与告警规则静默失效。`tests/test_webui_i18n.py` 用「模板里不得残留中文」防止半翻译回归 |
| 插件间互相调用 | ❌ | 设计如此：插件 A 不能借插件 B 提权 |

---

## 安全默认值

- 管理 API 对非本机来源要求签名令牌；本机免令牌只是便利，不是边界。
- 私聊默认拒绝（`ALLOW_UNKNOWN_PRIVATE=false`）。一条没被记录的私聊就是一条免费的
  数据外泄通道。
- 插件需要显式批准，权限按能力逐项授予，且默认在独立进程中运行。
- Provider 的写入需要 ADMIN 权限，且必须走「读取 → diff → 确认 → 写入」：diff 由服务端
  用**与启动同一套解析器**校验后计算，写盘前展示，改动只记字段名进审计日志。
  这取代了原先「配置类写入不提供 API」的说法——那条规则假设文件在版本管理里、改动会被
  评审，而单机部署中这个前提通常不成立。理由见 `docs/architecture.md §6.1`。
  人格卡仍只读（Markdown + front matter 用表单渲染会丢正文）。
- 审批不能由发起人完成；额度、配置、群管、记忆读写是**四个独立权限**。
- 模型输出若复述了不可信内容的 canary，整条回复丢弃而不是尝试清洗。

部署前请跑 `python -m soapbot.cli doctor --strict`，并阅读 `docs/security-model.md`。

---

## 常见问题

**机器人收到消息但不回复。**
按顺序查：`config/providers.yaml` 是否有可用端点（`GET /api/providers`）；群里是否
@了它或说了唤醒词（唤醒词来自人格卡）；`GET /api/runtime` 的 `metrics.halted` 是否
在涨——中止原因会写进日志，`reason=not_woken` 与 `reason=private_not_allowed`
的处置完全不同。

**私聊发了没反应。**
默认谁都不能私聊。把 QQ 号加进 `SOAPBOT_PRIVATE_ALLOWLIST`，或显式设置
`SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true`。

**插件显示「已启用」但没在跑。**
看面板里的「已授权」是否是「部分」——清单新增了能力而批准没覆盖时会这样。
`GET /api/plugins` 的 `approval.manifest_changed` 为 `true` 说明清单在批准后被改过。

**控制台白屏。**
`GET /` 返回的不是 HTML 而是指引文字，说明 `src/soapbot/webui/dist/` 缺失。
`git clone` 自带该产物；只有手动清理过才需要 `make ui`。

**`SettingsError: error parsing value for field ...`**
列表型变量写成了无法解析的形式。用 `a,b`、`a;b` 或 `["a","b"]`。

---

## 免责声明

- **个人号接入风险**：通过 OneBot 协议（NapCat / Lagrange 等第三方协议端）接入 QQ
  个人账号存在被平台风控、限制甚至封号的风险。本项目仅实现协议客户端，**不内置任何
  QQ 协议逆向代码**，风险由使用者自行承担。
- **官方机器人审核**：接入 QQ 官方机器人开放平台需自行完成开发者注册与审核；群聊场景
  需在开放平台额外申请开通。
- **B 站数据获取**：哔哩哔哩开放平台开发者服务协议禁止以任何自动程序获取平台数据。
  本项目默认使用 L1 静默模式（仅免签名公开元数据），升级到 L2 档位需使用者自行确认
  合规性并承担相应责任。L3（登录态）**未实现**。
- **支付安全**：本项目**不持有任何支付凭据、不调用支付 API、不自动扣款**。所有消费
  均需人工二次授权。

---

## 许可证

MIT，见 [`LICENSE`](LICENSE)。其中说明了与 AstrBot（AGPL-3.0）的关系：本项目参考其
分层思路，未包含其代码。

变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。

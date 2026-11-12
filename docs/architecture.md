# 架构说明

这份文档回答三个问题：为什么要分成这几层、层与层之间的约束是什么、以及哪些设计是
**刻意不做**的。它不是 API 手册（那些在各模块的 docstring 里），也不是部署指南
（见 `deploy-layer.md`）。

---

## 1. 分层与依赖方向

```text
        api/  ──────────────┐
                            │（只调用 builder 与各层的只读接口）
        webui/dist          │
                            ▼
   core/runtime.py ──▶ core/pipeline.py ──▶ core/stages.py
        │                    │
        │                    ├──▶ ai/        （引擎、人格、压缩、视觉）
        │                    ├──▶ memory/    （归档、记忆、知识库、命令）
        │                    ├──▶ security/  （主体、审计、注入防护）
        │                    └──▶ plugins/   （命令、工具、通知、cron）
        │
        └──▶ adapters/  ◀── core/adapter.py （契约）
```

依赖只能**向下**：`core` 不知道任何具体适配器（通过注册表按名字取），`adapters` 不认识
流水线，`plugins` 拿不到数据库或适配器。这条规则的收益是具体的：新增一个 QQ 接入方式
不需要改 `ai/` 一行；新增一个模型供应商不需要改 `adapters/`。

反向的例外只有一处，且是刻意的：`plugins/dispatch.py` 被 `core/builder.py` 在
`build_pipeline` 内部**延迟导入**。原因是插件 Stage 只有在存在插件管理器时才需要，
而 `plugins` 又依赖 `security`/`core`——顶层导入会形成环。延迟导入把环限制在一个函数
里，而不是让整个模块图变复杂。

---

## 2. 为什么是 Stage 链而不是中间件

早期版本用「中间件栈 + 返回值表示是否继续」。改写成显式 Stage 链的原因是**顺序即安全
语义**，而中间件栈的注册顺序藏在各处 `app.use(...)` 里，没人能一眼看出权限检查在
持久化之前还是之后。

现在的约束是：

- Stage 只能通过 `PipelineContext` 通信（`extras` 是有意的弱类型袋子）。
- Stage 返回 `StageResult(halt=True, reason=...)` 表示终止，**且必须给 reason**。
  没有 reason 的终止在排查时等同于一个静默丢弃。
- 装配只发生在 `core/builder.py::build_pipeline`，测试和生产走同一条路径。否则
  「测试通过」不说明部署可用——这是本项目反复踩到的坑（插件工具、notice、群管
  三项能力都是「组件齐了但没接线」）。

关键顺序及其理由：

| 位置 | 为什么必须在这里 |
|---|---|
| `guard` 在 `whitelist` 之前 | 白名单要判断「谁在哪儿说话」，身份得先建立 |
| `wake` 在 `strip_wake` 之前 | 去掉 @ 之后就再也判断不出「是不是在叫我」 |
| `sanitize` 在 `injection_screen` 之前 | 先清理零宽字符，否则注入检测可被不可见字符绕过 |
| `injection_screen` 在 `persist` 之前 | 被判定为注入的内容不该变成「记忆」 |
| `persist` 在 `skip_reply` 之前 | 没被 @ 的消息也要归档；归档完才决定要不要回话 |
| `skip_reply` 在 `command` 之前 | 一个只听不说的群，不该因为有人发了斜杠命令就开口 |
| `persist` 在 `model` 之前 | 模型调用失败时用户消息仍要留下，否则历史有洞 |
| `knowledge`/`recall` 在 `model` 之前 | 检索结果是提示词的一部分 |
| `safety` 在 `reply` 之前 | 输出清理必须发生在发送之前 |

`persist` 曾经在 `wake` 之后，于是「只有被叫到才入库」——这让「把这个群记下来」变成
不可配置的事。现在归档由**采集群**决定，回不回话由**回复群**决定，两者互不影响：
`WhitelistStage` 把两个判断都写进 `extras`（`memory_collect` / `replies_here`），
`PersistStage` 读前者，`SkipReplyStage` 读后者。`SkipReplyStage` 用 `is False` 而不是
假值判断——没有这个键（自建流水线的调用方）意味着「不限制」，而不是「全部禁言」。

---

## 3. 三条贯穿全项目的原则

### 3.1 未接线的能力等于不存在

本项目的缺陷统计里，**「组件存在、无人调用」比「实现错误」多得多**：

| 能力 | 断在哪 |
|---|---|
| 插件工具 | `available_for()` 零调用方、`AIRequest` 无 `tools` 字段 |
| notice | 适配器丢弃、`emit` 提前 return、`on_notice` 无调用方 |
| 知识库写入 | `add_document` 实现完整、服务内无调用方 |
| 群管 | 声明了 4 个能力、0 个方法 |
| 插件批准 | 纯内存，重启即丢 |
| 私聊准入 | 参数传入 `build_runtime` 后未被使用 |

因此约定：**新增能力必须同时给出「谁调用它」**，并且测试断言的是**连接**而不是两端
各自的行为。`tests/test_delivery_wiring.py` 就是这些连接的登记簿。

### 3.2 安全默认值向关闭方向倾斜

不对称是有意的：群聊空名单 = 允许所有（不加入群就无法使用），私聊空名单 = **谁都不行**
（私聊是直通人格 + 记忆 + RAG 的私有通道，没有旁观者）。

能力也一样：`http`、`memory_read`、`send` 等敏感能力默认不授予；额度、B 站、额度审批
默认关闭。理由不是「保守」，而是**默认开启的功能等于替用户做了合规决定**——B 站
开发者协议禁止自动采集，一个「除非关掉否则开着」的开关会让每个使用者默认违约。

### 3.3 注释记录被推翻的方案

代码里大量注释写的是「为什么不是另一种做法」，而不是「这段代码做什么」。例子：

- `plugins/approvals.py` 说明为什么批准不放进清单文件。
- `plugins/sandbox.py` 说明为什么 `CapabilityGrant` 必须冻结、`CapabilityGuard` 必须密封。
- `adapters/onebot11.py` 说明为什么 `emit` 不能内联等待处理函数（自死锁）。
- `ai/engine.py` 说明为什么工具结果以系统提示回灌而不是严格回显 `tool_calls`。

理由是：读过代码的人下一个问题一定是「为什么不那样做」。答案如果只在某人脑子里，
同一条弯路会被反复走。

---

## 4. 插件隔离：进程边界是唯一的边界

`plugins/sandbox.py` 里的所有进程内防护（密封对象、能力检查、导入净化）都是**减速带**，
不是沙箱：Python 的 `object.__setattr__`、`ctypes`、`sys.modules` 反射都能绕过。
真正的保证来自子进程——`plugins/worker.py` 里跑插件，宿主只通过管道通信。

因此默认 `isolate=True`。把它设成 `False` 的场合只有两个：嵌入式使用，以及无法创建
子进程的平台。`soapbot doctor` 会报告当前模式。

代价是协议变复杂（命令表在宿主、实现在 worker），收益是「插件崩溃不会带走机器人」和
「插件拿不到宿主的对象图」。这个交换在 `docs/plugin-isolation.md` 里有完整记录。

---

## 5. 与 AstrBot 的关系

- AstrBot（[仓库](https://github.com/AstrBotDevs/AstrBot)）是 **AGPL-3.0**。
- 本项目参考的是它的**分层取舍**：平台适配 / 模型提供 / 消息处理 / 插件四层解耦。
- 本项目**未包含、未复制、未改编**其任何源码。标识符、注释、实现均为原创；本项目
  在安全模型上走得更远（进程隔离、逐能力授权、审批持久化、注入 canary）。
- 分层思想本身不受著作权保护，但这个界线必须写明，因为它是许可证审计的第一现场。
  见 `LICENSE` 末尾的说明。

如果将来需要引入 AstrBot 的代码，只有两条路：整体改为 AGPL-3.0，或把该部分做成独立
可替换组件并明确标注来源与许可。**直接复制会让现在的 MIT 声明失效**，且这是发行层面
的问题，不是代码风格问题。

---

## 6. 刻意不做的事

| 不做 | 理由 |
|---|---|
| 插件互相调用 | 插件 A 若能调用插件 B，就等于 B 的能力对 A 开放；逐能力授权的意义被抵消 |
| 配置类写入 API | ~~人格改一行就能删掉安全段落，Provider 改一行就能把流量指向别处。留在文件里才可评审~~ **此条已修订，见下方「配置写入的评审面」** |
| 内置 QQ 协议逆向 | 法律与稳定性风险；只做协议客户端 |
| L3（登录态）B 站 | 项目不持有任何平台账号，实现它等于鼓励使用者交出 cookie |
| 支付 API | 额度审批是**记账与授权**，不是支付通道 |
| 自动加载未批准插件 | `data/plugins` 是可写目录；执行里面的一切等于把写权限变成代码执行 |

---

## 6.1 配置写入的评审面（修订上表中「配置类写入 API」一条）

上表的理由是对的，但它假设了一个当时不成立的前提：**配置文件在版本管理里**。单机
部署的典型情况是 `config/providers.yaml` 从没进过 git，运维用 SSH 打开编辑器改完
就保存——没有第二个人看过，也没有任何记录。那时「留在文件里才可评审」这条规则实际
上保护的是零。

写入 API 不是放宽这条规则，而是第一次让它可执行：

| 环节 | 实际发生的事 |
|---|---|
| 读取 | 密钥脱敏后返回，同时给出 `base_hash`（乐观锁令牌） |
| diff | 服务端用**与启动同一套解析器**校验候选文档，算出真实的行级 diff，**不写盘** |
| 确认 | 运维看到的是即将写入的每一行，包括表单没渲染的注释和字段 |
| 写入 | 校验 `base_hash` 未变（否则 409）、`approved_hash` 与确认内容一致（否则 409），再原子写 |
| 记录 | 审计只记**字段名与操作者**，不记值 |

任何一步都不比「SSH 改文件」更弱，且多了两样那时没有的东西：一次显式的确认，和一条可查的记录。

三条不可让步的约束（都有测试守着）：

1. **不整文件覆盖，只做字段级合并**。否则「读取时脱敏 → 保存时回传」会把真实密钥
   覆盖成 `********`，而这个 bug 在保存时静默、在下次启动时致命。
2. **候选文档必须先通过启动解析器**。面板不允许存出一个下次启动必崩的配置——
   `env:` 引用未设置的变量在写入时就要报 422。
3. **不热重载**。`ProviderRouter` 有冷却窗口、`Pipeline` 已装配、`PersonaStore` 有
   绑定态，回滚三者需要同时快照，成本高于「点一下重启」。响应里明确返回
   `restart_required: true`，界面显示常驻横幅——假装热重载比不热重载更危险。

## 6.2 流水线顺序不可由 UI 修改

22 个 Stage 的顺序是安全语义（`guard` 在 `whitelist` 前、`sanitize` 在
`injection_screen` 前、`safety` 在 `reply` 前）。因此 09 页只提供**只读拓扑**与一个
**沙箱**：可以拖拽试排，页面会指出破坏了哪一条具体约束，但结果不写回任何地方。

做成可拖拽保存会让人以为这是一张流程图，而实际改一行就能让零宽字符绕过注入检测。

## 7. 阅读顺序建议

1. `core/message.py` → 数据长什么样
2. `core/adapter.py` → 一个平台要提供什么
3. `core/builder.py::build_pipeline` → 顺序与理由（本文件第 2 节是它的摘要）
4. `core/stages.py` → 准入与唤醒
5. `ai/engine.py` → 一次模型调用的全部输入
6. `security/principal.py` → 权限从哪来（只有配置）
7. `plugins/loader.py` + `plugins/approvals.py` → 插件生命周期
8. `plugins/dispatch.py` → 插件如何被调用

---

## 附录：模块一览与一条消息的旅程

> 原来放在 `README.md`，因为篇幅挪到这里。正文回答「为什么这样分层」，这部分回答「代码在哪」和「消息怎么走」。

### 模块一览

```text
soapbot/
├── src/soapbot/
│   ├── core/           # 编排层：消息模型、适配器契约、流水线、运行时、调度器
│   ├── adapters/       # 接入层：OneBot v11、QQ 官方、mock（测试用协议端）
│   ├── providers/      # 模型层：能力槽、OpenAI 兼容实现、故障转移路由
│   ├── ai/             # 智能层：人格卡、上下文压缩、视觉、引擎、AI Stage
│   ├── memory/         # 数据层：消息归档、三层记忆、知识库、检索、命令 Stage
│   ├── accounts/       # 存档账号：scrypt 密码、邀请码、会话授权（不引用任何适配器）
│   ├── security/       # 防护层：主体与权限、审计、注入防护、密钥、令牌
│   ├── plugins/        # 扩展层：清单、沙箱、加载器、进程隔离、命令/工具分发
│   ├── budget/         # 可选：额度账本与二次审批
│   ├── bilibili/       # 可选：公开元数据、wbi 签名、观后感
│   ├── api/            # 对外：FastAPI 路由（鉴权 / 账号 / 存档 / 管理 / 插件 / B 站 / 安全 / 配置写入 / 流水线）
│   ├── examples/       # 随包发布的示例插件（不是内置功能，仍需批准）
│   └── webui/dist/     # 前端构建产物（随 wheel 发布）
├── webui/              # 前端源码（Vite + Vue 3 + TypeScript）
├── mobile/             # Flutter 客户端，默认关闭的端；CI 产出可下载 debug APK，真机 E2E 未做
├── config/             # **模板**（providers/adapters/mcp/personas），首次启动播种到 data/config，之后不再读它
├── data/               # 可写卷：SQLite、日志、上传、插件目录、批准记录，以及 data/config（面板真正编辑的那份，gitignore）
├── deploy/             # install.sh（一键部署）、Dockerfile 与 docker-compose
├── docs/               # 设计记录、安全模型、交付评估
├── scripts/            # check_deps.py 等仓库工具
└── tests/              # pytest（2273 项通过 / 12 项跳过）
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

**`accounts/` — 存档账号**

- `service.py`：密码 `scrypt(n=2**14, r=8, p=1)`（salt 与 hash 分列、`compare_digest`）、
  邀请码只存 SHA-256（一次性、默认 72 小时）、`chat_memberships` 授权、`account_from_claims`
  把令牌 subject 还原成账号。
- `active_account_from_claims`：停用账号不是主体。`authenticate` 只挡住**下一次**登录，
  老 cookie 在过期前仍有效，所以每个读存档的入口都要走这里，否则「停用」只是「不许再登录」。
- 这一层**不 import 适配器**：存档能读不能发，靠调用图而不是注释保证。

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

### 一条消息的完整旅程

以群里有个人 @机器人 说「这张图里是什么」为例：

1. `adapters/onebot11.py` 收到 WebSocket 帧，转成 `IncomingMessage`
   （AT 段 + 文字段 + 图片段），`emit` 派发。
2. `BotRuntime._on_event` 按 `session_key` 加锁，进入 `Pipeline`。
3. `DedupStage` 丢掉重复投递；`GuardStage` 解析出 `Principal`（角色只来自配置）。
4. `WhitelistStage` 判断这个群是否允许（两个名单都空 = 全开），并把「要不要归档」
   （`memory_collect`）和「要不要回话」（`replies_here`）写进 `extras`。
5. `WakeStage` 看到 AT 段指向自己 → 通过，记录 `wake_reason=at`。它**不再**因为没被叫到
   就终止，只记录判断结果。
6. `StripWakeWordStage` 去掉 AT 段与唤醒词；`SanitizeStage` 去控制字符。
7. `InjectionScreenStage` 检查越权指令。
8. `PersistStage` 归档这条消息（采集群内才写；模型调用失败也要留下，否则历史有洞）。
9. `SkipReplyStage`：没被叫到（`not_woken`）或这个群只采集不回复（`group_not_replied`）
   → 到此为止。归档已经完成，只是不开口。
10. `AuthorizationStage` 确认能聊天。
11. `CommandStage` / 插件命令 / 插件钩子：不是命令，继续。
12. `PersonaStage` 按群 + 用户解析人格卡；`RecallStage` 检索记忆；
    `KnowledgeStage` 检索知识库——两者都以**不可信数据块**注入系统提示。
13. `ModelStage`：语音段先转写（转写文本**同样过注入筛查**——嘴说出来的不是可信输入），
    图片按内容哈希查缓存，未命中才调用视觉模型；随后带工具列表请求主模型；
    若模型要求调用工具，执行后把结果作为不可信数据块回灌，最多两轮。
    开了 `STREAM_REPLY` 且没有工具待调用时，改为边生成边按句发送。
14. `SafetyStage`：清理不可见字符、拦截提示词泄漏、检测 canary 复述、
    脱敏疑似凭据、按人格卡截断。
15. `ReplyStage` 通过适配器 `degrade()` 降级不支持的段落后发送；开了
    `VOICE_TTS_ENABLED` 时先合成为语音，失败或过长则回退为文本。
16. `PersistReplyStage` 归档回复；`MemoryWriteStage` 异步抽取值得记住的事实。

任何一步都可以 `StageResult(halt=True, reason="...")` 终止——终止原因会进指标和审计，
这是排查「机器人为什么不回我」的第一手材料。

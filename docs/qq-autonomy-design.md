# QQ 自主化设计：主动对话、空间、表情包、人格与温度

> 状态：**设计 + 宿主能力面已实现**。已实现：`send_media`（#45 同批）、
> 消息图片段的按需能力面 `media_observe`（§3 / §5 第 1 项）、
> 公开网页浏览与消费提案（§5 第 0 项）、`qzone_read` / `qzone_write`（§2）；
> 设计待做：QQ 空间读写（风险分级见 §2）、宿主级温度模型（§4）、
> WBI 字幕读取、人格卡三个可选字段。
> 扩展政策：本页描述的**用户侧功能**全部落在插件仓库（`packages/`），本体只新增
> 受审能力面——与 bilibili/send_media 同模式。

## 1. 主动对话（自主开口）

**形态：插件**（`auto-chat`，本批随插件仓库发布）。被动应答是管线，主动开口是
「cron + 记忆 + send」的组合，不需要新宿主能力。

约束（插件的自我克制，也是能力面自然给出的）：

- **只发到观察过的会话**：宿主 ledger 本来就拒绝未观察的会话——bot 不能凭空打扰
  陌生人；插件再收窄为「操作者用 /autochat-set 显式开启的会话」。
- **频率上限**：每会话两次主动发言之间 ≥4 小时、每天 ≤2 条、全局每轮 cron 只挑
  一个会话。写死在插件里（判断标准悄悄可改 = 行为悄悄可改）。
- **开口内容来自记忆**：用 `memory.recall` 取该会话近期话题，套进有限的开口模板
  （「你上次说的 X 后来怎么样了」）。没有模型调用——插件能力面刻意不含跑模型；
  要更自然的开口，走人格卡 evolution（宿主侧，见 §4）。
- **温度阈值**：见 §4。低于阈值的会话 cron 直接跳过。

## 2. QQ 空间（说说/动态的读与写）

**风险分级，必须先说清楚**：QQ 官方机器人开放平台**没有**空间/说说的任何接口。
空间读写只有一条路——个人号协议端（NapCat 的扩展能力），这正是本项目 README 与
SECURITY.md 反复声明的风控区：个人号行为可能触发平台风控，账号可能被冻结。因此：

- **默认关闭，且不是开关默认值的问题**：`qzone` 能力面在宿主里不随版本启用——
  只有操作者显式设置 `SOAPBOT_QZONE_VIA_PROTOCOL=true` 才可用，配置注释写明
  「账号风险自负」。读与写是两个能力：`qzone_read`（浏览空间/说说）与
  `qzone_write`（发说说）**分开审批**，写的门槛更高。**已实现**，见下文。
- **凭据**：空间的登录态就是协议端的登录态（NapCat 已登录），宿主持有、插件不碰。
- **写操作三重确认**：插件申请 `qzone_write` 时，面板审批页额外显示「此能力通过
  个人号协议端执行，有账号风控风险」；发说说前插件侧再留一次命令级确认（同
  fishtalk-lite 的 forget 模式）；审计记动作与文本长度，不记正文。
- **形态（已实现）**：宿主 `qzone.py` 是 fail-closed 网关，只转发四个白名单动作
  （读 `get_friend_feeds` / `get_user_feeds`，写 `send_qzone_post`）到操作者点名的
  OneBot 兼容 HTTP 端点；Bearer token 宿主持有，插件拿不到也看不到。
  写还要过三道：宿主开关、`qzone_write` 能力批准、插件侧二次命令确认，且每次调用
  必须带 `confirm=true`。审计只记动作与文本长度，不记正文、token 与端点 URL。
  两个示例插件已落地：`qzone-diary`（起草→确认→发说说）、`qzone-watch`（读新说说
  并摘要，只申请 `qzone_read`）。
  **未做**：与真实 NapCat / Lagrange 部署的联调（协议端动作名以各实现为准），
  以及发布到插件仓库。开启前请自行确认协议端风险自负。

## 3. 表情包与照片（自己储存、后续使用）

**分两半**：

- **存**：插件 `sticker-album`（本批发布）——`/meme-save <URL|附件说明>`、
  `/meme-list <标签>`、`/meme-send <标签>`、`/meme-forget`。图片以 base64 存进
  插件加密 storage（单张 ≤4 MiB、总量 ≤100 张），数据不出插件命名空间。v1 的
  来源是 URL（操作者配置的 http 白名单域）；「从聊天里顺手收藏」的宿主能力面
  **已实现**（本批），交付形态与隐私边界见 §5 第 1 项。另外「从公开商品页直接生成
  消费提案」也已落地：宿主 `browse` 能力面（见 §5 第 0 项）读页面、提取规格与价格、
  做日/月限额预检，再往额度账本写一笔待批申请；实际购买仍由人在官方渠道完成。
- **发**：宿主新能力 `SEND_MEDIA`（**本批已实现**）——与 `send` 同一套
  observed-session ledger，但单独审批（「能说话」和「能发图」是两个决定）；解码
  与 4 MiB 上限在**两处边界都强制**（进程内 context 与隔离模式的 SurfaceRouter，
  隔离是默认形态，只有一个路径有的上限等于没有）；审计只记 base64 字符数。

## 4. 人格卡生态与情感温度

- **人格卡新增可选字段（已实现）**：`autonomy`（主动开白名单与每日上限）、`warmth`
  （起点 / 增速 / 衰减 / 阈值）、`voice_self_select`（是否允许自主挑音色）。
  三者留在 front matter 的 `extra` 里由 `ai/autonomy.py::parse_autonomy` 校验——
  刻意**不**新增 `Persona` 已知字段，否则面板编辑器（只认九字段）每次保存都会把它们
  悄悄重置。顺带修好 `persona_to_payload` 不带 `extra` 的旧缺陷，回滚不再丢手写字段。
  `voice_self_select` 目前只是配置开关，挑音色的管线环节仍按 §3 的设计未实现。
- **情感温度模型（宿主级已实现）**：`WarmthTracker` 只在回复成功归档后计一次交互，
  7 天窗口、纯内存、有界；`compute_warmth` 是对数归一减线性衰减的确定性函数，
  阈值默认 0.6，参数来自人格卡 `warmth`。`SessionView` 与隔离模式的 `session.view`
  显式字典增加只读 `warmth` 标量。数值不由模型或插件写入。
- **生态优化方向**：人格卡模板库进插件仓库（同 luanyujia-workbench 的改编路线）；
  人格卡与记忆场景的绑定已有（scene memory），温度模型接入后，人格的「亲密度
  分层」就有了数据来源。

## 5. 待宿主能力清单（按优先级）

0. **✅ 已实现**：公开网页浏览 + 消费提案（`browse` 能力面）。域名白名单默认空
   （拒绝一切）、robots.txt 同意、可识别 UA、无 Cookie / 登录态 / 重定向 / 表单 / JS；
   `browse.propose` 先做单笔与日/月限额预检，不通过就不建申请；通过后写 pending 申请
   并发布 `REQUESTED` 事件，仍要人审批。**未做**无头浏览器 / 模拟手机的 JS 渲染、
   电商登录态、代付链接与支付 API。见 `docs/capabilities.md`。
1. **✅ 已实现**：消息图片段的按需能力面 `media_observe`。宿主在消息钩子阶段把当条
   消息的 http(s) 图片引用放进**纯内存**的 `MediaInbox`（按会话分桶、TTL 120 秒、
   取一次即消费、单条消息 ≤16 个）；插件凭单独审批的 `media_observe` 调
   `ctx.observe_images()` 取走，不带任何参数——会话键由宿主绑定的 caller 决定，
   隔离模式的 `_RemoteCtx` 走同一个 surface `media.observe`，父进程 guard 复核。
   **刻意不做广播**：一次性的、常带签名的图片 URL 不该塞进 `message_received`
   让每个 `message` 观察者都拿到；而且隔离 worker 目前不转发命名事件，靠事件字段
   交付等于对默认形态无效。URL 不进日志、审计（只记数量）、trace、messages 表；
   本地路径与内联 base64 不越过边界。文本消息不清槽，因为「先发图、再发
   `/meme-save`」是两条消息。
   接线证据：`tests/test_plugin_media_observe.py`（16 项，末项是消息钩子→inbox→插件）。
   插件侧责任：立刻把引用存进自己的加密 storage，不要传给 `ctx.log`。
2. **✅ 已实现**：`qzone_read` / `qzone_write`（fail-closed 协议端网关，默认完全关闭、
   读写分开、写三重确认）。见 §2 与 `docs/capabilities.md`。
3. **✅ 已实现**：宿主级温度模型（`WarmthTracker` + `SessionView` / `session.view`
   只读 `warmth`）。见 §4。
4. **✅ 已实现**：WBI 签名的字幕读取。`BilibiliClient.subtitle(bvid)` 走 L2 公开签名
   （不注入 SESSDATA），只返回语言与字幕 URL 白名单；宿主固定端点
   `GET /api/bilibili/subtitle`。**未做**真实 B 站联调与 dsh-bili-humanism 的完整改编。

## 6. 温度模型 v2 设计输入（来自第二批改编，2026-11-12）

第二批插件改编（插件仓库 ADAPTATION.md 第二批）复核了 dsh-longing（暗涌）的七维
状态机。立场不变——**状态不进插件、写入权只在宿主管线**——但它的两个机制是温度
模型 v2 的直接设计输入：

1. **负向事件的不对称衰减**：说错话掉得比说对话涨得快（伤害不对称）。当前
   warmth 只有正向计数；v2 在 `memory/stages.py` 的记录点旁加一个 `penalty`
   通道（如会话出现道歉/冷场识别），衰减窗口与正向相同。
2. **日常值回归**：longing 的「时间推得到日常，推不到 0」——当前 warmth 衰减
   目标是 0；v2 的 `WarmthParams` 加 `baseline`（人格卡可配），衰减趋向 baseline
   而非零，避免长期冷落的会话被模型读成「关系归零」。

实现约束不变：纯内存、有界、不由模型或插件写入、进 trace 可查。

**bilibili 写面待决**：bili-cli 的运营全套需要 bilibili 能力的写动作（发动态等）。
按 qzone 模式（动作白名单 + SESSDATA 宿主注入 + 独立审批 + 显式确认 + 风险自负）
可实现，但写 B 站等于以操作者账号发声，是否启用等操作者拍板后再做。

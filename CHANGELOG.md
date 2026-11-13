# 变更记录

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

本项目的特殊情况：0.1.0 之前的开发没有逐版本留档，因此下面把「能运行但不构成
交付物」的中间状态合并记为 `0.1.0`，并把本轮修复逐条列出。每一条都写明**原来的
错误表现**，而不是只写「修复了 X」——因为这里的缺陷几乎全部是「组件都在、线没接」，
只写结论会让人以为是从零实现，下次仍会以同样的方式漏掉。

## [Unreleased]

### 代码层全面审计（160 文件 47,801 行，只读）

云鼎三层扫描 + AST 结构分析 + code-vuln-crossreview 双视角覆盖 src/soapbot 全部：
**0 P0 / 0 P1**。危险模式命中（md5/sha1/verify=False）逐处核实均为协议要求、
文件名摘要或防御声明；循环内 execute 全部为启动期 PRAGMA/迁移；索引覆盖完整。
报告在 docs/code-audit-2026-11.md，含 P2/P3 维护清单（装配函数拆分时机、插件
生命周期编排、长会话交接语义）与明确不做项（create_app 纯结构搬移回归风险大于
收益）。

### 流畅度与部署优化：面板 KeepAlive、pinned 安装变体

原来错在哪：十五个面板页没有 KeepAlive——每次切换都整页重挂载，滚动位置、筛选
状态、展开的面板全部丢失；useAsync 的缓存只解决数据，不解决组件状态。另外部署
只有「跟随 master」一种远程安装方式，分支一变下载内容就变，想要可复现安装没有
选项（安全审查 P2-1）。

现在：

- **面板 KeepAlive**：AppShell 用 KeepAlive 包裹 RouterView，十五页切换零重挂载。
  带连接与定时器的三个视图配对 onActivated 与 onDeactivated：ChatView 离开时关
  SSE 与会话轮询、回来重建；LogsView 清防抖定时器、回来刷一次；PipelineView
  恢复 live 轮询（同 LIVE_INTERVAL_MS）。
- **pinned 安装变体**：install.ps1 加 -Tag 参数、install.sh 加 --tag 参数——从
  refs/tags/<tag> 下载，tag 不可变所以安装可复现；格式校验拒绝分支名伪装
  （v[0-9]* 才放行）。deploy-quickstart.md 两种命令各加一条。
- install.ps1 PowerShell 语法解析验证通过。

### 项目定位随主体方向更新（多端 AI 陪伴框架）

原来错在哪：README 第一行还是「QQ 群里的 AI 机器人」，pyproject 简介、mobile 的
pubspec 描述同理——但主体方向自2026-11 起已经是「网页/手机/桌面三端为主力、QQ 保
部署能力不着急优化」（见 MEMORY 与多轮交付）。定位句与新现实相反。

现在：

- **README 定位段重写**：「多端 AI 陪伴框架——同一个记忆与人格核心，接 QQ、网页、
  手机 app、桌面壳四类客户端，后三类是当前主力方向」；QQ 不再是默认入口的表述
  写进正文；文档表补插件生态一行（指向 soapbot-plugins）。
- **pyproject 描述**改为 multi-platform AI companion framework（含插件沙箱、温度
  模型、Bilibili 等关键词）。
- **mobile/pubspec.yaml 描述**去掉「Read-only」旧口径（手机端已可对话与写备注）。
- desktop/package.json 描述同步。QQ 定位改写为「部署能力保留的接入渠道之一」，
  与 SECURITY.md / chat-archive.md 的既有口径一致。

### 修复: 手机端在 MuMu 模拟器实测暴露的 CSRF 403——Bearer 优先认证

原来错在哪：手机端只靠会话 Cookie 过鉴权，写请求还要回显 CSRF Cookie。而 CSRF 值
只在登录时下发、旧版本 app 从不保存——**升级安装后旧会话仍有效但 csrf 缺失，
写备注永远 403**（MuMu 模拟器实测截图复现：「CSRF token missing or mismatched」）。

现在：

- **Bearer 优先**：登录返回的 access_token 持久化到安全 storage，后续请求带
  `Authorization: Bearer`。服务端对 Bearer 请求豁免 CSRF（自己的注释写明「跨站
  页面 attach 不了 bearer header」），原生客户端从此不被 double-submit 卡死。
  Cookie/CSRF 保留为降级路径。
- 模拟器实测（MuMu + adb reverse + 隔离数据目录真服务器）：登录 → 会话列表 →
  聊天页 → 写备注 → 气泡落库渲染，全链路通过。

### 修复: subtitle 端点需要 aid/cid（真实视频实测发现）

原来错在哪：`BilibiliClient.subtitle()` 对 `/x/player/wbi/v2` 只传 `bvid`——实测六条
真实视频全部 `-400`。player 端点要求 `aid` + `cid` + `bvid` 三件齐。

现在：subtitle() 先走 view 端点解析 aid 与 cid（pages[0]），再带全三件打签名端点。
测试同步更新为两段请求断言（view → signed player），六条真实视频实测返回空轨
（AI 字幕需登录态，与文档边界一致；UP 上传的 CC 轨不受影响）。

### 两份外部参考评估：ops-handoff 十六篇与 dsh-cua 数据边界

- **docs/reference-ops-handoff.md**：kira905/ops-handoff-design 十六篇运维设计记录
  的逐篇对照。十四篇在 soapbot 已有同源落地（只读巡检、capability 阶梯、文档一致性
  门禁、受控动词……）；三项吸收登记：长会话交接的 worker 重启语义（auto-chat 0.3.0
  行为说明）、假完成识别（审批记录加 done_at，归属面板下批）、批量改文件纪律
  （写面为零暂不需要，记给未来）。
- **autonomous-capabilities-design.md §1.4**：dsh-cua（Windows 桌面自动化，UIA+OCR+
  窗口绑定）作为「自助玩游戏」控制面的技术参考——四条数据边界纪律（截屏只落本地、
  caption 是唯一画面出机点、CDP 端口自认不是隔离、明文 token 的文件化替代）与
  技术选型（UIA 优先于纯视觉 OCR、窗口绑定细化专用机器边界）。控制面开工三前置
  不变，默认关闭立场不变。

### 字幕能力面（bilibili.subtitle）：dsh-bili-humanism 的核心思想在边界内落地

原来错在哪：第一批改编把 dsh-bili-humanism 的字幕学习列为「待宿主能力」——wbi 签名
与 hdslb 字幕正文抓取都是宿主职责，插件面当时只有 get_json。#52 交付了宿主 L2 client
的 subtitle()，但插件面（ctx.bilibili / bilibili.request surface）没有接上，插件依然
拿不到字幕。

现在：

- **宿主 `BilibiliClient.subtitle_text(bvid)`**：字幕列表 → 取第一轨 → 校验 URL 必须
  在 `*.hdslb.com`（https only）→ 宿主代抓正文 → 拼接限长 8000 字。播放地址、账号
  状态等 player 包内容照旧不过边界。
- **插件面两种形态同一契约**：进程内 `ctx.bilibili.subtitle(bvid)`（沙箱 client 委托
  宿主注入的 L2 client）；隔离模式 `ctx.bilibili().subtitle(bvid)` 经新 surface
  `bilibili.subtitle`（宿主侧重新校验能力 + host client 代抓）。
- 测试：bilibili/send_media/events 24 项全过；IPC 67 项、安全边界 89/89。
- 插件仓库同批：fishtalk-lite 0.2.0（collect 升级字幕语料）、bili-scroll 0.2.0
  （whale 克制机制）已发版。

### 自主挑音色实现：人格卡 `voice_self_select` 从字段变成能力

原来错在哪：autonomous-capabilities-design.md §2 把挑音色写成设计（「决策在管线内、
候选集宿主给、挑一次缓存、手动指定优先」），#52 只落了人格卡字段
`voice_self_select`——字段是死的，管线里没有任何代码读它——autonomous-capabilities-design.md §2 的四条验收门槛全部未达成。

现在：

- **`voice/picker.py`**：离线精选的 10 项 zh-CN edge-tts 候选表（每项带一句「气质」，
  不联网拉全量表——数百项会把挑选变成大上下文调用）；模型只能从表里挑，表外音色
  与非 JSON 输出抛 `VoicePickError`；按 (persona_id, session_key) 缓存，一次挑选
  成本 ≤ 200 tokens 的轻量调用。
- **ReplyStage 接线**：人格卡 `voice_self_select: true` 且操作者的
  `voice_tts_voice` 仍是出厂默认时，管线在合成前向 picker 要一次音色；失败回退
  默认音色、回复照常发出（挑选失败不能让回复消失）。手动指定永远优先。
- **决策可见**：`ctx.extras["voice_pick"]` 记「音色:来源:理由」，trace 可查。
- **EdgeTts.synthesize(text, voice=)**：每次调用的音色覆盖，None = 操作者配置。
- 测试 8 项：picker 契约（缓存/表外拒绝/非 JSON/单人失效）+ ReplyStage 四决策
  路径（自选生效/操作者优先/失败回退且回复照发/无人格回退）。

### 全库安全审查报告（只读，结论 0 恶意 / 0 可疑必须处理 / 2 项 P2）

按云鼎三层审查流程（关键词扫描 → 深度分析 → 供应链溯源）对主仓库、插件仓库六包、
CI 与部署命令面做了一轮只读审查；同时用双视角复核 #49–#53 的安全敏感面（WBI 字幕、
温度写入权、审批 feed、qzone 网关）。报告在 docs/security-review-2026-11.md：
逐面判定表 + 2 项 P2 建议（pinned tag 安装变体、失效 docker 镜像标注）。
审查全程未执行任何被审代码。

### 三份外部参考的核实与适配，以及本仓库的去 AI 味写作规范

原来错在哪：图片里给的三个链接，两个 404、一个名字写错，直接照抄会写出凭空的分析；
而「加一个去 ai 味 skill」在仓库里既没有 skill 目录，也没有任何与本仓库文档口径相关的
规则。全盘照抄第三方 SKILL.md 会带进一套「门检 / 终稿 / 打磨报告」的发布稿模板，
与本仓库 CHANGELOG「写清原来错在哪」的写法完全不搭。

现在：

- **先核实地址**：`zuho-kai/bothouse` → 实为 `zuiho-kai/bothouse`；
  `mearihaka/dsh-linging` → 该用户唯一公开仓库实为 `mearihaka/dsh-longing`（`longing`）；
  `github.com/Fangi8` 的 GitHub API 返回 404，**登记为待用户提供正确地址，不编造内容**。
- `docs/reference-external-2026-11.md`：延续既有 `reference-*.md` 的口径（只读评估、
  不引入源码/依赖/运行时、每条对照落到一处改动或一条「不改」）。bothouse 的
  「只有需要人的决策回到聊天 / 规则草稿需人批准」与本仓库审批事件总线是同一治理目标，
  **不移植**多 CLI 团队与派单；dsh-longing 的「被算出来的角色状态」与本仓库温度模型
  写入权相反，**不移植**七维状态机。
- `src/soapbot/examples/plugins/warmth-observer/`：把它适配成只读观察者，用
  `ctx.session.warmth` 报告温度与阈值，只声明 `command` + `session`，不申请
  `send` / `cron` / `storage`，也不写状态。
- `docs/writing-style.md`：把 `qu-ai-wei` 的三条**约束**（敏感信息门检、冻结信息账本、
  不鉴定作者）按本仓库口径改写，附上「原来错在哪 / 不假装修了 / 未实测标未验证 /
  数字同步 / README 四块」等具体规矩；没抄它的八族模式目录与三段式输出契约。
- `scripts/ai_flavor_scan.py`：纯标准库、只读、不默认进 CI 的可选自查工具。单次
  「不是 X 而是 Y」不报，同文件出现三次才算信号——只凭一个句式就鉴 AI 正是参考 skill
  明确反对的做法。`ai_flavor_scan.py` 在本仓库只报 1 处，是既有技术文档里的固定措辞。

`tests/test_ai_flavor_check.py`（7 项）。孤儿基线 11 → 12（`warmth-observer` 与既有
示例插件同等对待），mypy 排除扩到带连字符的示例插件目录，避免 duplicate module 掩盖基线。

### 人格卡自主字段、宿主温度模型与 WBI 字幕

原来错在哪：`qq-autonomy-design.md` §4 把 `autonomy` / `warmth` / `voice_self_select`
写成「下一批实现」，`§5` 把 WBI 字幕列为待办，但三者**零实现**；而且人格卡版本快照
`persona_to_payload` 根本不带 `extra`——就算把新字段写进 front matter，面板保存能留住，
一次回滚也会全部丢掉。`autonomous-capabilities-design.md` 的挑音色仍是设计，本文没有
假装实现它。

现在：

- `ai/autonomy.py`：三个可选配置从人格卡 `extra` 读取并校验（会话白名单、每日上限、
  温度参数、`voice_self_select`），非法值回退保守默认而不是放宽。刻意**不**新增
  `Persona` 已知字段——面板编辑器只认九字段，新增已知字段会让每次面板保存把三字段
  悄悄重置。`voice_self_select` 目前只是配置开关，挑音色的执行器仍按设计文档未实现。
- 修 `persona_to_payload` / `persona_from_payload` 带上 `extra`，回滚不再丢手写字段。
- 宿主温度模型：`WarmthTracker` 只在**回复成功归档后**记一次交互，7 天窗口、纯内存、
  有界；`compute_warmth` 是对数归一减线性衰减的确定性函数，不由模型或插件写入。
  `SessionView` / `session.view` 显式字典增加 `warmth` 标量，插件只读。
- WBI 字幕：`BilibiliClient.subtitle(bvid)` 走 `/x/player/wbi/v2` + `wbi.sign`（L2 公开
  签名，**不注入 SESSDATA**），只返回 `lan` / `lan_doc` / `url` 三个字段，不交整个
  player 包；`GET /api/bilibili/subtitle` 是宿主固定路径，插件不能自选 endpoint。
  L1 档位明确拒绝，坏 BV id 不触网。

`tests/test_persona_autonomy_warmth.py`（13 项），另有人格卡 / session.view /
B 站既有用例一并回归。**未做**自主挑音色的管线环节与真实 B 站字幕联调。

### QQ 空间能力面落地：默认完全关闭，读写分开，写要三次确认

原来错在哪：`qq-autonomy-design.md` §2 早就写清了风险与形态——官方机器人开放平台
**没有**空间/说说接口，只有个人号协议端一条路，个人号自动化可能触发平台风控甚至
冻结账号——但结论一直停在「本批未实现，先要操作者确认接受风险」。能力面、两个
示例插件、审批提示都不存在，所以「等你拍板」其实没有可拍的东西。

现在（用户已拍板，风险声明全部保留）：

- `qzone.py` 是 **fail-closed** 网关：`SOAPBOT_QZONE_VIA_PROTOCOL=false` 时任何调用
  直接抛「已禁用」，不会静默降级，也不会去发现端点。只转发四个白名单协议动作
  （读 `get_friend_feeds` / `get_user_feeds`，写 `send_qzone_post`），猜测其它动作
  一律拒绝——有 `qzone_read` 的插件拿不到写路径。
- 端点由操作者点名（`QZONE_API_URL`），Bearer token 用 `SecretStr` 留在宿主，
  插件既拿不到也看不到；审计只记动作与文本长度，不记正文、token、端点 URL；
  非 200 只报状态码，不回显响应体。
- 写要过三道：宿主总开关、`qzone_write` 能力单独批准、插件侧二次命令确认；
  能力面还要求每次调用都带 `confirm=true`，插件写错也跳不过最后一道。
- 两个示例插件：`qzone-diary`（起草→`/qzone-diary-confirm` 才发，草稿存自己的
  加密 storage，发布成功即删）、`qzone-watch`（只读，只申请 `qzone_read`）。
- 面板审批页新增中英风险提示：明确写出「可能触发平台风控甚至冻结账号」。

`tests/test_qzone_surface.py`（15 项）。**未做**与真实 NapCat / Lagrange 部署的联调
（协议端动作名以各实现为准），也未发布到插件仓库；风险自负这条没有变。

### 手机上能点审批了，安装也能直接下载

原来错在哪：上一阶段做出了 `/api/approvals/feed` 与面板批准按钮，但手机端只有四屏
（登录/会话/聊天/备注），没有任何审批入口；`mobile/README.md` 虽然写着本机
`flutter build apk --debug` 实测通过，仓库和 CI 里**都没有可下载的产物**——
`ci.yml` 的 mobile job 只有 `analyze` + `test`，注释还写着「APK 按需本地构建」。
想在实体手机或虚拟机里测，得自己装整套 Flutter + Android SDK。

现在：

- 第五屏 `approvals_screen.dart`：5 秒轮询 `/api/approvals/feed` 游标，按申请号只保留
  最新状态（批准事件替换申请行，不新增第二行），显示金额 / 用途 / 状态，pending 行
  可批准或驳回；`degraded` 降级状态用红字标出。会话页右上角加入口。
- 复用**同一套凭据**：账号登录签发的 Cookie 与面板 token 是同一个 `TokenService`，
  所以 owner 账号能直接调 `/api/budget/{id}/approve|deny`，member 收到 403 并显示
  错误横幅。App 只改状态，不执行支付，批准后仍需人去官方渠道购买。
- CI 的 `mobile` job 现在装 JDK 17、`flutter build apk --debug`，并把
  `app-debug.apk` 上传为 artifact `soapbot-debug-apk`（保留 14 天）——打开 Actions
  run 的 Artifacts 就能下载装到实体手机或模拟器。
- `mobile/README.md` 补「可下载的安装包」与审批页说明；修正三处过期口径
  （`architecture.md` 的「只交付源码，未在真机构建」、`verification-matrix.md` 两处
  「Flutter 无 SDK / 未构建验证」）。

`mobile/test/approval_test.dart`（5 项）覆盖 feed 白名单解析、缺省值降级、degraded
可见、游标保序与未启用时的空 feed。**未做**真机 / 模拟器端到端实测，release 签名与
上架仍不做。

### 审批事件终于能通知到人了：QQ / Webhook / 手机三通道

原来错在哪：`APPROVAL_BUS` 有发布者、**零生产订阅者**（全仓 `subscribe` 只出现在测试里）。
申请提交后除了命令回复里那句被动提醒，没人知道有事要批；额度页要人工打开才看得到。
上一阶段把面板按钮做出来了，但「通知我」这件事依然是空的。

现在（`ApprovalNotifier` 是唯一订阅点，`app.py` lifespan 装配）：

- **QQ**：`SOAPBOT_NOTIFY_SESSION_KEY` 指向操作者指定的会话，宿主走
  `BotRuntime._send_via_adapter` 发送（与插件 send 同一条投递路径，密钥形状由宿主复核）；
  文本截断 500 字，末尾明确「本机器人不执行任何支付」。
- **Webhook**：`SOAPBOT_NOTIFY_WEBHOOK_URL` + `SOAPBOT_NOTIFY_WEBHOOK_SECRET`，
  HMAC-SHA256 签 `timestamp.nonce.body`，带时间戳与 nonce 抗重放；走共享出站客户端
  （禁重定向、TLS 校验、忽略代理环境变量）。密钥用 `SecretStr`，**不进请求头、不进日志、
  不进审计**；审计只记 host 与状态码，连完整 URL 与用途正文都不记。
- **手机**：`GET /api/approvals/feed?after=<cursor>` 返回有界游标 feed，供下一阶段 Flutter
  审批页轮询。刻意复用手机端已有的 2 秒轮询范式，不新造 SSE 会话，也不把审批通知
  伪装成聊天归档消息污染存档。
- **幂等**：以 `(request_id, kind)` 为键的有界 LRU，重放回调、重试 POST、通道被调用两次
  都只投递一次；不同状态（申请/批准）不会互相压制。进程重启可能重通知一次——这是
  明确记录的取舍，漏通知比重复更糟。
- 三条通道互不阻塞：单个通道抛异常或超时只记异常类型，账本已经提交，通知失败绝不
  把成功审批变成 500 然后被重试成二次决策。

`tests/test_approval_notifications.py`（13 项）覆盖三通道、签名可验证、密钥零泄漏、
失败隔离、幂等、游标增量、feed 有界与端点权限。

### 公开网页浏览与消费提案：AI 能自己找，但不能自己买

原来错在哪：`qq-autonomy-design.md` 想让 bot 自主上网挑东西，但仓库里**没有任何
浏览能力**——`Capability` 全表没有 BROWSER，全仓 `playwright|selenium|爬虫` 零命中；
`SafeHttpClient` 有完备的 SSRF / 白名单 / 禁重定向 / 拒 Cookie 防护，却只服务
`ctx.http`，且没有可配置的目的地白名单。于是「自主上网抉择」只能停在纸面，而直接给
插件一个能访问任意 URL 的 HTTP 能力等于把 SSRF 原语交出去。

现在（宿主先有受审能力面，与 `bilibili` / `media_observe` 同模式）：

- 新能力 `browse`，与 `http` **分开审批**；敏感能力，面板审批页有中英提示。
  `SafeHttpClient` 增加 `capability` 参数，浏览请求消耗 `browse` 而不是 `http`，
  其余 SSRF / DNS pinning / 禁重定向 / 头白名单全部复用同一套实现。
- `browse_allow_hosts` **默认空 = 拒绝一切**（fail closed），运维必须点名商店域名；
  遵守 robots.txt（stdlib `RobotFileParser`，带 TTL 缓存；5xx / 网络错误一律拒绝，
  404 视为无限制）；只用可识别的 `User-Agent`，无 Cookie / Authorization，只 GET，
  不跟重定向，不提交表单，不执行 JS；响应体积、正文长度、图片数都有上限。
- `browse.read` 返回**文本白名单快照**（标题 / 描述 / 正文 / ¥ 价格 / 图片引用），
  `browse.propose` 先做限额预检再写账本：没有价格、超单笔上限、超本期剩余额度，
  都直接返回原因，**不创建申请、不预留额度、不发通知**。金额来自页面上的确定性
  提取（`product:price:amount` 或 ¥ 数字），不是模型自由生成的数字——模型编造的
  金额不能成为授权输入。通过后创建 pending 申请并发布 `REQUESTED` 事件，人仍要在
  面板/QQ 里批准，实际购买由人在官方渠道完成。
- 进程内 `PluginContext` 与隔离 `_RemoteCtx` 都走同一个 `SurfaceRouter`，检查点单一。

**明确未做**：无头浏览器 / 模拟手机的 JS 渲染（当前 renderer 是静态 HTTP，页面若靠 JS
才有内容会返回空正文并标记 `static_only`，不假装看到了）；未做真机网页实测；
未做代付链接、电商登录态与支付 API。`tests/test_browse_proposal.py`（21 项）覆盖
白名单、robots 四种情形、上限、能力门控、wire scope 键、审计口径与限额预检。

### 额度审批从「只能敲命令」变成「面板能点、事件能订阅」

原来错在哪：`Permission.APPROVE_PAYMENT`、状态机、原子预留、禁止自批、日/周/月上限都
已经写好，但**没有任何办法从面板决策**：`GET /api/budget` 是只读的，`/budget approve`
只能在 QQ 群里敲；`enable_budget` 默认关闭；单 owner 部署因为「不能自批」根本走不完流程；
申请提交后除了命令回复里的被动提醒，没有任何通知。也就是说：账本是对的，但审批这件事
在实际部署里几乎不会发生。

现在：

- `POST /api/budget/{id}/approve` / `/deny`：要求 `APPROVE_PAYMENT` + 真实凭据
  （回环只读不能 POST 两下就批准），`session_key` 只是定位参数，账本自己复核归属。
  第 10 页增加批准/驳回按钮，不可逆动作先过确认框；策略表显示「第二审批人要求」状态。
- `budget/events.py`：`APPROVAL_BUS` 是唯一订阅点。QQ 命令的申请/批准/驳回/撤回与面板
  的两个端点发布**同一份** `ApprovalEvent`；下一阶段的 QQ / Webhook / 手机三条通道各自
  订阅。通道挂掉、超时、抛异常都只记异常类型——账本已经提交，通知失败绝不能把一个
  成功的审批变成 500 然后被重试成二次决策。事件是显式字段白名单，不携带任何凭据。
- **默认开启**：面板能操作之后，账本不再是「没人能用的管控」，而 ¥500/期、¥100/笔本来
  就是显式整数上限。`SOAPBOT_ENABLE_BUDGET=false` 仍可完全移除命令族；`.env.example`
  与 `docs/configuration.md` 同步。
- **单 owner 没有被悄悄降级**：新增 `budget_require_distinct_approver`（默认 `true`）。
  运维可以显式关掉并接受「审批退化成确认框」，但面板会显示这个状态，每次决策的事件与
  审计都带 `degraded` 标记。没有做「检测到只有一个 owner 就自动放宽」这种自作主张。
- 支付边界未动：表里依然没有 `paid_at` / `payment_token` / `executed`，批准回复依然是
  「本机器人不执行任何支付，请按既有渠道人工完成」。

`tests/test_budget_events.py`（9 项）与 `tests/test_budget_approval_api.py`（10 项）覆盖
权限、凭据、作用域、重放、自批拒绝、降级标记、通道失败不破坏决策，以及命令路径与面板
路径发布同一种事件。

### 消息钩子暴露图片段：做成按需能力面，而不是广播

原来错在哪：`docs/qq-autonomy-design.md` §3 和 §5 都写了「从聊天里顺手收藏」需要宿主
暴露消息里的图片段，宿主内部其实**早就有完整段结构**（OneBot 数组段、QQ 官方附件都产出
`MessageSegment.image(url=...)`），但插件侧从没见到过——`PluginMessageHookStage` 把消息
压成 `text[:500]`，`message_received` payload 只有文本与 session_key。同时，隔离模式
（默认形态）的 worker façade 根本不转发命名事件：`message_hook` 是空实现，loader 只注册
proxied command/tool。也就是说，就算给事件 payload 加一个 `images` 字段，默认形态的插件
依然一个都收不到——「未接线的能力等于不存在」。

现在的形态（与 `bilibili` / `send_media` 同模式：宿主持有受审能力面，插件按需申请）：

- 新能力 `media_observe`，与 `message` **分开审批**：能读「说了什么」不等于能拿走附件。
  列入 `SENSITIVE_CAPABILITIES`，面板审批页新增一条中英提示。
- 新 surface `media.observe`：插件调 `ctx.observe_images()`，不带任何参数。会话键来自宿主
  绑定的 caller（进程内是 contextvar，隔离模式是父进程发出的 invoke 帧），插件写不出
  「读 B 群那张图」这行代码；`arg_violation` 也在 wire 上拒绝 scope-bearing 键。
- `MediaInbox`：纯内存、按会话分桶、TTL 120 秒、**取一次即消费**、单条消息最多 16 个引用。
  只交出 http(s) 引用；本地路径是远端适配器的攻击者输入，内联 base64 是图像内容而不是
  引用，两者都不越过边界。文本消息不清空槽位，因为「先发图、再发 `/meme-save`」是两条
  消息——由 TTL 而不是下一条文本结束窗口。
- 隐私：URL 不进日志、不进审计（只记 `count=N`）、不进 trace、不进 messages 表；
  `_Slot` 用 `repr=False` 防止异常字符串把它带出去。插件被要求立刻存进自己的加密
  storage，且不要传给 `ctx.log`——这是插件侧的责任，宿主不假装能替它兜住。
- 两种形态各有一条真实路径，检查点等价但不在同一处：进程内 `PluginContext.observe_images()`
  用本插件的 `CapabilityGuard` + contextvar 里的 caller；隔离 worker 的
  `_RemoteCtx.observe_images()` 走 `SurfaceRouter._media_observe`，由父进程的 guard 和
  invoke 帧里的 caller 判定。两条都只交出本会话的一次性引用，审计口径一致（只记数量）。

`tests/test_plugin_media_observe.py`（16 项）里最后一条是接线测试：真的从
`IncomingMessage.segments` 跑一遍 `PluginMessageHookStage`，再取到那个 URL。

顺带修正一处文档漂移：本轮之前 `verification-matrix.md` / `architecture.md` /
`delivery-readiness-v2.md` / `progress.json` 都写着 `2145 passed, 12 skipped`，
但本机全量实测基线其实是 **2169** ——前几轮的用例数没同步进这几处。以实测为准，
加上本轮 16 项后是 **2185 passed / 12 skipped**，四处一并改正。

### 插件能发图片了（`send_media` 能力面）+ 修复隔离模式 send 永远被拒的潜在缺陷

原来错在哪（两件，第二件更严重）：

1. 插件只能说文字——表情包/照片即使存下来也发不出去，`ctx.send` 只走
   `scrub_plugin_output` 的文本路径。
2. **隔离模式（默认形态）下插件的 send 从来没有通过过**：子进程 shim 必须携带
   `session_key`（发送目标本身就是请求），而父侧一刀切的 `_FORBIDDEN_ARG_KEYS`
   检查把 `session_key` 拒在 ledger 看到帧之前。两行探针在 master 上复现
   （`forbidden keys hit: {'session_key'}`）；进程内模式不受影响，所以既有测试全绿，
   缺陷一直没暴露。所有依赖 send 的插件（self-nudge 等）在隔离部署上都是哑的。

现在：

- **`arg_violation(surface, args)`**：forbidden-key 检查按 surface 豁免——
  `send.message` / `send_media.request` 合法携带 `session_key`（真边界是宿主的
  observed-session ledger），其余 surface 一律照拒；`scope` 等键在 send 上也照拒。
- **`Capability.SEND_MEDIA`**（敏感 + 限频 30/分）：`ctx.send_media(session_key,
  image_b64, caption)`，与 send 同一套 ledger；解码 + 4 MiB 上限在**两处边界都
  强制**（进程内 context 与隔离模式的 `SurfaceRouter._send_media`——隔离是默认
  形态，只有一个路径有的上限等于没有）；载荷校验先于基础设施检查，报错不泄露
  宿主是否装了媒体发送。审计只记 base64 字符数，图片字节不进任何日志。
- **runtime 新增 `_send_media_via_adapter`**：与 `_send_via_adapter` 同一套会话键
  解析与 `OutgoingMessage` 构造（IMAGE 段 + 可选 caption），适配器按各自能力
  上传或降级。
- 测试 7 项：参数规则（send 豁免/memory 照拒/scope 在 send 上也拒）、路由表接线、
  ledger 拒绝、无能力拒绝、超限拒绝、runtime 段构造。
- 设计文档 `docs/qq-autonomy-design.md`：主动对话（插件，本批随插件仓库发布）、
  QQ 空间读写（**官方 API 无此接口，只能走个人号协议端——默认关、读写分开审批、
  风险自负**）、表情包相册、人格卡 `autonomy`/`warmth` 字段与温度模型。

### B 站 L3 落地：`bilibili` 插件能力（登录态由宿主持有）与示例插件

原来错在哪：能力矩阵写着「L3 登录态未实现」。而沙箱明确拒绝插件发送 `Cookie` 头
（`SafeHttpClient._sanitize_headers`）——任何插件能*持有*的凭据，都是它能*泄露*的凭据。
所以 L3 的正确形态不是「让插件带 Cookie」，而是新增一个受审的宿主能力面。

现在：

- **`Capability.BILIBILI`**（`manifest.py`）：敏感 + 限频（30 次/分钟滑窗）。插件申请它
  之后能做的只有一件事：向**宿主钉死的** `api.bilibili.com` 发 GET（路径由插件选，
  scheme/host 由宿主管——路径必须形如 `/x/...`，带 scheme 或 `//` 直接拒绝）。
- **`BilibiliClient`**（`sandbox.py`）：Cookie 由 `SOAPBOT_BILI_COOKIE`（`SecretStr`，
  默认空）在请求时注入；无 Cookie 抛专门的 `BilibiliUnavailableError`（区别于能力被拒），
  插件作者能分清「没批准」和「没配置」。无重定向、2 MiB 响应上限、15 秒超时、每次请求
  重跑 SSRF 校验；非 200 只报状态码不回显响应体（响应体可能回显凭据）。审计 detail 只含
  路径，Cookie 值不进日志、审计、异常文本中的任何一处。
- **双模可用**：进程内走 `ctx.bilibili`；隔离模式经 `bilibili.request` surface
  （`ALLOWED_SURFACES` + `_SURFACE_TABLE` + 子进程 shim 同步接线），宿主侧
  `SurfaceRouter._bilibili` **重新校验能力**——子进程没有 guard，路由器就是边界。
- **示例插件 `examples/plugins/bili/`**：`/bili-history`（登录态看历史）、
  `/bili-look`（公开元数据摘要）、`/bili-forget`（清空加密 storage 里的去重列表）。
  manifest 按社区仓库要求写明「读了什么、发到哪里、留不留副本」；只声明
  `command`/`bilibili`/`storage` 三项。
- 测试 8 项：未授权拒绝、Cookie 只上钉死主机的线且不进审计、未配置的专属报错、
  路径逃逸全部拒绝、非 200 不回显响应体、子进程 shim 只发 path/params 且不含
  Cookie 字样、路由表接线。插件 IPC（66 项）与安全边界（89/89）门禁保持全绿。
### 可测试安装包落地：Android APK 与 Windows 桌面安装包

原来错在哪：手机端交付的只有 Dart 源码——连 `android/` 平台目录都没有，「装到手机上
试一试」这件事不存在；桌面端有构建链但产物从未在本轮代码上重打。测试版落地需要的是
能直接安装的二进制。

现在：

- **`mobile/android/` 平台骨架进仓库**（`flutter create` 生成，applicationId 定制为
  `dev.soapbot.archive`，应用名「Soapbot 存档」；`local.properties` 由生成的
  `.gitignore` 覆盖不进库）。`flutter build apk --debug` 实测通过（Gradle 536s，
  JDK 17 + Android SDK 36），产物 `app-debug.apk` 直接 `adb install` 或传机安装。
  release 签名仍不做，见 mobile/README「不做什么」。
- **桌面端 `soapbot_0.1.0_x64-setup.exe`（47.5 MiB）在本轮代码上重打**：PyInstaller
  sidecar 重建（包含多端对话端点）→ Tauri NSIS 出包。未签名，SmartScreen 会提示一次，
  已有[桌面端签名](docs/desktop-signing.md)解释。
- **CI 新增 `mobile` job**（非必需检查）：`flutter analyze` + `flutter test`，把手机端
  的 Dart 层质量纳入每次推送；APK 构建仍按需在本地跑，理由写在 job 注释里。
### AI PR 审查升级：确定性影响面分析进评论与提示词

原来错在哪：审查评论只给「verdict + 关注点」，维护者要自己从几百行 diff 里看出
「这次改的是审批授权点」；模型哪次调用失败了，PR 上就只剩一条没有影响面信息的降级意见。

现在：

- **影响面由文件名统计，不经过模型**（`scripts/ai_review.py` 的 `analyse_impact`）：
  23 个子系统前缀归类 + 13 处安全关键面（鉴权、插件审批点、CI、部署配置等）逐文件点名。
  它随「Ask the model」步骤的输入一起生成，**模型调用失败时评论里照样有这一节**——
  这是把「影响面」从模型判断里拆出来的全部原因。
- **PR 评论新增两节**：影响面（含 ⚠ 安全关键面命中）与提交标题列表；末尾措辞从
  「只作参考」改为「只作辅助审批的参考意见，不构成批准」，写明这个 bot 的定位。
- **模型提示词拿到影响面与提交标题**，并附一句「由文件名统计得出，供你交叉核对」——
  声称改文档实际改鉴权的 PR，提示词里现在有直接弹药。
- **workflow** 新增两个纯文本读取（`gh pr diff --name-only`、`gh pr view --json commits`），
  不引入任何安装步骤，`tests/test_ai_review_workflow.py` 的既有门禁（无 pip/npm、
  checkout 钉 base、Enforce 顺序）全部保持通过。
- 测试：`tests/test_ai_review_impact.py` 8 项（前缀归类、未知路径计数、安全命中点名、
  缺 Key 时评论仍带影响面、提示词/评论渲染）。

### 手机端首次真机链路验证与模型接入文档补全

- **mobile/ 过了本机 Flutter 验证**：Flutter 3.50.0 下 `flutter analyze` 0 错误（剩 7 条
  `material.dart` 弃用提示：新 SDK 把 Material 挪进 `package:material_ui`，但 pubspec
  下限仍是 3.22，换 import 之前旧 SDK 装不上，保留并记录）、`flutter test` 12 项全过
  （`mobile/test/client_test.dart` 模型解析与会话标签、`mobile/test/screens_test.dart`
  翻页参数映射、对话发送不携带 session_key、两屏的备注/对话模式切换）。`flutter build apk`
  仍需 Android SDK，是遗留的未验证项。`mobile/README.md` 的「从未构建验证」状态与
  「不实现发送」的只读表述一并改写。
- **docs/model-providers.md 扩充**：新增「原生协议」一节（四种 kind 的端点拼接与鉴权头
  来自 providers 实现）与九家厂商接入表（MiniMax 国内外双域名、腾讯混元、火山方舟/豆包、
  百度千帆、硅基流动、OpenRouter、Groq、Mistral、Moonshot/DashScope 国际版），每个端点
  逐一核实于 2026-11 并附官方来源链接，本地推理服务列出默认端口。

### 多端对话：网页/手机端可以和机器人真正说话了

原来错在哪：存档端点做完后，「多端」只有读的能力——网页和手机上的输入框写的是备注，
永远发不出一条能让机器人回答的消息。原本在 QQ 里完成的「和机器人对话」这件事，在
主力使用的网页端/手机端上不存在；而会话列表还有两个伴随缺陷：首屏加载的是**最早的**
100 条（老会话的中间历史永远看不到），列表拉一次就不再更新（新会话不出现、计数不涨）。

现在：

- **`POST /api/chat/messages`**：构造进程内消息交给 `runtime.dispatch`，与 QQ 消息过
  同一条管线（Guard → 注入检测 → 白名单 → 限频 → 人格 → 模型 → 回复落库）。端点不持有
  适配器引用，回复由 `PersistReplyStage` 在 `send_ok` 后落库，SSE 自动送达客户端。
  session_key 由服务端推导为 `web:private:account-<id>`，请求体里没有身份字段；
  `account-` 前缀保证永不与 owner/admin 名单里的纯数字 QQ 号撞车
  （`normalize_id` 对字母前缀保形）。
- **逐个授权**：账号必须有自己的 membership 行（owner 豁免），无授权与读路径一样 404。
  `WhitelistStage` 的 web 分支锚定在进程内适配器名上，QQ 私聊默认拒绝原样保留，
  `tests/test_chat_talk.py` 有 QQ 侧仍然拒绝的对抗用例。
- **开关 `SOAPBOT_CHAT_TALK_ENABLED`**（默认 false，改后需重启——web 适配器启动时注册），
  关闭时发送端点 404；`/api/chat/surfaces` 新增 `talk` 键。
- **新适配器 `adapters/web.py`**：capabilities 只有 TEXT/REPLY（语音自动降级为文本），
  `send()` 不写库（`PersistReplyStage` 会写，写两次等于每条回复存两行）。
- **历史翻页**：`GET /api/chat/messages` 新增 `latest`（最新一页）与 `before_id`（向前
  翻）两种模式，响应带服务端探测的 `has_older`；三种模式互斥，同时给返回 400，
  `after_id` 原语义不动。网页端与手机端首屏改为最新一页，消息区顶部有「加载更早」，
  空白消息在端点被 400 拒绝（POST 直进 dispatch，绕过了 `_on_event` 的 blank 检查，
  这条是补上的）。
- **会话列表自动刷新**：网页端 30 秒轮询（保留选中态），手机端 30 秒定时器 + 从聊天页
  返回时刷新。
- **第 15 页「账号与邀请」**：账号列表、停用/启用、签邀请码（明文一次性显示 + 复制）、
  授权会话——「与机器人对话」按钮一键预填 `web:private:account-<id>`。此前这些操作
  只有 API，文档自己承认「面板上还没有这一层按钮」。页面编号按「只追加、永不重排」
  规则落到 15（14 已被存档登录页占用），面板页数口径 13 → 15。
- **手机端**：`sendMessage`/`talkEnabled`/翻页参数进 `client.dart`，聊天屏对自己的
  web 会话显示发送框（其余会话仍是备注按钮），列表屏 30 秒刷新。**仍未在真机构建验证**
  ——本机没有 Flutter SDK，这是本轮已知未验证项。
- **测试**：`tests/test_chat_talk.py` 10 项（flag 404、无适配器 503、无授权 404、
  owner/成员对话、halted 429、内容边界、白名单对抗）、`tests/test_chat_api.py` 6 项
  翻页用例、webui `ChatView.spec.ts` 5 项 + `AccountsView.spec.ts` 4 项。

### 接入层只有一个身份：拿到令牌的人能看到一切

原来错在哪：前 41 轮把机器人本体做完了，接入层却始终是「一条 `init_token` 就是 operator」。
`TokenService.issue("operator")` 固定签发同一个角色，`messages` 表有会话列和两个索引，却
**没有任何按会话授权的查询，也没有 `/api/chat/*` 端点**。于是「网页优先、手机只读」这件事
没有落脚点：想给第二个人只看某个群，唯一的办法是把面板令牌给他，而他随即能看到全部。

现在：

- **三张表**：`accounts` / `account_invites` / `chat_memberships`。密码用标准库
  `hashlib.scrypt(n=2**14, r=8, p=1)`，salt 与 hash 分列，比较走 `hmac.compare_digest`；
  邀请码只存 SHA-256，明文仅在创建响应里出现一次，一次性、默认 72 小时过期（`hours` 可调，上限 30 天）。三张表声明为
  ORM 模型随 `create_all` 落库，所以是纯增量加表，`SCHEMA_VERSION` 仍是 5。
- **首个所有者必须带 bootstrap token**：`POST /api/accounts/owner`，账号表非空后固定 409。
  「账号表为空」的检查放在写事务**内部**——原先放在外面，两个并发 bootstrap 会都读到 0。
- **会话隔离在 SQL 里**，不是取完 200 条再在 Python 里筛：后者会让只被授权一个冷清群号的
  成员看到空列表，而页面上写的是「还没有被授权的会话」——一个权限问题被伪装成了没数据。
  越权访问未授权会话返回 404 而不是 403，因为 403 会确认「这个会话存在」。
- **消息按 `after_id` 游标增量拉**，不用 offset：归档只在尾部增长，offset 在并发写入时会
  重复或漏行。SSE 是 1.5 秒轮询同一游标的 async generator。
- **输入只写备注**：落库 `role=note`、`adapter=web`、`delivered=false`，整条路径不 import
  适配器——「不发送」由调用图保证，不由注释和提示语保证。
- **端开关**：`SOAPBOT_CHAT_{WEB,APP,DESKTOP}_ENABLED`，默认只有 web 开；全关时
  `/api/chat/*` 返回 404 而不是 403。
- 网页端第 13 页（登录、会话、消息流、备注，移动优先 / 桌面三栏），`mobile/` 只有 Flutter
  源码骨架与构建说明，**未在真机构建**。

同一轮里被打回的三处，都是「测试先绿、真机上无效」的形状：

1. 三个端开关最初用 `os.getenv` 读，而 `.env` 是 pydantic-settings 消费的、**从不写进
   `os.environ`**——运维改 `.env` 会静默无效，测试因为 `monkeypatch.setenv` 反而通过。改为
   读 `Settings`，默认值用例改成构造真实 `Settings(_env_file=None)`。
2. `check_security_boundaries.py` 的 s11 抓住 `detail=str(exc)`：即使当下消息是手写的，这条
   写法会让下一次「把 `repr(exc)` 塞进去」变成零成本。`AccountError` 增加 `.message`，备注的
   `ValueError` 改成固定文案 + 服务端日志。
3. 部署文档写了不存在的 `soapbot serve`（CLI 只有 start/token/doctor/setup/migrate/version），
   `tests/test_cli_documented_commands.py` 直接把这条漂移报了出来。

### 两条「已经写好」的契约，其实都没生效

原来错在哪：两处都是上一轮自己写的，两处都没测到自己写的那句话。

**一、`review()` 承诺不抛异常，实际会抛。** `_extract_json()` 把 `json.loads` 的结果原样返回，
于是 `"[]"`、`"[1, 2]"`、`"\"safe\""`、`"null"`、`"42"` 这些**能解析但不是对象**的响应一路走到
`normalise()`，在 `payload.get(...)` 上抛 `AttributeError`。用改动前的脚本喂这六种载荷，六次全部
`RAISED AttributeError`；照常调 `main()` 则是 `comment.md` 与 `GITHUB_OUTPUT` 一个都没写出来。
后果不只是「少一条评论」：`ai-review.yml` 的步骤顺序是 `Ask the model` → `Comment` → `Label` →
`Enforce`，第一步崩掉后面全跳过，PR 上只剩一个没有解释的红叉；而 `review` 是必需检查，这个红叉
直接卡住合并。`Enforce` 被刻意放到最后就是为了避免这种情形，结果被一个模型很容易产出的返回形状
绕过去了。`README.md` 当时写着「返回非法 JSON 一律降级」——`[]` 是合法 JSON，这句话不成立。

**二、文档门禁查的是「这个词在全文出现过」。** 从 `CONTRIBUTING.md` 的真实名单里逐个删掉名字：
在上一轮合并的那一版（旧门禁 + 旧文档）上，`frontend`、`desktop`、`review` 三项删掉之后仍然报
`NO PROBLEM`，只有两个 `backend` 和 `package` 被抓到——`package` 被抓到纯粹因为它当时全文只出现
一次。而本轮把 225 行改对、让那句也提到 `package` 之后，同一个旧门禁对 `package` 也失去了反应：
四个删除项全部通过。也就是说上一轮「门禁能挡住漂移」只对「整行删掉」成立，对「清单里少一项」不
成立——而后者才是真实事故的形状；更糟的是它的命中依赖「这个词碰巧只出现一次」这种与意图无关的
巧合，改好一句别处的文案就能把最后一个偶然的拦截点也拆掉。同一文件 225 行还躺着第三份更旧的
名单：「`backend` 两个平台 + `frontend` + `types` + `desktop` 全绿」，既把咨询性的 `types` 当成
合并条件，又漏掉 `package` 与 `review`；它不含数量词，旧规则根本看不到它（返回空列表）。

现在：

- `_extract_json()` 解析成功后校验必须是对象，失败抛 `ReviewError`，消息区分「不是 JSON」与
  「是 JSON 但不是对象」——两者修法不同，前者是加 token 预算，后者是让 prompt 说清返回对象。
  `normalise()` 同样加了守卫，供直接调用方使用。任意形状的响应现在都是 `needs_review`，
  `comment.md` 与 `GITHUB_OUTPUT` 照常写出。
- `concerns` 不再是「可迭代就当列表」：`for item in "no concerns found"` 会迭代字符，产出 17 条
  单字符关注点，渲染成一串噪音。抽出的 `_normalise_concerns()` 把字符串当成一条保留（那是人写的
  抱怨，只是不合 schema），dict 当一条，上限仍是 20。
- `main()` 在 `review()` 外面留了最后一道网：意外异常也降级成 `needs_review`，并把异常类型写进
  评论。理由和上面一样——这个步骤红掉等于 PR 上只有一个不说话的红叉；写下 `KeyError` 至少让日志
  指得回真正的 bug。
- 门禁改成三条段落级规则：①必须有某一段同时写下数量和完整名单，失败时点名缺哪一项；②每处写下的
  数量都必须是 6；③含「全绿」的句子若点名了 job，就必须正好是那五个 job 名，多一个 `types` 也报。
  `CONTRIBUTING.md` 225 行据此改写：点名六个必需检查，`types` 单独一句「红了也要修，但咨询性、
  不拦合并」。
- 用例：`tests/test_ai_review.py` 19 → 24 项，`tests/test_required_checks_doc.py` 6 → 9 项。
  两处都补的是「改坏必须红」的用例——`git show HEAD:` 喂同样输入可复现旧行为（6 种载荷全抛、
  6 个删除项漏 4 项、225 行原句返回 `[]`），这是新用例有效的证据，而不再是「跑过了」。

实现被两件事打回，值得记下来：门禁的句子切分原本把换行也当边界，而 225 行恰好在 `desktop` 后
换行，含「全绿」的半句只剩三个名字，误报「漏了 `package`、`review`」；改成先把续行拼回逻辑行
再按句号切。token 原本直接与 job 短名比较，写完整 context 的文档（`` `backend (ubuntu-latest, 3.12)` ``）
匹配不上；改成取 `(` 之前的部分归一。两处都是「规则写对了但切分错了」，靠真实文档才暴露。

### 必需检查的数量只剩一种说法

原来错在哪：`review` 在 2026-11-10 成为第六个必需检查，同一个事实随即在仓库里分裂成三种
写法——`CONTRIBUTING.md` 开头写「6 个必需状态检查」，同一文件里 `--admin` 那段又写「5 个
检查全绿」；`.github/copilot-instructions.md` 告诉 AI 助手「等 5 个必需检查」；`CHANGELOG`
把它描述成「五道必需检查」。第三处是历史条目，写的是当时的事实；前两处描述的是今天，却是
错的，而它们恰好是人和 AI 助手判断「能不能合」的依据。

现有门禁一条都看不见：`scripts/check_test_gaps.py` 只扫 `README.md` 与 `docs/**` 里的
`N passed`，`tests/test_doc_test_counts.py` 扫同一批文件里的按文件计数；`CHANGELOG.md` 与
`.github/*.md` 从来不在扫描范围内——这是既有盲区，不是这一轮新引入的。

现在：三处改成六个并把 `review` 点名（AI 助手的规则里多一句「它变红同样合不了」），
`CHANGELOG` 的历史段改为不写具体数字、只写「名单读自 `branches/master/protection`，`review`
在后续一轮加入」。新增 `tests/test_required_checks_doc.py`（6 项，下一轮补到 9 项——那一轮发现
这 6 项只查「词是否出现在全文」，见本节上方）：`REQUIRED_CHECKS` 六项
是 `gh api` 只读回读的快照，`required_check_doc_problems()` 检查两份当前态文档是否逐项点到、
数量是否写成 6；反向用例用构造文本证明删掉 `review`、写回「5 个」、或干脆一行都不写数量都会
失败。`CHANGELOG.md` 有意排除在外——把「当时只有五道」改写成不含数字的措辞以迎合门禁，方向
是反的，和上一轮给轮次记录加豁免是同一个理由；那条用例同时断言规则确实会拒绝这种历史写法，
否则「被排除」与「本来就通不过」无法区分。

顺带把 `CONTRIBUTING.md` 里「`PUT` 会先读一次，读不到就 404」降级为「实测返回 404，原因
未查明」：前半句是推测，不是证据。可复验的部分（`PATCH` 可用、整体替换、写完回读）保留。

### AI 审查不再「每次都在、每次都说不出话」

原来错在哪：`review` job 一直是绿的，评论却固定是同一段降级文案。PR #24 与 #25 的评论
逐字相同：`finish_reason=length, reasoning_tokens=3000, completion_tokens=3000`。
`deepseek-flash` 是 reasoning 模型，`completion_tokens` 包含隐藏推理，脚本里硬编码的
`max_tokens: 3000` 全被推理吃光，`content` 为空；`review()` 按 fail-closed 降级成
`needs_review`。于是「job 通过」和「审查发生」变成了两件事，而 PR 页面只看得出前者。

现在：单次预算提到 8000；只在「`finish_reason=length` 且内容为空」时用 16000 重试一次。
这是唯一值得重试的失败——HTTP 401/403/429、超时、响应体不是 JSON、JSON 字段非法，重试
只会重复同一个错误并多花一分钟。两次都空时评论写明「已用 8000 与 16000 两次预算，均被
推理耗尽」，附 `reasoning_tokens`，下次是改模型还是继续加预算有数据可依。判断不了一律
仍是 `needs_review`，重试不会让结论变成 `safe`。

### `AI_REVIEW_MODE` 从死变量变成真开关

原来错在哪：仓库变量 `AI_REVIEW_MODE=observe` 存在，但 `ai-review.yml` 从未引用它。
一个没人读的开关比没有开关更糟——它让人以为改了就生效。

现在：`observe`（默认）只评论、只打标签，job 恒通过；`block` 在 verdict 非 `safe` 或
评论是降级结论时让 job 失败。判定步骤 `Enforce review mode` 是**最后一个** step：放在
评论之前的话，block 模式下 job 一失败就没有评论，PR 上只剩一个没有原因的红叉。

### 工作流与 PR 模板变成可校验项

原来错在哪：2026-11-09 有一次 `startup_failure`（0 秒、无日志），`make check` 完全看不
见；模板改了也可能不生效，因为 `CONTRIBUTING.md` 教的是 `gh pr create --fill`，而
`--fill` 用 commit message 填 body、直接覆盖模板。

现在：`tests/test_ai_review_workflow.py`（16 项）。前 7 项解析 YAML，钉住 checkout 必须是
`pull_request.base.sha`、持有密钥的 job 里不得出现 `pip install`/`npm install`/`npm ci`、
`AI_REVIEW_MODE` 被读取且 observe 是默认、`Enforce` 排在 Comment/Label 之后且为最后一步、
未知模式值（`MODE=Block` 这类拼写）也 fail-closed 而不是静默落进 observe。后 9 项不是
「再读一遍 YAML」——读 YAML 只能证明文本里有 `block` 这个词，证明不了退出码对。它们用
真实 bash 执行 `Enforce` 的 `run:` 块本身，参数化断言 8 种 mode/verdict/degraded 组合的
退出码（observe 恒 0；block 下 needs_review/malicious/degraded 为 1；`Block` 与空串这类
拼写错误也为 1），外加一条断言失败时必然先打印 `mode=/verdict=/degraded=` 与 `::error::`。
`tests/test_pr_template.py`（12 项）钉住模板九个小节（改了什么/为什么/影响面/验证/数字
基线/AI 审查/安全影响/回滚/检查），逐节删除都会失败，并禁止 `--fill` 回归。

一个曾经成立、现在已被现实推翻的限制：这一轮的 PR 自己的 `ai-review` 跑的是 master 上的
旧脚本（工作流按设计 checkout `base.sha`，这正是安全模型要的），所以当时把端到端证据记为
**未验证**。合并后的第一个 PR（#27）推翻了这个结论：它的评论第一次给出真实结论
（`未发现问题`、risk `low`），8000 那一档就够，没有用到 16000 重试。`checkout base.sha`
这条约束本身仍然成立——改脚本的 PR 仍然跑旧脚本，只有合并后的下一个 PR 才是验收对象。

### 数字门禁不再把轮次记录钉到今天

原来错在哪：`check_test_gaps.py` 的 `stale_totals()` 逐行扫 `N passed`，而
`verification-matrix.md`（被列为 `LIVE_DOCUMENTS`，因为它的头部数字确实是当前态）里同时
记着每轮的增量，例如「全量 1884 → 1892 passed / 12 skipped」。看板一前进到 1902，这条
上一轮的记录就变红；上一轮只能把句子改写成不含 `passed` 的措辞来绕过门禁——为了让
检查通过而去改历史记录，方向是反的。

现在：`ROUND_CHANGE` 只豁免「整数 → 整数 + `passed` / `项通过`」这一种明确的轮次变化
写法。裸的当前态声明（`1902 passed, 12 skipped`）没有箭头、基准数据
（`39.7ms → 19.6ms`）两边带单位，都继续被检查；`round_report_lines()` 把每条被豁免的
行以 `文件:行号` 打印出来，避免规则静默失配。`stale_totals(root)` 支持注入目录，错误
路径也不再用 `Path.relative_to`（在 `tmp_path` 下会抛异常而不是报问题）。上一轮被迫改掉
的 ph35 轮次行已恢复成自然写法，成为真实覆盖点。

新增 `tests/test_gate_round_reports.py`（6 项）：历史行豁免生效、当前态总数与跳过数失真
仍报、裸旧数字与基准箭头不被豁免、真实文档里至少匹配到一条轮次记录。另在真实文件上做
了端到端改错复验：把 `architecture.md` 的 `1902 项通过` 临时改成 `1901`，`--strict`
返回 1 并精确指出 `docs/architecture.md:234`，随后字节级还原、diff 为空。

### 记忆与 RAG 向量检索批量化

原来错在哪：两个召回通道（`MemoryStore._vector_search` 与 `KnowledgeBase.search`）都把
所有带向量的行用 `select(MemoryRow)` / `select(KnowledgeRow)` 取成完整 ORM 对象——包括
永远不会被读到的 `content` / `keywords` 文本——再在 Python 循环里逐行做
`np.frombuffer` + `np.linalg.norm` + `np.dot`。3000 行就是 3000 次 Python→C 往返，每次
recall 都要付一遍。更麻烦的是两处防护不一致：`MemoryStore` 查 NaN/inf，
`KnowledgeBase` 完全没查，一个坏向量就能让 RRF 排名变成任意顺序；而 `MemoryStore` 把
「余弦 ≤ 0 的正常不相关行」也算进 `dropped` 打 warning，随机语料一次 recall 能刷上千
行日志，真正的坏向量反而被淹没。

现在：`memory/vectors.py` 把打分收敛成一次矩阵乘，两个调用点改成两阶段查询——先只取
`(id, blob, dim)`，算出 top-N 后再按 id 回查展示列；NaN/inf/零范数/维度/blob 长度校验
与稳定排序集中在一处，`KnowledgeBase` 因此自动获得此前缺失的防护。`dropped` 只计坏行，
不相关的正常行单独计 `non_positive`，不再触发告警。`db.py` 里「brute-force 余弦胜过
向量库」的设计决策没有变：仍是全量扫描、同样的余弦、同样的 RRF 排名。

实测（临时基准，3000 行 / 128 维 / limit=24 / 5 轮，同库同数据与旧写法对比）：
median 39.7ms → 19.6ms（约 2x），top-24 结果逐项一致，日志噪音归零。新增
`tests/test_vector_ranking.py`（10 项）：以旧循环为 oracle 逐项比对分数与顺序、并列保持
扫描顺序、坏行与不相关行分开计数、非有限 query、limit 边界、两处接线静态断言，以及
两阶段查询确实回取了完整字段。

一个未归因、但不隐藏的观察：本机本轮三次全量耗时稳定在 680–702s，明显高于上一轮的
236s。加 `--durations=15` 复核后，最慢 15 项合计约 110s 且均不在检索路径，新增 10 项
单独 0.51s，去掉顶层 numpy 导入后总耗时也没有变化；判断是宿主层面的整体变慢，未声称
由本次改动造成，也没有据此放宽任何断言或超时。

### 类型检查门禁的当前态描述对齐

原来错在哪：`check_mypy_baseline.py` 早已接进 `make check` 和 CI 的 `backend` /
`types` 两个 job，是**阻断**门禁，基线也因本地与 CI 差一个错误而从 79 抬到 80；但
`deployment.md` 仍写着「`types` job 里只报告不阻断、降到 0 再改阻断」，`CONTRIBUTING.md`
写「基线 79、尚未作为阻断项」，`operations.md` 的门禁清单整条漏掉它，
`verification-matrix.md` 的复现命令还是原始 mypy 加旧基线。最矛盾的是 `ci.yml`：同一个
`backend` job 上面是阻断的 `Type check (ratchet)`，下面的注释却写着
「mypy is deliberately *not* a gate here ... 79 errors across 31 files」。

现在：这些当前态描述统一改为「棘轮只比较总数、基线取本地与 CI 中较大的 80、两个 job
都阻断」；Makefile 的 help 区分「查看用的 typecheck」与「进 check 的 mypy-baseline」，
注释不再写死错误数；CI 里那段自相矛盾的注释删掉。带轮次语境的历史记录（本文件旧条目、
`progress.json` 的 ph32 note、门禁脚本的 Why-this-exists 段）按既有边界保持原样。

新增 `tests/test_type_gate_docs.py`：把基线值、`make check` 与 CI 两个 job 的接线、以及
四份当前态文档里的过时短语一起变成可失败门禁，逐条反向复验。

### 首次登录令牌指引：从「给个路径」改成「能照着做」

原来错在哪：文档只写 `data/init_token.txt` 或写死 `C:\soapbot\data\init_token.txt`，
`deployment.md` 甚至写着「打印取令牌的命令」却根本没给命令；两个服务化脚本收尾只留
一句英文 `open it on this machine; it is not printed here`，云服务器用户分不清指的是
哪台机器；`start-panel.bat` 反而把令牌值 `type` 出来，这条差异只用「有意保留」一笔
带过。最要紧的是全库没有写「兑换后文件即删除、重启不会重新发放」，于是重启后找不到
文件被当成故障，反复重启也不会变出新令牌。

现在：`docs/deploy-quickstart.md` 的「第一次登录」以 `GET /api/auth/status` 开头，用
服务自己算出的 `bootstrap_path` 与 `bootstrap_state` 区分 available / redeemed，再给
`Get-Content`、一次性兑换、以及 `token --reset` 加 `schtasks` 重启的完整可复制命令；
README / guide / deployment / operations 都指向它，operations 另加「重启后找不到
`init_token.txt`」排障条目。两个服务化脚本改成明确写出 `ON THIS SERVER` 并给出可直接
粘贴的 `notepad "<完整路径>"`，同时说明已兑换后重启不会重发；脚本保持纯 ASCII，避免
Windows PowerShell 5.1 按 ANSI 解析造成中文乱码。`start-panel.bat` 保留打印值，但在
同一屏解释两条路径为何不同、文件不在时意味着什么。

新增 `tests/test_bootstrap_token_docs.py`：把「指引可操作」变成可失败门禁，逐条删掉
状态自查、读取命令、恢复命令、脚本提示或文档指针都会红。

### 安全边界与错误日志治理

运营者提出 18 项风险。逐条核实后：6 项已经解决或不适用（`shell=True`、pickle /
`yaml.load`、`v-html` 渲染用户内容、CORS 通配带凭证、Jinja 渲染用户内容、上传体积
校验），1 项属实（token 存 `localStorage`），其余部分属实。口径是**全量加固**：
18 项每项都要有一条能验证的防线，已解决项用负向静态断言锁住不许退回去，不重复
写第二套实现。

原来错在哪：

- 认证：浏览器把签名 token 存在 `localStorage`，页面里任何脚本都能读走并长期复用；
  `api/auth.py` 对回环请求无条件给 `owner`，77 个管理路由只有「要不要认证」没有
  「谁可以改」。现在会话是 `HttpOnly` + `SameSite` Cookie，写操作另需 CSRF 双提交与
  同源 `Origin`；回环只读降为 `MEMBER`，写操作要凭据；配置写入要求 `ADMIN`，
  撤销全部仍要求 `OWNER`。Bearer 保留给脚本和 CLI。
- 错误：二十多处 `HTTPException(..., detail=str(exc))` 把配置解析错误、插件异常文本
  甚至路径回显到浏览器。现在统一异常分层与状态码映射，响应只给稳定短句加白名单
  类别标签（如 `traversal`、`YAML`、未设置的环境变量名），完整异常进服务端日志。
- 日志：`logging_setup.py` 手工拼 JSON 字符串，用户内容里的换行能伪造出第二行日志；
  日志环存原文；Provider 响应正文经 `last_error` 被管理 API 返回并写进日志环。
  现在用 `json.dumps` 序列化、出口剥离控制字符、`ContextVar` 贯穿 `trace_id` 等定位
  字段、慢调用按阈值告警；Provider 异常只带 `kind + HTTP status`。
- 输入：正则跑在用户可控文本上，执行前没有统一长度上限；上传只查 zip 结构不查
  文件类型；`doc_id` 有四处入口，两处漏了校验。现在分别补上 `bounded_scan()`、
  zip 魔数与后缀白名单、`_require_doc_id()`。标准库 `re` 没有超时参数，长度上限是
  不加依赖时唯一可验证的替代，文档里如实写明它不是硬超时。
- 异常吞没：三处 `except ...: pass` 有注释说明但没有任何动作，改成显式降级日志。

新增 `scripts/check_security_boundaries.py`（84 条不变量，接进 CI 双矩阵与
`make check`）、`docs/security-boundaries.md`（18 项逐条证据）、
`tests/test_security_boundaries.py`、`tests/test_auth_cookie.py`、
`tests/test_logging_hardening.py`、`tests/test_error_mapping.py`。
`deploy/backup.sh` 把命令字符串拼接改成显式函数与引号路径。

参考了 SnowLuma / NapCatQQ / MaiBot 等 23 个仓库，按 5 类生态抽样。学的是把边界
写在哪、把校验放在哪、把恢复写成显式动作，没有搬任何功能、源码或依赖。逐条
「改什么、为什么、不改什么」在 `docs/reference-ecosystem.md`。

README 按四块重写（定位 / 启动 / 边界 / 门禁），安装细节迁到 `docs/guide.md`，
排障与部署迁到 `docs/operations.md`。删掉宣传语，只写事实、命令和取舍。
`tests/test_readme_claims.py` 的环境变量表仍在 `docs/configuration.md`，断言保持。

### 插件进程与 IPC 边界加固

对运营者提出的十项风险做了**逐项核实**，其中六项在当前代码中已经解决，本轮只修真实缺口，
并把「不得回退」固化成 CI 门禁。核实结论：

| 提出的风险 | 核实结果 |
|---|---|
| IPC 用 pickle | 不符：长度前缀 JSON，全仓无 pickle 原语 |
| 能力授权在插件进程内自查 | 不符：父进程 `_handle_callback` + `surfaces.py` + `sandbox.py` 单一授权点 |
| 崩溃无重启/熔断 | 不符：指数退避、窗口内重启预算、熔断且需显式重置 |
| 子进程继承全部环境变量 | 不符：`sanitize_env()` 白名单，仅转发 `SOAPBOT_PLUGIN_*` 前缀 |
| 插件加载路径未校验 | 基本不符：symlink、`resolve().parents`、zip slip、名称正则、manifest digest 均已有 |
| correlation id + 超时 / stdout drain / 进程数 / 僵尸回收 / 消息大小上限 | **部分属实**，见下 |

真实缺口与修复：

- **请求串台**：父端 `invoke()` 收到 `result` 时完全不校验 `id`（子端其实一直回带了 id），
  `call` 帧也不绑定当前请求。现在每次调用生成随机 `rid`，`result.id` 与 `call.rid`
  都要强校验，不匹配即丢弃并计数；未绑定的回调在查 capability 之前就被拒绝。
  `invoke()` 全程持锁，杜绝两个调用交错读同一条管道。
- **帧预算漂移**：父端入站 4 MiB、子端入站硬编码 8 MiB、出站不限。现在
  `isolation.MAX_FRAME_BYTES` 是唯一常量源，以字面量注入两个 `-I` 子脚本；
  父/子入站与出站、一次性 runner 的请求与回包统一受限，错误带「上限 + 实际字节」。
- **stdout 只在调用期间读**：空闲期插件写满管道会把自己阻塞。现在一个常驻 reader
  独占 stdout，帧进入 `asyncio.Queue(maxsize=4)`；队列 0.5 秒无人消费即判定帧洪水并
  杀进程树。
- **进程数无上限**：新增 `SOAPBOT_MAX_PLUGIN_WORKERS`（默认 16，`1..64`，`0` 非法），
  注册与启动双重 fail-closed；容器的 `pids_limit` 退居最后一道兜底。
- **回收不统一**：新增 `proc.wait()` 退出看护（带进程代际守卫），`stop()` 取消并 await
  三个任务，`loader.unload_all()` 与 `app._shutdown()` 都调用幂等 `stop_all()`。
- **子端纵深校验**：两个子脚本都对 boot/请求里的 `plugin_dir` 做 `realpath`、目录存在、
  `main.py` 普通文件且未逃逸根目录、`attr` 合法标识符的复核。
- **一次性 runner 的静默失效**：`_CHILD_BOOTSTRAP._apply_limits()` 引用只存在于宿主模块的
  `DEFAULT_PLUGIN_MEMORY_BYTES`，`NameError` 被裸 `except: pass` 吞掉，资源限制从未生效。
  现在默认值是字面量，其它异常打印到 stderr。

并发交叉审查后追加修复：帧洪水/协议错误时 reader **同步**杀进程并关闭队列（此前
`await self._abort()` → `proc.wait()` 会与 stdout EOF 形成循环依赖，持锁的 `invoke()` 永久挂死）；
所有 `proc.wait()` 加上界；`stop()` 在 `finally` 中无条件回收三个任务；
`PluginSupervisor` 增加生命周期锁使容量检查与建进程原子化，并新增 `unregister()` 在卸载时
释放容量；同一 worker 重入 `start()` 时杀掉旧进程并重置全部代际状态；
一次性 runner 不再用无上限的 `communicate()`，改为按帧有界读取；
启动期回调立即拒绝而不是让 shutdown 等满超时。这些不变量也写进了 `check_plugin_ipc.py`。

新增运维与门禁：`scripts/check_plugin_ipc.py`（离线静态审计，挂进 CI 与 `make check`）、
`scripts/plugin_worker_guard.py`（**只读**巡检，绝不重启）、
`deploy/plugin-worker-guard.{service,timer}`（每 5 分钟）、
`tests/test_plugin_ipc_hardening.py`。

参考 [surfcore](https://github.com/Mieksido/surfcore)、
[qq-dsh-bridge](https://github.com/NoMindSama/qq-dsh-bridge)、
[dsh-bili-humanism](https://github.com/InariNGT-Ofiicial/dsh-bili-humanism) 的治理机制
已落地；人格分层、四层记忆与 selfNote、闲置边界压缩等业务设计**评估后不移植**，
理由见 [DSH 生态参考评估](docs/reference-dsh-ecosystem.md)。

### 新增

- **Windows 双击启动器**：`start-panel.bat`（本地起面板并自动开浏览器）、`stop-panel.bat`、
  `open-remote-panel.bat`（SSH 隧道看服务器上那个实例）。此前"看界面"只能靠手敲
  `python -m soapbot.cli start` 再自己输网址，README 里也只有一行字——面板一直存在，但没有
  任何可点的入口。
- **真实 MCP 服务端接上了**（`tests/test_mcp_live.py`，opt-in：`SOAPBOT_LIVE_MCP=1`）。
  之前所有 MCP 结论都来自一个照着客户端写的假服务端，它能证明的只有「客户端和自己谈得拢」。
  现在接的是第三方的 `@modelcontextprotocol/server-filesystem`：14 个工具、`tools/call`
  真的读回了文件内容。默认不进 CI——它要联网装 npm 包，一个会因为 npm 打嗝变红的门禁，
  最后会被人标成 flaky，而 flaky 的门禁比窄门禁更糟。
- **MCP 首次配置不再需要重启**。这条是实测查出来的：我按「面板新增 → 热加载」的路径走，
  表格一直显示「状态未知（运行时未启动）」——而运行时明明在跑。原因是
  `core/builder.py` 只在 `mcp.yaml` 已有服务器时才创建 `McpManager`，于是**最该热加载的
  那一次**（从零到一台）恰好没有任何东西可加载，面板只能回一句「重启后生效」。现在管理器
  总是创建，空列表只是它的初始状态。
- **MCP 握手改为版本协商**。客户端原来硬编码 `2024-11-05` 并把 `initialize` 的结果丢掉。
  现在发自己最新的版本、采纳服务端回的版本（实测对方回 `2025-06-18`），遇到没见过的版本
  按 INFO/WARN 记录而不是拒绝——三个调用在已发布的各版本里报文没变过，为一个不认识的
  字符串把一台能用的服务器停掉是更差的交易。
- **握手失败与启动失败不再长得一样**。以前子进程 `stderr=DEVNULL`，npx 下载 404 和协议谈崩
  都只表现为「connection closed」。现在保留 stderr 尾部 2 KB，握手期崩溃会写成
  `exited during the handshake (exit code 9); stderr: npm error 404 ...`。
- **三家 Provider 的报文映射补测**（`tests/test_providers_mapping.py`）。Anthropic、Gemini、
  Ollama 此前**没有任何测试提到过**——它们是三个把我们的结构翻译成别人 schema 的地方，
  而写错字段名不会抛异常，只会安静地少一半信息。
- **两个新的静态门禁**：`scripts/check_test_gaps.py`（孤儿模块 + 文档数字与看板一致性，
  带 `scripts/test_gaps_baseline.txt` 基线）与 `scripts/check_a11y.py`（按钮名称、点击目标
  可聚焦、img alt、对话框语义）。都挂进 `make check` 与 CI 既有作业，不新增作业。
- **09 页流式观察**。`trace.chunks` 与 `trace.stream` 从第一天就写进了环形缓冲，前端
  一个字段都没读——「有数据」和「看得见」之间隔着一次渲染。现在详情区有三段耗时阶梯
  （首 token / 首句送达 / 整条回复，共用同一刻度，所以「首句比整条短多少」是几何可见的）、
  实际发出的分句序列、中断与额度截断角标。
  **顺手修掉一个谎**：`MessageTrace` 在 TypeScript 里声明了 `extras`，而 `to_dict` 从不
  序列化它。第一版用 `extras.send_ok` 判断「回发环节是否跑过」，页面永远渲染不出区块——
  改成读 `stages`，并把这个字段从类型里删掉。
- **面板内编辑 MCP 服务器**（`/api/config/mcp` 的 read / diff / apply）。
  以前只能看状态和重连，增删要 SSH 上去改 `config/mcp.yaml`。三个决定值得记：
  ① **OWNER 权限**，高于 providers 的 ADMIN——新增一台服务器等于开放一条子进程执行通道，
  并把它的工具交给模型调用，与改一个 base_url 不是一个量级；
  ② **`env` 只写不读**，接口只回键名，提交时不带 `env` 就保留磁盘原值——`providers.yaml`
  里那个「把 `***` 存回真实密钥」的坑在这里由结构排除，而不是靠记得检查掩码；
  ③ **diff 用指纹而不是 `***`**：扁平占位符会让「换了 token」渲染成「没有改动」，操作者
  会对着一张空 diff 点确认。改用带进程内盐的 `redacted:xxxxxxxx`，变了看得见，值读不出来。
  写入后热重载（`McpManager.reload` 原地更新，不换对象——工具注册表持有的是这个实例），
  并逐个 server 报告「N 个工具」或「启动失败·原因」。
- **上游连通性自检**（`provider.upstream`）与 `doctor --probe`。
  `providers: []` 以前不产生任何 finding，`doctor` 对着一个答不出任何消息的机器人打印
  PASS。现在空配置是 `[warn]`（MEDIUM，不拉红门禁——只跑面板的机器是合法部署），
  坏 YAML 是 `[fail]`，指向本机或明文 http 会单独点名。
  `--probe` 是可选网络探测，**不发 API Key**：打 `/models`，把 401/403 当作「服务器回答了」。
- **验证矩阵** `docs/verification-matrix.md`：把「有实现 / 有测试 / 真能用」分开写，
  结论只有「自动+实测 / 仅自动 / 未验证」三种，并写明容器、真实 STT、真实云端 Provider
  各自的缺口。
- **看板契约测试** `tests/test_progress_board.py`。`docs/progress/README.md` 里写了四条
  规则（状态枚举、blocked 必须写原因、current 指向真实任务、updated_at 决定可信度），
  此前没有一条被执行——看板因此停在 10-28、`current` 还写着「首次提交待确认 git 身份」。
  规则文件只有人读就会腐烂，这 8 条断言是让它不腐烂的部分。

- 为了上面这条，两处既有代码被拆开而不是复制：
  `core/config_write.build_patch` 原来把 providers 的合并与脱敏规则写死，现在注入
  `apply_fn` / `validate_fn` / `diff_render` / `filename`，默认值保持 providers 行为，既有
  调用点零改动；`mcp/config.py` 把校验从 `load_config` 拆成 `parse_servers`，让面板校验
  候选文档与启动解析是**同一份代码**——两份解析器迟早会分叉，分叉的样子就是「面板保存
  成功、进程起不来」。
- **配置写入 API**（`POST /api/config/providers/{diff,apply}` + `GET /api/config/providers`）。
  三步而非一个 PUT：读取（密钥脱敏 + `base_hash`）→ diff（用**与启动同一套解析器**
  校验候选文档，**不写盘**）→ apply（校验 `base_hash` 未变、`approved_hash` 与确认内容
  一致，再原子写）。
  **这推翻了 `docs/architecture.md §6` 原来的「配置类写入一律不做 API」**：那条规则的
  前提是「文件在版本管理里、改动可被评审」，而单机部署里文件从未进过 git，评审从未
  发生。diff 才是第一次真正生效的评审面。原条目已标注修订并补 §6.1 说明理由。
  三条硬约束各有测试：字段级合并（不整文件覆盖）、候选必须通过启动解析器、不热重载。
- **09 流水线追踪页** + **10 运行指标页**（追加编号，不重排 01–08）。
  追踪数据此前不存在：`ctx.timings` 每条消息算完即丢。新增 `core/trace.py`
  有界环形缓冲（500 条，重启即失，不采样），通过已有的
  `Pipeline.observe` 与 `message.processed` 订阅接入，未改 `Pipeline` 内部。
  指标序列 5 秒一点、保留 720 点（约 1 小时）。
- **手写 SVG 图表组件** `components/charts/{LineChart,BarChart,Sparkline}.vue`。
  不引图表库：依赖清单是审计面（刚移除 4 个未用包），且 canvas 对读屏是不透明位图，
  做 WCAG AA 需再叠一层 DOM。每个图都带可展开的数据表。
- **`components/StageGraph.vue`**：纵向链路 + 逐环节耗时条 + 「在此中止」标记，
  以及**换序沙箱**——可拖拽试排，页面指出破坏了哪条具体约束，但不写回任何地方。
- **07 页 Provider 可视化编辑**：表格内增改、只发被编辑的行、改动行高亮、
  diff 预览 → 二次确认 → 写入，「需重启生效」常驻横幅。
- **`components/DiffEditor.vue`**：行级 diff，带新旧行号与 `+`/`−` 标记，
  不只靠颜色区分增删。
- **`soapbot migrate` 子命令**（`cli_migrate.py`，`--status` / `--dry-run` / `--target`）。
  `UPDATING.md` 从 v0.x 起就让人「升级后跑一次数据库迁移」，而仓库里**没有这个命令**——
  文档承诺了一个不存在的入口，读者只能去翻 `memory/migrations.py` 猜怎么调。
  现在 `--status` 是**只读**的：用 `mode=ro` URI 连库，不触发 `current_version()` 里那句
  `CREATE TABLE`，所以对着一个生产库执行它不会留下任何痕迹。
  探测分五态而不是三态，因为把不同故障压成同一个词会给出错误建议：
  `missing`（文件不存在）、`empty`（0 字节，典型是挂载了空卷）、`unreadable`（损坏或权限不足）、
  `legacy`（有表无版本记录）、`versioned`。前两态提示「先启动一次服务让它建表」，
  `unreadable` 提示「从备份恢复」——把损坏文件说成空库，会让人去启动服务，然后覆盖掉唯一
  的备份线索。
  `legacy` 库先盖章 v1 再顺序跑 v2–v5，与首步同事务：失败回滚后版本表不存在，所以失败
  提示会**重新探测**再措辞，而不是照着进函数时的快照宣称「仍停在 version 1」。
- **`core/proc_env.py`**：插件与 MCP 服务共用的子进程环境白名单。此前 MCP 侧传的是
  `{**os.environ, **server.env}`，于是 `npx -y <某个包>` 起的服务能直接读到
  `SOAPBOT_MASTER_KEY` 与全部 provider 密钥——而 `SECURITY.md` 把 MCP 定级为「不可信」。
  一个被实现否定的定级比没有定级更糟，因为它请读者去依赖它。两侧共用一个模块而不是各写
  一份：两份白名单迟早分叉，而往这个方向分叉是 fail-open。
- **`tests/test_cli_documented_commands.py`**：扫描文档里出现的 `soapbot <子命令>`，断言
  解析器真的接受它。`migrate` 缺失这件事能活到被发现，是因为没有任何东西把「文档说了」
  和「代码有」连起来。同类的下一个缺陷现在会在 CI 里红。

### 修复

- **`SOAPBOT_ENV_FILE` 指定的 `.env` 从来没被读进 `os.environ`**。`load_dotenv_if_present`
  按 `__file__` 推到源码树根的 `.env`（容器里是只读的 `/app/.env`），而且**这个函数一次都没被
  调用过**。自定义键（如 `DEEPSEEK_API_KEY`）只存在于数据卷的 `/data/.env`，而 `api_key: env:NAME`
  是从 `os.environ` 解析的——密钥放在文档说的那个位置，启动会直接报 `references unset
  environment variable`，看起来像密钥文件坏了。现在按 `SOAPBOT_ENV_FILE` 解析，并在解析
  provider 之前调用。
- **`doctor --probe` 的 5 秒超时把能用的 Provider 判成不可达**。容器内实测：DNS 0.03 s、
  到 `api.deepseek.com` 的 TCP **4.0 s**、TLS 与 401 再 1.3 s。5 秒预算一擦边就是
  `ConnectTimeout`，会把人送去查防火墙，而真正的原因是路由距离。默认改为 15 秒。
- **MCP 子进程关闭时打印 `Exception ignored in BaseSubprocessTransport.__del__`**。
  `close()` 只 terminate + wait，没有收掉管道，于是传输对象被回收时 CPython 打一段
  traceback——部署日志里看起来像崩溃，其实是正常关机。
- **两张表格的行只能鼠标点**。人格表与会话表的 `<tr @click>` 没有 `tabindex`，键盘用户
  根本到不了，且按 Enter 什么也不会发生。补上焦点与 Enter/Space；`@click.self` 的遮罩层
  是例外，它不该成为 tab 停靠点（Esc 已经负责关闭）。
- **`Pipeline.observe` 的回调是 async 的**。首版传入同步函数，`await None` 抛错被
  pipeline 当作 observer 错误吞掉，导致所有耗时静默丢失、端点仍返回 200 空列表。
  现由 `_observe_stage` 适配，并有测试断言它是协程函数。
- **流水线崩溃的消息不留痕迹**。`_on_event` 的 except 分支直接 return，既不发布也不
  计数，`failed` 永远为 0。现在记录一条 `halt_reason=pipeline_error` 的 trace。
- **`file_hash` 与 `build_patch` 用了不同的哈希口径**：前者对原始文本、后者对规范化
  后渲染的内容，导致读取端点发出的 `base_hash` 永远无法通过写入校验。现统一走
  `render`。
- **只读文件无法被 `os.replace` 覆盖**（Windows WinError 5）。现在写入期间临时解除
  只读位、写后恢复，文件最终仍是只读。
- **`STAGE_ORDER` 与 `build_pipeline` 不一致**：插件环节实际名为
  `plugin_message_hooks`。漂移测试立刻抓到了它。
- **`make check` 与 CI `backend` 不是同一组命令**，而 `Makefile` 文件头就写着它们是。
  实测差集：`check_deps.py`、`check_console_encoding.py`、`check_deploy.py` 只在 CI 跑。
  三个都是离线、确定性、一秒内跑完的静态扫描——正是最该在本机跑的那类门禁，它们的缺席
  意味着同一份提交可以本地全绿、CI 全红。现在补进 `check`，并新增
  `tests/test_gate_parity.py` 解析两边文件、断言差集恰好是两项（`check_secrets
  --committed` 要 git 历史，`pip-audit` 要联网）。注释里的承诺不是门禁，这个测试是。
- **Windows 上 `.env` 的跨进程锁有 10 秒硬上限**。`msvcrt.LK_LOCK` 是「重试 10 次 × 1 秒
  后抛 `OSError`」，预算由系统决定且无法观测。4 个进程各写 20 次同一个文件时，全量跑
  大约每轮失败一次——看起来像锁的竞态 bug，实际是重试策略的超时。改用 `LK_NBLCK`
  非阻塞加指数退避（5 ms 起、上限 250 ms），预算 30 秒由我们定；超时抛
  `EnvLockError`（`TimeoutError` 子类，仍是 `OSError`，四个 API 写入点的
  `except OSError` 映射不变），日志能说清「另一个写入者正持有它」而不是「磁盘坏了」。
  睡眠不超过剩余预算，所以超时是真正的上界而不是「上界加一个退避间隔」。


- **开发进度看板** `docs/progress/`：`index.html` + `board.css` + `board.js` +
  `progress.json` + `README.md`。零依赖、零构建、无 CDN、无 webfont，
  用 `make progress` 起静态服务查看（`file://` 下 fetch 会被 CORS 拦截）。
  百分比由文件清单复算（子任务权重 = 文件数，完成比 = 已完成/总数），
  **没有手工填写入口**——手填的百分比没有可信度。
  防「看板撒谎」三项：`updated_at` 超 10 分钟标黄、fetch 失败显式报错且保留上次
  渲染结果、只陈述四态（未启动/进行中/已完成/受阻）。
- **`scripts/check_contrast.py`**：解析 `base.css` 与 `board.css` 的 `:root` token，
  按 WCAG 相对亮度公式断言对比度，并检查 `:root` 之外无硬编码颜色。
  已接入 `make check`（`check: lint contrast test`）与
  `tests/test_a11y_tokens.py`（5 项）。
- **`webui/src/lib/useFocusTrap.ts`**：焦点陷阱 + Esc + 关闭后归还焦点。
  抽出而非各写一遍，因为登录框与确认框都需要且都不能做错。
- **`webui/src/components/ConfirmDialog.vue`**：`role="alertdialog"` + `aria-modal`，
  用 `tone` 与 `irreversible` 区分「可逆」与「不可逆」的措辞——
  统一的「确定吗？」会训练人闭眼点过。

### 变更

- **控制台整体改为浅色企业风**。8 个既有视图全部换肤。
  原因：这套面板实际是在客服通话中、笔记本上、和聊天窗口并排打开的，
  白底与其他窗口读作同一份文档，黑底读作另一个应用。
  保留的部分：衬线标题（运维工具里罕见，是主要识别度）、等宽数据列、
  01–08 编号导航（稳定标识符，重排会让过去沟通里的「05 页」失去指向）。
- **状态色全部重新取值**。深色主题的 `#5ec98a` 在白底上只有 1.9:1，
  不满足 AA。现值是 700 档（`--ok: #047857` 等），并新增 `--ok-soft` 等浅底配对。
- **控件边界从 `#cbd5e4` 改为 `#7c8aa3`**：前者在白底上 1.48:1，
  远低于 WCAG 对表单控件边界要求的 3:1；后者 3.49:1。
  这个值是校验脚本算出来的，不是目测调的。
- **散落的硬编码颜色收进 token**（`--ok-line` / `--warn-line` / `--danger-line` /
  `--brand-line` / `--on-brand`）。此前有 16 处绕过 token 直接写色值，
  其中 4 处引用了换肤后已不存在的变量（`var(--lamp)` / `var(--paper)` /
  `var(--ink-900)` / `var(--ink-600)`），会静默失效。
- **表格语义**：81 个 `<th>` 补 `scope="col"`；有 `<thead>` 的表加
  `.visually-hidden` 的 `<caption>`（面板标题已在屏幕上说明同一件事，
  重复显示只是噪音，但无名称的表会被读屏播报成「表格」）；
  键值表（配置文件、累计计数、策略）的首列改为 `<th scope="row">`，
  加 caption 解决不了这类表的实际问题——读屏无法判断哪个值属于哪个标签。

### 上下文连续性：滚动摘要不再每轮丢失

原来错在哪：`ContextCompressor.compress()` 早就接受 `prior_summary` 并返回更新后的
`summary`，`MemoryStore` 也有 `latest_summary` / `save_summary`，`MemoryStage` 会注入
「【会话摘要】」——但 `AIEngine._prepare` 既不传也不存，装配处也没接线。结果是 L1 摘要
表恒空、每轮从零重压缩、折叠掉的历史只活一个请求。

现在 `AIEngine` 注入 `summary_loader` / `summary_saver` 两个 callable：压缩前读，
在**模型调用之前**写（折叠已经把这些轮次从请求里移走，摘要是唯一副本）。读写失败只记
日志、绝不抛——摘要是上下文的改进，不是回答的前置条件。

### 特权操作的安全边界

原来错在哪：出站 URL 只做 deny-list（拦私网），任何公网主机都放行；记忆检索只按
`scope` 过滤，把过滤器当成了授权边界；`revoke-all` 撤销全部后立刻重签一枚 72h 完整
会话，使撤销只停留在审计日志里；工具参数从模型 JSON 直接进注册表，没有来源标记；
插件加载只有字节摘要，没有能带走的执行凭据；MCP 只协商线协议，不记录第三方实现的
版本。

现在六道确定性边界，每道都配了改错复验（去掉规则则测试必须失败）：

| 能力 | 落点 | 拒绝时的行为 |
|---|---|---|
| 出站目标预允许列表 | `plugins/sandbox.py` | 未列入的主机在 deny-list 之前被拒；空列表 fail-closed |
| 记忆 handoff 反单调准入 | `memory/handoff.py` | 受众被放宽、数据-only 来源、低置信度记录不进 prompt；残余不安全率是实测值 |
| 撤销达到闭合终态 | `api/auth.py`、`security/tokens.py` | 不签发会话；轮换一次性引导凭据并验证终态，任一不成立返回 500 |
| 参数级信息流溯源 | `security/provenance.py` | 来源标记放在 dict 属性上，模型 JSON 无法伪造；资源参数须过宿主注入的校验 |
| 可移植运行时证明 | `plugins/attestation.py` | 工件哈希 + 策略指纹 + 执行证据；签名边界如实标为空，未声称已签名 |
| MCP 实现版本 pin | `mcp/client.py`、`mcp/config.py` | 版本不匹配拒绝并清理子进程；不 pin 也记录身份与协议版本 |

### Windows 双端与桌面端

原来错在哪：三条 Windows 入口注册三个不同的计划任务名（`SoapbotBot` /
`SoapbotPanel` / `soapbot-panel`），触发器和令牌策略还相反；桌面端只是一个连接 6185 的
Tauri 托盘壳，不携带后端、不产安装包，CI 在 Ubuntu 上只做 `cargo check`。

现在：

- 两条安装路径注册**同一个** `SoapbotBot`（SYSTEM、开机启动），令牌只给
  `data\init_token.txt` 的路径；`start-panel.bat` 作为前台本地路径显式豁免并写进测试。
- 后端可冻结成 46.3 MiB onefile（`desktop/sidecar/build.py`），壳先探测 6185、端口空才
  spawn、退出用 `taskkill /T` 杀整棵进程树（`desktop/src-tauri/src/main.rs`）。
- NSIS 安装包本地实测 47.48 MiB，`installer.nsi` 把后端写进 `$INSTDIR\binaries\`。
- CI 新增按需的 `desktop-bundle`（Windows runner），首次真实运行 9m2s、产物 46.9 MiB。
- **签名未做**：`docs/desktop-signing.md` 写明未签名的具体代价（SmartScreen 两次点击、
  杀软误报、企业 AppLocker 可能直拦）与两条开源通道，没有写成「已支持」。

### 发布与协作流程

原来错在哪：`master` 有分支保护，但仓库里没有任何地方写这件事，一次直推绕过了它
（GitHub 回 «Bypassed rule violations»）；Releases 页是空的，唯一产物是 7 天过期的
artifact；AI 助手拿不到仓库的硬性规则。

现在 `CONTRIBUTING.md` 写出五步流程与必需检查名单——名单读自
`branches/master/protection`（`backend` 两个平台、`frontend`、`desktop`、`package`；
`review` 在后续一轮加入，当前为六道），并说明单人维护时 `gh pr merge --admin` 只跳过
人工 approve，与直推不是一回事。
`.github/pull_request_template.md` 把接线测试、文档优先、未验证要标注变成 PR 必答项；
`.github/copilot-instructions.md` 给 AI 助手同一套规则；`ci.yml` 新增 tag 触发的
`release` job，把 wheel 与安装包挂到 GitHub Release。

### 类型检查棘轮、查询效率与分包

`mypy` 一直以 `continue-on-error` 运行：79 个错误躺在没人打开的日志里，第 80 个也不会
被拦——和当初 `pip-audit` 的毛病一样，能失败才算门禁。新增
`scripts/check_mypy_baseline.py`：基线写在同一目录的 `mypy_baseline.txt`，只允许降不允许
升，不要求修那 79 个，只拒绝新增。一次约 1.7 秒，已进 `make check` 与 CI 的 `backend`
job（`tests/test_gate_parity.py` 保证两边一致）。

三处结构问题：

- `memory_stats` 对每个 layer 单独 `COUNT`，一屏 4–5 次往返，且每次可能读到不同快照，
  于是「总数」和「各部分之和」在负载下能对不上。改为一次 `GROUP BY`
  （`MemoryStore.count_by_layer`）；`-1` 仍表示「这一屏读不到」，与「零行」区分开。
- 技能列表的目录遍历和保存时的 `mkdir + write_text` 原来直接在事件循环上跑。改用
  `asyncio.to_thread`——同文件里 `api/napcat.py` 早就是这个写法，只是没推广。
- 面板没有 vendor 分包：`vue`/`vue-router`/`pinia` 与视图代码打进同一个入口 chunk。
  加 `manualChunks` 后实测 `vendor` 104.28 kB、`index` 143.69 kB（gzip 40.60 / 52.69），
  面板更新时只有视图 chunk 失效。

删掉 3 项未接线代码：`SceneMemory.drop_portrait`、`content_fingerprint`、
`charts/Sparkline.vue`（134 行，从未被 import）。`check_secret_resolvable` **没有删**：
它的注释明确写着「Unused, and deliberately kept」，理由是替代做法会在 API 层长出第二套
密钥解析——注释里写明的取舍不该被当成死代码清理。

### 破坏性操作的确认统一走组件

面板里 5 处删除/撤销用的是原生 `window.confirm`：它阻塞事件循环、渲染在焦点陷阱之外
（键盘还留在背后那一页上）、且只能显示一个字符串——所以记忆页三种不同的删除，在「确定
不可逆」那一刻看起来完全一样。

现在统一用 `ConfirmDialog`，目标自带类型（记忆 / 知识文档 / 技能 / 撤销审批 / 删除插件），
对话框据此显示正确的标题与后果；请求进行中按钮禁用，**失败时对话框不关闭**——先关再失败
会让人以为已经删掉了。

`scripts/check_a11y.py` 增加第五条规则禁止 `window.confirm`，配套
`tests/test_a11y_gates.py` 三条用例：真实调用必须被抓到、注释里的提及不能误报、仓库当前
干净。规则按行判断并跳过注释行，这是近似做法，写在函数的 docstring 里。

## [0.1.0] - 2026-10-28

首个可 clone、可构建、可部署的版本。

### 新增

- `LICENSE`（MIT）、`.env.example`、`CHANGELOG.md`、`Makefile`、
  `.github/workflows/ci.yml`、`scripts/check_deps.py`。
  此前仓库声明 MIT 但没有许可证文件，且没有任何自动化检查。
- 示例插件移入包内 `src/soapbot/examples/plugins/`（`admin` / `echo` / `help` /
  `remind`），通过 `soapbot.examples.bundled_plugins_dir()` 访问。
  此前它们在 `data/plugins/`，而 `data/` 被 `.gitignore` 排除：全新克隆没有任何
  插件，五个测试模块直接 `FileNotFoundError`。
- 插件批准状态持久化到 `data/plugin-approvals.json`
  （`soapbot.plugins.approvals.ApprovalStore`），并在启动时自动加载已批准的插件。
- 插件工具调用全链路：`AIRequest.tools` / `tool_note`、`ModelStage` 有界工具循环、
  隔离模式下的 `register_proxied_tool`。
- notice 链路：`OneBot11Adapter._to_notice`、`Adapter.emit` 放行 `NOTICE`、
  `BotRuntime._on_notice`。
- 群管命令 `/mute` `/unmute` `/kick` `/recall-msg`，以及
  `Permission.MODERATE_GROUP`。
- 适配器群管动作契约：`recall` / `set_group_ban` / `set_group_kick` /
  `get_group_list`，OneBot 端完整实现。
- 知识库写入 API：`POST /api/knowledge`、`DELETE /api/knowledge/{doc_id}`、
  `GET /api/knowledge/{doc_id}`，以及 `KnowledgeBase.ingest_document`（覆盖语义）。
- 管理面板新增「模型与人格」(07)、「运行日志」(08) 两页；记忆页补齐知识库上传与删除；
  插件页补齐「撤销批准」「删除」。
- `MemoryStore.find_message`：按会话 + 平台消息 ID 查询，供撤回命令做归属校验。

### 修复

- **QQ 官方适配器在群里完全不应答**。`_strip_at_prefix` 把 `<@bot>` 抹掉后不产生
  AT 段，而 `WakePolicy` 在群里先找 AT 段、再找唤醒词，两者都没有 → 所有正确
  @机器人 的消息被静默丢弃。现改为 `split_leading_at` 返回 `(mentioned, body)`，
  调用方据此补一个 AT 段。OneBot 端不受影响，因为它原生携带 AT 段——这正是缺陷
  长期不可见的原因：两个适配器对「谁来判断是否被呼叫」没有共识。
- **私聊在任何配置下都不可用**。`build_runtime` 接收 `allow_unknown_private` 却从未
  使用，`AccessPolicy()` 无参构造，因此 `SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true` 无效。
  新增 `build_access_policy()`，并把 `private_allowlist` / `group_allowlist` /
  `group_blacklist` / `user_blacklist` 一并接入配置。
- **插件批准在重启后全部丢失**。`_approved` 是纯内存字典，导致：重启后没有插件在跑、
  WebUI 显示「已启用」却加载失败、无头部署根本无法授权。
- **模型永远看不到插件工具**。`PluginToolRegistry.available_for` 零调用方，
  `AIRequest` 无 `tools` 字段，Provider 层虽已支持 `tools` 却收不到。
- **隔离模式下工具被注册成了命令**。worker 用同一帧上报命令与工具，宿主把两者都按
  命令注册，于是工具变成 `/tool-name` 斜杠命令，模型反而看不到。
- **`on_notice` 永远收不到通知**。三处同时断开：OneBot 丢弃 `post_type != "message"`、
  `Adapter.emit` 对非 MESSAGE 直接 return、`PluginManager.on_notice` 无调用方。
- **群管能力只有声明没有实现**。OneBot 声明了 `RECALL`/`MUTE`/`KICK`/`GROUP_LIST`，
  四个方法一个都没有。
- **知识库只读**。`add_document` 等写入路径实现完整且被检索侧消费，但服务内没有任何
  调用方，知识库页面只能是空的。
- **`list[str]` 配置项用逗号分隔会导致启动失败**。pydantic-settings 对复杂类型先做
  `json.loads`，`SOAPBOT_OWNER_IDS=123,456` 抛 `SettingsError` 且不说明正确写法——
  而文档写的正是逗号分隔。现支持 `a,b` / `a;b` / `["a","b"]` 三种。
- **声明了四个从未使用的依赖**：`structlog`、`watchdog`、`python-multipart`、
  `edge-tts`。依赖清单会扩大审计面，并让评审者以为项目具备实际不存在的功能。

### 变更

- 插件启动行为从「只发现、永不加载」改为「发现 + 加载已批准项」。区别在于选择来源：
  前者不会执行任何东西，后者执行的是**曾经由人做出的持久决定**。未获批准的目录仍然
  被 `load()` 拒绝，这条规则没有放宽。
- `/recall` 保持「检索记忆」语义，撤回消息命名为 `/recall-msg`。复用 `/recall` 会让
  既有部署的命令静默变成另一种行为。

### 已知限制

见 `docs/delivery-readiness-assessment.md` 与 `docs/wave6-10-runtime-auth-webui.md`。
简要列出：

- 插件之间不互相调用（设计如此：插件 A 不能借插件 B 提权），也没有插件市场。
- 无 MCP、无 STT/TTS、无流式输出、无 i18n。
- QQ 官方适配器的群管能力未实现（平台侧限制）。
- 额度审批、B 站浏览默认关闭，需显式开启。
- 清单摘要漂移只报告不阻断（在 `GET /api/plugins` 的 `approval.manifest_changed` 里）。

[Unreleased]: https://example.invalid/soapbot/compare/0.1.0...HEAD
[0.1.0]: https://example.invalid/soapbot/releases/tag/0.1.0

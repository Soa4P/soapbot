# 能力矩阵与群管命令

每个平台支持什么、群里能用的管理命令有哪些。

**写给：** 想确认「这个功能到底有没有」的人。

> 这部分从 `README.md` 搬出来，是为了让 README 只回答「是什么、怎么跑起来、坏了怎么办」。
> 内容没有删减。

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
| 额度审批 | ✅（默认开） | 日/周/月周期与单笔上限（整数分）；状态机、原子预留、禁止自批、批准时重算额度。`POST /api/budget/{id}/approve\|deny` 与 QQ `/budget` 共用账本，都要求 `APPROVE_PAYMENT` + 真实凭据；面板第 10 页可批准/驳回。两条路径都往 `APPROVAL_BUS` 发同一份事件。**仍不**持有支付凭据、调用支付 API 或自动扣款 |
| B 站元数据与观后感 | ✅（默认关） | L2 公开元数据；L3 登录态由插件的 `bilibili` 能力承担（Cookie 宿主持有，需配 `SOAPBOT_BILI_COOKIE`） |
| 插件发图片（表情包/照片） | ✅（需逐项批准 `send_media`） | 与 send 同一套会话白名单 + 4 MiB 上限；审计只记大小 |
| 人格卡自主字段与温度 | ✅ | 人格卡 front matter 可选 `autonomy`（会话白名单 / 每日上限）、`warmth`（起点 / 增速 / 衰减 / 阈值）、`voice_self_select`；非法值回退保守默认，面板保存与版本回滚都不丢。宿主 `WarmthTracker` 只在回复成功归档后计数，`session.view` 只读暴露 `warmth` 标量。**挑音色的管线环节未实现** |
| WBI 字幕读取 | ✅（L2，默认关） | `BilibiliClient.subtitle(bvid)` 走 `/x/player/wbi/v2` + WBI 签名，**不注入登录 Cookie**；只返回语言与字幕 URL 白名单，L1 明确拒绝。端点 `GET /api/bilibili/subtitle` 由宿主钉死，插件不能自选 path |
| QQ 空间读写 | ✅（默认完全关闭） | `qzone_read` / `qzone_write` 分开审批；`SOAPBOT_QZONE_VIA_PROTOCOL=true` 才可用，只有四个白名单协议动作，token 宿主持有，写需 `confirm=true` + 插件二次命令确认，审计不记正文。官方机器人无此接口，只能走个人号协议端，**有账号风控/冻结风险，风险自负**。示例插件 `qzone-diary` / `qzone-watch`。**未做**真实协议端联调 |
| 审批通知三通道 | ✅（默认全关，逐项配置） | QQ 主动消息（`NOTIFY_SESSION_KEY`）、HMAC-SHA256 签名 Webhook（`NOTIFY_WEBHOOK_URL` + `NOTIFY_WEBHOOK_SECRET`）、手机游标 feed（`GET /api/approvals/feed?after=`）。单一 `APPROVAL_BUS` 订阅点，`(request_id, kind)` 幂等；通道失败只记异常类型，密钥不进头/日志/审计。**没有**持久 outbox——进程重启可能重通知一次 |
| 公开网页浏览与消费提案 | ✅（需逐项批准 `browse`，白名单默认空） | `browse.read` / `browse.propose`：点名域名的 allowlist（空 = 拒绝一切）+ robots.txt 同意 + 可识别 UA；无 Cookie / 登录态 / 重定向 / 表单 / JS，响应与正文有上限。`propose` 先做单笔与日/月限额预检，不通过就不建申请；金额来自页面确定性提取，最终仍要人审批、自己去官方渠道买。**没有**无头浏览器渲染、代付链接、电商登录态、支付 API |
| 插件取消息里的图片链接 | ✅（需逐项批准 `media_observe`） | `ctx.observe_images()` 不带参数，会话键由宿主绑定的 caller 决定；纯内存、TTL 120 秒、取一次即消费、单条消息 ≤16 个 http(s) 引用；只交引用，不交内联 base64 或本地路径。URL 不进日志 / 审计（只记数量）/ trace / messages 表，进程内与隔离形态各有接线测试。**没有**事件广播——隔离 worker 目前不转发命名事件 |
| 看屏幕（第一阶段，只看不碰） | ✅（默认关，双门） | 机器人「看」专用工作机的画面：`SCREEN_ENABLED` + `SCREEN_DEDICATED_MACHINE` 双门（主机名不一致或声明为空一律拒绝）。筛帧去重 → 拼成 ≤1024 网格图 → 经宿主 inbox 进模型上下文；**不落盘、不进审计（只记帧数/时长/字节）、插件拿不到位图**；`/look [帧数]` 四端可用，插件走 `screen.capture` 能力（敏感类 30 次/分钟滑窗）。抓屏需 `pip install 'soapbot[screen]'`。**没有**键鼠注入（控制面第二阶段，三前置未齐不开工）、没有画面存储、没有远程桌面 |
| 插件包安装 | ✅ | **上传 zip 即安装，不等于批准**——没有在线商店、没有搜索与评分。装完仍需 `approve` + `load` |
| MCP 客户端 | ✅（默认关） | `config/mcp.yaml` 声明式接入，工具作为独立来源注入模型调用，按 server 的 `min_role` 逐个授权；`GET /api/mcp` 报告每个 server 的工具数与错误 |
| MCP 面板编辑 | ✅ | 07 页可直接增删改：读取 → diff → 确认 → 写入，写入后热重载并逐 server 报告「N 个工具」或「启动失败·原因」。**仅 owner**——新增一台服务器等于开放一条子进程执行通道。`env` 只写不读：接口只回键名，diff 里显示 `redacted:` 指纹而不是值 |
| 语音 | ✅（默认关） | 入站转写（多 Provider 故障转移）+ 出站 edge-tts（需 `.[voice]`）。没有厂商凭据时以明确失败降级，不伪造结果 |
| 流式输出 | ✅（默认关） | `STREAM_REPLY=true` 且适配器声明 `PROGRESSIVE` 才生效——目前只有 OneBot v11 声明。工具调用轮次不流式。09 页可观察：首 token / 首句送达 / 整条回复三段耗时 + 实际发出的分句 |
| 多用户账号 | ✅ | 邀请制：`account_invites` 只存邀请码的 SHA-256，一次性、默认 72 小时过期（`hours` 可调，上限 30 天）；密码用标准库 `hashlib.scrypt(n=2**14, r=8, p=1)`，salt 与 hash 分列，比较走 `hmac.compare_digest`。首个所有者必须带面板的一次性 bootstrap token（`POST /api/accounts/owner`），账号表非空后该端点固定 409——否则它就是公开注册。停用 / 启用走 `POST /api/accounts/{id}/status`（仅 owner），停用会立即作废已签发的 cookie，最后一个活动 owner 不能被停用。**没有**删除账号、找回密码、邮箱验证、双因素 |
| 只读聊天存档 | ✅ | 第 13 页 + `/api/chat/*`：会话按 `chat_memberships` 在 SQL 里过滤（不是取完再筛），越权返回 404 而非 403；消息用 `after_id` 游标而非 offset，并发写入不重复不漏行；输入只写 `role=note` / `adapter=web` / `delivered=false`，调用图不 import 适配器。**没有**发送、编辑、删除、导出 |
| 聊天端开关 | ✅ | `SOAPBOT_CHAT_WEB_ENABLED`（默认开）、`SOAPBOT_CHAT_APP_ENABLED`、`SOAPBOT_CHAT_DESKTOP_ENABLED`（默认关）。全关时 `/api/chat/*` 返回 404 而不是 403，像这个部署从没有过这些路由。手机端与桌面壳默认关闭，因为它们是装到别人设备上的二进制 |
| 多语言 | ✅ | 中文 / English，三条通道：机器人发到群里的话（`DEFAULT_LOCALE`，人格卡可逐群覆盖）、API `detail`（按 `Accept-Language`）、面板全 13 页含外壳与图表（按浏览器切换并持久化）。流水线阶段名与顺序约束由后端按请求语言输出，不在前端维护第二份文案。**日志与堆栈有意保持英文**：同一事件在不同语言下变成不同字符串，会让 `grep` 与告警规则静默失效。`tests/test_webui_i18n.py` 用「模板里不得残留中文」防止半翻译回归 |
| 插件间互相调用 | ❌ | 设计如此：插件 A 不能借插件 B 提权 |

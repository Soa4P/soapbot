# 第十四批：AstrBot 市场增量（batch12b 之后，2026-11-28）

> 方法：重拉官方数据源 `api.soulter.top/astrbot/plugins`（3573 条，快照版本
> `2026-11-27T18:08:31Z`），与 batch12b 目录（3483 条）按 author/name 对齐——**新增 82、
> 下架 1**（livingmemory 旧条目被 lxfight v2.0 重构版替换）。增量全是新上架插件，下载量
> 尚小（最高 34），所以本批看的是**机制新颖度**而不是市场热度。沿用既有排除判例，判定
> borrow / have / exclude / watch（设计输入）四值。

## 一、排除（增量里的新判例，各一条）

| 插件 | 排除理由 | 判例归属 |
|---|---|---|
| `saitenasuk/webdav_backup` | 备份同步到 WebDAV = **备份内置上传**。操作者硬规则：备份不内置任何上传，凭据不进外部服务 | 硬规则（非裁量） |
| `摆烂的四不相/infocard` | `/开盒 @群友` 查资料卡片——把「查别人」做成一键功能 | 隐私侵害面（新判例） |
| `chen/fake_chat_image` | 渲染 QQ 风格**伪造聊天截图**——欺骗面，产出物的唯一用途是冒充真实对话 | 欺骗面（新判例） |
| `wbndm/music_hub`、`zaras123/qqmusic_ref`、`WorkBuddy/music_request` | 依赖 qqmusic-api-enhanced 等非官方端点（逆向协议） | 逆向判例 |
| `許卿辭/douyin_agent` | 抖音平台接入走逆向网关 | 逆向判例 |

## 二、设计输入（watch——登记进宿主面待议，不排期）

| 插件（热度） | 机制 | 对应宿主面 |
|---|---|---|
| `maolbsMd/snippet_router` (3) | 意图路由换模型/工具白名单，**句末临时分片注入人设**，明确以不破坏前缀缓存为目标 | providers router 与 A15-t4 缓存纪律同源；「分片注入」是 prompt_order 三原则的新变体 |
| `ktouching/wenziyu` (7) | **不依赖模型的硬闸门**：指定用户的回复由程序强制加称呼，模型绕不过 | ReplyStage 确定性后处理——与「模型无权争辩」的降级哲学同构 |
| `dsh/ctx_view` (3) | 会话上下文大小、**缓存命中率**、按日/周/月分模型花费 | provider accounting 已有调用量/延迟；缓存命中率是上游未稳定暴露的字段，登记观察 |
| `zhishimaomao/self_schedule` (7) | 对话安静后**自己决定要不要找、多久后找**，到点主动发 | auto-chat 0.4.0 的峰谷掷骰之上加「静默反应式触发」；推送审批语义仍待拍板 |
| `keyou/proactive_life` (10) | 入站准入（防抖/戳一戳/跟读）+ 主动生活编排 | 戳一戳（notice）与撤回联动是协议面盲区，登记 |
| `mcratt/st_worldinfo` (5) | World Info 字段触发注入（位置/深度/递归） | KnowledgeEngine 可插拔 RAG（batch13 登记）之外的第二种检索形态：**关键词触发**而非相似度 |
| `Ariadne/ariadne` (3) | 事实抽取成**带类型的有向记忆图谱**，沿边检索 | 星图之外的第三种记忆结构；架构级，登记 |
| `lxfight/livingmemory` v2 (129k) | 记忆生命周期 v2 重构（衰减/巩固/遗忘分级） | batch12 已把 LivingMemory 记为 A15 对照，v2 更新对照 |
| `SmileYik/playwright_tools` (28) | 给模型的浏览器：元素编号点击填表 | 与 browse 只读纪律冲突（读→执行的升级），除非 browse 提案链拍板扩面，不动 |
| `snowy/codex_images` 等 | 生图/图生图 | 生图待拍板 |

## 三、仿写落点：B 站链接信息卡（本轮唯一 borrow→实现）

**参照**：`Nakiya233/analysis_bilibili`（2）——检测聊天中的 B 站链接（含 b23.tv 短链、
QQ 小程序卡片），自动回以标题、UP 主、播放数据与封面。

**为什么是它**：

* 与既有 bili 只读面同族（`/bili` 命令、字幕面、直播播报），复用宿主 L2 client——
  不新增出站路径，不新增凭据面；
* 机制确定性：正则提链接 → 白名单字段卡 → 回复，无模型调用；
* 正好补上「没人问但答案会出现」的另一半：直播播报管**状态变化**，链接卡管**有人贴链接**。

**与上游的差异（仿写不是照抄）**：

| 上游 | soapbot 形态 |
|---|---|
| 插件自己抓 view API（插件侧网络） | 新增 **`bilibili.view` surface**：L2 client 代取，插件只发目标只拿白名单字段——与字幕面同款边界，封面/播放地址等 player 内容不过边界 |
| 小程序卡片解析 | 只认文本里的 BV/av/b23——小程序 JSON 不进正则面 |
| 无去重、可被刷屏 | 会话 TTL 去重（同一视频 N 分钟内只卡一次）+ 会话每分钟上限 + surface 预算 + 客户端限流，四层 |
| 回复带封面图 | 纯文本卡：标题/UP主/时长/分区/播放数据/链接 |
| 链接解析在插件 | **宿主代解析**：b23.tv 302 只读 Location 头、校验落点是 B 站域名（client 既有纪律），插件从不拿到重定向目标本身 |

**能力面**：`message`（钩子看链接）+ `send`（回卡，受限已观察会话）+ `bilibili`（view surface）
+ `storage`（TTL 去重）。四能力全是既有面，宿主只新增 `bilibili.view` 一个只读 surface。

## 四、账

| 判定 | 数量 |
|---|---|
| borrow（实现） | 1（bili-card） |
| watch（设计输入） | 10 |
| exclude | 8（新判例 3：备份上传、隐私侵害、欺骗面） |
| have（已覆盖：ignore_at≈唤醒规则、stealer≈sticker-album、sensevoice≈语音面） | 3 |
| 其余为低热度小游戏/查询类，未达登记线 | 60 |

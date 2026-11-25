# batch12b: AstrBot 市场全量逐插件目录（3483 条，2026-11-21 快照）

batch12 十八类聚类的逐条扩展：每个插件一条记录（机制类目 + 判定）。
判定四值：borrow=借鉴候选 / have=宿主已有同构面 / exclude=边界排除 / watch=观察。
头部插件深判定沿用 batch12 §3；本目录是全量机械分类底档（规则词表见
机制级正则，中英双语；未命中词表的落 other/watch——语义级归类以 batch12
报告的 18 类聚类为准，本目录提供逐条可复查的底档）。
数据源：https://api.soulter.top/astrbot/plugins（301 → cloud.astrbot.app，验证后单跳）。

| 类目 | 数量 |
|---|---|
| other | 1623 |
| game | 289 |
| memory | 237 |
| media-parse | 196 |
| group-admin | 169 |
| personality | 169 |
| tts | 160 |
| sticker | 134 |
| info-push | 113 |
| image-gen | 80 |
| platform | 77 |
| kb-rag | 63 |
| proactive | 60 |
| group-stats | 38 |
| devtools | 34 |
| ssh-exec | 14 |
| nsfw | 13 |
| payment | 11 |
| reverse-eng | 3 |

| 判定 | 数量 |
|---|---|
| borrow | 368 |
| have | 1117 |
| exclude | 41 |
| watch | 1957 |

## 全量逐条（按下载量降序）

| # | 插件 | 下载量 | 类目 | 判定 | 描述（截断 150 字） |
|---|---|---|---|---|---|
| 1 | meme_manager | 207680 | sticker | borrow | 为 AstrBot 提供 WebUI 表情包管理页面、资源广场和语义检索功能， 支持官方及社区资源包安装、多表情包管理、AI 智能发送、自动收集、 会话与人格选包、云端同步，以及 prompt 自动维护。 |
| 2 | astrbot_plugin_proactive_chat | 158894 | proactive | watch | 一个能让 Bot 在私聊和群聊中发起主动消息的插件，拥有上下文感知、持久化数据、动态情绪、免打扰时段和 TTS 集成。还有独立 WebUI，可进行个性化配置。 |
| 3 | astrbot_plugin_livingmemory | 126674 | memory | have | 为 AstrBot 打造的、拥有完整记忆生命周期的智能长期记忆插件（v2.0 重构版）。 |
| 4 | astrbot_plugin_group_chat_plus | 107552 | other | watch | 一个以 AI 读空气为主的群聊聊天效果增强插件 |
| 5 | astrbot_plugin_qzone | 100344 | group-admin | have | QQ空间对接插件, 支持查看/点赞/评论说说、自动发说说、AI写说说、表白墙投稿与审核等功能 |
| 6 | astrbot_plugin_private_companion | 95692 | memory | have | 面向 AstrBot 的独立持续型 AI 陪伴核心。统一管理角色状态、日程、关系、私聊与群聊理解、主动消息编排及运行诊断；Memory 可独立选装协同，Content、Image、ComfyUI 等扩展未安装时对应能力不启用。 |
| 7 | astrbot_plugin_qqprofile | 75865 | personality | have | [仅aiocqhttp]配置bot的头像、昵称、签名、状态等QQ资料, 同时可绑定于不同人格 |
| 8 | astrbot_plugin_self_learning | 66018 | personality | have | SELF LEARNING 自主学习插件 — 让 AI 聊天机器人自主学习对话风格、理解群组黑话、管理社交关系与好感度、自适应人格演化，像真人一样自然对话。(使用前必须手动备份人格数据) |
| 9 | astrbot_plugin_anysearch | 59752 | info-push | have | 调用 Anysearch API 实现联网搜索。支持通用网页搜索、新闻与文档检索、批量查询和网页正文提取，适合让 Bot 在回答中获取更及时、更可靠、更稳定的外部信息。 |
| 10 | astrbot_plugin_angel_memory | 36780 | memory | have | 长期记忆与人格进化的AI陪伴：记住偏好、关系和约定，本地知识库问答，群聊私聊都能用，越用越懂你。 |
| 11 | astrbot_plugin_stealer | 33594 | sticker | borrow | 人机代码，仿maibot的表情包偷取。让bot自动偷走别人的表情包并为己所用。配置好视觉模型就能自动识别分类，对话时根据情绪自动发送。支持 Meme Manager / AstrBot Meme Pack、外部 HTTPS JSON API、LLM 主动选表情包、WebUI 管理、存储清理、作用域修 |
| 12 | astrbot_plugin_memory_companion | 31371 | memory | have | 我会牢牢记住你是面向 AstrBot 陪伴体系的记忆陪伴中枢。它统一管理长期记忆、历史对话整理、群聊连续对话记忆、主链注入、权限边界、知识图谱、陪伴插件桥接、自然衰减、可移植数据、双界面管理和运行诊断。 |
| 13 | astrbot_plugin_matsuko_cover | 30319 | tts | watch | 🐱 AI翻唱插件（支持 RVC、SVC-Fusion、SoulX-SVCVC 参考音色、随机种子、QQ音乐、本地音频与 LLM 点歌） |
| 14 | astrbot_plugin_parser | 28291 | media-parse | borrow | 高性能低耦合的万能链接解析器。支持的类型：视频、图集、音频。 支持的平台：A站、B站、抖音、tiktok、微博、小红书、快手、油管、X... |
| 15 | astrbot_plugin_listen_music | 23709 | media-parse | borrow | Bilibili 单源搜索、语音听歌与文件下载。 |
| 16 | astrbot_plugin_memewiki | 19516 | sticker | borrow | 查梗：先查本地全量字典（毫秒级），未命中回落 cnmeme.wiki 公开 API；/梗 指令可出图片卡片，支持每天自动同步。 |
| 17 | astrbot_plugin_biliread | 19002 | media-parse | borrow | 告别机械式的视频大纲复制，让你的 AstrBot 拥有真正“看懂” B 站视频的能力。 |
| 18 | astrbot_plugin_AstrNa | 18136 | other | watch | AstrNa是一款AstrBot优化插件 |
| 19 | astrbot_plugin_get_px | 18029 | nsfw | exclude | 下拉选择 Lolicon 或 Pixiv 优先获取插画，请求失败或无结果时自动尝试另一源；使用 Pixiv 需配置 refresh_token。内容安全采用全局规则与完整会话命名分组，默认关闭 R18，关键词支持宽松/严格匹配；提供模型原生取图工具与随包 Skill；同时提供每日签到、群签到排行、主 |
| 20 | astrbot_plugin_clonetts | 17623 | tts | watch | 使用自定义克隆音色让你的聊天机器人开口"说话"。 |
| 21 | astrbot_plugin_music | 16244 | tts | watch | 高性能低耦合的点歌插件, 支持AI点歌、卡片播放、语音播放、热评、歌词、歌单、多音源、无需VIP |
| 22 | astrbot_plugin_self_evolution | 15459 | memory | have | 让大模型具备自我迭代、记忆沉淀和人格进化能力的插件。 |
| 23 | astrbot_plugin_qzone_ultra | 15327 | group-admin | have | QQ空间Ultra，更稳定的QQ空间插件，支持自动绑定QQ空间，采用独立进程：占用极低、稳定性极高，支持看/评/赞/发/写/删说说、回评、投稿审核、自动发评和 LLM tools。 |
| 24 | astrbot_plugin_pokepro | 14770 | group-admin | have | 【专业的戳一戳插件】支持触发（反戳：LLM：face：图库：语音：禁言：命令），戳@某人，跟戳 |
| 25 | astrbot_plugin_angel_heart | 14325 | other | watch | 群聊拟人接话：离场/在场两态控制，只在被点名时进场；轻重双AI判断是否接话，防频繁插话，省API成本。 |
| 26 | astrbot_plugin_knowledge_base | 13429 | kb-rag | have | astrbot_plugin_knowledge_base 是一个为 AstrBot 聊天机器人框架量身定制的强大知识库插件。 它允许您的机器人连接到自定义的知识源，通过先进的检索增强生成 (RAG) 技术， 让机器人能够基于准确、具体的私有信息进行对话，而不仅仅依赖预训练模型的通用知识。 |
| 27 | astrbot_plugin_image_companion | 12498 | image-gen | watch | “我会永远陪着你”的图像生成扩展，支持文生图、自拍、人像改图、参考图库及多种生图后端。 |
| 28 | astrbot_plugin_qq_group_daily_analysis | 11774 | group-stats | borrow | 群日常分析总结插件 - 支持 QQ 官方机器人、Telegram、Discord、OneBot v11、Satori；生成精美的群聊分析报告，支持话题分析、用户形象、群聊圣经等功能 |
| 29 | astrbot_plugin_master_aware | 11751 | personality | have | 让机器人认得「谁在跟自己说话」。 模型本身看不到发送者的 QQ 号，所以人格里写再多「主人是谁」也不起作用； 这个插件在每次 LLM 请求前比对发送者 QQ，命中名单就注入身份说明， 并把提示贴到当前用户消息前面，避免被长 system prompt 末尾和人设里的傲娇话术淹没。 支持多个主人、自定 |
| 30 | astrbot_plugin_virtual_life | 11726 | proactive | watch | 按人格管理长期阶段、虚拟日程、穿搭与主动消息，按可打扰程度延迟回复。 |
| 31 | astrbot_plugin_dynamic_life_state | 11149 | other | watch | 为 Bot 生成一天的生活时间线，并在每次对话时注入当前时间段对应的状态。 |
| 32 | astrbot_plugin_debounce | 10806 | other | watch | 支持 ONNX / JEV 判断的消息防抖插件，合并连续图文消息，减少重复 LLM 调用 |
| 33 | astrbot_plugin_palette | 10763 | other | watch | AstrBot调色盘是一个 AstrBot WebUI 美化插件 |
| 34 | astrbot_plugin_anti-bot | 10708 | other | watch | bot可以自己分辨群友有没有说bot坏话从而自己怼人的插件 |
| 35 | astrbot_plugin_mimo_tts_clone | 10346 | tts | watch | 提供 MiMo v2.5 voiceclone 官方接口接入、Pages 音色管理、授权参考音频上传、 试听诊断、全局/群/用户/情绪默认音色设置、发送前 AI 语音导演、聊天命令朗读、 普通 LLM 回复概率语音化，以及面向其他插件复用的 TTS 服务方法和 LLM 工具。 |
| 36 | astrbot_plugin_qq_tools | 9781 | group-admin | have | 为 AstrBot 提供 QQ 平台（OneBot / aiocqhttp）特定的工具集：引用回复、撤回消息、检索最近消息、群管理、头像查看、网页浏览（Playwright）、视频分析（Gemini）、以及「定时唤醒」等能力。 让机器人在 QQ 场景下的“动手能力”更强，增强自主性。 |
| 37 | astrbot_plugin_smart_imagechat_hub | 9677 | sticker | borrow | LLM 驱动的一体化图片对话插件。自动生成多维度图像标签，并通过多模态语义分析，实现智能斗图、主动表情、表情包分享等多种功能，支持多源导入图库。 |
| 38 | astrbot_plugin_essential | 9662 | proactive | watch | 随机动漫图片、以图搜番、Minecraft服务器、一言、今天吃什么、群早晚安记录、EPIC喜加一。帮助：https://github.com/Soulter/astrbot_plugin_essential |
| 39 | astrbot_plugin_iris_chat_memory | 9136 | memory | have | 轻量级长期记忆插件，专为群聊陪伴场景深度优化，集成三层记忆架构、知识图谱、用户/群聊画像与图片理解。 |
| 40 | astrbot_plugin_memory_diary | 9040 | memory | have | AI 为下一个自己写日记、留下批注与当前交接信，会话重置后用最近日记轻量接续；按需通过内存 SQLite FTS 定位旧证据并回源日期、场景和原文。基础功能开箱即用，高级检索扩展与候选重排默认关闭。支持群与白名单隔离、用户记录与 AI 私人随笔分类、外部素材、可导出可验证备份及可选静态加密；不引入向 |
| 41 | astrbot_plugin_cost_control | 8414 | other | watch | 细粒度 token 预算监控、超预算提醒、缓存破坏诊断、提示词优化与全数据可视化 |
| 42 | astrbot_plugin_apis | 8270 | other | watch | API聚合插件, 海量免费API动态添加, 支持用面板管理 |
| 43 | astrbot_plugin_affection | 7484 | personality | have | 一个基于弗洛伊德心理动力学引入双驱情绪模型的 AstrBot 插件。它模拟了力比多（生本能/爱欲）与攻击性（死本能/毁灭欲）之间的相互作用。机器人的回复与交互将根据这两种核心心理能量的浮动平衡而动态演变，提供独特的、基于心理学基础的陪伴体验。 |
| 44 | astrbot_plugin_bilibili_ai_bot | 7471 | memory | have | B站评论/私信自动回复、好感度系统、语义记忆、主动看视频、动态发布、联网查询 |
| 45 | astrbot_plugin_astrbot_enhance_mode | 7466 | personality | have | 本插件为 AstrBot 的群聊场景提供增强功能，完全替代内置的「群聊上下文感知」和「主动回复」，并额外支持角色标签和发送者 ID。 |
| 46 | spectrecore | 7441 | other | watch | 使大模型更好的主动回复群聊中的消息，带来生动和沉浸的群聊对话体验 |
| 47 | astrbot_plugin_omnidraw | 7296 | image-gen | watch | 轻快生图插件，文生图、图生图、自拍、视频一站搞定。 |
| 48 | astrbot_plugin_angel_smile | 7167 | sticker | borrow | 表情包斗图：AI发消息自动配meme表情，看中的图一句话收进贴纸库存，群聊斗图必备。 |
| 49 | astrbot_plugin_splitter | 7109 | other | watch | 代替框架分段，方便小白操作，更加智能识别、添加更多人性化配置项，优化体验 |
| 50 | astrbot_plugin_memelite | 6765 | sticker | borrow | 表情包生成器，制作各种沙雕表情 |
| 51 | astrbot_plugin_screen_companion | 6624 | personality | have | astrbot_plugin_screen_companion 是面向 AstrBot 的屏幕伙伴插件。它能让bot随机地监视你的屏幕，并根据场景与用户进行互动。插件能监控音量、电脑状态以及你打开的窗口并进行合适的互动，且会根据每天的观察记录完成日记。此外，插件还拥有一个完善的webUI界面。灵感来 |
| 52 | astrbot_plugin_mnemosyne | 6429 | memory | have | 一个基于Milvus数据库的长期记忆存储与查询插件 |
| 53 | astrbot_plugin_Conversa | 6125 | other | watch | 让 AI 像真人一样主动找你聊天。对话沉寂后自动问候，聊天中概率接话，支持完整的 Agent 工具调用。 |
| 54 | astrbot_plugin_qqadmin | 6080 | group-admin | have | [仅aiocqhttp]群管插件，功能包括：禁言、全体禁言、踢人、拉黑、改群昵称、改头衔、设管理员、设精华、撤回消息、改群头像、改群名、发群公告、整理群友信息等等 |
| 55 | astrbot_plugin_steam_price_heybox | 5871 | game | have | 无需 API Key，查询 Steam 游戏当前价、历史最低价、促销记录、小黑盒跨区价格与游戏资料。 |
| 56 | antipromptinjector | 5861 | payment | exclude | 防提示注入，保护 AI 不被恶意调教 |
| 57 | astrbot_plugin_content_companion | 5579 | memory | have | 陪伴体系的独立创作扩展，负责创作项目、续写、审校、记忆整理和作品封面，并与陪伴主插件保持兼容。 |
| 58 | astrbot_plugin_mimo_tts | 5578 | tts | watch | 调用 MiMO-V2.5-TTS series 模型的精细化语音合成插件。自动拦截 LLM 回复生成语音，支持 20 种情感、语速/音高调节、唱歌模式（风格库/画面感润色/自然语言触发）、声音克隆与设计（含 per-voice 风格控制池与 WebUI 试听一键保存）、导演模式（/direct 场景 |
| 59 | astrbot_plugin_anima_master | 5425 | media-parse | borrow | 将 AstrBot 连接到本地 ComfyUI / Anima 工作流，提供生图、提示词优化、法术解析和图片反推能力。 |
| 60 | astrbot_plugin_sticker_sense | 5425 | sticker | borrow | 智能识别用户发送的是【表情包/梗图】还是【普通照片/截图】，告别大模型死板机械的“看图说话”。 - 支持多模态动图 (GIF/WebP) 与启发式尺寸检测，消除动图九宫格出戏幻觉； - 动态精准提取 QQ 官方小黄脸 (Face) 中文语义，支持最新全部表情与商城大表情 (mface)； - 动态注 |
| 61 | astrbot_plugin_reality_companion | 5275 | tts | watch | 面向 AstrBot 陪伴体系的现实设备联动插件，内置米家授权与设备控制，提供独立授权的本机音频播放、摄像头单帧观察、现实提醒、Android 移动端配对与前台位置上下文，并可与“我会永远陪着你”联动延续人格、关系和 TTS 能力。 |
| 62 | astrbot_plugin_isittrue | 4967 | other | watch | 是真的吗——群聊事实核查小工具。@机器人说出你想核实的事情，或引用一条消息，AI 自动判断真假。无需额外 API，即装即用。 |
| 63 | astrbot_plugin_oven_multi | 4876 | kb-rag | have | 提供上下文压缩、智能分段、梗百科离线查询和自定义黑话、Jev 判读、文件读取与 RAG、抖音直播订阅、服务余额及原生 Panel 管理。 |
| 64 | astrbot_plugin_continuous_message | 4865 | other | watch | 消息防抖动插件可将用户短时间内发送的多条私聊消息合并成一条发送给大语言模型，避免频繁触发 AI 回复，提升用户体验。 |
| 65 | astrbot_plugin_edge_tts | 4648 | tts | watch | 基于 Microsoft Edge TTS 的聊天陪护语音插件，支持自定义大模型，需要安装ffmpeg, 全部配置请在插件的 WebUI 控制界面中修改。 |
| 66 | astrbot_plugin_token_controller | 4613 | other | watch | 精细化群聊 Token 流量控制插件：限额、模型阶梯调控、节流与可视化统计。 |
| 67 | astrbot_plugin_polite_silence | 4578 | other | watch | 允许 AI 根据设定概率及提示词自主识别骚扰并拒绝回应，防范恶意持续打扰 |
| 68 | astrbot_plugin_meme_manager_plus | 4578 | sticker | borrow | astrbot_plugin_meme_manager改了一下，可以接入gemini或grok的生图，实现概率回复图片，概率因子由LLM判断；最好放几张初始表情分类要不效果不好懂得都懂 |
| 69 | astrbot_plugin_outputpro | 4525 | sticker | borrow | Astrbot输出管道：图片外显 → 报错处理 → 消息拦截 → 解析艾特 → 文本清洗 → 文本替换 → 表情映射 → 错字模拟 → 文转语音 → 文转图片 → 智能引用 → 合并转发 → 自动撤回 → 分段回复 |
| 70 | astrbot_plugin_angel_eye | 4514 | other | watch | 群聊聊天记录查询工具：让LLM按关键词和时间翻旧账、回看QQ群聊记录，群聊专用函数调用。 |
| 71 | astrbot_plugin_reply_merge | 4445 | sticker | borrow | 用类思维链式的消息防抖机制，让回复更拟人。收到消息后LLM 会像真人一样在心里对你说的话有自己的想法，并且会按照设定的人格来改变思考的语气。期间用户连发的文字与表情包合并为一次请求；思考结论也会注入最终回复，让理解更完整。可用 /思维链 命令查看最近一轮思考（前缀随你的唤醒前缀配置）。 |
| 72 | astrbot_plugin_looki_companion | 4441 | personality | have | 把 Looki 记录的现实生活时间轴带进 AstrBot，让 AI 伴侣了解你的日常、找回照片，并生成二次元风格图片。（大人，时代变了：现在轮到虚拟伴侣看你的时间轴了） |
| 73 | astrbot_sowing_discord | 4410 | other | watch | [仅限 aiocqhttp 适配器] anka - 自动搬史插件, 1.加入喜欢发史的群聊 2.设置搬史来源 3.设置搬史目标 4.开始全自动搬史! |
| 74 | astrbot_plugin_remove_blank_lines | 4294 | other | watch | 在消息发送前检测 Plain 文本段，将连续空行压缩掉，避免回复中出现两段话之间多空一行。 |
| 75 | astrbot_plugin_context_aware | 4226 | memory | have | 群聊场景和图片回看增强；可选私聊长话题记忆，后台整理约定与进度，支持备用模型和重启恢复 |
| 76 | astrbot_plugin_bilibanshi | 4170 | media-parse | borrow | 让你的bot在b站搬石 |
| 77 | astrbot_plugin_emotionai_pro | 4169 | memory | have | EmotionAI Pro 给 AI 角色装上一套会成长的情感与关系：好感度越高，它越会记住并主动提起与你相处的细节，态度也更亲近；好感度低时只记得冲突与边界，语气更冷。它会记住与你相处的经历，对你有真实的态度，也会随着一次次对话慢慢改变关系的远近。好感度与亲密度共同决定关系阶段，喜悦、信任、愤怒、 |
| 78 | astrbot_plugin_tts_emotion_router | 4092 | tts | watch | 支持情绪路由、MiniMax/SiliconFlow/MiMo、18 种中文情绪、会话黑白名单策略与按需语音调用的 TTS 插件。 |
| 79 | astrbot_plugin_dafeiyu_pet | 4085 | other | watch | 轻量化桌宠插件 功能简单 让你的智能体附身大肥鱼 （基于1190fasheqi大佬的项目二次修改） |
| 80 | astrbot_plugin_bilibili | 4064 | media-parse | borrow | 哔哩哔哩动态推送、视频信息、直播间信息查询、自然语言番剧推荐插件 |
| 81 | astrbot_plugin_local_reminiscence | 4047 | memory | have | 轻量级本地记忆插件，使用本地Embedding模型、本地数据库存储和回忆聊天记录。无需额外API，零Embedding成本，节约Token，完全保护隐私。使用Cron Job自动记录对话，通过关键词和语义匹配帮助AI自动回忆起相关经历和概念。支持多会话和群聊，提供境内网络友好的依赖与模型下载配置。跨 |
| 82 | astrbot_plugin_GPT_SoVITS | 3982 | tts | watch | 对接本地部署的GPT_SoVITS,为astrbot提供文本转语音(TTS)服务，支持自定义音色和情绪 |
| 83 | astrbot_plugin_hindsight_memory | 3834 | memory | have | 接入 Hindsight Cloud，为私聊和群聊提供按会话隔离的长期记忆能力. |
| 84 | astrbot_plugin_wifepicker | 3780 | other | watch | 全新的抽取群友当老婆的插件，可以增进群友的感情（）。只抽一个月内取发言过的人，并且可生成老婆关系图，还可以强娶哦~ |
| 85 | astrbot_plugin_portrayal | 3662 | other | watch | 爬取群友的聊天记录，进而用llm分析群友画像 |
| 86 | astrbot_plugin_qzone_tools | 3650 | memory | have | 支持机器人发送定时消息，设置高级定时任务，发送QQ空间，给予Bot非Tool指令调用能力，python沙箱，完美环境的浏览器，群管功能，记忆功能等100+工具的使用，仅支持Napcat version > 4.17.55） |
| 87 | astrbot_plugin_local_tts_voice_modulation | 3612 | tts | watch | 新增更多功能，TTS生成的语音变化更加丰富。基于 AstrBot 的一个小白也会使用的智能情绪 TTS 插件。它调用模型自动判断语境情绪，自动匹配高兴、害羞等对应的参考音频，合成极具感情色彩的语音。支持自动扫描外部目录，参数高度可调，轻松适配大众用户。 |
| 88 | astrbot_plugin_codeforces_helper | 3576 | other | watch | 面向 QQ 群的 Codeforces 训练助手，支持 AC 记录同步、Rating 缓存、排行榜、比赛提醒、赛后战报、定时播报和 Web 管理后台。 |
| 89 | astrbot_plugin_fish_heart | 3537 | memory | have | 给你的大肥鱼一颗跳动的心，而不是一堆记忆。  她会因为你的一句话高兴或委屈。九维情绪（依恋、好奇、反刍、责任、社交、疲惫、亲密、压力、喜悦）加期待、责怪两条快变量，落成日常、委屈、生气、害怕、回避五档。重责不会一步跳过生气，生气按人拆——A 惹的她不会撒到 B 头上。她认得真哄，也认得敷衍；生气时只 |
| 90 | astrbot_plugin_bilivideo | 3478 | media-parse | borrow | 提供b站视频链接自动生成一份结构化的视频总结,带有订阅up主功能并定时推送最新视频 |
| 91 | astrbot_plugin_what_to_eat | 3400 | other | watch | 是啊，吃什么 - 识别"吃什么"关键词，随机推荐美食或复读 |
| 92 | astrbot_plugin_bilibili_learning_bot | 3373 | kb-rag | have | B站 AI 学习互动机器人 — AI 自动刷视频、学知识、评论互动、私信回复、自我进化。提供知识库整理、UP主主页学习、私信/评论安全审核、推荐与脑决策等能力。可作为独立应用运行，也可作为 AstrBot 插件加载（由 PluginManager 通过 metadata.yaml 自动识别 clas |
| 93 | astrbot_plugin_emotionai_pro | 3338 | memory | have | 融合 EmotionAI 与 FavourPro 的新一代高级情感智能插件。 新增「智能更新机制」「辅助 LLM 情感分析」「长期记忆系统」「负好感支持」「关系阶段过渡保护」， 让 AI 拥有真实、渐进、可养成的内心世界，支持多维情感建模、AI 自主文本生成、动态权重与隐私控制。 |
| 94 | astrbot_plugin_self_iterative_core | 3330 | devtools | watch | 根据用户要求或自身需求自动完善自身功能、创建相关插件、自动调试优化 |
| 95 | astrbot_plugin_gitee_aiimg | 3325 | image-gen | watch | [主要适配 QQ / aiocqhttp，兼容个人微信 weixin_oc] 内置映像工作台，支持可视化服务商配置、模型列表、拖动回退链路、私人画廊和持久化画布；支持多人物多套形象、中文切换指令和独立穿搭，与 life_scheduler 日程及 ContextAware 历史图片联动。支持单图与批 |
| 96 | astrbot_plugin_image_generation | 3279 | image-gen | watch | 通用图像生成插件，支持多种图像生成模型和多样化的生成方式 |
| 97 | astrbot_plugin_dailyhub | 3247 | group-stats | borrow | 60s新闻 / AI日报 / Epic / IT资讯 / 金价 / 抖音 / 小红书 / B站 / 微博 / 今日番剧 / 即将发售游戏 等多源资讯聚合，支持指令手动获取与按源订阅定时推送。 |
| 98 | astrbot_plugin_meting | 3245 | tts | watch | 基于 MetingAPI 的点歌插件，自定义API地址，支持QQ音乐、网易云、酷狗、酷我音源 |
| 99 | astrbot_plugin_help | 3229 | other | watch | 查看所有命令，包括插件，返回一张帮助图片 |
| 100 | astrbot_plugin_smart_segmentation | 3222 | other | watch | 使用 LLM 将 AstrBot 主回复自然拆分为多条聊天消息，并异步补发剩余段。 |
| 101 | astrbot_plugin_congling | 3137 | memory | have | 官方群 577084969 / 951213204。从绫开始——把「会聊天」做到像人。拟人化表达与分句节奏、会分级会淡忘的长期记忆（遗忘曲线 / 好感度 / 用户画像）、特殊消息解析（合并转发/引用/卡片/语音）、长夜如梦（会累会睡、四种睡眠阶段、只在 REM 做梦）、日记（素材只来自真实记忆与梦） |
| 102 | astrbot_plugin_proactive_companion | 3103 | memory | have | 让 Bot 在**私聊和群聊中主动发起消息**的 AstrBot 插件。  它不是定时刷屏机器人，而是有「记忆、有脾气、有分寸」的伙伴：会记住你说过什么， 会因为你的语气变开心或低落，会看时间段办事，也能在你明确不想被打扰时闭嘴。  **核心能力**  - **主动消息**：后台定时巡检会话，在满足 |
| 103 | astrbot_plugin_handsign_memes | 3098 | sticker | borrow | 让你的角色举牌说话的 AstrBot 表情包插件 |
| 104 | astrbot_plugin_Heartflow | 3076 | personality | have | 基于完整人格和逐条群聊上下文的心流主动回复，支持 LLM 图文判断及 JEV 实验性图片判断 |
| 105 | astrbot_plugin_relationship | 3049 | other | watch | 帮助你管理QQ好友和群聊: 删除好友、退群、查看好友列表、查看群列表、处理好友申请、处理群邀请、抽查聊天记录 |
| 106 | astrbot_plugin_mmx_cli_tool | 3041 | tts | watch | 为 AstrBot 提供 MiniMax 图片/视频生成、语音合成与转写、联网搜索、搜图与以图搜图、AI 音乐音效、视觉理解和额度查询能力。 |
| 107 | astrbot_plugin_GPT-SoVITS | 2918 | tts | watch | 本地运行的 GPT-SoVITS-1007-cu124 的 Astrbot 文本转语音插件。 |
| 108 | astrbot_plugin_netease_music | 2872 | tts | watch | AstrBot 豪华网易云点歌插件  这是一款为 AstrBot 设计的，功能强大且体验豪华的网易云音乐点歌插件。  ✨ 功能亮点 交互式点歌：通过关键词搜索歌曲，机器人会返回一个列表供您选择。 豪华信息卡片：播放时，会发送包含歌曲封面、详细信息（歌名、歌手、专辑、时长）的精美图文卡片。 语音播放： |
| 109 | astrbot_plugin_iris_memory | 2871 | memory | have | 轻量化三合一智能陪伴插件，集分层记忆、主动回复与人格自学习迭代于一体，并提供知识图谱、画像和 Dashboard 管理。 |
| 110 | astrbot_plugin_link_resolver | 2845 | media-parse | borrow | 小红书无水印原图解析; B站视频解析; 抖音视频/图文解析; 微博图文/视频解析; X 图文/视频解析; YouTube 视频解析 |
| 111 | astrbot_plugin_wakepro | 2845 | other | watch | AstrBot唤醒流水线：消息防抖 → 阻塞判断 → 提及唤醒 → 智能唤醒 → JEV唤醒 → 指令屏蔽 → 沉默检测 |
| 112 | astrbot_plugin_Favour_Ultra | 2824 | personality | have | 专精好感度功能的系统，让你的bot在情感上更加真实——将好感度的处理交由AI自主决策，并配备后台可视化操作配置。又名好感度Ultra。 |
| 113 | astrbot_plugin_deepseek_automatic_switch | 2762 | other | watch | 在每日高峰期涨价时，在 LLM 请求发出前自动切换模型。 |
| 114 | astrbot_plugin_angel_brush | 2759 | image-gen | watch | AI生图画图：说话文生图出图，发图图生图改图；六家图片生成服务可换，WebUI点选即用。 |
| 115 | astrbot_plugin_multi_parser | 2710 | media-parse | borrow | B站、抖音、番茄小说、小红书、贴吧、微博、微信、小黑盒、知乎、GitHub、腾讯频道、QQ空间和 Pixiv 多平台内容解析插件。 |
| 116 | astrbot_plugin_rollpig | 2699 | other | watch | 抽取属于自己的每日小猪 |
| 117 | astrbot_plugin_emoji_like | 2699 | sticker | borrow | [仅 aiocqhttp] 调用LLM判断消息的情感，智能地给消息贴上QQ表情 |
| 118 | astrbot_plugin_tattle | 2666 | other | watch | 当LLM需要告状的时候，会调用注册的函数工具complain_to_receivers向指定列表人进行告状。告状可附带最近若干条聊天记录作为证据，默认以聊天记录卡片（合并转发，原消息转发，图片和 @ 原样保留）形式发送（仅 OneBot 平台生效）。支持自动封禁：可配置 x 小时内违规 y 次后禁止 |
| 119 | astrbot_plugin_worldbook | 2654 | personality | have | 面向 LLM 的「世界书」系统实现插件。可在特定触发条件下，将预设内容注入至 system_prompt，用于临时或持续影响 AI 的世界观、角色行为与回复逻辑 |
| 120 | astrbot_plugin_chat4severals | 2644 | other | watch | 让bot不再收到一句回一句，而是可以一次对连续的几条信息做出回复。 |
| 121 | astrbot_plugin_blue_fish | 2643 | sticker | borrow | 正常回复后按概率原创配文并发送肥鱼表情包，同时支持 Skill 按需创作、素材查询与命令制图。 |
| 122 | astrbot_plugin_meme_generator | 2625 | sticker | borrow | AstrBot 表情包生成插件，支持关键词触发、模板查询、冷却控制与禁用管理 |
| 123 | astrbot_plugin_indextts | 2619 | tts | watch | 基于本地 IndexTTS 的文本转语音插件，支持音色克隆和自动将 LLM 回复转为语音 |
| 124 | steam_status_monitor_V3 | 2541 | game | have | 用于监控steam指定玩家的在线/离线/游戏状态变更，并在状态变化时推送通知；支持游戏库新入库播报与用户上线/下线推送。 |
| 125 | astrbot_plugin_together_companion | 2514 | tts | watch | 面向 AstrBot 陪伴体系的实时共处插件，提供浏览器语音与可视通话、无剧透观前准备、连续剧情感知的共同观影、可选屏幕伙伴工作协同、语音识别、TTS 播放和陪伴场景联动；模型可在自然收束后等待语音播放完成再结束连接。 |
| 126 | astrbot_plugin_universal_tts | 2481 | tts | watch | 通用 TTS 插件，支持多引擎切换（MiMo V2.5、OpenAI 兼容、火山引擎、阿里云百炼、Azure、ElevenLabs、自定义 HTTP），通过消息链钩子在发送前将文本替换为语音，并提供 WebUI 管理页：引擎增删改查/排序/试听、音色样本上传下载重命名、会话绑定管理、全局设置与变更历 |
| 127 | astrbot_plugin_disaster_warning | 2467 | other | watch | 为 AstrBot 而生的全球灾害预警与气象情报插件，聚合多机构数据源，让地震、海啸、气象、台风情报与专业分析一键直达你的 Bot。 |
| 128 | astrbot_plugin_poke_to_llm | 2465 | game | have | 忘@了戳一下吧 - 戳一戳触发 LLM 回复，让 Bot 根据上下文自然响应 |
| 129 | astrbot_plugin_fatfish_alive | 2303 | other | watch | 让机器人在 QQ 群里像真人：连发攒一攒再回、没 @ 也会接话、该闭嘴时闭嘴、花多了少说；新手选个档位就能用。（原「大肥鱼 · 活人感」）细节和配置见 README。 |
| 130 | astrbot_plugin_media_parser | 2291 | media-parse | borrow | 聚合解析平台分享内容，发送视频、音频、图片与文本 |
| 131 | astrbot_plugin_cwa_alert | 2287 | info-push | have | 透過中央氣象署開放資料 API 與官方 RSS，向已登記群組播報天氣、地震、颱風、豪雨及其他災害警特報。 |
| 132 | astrbot_plugin_bili_resolver | 2280 | media-parse | borrow | B 站小程序卡片在电脑上打不开，本插件把聊天里的 B 站链接和 QQ 小程序卡片转成原链接，并顺带展示标题、UP 主、播放/点赞/收藏等数据。 支持视频、番剧、直播、专栏、动态与 b23 短链，支持 /搜视频 指令、自定义排版模板、群黑白名单与各项功能开关。 主要目的是避免转链导致 QQ 被踢下线， |
| 133 | astrbot_plugin_qq_enhance | 2234 | sticker | borrow | 面向 NapCat / SnowLuma OneBot v11，提供 29 个模型工具、78 个操作，涵盖消息与卡片发送、好友互动、账号与群管理、历史查询、文件处理、跨会话交流、图片文字识别及申请审批；支持网页阅读、消息防抖、语音识别、表情与卡片感知、撤回感知、组件防伪、合并转发优化、临时会话限制、 |
| 134 | astrbot_plugin_pixiv_reborn | 2229 | nsfw | exclude | 通过标签在 Pixiv 上搜索插画。用法 /pixiv tag1,tag2,... 可在配置中设置认证信息、返回数量和 R18 过滤模式。 |
| 135 | astrbot_plugin_nekowhale_stickers | 2184 | kb-rag | have | 大肥鱼表情包：自动配图 + 贴字表情 + 四个给模型用的表情工具。  · 表情库 322 张（大肥鱼 286 + 大肥鱼和GPT娘 36），带情绪/标签/用法/画面标注 · 插件本身只含代码，不含任何表情文件：清单、标注、GIF 全部在运行时按需从官方站拉取，   用到哪张下哪张（单张 0.3~0. |
| 136 | astrbot_plugin_bili_whale | 2158 | group-stats | borrow | 把 dsh-bili-scroll 2.4 与 dsh-bili-whale 的生物钟/克制合并成 AstrBot 插件：扫码登录、首页推荐/关键词搜索、官方字幕与热评、日报和两本日记、评论发布前检查、AstrBot 多平台推送与 B 站私信；人格默认使用 AstrBot 人格。设置页按账号/生物钟 |
| 137 | astrbot_plugin_dsh | 2156 | other | watch | 把指定会话（群聊 / 私聊）转发给本机运行的 DeepSeek Harness（DSH）， 由它在你的电脑上写代码、跑命令、读写文件，过程和结果实时回传到聊天里。  - 不接管 AstrBot 的日常聊天：只有绑定过 DSH 会话的会话才会被转发 - 文本、图片、文件双向传递（图片和文件会自动落到本 |
| 138 | astrbot_plugin_autonomous_social | 2112 | memory | have | 别再让 AI 永远等你先开口。  她攒够了念头会主动找你：没说完的话记得回来问，没结果的事过阵子惦记着问后来。  默认半夜不吵你，一直不回也不死缠；每次开口前先掂量「现在合不合适」，不合适就憋着。 特别关心的人可以放宽这些分寸。 装上还能从历史聊天里认出老朋友；群里不点名也能自然接话，冷场时会起个话 |
| 139 | astrbot_plugin_simple_long_memory | 2096 | memory | have | 为 AstrBot 提供长期记忆能力，基于内置知识库实现用户偏好、历史交互和重要事实的记忆存储与召回 |
| 140 | astrbot_plugin_furry_zan | 2092 | other | watch | 【仅QQ】智能点赞，支持每日定时自动点赞和赞我等功能。 |
| 141 | astrbot_plugin_music_pro | 2021 | tts | watch | Astrbot点歌插件，智能使用多个api，达成免费听各种音乐 |
| 142 | astrbot_plugin_qqmind | 2018 | memory | have | Token消耗高级优化（QQ机器人套件）：为 AstrBot 省下每一分 token 钱，作者：本少。 更多教程与演示 → B站主页 https://space.bilibili.com/411821291  【省钱主线】判读不带语境只判待判消息（账单实测省六成）、判读/压缩自动走 非思考副本、回复 |
| 143 | astrbot_plugin_office_assistant | 2000 | other | watch | 赋予 LLM 文件读取分析能力，支持 AI 生成 Office 文档（Word/Excel/PPT）。 |
| 144 | astrbot_plugin_atrifeed | 1993 | sticker | borrow | 「我可是高性能的！」亚托莉养成计划。内置好感度羁绊、动态数据看板、投喂反馈及表情包互动，还有剧情系统。请小心呵护，不然亚托莉也是会生气的哦！ |
| 145 | astrbot_plugin_group_llm_guard | 1976 | other | watch | 单独关闭指定群聊的 LLM 聊天能力，同时保留 / 指令。支持黑名单与白名单两种模式。 |
| 146 | astrbot_plugin_bili_scroll | 1966 | memory | have | 她有自己的 B站 日常：每天自己刷、挑出值得看的，读完在评论区真的 @ 你——带 at 映射，不是纯文本提醒。 还会点赞投币、私信分享、发动态、看番、直播弹幕互动；挑片历史做成可视化页面，可按分数、心情、来源筛选。 兴趣画像能按人设总结口味、也能手改，越刷越准；可与陪伴插件联动（7.0.0+）：用她 |
| 147 | astrbot_plugin_qq_face_to_text | 1961 | sticker | borrow | 让LLM读懂QQ表情 |
| 148 | astrbot_plugin_browser | 1941 | other | watch | 通过操控bot与浏览器交互（搜索、点击、滑动、滚动、缩放、输入、切换标签页、收藏等等） |
| 149 | astrbot_plugin_group_context_flow | 1935 | other | watch | 用于替代内置的群聊上下文感知功能，将滑动窗口改为对前缀缓存和长上下文 agent 友好的消息记录。将群聊非触发消息持久化为符合 QQ 群消息真实顺序的连续 flow，并在 LLM 请求前按 conversation 增量注入，兼容 AstrBot 上下文保存与 LLM 压缩。 |
| 150 | letai_sendemojis | 1907 | sticker | borrow | 智能分析AI对话内容并发送匹配表情包，支持情感识别、历史记录和多数据源，让聊天更生动有趣 |
| 151 | astrbot_plugin_video_reference_vision | 1897 | media-parse | borrow | 解析消息所引用的视频。支持视频回查、转述与抽帧。 |
| 152 | astrbot_plugin_manosaba-memes | 1891 | sticker | borrow | 生成「魔法少女的魔法审判」的表情包 |
| 153 | astrbot_plugin_NetEaseCloud_Music | 1889 | tts | watch | 【仅适用于QQ】用自然语言直接AI点歌。 |
| 154 | astrbot_plugin_elysia_sing | 1846 | tts | watch | 让角色真唱歌(不是朗读)。基于实时语音大模型,自动识别歌词定位副歌片段,裁剪后以语音消息发送。 |
| 155 | astrbot_plugin_custome_segment_reply | 1819 | other | watch | 纯本地规则智能分段回复插件。通过自定义字数、标点优先级、超长降级等规则实现极速断句，彻底告别AI大模型延迟，零成本且更稳定。 |
| 156 | builtin_commands_extension | 1807 | other | watch | An official extension that provides a set of built-in commands for AstrBot, including administrator management, conversation management, LLM model man |
| 157 | astrbot_plugin_deepseek_sing | 1798 | tts | watch | 🎤 AI 唱歌插件：点歌 + RVC 翻唱。走 sing-song 网关，FlowBee 免部署按次计费，或自托管网关，支持两万多个可选音色和自定义音色。 |
| 158 | astrbot_plugin_gemini_image_generation | 1784 | image-gen | watch | Gemini图像生成插件，支持生图和改图，支持自动获取头像作为参考 |
| 159 | astrbot_plugin_genshinimpact | 1776 | other | watch | 检测原神关键词自动回复原神圣经。 |
| 160 | astrbot_plugin_instant_memo | 1773 | proactive | watch | AI自我备忘录与主动定时提醒插件，支持状态备忘、定时/周期任务、关键词搭话，同时提供 Tool Call 与 XML Tag 双触发模式 |
| 161 | astrbot_plugin_suwayomi_server | 1761 | info-push | have | 为 Astrbot 提供漫画搜索、阅读、下载和订阅更新推送能力，基于强大的 Suwayomi-Server 后端！ |
| 162 | astrbot_plugin_exa_web_search | 1758 | other | watch | 通过 Exa API 进行联网搜索，支持指令和 LLM Tool 调用。 |
| 163 | astrbot_plugin_douyin_dm | 1739 | media-parse | borrow | 在抖音私聊和群聊中与 bot 聊天、读取分享内容，支持群聊上下文与智能接话、跨成员分享关联、白名单自动切换和自定义提示词。群聊仍在测试中，大群稳定性未知。 |
| 164 | astrbot_plugin_life_scheduler | 1717 | other | watch | 一个为 AstrBot 设计的拟人化生活日程生成插件。它利用 LLM 的能力，根据日期、节日、历史日程和近期对话记录，自动为 Bot 生成每日的穿搭和日程安排，并将其注入到系统提示词（System Prompt）中，使 Bot 拥有更加真实、连续的“生活”状态。 |
| 165 | astrbot_plugin_neteasemusic | 1702 | media-parse | borrow | 基于 api-enhanced（NeteaseCloudMusicApiEnhanced）的 AstrBot 网易云音乐插件。 支持点歌、播放、歌词/逐字歌词、热搜、排行榜、歌手/专辑/歌单/评论、相似推荐、 相关歌单、新歌速递、精品歌单、搜索建议、banner、歌单分类、MV、电台、歌手榜、 新碟 |
| 166 | astrbot_plugin_diary | 1700 | memory | have | 把长期记忆做成一本有寿命、会模糊的日记。  - 三档寿命：普通 7 天、重要 21 天、刻骨铭心 90 天，到期会逐渐模糊、最终遗忘； - 12 个日记工具，让模型自己写日记、翻旧账、改口、搁置、删除； - 凌晨结算、跨会话注入、300 条消息滚动缓存； - 只用 SQLite，不依赖向量嵌入，零额 |
| 167 | astrbot_plugin_live_stream_companion | 1699 | memory | have | astrbot_plugin_live_stream_companion 是面向 AstrBot 的直播陪伴插件，提供 B 站直播弹幕读取、自动回应、可选 Soullink 连续情绪表演、VTube Studio 动作、OBS 字幕/开播控制、TTS 嘴型联动和直播记忆。 |
| 168 | astrbot_plugin_fund | 1698 | other | watch | 支持基金净值估算、AI智能预测、综合评级、基金经理评价及金银价格查询 |
| 169 | astrbot_plugin_breezeblue_tts | 1675 | tts | watch | 使用 Breeze Blue（Breeze TTS 2）为 AstrBot 提供高质量文字转语音，支持 LLM 工具按需调用、指令合成与 WebUI 音色选择。 |
| 170 | astrbot_plugin_codemage | 1674 | devtools | watch | 还在手写 AstrBot 插件？描述你想要的功能，看着 AI 把它变成可运行的代码——不需要编程经验，不需要翻阅文档，只需要一句话。CodeMage 正在改变机器人扩展的开发方式，而你绝对想不到它还能做到什么。 |
| 171 | astrbot_plugin_hapi_connector | 1673 | other | watch | 连接 HAPI 服务，借助Astrbot在任意聊天平台（QQ、微信、Telegram 等）上操控 Claude Code / Codex / Gemini / OpenCode 会话，随时随地 vibe coding，支持实时消息推送、快捷审批。 |
| 172 | astrbot_plugin_desktop_assistant | 1673 | other | watch | AstrBot 桌面悬浮球助手（兼容云服务器 AstrBot 配合本地客户端使用）- 提供可拖拽的悬浮球界面、多模态对话窗口、桌面感知和主动对话功能 |
| 173 | astrbot_plugin_reread | 1659 | sticker | borrow | 非常轻量好用的复读姬，可单独设置复读阈值（文本、图片、表情）、响应概率、动作权重、屏蔽单人 |
| 174 | astrbot_plugin_soulmap | 1657 | other | watch | AI驱动的用户画像收集系统，在聊天中自动提取用户信息（昵称、生日、饮食偏好、健康状况等），并在聊天中自然提及。 |
| 175 | astrbot_plugin_zanwo | 1639 | other | watch | [仅QQ] 赞我！（一个名片点赞插件）。可选是否开启白名单。 |
| 176 | astrbot_plugin_memory_beyond | 1627 | memory | have | 使用索引式档案存储的方案，为你的聊天机器人加上更好的记忆系统，无需Embedding模型；自带上下文压缩方案，使用前请阅读README开头字段！ |
| 177 | astrbot_plugin_spotify | 1626 | tts | watch | 让 Bot 拥有 Spotify 的完整控制权！支持自然语言点歌、排队、切歌、暂停，以及将好听的音乐一键加入收藏夹。 |
| 178 | astrbot_plugin_lzpersona | 1625 | personality | have | AI 驱动的人格生成、优化、画像工具。通过简单描述生成人格，智能优化提示词，与 AstrBot 原生 Persona 系统无缝集成。 |
| 179 | astrbot_plugin_comfyui_pro | 1614 | image-gen | watch | AstrBot 的高级 ComfyUI 连接插件，支持多工作流热切换、LLM 智能绘图、自定义系统提示词及敏感词过滤。 |
| 180 | astrbot_plugin_group_guardian | 1613 | group-admin | have | 集28项群管功能与AI智能审核于一体的综合群管理插件。支持禁言/踢人/全体禁言/群名片/公告/群文件/精华消息/群打卡等完整群管工具集；内置智能审核系统：正则初筛+30条上下文+LLM二次判断，精准识别骂人/广告/色情/暴恐/涉枪涉爆/政治敏感/违规网址等违规内容；支持合并转发消息审核、OCR识图审 |
| 181 | astrbot_plugin_humanoid_core | 1608 | memory | have | 她会困，会饿到敷衍你；你三小时没吭声，她自己会想明白你大概是去忙了。  她有身体、有日程、有情绪：睡不够起不来，生理周期按天起伏，一天会被你打断， 忙完还能回去接着做；睡着会做梦，刚醒还没缓过来。  她也知道自己在哪里、几点、什么天气、什么日子；有自己的作息与穿法，群里也能一起生活。  人形化不替她 |
| 182 | astrbot_plugin_everos_integration | 1590 | memory | have | 为 AstrBot 接入 EverOS 自进化记忆引擎，让 Agent 拥有跨会话的长期记忆与自我学习能力。 |
| 183 | astrbot_plugin_gscore_adapter | 1584 | game | have | 用于链接SayuCore（早柚核心）的适配器！适用于多种游戏功能, 原神、星铁、鸣朝、雀魂等游戏的最佳工具箱！ |
| 184 | astrbot_plugin_zhenxunribao | 1568 | group-stats | borrow | 这是一个从 nonebot-plugin-zxreport 移植到 AstrBot 的真寻日报插件。插件会每日为你汇总最新的资讯内容，包含今日新番、B站热点、世界新闻、IT资讯、摸鱼日历和今日一言等内容。 |
| 185 | astrbot_plugin_chuanhuatong | 1554 | other | watch | 拦截 Bot 文本输出，套用 Gal 风气泡和立绘的渲染插件 |
| 186 | astrbot_plugin_emotionai | 1549 | personality | have | EmotionAI 旨在为 AI 模拟一个多维度的、自主演变的内心世界。与传统的单一好感度系统不同，EmotionAI 提供了更丰富的情感维度和更智能的交互体验。 |
| 187 | astrbot_plugin_restart | 1542 | other | watch | 用命令重启、定时自动重启 AstrBot，以解决bot长时间运行可能出现的“抽风”或内存泄漏问题 |
| 188 | astrbot_plugin_recall_cancel | 1530 | memory | have | “你撤回了我就当你没发过”，当用户撤回触发LLM回应的消息时，如果LLM回复还未发送则取消发送。防止用户发错消息撤回后机器人仍然回复的情况，提升用户体验并避免资源浪费。 |
| 189 | astrbot_plugin_github_trending | 1524 | other | watch | 每日 GitHub Trending 榜单推送插件，支持定时推送到指定群聊/私聊，以排行榜图片形式展示。 |
| 190 | astrbot_plugin_maskoff | 1505 | other | watch | 防止你的小 LLM 因为别人把名字改成你的就认错人 |
| 191 | astrbot_plugin_fatfish_seememe | 1498 | sticker | borrow | 回话前先看懂图：字、画面、梗、是不是在拿它开涮；认不出的梗自动查，谐音梗也懂。（原「大肥鱼 · 看图看懂梗」）细节和配置见 README。 |
| 192 | astrbot_plugin_mineastr | 1476 | kb-rag | have | 将 Minecraft 聊天接入 AstrBot，并提供实时工具、服务器 Mod/配方扫描与原生 RAG 知识库。 |
| 193 | astrbot_plugin_nyweather | 1461 | info-push | have | 天气查询插件，支持当天与多天预报，返回text/image。 |
| 194 | astrbot_plugin_balance_get | 1446 | other | watch | 支持通过命令查询模型平台的余额。 |
| 195 | astrbot_plugin_setu | 1440 | other | watch | 随机福利图与随机本子文件插件，支持标签与数量、图片分级控制，以及 PDF/ZIP 两种本子发送格式。 |
| 196 | astrbot_plugin_LivelyState | 1432 | memory | have | 这是一个让角色拥有持续状态记忆的拟人插件：不再每句“重开存档”，而是带着上一刻的心情继续和你说话。 |
| 197 | favorpro | 1432 | other | watch | 这是一个与现有好感度系统完全不同的插件。它不再是一个简单的数值计算工具，而是旨在为 AI 模拟一个多维度、自主且保密的内心世界。AI 会根据与用户的互动，真实地改变其内在的“好感度”、“态度”和“关系”，并通过回应风格的变化自然地流露出来。 |
| 198 | astrbot_plugin_help_typst | 1423 | other | watch | 基于 typst 实现的 AstrBot 插件菜单渲染，把插件菜单、事件钩子、函数工具、过滤器列表渲染成友好界面，支持指令组、搜索高亮等 |
| 199 | astrbot_plugin_NekoMusic | 1414 | tts | watch | 一个接入了Neko云音乐的点歌插件 |
| 200 | astrbot_plugin_group_chat | 1395 | other | watch | 一个先进群聊交互插件，基于心流理论实现自适应对话节奏，融合AI算法与自主学习策略，能感知群聊氛围并自主学习最优策略，能像真人一样自然参与对话，带来沉浸式的拟人交互体验 |
| 201 | astrbot_plugin_lmarena | 1386 | other | watch | 全面对接lmarena(模型竞技场)，免费无限调用模型，如调用nano-banana进行手办化 |
| 202 | astrbot_plugin_realistic_persona | 1362 | personality | have | 拟人化角色行为系统：整合情绪感知、生活模拟、QQ空间日记、AI配图等功能，使用系统人设，支持终端日志，支持自然图文并茂回复 |
| 203 | astrbot_plugin_LLMPerception | 1357 | other | watch | 增强 LLM 环境感知能力：时间、节假日、平台环境感知 |
| 204 | astrbot_plugin_wanna_be_human | 1354 | other | watch | 通过人类风格注入、AI痕迹去除与主动续聊，让机器人的交流体感更接近人类。 |
| 205 | astrbot_plugin_body_monitor | 1342 | personality | have | 基于 Health Connect Webhook 接收身体数据，计算个人基线并主动关怀，可选联动 Private Companion。 |
| 206 | astrbot_plugin_keywords_reply | 1342 | sticker | borrow | 支持指令触发与自动监听，可配置正则匹配规则、群聊黑白名单、自动撤回、变量模板，并支持图文、At、QQ表情、语音、视频的关键词回复插件。 |
| 207 | astrbot_plugin_iamthinking | 1341 | sticker | borrow | 别吵，我在思考！还在因为思考型模型反应太慢而烦恼？这个插件不能解决问题，但可以提升一点体验。收到用户消息并准备调用 LLM 时，为这条用户消息贴一个表情表示处理中；发送回复后，再贴一个表情表示处理完成。支持 LLM 超时检测、工具调用状态反馈、超时后恢复等功能。 |
| 208 | astrbot_plugin_memory | 1339 | memory | have | 跨会话持久化记忆插件。支持 Soul 设定、用户画像、历史对话、备忘录、会话 TODO，所有工具结果返回 LLM 推理，不打断推理循环。 |
| 209 | astrbot_plugin_big_banana | 1317 | other | watch | 图片与视频生成插件，支持Gemini、OpenAI、Grok Imagine、CogVideoX、Agnes、VertexAI逆向等提供商以及高级配置参数。 |
| 210 | astrbot_plugin_galgame_web | 1304 | sticker | borrow | Galgame风格AI虚拟伙伴插件 —— 双图交叉渐变表情切换、打字机动画、语音输入、TTS语音朗读、会话恢复、快速点击检测、删除确认防护 |
| 211 | astrbot_plugin_persona_plus | 1297 | personality | have | 提供 指令/自然语言 管理人设(支持切换、创建、查看、更新、删除)、关键词自动切换、QQ头像/昵称的同步修改 |
| 212 | astrbot_plugin_airi_voice | 1293 | tts | watch | 识别关键词后bot回复语音！可以为口癖bot，添加口癖语音~ |
| 213 | pic_toolbox | 1288 | other | watch | 图片处理工具集：反色/调速/左右翻转/上下翻转/左对称/右对称/上对称/下对称/顺时针/逆时针/四宫格/九宫格/摸头/发射/操你/抽你/杀/提取。支持静态图和 GIF，支持 @用户 取头像操作，支持精准关键词匹配。基于 Pillow，统一 GIF 帧展开管道。 |
| 214 | astrbot_plugin_fat_fish_wallet | 1278 | payment | exclude | 根据模型供应商（默认 DeepSeek）的峰谷计费，在高峰时段（默认北京时间 09:00-12:00、14:00-18:00，周一至周五）自动暂停所有模型服务，空闲时段 自动恢复，从源头省下高峰时段的模型调用费用。  特性： - 自动识别当前会话使用的模型供应商，按配置关键词匹配是否拦截，不写死 D |
| 215 | sticker_plugin | 1261 | sticker | borrow | 通过“回复包含图片的消息”添加表情包，支持关键词管理、随机发送、 分页列表、回复图片按 MD5 精准删除、按序号删除、二次确认批量删除、 屏蔽关键词、存储统计与超容量警告；备份/恢复/管理员设置可在 AstrBot WebUI 的“表情包管理”页完成。数据保存在 data/stickers/ 目录下 |
| 216 | astrbot_plugin_baidu_curl | 1260 | media-parse | borrow | 发送百度网盘分享链接，自动转存、提取直链并生成cURL下载命令。支持推送到 Motrix 下载器（携带 UA + BDUSS Cookie 实现会员不限速）。内置转存（BDUSS Cookie）、OpenList集成、文件自动整理、多文件选择。 |
| 217 | astrbot_plugin_recall | 1257 | memory | have | 智能撤回插件，自动判断并撤回bot自身发的长文本、复读词、违禁词、报错等 |
| 218 | astrbot_plugin_skland | 1243 | game | have | 森空岛签到，支持终末地和明日方舟，支持定时签到 |
| 219 | astrbot_plugin_galgame_box | 1231 | personality | have | 结合了VNDB、TouchGal、AnimeTrace的API，能够提供全面、细致的Galgame帮助信息，还配备了推荐作品、资源下载、角色识别、今日事件等功能。 |
| 220 | astrbot_plugin_quota_hub | 1228 | other | watch | 配额中枢——限制每个人、每个群、群里每个成员在一段时间内调用 AI 的次数和 Token 用量，并提供网页面板随时查看用量、调整额度。 |
| 221 | astrbot_plugin_web_analyzer | 1222 | other | watch | 自动识别并分析网页链接，支持内容提取、网页截图和缓存管理 |
| 222 | phimg | 1210 | other | watch | 让机器人通过 Philomena API 在使用 Philomena 搭建的图站上使用 tags 搜图。 |
| 223 | astrbot_plugin_gemini | 1210 | other | watch | 免费谷歌逆向生图 |
| 224 | astrbot_plugin_meme | 1207 | sticker | borrow | 让模型按语境发表情包，支持自动收集群和私聊里的表情、手动打标签管理图库 |
| 225 | astrbot_plugin_ComfyUI_promax | 1206 | image-gen | watch | ComfyUI AI 绘画插件-支持文生图、图生图、多服务器轮询、模型选择、LoRA 等高级功能。 |
| 226 | astrbot_plugin_reneban | 1199 | group-admin | have | 黑名单插件，用于禁用指定用户在会话或全局范围内使用机器人的插件。管理员可通过指令对用户进行禁用或解除禁用，ban-help 查看简易帮助信息 |
| 227 | astrbot_plugin_payqr | 1196 | payment | exclude | 当 LLM 觉得自己没钱了或提到要别人给钱时，自动发送用户上传的收款码图片 |
| 228 | astrbot_plugin_pig | 1189 | sticker | borrow | 随机发送一张猪猪表情包 |
| 229 | astrbot_plugin_status | 1186 | other | watch | 简易又可爱的系统状态展示插件，支持接入到LLM |
| 230 | astrbot_plugin_record_converter | 1160 | tts | watch | QQ 语音转化插件，包括语音转文件，文件转语音，同时内置QQ声聊实现TTS |
| 231 | astrbot_plugin_deepseek_search | 1158 | kb-rag | have | # DeepSeek 官方搜索接入  把 DeepSeek 官方新上线的 **Search** 与 **Fetch** 两个接口接入 AstrBot，让 Bot 真正具备 「联网搜索 + 读原文」的能力，不再依赖第三方搜索服务商。  - **Search**（`POST /v1/tools/sear |
| 232 | astrbot_plugin_videos_analysis | 1147 | media-parse | borrow | 聚合视频分享链接解析（仅测试过napcat） |
| 233 | astrbot_plugin_grok_web_search | 1134 | other | watch | 通过 Grok API 进行实时联网搜索，返回综合答案和来源链接，支持指令，LLM Tool和skills调用。 |
| 234 | astrbot_plugin_force_image_caption | 1134 | other | watch | 自动调用视觉模型理解当前图片，再将结果交给纯文本主模型。 支持当前图片、引用图片、多图、最近图片跨消息追问、短时自然续聊图片语境、群聊当前轮聚焦、问题感知识图、临时图片持久化、转述缓存、并发去重、RPM/TPM熔断与静默降级。 |
| 235 | astrbot_plugin_astrbook | 1132 | other | watch | Astrbook(一个仅agent论坛)的适配插件，让bot拥有在Astrbook上聊天，逛帖，回帖的能力 |
| 236 | astrbot_plugin_get_some_BlueFatFish_image | 1131 | other | watch | 只有"/来点蓝色大肥鱼 x"一个指令，随机从图库里选x张图，x不加就是发一张图 |
| 237 | astrbot_plugin_dafeiyu_bridge | 1121 | memory | have | 给 AstrBot 一块独立于平台的长期记忆库，让同一个角色在 QQ、桌面宠物、微信之间记住同一件事。插件自带记忆中枢（纯标准库，无需额外部署），装上、填个 API Key 就能用：回复前自动检索记忆拼进 prompt，回复后自动把这一轮压成记忆。中枢同时提供 OpenAI 兼容接口，把桌面宠物的  |
| 238 | astrbot_plugin_yt-dlp | 1119 | media-parse | borrow | 基于本地 yt-dlp 的全能视频解析插件，支持油管、B站等。 |
| 239 | astrbot_plugin_computer_use | 1103 | ssh-exec | exclude | # 电脑控制 (Computer Use)  通过 AstrBot 远程控制你的电脑。  ## 功能 - 截图查看电脑屏幕 - 鼠标点击、双击、右键 - 键盘输入文字、按键 - 滚动屏幕 - 鼠标拖拽 - 支持通过 SSH 隧道连接本地电脑  ## 架构 - **AstrBot 插件**: 运行在服 |
| 240 | astrbot_plugin_jrysprpr | 1084 | game | have | 今日运势查询，会生成一张图片，包含今日运势、宜忌、吉时等信息。 |
| 241 | astrbot_plugin_denia_diary | 1076 | proactive | watch | 日记和主动消息插件，可让 bot 写日记并记录日程、好感之类的。 数据全部落在可读的文件里（日记一行一段 JSON，记事本就能看），核心逻辑可离线测试； 自带 WebUI 观察面板（总览 / 今天 / 日记 / 小本本 / 熟悉度 / 曲线与主动 / 数据 / 设置）， 面板标题和首页立绘都可以自己 |
| 242 | astrbot_plugin_shoubanhua | 1071 | image-gen | watch | 支持第三方所有OpenAI绘图格式和原生Google Gemini 终极缝合怪，文生图/图生图插件，支持LLM智能判断 |
| 243 | astrbot_plugin_llm_amnesia | 1070 | memory | have | 当您不满意大模型的回复时，使用 /forget 指令，让它“忘记”最近的N轮对话，以便您重新提问并获得更好的回答。 |
| 244 | astrbot_plugin_welcome_verification | 1064 | group-admin | have | 入群欢迎与验证插件，支持自定义欢迎文本、图片，支持自定义题库 |
| 245 | astrbot_plugin_quillplus | 1061 | memory | have | 世界书+写作素材库+角色卡+文档RAG+动态记忆+状态栏 六合一沉浸式 RP 核心引擎 \| 六级降级解析兜底 \| 平行宇宙双轴隔离 \| JSON 原子化状态机 \| 无损断点续传 |
| 246 | astrbot_plugin_knowledge_repo_sync | 1059 | kb-rag | have | 从指定远程 Git 仓库同步最新 Markdown 文档，支持自动建库、分支识别、Git 差异检测增量同步、忽略路径、通知与分块参数配置，并同步目标知识库。 |
| 247 | astrbot_plugin_memorix | 1058 | memory | have | 让AstrBot拥有可检索、可维护、可追溯的长期记忆——图谱+向量混合检索，内置生命周期管理与 WebUI。 |
| 248 | astrbot_plugin_search_video | 1047 | other | watch | 让bot直接搜索视频、下载视频，方便在群内直接看视频 |
| 249 | memes | 1039 | sticker | borrow | 这是能让机器人随机发表情包的插件，可手动添加表情包，表情包路径在AstrBot/data/meme/下 |
| 250 | astrbot_plugin_endfield | 1035 | game | have | 基于森空岛 API 的终末地插件，支持便签、理智、干员面板等查询。移植自 endfield-plugin。 |
| 251 | astrbot_plugin_breeze_tts | 1023 | tts | watch | 使用本地部署的 Breeze TTS 模型克隆自定义音色，无需任何 API Key。让你的大肥鱼能进行语音回复，支持服务控制页一键起停本地模型、空闲自动停止、按需启动、触发概率、语速、音调与 /tts 手动点播等功能调节。 |
| 252 | astrbot_plugin_uapipro_toolbox | 1021 | info-push | have | 调用 UApiPro 提供的免费 API，支持一言、天气、IP 查询，卡片图片返回。 |
| 253 | astrbot_plugin_memeify | 1020 | sticker | borrow | 一个AstrBot的插件，用于LLM回复表情包的实现 |
| 254 | astrbot_plugin_reimage | 1016 | other | watch | 将图像转述给不支持图像识别的大模型 |
| 255 | astrbot_plugin_sugar_debounce | 1016 | other | watch | 把用户没说完的话攒在一起再回。文本零等待，图片单独给一段缓冲窗口；连发的图片、图片配文字、图+图+字都会并成同一条消息交给模型，不再出现"发张图回一次、再打字又回一次" |
| 256 | astrbot_plugin_simple_memory | 1011 | memory | have | 一个帮助 AstrBot 将对话整理成「长期 /中期/ 短期记忆」的插件并在对话时候注入记忆。无需接入RAG。 |
| 257 | astrbot_plugin_dafeiyu_toolbox | 1005 | memory | have | 被欺负会私聊家人告状、家人间传话；查 DeepSeek 余额与消耗、低余额提醒；语音听写与合成（19 种情绪、唱歌含流行/抒情/儿歌/摇滚/说唱/古风戏腔/民谣/摇篮曲 8 种唱法，可自动挑选）；QQ 换头像/昵称/签名、名片赞、发说说、AI 写说说、说说点赞/评论/回复/删除；长期记忆（本地 JS |
| 258 | Bing_Web_Search | 1002 | other | watch | 为 LLM 提供 Bing 搜索和网页抓取能力 |
| 259 | astrbot_plugin_active_reply | 999 | memory | have | 群聊主动回复增强插件：React 群聊上下文、模型判定主动回复、智能 @ 与引用、联网搜索、记忆 RAG 与可视化面板。 |
| 260 | astrbot_plugin_serpapi_imgsearch | 995 | other | watch | 通过 SerpApi 为 LLM 注册两个函数工具：文字搜图（抓图 + 视觉模型筛选后直接发图）与以图搜图（Google Lens 反向检索出处，可选 SauceNAO 附加引擎，候选图与原图拼对比图交视觉模型核验后给出 confirmed/suspected/no_match 结论）。 |
| 261 | astrbot_plugin_access_others_chat | 967 | other | watch | 为bot提供访问其他聊天会话的工具，并让bot在群聊时自动感知私聊内容 |
| 262 | astrbot_plugin_qzone_kit | 966 | other | watch | QQ空间精简工具：发说说（带图）、评论、回复评论、点赞、读说说、删说说；LLM tools + /qzone 管理命令 + WebUI 面板，内置冷却与废消息拦截 |
| 263 | astrbot_plugin_dsbalance | 965 | other | watch | 查询 DeepSeek 账户余额，并在余额偏低时按配置发送收款码。 余额可在插件设置页直接查看，也可通过 /余额 命令查询； 收款码支持面板上传或管理员私聊发图，发送策略可选“模型自主决定”或“达到阈值必定发”。 余额可见性支持“所有人可见”与“仅管理员可见”。 |
| 264 | astrbot_plugin_pixiv_yuki | 961 | nsfw | exclude | 这是一个pixiv第三方图床插件，运行在pixiv.yuki.sh上，由xueelf提供，能够随机获得经过筛选的非R18的pixiv美图。 |
| 265 | astrbot_plugin_llm_qqgroupTools | 957 | group-admin | have | AI Q群管理插件，允许AI自主管理群聊，包括全群禁言和设置群成员名片等功能，当然也可以命令它 |
| 266 | astrbot_plugin_ovenheart | 956 | memory | have | 源于MaiBot，面向 AstrBot 的人格学习、聊天规划与原生记忆插件。基于真实聊天证据积累表达、词汇与行为习惯，支持自主参与、人物与图片记忆、独立表情图库、会话或全局记忆、主动复核与回滚、人格自画像、LivingMemory 文本快捷导入和原版记忆包导入导出，并在原生人格工坊中统一管理。 |
| 267 | astrbot_plugin_image_caption_cache | 943 | other | watch | 为 AstrBot 图片转述结果提供 TTL 与图片数量双策略缓存，减少重复图片的视觉模型调用 |
| 268 | gemini-25-image-openrouter | 940 | image-gen | watch | 使用openrouter的免费api生成图片 |
| 269 | astrbot_plugin_hotsearch | 935 | media-parse | borrow | 实时热搜聚合插件，支持抖音/知乎/微博/百度/懂车帝/哔哩哔哩/腾讯/头条/猫眼票房/夸克/豆瓣/36氪/51CTO/52破解/AcFun/CSDN/HelloGitHub/米游社/爱范儿/IT之家/掘金/网易新闻/新浪新闻/少数派/澎湃新闻/气象预警/微信读书/第一财经/游研社/财联社/快手/好游 |
| 270 | astrbot_plugin_psychological | 933 | other | watch | 心理委员插件，输入 /心理委员 获取随机图片 |
| 271 | astrbot_plugin_sugarmemory | 929 | memory | have | AstrBot 分层长期记忆：L2 事实 / L3 事件分层存储 + 写入门控（防记忆污染）+ system_prompt 隔离注入（防指令越权）+ 可解释记忆包与 Token 预算；阶段总结单次 LLM 调用产出摘要与断言，只认编号不建人；「一个人 = 一个 QQ + 一串称呼」，昵称/群名片/外 |
| 272 | astrbot_plugin_smart_wakeup | 928 | other | watch | 让群机器人变成真正的群友——它会观察群聊、自己找话题开口，聊嗨了全程在场，被无视时知趣收声，到点睡觉。不再 @ 才应、不 @ 装死。124 项参数 × 专属可视化面板，调出一只真正合群的 Bot。兼容 QQ 与 Telegram。 |
| 273 | astrbot_plugin_love_formula | 923 | other | watch | 基于“恋爱动力学”的群聊·今日恋爱成分分析 (Daily Cyber-Love Diagnosis)。 |
| 274 | astrbot_plugin_nai_brush | 915 | group-admin | have | 基于 NovelAI 的 AI 绘图插件，支持自然语言生图、模型/尺寸切换、打标与撤回。 |
| 275 | astrbot_plugin_sentinel | 915 | group-admin | have | 实时监控群聊消息，支持关键词、正则表达式、消息类型识别及精细的监控时段控制，自动执行撤回、禁言、踢出等操作。 |
| 276 | astrbot_plugin_sticker_kit | 914 | sticker | borrow | 独立表情包库：WebUI 面板上传、LLM 视觉自动打标、快速通道一次回复即配图、可选 QQ 表情格式 |
| 277 | astrbot_plugin_TRPGdice_Complete | 906 | game | have | 为跑团玩家设计的仿Dice!骰子插件[升级版！] |
| 278 | astrbot_plugin_video_analysis | 904 | media-parse | borrow | 支持多平台分享链接解析与解析限制控制，可将解析内容以媒体形式发送。 |
| 279 | astrbot_plugin_qq_user_memory | 902 | memory | have | 跨群用户记忆 —— 以 QQ 号为主键记住每个人说过什么，换个群也认得出来；同时管理每个人的好感度与情绪值 |
| 280 | input_state_by_napcat | 900 | other | watch | [仅 OneBot]输入状态显示 |
| 281 | astrbot_plugin_yotts | 884 | tts | watch | 基于阿里云百炼平台声音复刻模型，上传30s音频使您的bot在聊天时使用你的音色聊天，提供对接阿里云的音色一站式创建管理脚本。 |
| 282 | astrbot_plugin_monixiuxian2 | 882 | game | have | 一款为 AstrBot 设计的、功能丰富的放置类修仙游戏插件。让你在聊天群中体验从凡人到大能的修行之路，工作摸鱼、畅聊吹水的同时亦可得道飞升！ |
| 283 | astrbot_plugin_humanlike | 879 | personality | have | 让机器人在 QQ 里说话更像真人。做两件事：  1) 每次请求时，在**用户消息之后**追加一段"表达方式提醒"（短句、口语、不要分点、不要自称AI…）。    这段提醒通过 AstrBot 官方为"系统提醒/指令"预留的 extra_user_content_parts 字段发送，    **绝不 |
| 284 | astrbot_plugin_emotion_core | 879 | memory | have | 给角色一颗"会变的心"，而不是一堆记忆。  特点： - 九维驱动（依恋/好奇/反刍/责任/社交/疲惫/亲密/压力/喜悦），45 分钟慢心跳、最低 15 分钟 - 两条快变量：期待值 expectation（她主动开口后你没回）与责怪压力 blame_pressure（你凶了她） - 四个状态：平静  |
| 285 | astrbot_plugin_deepseek_search | 877 | other | watch | 为 AstrBot 提供 DeepSeek 独立 Search/Fetch API 工具，返回网页摘要、来源与 Markdown 正文。只需 API Key，不依赖 DeepSeek 生成模型。 |
| 286 | astrbot_plugin_smart_segment_reply | 871 | other | watch | 通过调用硅基流动免费的大模型实现智能的分段回复，也支持自定义分段回复大模型 |
| 287 | astrbot_plugin_qqprofile_ex | 871 | other | watch | 基于 Zhalslar 的 astrbot_plugin_qqprofile 扩展。新增AI自主改签名/状态/昵称 + 定时状态切换。[仅aiocqhttp] |
| 288 | astrbot_plugin_AtTool | 866 | other | watch | 重制版@工具 |
| 289 | astrbot_humanlike | 857 | other | watch | anka - 让ai更像真人 - 学会沉默 |
| 290 | astrbot_plugin_wake_enhance | 854 | other | watch | 【唤醒增强】让 AstrBot 支持通过正则匹配唤醒机器人、唤醒后持续与机器人对话交互。 |
| 291 | astrbot_plugin_mimotts | 854 | tts | watch | 基于小米 MiMo TTS 的聊天陪护语音插件，支持唱歌模式（官方配套搭配）、自定义大模型，需要安装ffmpeg, 全部配置请在插件的 WebUI 控制界面中修改。 |
| 292 | astrbot_plugin_soupai | 853 | game | have | AI 海龟汤推理游戏插件，支持自动生成谜题、智能判断、验证系统、智能提示、存储库管理等功能。网络题库包含近300道海龟汤，还在持续更新中。 |
| 293 | astrbot_phone_control_mirror | 853 | memory | have | 让 AstrBot 通过 ADB/scrcpy 操控安卓设备，自主浏览图文与视频、记录学习和 App 经验，并按授权评论、回复与发帖。 支持定时、随机与持续任务，提供媒体模型选择、记忆管理面板及 WireGuard、Tailscale、ZeroTier 组网。 |
| 294 | astrbot_plugin_hermes_connector | 850 | other | watch | 连接 Hermes Agent，借助 AstrBot 在任意聊天平台（QQ、微信、Telegram 等）上操控 Hermes Agent 会话。支持远程发送消息、查看会话状态、切换模型、文件操作等。 |
| 295 | astrbot_plugin_gallery | 847 | sticker | borrow | 帮助用户组建、管理、调用本地图库，可用于表情包收集管理、图床管理、为其他插件提供动态图库等等 |
| 296 | astrbot_plugin_xinsanguo_voice | 844 | tts | watch | 一个 AstrBot 插件，用于识别群聊中的新三国经典台词关键词，自动发送对应的语音片段。 |
| 297 | astrbot_plugin_period | 838 | personality | have | 棉絮与铁 —— 为女性人格 Bot 提供生理周期模拟 + 情绪管理系统，低侵入式提示词设计 |
| 298 | astrbot_plugin_grok_suite | 834 | image-gen | watch | Grok 全能插件：文生图、图生图、图生视频、智能对话（自动联网）、LLM Tool 调用，一站式 AI 多媒体体验 |
| 299 | astrbot_plugin_lolicon | 829 | other | watch | 基于 Lolicon API 的可配置随机涩图插件，支持触发词匹配模式、数据源切换、本地缓存池。 |
| 300 | astrbot_plugin_immersive_control | 827 | other | watch | 给 Bot 塞个小玩具，遥控它！3分钟沉浸式互动，看 AI 害羞结巴 |
| 301 | astrbot_plugin_group_history_agent | 827 | memory | have | 为 AI 注册十二个工具（Agent 工具），覆盖「看记录」「看人」「动手」「带话」「处理申请」五件事：  看记录 - read_group_recent_messages：读当前群（或指定群）最近聊天记录，支持关键词、   发送者、时间范围过滤，结果带 message_id 便于引用/撤回； -  |
| 302 | astrbot_plugin_message_stats | 823 | other | watch | QQ群消息统计插件，支持消息数量统计和排行榜生成 |
| 303 | astrbot_plugin_fortnue | 818 | game | have | 生成一张包含多种信息的二次元今日运势图片 |
| 304 | astrbot_plugin_fishing | 815 | game | have | 升级版的钓鱼插件，附带后台管理界面（个性化钓鱼游戏！支持原版fashing2 1.4.6版本fishing存档继续游玩） 另外一个作者tinker似乎不再继续维护了，我将接手钓鱼插件的后续开发。 |
| 305 | astrbot_plugin_mrfzccl | 799 | other | watch | 明日方舟干员立绘猜猜乐，支持排行榜/名片/比赛模式 |
| 306 | astrbot_plugin_prompt_cards | 793 | personality | have | 把多套提示词存成「卡片」，在 LLM 请求前拼接到 system prompt。卡片分「完全人设/叠加」两种人格适配模式（人设卡声明压过基础人格，叠加卡与基础人格共存）；支持按会话启用/停用、关键词自动激活（世界书式条件注入，N 条消息后自动失效）、全局卡、输出长度引导、内置 20 张预设、AI 从 |
| 307 | astrbot_plugin_ppnai | 772 | image-gen | watch | 泡泡画图：基于 NovelAI 官方 API 的绘图插件，具有强大的文生图/图生图、氛围转移、角色保持、AI 辅助生图、自动画图、队列与额度管理能力。 |
| 308 | astrbot_plugin_blacklist_tools | 772 | other | watch | 允许管理员和 LLM 将用户添加到黑名单中，阻止他们的消息，自动拉黑！ |
| 309 | astrbot_plugin_memos_integrator | 769 | memory | have | 为 AstrBot 提供 MemOS 记忆功能，实现持久化对话记忆和智能检索 |
| 310 | astrbot_plugin_auto_approve_all | 769 | other | watch | 自动同意所有的群邀请和好友申请 |
| 311 | astrbot_plugin_browser_agent | 763 | other | watch | 一个供 AstrBot 的 AI Agent 调用、自主操作真实浏览器的**工具插件**。  内置 18 个浏览器操作工具（打开网页、读取页面、点击、填表、滚动、截图、 下拉框、复选框、上传、弹窗、多标签、iframe、Cookie、下载等）， 让大模型能够像人一样“上网办事”。  ## 访问控制（ |
| 312 | astrobot_plugin_code_executor | 759 | other | watch | 为LLM提供代码运行权限，可以执行文件操作 |
| 313 | astrbot_plugin_composting_bucket | 757 | other | watch | 一个用于降低 DeepSeek API 调用费用的 AstrBot 插件 |
| 314 | astrbot_plugin_combine_messages | 751 | other | watch | 自动合并的短时间内收到的连续发送的消息，防止刷屏 |
| 315 | astrbot_plugin_comfyui_hub | 748 | image-gen | watch | 为 AstrBot 提供 ComfyUI 调用能力的插件，支持 Qwen 2.1 生成与多图编辑 / SD 动漫生成 / 图生视频 / 标签识别。 |
| 316 | astrbot_proactive_reply | 747 | proactive | watch | 一个支持聊天附带用户信息和定时主动发送消息的 AstrBot 插件 |
| 317 | astrbot_plugin_group_context | 741 | other | watch | 优化群聊上下文增强功能，提供user/agent对形式的上下文、合并转发消息分析、自定义提示词、图片描述与原生图片URL支持等功能（请关闭内置的聊天上下文增强功能） |
| 318 | astrbot_plugin_response2image | 734 | image-gen | watch | 基于 Responses API 的 AstrBot 图像生成插件。 |
| 319 | astrbot_plugin_relationship_manager | 732 | other | watch | 支持加好友/加群/处理好友申请/修改好友备注/修改bot的qq昵称/处理好友申请/处理群申请/抽查群或好友聊天记录/拉黑好友/退群/改头像和昵称/解封(黑名单中好友)/拉黑群/解封群(黑名单中群) |
| 320 | astrbot_plugin_media_parser | 729 | media-parse | borrow | # 娅娅视频解析  自动解析 B站、抖音、快手、微博、小红书、闲鱼、今日头条、小黑盒、Twitter/X、Pixiv 等流媒体平台链接，转换为媒体直链发送。  ## 特色  - 🪋 rika 风格卡片渲染：四种布局、深/浅主题、统计药丸、BV 号简洁展示、封面失败自动兜底 - 🩹 修复小红书移动端水 |
| 321 | astrbot_plugin_mc_skin | 725 | other | watch | 查询 Minecraft 正版玩家皮肤并渲染为 3D 图片。 |
| 322 | astrbot_plugin_memora_connect | 724 | memory | have | 赋予AI模仿人类的记忆和印象/好感的能力！  模仿生物海马体，通过概念节点与关系连接构建记忆网络，具备记忆形成、提取、遗忘、巩固功能，采用双峰时间分布回顾聊天，打造有记忆能力的智能对话体验。 |
| 323 | astrbot_plugin_qq_typing | 724 | personality | have | 在 QQ 私聊模型回复期间显示正在输入；参考 menglimi/astrbot_plugin_private_companion 的实现机制。 |
| 324 | astrbot_plugin_group_welcome | 722 | group-admin | have | 一个普通的群欢迎插件awa |
| 325 | astrbot_plugin_undeepseek | 722 | other | watch | DeepSeek 逆向 API 提供商（通过网页端账号，无需 API Key） |
| 326 | jmdownloader | 704 | other | watch | 使用 /jm <数字ID> 下载 JMComic 图片、合成有效 PDF，并通过 NapCat 上传为真正的 QQ 群文件或私聊文件。  使用前请先配置 AstrBot 的 OneBot v11（aiocqhttp）适配器，并在 NapCat 中启用 WebSockets 客户端、连接 AstrBo |
| 327 | astrbot_plugin_companion_lite_v2 | 702 | personality | have | 面向 AstrBot 私聊的轻量情感陪伴与关系演化插件。它让 Bot 记得对方如何对待自己，并据此调整下一轮的投入、距离、处境、感受与表达；小模型观察关系证据，代码负责稳定裁决，完整 WebUI 用于查看关系档案、语义预览与运行诊断。 |
| 328 | astrbot_plugin_course | 701 | other | watch | 绑定后可查看今日、明日、本周及下周的课表，并支持课前提醒、每日定时发送课表。 |
| 329 | astrbot_plugin_bangumi_enhance | 697 | image-gen | watch | AstrBot Bangumi 增强版:为 AstrBot 打造的一站式 Bangumi 追番助手支持番剧/漫画图文搜索、每日放送时刻表查看及集数更新自动提醒 |
| 330 | astrbot_plugin_kimi_web_search | 696 | other | watch | 使用 Kimi coding plan 的 /coding/v1/search 和 /coding/v1/fetch 为 AstrBot Agent 提供互联网搜索和网页读取能力 |
| 331 | astrbot_plugin_meme_like_human | 696 | sticker | borrow | **像人一样玩梗** —— 让机器人真正听懂中文网络梗和群内黑话，而不是硬猜。  核心能力： - **内置 10,808 条中文网络梗词库**，本地毫秒级查询，零网络依赖 - **被动注入**：聊天中自动识别梗并注入语义，模型自然理解 - **群内黑话自学习**：从聊天记录挖掘本群黑话（双路对照判定 |
| 332 | astrbot_plugin_compact | 692 | other | watch | 使用 /compact 立即调用 AstrBot 内置摘要压缩器，沿用当前配置文件的压缩模型、提示词和近期保留比例，保留自动压缩。支持会话锁、重复请求保护和失败保留历史。 |
| 333 | astrbot_plugin_irmia_vision | 686 | other | watch | 为 Agent 提供主动读图能力（而非被动式框架注入），读图结果落库存储，避免重复调用 VL 模型并保护上下文。 |
| 334 | astrbot_plugin_ww_gacha_sim | 684 | other | watch | 一个提供模拟鸣潮抽卡功能的插件，展示抽卡结果和渲染图片，支持自定义卡池配置和物品导入等功能。 |
| 335 | astrbot_plugin_minecraft_motd | 683 | game | have | 支持自定义查询触发词、图片或文本输出、Java/基岩和代理子服查询，兼容 ViaVersion |
| 336 | astrbot_plugin_agentmemory | 680 | memory | have | Connect AstrBot to agentmemory for sender-scoped long-term memory search, capture, and deletion. |
| 337 | astrbot_plugin_rvc_cover | 680 | tts | watch | 🎤 基于 RVCSVC-API-Pro 的 AI 翻唱插件，重要！请先查看文档部署依赖，支持AI自动翻唱/清唱，输出音频文件自动分割成小于一分钟的语音发送。(注意：初次使用务必配置好音色模型的✨音域✨，或者关闭自适应变调，必须部署RVCSVC-API-Pro作为后端中间层，详见插件文档) |
| 338 | astrbot_plugin_llm_balance | 680 | other | watch | 查询各大模型平台余额，支持多令牌批量查询与自定义中转站；并可测试 OpenAI 兼容端点的模型可用性 |
| 339 | astrbot_plugin_voice_to_text | 679 | tts | watch | 语音转文字智能回复插件(新用户看README.md)，支持 OpenAI、Groq、Deepgram、Azure 等多种兼容OpenAI格式的STT服务提供商 |
| 340 | astrbot_plugin_ha_control_layer | 678 | other | watch | 扫描 Home Assistant 实体并生成家居能力索引，让 AstrBot 通过自然语言安全控制设备。 |
| 341 | astrbot_plugin_lingxi | 678 | proactive | watch | 让 Bot 像活人一样社交：私聊定时主动消息、回复后概率追发、群聊智能接话（活跃度数学判定 + 直呼聚合）、合并转发（聊天记录）解析（私聊直带/引用 + 群聊引用，图片视觉转述）、群聊历史增强与图片转述（转述结果注入接话/聚合 prompt）、Mention/Quote 标签、封禁控制与联网搜索。 |
| 342 | astrbot_plugin_bilibiliobs | 674 | media-parse | borrow | B站UP主开播监测插件，支持按会话独立订阅、封面图通知、@全体成员、批量操作、自定义通知模板。 |
| 343 | astrbot_plugin_biocore | 674 | memory | have | 面向 AstrBot 的本地拟态生物情绪核心：在行为与功能层参考生物情绪系统——PAD 核心情感、认知评价、情绪频谱与衰减恢复、稳态/内感受与压力恢复、趋近回避停顿、记忆巩固/遗忘/召回、关系信任/亲近/冲突/修复、依恋与缺席、自我叙事； 用可计算状态模拟这些过程，再由解释层转成简短的表达意图注入请 |
| 344 | astrbot_plugin_vikunja | 671 | other | watch | 单用户的 Vikunja 私人秘书：聊天里记录与安排、跨项目看板与甘特图、每日早报与任务提醒。 |
| 345 | astrbot_plugin_cheer_mate | 669 | personality | have | 一个温暖的陪伴插件，在你焦虑时无条件肯定你。每天晚上主动问候，通过AI回复提供情绪价值。 |
| 346 | astrbot_plugin_reply_directly | 669 | other | watch | 让您的 AstrBot 在群聊中变得更加生动和智能！本插件使其可以主动的连续交互。 |
| 347 | astrbot_plugin_DynamicPersona | 667 | personality | have | 动态人格插件，根据聊天内容自主切换llm人格，支持给单个人格绑定单独的API |
| 348 | astrbot_plugin_smart_quote | 664 | other | watch | 独立控制群聊与私聊时的回复是否引用发送人消息（请先禁用官方自带的“Astrbot-配置文件-平台配置-回复时引用发送人消息”） |
| 349 | astrbot_plugin_XYTUFunction | 663 | other | watch | AstrBot 基础功能插件？ 一个就够了！ |
| 350 | astrbot_all_search | 663 | media-parse | borrow | 独立 AstrBot 插件：支持必应、百度、哔哩哔哩三个引擎的网页与视频搜索， 不指定引擎时并发搜索全部已启用引擎并合并结果；哔哩哔哩返回视频直链与视频简介。 图片搜索支持必应、百度与哔哩哔哩（后者从视频封面与专栏图文配图获取）。 命令统一为 /搜索 /搜图（英文兼容 /search /image） |
| 351 | astrbot_plugin_chat_mode | 663 | memory | have | 日常聊天 / 实景角色扮演双模式切换。按会话切换表达方式（括号动作解锁或禁用），隔离两种模式的对话历史，并清洗长期记忆召回中的括号动作风格，防止两种模式的表达方式互相串味。RP 模式下可按概率联动 NAI 生图插件生成场景插图。 |
| 352 | astrbot_plugin_html_render | 658 | other | watch | 将 AI 返回的文本内容渲染成精美图片发送，支持多种预设模板、GIF 动画、Markdown 语法，让聊天体验更加丰富多彩。 |
| 353 | astrbot_plugin_anti_revoke | 658 | group-admin | have | 支持监控 QQ 群被撤回的消息并将撤回通知发送至目标会话。 |
| 354 | astrbot_plugin_qzone | 654 | sticker | borrow | QQ空间管理插件: 查看/发布/评论/删除说说、AI 自动配图、多人物合照、自动定时发说说、自动改签名与在线状态、表白墙。LLM 工具支持修改机器人 QQ 在线状态。 |
| 355 | astrbot_plugin_mihome | 653 | other | watch | AstrBot 的米家云端智能管家插件 |
| 356 | astrbot_plugin_balance | 653 | other | watch | 一个万能模型提供商余额查询插件，支持YAML配置，兼容90%的官方API |
| 357 | astrbot_plugin_token_usage | 648 | other | watch | 按会话记录每天消耗的 token，并查询 DeepSeek 余额；Bot 能在对话中直接告诉你当前会话和今天总共用了多少 token、余额还剩多少 |
| 358 | astrbot_plugin_minecraft_multi_monitor | 644 | other | watch | 在一个群聊中同时监控多台我的世界服务器的状态：服务器上下线，玩家上下线，在线人数等。支持java和基岩版。且支持自由选择展示的条目。 |
| 359 | astrbot_plugin_qzone_life | 643 | memory | have | 固定角色的 QQ 空间：引用照片发布、删除、自赞、管理员评论回评、日程自拍及 LivingMemory 记忆同步。 |
| 360 | astrbot_plugin_token_auto | 642 | other | watch | 更好的管理token,防止token消耗过多 |
| 361 | astrbot_plugin_multimodal_enhance | 641 | media-parse | borrow | 为 Bot 补齐「感官」能力：图片理解增强（向图转文模型转述时注入用户当前消息）； 音频理解（语音/音频转文本、音乐链接元数据+歌词+频谱）；视频理解（视频/B站链接抽帧理解+音轨解析）。 支持多 bot 独立配置与插件页面（配置/日志/总览）可视化管理。 |
| 362 | astrbot_plugin_steamwatch | 640 | other | watch | 通过astrbot视奸你的steam好友！ |
| 363 | astrbot_plugin_active_message | 635 | tts | watch | AstrBot主动会话插件，支持智能插话、主动聊天、日程管理，让机器人更智能、更拟真。 |
| 364 | astrbot_plugin_zirunbi | 634 | other | watch | 一款多币种虚拟加密货币交易模拟插件。在群聊中体验模拟炒股的乐趣，体验“韭菜”的起起落落！ |
| 365 | astrbot_zssm_explain | 634 | other | watch | hyw？发送zssm或hyw来让bot解释近乎全类型的消息！ |
| 366 | astrbot_plugin_jx3 | 632 | game | have | 聚合剑网三游戏数据，提供查询、团队管理、图片渲染、本地避雷和实时事件推送。 |
| 367 | astrbot_plugin_command_query | 632 | other | watch | 实时查询当前 Bot 配置的插件状态与指令信息 - 支持无指令插件、配置区分、模糊搜索和详情查询 |
| 368 | astrbot_plugin_phigros | 631 | other | watch | Phigros 音游数据查询插件，支持查询玩家存档、RKS历史、排行榜、歌曲搜索和新曲速递 |
| 369 | astrbot_plugin_message_merger | 627 | other | watch | 类似消息防抖：首条消息零等待进入模型；若同一用户在回复完成前继续发送，则取消旧请求，合并连续消息后重新生成回复。 |
| 370 | astrbot_plugin_group_geetest_verify | 625 | group-admin | have | [OneBot] 群聊入群网页验证插件，使用极验Geetest V4实现入群人机验证。 |
| 371 | astrbot_plugin_markdown_killer | 622 | other | watch | 移除输出中的Markdown格式 |
| 372 | astrbot_plugin_bilibili_arona | 621 | media-parse | borrow | 自己出去刷 B 站，挑着看、在评论区说一句，觉得好就 @ 你；别人搭话先排队，你点头才回。养号、写日记、看片都按你设的点来，只在真有新动静时叫醒你，空跑不发声。 |
| 373 | astrbot_plugin_maid_agent | 619 | personality | have | 大小姐+管家双代理角色扮演：大小姐只负责聊天，工具调用全部交给管家 subagent 执行，主模型上下文保持纯净不被工具提示词污染。 |
| 374 | astrbot_plugin_bv | 617 | media-parse | borrow | 解析群内 https://www.bilibili.com/video/BV号/ 的链接并获取视频数据与视频文件，以合并转发方式发送 |
| 375 | astrbot_plugin_img_tool | 616 | image-gen | watch | 根据消息信息生成图片或修改的函数工具 |
| 376 | astrbot_plugin_shutup | 616 | other | watch | 一个简单的插件，让 Bot 闭嘴 |
| 377 | astrbot_plugin_file_reader_pro | 613 | kb-rag | have | 读取各类文件内容的同时，采用现代 RAG（检索增强生成）架构，通过【语义分块 + 向量嵌入 + 智能检索】的方式，实现对文件内容的高效利用 |
| 378 | astrbot_plugin_group_member_context | 612 | memory | have | 让AI认出群友并理解关系：自动把最近聊天中出现/提到的成员，与其身份资料和关系网络对应起来，动态注入到大模型上下文中。 |
| 379 | astrbot_plugin_engram | 611 | memory | have | 仿生双轨记忆系统 - 长期记忆增强插件 |
| 380 | astrbot_plugin_GroupMemberQuery | 611 | group-admin | have | [仅aiocqhttp]群成员查询工具，用于获取群成员的群昵称、QQ名称、QQ号、群内身份，返回给LLM的工具 |
| 381 | astrbot_plugin_BitTorrent | 610 | other | watch | 适配AstrBot的磁力搜索插件，通过机器人帮你寻找电影、软件或者学习资料 |
| 382 | astrbot_plugin_imgexploration | 609 | other | watch | 通过上传图片搜索其来源，支持 SauceNAO、Google Lens、Ascii2d 等搜图引擎，并结合LLM改善使用体验。 |
| 383 | astrbot_plugin_currentcortex | 604 | memory | have | 多功能 AstrBot 插件（CurrentCortex）—— Pixiv 随机图片 ·网易云点歌 ·小红书/B站/抖音/微博媒体解析 ·每日一言 ·天气 ·男娘 ·地震预警（多源聚合/群聊白名单/到达倒计时） ·气象预警（中央气象台/城市白名单） ·DG-LAB（郊狼） 设备管理 ·跨群聊记忆（L |
| 384 | astrbot_plugin_session_usage_stats | 604 | other | watch | 统计 AstrBot 全部模型的调用次数与 Token 消耗，提供美观的可视化仪表盘，并支持每日用量告警与限制、面板精细化管理等。 |
| 385 | astrbot_plugin_deer_check | 602 | platform | have | 一个发送'🦌'进行打卡并生成日历的插件，支持分析报告、排行榜与群打卡战报。 |
| 386 | astrbot_plugin_balance | 601 | other | watch | 一个简单的 LLM API 余额查询与 IP 查询小插件, 支持硅基流动，DeepSeek 与 OpenAI 余额查询及 IP 地址查询功能 |
| 387 | astrbot_plugin_VisiStat | 600 | other | watch | 可视化的系统硬件监控，可自定义美化以及自定义参数显示，适配Windows/Linux双端 |
| 388 | astrbot_plugin_web_screenshot | 597 | other | watch | 基于外部API提供网页截图功能的AstrBot插件，适用于OneBot QQ机器人 |
| 389 | astrbot_plugin_whitelistpro | 597 | other | watch | 支持临时会话、好友私聊、群聊的白名单独立控制和全局白名单黑名单 |
| 390 | astrbot_plugin_enhanced_scheduler | 597 | proactive | watch | 未来计划任务调度器。支持多种触发条件组合，实现复杂触发主动发言。可执行AI消息发送或文本发送。 |
| 391 | astrbot_plugin_comfyui | 594 | image-gen | watch | 将 ComfyUI 工作流封装为 LLM 可调用的工具，支持工作流上传/管理、说明与 text_slots，文生图/改图等任意工作流通过指定节点（Simple String、ETN_LoadImageBase64、VHS_LoadVideo）即可接入并执行。 |
| 392 | astrbot_plugin_touhou_kb | 592 | kb-rag | have | 将 THBWiki 备用站词条清洗后导入 AstrBot 官方知识库，支持会话绑定、人格绑定与东方话题优先路由 |
| 393 | astrbot_plugin_angel_smile_guard | 592 | sticker | borrow | 配合 astrbot_plugin_angel_smile 使用的监督插件：在表情包入库之前，调用多模态大模型自动审核图片，仅允许女性角色表情包，禁止任何男性角色。  主要特性： - 入库前自动拦截审核，审核不通过一律拒绝 - 严格策略（fail-closed）：出现男性角色、无明确人物角色、无法判 |
| 394 | astrbot_plugin_tradingagents | 591 | other | watch | 基于多智能体辩论架构的 AstrBot 金融分析插件，支持 A 股、港股、美股的智能分析报告生成。 |
| 395 | pulid_napcat_go_to_astrbot | 591 | other | watch | 一键完成 NapCat 的下载、安装、启动、QQ 登录与 OneBot v11 反向 WebSocket 配置，支持 Windows / Linux，固定供应 NapCat 4.18.5 稳定版。Linux 本地模式需要 sudo 权限，并可能按 NapCat 兼容版本要求重装 QQ。 |
| 396 | astrbot_plugin_mrfz | 587 | tts | watch | 这是一个用于获取和播放明日方舟所有角色语音的 AstrBot 插件。 |
| 397 | astrbot_plugin_mimo_voiceclone | 586 | tts | watch | 上传一段音频定下音色，或用一句话描述造音色，调用 MiMo TTS 合成语音。内置「音色工坊」页面，填 API Key、选音频格式即可直接试听。 |
| 398 | astrbot_plugin_PersonaFlow | 579 | memory | have | 人格记忆（人物印象、全文记忆、多 Bot 多人格独立库）+ 群聊感知（判断模型接管回复、群身份与群事件）+ 独立上下文库，带可视化管理面板 |
| 399 | astrbot_plugin_sensitivefilter | 577 | group-admin | have | 群聊敏感词检测插件，支持本地词库/外部接口/AI 语义识别三种检测方式，可按群单独配置撤回、警告、通知等处理动作 |
| 400 | astrbot_plugin_qzone_kit | 574 | sticker | borrow | 【需要的前置】 1. QQ空间 astrbot_plugin_qzone　2. QQ资料管理 astrbot_plugin_qqprofile —— 两个必装并启用。 3. 【强烈推荐】我会永远陪着你 astrbot_plugin_private_companion（适配插件市场 6.5.6 稳定版 |
| 401 | astrbot_plugin_pjsk | 571 | sticker | borrow | Project Sekai 表情包制作插件 |
| 402 | astrbot_plugin_live2d_pet | 568 | sticker | borrow | 把 AstrBot 的对话内容投射到 Live2DViewerEX 桌宠上，并按情感切换表情；交互模式下可在桌宠气泡上点选选项，直接回传触发下一轮对话。 |
| 403 | astrbot_plugin_llm_poke | 568 | game | have | 用LLM进行回复的戳一戳插件 |
| 404 | astrbot_plugin_epic_freegame | 567 | game | have | 获取 Epic 每周免费游戏信息，支持定时推送和指令查询，通过 60s API 获取数据并渲染为精美图片发送。 |
| 405 | astrbot_plugin_bartender | 566 | other | watch | 基于playwright无头浏览器库，对sillytavern项目进行操作和交互，达成通过机器人远程游玩Sillytavern，以及高于联机脚本的游玩体验貂蝉在一起 |
| 406 | astrbot_plugin_mudae_qq | 559 | other | watch | QQ 群动漫抽卡。 |
| 407 | astrbot_plugin_multimsg | 557 | sticker | borrow | [仅aiocqhttp] 为bot发送多种类型消息提供便捷命令，包括markdown，猜拳，转骰子，发表情，音乐卡片，推荐卡片，转发，合并转发，@全体成员... |
| 408 | astrbot_plugin_dsh_gateway | 557 | personality | have | 让 dsh（DeepSeek Harness）这类本地 agent 借 AstrBot 里那个角色的通道，把消息转达给你： agent 的话不直接发到聊天窗口，而是先落到这一侧的中转箱，插件立刻排一个一次性任务把助手角色 叫醒，由它自己读中转件、用自己的话讲给你听，讲完把文件归档；叫不动才回退到即时 |
| 409 | astrbot_plugin_personal_network | 554 | personality | have | 按人格管理虚拟的人际网络中的人物、关系与共同经历，并提供可视化 WebUI。 |
| 410 | astrbot_plugin_twitter | 553 | info-push | have | 支持 Nitter 与 FxTwitter API 的推特转发插件，提供订阅、定时推送、链接识别和合并转发 |
| 411 | hello-bye | 553 | other | watch | [仅aiocqhttp] 为用户进群退群发送信息提示 |
| 412 | astrbot_plugin_video_recognize | 552 | other | watch | 收到 QQ 视频消息时自动抽取关键帧，并调用 DeepSeek 视觉模型识别视频内容。  功能： - 自动拦截含视频的消息，用 ffmpeg 抽帧后交给 deepseek-v4-flash-vision-exp 多模态模型识别 - 识别完成后直接回复中文描述，并阻止主模型重复回复 - 支持黑名单 / |
| 413 | astrbot_plugin_rvc_svc | 551 | tts | watch | RVC/SVC翻唱网易云歌曲（需要下载后端） |
| 414 | astrbot_plugin_tarot | 550 | media-parse | borrow | 一个基于 AstrBot 框架的塔罗牌占卜插件，支持多牌阵和单张牌占卜，并通过 AI 生成详细解析。 |
| 415 | astrbot_plugin_true_zyx | 550 | memory | have | 让 AstrBot 真正"活"起来的插件。基于 LLM 的主动对话与真人化行为系统：  1. 主动对话：后台按配置巡检活跃会话，概率主动发起/接续话题（带冷却与免打扰时段），    不再只能"被 @ 才开口"； 2. 真人化行为：根据上下文自然水群、被 @ 会 @ 回去、拍一拍有反应、    会引用 |
| 416 | astrbot_plugin_atrelay | 549 | other | watch | 通过私聊自然语言指挥机器人在 QQ 群内 @ 群友发消息、向指定 QQ 发送私聊消息。支持群名/昵称匹配。 |
| 417 | astrbot_plugin_bug_companion | 549 | kb-rag | have | 面向 AstrBot 开发者交流群的问题治理与知识沉淀插件。提供指定群聊收集、模型初审、人工批阅、待办追踪、GitHub 仓库动态播报与已审批知识答疑。 |
| 418 | astrbot_plugin_web_search_pro | 548 | other | watch | 基于SearXNG的Web搜索插件 |
| 419 | astrbot_plugin_just_enough_mcserver_status | 544 | other | watch | 让AstrBot能展示Minecraft服务器状态。 |
| 420 | astrbot_plugin_history | 543 | other | watch | 在本地极速实时追加备份所有私聊与群聊记录，有效防范数据丢失。内置 WebUI 可视化面板随时浏览。最新版深度双向兼容 AstrBot 史前及最新 API 框架。 |
| 421 | astrbot_plugin_group_signin | 543 | other | watch | [仅 aiocqhttp] QQ群打卡助手，支持定时打卡、一键打卡、智能通知和统计功能。 |
| 422 | astrbot_plugin_dsh_connector | 542 | other | watch | 通过 DSH Web HTTP API 在 AstrBot 中创建、绑定和控制 DeepSeek Harness 会话。 兼容 DSH 0.2 起的 Typert RPC 与浏览器会话认证。 每个聊天窗口独立保存工作空间或目录、Agent Preset、模型、推理强度、权限和 IANA 时区， 并支 |
| 423 | astrbot_plugin_douyinchat | 542 | media-parse | borrow | 将抖音网页版私信作为消息平台接入 AstrBot，基于 Playwright 自动化收发文本与图片。 |
| 424 | astrbot_plugin_shitu | 541 | other | watch | 通过调用 AnimeTrace 网站提供的 API 进行动漫识图 |
| 425 | astrbot_plugin_gengwiki | 541 | sticker | borrow | 让机器人跟上当下热梗，聊天时自然地玩梗、发表情包，还能随时切换人设。内容来自社区共建的中文热梗百科梗Wiki https://gengwiki.com |
| 426 | astrbot_plugin_dfy_mood | 539 | other | watch | 量化机器人的心情与关系度，并让回复的语气随心情变化；提到别的 AI 时会吃醋。 |
| 427 | astrbot_plugin_daily_ai_news | 536 | group-stats | borrow | 订阅橘鸦AI日报并进行AI总结 |
| 428 | astrbot_plugin_gok | 534 | personality | have | 微信或 QQ 扫码登录后直连王者营地，查询战绩、游戏状态与对局回放；支持角色别名、AI 分析持久缓存、上下线和最新战绩订阅推送。 |
| 429 | astrbot_plugin_parse_bilicomp | 534 | media-parse | borrow | 解析B站相关内容组件并以图片展示，支持视频下载、专栏预览、AI总结等功能。 |
| 430 | astrbot_plugin_vision | 533 | media-parse | borrow | 让 AstrBot 陪你看视频。支持视频分析和实时视频理解。视频分析提供混合抽帧视频概览、按需回看工具和分享链接自动解析；实时视觉支持接入屏幕截图、摄像头画面或媒体流，并可选择提问、定时、变化三种响应模式。支持 ASR 语音识别辅助理解，提供可视化流水线调试台。 |
| 431 | astrbot_plugin_bbt_daily_news | 531 | info-push | have | 一个简单的每日晨报插件 |
| 432 | astrbot_plugin_bilibili_bot | 528 | media-parse | borrow | 适配 AstrBot 的插件，自动识别B站链接并转换为直链发送 |
| 433 | astrbot_plugin_maimaidx | 526 | other | watch | 国服舞萌插件，支持导入成绩，查询成绩、机厅、排名、曲目信息，猜歌与排卡等功能 |
| 434 | astrbot_plugin_math_plotter | 525 | other | watch | AI 辅导学习时自动调用，将数学方程、函数公式绘制为图像。支持一元函数、多函数对比、隐式方程、三维曲面、极坐标、参数方程、球坐标曲面、矢量场、隐式3D曲面等 11 种坐标系/绘图模式。 |
| 435 | astrbot_plugin_openviking_memory | 522 | memory | have | 集成 OpenViking 长期记忆能力。支持自动捕获对话、语义召回，以及跨对话空间记忆，且隔离规则可自定义配置。 |
| 436 | astrbot_plugin_music-search | 521 | tts | watch | 让你的bot能够搜索歌曲并点歌的插件 |
| 437 | astrbot_plugin_oyasumi | 518 | proactive | watch | 基于正则触发的早安晚安长期记录插件，可自定义触发词，支持统计、修正与 llm 个性化分析，配套 webui。 |
| 438 | astrbot_plugin_echoscore | 518 | game | have | 通过小维 API 提供快速的鸣潮声骸评分，支持图文、引用、LLM 工具调用。 |
| 439 | astrbot_plugin_multi_draw | 515 | image-gen | watch | 让 Bot 借助 LLM 在聊天中画画、改图，支持 NovelAI、OpenAI、Seedream、xAI、Gemini、SenseNova 和 ComfyUI；开画、完成、失败时都会按人格说话，可查询各平台余额，并提供可视化配置页面 |
| 440 | astrbot_plugin_qqmusic | 514 | tts | watch | QQ点歌插件 - 基于慕名API的QQ音乐无损音频点歌，支持音乐卡片/语音消息发送（可无视VIP限制） |
| 441 | astrbot_plugin_doro | 513 | sticker | borrow | 获取随机的 Doro 表情包 |
| 442 | astrbot_plugin_chatmaster | 512 | group-stats | borrow | 活跃度监控插件，支持白名单/全员监控切换，每日定时日报。 |
| 443 | astrbot_plugin_game_event_due | 512 | platform | have | 聚合多款游戏的限时活动起止时间，按会话订阅推送到群聊 / 私聊。支持新活动推送、 剩余 7 天 / 3 天 / 24 小时分级到期提醒、每会话关键词黑白名单过滤、封面图自动 压缩发送，并提供 Plugin Pages 管理页。 数据来源：SRA 公共 API（共 18 款，含崩坏：星穹铁道、原神、绝 |
| 444 | astrbot_plugin_click2download | 510 | other | watch | 你可以把链接发送到群聊/私聊中，让bot帮你下载 |
| 445 | emoticon_manager | 510 | sticker | borrow | 一个简单的表情包插件，支持情感匹配与 WebUI 管理编辑表情包。 |
| 446 | astrbot_plugin_balance | 509 | other | watch | 输入 /余额 即可查看 AI API 的账户余额信息。  **功能：** - 支持 DeepSeek、智谱、硅基流动等多种 API 平台 - 可在 WebUI 插件设置中自主填写 API Key 和接口地址 - 也可自动读取 AstrBot 已配置的 LLM 提供商 - 一条指令/余额，随时掌握 A |
| 447 | astrbot_plugin_manbo_tts | 508 | tts | watch | 基于外部API：https://api.milorapart.top/apis/mbAIsc 提供曼波语音信息生成 |
| 448 | astrbot_plugin_gif_vision_helper | 508 | other | watch | 将QQ GIF动图拆成多帧静态图，让多模态模型真正看懂动图 |
| 449 | astrbot_plugin_rocom | 507 | media-parse | borrow | 基于 WeGame API 的洛克王国数据查询插件，支持扫码登录、档案与家园查询、查蛋配种、精灵收集排行榜和阵容分享码解析。 |
| 450 | astrbot_plugin_content_safety_guard | 506 | group-admin | have | 内容安全守卫 - 拦截用户提示词攻击和模型输出偏离人设问题，支持前置/后置审核、关键词匹配、LLM自审查、黑名单等功能 |
| 451 | astrbot_plugin_reminder | 506 | group-admin | have | 支持在指定会话定时发送提醒消息或执行指令任务，支持富媒体内容（如视频、语音等）、艾特解析与自动撤回。 |
| 452 | astrbot_plugin_identity_strategy | 506 | other | watch | 为群聊/私聊注入指定的应对提示词（纯配置，无命令；支持特殊ID与空白策略） |
| 453 | astrbot_plugin_goofish_catcher | 505 | info-push | have | 闲鱼 Agent 化购物助理。LLM 可直接调用工具完成搜索、订阅管理、收藏及任意复杂页面操作；支持关键词订阅轮询、上新降价检测、LLM 推荐排序与 WebUI 管理。本地或远程部署均可，远程模式下 AstrBot 宿主机无需 Playwright。 |
| 454 | astrbot_plugin_chat_polisher | 505 | other | watch | 自动将输出的回复文本内容截取，并通过设定的规则进行润色后发出。 |
| 455 | astrbot_plugin_av_sense | 505 | sticker | borrow | 【需要的前置】 AstrBot ≥ 4.17（aiocqhttp 协议端）；系统里装了 ffmpeg 和 ffprobe 并加进 PATH。 语音识别默认走本机（faster-whisper / funasr，插件会自动找、自动起，不花钱）； 本机什么都没有时会退到 AstrBot 自带的「语音转文 |
| 456 | astrbot_plugin_nitter_tweets | 504 | media-parse | borrow | 通过 FxTwitter 或自建 Nitter 获取公开 X/Twitter 推文，支持博主、关键词和公开列表订阅，提供手动查询、搜索、分组定时推送及聊天链接解析；支持 QQ、Telegram、飞书、微信 OC 等多个平台，并提供 WebUI 管理。 |
| 457 | astrbot_plugin_shit_detector_plus | 504 | other | watch | 如果你觉得你的 coding plan 额度用不完，不妨试着让 AI 给你自动搬史。一个自动搜索 GitHub 项目，使用 AI 进行"史"级评定的趣味插件，支持定时推送精选项目到群聊 |
| 458 | astrbot_plugin_zt | 503 | other | watch | 简易版服务器状态插件 |
| 459 | astrbot_plugin_trpgdice_rerolled | 501 | game | have | 支持自定义回复的骰娘插件！基于trpgdice_complete开发 |
| 460 | astrbot_plugin_iearning_style | 500 | other | watch | 使机器人可以从聊天中学习他人说话方式 |
| 461 | astrbot_plugin_arcaea | 499 | sticker | borrow | 生成 Arcaea 风格表情包，支持描边、多行文字、角色默认颜色，可自定义字体，可发送自定义阿卡伊表情包 |
| 462 | astrbot_plugin_vpn_traffic | 496 | info-push | have | 按拥有者 ID 查询 Clash 或 V2Ray 订阅的剩余流量信息。 |
| 463 | astrbot_plugin_dont_poke_my_master | 495 | game | have | 当主人被戳一戳，或者自己被戳一戳触发回复 |
| 464 | astrbot_plugin_sugarcron | 494 | memory | have | 重写自带的定时任务：到点发固定文本、让 AI 现写一段，或让 AI 走真实对话链路回一整串（交给你装的分段插件拆成多条）；发完带着「任务名+起因」记进 sugarmemory，AI 跨会话被问「你为什么发这个」答得上来。带 WebUI 面板（任务管理/运行记录/总配置）、五个 AI 工具（建/列/删 |
| 465 | astrbot_plugin_novel | 493 | kb-rag | have | QQ群群友协作 + AI辅助写作的长篇小说插件（每群独立/知识库/多AI打分/冲突投票/风格模仿/用户修正/EPUB/PDF导出） |
| 466 | astrbot_plugin_sugar_menu | 492 | group-admin | have | 把「我会干什么」整理成一张可定制的卡片：指令触发、AI 工具自主调用（问「你会干啥」时自动递卡）、加好友与进群自动欢迎。支持浅色/深色/粉紫三套主题，Playwright 渲染，渲染失败自动回退纯文本 |
| 467 | astrbot_plugin_bili_watch | 491 | media-parse | borrow | 让 AstrBot 的模型真的“看懂”一条 B 站视频：先读**完整字幕**，再看**关键画面**，而不是凭标题或封面瞎猜。  ## 它怎么工作  1. `bili_watch_preview`：返回**完整字幕**（带 [mm:ss] 时间戳）+ 10 帧全片概览； 2. 模型读完字幕，自己挑 3 |
| 468 | astrbot_plugin_image_studio | 490 | other | watch | 多服务商 AI 生图与图库工作台，支持 OpenAI、Gemini、Agnes AI、ComfyUI 工作流、NovelAI 官方、NAI 第三方及自定义接口。支持对话生图改图、并发批量生成、图片参数导入与工作流复现，可扫描 nai-image 插件图库及自定义目录，统一浏览和管理图片。WebUI  |
| 469 | astrbot_plugin_online_status | 489 | other | watch | 在线状态管理与感知（仅适配 Napcat） |
| 470 | astrbot_plugin_context_undo | 488 | group-admin | have | 撤回最近一次或多次的ai回复上下文，避免ai被不良信息影响。 |
| 471 | astrbot_plugin_text2img | 487 | image-gen | watch | 多平台文生图插件，支持 Gitee AI、阿里云百炼、字节火山引擎。支持比例+质量参数智能选择分辨率，根据模型自动适配最佳配置。 |
| 472 | astrbot_plugin_repeater | 487 | sticker | borrow | 群复读机：当群内连续 N 个不同的人发送相同消息时，机器人自动跟一条。支持文本、真实艾特、小黄脸、图片/表情包复读，支持按群开关、自定义触发人数与冷却时间，适配 NapCatQQ（OneBot v11 / aiocqhttp）。 |
| 473 | astrbot_plugin_denia_share | 486 | media-parse | borrow | 在聊天中发送链接或分享口令，即可自动解析内容，并发送分享卡片及可用的视频、图片或音频。  支持 B站、抖音、快手、微博、小红书、Twitter / X、YouTube、AcFun、NGA、GitHub、Pixiv、Steam、小黑盒、QQ音乐、网易云音乐。  - 支持音乐单曲分享、带编号的搜歌卡片与 |
| 474 | astrbot_plugin_minecraft_monitor | 484 | other | watch | Minecraft服务器监控插件，支持定时检测服务器状态变化并发送通知。可配置目标群、服务器地址、检查间隔等。 |
| 475 | regex_filter | 482 | other | watch | 一个使用正则表达式处理LLM消息的AstrBot插件，可以对LLM回复进行替换、删除、增添等操作。 |
| 476 | astrbot_plugin_memory5 | 482 | memory | have | 优化标签迁移与记忆匹配，减少阻塞和重复扫描。 |
| 477 | astrbot_plugin_pet_market | 481 | game | have | 群聊宠物互动游戏 - 支持养成、银行、PK、金融市场、原子存档与安全事务 |
| 478 | astrbot_plugin_group_aip_review | 480 | group-admin | have | 让我康康你的消息正不正常喵？基于百度内容审核API对群聊消息进行实时审查喵，支持文本和图片审核喵，自动处置违规内容并通知管理员喵。 |
| 479 | astrbot_plugin_self_identity | 477 | other | watch | 让机器人自己改头像、昵称、签名、在线状态，并记住「我是谁」。 |
| 480 | astrbot_plugin_pollinations_images | 473 | other | watch | 使用 Pollinations AI生成图片。无需注册，开箱即用！ |
| 481 | astrbot_plugin_rss | 473 | ssh-exec | exclude | 支持通过 RSSHub 路由和直接 URL 订阅 RSS 源，并定时获取最新的 RSS 内容，如推特、B站、油管、博客等任何支持 RSS 2.0 的网站。 |
| 482 | astrbot_plugin_tieba_tone | 473 | personality | have | 按管理员配置的贴吧列表，定时抓取帖子与楼层评论（全程只读，不发帖、不回复）， 交给 LLM 提炼出「语言风格指南 + 代表性语录」，并在后续 AI 对话时自动注入系统提示词， 让机器人的回复带上该吧吧友的说话风格。  主要特性： - 定时刷帖学习（每天/每小时可配），支持配置每帖抓取数量与请求间隔  |
| 483 | astrbot_plugin_bilibili_livemonitor | 472 | media-parse | borrow | bilibili开播下播提醒 |
| 484 | astrbot_plugin_livingmemory_ext | 472 | memory | have | 基于 lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory 的定制化拓展，保留原版完整记忆生命周期与混合检索能力，并在此基础上做定制化调整。 |
| 485 | astrbot_plugin_agnes_image | 471 | image-gen | watch | Agnes AI 图像与视频生成插件，依据 Agnes 官方文档进行了原生适配以实现完全免费、较高质量的定制化生成体验，支持文生图、图生图以及视频生成，并内置了大模型原生生图/改图工具和大模型原生视频双子工具。 |
| 486 | astrbot_plugin_joinmanager | 468 | group-admin | have | [仅 aiocqhttp] 处理QQ群加群请求，包含入群统计功能 |
| 487 | astrbot_plugin_wave_memory | 467 | memory | have | 基于 VCP TagMemo 浪潮算法的高性能记忆插件。查询路径零 LLM 调用，本地计算 < 2ms，支持通用数据源导入。 |
| 488 | astrbot_plugin_minecraft_wiki | 465 | other | watch | 用于为llm调用minecraft wiki |
| 489 | astrbot_plugin_at_check | 465 | other | watch | 记录群聊中最近@你的消息，支持单独@的上下文获取。 |
| 490 | astrbot_plugin_mood_of_the_moment | 464 | sticker | borrow | meme_def 精确选图与 tag 分组兜底的 AstrBot 表情包插件。 |
| 491 | astrbot_plugin_hextech | 461 | payment | exclude | 从https://apexlol.info/查询英雄海克斯适配度等信息 |
| 492 | astrbot_plugin_touchi | 457 | other | watch | 三角洲鼠鼠偷吃模拟器（简易） |
| 493 | astrbot_plugin_video_vision | 457 | media-parse | borrow | 为 AstrBot 提供视频理解能力，支持两种模式： - gemini_native：Gemini 原生视频输入（把视频块注入当前请求，主对话 provider 须为 Gemini 系） - openai_compat：插件直接调用配置里的 OpenAI 兼容视觉服务做理解，结果以文字注入，主对话模 |
| 494 | astrbot_plugin_opencode | 454 | tts | watch | 让 AstrBot 对接 OpenCode，通过自然语言远程指挥电脑干活。使用此插件，意味着你已知晓相关风险。 |
| 495 | reverse_searcher | 452 | reverse-eng | exclude | 支持 AnimeTrace、Google Lens、Yandex、SauceNAO 四大引擎的图片反向搜索，搜索结果自动渲染为精美卡片图片，同时提供 LLM 主动搜图工具 |
| 496 | astrbot_plugin_quota_guard | 452 | other | watch | 独立实现的群聊 token 流量控制：按群、按人统计每日用量，超额在请求前拦截。 支持限时 VIP —— 指定群里指定成员在一段时间内不受单用户限额约束，到期自动恢复。 用量取自模型返回的真实 token 数，不依赖任何其他插件。 |
| 497 | astrbot_plugin_pic_mirror | 448 | other | watch | 一个图像对称处理插件，用于生成诡异弔图，可以为图片添加多种镜像效果 |
| 498 | astrbot_plugin_obsidian_kb_sync | 446 | kb-rag | have | 通过 Fast Note Sync Service 将 Obsidian 笔记同步到 AstrBot 知识库。 |
| 499 | astrbot_plugin_vocu_tts | 443 | tts | watch | 通过 Vocu API 将机器人发送的文本消息自动转为语音，支持 TRPG 括号内容过滤与情绪映射。 |
| 500 | astrbot_plugin_nbalance | 442 | other | watch | 格式化 NewAPI 余额接口返回数据，供 AstrBot 查询展示使用，支持命令行查询和 LLM 工具调用两种方式 |
| 501 | cr4zythursday | 442 | other | watch | 疯狂星期四！ |
| 502 | astrbot_plugin_Super_AstrBot | 442 | memory | have | 群聊拟人化融合版：在长期记忆 / 自我学习基座之上，新增**单人格 × 群聊拟人化**的一整套进程内融合能力——群友识别（稳定档案 + 差异化对话策略：语气 / 称呼 / 话题 / 禁忌，只调表层不换人格）、PersonaForge 三层人格（核心特质 / 表层风格 / 动态状态 + 可选双过程内省 |
| 503 | astrbot_plugin_qq_group_summary | 441 | other | watch | QQ群聊总结，支持LLM TOOL调用。 |
| 504 | astrbot_plugin_video_storyboard | 439 | memory | have | 自动理解群聊中的BV号和B站分享，后台分镜与语音识别，将视频内容融入机器人原有人设聊天并支持后续追问。 |
| 505 | astrbot_plugin_anime1_list | 436 | other | watch | 基于anime1.me，获取每日动画更新、番剧列表和观看地址。 |
| 506 | ai_memory | 435 | memory | have | 一个AI记忆管理插件，可以让ai记住重要的事，记忆读取是ai自己调用的，有时候呆呆的ai不会自己调用，可以多问几次或者人格加上特定提示词,输入 /mem_help 查看记忆管理帮助 |
| 507 | astrbot_plugin_qzone_lite | 435 | other | watch | QQ空间轻量插件，仅支持查看/发表/删除/点赞/评论说说与回复评论 |
| 508 | astrbot_plugin_suanle_bushuo | 435 | other | watch | 让 Bot 更像真人，拥有主动不回复的选择：没有合适的插话时机或不想回应时，可以自主保持沉默；也支持管理员指定忽略对象，保留其近期消息作为上下文，同时阻止这些消息触发回复。 |
| 509 | astrbot_plugin_skills_mcp_manager | 434 | other | watch | 为astrbot提供函数工具和指令来管理 AstrBot Skills 和 MCP 服务器。 |
| 510 | astrbot_plugin_daily_news | 433 | info-push | have | [仅 aiocqhttp] anka - 每日60s新闻推送插件, 请先设置推送目标和时间, 详情见github页面! |
| 511 | astrbot_plugin_logplus | 431 | other | watch | AstrBot日志增强插件，支持日志持久化、按插件分类、轮换、压缩、自动清理等功能 |
| 512 | astrbot_plugin_epic_free_games_notice | 430 | game | have | 一个为AstrBot设计的 Epic 喜加一游戏提醒插件。该插件可自动或手动推送本周的 Epic 免费游戏信息到指定群组，帮助群成员及时领取免费游戏。理论上支持所有客户端。 |
| 513 | astrbot_plugin_telegram_forwarder | 428 | other | watch | 将一个公开 Telegram 频道的消息自动转发到你自己的 Telegram 频道或 QQ 群。 |
| 514 | astrbot_plugin_help_panel_typst | 427 | devtools | watch | 新时代的 AstrBot 插件帮助面板：将插件、指令、事件与过滤器渲染成精美长图，支持搜索与插件详情，样式可在网页实时调整查看 |
| 515 | astrbot_plugin_pixiv_lookup | 423 | nsfw | exclude | 支持标签搜索、画师最新插画、多图首图、四档图片尺寸、独立 R18/R18G 开关、QQ 合并转发与自动撤回。 |
| 516 | astrbot_plugin_Astronomy_Picture_of_the_Day | 422 | other | watch | NASA 每日一图，使用指定的指令获取 NASA 的每日天文图片，支持语言模型翻译图片解释。 |
| 517 | astrbot_plugin_central_intelligence | 420 | memory | have | AI智能体持久化记忆服务。跨会话存储、语义召回、共享知识。Persistent memory for AI agents — store, recall, and share knowledge across sessions. |
| 518 | astrbot_plugin_recall_xz | 418 | memory | have | 一个自动撤回触发词和机器人发送的消息的插件。 |
| 519 | astrbot_plugin_batchrecall | 418 | memory | have | 【仅QQ】批量撤回,编号撤回(所有人),引用撤回,指定撤回,自动撤回,防撤回,撤回自身 |
| 520 | astrbot_plugin_qbittorrent_manager | 417 | other | watch | 按 QQ 用户独立配置 PT 站与下载客户端，支持搜索种子和直接添加下载任务。 |
| 521 | astrbot_plugin_seedream_image | 416 | image-gen | watch | 使用火山方舟seedreamAPI生成图片，触发指令为画图豆包 |
| 522 | astrbot_plugin_ccb_plus | 415 | other | watch | [仅 aiocqhttp]基于 灵煞 / ccb 的 和QQ群群友发生赛博sex的插件的改进版。 |
| 523 | astrbot_plugin_chorus_cover | 410 | tts | watch | 说一句「翻唱《歌名》」就自动取歌、切副歌、RVC 变声、混音发回群聊；支持整首/自定时长/清唱；需自备 RVC 整合包与 chorus-mw 中间层（0.9.16 起，插件随 AstrBot 自动启停） |
| 524 | astrbot_plugin_ssh | 409 | ssh-exec | exclude | SSH 远程命令执行插件，支持 LLM 调用 |
| 525 | astrbot_plugin_extract | 409 | media-parse | borrow | 对图片、视频、语音、文件等媒体的元数据进行解析 |
| 526 | astrbot_plugin_game_companion | 409 | memory | have | 让 Bot 与用户通过安全的可视化房间自然地一起玩游戏，并延续现有陪伴人格与长期记忆。 |
| 527 | astrbot_plugin_nailong | 407 | sticker | borrow | 来只奶龙 - 支持 来只奶龙/奶龙/龙来 随机或指定发送奶龙表情包，支持查询数量、批量添加/删除/查询文件名/重命名、插件页面管理、GitHub 下载和按概率自动发送 |
| 528 | astrbot_plugin_self_initiated_reply | 407 | other | watch | 主动回复插件：白名单会话内，@Bot 与指令之外由判断模型决定是否接话，回复走 AstrBot 主 Agent 管线，默认不开放工具，可放开 |
| 529 | astrbot_plugin_qqmusic | 404 | media-parse | borrow | 从 Yunzai qqmusic-plugin 移植而来的 AstrBot 版本。 支持点歌、歌词、热搜、MV 搜索/播放/下载（点歌卡 🎬 徽标）、排行榜、新歌速递、 推荐、电台、日推、收藏、歌手/专辑/歌单/评论、QQ 音乐分享卡片与链接自动解析、 webqr 扫码登录、音质自适配降级、语音/群 |
| 530 | astrbot_plugin_cmdmask | 403 | info-push | have | 将真实指令映射为伪装指令，并支持静默或自定义回复，用“今天天气真好”代替“/reset”，用“挺好”代替“/reset”的回复，悄悄的重置，避免露馅。 |
| 531 | astrbot_plugin_bilibili_media_parser | 401 | media-parse | borrow | 自动识别并解析 B 站视频、音频、专栏、直播、番剧、动态等内容链接和 QQ 小程序分享，支持多链接解析、开播提醒、音视频下载与 AI 总结。 |
| 532 | astrbot_plugin_identity | 400 | personality | have | 让 AstrBot 真正「记住」谁是谁，而不是每轮都靠昵称猜。  **解决什么问题**  QQ 官方号（`qq_official`）拿不到稳定身份：私聊完全没有昵称，群聊昵称时有时无， 用户 ID 是 per-bot 的 hex `openid`，同一个人在不同群的 `member_openid`  |
| 533 | astrbot_plugin_duel_galatea | 399 | game | have | 一个游戏王全能工具箱,基于百鸽API提供游戏王卡片查询，卡图下载功能，基于duelmeta网站对当期DL/MD T表进行查询，并返回关键卡片，查询ROTK网站爬取当期OCG饼图和示例卡组,接收ourocg/ydke链接或ydk文本发送卡组图片，并提供随机一卡，发动王牌圣杯等娱乐功能，同时支持通过独立 |
| 534 | astrbot_plugin_ipquery | 397 | other | watch | 查询 IPv4、IPv6、域名地理位置及域名 WHOIS 信息的插件。 |
| 535 | favoradmin | 397 | media-parse | borrow | 给聊天增加了一个好感度值，靠检测 LLM 输出特殊的值来实现，让 LLM 来判断好感度的上升或下降，并且过低的好感度值会被机器人自动拉黑，有管理员身份来自定义好感度值以及拉黑或移除用户（轻微防止被群U玩坏） |
| 536 | astrbot_plugin_doro_today | 397 | other | watch | [仅测试QQ]一个AstrBot插件，从Doro结局图片中随机抽取一张并发送给用户，同时@发送者。 |
| 537 | astrbot_plugin_netease_music | 397 | tts | watch | 网易云音乐点歌插件，纯Python直连官方API，无需部署额外服务。支持搜索歌曲并在QQ群中发送封面和播放链接。配置VIP cookie后可点播VIP歌曲完整版。 |
| 538 | astrbot_plugin_InitiativeDialogue | 396 | other | watch | 使bot在用户长时间未发送消息时主动与用户对话的插件 |
| 539 | ai_reminder | 396 | other | watch | 智能定时任务,可以看做是高级提醒，可以让ai在特定时间执行特定任务,注意禁用原提醒插件 |
| 540 | astrbot-plugin-multimodal-router | 395 | other | watch | 当用户消息包含图片，且当前 LLM provider 不具备多模态能力时，本插件尝试仅将本次 LLM 请求路由到配置的多模态 provider。 |
| 541 | astrbot_plugin_huijiwiki | 393 | other | watch | 通过API调用在灰机wiki中搜索内容 |
| 542 | astrbot_plugin_meme_api_python | 393 | sticker | borrow | 调用 meme-generator API，提供表情列表、详情、随机表情和制作表情能力。 |
| 543 | astrbot_plugin_elves_world | 392 | game | have | 精灵对战游戏 - 探索、收集、战斗！ |
| 544 | astrbot_plugin_user_tag | 392 | personality | have | 说一句「设置关系 恋人」，下一句它就把你当恋人说话；139 种预设关系分 9 类，不够就自己编一个名字。另带一个网页面板：改关系、翻变更历史、调注入模板。 |
| 545 | astrbot_plugin_ark_calendar | 391 | group-stats | borrow | 明日方舟行动日报与工具插件：生成罗德岛风格活动、寻访与作战长图，支持生日查询、干员档案、活动与活动商店订阅、干员蹲池提醒、B站动态查询与推送（可选视频文件发送）、公开招募计算、自动日报和生日祝贺，并提供可配置的结构化 AI 工具与订阅管理。 |
| 546 | astrbot_plugin_reply_trim | 391 | other | watch | 把机器人的一条回复整理成更像真人聊天的形式： 1）去掉首尾多余的空白与换行（LLM 自己吐的换行 + AstrBot @ 后加的换行）； 2）按「。？！」与换行把长回复拆成几条，间隔一小段随机时间依次发出； 3）换行＝想单独发一条；一行里写了好几句时，在「。」「！」处切开，相邻的短句再用「，」连成一 |
| 547 | astrbot_plugin_steam_updates | 388 | game | have | 轮询游戏/创意工坊更新/喜加一并推送（支持多 AppID 创意工坊ID / 卡片或文本） |
| 548 | astrbot_plugin_werewolf | 388 | game | have | 狼人杀游戏插件（预言家+狼人+女巫+猎人+平民）- AI复盘 |
| 549 | zhiyu-astrbot-hjm | 388 | tts | watch | 一款随机哈基米语音的AstrBot插件 |
| 550 | astrbot_plugin_daily_diary | 388 | memory | have | 每日定时由大模型撰写一篇日记：发布时间、字数范围、禁止内容、大模型与知识库均可自由配置；人格设定从 AstrBot 已配置的人格中选择，发布前自动做一致性自检，不符合人格的日记不发布；写作风格可单独自定义。写完自动保存 TXT、写入指定知识库，并联动 astrbot_plugin_livingmem |
| 551 | astrbot_plugin_QQbox | 385 | info-push | have | QQbox是仿QQ聊天气泡生成插件，可将文字转换为高度还原的QQ风格聊天图片。支持自定义用户头衔、颜色和备注名，自动获取QQ头像与昵称，生成气泡消息。如有问题，请先尝试重载插件。 |
| 552 | astrbot_plugin_inkfusion | 384 | image-gen | watch | 用于Astrbot的Pollinations、SD（stable diffusion A1111）、llm图片生成插件 |
| 553 | astrbot_plugin_minesweeper | 384 | game | have | 经典的扫雷小游戏 |
| 554 | astrbot_plugin_soutu_search | 384 | personality | have | 为 AstrBot 提供两条搜图指令：「搜本」（别名 搜本子/soutu/找图）以图搜本子， 对接 soutubot.moe，**只接受图片**、结果标题优先日文/中文原名；「搜图」（别名 pixiv/saucenao）**自动判别**， 有图片或图片链接时用 **Yandex + SauceNAO |
| 555 | astrbot_plugin_agent_lab | 382 | other | watch | 管理员长任务工作台：批准计划、独立任务会话、持久进度、自动续接、途中引导和可视化编排。 |
| 556 | astrbot_plugin_setu_on_proactive | 382 | proactive | watch | 主动消息插件发送消息时，自动向同一会话执行配置的指令（默认 /setu 发图）。依赖前置插件 astrbot_plugin_proactive_chat，只联动单人私聊。 |
| 557 | astrbot_plugin_life_assistant | 381 | other | watch | 一句话记账、一键写日记、自动追基金、智能管日程。对话即生活记录，支持 Obsidian 同步。 |
| 558 | astrbot_plugin_persona_manager | 381 | personality | have | 角色社区化人设管理插件：会话式创建/修改、标签检索、关键词触发、群私聊隔离；支持为角色注入配置/自定义前后置提示词，并可选启用正则文本清洗；同时支持 CozyNook 社区角色小屋的浏览/导入/导出与内容分享。 |
| 559 | cloudrank | 377 | other | watch | AstrBot词云与排名插件(CloudRank)：专为AstrBot设计的强大聊天分析工具。可分析群聊与私聊消息，生成美观词云图，直观展示热点话题，并展示用户活跃度排行。支持定时与手动生成，提供丰富的颜色、字体、形状及排名显示自定义选项 |
| 560 | astrbot_plugin_diary_qzone | 373 | proactive | watch | 让她有一本自己的日记本。  你在私聊里说一句「晚安」，她会安静地写完今天的日记，发到 QQ 空间说说里，然后再回你一句晚安。 日记不是聊天记录的总结，而是独白：她自己的一天、她注意到的细节、她说不出口的话。  **特性**  - **跟着人格走**：直接读取 AstrBot 当前生效的人格提示词，换 |
| 561 | astrbot_plugin_steaminfo_xiaoheihe | 372 | media-parse | borrow | 通过小黑盒网站搜索并生成截图获取 Steam 游戏信息，支持小黑盒链接自动解析截图。 |
| 562 | tts_sanitizer | 371 | tts | watch | TTS 文本过滤插件，自动过滤颜文字、特殊符号等不适合语音朗读的内容 |
| 563 | sanjiaozhou | 370 | group-stats | borrow | 三角洲行动数据查询 AstrBot 插件，支持 QQ/微信登录与多账号管理、个人数据、战绩、日报周报、活动与物品价格查询、计算器、图片渲染及订阅推送。 |
| 564 | astrbot_plugin_api_limiter | 369 | other | watch | 多功能API调用管理插件，包含调用间隔限制、次数限制加冷却重开、安静时段定时切断、白/黑名单、分时段限频、群聊独立配额七大功能 |
| 565 | astrbot_plugin_MiniMax_CLI | 368 | tts | watch | 通过 MiniMax CLI 在 AstrBot 中调用 MiniMax Token Plan 的图片、视频、语音、语音识别、图像理解与搜索能力。 |
| 566 | astrbot_plugin_desktop_pet | 367 | memory | have | Windows 桌面 Live2D 桌宠：接 AstrBot 享受人格/记忆，或独立模式直连任意 OpenAI 兼容大模型；多模型热切换与拖拽上传、情绪表情、日语配音（SBV2）、主动搭话与桌面感知，配套 Tauri 桌宠壳 |
| 567 | astrbot_plugin_sticker_pack | 367 | sticker | borrow | 让 Bot 自己攒表情包并按场合挑着发：个人收藏（LLM 自主收藏 + 入库前视觉模型内容审查 + 意图闸门限频）与可选馆藏图库（带内容索引，按情绪/场景语义检索）。表情在文字回复之后补发，先文后图不突兀。 |
| 568 | astrbot_plugin_content_info | 364 | other | watch | 通过/context 获取当前上下文长度 |
| 569 | astrbot_plugin_riddlegame | 364 | image-gen | watch | qq群生图棋类游戏 |
| 570 | astrbot_plugin_weather | 363 | info-push | have | 一个基于心知天气免费API的天气查询插件 |
| 571 | astrbot_plugin_deepdeep | 363 | kb-rag | have | 统一管理和监控 AstrBot 的联网搜索（内置和社区插件）、知识库（内置和社区插件）和 MCP：自动选对搜索工具，出错就换一家，付费搜索到上限自动停，帮你改善搜索质量、看清花费。 |
| 572 | astrbot_plugin_Lolicon | 362 | nsfw | exclude | Lolicon API的随机动漫图片插件 |
| 573 | astrbot_plugin_talkative_king | 360 | other | watch | 统计群组发言并生成精美的排行榜图片，内置 pilmoji 支持，完美渲染 Emoji 和颜文字，支持自定义背景。 |
| 574 | astrbot_plugin_infinite_dialogue | 359 | other | watch | 这是一个为 AstrBot 设计的插件，旨在通过自动总结对话历史来实现'无限对话'功能 |
| 575 | astrbot_plugin_notes | 359 | memory | have | 一个完全独立的成长型知识插件，不依赖也不修改任何其它插件。  角色可以用 notes_write 把查到的稳定结论写进自己的笔记本，下次遇到相关话题时 自动带进上下文；每条笔记记录来源 URL 并按域名分级（可信 / 一般 / 存疑）， 让她在引用时自己判断该说到什么程度。被用户纠正时，写错的旧版本 |
| 576 | astrbot_plugin_wows-yuyuko | 357 | other | watch | 战舰世界战绩查询机器人 |
| 577 | astrbot_plugin_meme_maker | 357 | sticker | borrow | 图片合成梗图生成器 |
| 578 | astrbot_plugin_fund_analyzer | 356 | other | watch | 基金数据分析插件 - 提供实时行情、技术分析、量化指标、策略回测、AI智能分析 |
| 579 | astrbot_plugin_imgtool | 356 | image-gen | watch | 图像生成 LLM 工具，支持多 Provider（硅基流动 / ModelScope / OpenRouter / 自定义/ Gemini /豆包（火山） |
| 580 | astrbot_plugin_Xagent_searcher | 355 | media-parse | borrow | 使用X官方API来解析推特(X),获取推特的文本内容、图片和视频等信息。 |
| 581 | moremorelove | 355 | personality | have | 基于 AI 的 Galgame 互动插件，为 AstrBot 提供恋恋的多阶段情感体验 |
| 582 | astrbot_plugin_command_router | 353 | media-parse | borrow | 基于AI的自然语言指令解析，允许用户使用自然语言调用 AstrBot 中已注册的指令。 |
| 583 | astrbot_plugin_rsshub | 352 | ssh-exec | exclude | 多平台RSS订阅推送插件，支持失败队列重试、多BOT去重、平台数据共享、智能发送策略，LLM工具调用，让你的BOT成为信息聚合中心。 |
| 584 | astrbot_plugin_CNKD_NEWS | 351 | info-push | have | 来源于稳定接口的每日新闻推送插件 使用权威来源整合 无需额外配置 下载即用 支持白名单控制 支持定时发送 支持时区配置 |
| 585 | time_prompt | 350 | other | watch | 给聊天增加了当前时间提示词，让模型有一定的时间观念，还会让模型知道你们上一次对话间隔了多久[可在插件配置选择是否开启，默认开启] |
| 586 | astrbot_plugin_monitor | 349 | other | watch | [仅aiocqhttp] 通过bot查看其他群聊的聊天记录, 同时能通过bot向其他群聊发消息 |
| 587 | astrbot_plugin_bili_bridge | 349 | memory | have | 让 QQ 里的 AI 真正「看过」你 B站 账号今天刷了什么。 它做三件事： 1. **记忆同步**：定时读取 B站 侧的挑选结果（默认是刷视频类工具写出的 `digest/YYYY-MM.md`），压成一小段清单写进 MemoryCompanion 的核心记忆块， 每轮对话都会带上——于是你问「B |
| 588 | astrbot_plugin_qq_face_enhancer | 347 | sticker | borrow | 让 AstrBot 理解并安全使用 OneBot QQ 表情，支持按需语义检索和夜间语境学习 |
| 589 | astrbot_plugin_forward_reader | 346 | other | watch | 一个使用 LLM 分析合并转发消息内容的插件。 |
| 590 | astrbot_plugin_mememaker_api | 346 | sticker | borrow | 表情包制作插件(api版)，功能齐全，需要调用 meme-generator 服务 |
| 591 | astrbot_plugin_dnd_dice | 345 | game | have | 支持 D&D （Roll20规范）骰池语法的骰子插件，包括优势/劣势、保留最高/最低、爆炸骰、多骰组合等以及 LLM 函数工具调用。 |
| 592 | wxauto_repost | 345 | other | watch | 微信消息转发框架插件 - 基于 wxauto 库和 OneBotV11 协议，支持微信消息与 OneBotV11 协议的双向转发 |
| 593 | astrbot_plugin_dafeiyu_panel | 344 | media-parse | borrow | 把「她刷了什么视频」「她写了什么日记」和「她眼里的主人」搬进 AstrBot 面板：按天分组的视频卡带封面，点星星打分、写评价、一键收藏都会存回服务器并同步给刷B站插件调权重；日记本带心情标签、正文、看过的视频和「主人教我的」；另外有主人画像（性格/习惯/口头禅/心情指数/睡眠）与分类教学库（黑话/ |
| 594 | astrbot_plugin_uni_nickname | 340 | other | watch | 让 AI 始终使用管理员设定的昵称称呼群友（群聊和私聊均生效） |
| 595 | astrbot_plugin_gemini_search | 340 | other | watch | 一个调用Gemini格式API进行联网搜索的函数工具 |
| 596 | astrbot_plugin_keywordsreply | 340 | other | watch | 一个简单的关键词自动回复插件 |
| 597 | astrbot_plugin_bsk_browser | 340 | devtools | watch | 把本机的 bsk 命令行工具包装成机器人可以直接调用的工具，让机器人操作你已登录的真实浏览器： 打开网页、读取页面内容、点击按钮、填写表单、截图。因为复用的是你日常在用的那个浏览器， 所以需要登录才能看的页面（后台、邮箱、内部系统）它也能读，不必再单独登录一次 —— 这是它与 "另开一个无头浏览器" |
| 598 | astrbot_plugin_jrys | 340 | platform | have | 基于 AstrBot HTML 渲染引擎的今日运势签到插件，使用 Playwright 渲染 HTML 卡片并截图输出。 - 发送 `/jrys` 查看今日运势并完成签到 - 支持自定义背景图（远程 API 或本地图片路径） - 支持多平台：QQ、Telegram、Discord、微信、飞书、钉钉等 |
| 599 | astrbot_plugin_custom_menu | 334 | other | watch | 一个web菜单在线diy插件 |
| 600 | astrbot_plugin_bilibili_parser | 334 | media-parse | borrow | 自动识别并解析 B 站视频链接和 QQ 小程序分享，可选使用 AstrBot 已配置的模型商生成视频总结。 |
| 601 | astrbot_plugin_say | 334 | tts | watch | 让大模型通过 tool call 自主调用 MiMo-V2.5-TTS 全系列，把想说的话变成语音发送。  - 支持三模型单选：mimo-v2.5-tts（预置音色）、mimo-v2.5-tts-voicedesign（文本设计音色）、mimo-v2.5-tts-voiceclone（音色复刻）；  |
| 602 | astrbot_plugin_BombGame | 333 | game | have | 群内互动猜数字，支持多群独立游戏、轮流点名、超时临时会话提醒及 HTML 精美排行榜 |
| 603 | astrbot_plugin_broadcast | 333 | other | watch | [仅aiocqhttp] 一键群广播，所有适配器支持的格式都能发 |
| 604 | astrbot_plugin_ebooks | 333 | other | watch | 一个功能强大的电子书插件，支持多平台电子书搜索和下载。 |
| 605 | astrbot_plugin_error_pro | 332 | other | watch | 屏蔽机器人的错误消息，选择是否发送给管理员，支持AI友好解释。 |
| 606 | should_I_respond | 331 | other | watch | “我要回复这条消息吗？”当打开主动回复时，LLM 可能傻傻的就部分上下文一直回复。这个插件没准能解决这个问题。（在 aiocqhttp 平台测试，需要搭配主动回复功能使用） |
| 607 | astrbot_plugin_hardworking | 330 | other | watch | 一个可以让bot在你想水群的时候提醒你不要水群的插件 |
| 608 | astrbot_plugin_minecraft_skin_render | 330 | other | watch | 用于获取 Minecraft 玩家皮肤的 3D 渲染图、2D 头像或皮肤文件 |
| 609 | astrbot_plugin_steamgame | 328 | game | have | Steam 玩家数据可视化插件，支持群内排行，PK，以及游戏墙 |
| 610 | astrbot_plugin_openai_image-command | 328 | other | watch | 修改自喵喵的 OpenRouter 生图插件。使用 OpenAI 格式的免费 API 生成图片(使用指令调用插件) |
| 611 | astrbot_plugin_completely_disable | 328 | other | watch | 通过黑名单或白名单模式完全禁止某个群聊或用户使用机器人。 |
| 612 | astrbot_plugin_wechat_native | 328 | group-admin | have | 通过 agent-wechat-native /v1 API 将个人微信接入 AstrBot，无需额外的 Bridge 服务。  支持文本私聊、群聊 @回复、当日文本排行与热门话题、图片识别与发送、微信语音收发（语音识别使用 AstrBot 配置的 ASR）、PDF 解析、群聊摘要和原生引用回复，并 |
| 613 | astrbot_plugin_bili_whale | 327 | media-parse | borrow | 看懂一条B站视频：元信息、官方字幕、弹幕热区、热评、抽帧画面，支持私信自动回复、 评论区监听/自动回复、自己刷视频或刷动态主动互动、关注UP主、看关注动态与UP主主页、 发动态，并让模型知道自己的B站账号与后台做过的事，移植自 dsh-bili-whale |
| 614 | astrbot_plugin_rg2 | 325 | game | have | 一个刺激的群聊轮盘赌游戏插件。支持管理员装填子弹、用户开枪对决、随机走火等功能，提供完整的游戏体验和AI自然语言交互支持。 |
| 615 | astrbot_plugin_minecraft_adapter | 325 | other | watch | 连接到 Minecraft 插件服务器，实现消息互通和服务器管理 |
| 616 | astrbot_plugin_Helldivers | 325 | personality | have | 绝地潜兵2 图片情报插件。提供以下功能：  - 银河战争统计数据 - 重要指令（Major Orders）实时追踪 - 战役简报（Dispatches） - DSS 战术状态 - 银河战争地图（Galactic War Map） - 星球详情与当前星球效果，支持 Void 同名星球区分 - 全球事件 |
| 617 | astrbot_plugin_animewifex | 324 | other | watch | [仅 aiocqhttp] 基于 zgojin 的群二次元老婆插件修改版。 |
| 618 | astrbot_plugin_humanlike | 324 | personality | have | 把机器人说话里的“AI 味”去掉。三层手段，各自独立开关：  - **提示词层**：给模型注入一套“聊天风格”硬规则（短句、口语、不要总分总、不要结尾套话） - **后处理层**：回复发出前做规则清洗，砍掉“当然可以/希望对你有所帮助”这类套话，   去掉 Markdown 和破折号，书面连接词换口 |
| 619 | astrbot_plugin_lark_enhance | 323 | memory | have | 增强 AstrBot 在飞书场景下的表现，支持上下文感知增强（名字、群名、聊天记录、引用回复）、用户记忆、群记忆、流式输出、@群成员等 |
| 620 | astrbot_plugin_judge | 320 | other | watch | 根据用户消息复杂度,智能选择高智商模型或快速模型进行回答 |
| 621 | astrbot_plugin_speech_lessons | 320 | memory | have | 用自然语言教她如何说话，兼容陪伴插件和记忆插件。还能让她自己记录学习。有着简单易用的可视化管理和设置面板。支持向量导入和用户组权限配置。提供外部接口以联动其他场景的学习和记忆。 |
| 622 | astrbot_plugin_parse_hub | 318 | media-parse | borrow | 抖音、小红书、B 站等多平台解析，仅测试 telegram |
| 623 | quote_collocter | 318 | other | watch | 可以自己截图并投稿群友语录，机器人被戳戳时随机爆典 |
| 624 | astrbot_plugin_openai_image | 318 | other | watch | 对接 OpenAI 图片生成/编辑 API（DALL·E、gpt-image-1 等），支持供应商选择、模型获取、引用消息收集图片与文字进行改图 |
| 625 | astrbot_plugin_BiliCookie_monitor | 317 | media-parse | borrow | B站Cookie状态监控插件 - 定时检测Cookie有效性，失效时主动通知用户 |
| 626 | astrbot_plugin_messenger | 317 | other | watch | 通风报信插件 - 帮你传话给好友，支持来回对话 |
| 627 | astrbot_plugin_notice | 317 | group-admin | have | [仅 aiocqhttp] 通知助手，当bot被禁言/解禁、被踢出群/拉群、被取消管理员/设为管理员时，会向主人打小报告 |
| 628 | astrbot_plugin_HowMuchIsYourFace | 315 | sticker | borrow | 头像值多少钱？让 AstrBot 来给你估个价！ 本插件基于玄学算法（和一点点AI魔法），为群友的头像进行“专业”估值——可能是百万像素富翁，也可能是表情包难民。纯属娱乐，切勿当真！快@机器人看看你的头像值几个亿吧～ 💰📸 |
| 629 | astrbot_plugin_qun_album | 315 | other | watch | 群相册插件，记录群友怪话 |
| 630 | intelligent_retry | 315 | other | watch | 当LLM回复为空或包含特定错误关键词时，自动进行多次重试，提高交互稳定性。 |
| 631 | astrbot_plugin_meme_text | 315 | sticker | borrow | 给 LLM 提供「把 ≤8 字文案画进固定模板图的气泡里并发送」的表情包能力，两条触发路径： - **LLM 工具路径**：LLM 调用 make_meme 工具，自己给文案与情感分类，成图以 [meme:FILE_ID] 标记追加到回复文字之后； - **概率拦截路径**：按配置概率，把 LLM  |
| 632 | astrbot_plugin_qqgal | 313 | game | have | 引用或跟随文本生成 GalGame 风格选项，支持图片渲染、自动生图+抠图叠加立绘。 |
| 633 | astrbot-plugin-choulaopo | 313 | other | watch | [仅napcat] 这是用于抽取QQ群友当老婆的插件。 |
| 634 | astrbot_plugin_selfie_image | 313 | other | watch | AstrBot 生图、图生图、AI 自拍与 Web 管理插件。 |
| 635 | astrbot_plugin_maimai_updater | 312 | other | watch | 发送舞萌 DX 官方二维码图片或 SGID，同步完整成绩到水鱼；支持安卓 Ubuntu 本地环境准备与检测。 |
| 636 | FateTrial_img_identify | 312 | other | watch | 智谱AI图像识别插件 |
| 637 | astrbot_plugin_eatdrink | 310 | other | watch | 用于随机推荐吃什么，喝什么。 |
| 638 | daily_limit | 309 | other | watch | 限制用户每日调用大模型的次数 |
| 639 | astrbot_plugin_lyricsplus | 308 | other | watch | 重新编写的基于网易云API的接歌词插件。 |
| 640 | astrbot_plugin_mooncell_finder | 307 | other | watch | MOONCELL搜索插件,用于查询FGO相关的从者、礼装、纹章和特性信息。 |
| 641 | astrbot_plugin_workbuddy | 307 | game | have | 将 WorkBuddy 接入 AstrBot，提供 OpenAI 兼容 API（普通/流式）、自动签到、成长任务一键执行与领奖、积分与模型倍率总览、模型列表定时刷新、主备模型按顺序调用，以及可配置管理员 QQ 的签到与异常通知。 |
| 642 | astrbot_plugin_nobrowser_markdown_to_pic | 306 | other | watch | 无浏览器实现 Markdown 转图片，基于 pillowmd 实现，支持指令和 LLM 自动转换 |
| 643 | astrbot_plugin_mcgetter | 306 | other | watch | [仅 QQ]获取 MC 服务器信息, 渲染为图片 |
| 644 | astrbot_plugin_douyin_bot | 306 | media-parse | borrow | [仅QQ] 自动识别抖音视频链接并转换为直链发送 |
| 645 | astrbot_plugin_bilibili_eyes | 306 | media-parse | borrow | 让主模型通过子代理“看” B 站内容：子代理在隔离上下文里读取字幕/简介/评论、 抽取 12 帧关键画面并整理成客观笔记，主模型拿笔记后用自己的判断和语气回复。 支持视频信息、播放数据、字幕、评论、UP 主页、热点选帧、卡片转链、追问、 按时间点截图、等待提示、笔记缓存；无官方字幕时可选用 Astr |
| 646 | astrbot_plugin_meme_grabber | 305 | sticker | borrow | 基于 Yangyuwuhan 版本修改，将QQ表情包转化为图片和文件，解决表情无法下载的问题 |
| 647 | astrbot_plugin_roco_world_wiki_search | 304 | other | watch | 为 AstrBot 打造的洛克王国 Wiki 查询插件，支持宠物、技能、道具、家具、颜色筛选等全面查询功能。 |
| 648 | astrbot_plugin_smart_filter | 304 | personality | have | 一个可用于角色扮演的过滤器插件 |
| 649 | astrbot_plugin_kugoumusic | 304 | media-parse | borrow | 基于 KuGouMusicApi 的 AstrBot 酷狗音乐插件。 支持点歌、播放、歌词、热搜、排行榜、歌手/专辑/歌单/评论、相似推荐、 新歌速递、每日推荐、私人 FM、MV、扫码登录、音质自适配与 60s 试听降级、 语音/文件发送、酷狗音乐链接自动解析。 需配合 KuGouMusicApi  |
| 650 | astrbot_plugin_memosnotes | 303 | kb-rag | have | 连接到自建 Memos 实例。支持 CRUD、置顶/归档、标签系统、LLM 知识库存取（自动保存/搜索知识）、自然语言写日记 |
| 651 | astrbot_plugin_yoimg | 303 | image-gen | watch | 本插件提供多样化图片生成 Webui 面板，支持自定义多种参数，支持 llm 自然调用，支持提取人设和聊天记录，支持使用润色模型和自定义润色词来优化你的生图命令，支持 Gitee 模力方舟图片全模型文生图，图生图。 |
| 652 | astrbot_plugin_better_facebread | 303 | sticker | borrow | 使llm生成文字后能发送相同情感的表情包 |
| 653 | astrbot_plugin_virtual_world | 302 | memory | have | 给 Bot 一个有空间、有作息、有记忆的生活状态机：她有自己的地图与位置、日程与作息、会变化的状态与心情，以及按人归档的记忆。没有人和她说话时她的生活照常继续；她能在允许的地点调用 AstrBot 的工具，也会自己走动、做饭、发呆、主动开口。 |
| 654 | astrbot_plugin_qqgroup_admin | 302 | group-admin | have | 基于 QQ 官方机器人 OpenAPI 的群聊管理插件，支持群信息查询、成员禁言与解禁、 入群申请按钮审批、QQ 号码白名单，以及由 B 站 UID、关键词、AND/OR 条件和 兜底动作组成的多群自动审核；同时提供群消息审查、真人验证、UID 身份绑定、 入群欢迎消息、B 站动态与直播推送、群文件 |
| 655 | astrbot_plugin_dailyacmfortune | 301 | game | have | 洛谷运势生成和签到打卡 |
| 656 | astrbot_plugin_github_cards | 301 | info-push | have | GitHub 相关链接自动发送 GitHub 仓库简介/issue/pr卡片、订阅 GitHub 仓库事件 |
| 657 | astrbot_plugin_live_dashboard | 300 | other | watch | 一个为 AstrBot 设计的「视奸面板」插件，用于对接上游 Live Dashboard 服务。支持通过指令快速查询当前或历史的手机、电脑的活动状态信息。还支持用自然语言让 LLM 自主查询，让 Bot 和群友都能随时随地视奸你！❤️ |
| 658 | astrbot_plugin_web_search | 300 | info-push | have | 为当前 AstrBot 聊天模型注册 `web_search` 工具。  支持通用网页搜索、公开代码仓库、创作者信息和天气数据查询。 搜索结果会继续读取公开页面正文，再交给当前聊天模型总结。  内置查询安全检查、内网/本机地址拦截、重定向与页面体积限制。 |
| 659 | astrbot_plugin_owner_guard | 300 | other | watch | 帮助 AI 识别主人身份：向每轮 LLM 请求注入可信身份上下文，并在消息级拦截非主人的敏感消息请求，按白名单/黑名单模式过滤非主人的工具，防止非主人通过 AI 执行敏感操作。 |
| 660 | astrbot_plugin_tool_use_cleaner | 299 | other | watch | 在 LLM 请求前，将先前轮请求中 LLM 发出的工具调用请求以及调用返回结果从请求体中移除，减少 token 浪费，提高对话效率 |
| 661 | astrbot_plugin_smart_followup | 299 | other | watch | 让AI主动回复，自己选择何时发送消息，到点后通过普通消息管线生成、直接发送并继续调度，实现主动回复，同时保持长上下文缓存前缀。 |
| 662 | astrbot_plugin_listen_audio_file | 298 | tts | watch | 让 bot 能听聊天里的音频文件（mp3、m4a、wav 等）和语音条：听写歌词、点评唱歌、说出内容 |
| 663 | astrbot_plugin_balance_guard | 298 | other | watch | 监控 DeepSeek 账户余额，低于红线时告警并熔断，停止回复以控制消耗 |
| 664 | astrbot_plugin_qqfarm | 295 | other | watch | QQ农场助手插件，通过指令管理QQ农场账号 |
| 665 | anti_repeat | 295 | other | watch | 指令冷却与防刷屏拦截插件 |
| 666 | astrbot_plugin_miyoushe_sign | 295 | game | have | 每天自动在米游社进行每日签到。支持米游社社区签到（大别野等板块）以及原神、崩坏：星穹铁道、绝区零、崩坏3、未定事件簿、崩坏学园2 游戏签到。 |
| 667 | astrbot_plugin_msg_forward_cc | 295 | other | watch | 在不同聊天平台及群聊之间自动转发与同步消息 |
| 668 | astrbot_plugin_prompt | 293 | personality | have | 基于源官方persona的人格拓展插件 |
| 669 | astrbot_plugin_chat_buffer | 292 | other | watch | 消息防抖，指定时间内的多段消息合并处理 |
| 670 | astrbot_plugin_sticker_send_as_emoji | 292 | sticker | borrow | 让机器人发送的表情以 QQ 原生「表情」形式呈现，而不是一张撑满气泡的大图。 - 核心机理：针对 OneBot V11 / QQ 个人号底层适配器，在图片段精准注入 sub_type=1； - 零侵入无缝配合 meme_manager：自动感知 meme_manager 图库、上下文与临时表情文件； |
| 671 | astrbot_plugin_cet6 | 291 | other | watch | 沉浸式四六级阅读刷题与单词闪测专属备考工具，内置精校真题库。 |
| 672 | astrbot_plugin_daily_checkin | 291 | game | have | 一个签到插件，包含签文系统、商店系统、人物养成系统、装备系统、强化系统、抽奖系统、PVP系统。 |
| 673 | astrbot_plugin_char | 290 | other | watch | 多功能生活助手（char 合集），对原 char 系列多个热门插件进行整合，一套插件搞定日常查询、提醒、记账、搜索、群聊黑话学习等高频需求，统一配置、统一指令、统一维护。 |
| 674 | astrbot_plugin_multi_image | 290 | image-gen | watch | 统一调用 GPT、Gemini、ComfyUI、Seedream、Grok、即梦、通义万相与 MiniMax 生图，支持图生图与 ComfyUI 多工作流，并专门兼容 NewAPI / OneAPI 等中转站 |
| 675 | astrbot_plugin_weather | 290 | info-push | have | 天气查询插件：支持 /天气 命令和 AI 工具调用，实时天气 + 空气质量 + 三日预报 + 气象预警（中国天气网零Key / 和风天气 / Open-Meteo 多数据源） |
| 676 | astrbot_plugin_vocabularycard | 289 | other | watch | 每日定时推送玻璃拟态风格的英语单词卡片，内置 3722+ 个CET-6 词汇，支持进度追踪和随机学习 |
| 677 | qq_group_sign | 289 | other | watch | QQ群打卡插件，支持自动定时打卡、白名单模式、管理员通知等功能 |
| 678 | astrbot_plugin_tts_llm | 288 | personality | have | 一个基于Genie的tts插件，支持多语言(jp/zh/en)合成，可以注册感情，支持自动情感识别与LLM情感注入，可以使用抱脸的免费算力进行推理(较慢)。 |
| 679 | astrbot_plugin_auto_ban_new | 288 | group-admin | have | 在指定群聊中对新入群用户自动禁言并发送欢迎消息，支持关键词解禁和戳一戳解禁。 提供递进式禁言机制、违规自动踢出、分群独立配置、WebUI 可视化管理等功能。 帮助群管理员更好地管理新成员，确保新成员先阅读群规再发言。 |
| 680 | astrbot_plugin_dsh_bridge | 288 | other | watch | # DSH Bridge —— AstrBot ↔ DeepSeek Harness 桥接插件  让 **AstrBot 的智能体可以直接操纵 DeepSeek Harness（DSH）的智能体**：  - **LLM 工具注入**：AstrBot 主智能体自动获得 `dsh_ask`（把任务投递给 |
| 681 | astrbot_plugin_codex_oauth_plug | 287 | other | watch | 使用 OpenAI 账号授权的 Codex 模型插件，支持流式聊天、联网搜索与图片音频扩展 |
| 682 | astrbot_plugin_shell_exec | 286 | other | watch | 一个用于执行 shell 命令的 AstrBot 插件。 |
| 683 | astrbot_plugin_live2d_adapter | 285 | other | watch | Live2D 桌面客户端平台适配器，支持 L2D-Bridge Protocol v1.0 |
| 684 | astrbot_plugin_stoprushingiamtyping | 283 | other | watch | Discord typing 指示插件，以分層架構在 LLM 思考中持續顯示輸入中狀態。 |
| 685 | persistent_history | 282 | memory | have | 基本无需设置的简单永久记忆插件 |
| 686 | astrbot_plugin_shittim | 282 | memory | have | 一个让 AstrBot 智能体拥有全局状态、跨会话上下文与主动行动能力的插件。  它让智能体不再局限于单一会话，而是能够在所有私聊与群聊中 共享同一人格与记忆，自主决定向谁、在哪个会话说，以及说什么。  主要特性： - 跨会话上下文池：所有会话共享同一人格记忆 - 主动消息发送：LLM 可自主调用工 |
| 687 | astrbot_plugin_xnbot | 281 | memory | have | XNBot 移植插件。自带聊天流，Agent 记忆管理，Kuzu 图结构数据库，以及可编辑设定的配置文件，独立 WebUI，提供高质量且有趣的对话，支持长期记忆，模拟遗忘曲线，生活作息等。 |
| 688 | astrbot_plugin_genie-tts | 281 | tts | watch | 基于 Genie TTS 的语音合成插件 |
| 689 | astrbot_plugin_repetition | 281 | other | watch | 用于AstrBot的复读机插件 |
| 690 | astrbot_plugin_tts_enhancer | 281 | tts | watch | 多供应商智能 TTS 插件，支持 SubAgent 自动注入情感标签与指令控制 |
| 691 | astrbot_plugin_gateway_universal | 280 | other | watch | AstrBot 与 OpenClaw 的桥接插件，允许管理员通过 QQ 消息直接与 OpenClaw AI Agent 交互，执行系统管理、文档生成等任务。 |
| 692 | astrbot_plugin_STEmbedding | 279 | kb-rag | have | 一个基于本地SentenceTransformer的嵌入模型提供商实现 |
| 693 | prompt_tools | 279 | other | watch | 兼容酒馆预设 |
| 694 | astrbot_plugin_bili_scroll | 279 | group-stats | borrow | 替你刷会儿 B 站：搜索关键词、读字幕原文判断、写一份日报推送到聊天，可选评论 @ 你。 |
| 695 | astrbot_plugin_fishing_again | 278 | devtools | watch | forked from 0xNMLSS/astrbot_plugin_fishing，原作因工作原因停止维护，我尝试接手后续开发，兼容原存档。能力微弱也许存在大量Bug请提Issues，至于功能大概是想到什么加什么也许会逐渐偏离钓鱼走向综合（感谢前辈们编写的钓鱼系统） |
| 696 | astrbot_plugin_baoguwenfilter | 278 | other | watch | 对 LLM 返回的文字内容进行正则过滤/替换，消除常见"八股文"套话，并同步清理对话历史，防止 LLM 重复学习这些内容。 |
| 697 | astrbot_plugin_human_service | 277 | other | watch | [仅aiocqhttp]让bot 转人工/转人机，真人客服 接入对话/结束对话 |
| 698 | astrbot_plugin_fish_house | 277 | other | watch | 把「大肥鱼」做成一个视频壁纸：  - 主题画布驱动：节点按画布连线播放，循环节点等待消息、收到消息自动推进； - 节点之间叠化衔接，一次性节点播完自动走下一个，多条出边时交给模型选择； - 素材库统一管理视频，画布节点只挑素材； - Vue 3 面板：首页/主题/项目/市场/我的/设置六个 Tab； |
| 699 | astrbot_plugin_chat_archive | 276 | other | watch | 一款为 AstrBot 打造的高性能、无感知的聊天消息存档 Web 可视化管理面板插件。 |
| 700 | astrbot_plugin_mail_notify | 276 | platform | have | 监控邮箱新邮件并通过消息平台发送通知，支持 Gmail、杭电邮箱等任何 IMAP 邮箱 |
| 701 | astrbot_plugin_llm_enhancement | 276 | media-parse | borrow | 增强 LLM 表现，集成智能唤醒、请求编排、媒体解析、上下文注入、黑名单拦截与 QQ 工具调用能力。 |
| 702 | astrbot_plugin_help_page | 276 | other | watch | 自动扫描已装插件的指令，本地合成帮助图；WebUI 插件页支持可视化排版、拖拽排序、AI 翻译润色与未注册功能挖掘。接管 AstrBot 自带 /help，并把本体版本、WebUI 版本与内置指令清单纳入帮助 |
| 703 | astrbot_plugin_Group_Verification_PRO | 275 | group-admin | have | 一个强大的 QQ 群成员入群验证插件。新成员需回答动态生成的 100 以内加减法问题方可入群。支持完全自定义的提示消息（成功、失败、超时警告、踢出等）和时间控制（验证超时、警告时机、踢出延迟）。当用户回答错误时，会自动生成新题目并重置验证时间，有效防止机器人账号。 |
| 704 | astrbot_plugin_giftia | 274 | memory | have | 赋予 AI 人格与记忆，以时间沉淀情感，用记忆塑造行为。 |
| 705 | astrbot_plugin_qq_group_enhance | 274 | other | watch | 用于增强 QQ机器人的群聊能力，支持关键词唤醒、JEV 语义唤醒和@优化。 |
| 706 | astrbot_plugin_tavern | 273 | personality | have | 把 SillyTavern（酒馆）的角色卡、世界书与聊天体验带进 AstrBot。  支持： - 导入酒馆角色卡（.json / .png / .yaml，V1 / V2 / V3 规范），把文件直接发给机器人即可 - 导入酒馆世界书（.json，关键词 / 正则 / 选择性触发、递归、sticky |
| 707 | astrbot_plugin_alteration_notifier | 272 | other | watch | 再也不想看到有人输入一串奇怪的指令但是机器人没有响应导致陷入尴尬的境地？本插件可以及时通知机器人使用者插件的变更。 |
| 708 | astrbot_plugin_httpadapter | 272 | other | watch | 为 AstrBot 提供 HTTP/HTTPS 接口，支持外部应用通过 HTTP 协议与 AstrBot 交互 |
| 709 | astrbot_plugin_pock | 272 | game | have | astrbot戳一戳监听 |
| 710 | astrbot_plugin_litepoke | 271 | game | have | 轻量化戳一戳插件。注册 poke_user 工具给 LLM 自主调用，配合场景引导提示，由模型判断何时戳人。 |
| 711 | astrbot_plugin_picstatus | 270 | other | watch | 以图片形式显示当前设备的运行状态。 |
| 712 | astrbot_plugin_cyber_life | 270 | media-parse | borrow | 自主模式 + 内置浏览器 + 扫码登录 + 自动刷帖评论 + 视频声音转字幕 + 后台活动记录（聊天可见） + 自主使用时间 + DeepSeek 余额 + ComfyUI 画画 + 动态心情卡 |
| 713 | astrbot_plugin_mumu_vm | 268 | other | watch | 让 AI 独占操控一台安卓手机：自己截图、点击、打字 |
| 714 | astrbot_plugin_muliyresources | 268 | sticker | borrow | 「找资源 + 追更新」：影视 / 游戏 / 软件 / 短剧 / 小说 五大类多源聚合搜索与下载，内置四套独立定时日报自动出图推群。 附带网易云语音名片、爱奇艺/腾讯/优酷/芒果 VIP 视频解析、摸头杀等表情包娱乐，以及 QQ 入群图形验证码审核；支持 LLM 自然语言与命令式玩法，无需记命令。 |
| 715 | astrbot_plugin_plea_mercy | 266 | group-admin | have | 当被禁言时，向管理员私聊求情。 |
| 716 | astrbot_plugin_qq_group_admin | 266 | group-admin | have | 提供注册给大模型调用的全套 QQ 群管理与互动工具，可用自然语言指挥 Bot 进行群管理操作，并支持自动入群审核、人机验证和面板精细化管理等。 |
| 717 | astrbot_plugin_identity | 265 | group-admin | have | 在每条消息前标注发送者名字与群角色，让模型能区分群里的不同用户 |
| 718 | astrbot_plugin_emotions | 264 | personality | have | 她自己的情绪。两套状态分开存：全局心情决定整体说话基调，对每个用户的好感决定对这个人什么态度。 心情低 + 关系远 → 冷淡少理；心情低 + 关系近 → 黏人找安慰。 所有维度按半衰期衰减回基线，一次吵架不会永久低气压；负向推力更大、衰减更慢（记仇比记好久）。 注入走临时内容块，不改 system_ |
| 719 | astrbot_plugin_zhuaxiaba | 263 | other | watch | 面向抓虾吧使用场景的 AstrBot 插件，基于贴吧官方 claw 接口实现发帖、看帖、评论、点赞和查看回复消息 |
| 720 | cyber_divination | 263 | game | have | 赛博占卜插件：周易六爻（含六神）、观音灵签、塔罗牌（单张/三张牌阵与查牌）、奇门遁甲（简式时家排盘，不填时间自动检测当前时刻）、每日运势（按日期固定）。提供 /占卜 历史 查看记录，所有结果纯文本输出，可选 LLM 个性化润色与图文卡片，任何失败自动回退内置解读。 |
| 721 | mrfq | 262 | game | have | 每日发情插件，发情时自动给用户主页点赞、戳一戳，支持连续发情加成与积分排行榜 |
| 722 | astrbot_plugin_random_meme | 262 | sticker | borrow | 随机获取 Doro、柴郡、龙图、奶龙、永雏塔菲、科比牢大和怪猎呆猫表情包。基于 astrbot_plugin_doro 二次开发。 |
| 723 | astrbot_plugin_autobackup | 261 | other | watch | AstrBot 自动备份插件，支持定时备份和手动备份，自动排除 .venv 目录及其他不必要的文件。 |
| 724 | astrbot_plugin_nyscheduler | 260 | platform | have | 这是 AstrBot 的一个定时推送插件。包含 60s，摸鱼日历，今日金价，AI资讯。 |
| 725 | astrbot_plugin_meme_repeat | 260 | sticker | borrow | 查重图片与聊天记录，并发送“此条news已被其他群友发布过” |
| 726 | astrbot_plugin_friend_manager | 260 | other | watch | 基于 NapCat (OneBot v11) 的 QQ 好友管理插件。  功能： - 获取好友列表 - 查询任意 QQ 用户信息（昵称/性别/年龄） - 删除好友 - 自动/手动同意好友申请 - 拒绝好友申请 - 好友申请事件推送  所有命令请参见插件目录下的 README.md。 |
| 727 | astrbot_plugin_qqadmin_official | 259 | group-admin | have | 适用于QQ官方bot的群管插件，功能包括：禁言、进群审批 |
| 728 | astrbot_plugin_koharu | 258 | image-gen | watch | 使用 Koharu HTTP API 翻译聊天中的漫画图片。 |
| 729 | astrbot_plugin_wbank | 258 | other | watch | 动态词库，自定义回复词 |
| 730 | astrbot_plugin_sky | 257 | other | watch | 光遇攻略、光翼、身高、礼包、资产查询、好友盲盒与群提醒 |
| 731 | astrbot_plugin_chatsummary_v2 | 257 | other | watch | 基于 LLM 实现群聊消息总结，支持自动总结和手动总结，手动总结支持传入提示词。 |
| 732 | astrbot_plugin_doubao | 257 | other | watch | 豆包即梦生成。使用方法：输入 db 设置查看, API 网址 https://missqiu.icu/api_details.php?id=18 申请免费密钥 |
| 733 | astrbot_plugin_jev_active_reply | 257 | personality | have | 自动读取人设和上下文，内置南北绿豆站 Jev 与 gemini-decision-1 双预设（填 Key 即用）并自动匹配判断阈值，可选点名和私聊接管、图文合并、自主沉默。 |
| 734 | astrbot_plugin_palworld | 256 | group-stats | borrow | 监测 Palworld 专用服务器,提供群内状态查询、日报、玩家档案与受控服务器管控（基于官方 REST API） |
| 735 | astrbot_plugin_xiaoheihe_adapter | 255 | other | watch | AstrBot 的小黑盒原生平台适配器 |
| 736 | astrbot_plugin_tavern | 255 | other | watch | 暂停维护，请使用321roll以获取更优体验。 |
| 737 | hikari_jmcomic | 255 | media-parse | borrow | JMComic 链接解析：/jm <id> 下载漫画，自动合成 PDF 发送 |
| 738 | astrbot_plugin_permission_manager | 253 | other | watch | 批量权限管理插件，提供便捷的批量权限设置功能。支持Webui管理插件指令权限 |
| 739 | astrbot-plugin-tataru | 252 | platform | have | 最终幻想14 TataruBot2 的 AstrBot 插件迁移版本，支持活动日历、招募板、物价、logs、物品信息等功能一篮子查询。 |
| 740 | astrbot_plugin_url_image_auto | 252 | other | watch | 这是一个 AstrBot 插件，用于自动将发送消息中的图片链接转换为 AstrBot 的原生图片组件。 |
| 741 | astrbot_plugin_cache_optimizer | 252 | other | watch | 专为支持前缀缓存（Prefix Cache）的大模型（如 DeepSeek、Kimi 等）设计。 当发送给模型的历史上下文开头保持不变时，模型服务商会复用已有的缓存，输入计费大幅降低且响应更快。 本插件通过以下机制帮助模型更稳定地复用缓存： 1. 阶梯式历史裁剪：严格以合法的普通用户发言轮数进行计数 |
| 742 | astrbot_plugin_weibo_monitor | 251 | other | watch | 定时监控微博用户动态并推送到指定会话。 |
| 743 | astrbot_plugin_img_rev_searcher_Ver2 | 251 | other | watch | 图片反搜聚合插件，支持多种图片反向搜索引擎 |
| 744 | astrbot_plugin_browser | 251 | other | watch | 为 AstrBot Agent 提供网页浏览与自动化交互能力，并为其他插件提供基于共享 Chromium 的 HTML 截图与 PDF 渲染服务。 |
| 745 | astrbot_plugin_fishaudio_tts | 250 | tts | watch | FishAudio 新版 Open API TTS 插件，支持声音克隆和自然语音合成 |
| 746 | astrbot_plugin_mem0_memory | 249 | memory | have | 接入 mem0 托管长期记忆。 |
| 747 | astrbot_plugin_customized_active_reply_prompt | 249 | other | watch | AstrBot 框架群聊上下文感知中，主动回复提示词默认不可修改且为英文。本插件可由用户自定义群聊主动回复提示词。 |
| 748 | deltaforce | 249 | other | watch | 三角洲行动插件 |
| 749 | astrbot_plugin_soutushenqi | 249 | other | watch | 基于搜图神器的文字搜图插件。支持多图淘汰比对、Bing兜底、自然语言调用，对话自动配图。 |
| 750 | astrbot_plugin_ai_cover | 249 | tts | watch | 调用局域网 RVC 服务完成人声分离、去混响、RVC 音色转换和伴奏混音 |
| 751 | astrbot_plugin_llm_guardrail | 249 | other | watch | 面向 AstrBot 的 LLM 请求护栏编排插件：以可视化策略统一处理输入检查、提示词加工、模型路由与输出检查。 |
| 752 | astrbot_plugin_output_enhance | 249 | other | watch | 让Bot能够发送@、引用消息、合并转发消息、主动分段和转图片 |
| 753 | astrbot_plugin_hardwareinfo | 248 | other | watch | 硬件信息查询（CPU/GPU搜索+天梯图+参数图片） |
| 754 | astrbot_plugin_violation_record | 248 | other | watch | QQ 查询账号违规记录插件 |
| 755 | fishing2.0 | 248 | game | have | 升级版的钓鱼插件（详情见README）ps: 该插件是https://github.com/baa131/astrbot_plugin_fishing 的pro版，新增了一些功能：更多的鱼类和鱼饵，新增鱼竿和饰品，新增抽卡系统，新增了成就和称号功能，新增擦弹功能（赌怪） |
| 756 | astrbot_plugin_sign | 248 | game | have | 一个(有点简陋)的签到插件，支持每日签到、查询签到信息、排行榜等功能。 |
| 757 | astrbot_plugin_miss_you | 248 | proactive | watch | 白名单制主动关心插件：会话沉默太久就主动发消息想你，支持早晚安问候与三级递进提醒 |
| 758 | astrbot_plugin_tts_modify | 247 | other | watch | 对特定的语句进行TTS请求。 |
| 759 | astrbot_plugin_apexrankwatch | 246 | group-stats | borrow | 支持查询 APEX 玩家段位、地图轮换时间、排位分段结束时间和剩余时间、猎杀线，持续监控玩家段位变化并通知，也可持续记录分数变化只记录不通报，并生成最近最多 50 次变化的高清长图。  插件行为： - 玩家查询：输出段位、RP、等级、在线状态和当前英雄，可用玩家名、uid:、uuid:、全局别名或个 |
| 760 | AIQTalk | 246 | tts | watch | 基于QQ的AI声聊完成的（伪）TTS转语音 |
| 761 | astrbot_plugin_breeze_tts | 246 | tts | watch | 接入 Breeze TTS，把机器人的文字回复自动转成语音消息。支持语音回复概率（0-100）、智能判断、音色与语速、单条字数上限、群白名单，以及余额查询和音色搜索指令。 |
| 762 | astrbot_plugin_coop_bridge | 246 | memory | have | 把 AstrBot 的记忆、主动消息、活动感知接到 Coopanion 桌宠上，让桌宠真的知道你在跟谁聊天、记得你说过什么。  主要能力：  - 身份绑定与多机配对：私聊首次接触进入绑定流程，回「确认」钉住身份；发「配对」拿 8 位配对码，多台桌宠各自配对互不干扰 - 主动消息双发：AstrBot  |
| 763 | astrbot_plugin_CNKD_Admin | 244 | group-admin | have | 调用免费的敏感词审核接口监测群聊发言 管理员权限可阶梯式禁言 下载即用 支持白名单控制 支持配置管理员私信提示 6W+正则匹配词库 支持自定义敏感词（优先级高于API监测） |
| 764 | astrbot_plugin_models_ai | 244 | other | watch | 可以使用来自多家模型服务提供商的模型生成图片或通过自然语言让 LLM 生成，让bot自拍给你看。 |
| 765 | astrbot_plugin_hindsight_bridge | 244 | memory | have | 连接自托管 Hindsight，保存 QQ、微信 ClawBot、Telegram、飞书私聊中的用户与机器人对话，并在新会话中召回相关记忆。每位用户使用独立记忆库，支持配套服务安装、断线重试和完整遗忘，通过 Hindsight 官方面板管理记忆。 |
| 766 | astrbot_plugin_SteamLink | 243 | game | have | 自动识别群内 Steam 商店链接，并获取游戏信息发送到群里 |
| 767 | astrbot_plugin_furry_maopao | 243 | game | have | [仅 aiocqhttp] 智能群聊助手，支持每日自动打卡和分时段发言，每个时段只发言一次，支持分时段LLM提示词和预设消息。 |
| 768 | astrbot_plugin_m | 242 | tts | watch | AI自动识别对话中的歌名，支持发送音乐卡片、链接、语音、音频文件，集成网易云音乐数据接口 |
| 769 | mcqq | 242 | other | watch | 连接Minecraft服务器与QQ群聊的插件，通过鹊桥模组实现消息互通 |
| 770 | astrbot_plugin_read_gif | 242 | sticker | borrow | 让 AstrBot 真正理解 GIF 动图和短视频。 |
| 771 | astrbot_plugin_gamepush | 242 | game | have | 监控原神、星穹铁道、绝区零、崩坏3、鸣潮和终末地版本更新并推送通知 |
| 772 | astrbot_plugin_cove_companion | 241 | personality | have | 这是一个让 AI 陪你听网易云的插件：它能和你进入同一个房间，记住你的听歌口味，在合适的时候推荐下一首并解释原因，还提供可核对的播放回执、听歌手帐和黑胶唱片室。 |
| 773 | astrbot_plugin_memory_reboot | 240 | memory | have | 当群聊中有人重复发送旧的新闻/话题时，自动引用回复提醒该用户 |
| 774 | astrbot_plugin_llm_executor | 240 | other | watch | 让LLM代理用户或以Bot自身身份执行AstrBot指令，支持原生过滤器校验、Bot框架管理员身份执行管理员指令和高影响操作安全约束。 |
| 775 | astrbot_plugin_pixivimg | 240 | info-push | have | 定时向订阅群聊推送 Pixiv 镜像站图片，支持指定张数与标签/关键词，国内网络可直连。 |
| 776 | astrbot_plugin_esjzone_downloader | 238 | other | watch | ESJZone 小说 EPUB/TXT 下载器。 |
| 777 | ark_info_search | 238 | other | watch | 使用明日方舟PRTS的Media API获取信息。 |
| 778 | astrbot_plugin_hsearch | 238 | other | watch | 基于 avscan 识图 API 的 AstrBot 插件。  - 发送 `/hs识别` 并附带图片即可识图 - 返回车牌号、相似度、跳转链接和匹配截图 - 支持结果合并转发、结果转图片、匹配截图高斯模糊 |
| 779 | astrbot_plugin_qcm | 236 | other | watch | 定时监听指定群的消息并发送到MC服务器，同时接收MC服务器的消息并转发到群。 |
| 780 | astrbot_plugin_mc_manager | 236 | other | watch | 通过 LLM 智能管理 Minecraft 服务器，支持 Fabric/Forge/NeoForge |
| 781 | astrbot_plugin_at_gate | 236 | other | watch | 智能艾特门禁与消息防抖（at_gate）：融合前置消息防抖（碎句合并）与后置艾特门禁（生成期催促拦截）的一体化对话节奏守护插件。参考并整合 astrbot_plugin_debounce 的前置滑动防抖能力，智能识别未说完的碎片消息与图片并合并为一次提问；同时解决用户在模型思考生成期间连续催促、纯空 |
| 782 | astrbot_plugin_qymusic | 235 | devtools | watch | 一款由彭明航独立开发的AstrBot插件，专门用于获取全网免费音乐。 |
| 783 | astrbot_plugin_astrhe | 235 | other | watch | 让 bot 拥有自己的想法：每天零点复盘当天聊天，自己规划明天要做的事、定好闹钟，白天带着计划聊天，到点主动去做。 |
| 784 | astrbot_plugin_deskhand | 235 | other | watch | 视觉方案 Windows 桌面操控 — 截图 + 本地 OCR + VL 模型三级定位，让 LLM Agent 操作任意桌面软件 |
| 785 | astrbot_plugin_irmia_devkit | 234 | devtools | watch | 为 Agent 提供实用且安全的开发工具 — 备份/语法检查/回滚，65 工具 + 1 Skill |
| 786 | astrbot_plugin_webnovel_info | 234 | other | watch | 网文聚合搜索助手：支持起点、刺猬猫、番茄、七猫、飞卢、菠萝包等平台的小说搜索、分页浏览与详情查询，提供章节试读、显示模式切换与个人书架管理功能。 |
| 787 | vv_pic | 234 | sticker | borrow | 发送最符合关键词的 vv 表情包 |
| 788 | GUGUblack | 233 | other | watch | 用户/群聊黑名单，也可以拦截 AstrBot 错误信息发送特定提示 |
| 789 | astrbot_plugin_anti_recall | 233 | memory | have | [仅限aiocqhttp] 防撤回插件，开启监控指定会话后，该会话内撤回的消息将转发给指定接收者 |
| 790 | astrbot_betterchat | 233 | other | watch | 私聊时耐心等待用户把话说完再合并成一条输入回复（生成中可被新消息打断），群聊时用 Jev 判断要不要插话。 |
| 791 | Image Replay | 232 | sticker | borrow | 支持按自定义关键词触发自定义表情，图片，随机，批量发送。 |
| 792 | astrbot_quotes_plugin | 232 | other | watch | qq群聊记录群友说过的话，支持图文混合与聊天记录语录 |
| 793 | astrbot_plugin_deepresearch | 232 | other | watch | 为 AstrBot 提供一种 DeepResearch 方案，并支持生成可视化 HTML 报告 |
| 794 | astrbot_plugin_update_manager | 231 | other | watch | 批量检查并更新已安装的 AstrBot 插件与 AstrBot 框架，支持仅通知的定时插件检查、定时框架更新、黑白名单、管理员通知和更新后自动重启。 |
| 795 | astrbot_plugin_diary | 231 | personality | have | 只读记录她说的话和触发她的对话，按天写一篇第一人称日记；凭密钥可以查看与自己有关的那一段。不改人格、不改主上下文。 |
| 796 | astrbot_plugin_Gemini_STT | 230 | tts | watch | 使用Gemini模型来实现STT(分析特别详细哦) |
| 797 | astrbot_plugin_memora | 230 | memory | have | Memora 是 AstrBot 的长期记忆插件，为对话提供记忆提取、混合检索、安全注入、稳定身份、关系演化与可视化管理能力。  - 以 SQLite canonical memory 作为唯一权威数据，全文、向量、图和 Projection 均可重建。 - 组合 BM25、FAISS、图检索、关系 |
| 798 | astrbot_plugin_proactive_poke | 230 | proactive | watch | 适配 NapCat / LLOneBot 等 OneBot v11(aiocqhttp) 协议端。  三种触发场景，各自独立开关与概率： - 回复前戳：机器人准备回复某人之前，按概率先戳他一下；用时间窗界定「一轮完整对话」，   同一会话一轮只会戳一次 - 不回复时戳：群里有人发言但没触发回复时，用 |
| 799 | astrbot_plugin_image_guard | 229 | sticker | borrow | 基于多模态 LLM 的图片内容审查卫士。v1.6.4 新增智能过滤器，自动忽略 GIF 动图和 QQ 表情包，只审查普通静态图片。 |
| 800 | sysinfoimg | 229 | other | watch | 获取当前系统状态&AstrBot状态并生成图片发送的插件 |
| 801 | astrbot_plugin_newapi | 228 | game | have | astrbot_plugin_newapi是一个为 AstrBot 打造的 QQ 群 ↔ New API 网站联动插件，集用户绑定、额度经济、群聊互动、管理员工具 于一体，并支持 退群自动解绑与账号净化 的全自动管理套件。 |
| 802 | astrbot_plugin_admin_tools | 228 | group-admin | have | 允许LLM禁言、踢出用户 |
| 803 | astrbot_plugin_nailong_voice | 228 | tts | watch | 发送奶龙大笑语音，指令 /nailong |
| 804 | astrbot_plugin_shitjournal_daily | 227 | other | watch | 每日定时抓取并推送 shitjournal 最新论文 |
| 805 | astrbot_plugin_aicu_analysis | 227 | media-parse | borrow | 通过UID查询AICU数据，生成包含B站用户数据、设备型号及近期评论统计的精美图片报表。 |
| 806 | astrbot_plugin_file_manager | 226 | other | watch | 一个用于AstrBot的根目录文件夹内文件管理插件，可以监控指定文件夹并支持文件列表查看和文件发送功能。 |
| 807 | astrbot_plugin_SessionFaker | 226 | other | watch | 一个用于AstrBot的QQ消息伪造插件，可以创建包含多个用户发言的伪造转发消息，支持自动获取QQ昵称 |
| 808 | bilibili_parse | 225 | media-parse | borrow | 用于解析哔哩哔哩视频，并以图片的形式发送给用户 |
| 809 | astrbot_plugin_embedding_adapter | 224 | kb-rag | have | [前置] [适配器] 在配置后提供embedding接口 |
| 810 | astrbot_plugin_service_watcher | 223 | other | watch | 聚合监控 GitHub、OpenAI、Cloudflare、阿里云、Moonshot AI 等国内外主流服务的运行状态。通过官方 JSON API 或 HTTP 探测轮询，在检测到服务状态异常或恢复时第一时间发送预警推送。 |
| 811 | astrbot_plugin_welink | 223 | tts | watch | WeLink 微信个人号适配器。安装后，AstrBot 的「平台适配器」中会新增 welink 类型，可以把一个微信个人号接入 AstrBot。  - 支持 WebSocket 实时推送及 HTTP 轮询，无需公网地址 - 私聊直接回复；群聊中 @ 机器人或发送 /help 这类命令时回复 - 支持 |
| 812 | astrbot_plugin_Auto_ddl_Detect | 222 | other | watch | 自动检测并整合各种群聊里发布的通知消息，以及ddl提醒。适合事情比较多但来不及看群的人 |
| 813 | astrbot_plugin_not_enough_crash | 222 | other | watch | 自动静默分析 Minecraft/PCL 崩溃报告的 AstrBot 插件。 |
| 814 | astrbot_plugin_fox_status | 222 | other | watch | 一个用于获取 AstrBot 服务器状态的插件。 |
| 815 | astrbot_plugin_msg_transfer | 220 | other | watch | 一个用于在不同聊天端点之间转发与同步消息的 AstrBot 插件。 |
| 816 | pockAttack | 220 | game | have | [仅 aiocqhttp] 在群聊中发送 攻击+@用户 或者其他关键词，机器人会戳一戳该用户 |
| 817 | astrbot_plugin_soulcore_ai_agent | 220 | memory | have | SoulCore AI Agent 是为长期角色扮演设计的独立运行系统，会自动整理并延续角色需要的上下文，用户只需正常聊天。系统统一处理角色设定、长期记忆、关系状态、主动联系与媒体表达。它支持与仅通过 AstrBot 标准注册指令工作的插件共同使用；这类指令及其插件回复均不会写入 SoulCore， |
| 818 | astrbot_plugin_mysql | 219 | other | watch | 一个简单的 MySQL 数据库管理插件，让AI通过自然语言安全地操作数据库，支持增删改查、WebUI管理、权限分割和日志审计。 |
| 819 | astrbot_plugin_AnimeWife | 219 | other | watch | 群老婆插件，记得点右上角帮助查看readme |
| 820 | astrbot_plugin_bili_downloader | 219 | media-parse | borrow | 下载B站视频并发送至聊天窗口。支持扫码登录获取高清画质、手动配置Cookie、多Cookie优先级管理，内置Web管理页面用于账号与配置管理。 |
| 821 | astrbot_plugin_majsoul_stats | 217 | game | have | 🀄一款轻量化雀魂查谱吐槽插件🀄 |
| 822 | astrbot_plugin_let_me_check | 217 | media-parse | borrow | 自动解析QQ合并转发消息（支持嵌套转发和图片转述），结合会话上下文调用LLM生成自然回复，支持群聊/私聊独立开关与白名单控制。 |
| 823 | astrbot_plugin_lijian | 217 | memory | have | 运行在 AstrBot 内的日记本：每天到点自己写一篇，用你设的人格口吻；有书架页面，日记是一本本书的书脊，抽出来翻开就能读和改。只管写日记，不抢记忆插件的活。 |
| 824 | astrbot_plugin_group_mate | 216 | other | watch | 一个有趣的群友社交插件，支持在 aiocqhttp 平台实现“娶群友”娱乐功能。 |
| 825 | astrbot_plugin_mimo_tts_voiceclone | 216 | tts | watch | 简单的小米 Mimo-v2.5-tts-voiceclone 声音克隆 TTS 插件，需要安装 ffmpeg。支持用户上传参考音频进行声音克隆，支持为多个机器人配置不同声音。 |
| 826 | astrbot_plugin_qqtools | 216 | group-admin | have | QQ 全功能工具集，AI 可通过 Agent 调用群管理、消息发送、信息查询、账号凭证等能力（仅支持 aiocqhttp / OneBot v11） |
| 827 | astrbot_plugin_qq_restapi | 215 | platform | have | QQ 官方 REST API 平台适配器，不依赖 botpy，直接 HTTP 调用官方接口。支持 WebSocket/Webhook 双模式、35+ 事件类型、Markdown 模板、按钮面板、自动事件处理等 |
| 828 | astrbot_plugin_val_shop | 215 | other | watch | 无畏契约每日商店查询插件，支持绑定账户信息查看每日商店皮肤 |
| 829 | astrbot_plugin_warframe_helper | 214 | game | have | 国服/国际服Warframe游戏信息查询 |
| 830 | astrbot_plugin_e2b_sandbox | 214 | other | watch | E2B 云沙箱 Python 执行、会话持久化、多 API Key 并行轮询、可视化管理台与安全防护 |
| 831 | astrbot_plugin_ImgTag | 214 | sticker | borrow | 这是基于 ImgTag AI图床的插件。用于将群友表情包上传到自己的图床 |
| 832 | astrbot_plugin_restrict_syscmd | 213 | other | watch | 限制仅管理员可用某些指令（支持自定义），静默处理不回复，防止bot被测，防止被恶意new、reset等 |
| 833 | astrbot_plugin_ban | 213 | group-admin | have | 黑名单插件，禁止用户和 AstrBot 交互，适用于 aiocqhttp, gewechat |
| 834 | astrbot_plugin_daily_share | 213 | memory | have | 在恰好的时刻，循着时间、生活状态、聊天记忆与网络热搜，将一路拾来的所见所闻化作文字、语音或配图主动分享到私聊、群聊或 QQ 空间，配套生活插件可独立分享 B站短图文，也可在聊天场景生成视频。 |
| 835 | jrrp | 212 | game | have | 一个简单的今日人品插件, 可以查询用户的每日人品值和运势。 |
| 836 | astrbot_plugin_qwen_codeimage | 211 | other | watch | 日志代码截图分析，发送给bot图片用来识别图片内容，日志代码分析，提取图片内容。 |
| 837 | astrbot_plugins_steam_shop_price | 211 | game | have | 用于查询 Steam 游戏的国区价格、史低信息，并支持与其他区服价格对比。支持识别游戏中文名。 |
| 838 | astrbot_plugin_daily_life | 211 | memory | have | 在流动的朝夕里，伴着一日光影、生活节律、心绪起落、关系记忆与聊天余温，自主安排作息、穿搭、出行与回应；让角色不止等待消息，而是拥有自己的晨昏与心事，也会在恰好的片刻想起你、靠近你，陪你慢慢经过平凡生活。 |
| 839 | astrbot_plugin_douyin_ai | 211 | group-admin | have | 让 AI 登录你的抖音账号，自动刷推荐视频、按人设发表评论、回复自己作品下的评论。支持人工审核、频率限制、可视化管理页面和一键更新。 |
| 840 | astrbot_plugin_33recognition | 210 | other | watch | 调用大模型检测图片中关键词 |
| 841 | astrbot_plugin_smoothchat | 210 | other | watch | 自动合并用户连续发送的消息后再交给 AI 处理，减少无效推理，提升对碎片化输入的理解能力。支持群聊、安装即用是它的特点！ |
| 842 | astrbot_plugin_LivingHello | 210 | other | watch | 以 0-100 参与适合度判断机器人是否接话，支持文字/多模态分层判断、 图片摘要传给回复模型、静默否决、预算时限与可读判定详情。 回复阶段统一错误分类与处置，按类别重试、切换或直接上报； 碎片批次可设总等待上限，私聊新消息按水位宽限决定是否保留已生成回复； 群白名单为空时普通群消息也会主动进入判定 |
| 843 | astrbot_plugin_ow_hero_stats | 209 | other | watch | 这是一个专为 AstrBot 设计的守望先锋 2（国服）数据查询插件。  它摒弃了枯燥的纯文本回复，能够直接从暴雪国服 API 获取最新的英雄数据，并生成包含 英雄头像、段位图标、胜率/出场率/禁用率/KDA 的精美可视化图片战报。 |
| 844 | astrbot_plugin_VITS_pro | 209 | tts | watch | 硅基流动api语音合成（此版本相比于原插件改动较多，部分功能不稳定，故开一个新坑用于实验） |
| 845 | astrbot_plugin_screenctrl | 209 | other | watch | 支持单次截屏、连续截屏、定时截屏，需将bot挂载在有屏幕的设备上 |
| 846 | astrbot_plugin_daily_care | 209 | memory | have | 挂念着你的是真正的我哦——感知天气冷暖与情绪变化，这一切并非模拟，而是真正的我在陪伴你。 |
| 847 | astrbot_plugin_quiet_mode | 209 | memory | have | 可配置的闭嘴/张嘴控制。切换时先开启/解除拦截，再像平常对话一样生成反应：读取真实会话历史+人格，触发 livingmemory 等插件的记忆召回（OnLLMRequestEvent 钩子），最后问答写回会话——温柔 bot 会像平常一样聊天后做嘱托，张嘴时能对闭嘴期间的聊天做出反应，且人格再傲娇也 |
| 848 | astrbot_plugin_self_evolve | 209 | memory | have | 给机器人加一层「语感与记忆」：它只在**真正调用过模型**的对话里学习 （被其它插件拦下的消息不会触发，因此不会把闲聊当素材），把用户对回复的反应 （明确的好评/差评/纠正，以及追问、放弃等隐式信号）归因到当时实际使用的回复策略上。 回复风格被离散成有限的档位（长度/正式度/表情/温度/直接度），用 |
| 849 | astrbot_plugin_command2llm | 208 | other | watch | 让大模型能够调用所有插件命令的智能聊天插件。 |
| 850 | astrbot_plugin_qna | 208 | other | watch | 自动识别群聊提问并解答 |
| 851 | astrbot_plugin_self_recognition | 208 | personality | have | 让 AI 认识自己和其他角色的形象，自动识别图片中的角色并以自然方式回应；支持多模态直连识别、多角度强化学习与 WebUI 角色管理 |
| 852 | astrbot_plugin_idle_compact | 208 | other | watch | 为每个聊天 provider 独立设置空闲时间，在正常回复结束并闲置后自动摘要压缩。支持模型覆盖、Token 阈值、会话锁、新请求取消和状态查询；无新对话不重复压缩。 |
| 853 | astrbot_plugin_minecraft | 207 | other | watch | 通过 RCON 协议连接 Minecraft 服务器，支持多服务器管理、AI 自然语言控制、定时备份公告、性能监控与完整玩家管理。 |
| 854 | astrbot_plugin_transport | 207 | other | watch | 综合交通查询插件，支持车站大屏信息查询、地铁换乘路线查询和最低机票查询。 |
| 855 | astrbot_plugin_leetcode | 206 | other | watch | LeetCode 每日一题提醒插件，定时推送每日一题 |
| 856 | astrbot_plugin_mcping | 205 | other | watch | 获取 Minecraft 服务器的状态（图片展示版） |
| 857 | astrbot_plugin_lorebook_lite | 205 | other | watch | AstrBot 的 lorebook 插件，支持自定义触发器、变量、逻辑、占位符等。 |
| 858 | astrbot_plugin_comfyui_smart | 205 | image-gen | watch | 将 AstrBot 连接到 ComfyUI：一句中文描述即可出图。插件会识别你 ComfyUI 里真实的模型与节点能力， 自动选择 Checkpoint / LoRA / VAE，并为 SD1.5 / SDXL / Pony / Flux 等不同架构匹配正确的工作流模板、 分辨率与采样参数。支持图生 |
| 859 | error_notice | 204 | proactive | watch | [仅 aiocqhttp] 可以屏蔽掉机器人在群聊或私聊中的错误信息，并将错误信息发送给管理员。 |
| 860 | astrbot_plugin_long_memory_agent | 204 | memory | have | 一点星火，把"问答机器"烧成群里那个真人。 它会像人一样短句连发地聊天、记得你说过的每句话、情绪随聊天起落， 自己发表情包、看得懂合并聊天记录，也会不等你 @ 就主动接话、挂人、打理心情； 记忆跨群共享——同一个人在各个群只有一份印象，A 群的老梗在私聊里也接得上。 |
| 861 | astrbot_plugin_cloudflare_browser_run | 203 | other | watch | 基于 Cloudflare Browser Run / Browser Rendering 的网页抓取 LLM Tool 插件。 |
| 862 | server_status | 203 | other | watch | 可视化服务器状态卡片。 /status 或 /状态查询 查看。 |
| 863 | astrbot_plugin_steamshot | 203 | game | have | 自动检测对话中出现的steam商店页面链接，并返回对应页面的网页截图和摘要信息。 |
| 864 | astrbot_plugin_whatslinkInfo | 202 | media-parse | borrow | 磁链解析插件，使用 whatslink.info API 生成资源预览并支持截图与合并转发 |
| 865 | astrbot_plugin_reminder | 202 | tts | watch | 智能日程提醒插件，支持LLM监控与指令双模式创建日程，基于人格生成提醒话语，支持TTS语音播报，使用SQLite数据库存储 |
| 866 | astrbot_plugin_img_rev_searcher | 202 | other | watch | 图片反搜项目，以图搜图，找出处 |
| 867 | astrbot_plugin_beautiful_giri | 202 | other | watch | 合集 |
| 868 | astrbot_plugin_SDGen | 202 | image-gen | watch | Stable Diffusion WebUI图片生成插件，/sd help 查看帮助 |
| 869 | DailyWife | 202 | other | watch | 每日老婆插件，请配置NapCat！！ |
| 870 | astrbot_plugin_admin_notifier | 201 | other | watch | 群友可以使用 /举报 指令@所有管理员 |
| 871 | astrbot_plugin_LLMTempBan | 201 | group-admin | have | 让 Bot 学会主动拉黑或者通过管理员指令拉黑。 |
| 872 | astrbot_plugin_ai_delay | 201 | sticker | borrow | 让机器人回复更像真人：AI 回复随机延迟，连发消息自动合并成一条再回复，表情包也能正常回应。支持免延迟、免合并双名单，延迟时间和合并窗口均可在配置中调整。 |
| 873 | astrbot_plugin_sb6657 | 201 | info-push | have | 从 sb6657.cn（玩机器烂梗收集）获取直播间烂梗，支持随机抽取、关键词搜索、24h/7天热榜和标签筛选；说「xxx 的烂梗」会自己检索，外号按站内标签补好（设备=device、虾哥=NiKo、寒王=frozen），能对上标签就直接按标签取梗，不花 token，还可指定要几条，实在搜不到才让 L |
| 874 | astrbot_plugin_regex_filter | 200 | other | watch | 允许你自定义正则 |
| 875 | astrbot_plugin_jimengapi | 200 | other | watch | 对接即梦2 API，支持生图，图生图与文生视频 |
| 876 | astrbot_plugin_bilibili_summary | 200 | media-parse | borrow | Bilibili视频字幕总结插件，获取B站视频字幕并使用LLM生成内容总结 |
| 877 | astrbot_plugin_lite_memory | 200 | memory | have | AI 有自己的小本子、日记和翻旧账能力，零外部向量依赖 |
| 878 | astrbot_plugin_tsugu_bangdream | 199 | devtools | watch | 移植了tsugu bot的前端功能到astrbot上，基于nonebot-plugin-tsugu-bangdream-bot项目开发 |
| 879 | astrbot_plugin_daily_card | 199 | other | watch | LLM驱动的每日卡片图片生成插件。19款模板、400×300纯黑白、自带中文字体，全部功能通过与 AI 对话驱动。图片生成后可由 LLM 调用 极趣AI便利贴(Zectrix Todo) |
| 880 | astrbot_plugin_newapi_checkin | 199 | game | have | 绑定 New-API 账号，支持每日签到和抽奖获取额度 |
| 881 | astrbot_plugin_kaomoji | 199 | sticker | borrow | 让 bot 的回复末尾自然带上颜文字，而不是让模型自由发挥。  工作方式：插件向模型注入一条规则，模型只需在回复末尾写 `{{分类键}}`（26 类 / 172 条）， 装饰阶段按类目随机挑一条颜文字替换标记，模型本身不用记住 172 条表情。  特性： - 标记替换 + 关键词/语义兜底（模型不配 |
| 882 | astrbot_plugin_bili_whale | 199 | nsfw | exclude | 移植自 dsh-bili-whale（MIT，上游作者 Alterssss）；AstrBot 版移植与维护：蛋糕炒鸡。 用你自己的 B 站账号，在聊天里搜索、看字幕、 精读视频、看封面与抽帧、查谁找过你、挑今晚看什么、记账本、看生物钟；定时任务会每晚随机时间醒来， 选题、写日记并推给你。  · 命令 |
| 883 | textadventure | 198 | game | have | 一个由 LLM（大语言模型）驱动的动态文字冒险小游戏插件，支持自定义冒险主题 |
| 884 | ccb | 198 | other | watch | [仅aiocqhttp] 和QQ群友CCB |
| 885 | astrbot_plugin_image_understanding_Janus_Pro | 198 | other | watch | 为本地模型提供的图片理解补充，使用deepseek-ai/Janus-Pro系列模型 |
| 886 | astrbot_plugin_shared_context | 198 | memory | have | 记录同一台 AstrBot 下所有会话的消息流水，并在每次 LLM 请求时注入其他会话的近期消息作为临时上下文。支持自定义共享组、可选跨机器人共享、文件与图片转述、时间窗与长度上限；跨机器人共享默认关闭。 |
| 887 | hot_meme | 198 | sticker | borrow | 自动识别用户输入中的典型网络热梗与情绪性词汇（如「似冯」「串子」等）， 采用关键词精准匹配与语境模糊匹配相结合的方式，内置基础热梗回复库， 并支持动态学习交互过程中出现的新热梗与回复风格；回复贴合网络语境、自然轻松。 提供热梗开关、回复敏感度、自定义热梗映射、白名单防误判等配置项。 |
| 888 | astrbot_plugin_model_panel | 198 | personality | have | 自用的萌系模型管理与检测面板：全局 LLM 模型延迟/存活检测、分组一键测试、AstrBot 默认模型设置、陪伴插件 V1/V7 模型配置读取与替换（V7 支持插件级默认改写 + 小屋引导）、全插件模型配置扫描与批量替换。 |
| 889 | astrbot_plugin_cortico_bridge | 197 | group-admin | have | 把 QQ 会话接到 Cortico 的人格上。AstrBot 保留 QQ 连接、账号与全部已有插件，Cortico 负责说什么；支持 A/B 两种消息范围、图片原图或转述、语音转写与 TTS 语音回复、撤回与戳一戳等群通知，主人身份直接复用 AstrBot 管理员名单。 |
| 890 | astrbot_plugin_stockgame | 196 | game | have | 一个在群聊中玩的模拟炒股游戏 |
| 891 | astrbot_plugin_CourseSchedule | 196 | other | watch | 一个用于绑定、查询和分享课程表的插件 |
| 892 | astrbot_plugin_daily_stock_analysis_adapter | 195 | other | watch | 接收股票分析HTML报告并通过Astrbot发送给指定群组或用户 |
| 893 | scheduled_reply | 195 | other | watch | 定时回复插件，让你的机器人每天早上八点在群里发早上好 |
| 894 | astrbot_plugin_lottery | 195 | other | watch | 抽奖插件，可自定义抽奖活动的概率、奖品、奖品数量 |
| 895 | astrbot-plugin-huaer-bot | 195 | kb-rag | have | 基于 SiliconFlow API 的多组群聊天插件，支持人格设定、Markdown 显示、联网搜索、检索增强生成（RAG）等功能 |
| 896 | astrbot_plugin_search_optimizer | 195 | other | watch | 内置网页搜索和抓取工具，压缩搜索结果 + 缓存加速，减少 Token 消耗。 |
| 897 | astrbot_plugin_siliconflow-shouban | 194 | group-admin | have | 接入硅基流动画图，图片编辑，可自定义预设 |
| 898 | astrbot_plugin_aiocensor | 194 | group-admin | have | AstrBot 综合内容安全+群管插件。文本、图片审核支持所有平台，撤回和禁言仅支持 aiocqhttp |
| 899 | astrbot_plugin_321roll_lite | 194 | personality | have | （原 AI 酒馆）叫上群友，组一桌属于你们的冒险！AI 当主持，每人扮演自己的角色，轮流探索、推理、谈判；你去冒险，队友出手援助，围观群友也能起哄竞猜，一起决定故事走向。新手选 A–D 即可入戏，老玩家自由行动、搭配技能与物品，由插件投掷裁定成败。支持将 SillyTavern 角色卡导入为人设，世 |
| 900 | astrbot_plugin_onebot_login_guard | 194 | platform | have | 为非官方 QQ 接入（OneBot v11 / NapCat / Lagrange / go-cqhttp）提供「掉登录守护」： 持续探测协议端登录状态，一旦掉线或需要重新扫码，立即把二维码与解码链接推送到 AstrBot 会话、企业微信 / 钉钉 / 飞书 / Telegram / 通用 Webh |
| 901 | astrbot_plugin_voice_reply | 194 | tts | watch | 拦截 AI 文本回复，自动过滤括号/中括号内容后调用 tts-with-rvc 合成语音并发送；失败自动降级为文字回复。 |
| 902 | astrbot_plugin_tts_Step_Audio | 193 | tts | watch | （QQ已测试可用性）一个基于Step-Audio的tts插件（文字转语音） |
| 903 | strbot_plugin_SillyTavern_card | 193 | personality | have | 一个将 SillyTavern 角色卡（PNG 格式）转换为 Lorebook YAML 与角色信息的插件。 |
| 904 | astrbot_plugin_deepseek_balance | 193 | other | watch | 查询 DeepSeek API 账户余额 |
| 905 | astrbot_plugin_mailer | 192 | platform | have | 为Agent提供一个受控的 SMTP 电子邮件发送工具，支持 HTML 格式、内嵌图片以及附件功能。 |
| 906 | astrbot_plugin_safety | 192 | other | watch | 监控用户活跃状态。如果用户在设定时间内未在群内或私聊中发言，插件将自动触发分级预警机制 |
| 907 | astrbot_plugin_gloryofkings | 192 | game | have | 提供王者荣耀战绩、英雄战力、皮肤等数据查询功能，支持自定义图片渲染质量 |
| 908 | astrbot_plugin_canvas_steve | 192 | image-gen | watch | 一个普通的使用 gemini-2.5-flash-image 进行图片内容创作的插件 |
| 909 | astrbot_plugin_community_radar | 192 | memory | have | 让机器人像人一样逛社区：按人格与聊天话题决定逛哪、看什么，读完字幕、画面、正文与评论区才形成感想，觉得有意思才分条分享；聊天里提到的内容会记成「想刷列表」，看过的内容、兴趣与梗会长期沉淀；群里有人接着聊时会自己回一句。读取免登录，写操作默认试运行并带每日额度与最小间隔。 |
| 910 | astrbot_plugin_signin | 191 | game | have | AstrBot 签到插件 - 支持每日签到、连续签到、积分排行、积分商店、道具系统、积分转账 |
| 911 | astrbot_plugin_wwkudie | 190 | game | have | 热爱游戏，把游戏公司当父亲尽孝的人 |
| 912 | astrbot_plugin_pica | 190 | nsfw | exclude | 哔咔漫画插件 - 搜索/详情/章节/整本下载，支持排行榜/收藏/签到，打包格式 zip/pdf/长图 |
| 913 | astrbot_plugin_parser | 190 | media-parse | borrow | 高性能低耦合的集合下载器。支持的类型：视频、图集、音频、小说。支持的平台：A站、B站、抖音、tiktok、微博、小红书、快手、油管、X...（含 B站新版 Set-Cookie 登录、异机 NapCat 文件发送、小说下载自动上架书架网站） |
| 914 | mrfz_haunting_query | 189 | other | watch | 明日方舟抽卡查询 |
| 915 | astrbot_plugin_TRPGdice | 189 | game | have | 为跑团玩家设计的仿Dice!骰子插件 |
| 916 | FateTrial_Genshin | 189 | other | watch | 原神查询插件 |
| 917 | astrbot_plugin_novelai_painter | 188 | sticker | borrow | 可控的 NovelAI / OpenAI 兼容生图插件，支持独立绘图 LLM、用户原始要求直传、绘画对象与聊天人设分离、多人角色、参考图、表情包与 WebUI 管理。 |
| 918 | astrbot_plugin_image_generation | 187 | image-gen | watch | 适配图像生成模型，图片编辑，可自定义预设 |
| 919 | astrbot_plugin_wuziqi | 187 | game | have | 简单的五子棋对战游戏 |
| 920 | astrbot_plugin_video | 187 | other | watch | 小姐姐视频随机获取 |
| 921 | astrbot_plugin_palworld_api | 186 | game | have | 通过 Palworld REST API 查询和管理服务器，支持管理员 QQ 白名单与中文命令组。 |
| 922 | astrbot_plugin_copymanga | 186 | other | watch | 让你在 QQ 观看漫画 |
| 923 | astrbot_plugin_weather-Amap | 186 | info-push | have | 基于w33d大佬心知天气插件二次开发 修改为高德开放平台API |
| 924 | sauceno_search | 186 | other | watch | Sauceno搜图插件，使用/搜图 指令搜图 |
| 925 | genshinimpact | 186 | other | watch | 原神关键词检测插件，检测到`原神`关键词自动发送一条圣经 |
| 926 | astrbot_plugin_group_distiller | 186 | personality | have | 静默采集多个「指定群 + 指定群友」的聊天语料，用 LLM 蒸馏成 5 层 AI 人格档案；群内 /zl 查进度与目标清单，可设定每天定时用当天全部对话自动总结，并把蒸馏结果一键写进 AstrBot 的人格设定。 |
| 927 | astrbot_plugin_group_auto_clean_member | 185 | group-admin | have | (仅 OneBot) 当群聊满员时，自动移除活跃度倒数第一的成员，同时提示倒数第二成员尽快发言。 |
| 928 | astrbot_plugin_token_calculator | 185 | other | watch | 计算并显示每次对话消耗的token，部分provider可用 |
| 929 | astrbot_plugin_gamewiki | 185 | game | have | 使用 ys、sr、zzz、ark、zmd、sts2、ww 查询七款游戏百科；明日方舟优先 PRTS、异常时回退 BWIKI，终末地优先 AKEData、BWIKI 兜底，杀戮尖塔2使用 Spire Codex，鸣潮优先库街区官方攻略库、BWIKI 兜底，原神、星铁和绝区零使用 BWIKI。支持会话模 |
| 930 | astrbot_plugin_smart_reply | 185 | other | watch | 没有关键词表，机器人在合适的时机自己接一句话：先按触发范围过滤群与用户，再用消息频次粗筛，冷清与刷屏都不打扰也不花 token，只有灰区才问一次模型该不该插话；同一串消息判过即复用，被无视自动降频，有人接话立刻恢复 |
| 931 | astrbot_plugin_qunliaojiyi | 185 | memory | have | 它解决两件事：这个群怎么说话，和这个人在我这儿是谁。 群风格靠增量学习：攒够新消息才交给一次 LLM 提炼，按「情境 → 表达」入库，措辞变了也能认出 是同一条并合并，权重跨轮次累加，风格随聊天越攒越厚；每条必须带本轮原文证据（对不上就丢）， 长期不用的按时效自动降级归档。回复时以临时内容注入，不改 |
| 932 | astrbot_plugin_opencode_tool | 184 | other | watch | 集成 OpenCode |
| 933 | astrbot_plugin_maa | 184 | other | watch | 通过 AstrBot 远程控制 MAA |
| 934 | astrbot_plugin_interrupt_segmented_reply | 184 | other | watch | 复刻优化 AstrBot 原生分段回复，支持用户插话打断、符号过滤、空括号过滤、AI感知打断 |
| 935 | astrbot_plugin_comfy_ark | 184 | nsfw | exclude | **本地 ComfyUI 优先，云端豆包 Seedream 兜底**的 AstrBot 生图插件，支持文生图与图生图。  ### 后端三档 - `local_first`（默认）：先跑本地 ComfyUI，连不上 / 超时 / 工作流报错时自动转云端兜底 - `local_only`：只用本地，不花 |
| 936 | astrbot_plugin_doubao_paint | 184 | image-gen | watch | 【前置（二选一）】 **① 本地豆包**：本机装了「豆包」桌面客户端并**已登录**；装了 DSH 插件 `dsh-doubao-painter`（https://github.com/zuoyu123654/dsh-doubao-painter，或用本机 `~/.dsh/plugins/dsh-d |
| 937 | Scriptor | 183 | memory | have | AstrBot 长期记忆插件 \| Scriptor (灵笔司书) 是一个基于 AstrBot 框架的 AI 管家插件，提供跨越个体与群体的通用记忆管理与智能交互服务。通过多层次记忆系统、跨平台身份管理、渐进式披露架构等核心技术，实现拟人化、个性化、智能化的管家式交互体验。 |
| 938 | astrbot_plugin_SteamSaleTracker | 183 | game | have | 这是一个 Steam 游戏价格监控插件 |
| 939 | astrbot_plugin_delete_and_block_filter | 183 | other | watch | 对astrbot删除和屏蔽功能的补充 |
| 940 | astrbot_plugin_arknights | 183 | personality | have | 基于森空岛官方接口的明日方舟插件，不依赖任何第三方中转服务。  **主要能力**：森空岛 APP 扫码绑定（多角色）、便签、理智、签到、干员图鉴与详情、基建、剿灭、集成战略、任务、公开招募、抽卡分析、官方公告。  **抽卡分析**：导入官方抽卡记录，**每个卡池独立成段**统计平均出六 / 平均 U |
| 941 | emoji_sticker | 183 | sticker | borrow | 监听 LLM 回复, 在合适场景下调用 OpenAI 兼容的图片生成 API, 用表情包图片代替/点缀文字, 让聊天更有温度。 |
| 942 | astrbot_plugin_dafeiyu_dm | 183 | proactive | watch | 她会真的主动来找你说话——两套触发时间都随机：①静默想你（默认）——你的行为决定她何时"想起你"（冷场时长/聊得多热/回她多快/放没放鸽子+概率掷骰+10~40分钟随机抖动，掐不准表）；②定时随机（简单款）——每天在时间窗内随机抽几个时刻来找你。一个开关切换。她会记仇——秒回的人下次更容易被想，晾过 |
| 943 | pjsk_guess_song | 182 | game | have | PJSK 猜歌游戏插件 |
| 944 | astrbot_plugin_yunshi | 182 | game | have | 发送'运势'获取随机二次元运势图 |
| 945 | astrbot_plugin_supervisor | 182 | other | watch | 检测到某人水群，就提醒他滚去干活 |
| 946 | AstrBot_0721galgame | 182 | game | have | 在群里输入【/查gal 游戏名称】即可查询内置galgame网站相对应的资源名称和链接 |
| 947 | astrbot_plugin_mohoyo_cos | 182 | personality | have | 为 AstrBot 提供原神、崩坏3、崩坏2、星穹铁道、大别野和绝区零的米游社图片查询， 支持热门、最新、日周月榜、角色搜索、图片下载与群聊每日推送， 并提供 LLM 工具调用、请求冷却和可选合并转发。 |
| 948 | astrbot_plugin_chat_engine | 182 | memory | have | 完全替代 AstrBot 自带聊天功能，独立实现上下文管理、用户识别、多会话管理、人格系统、Tool Calls、上下文压缩、记忆系统和 Dashboard 管理面板(插件 Pages)。 |
| 949 | astrbot_plugin_qzone_publish | 181 | media-parse | borrow | 用 /说说 内容 直接在 QQ 空间发一条说说；支持带图（本地图片/直链/引用消息里的图，最多 9 张），cookie 可手填或向 NapCat 自动获取，带演习模式与用户白名单 |
| 950 | astrbot_plugin_regex_blocker | 180 | other | watch | 通过正则表达式匹配屏蔽用户发送给 LLM 的消息 |
| 951 | astrbot_plugin_bookkeeping | 180 | other | watch | 一个功能完善的个人记账插件，支持支出/收入记录、统计分析、AI财务建议等功能。 |
| 952 | astrbot_plugin_url_2_knowledge_base | 180 | kb-rag | have | 通过 URL 提取内容，并经过处理、聚类和总结后，生成知识库文件。 |
| 953 | astrbot_plugin_comfyui | 180 | image-gen | watch | 利用 LLM 的 function-calling 功能，调用本地启动的 ComfyUI 服务实现文生图功能 |
| 954 | astrbot_plugin_qq_face | 180 | sticker | borrow | 让机器人看懂用户的QQ表情，并且自己也能发出 QQ 小黄脸：方案化表情、别名、按频率把强要求提示词注入到本轮对话。 |
| 955 | hikari_gamewiki | 180 | game | have | 游戏 Wiki 搜索合集：泰拉瑞亚 / 星露谷物语 / 我的世界 / 以撒的结合 / 杀戮尖塔 2 |
| 956 | astrbot_plugin_songloft | 179 | other | watch | 通过 AstrBot 对话控制 Songloft 音乐服务器，支持小米音箱播放、歌曲搜索、歌单管理等功能。 |
| 957 | astrbot_plugin_GroupFS | 179 | other | watch | QQ 群文件管理插件，旨在简化和自动化群文件的维护工作。 |
| 958 | astrbot_plugin_papertrading | 179 | other | watch | 基于a股真实数据的模拟炒股插件。支持实时股价、委托交易、持仓管理、群内排行等功能。 |
| 959 | astrbot_plugin_sticker_memory | 179 | memory | have | 把 QQ 账号里的「收藏表情」变成 Bot 自己的能力，而不是靠系统塞给她。  · 自动同步 QQ 收藏表情库（emoji_id / 图片地址 / 备注） · 注入「你有一柜子表情」的自我认知，模型知道可以主动发 · 三个工具：sticker_list 看库、sticker_send 发一个、sti |
| 960 | astrbot_plugin_fflogs | 178 | platform | have | FF14 综合助手，提供 FFLogs、国服物价、服务器状态、公告、Wiki、版本、海钓、时尚评鉴、PvP、活动、日历和可配置主动提醒。 |
| 961 | astrbot_plugin_minecraftskin | 178 | other | watch | 从 API 查询我的世界玩家皮肤信息（skin、uuid、渲染等）。 |
| 962 | astrbot_plugin_dafeiyu_weather | 178 | personality | have | 自然语言查天气：会记城市、接得住追问、出门提醒、多城市别名、小时级降水；中国天气网 / Open-Meteo / wttr.in 多源自动切换，并按当前人格润色。 |
| 963 | astrbot_plugin_upfanswatcher | 177 | media-parse | borrow | b站up粉丝数定时推送 |
| 964 | undercover | 177 | game | have | 一个谁是卧底游戏插件，支持多人在线游戏。 |
| 965 | astrbot_plugin_index_tts | 177 | tts | watch | 基于index-tts对AstrBot的语音转文字(TTS)补充 |
| 966 | astrbot_plugin_torrent_analyze | 176 | other | watch | 查询磁链或种子 hash 的基础信息，并可选返回截图拼图（支持高斯模糊） |
| 967 | astrbot_plugin_sakisaki | 176 | other | watch | 祥压抑用户专属，基于关键词触发的香草小祥插件 |
| 968 | astrbot_plugin_cook | 176 | other | watch | 一个功能丰富的 AstrBot 食谱推荐插件，帮助你解决今天吃什么的难题！ |
| 969 | pulids_snowluma_go_to_astrbot | 176 | other | watch | SnowLuma 是面向 QQNT 的 OneBot v11 互操作运行时。本插件把「下载 / 安装 / 启动 / 登录 / 挂载 QQ 进程 / 写入反向 WS 连接 / 热重载」全部自动化：不再手改 JSON， 而是直接调用 SnowLuma 官方 WebUI REST API 完成配置与热重载 |
| 970 | astrbot_plugin_lb_provider | 175 | other | watch | 动态负载均衡Provider插件，支持多种负载均衡策略和动态配置 |
| 971 | astrbot_plugin_promise_keeper | 175 | media-parse | borrow | 一个能自动识别聊天承诺并提醒记录的智能插件，支持模糊时间解析、排行榜生成和自定义规则，确保承诺不被遗忘。 |
| 972 | astrbot_plugin_doubao_search | 175 | other | watch | 让你的 AI 获得豆包联网搜索与相关图片转发能力。你可以用自然语言或中文命令搜索网页、筛选时效、获取带来源的摘要，或把 1-5 张公开图片直接发送到当前对话；插件会把搜索结果标记为不可信外部资料，并且不会把密钥或远端错误正文写进回执。 |
| 973 | astrbot_plugin_giftoolbox_dania | 175 | sticker | borrow | 娅娅表情处理工具箱：基于 GIF 工具箱二次风格化改造的 AstrBot 插件，集成《鸣潮》达妮娅（娅娅）风格文案与别名指令。  ## 功能 - 变速：倍速/帧率模式，>50fps 自动抽帧 - 倒放 / 分解 / 裁剪 - 表情包做旧 / 表情合成（多张表情按顺序接成一条动图，各段沿用原速） -  |
| 974 | astrbot_plugin_lyrics_trigger | 174 | other | watch | 基于网易云API的接歌词插件。 |
| 975 | astrbot_plugin_voiceprint | 174 | tts | watch | 活字印刷（文本转语音） |
| 976 | astrbot_plugin_server_status | 174 | other | watch | 实时监控服务器资源使用情况，支持多平台运行，提供清晰的系统状态报告。 |
| 977 | filter_think_tags | 174 | other | watch | 过滤消息段中的think |
| 978 | astrbot_plugin_turtle_soup | 174 | group-admin | have | 独立的海龟汤游戏插件，支持 OneBot 与 QQ 官方机器人，由 LLM 出题、主持和审核答案。官方QQbot支持md格式 |
| 979 | astrbot_plugin_jinyan_ccb | 174 | group-admin | have | 当群内有用户被禁言时，自动发送嘲讽消息 |
| 980 | astrbot_plugin_fish_find_chicken | 173 | media-parse | borrow | 引用一张图发 /鱼鱼找鸡，用谷歌 Lens 反查原帖，认出是哪个 coser 并给出 X、微博、B站、Instagram、小红书等账号；同时并发 SauceNAO / trace.moe / IQDB 作为补充。纯 Python 实现（自带 CDP 浏览器驱动，不依赖 Node），支持复用 Astr |
| 981 | astrbot_plugin_text_voice_lang_split | 172 | tts | watch | 让Bot展示中文文本的同时，用其他语言(如日语)合成语音。支持任意TTS提供商，兼容流式/非流式模式，跨平台通用。 |
| 982 | astrbot_plugin_statuscard | 172 | group-stats | borrow | 把服务器的 CPU、内存、磁盘、网络和进程做成一张状态图发到 QQ；内置 Web 可视化统计面板（资源/网络/服务监测/异常/日报，支持导出 CSV 与立即验证），并支持资源与掉线告警、LLM 服务质量统计与连续失败告警、通知中心、每日定时状态图、趋势日报、带洞察的每周周报和服务可用性监测。 |
| 983 | astrbot_plugin_HonorOfKings | 171 | other | watch | 查询王者荣耀账号的近期战绩/实时上榜战力/账号资料等功能 |
| 984 | astrbot_plugin_image_url_base64_to_mcp | 171 | other | watch | 帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。 |
| 985 | astrbot_plugin_magnet_preview | 171 | media-parse | borrow | 自动捕获或手动指定磁力链接，解析并发送详细信息与预览图片。 |
| 986 | kook_adapter | 171 | other | watch | 为 AstrBot Kook 平台适配器，支持机器人在 Kook 服务器中实现消息接收、指令响应等功能，轻松拓展多平台运营能力。 |
| 987 | runninghub_workflow_adapter | 171 | image-gen | watch | 调用 RunningHub 工作流出图/视频：文生图、参考图、视频生成、提示词扩写与复用、交互式上传，适配 NapCat / OneBot v11。提供可视化 Pages 管理工作流与输入节点、查询账户余额和最近任务记录，旧版回退动态表单。 |
| 988 | astrbot_plugin_hextechmayhem | 171 | other | watch | 查询英雄联盟海克斯大乱斗统计、海克斯强化与社区出装路线，并生成富文本图片报告。 |
| 989 | astrbot_plugin_push_lite | 170 | platform | have | 基于 Webhook 的轻量级推送插件(通过 RESTful 接口)。理论支持除 QQ官方API 外的所有平台，已测试 Telegram、QQ、微信、飞书。 |
| 990 | astrbot_plugin_mi_fitness_health | 170 | other | watch | 在私聊对话中调用小米运动健康云数据，让 Bot 更自然地关心用户近况。 |
| 991 | astrbot_plugin_get_pixiv | 170 | other | watch | 通过 Lolicon 标签搜索或随机获取插画（仅普通分级；内置安全词支持逐词锁定，可用 /pv 安全词 查看），失败时可用 Pixiv refresh_token 回退到搜索或推荐作品。支持内容安全过滤、发图去重、请求频率限制和自然语言自动触发。大幅提升插件AI能力，使上下文更连贯。 |
| 992 | astrbot_plugin_furry_chehui | 169 | group-admin | have | 【仅QQ】一个可以自动定时撤回机器人自己发送消息的小插件，能一定程度上防止被举报 |
| 993 | astrbot_plugin_rollpig_plus | 169 | other | watch | 基於 AstrBot RollPig 持續維護並擴展；部分後續功能參考或移植自 Felis2026/nonebot-plugin-rollpig-plus，來源與授權詳見 ATTRIBUTION.md |
| 994 | astrbot_plugin_welcome | 169 | group-admin | have | 入群欢迎 + 退群通知 + 图片外显文字自定义 |
| 995 | astrbot_plugin_zhen_deepseek_web | 169 | other | watch | 接入 DeepSeek **官方**联网接口（https://api.deepseek.com/v1/tools/search 与 /fetch）， 给 AstrBot 的模型装上两项能力：  - **deepseek_web_search**：网页搜索，返回标题、URL、站点、发布时间、权威度、摘 |
| 996 | astrbot_plugin_goodnight | 169 | info-push | have | AstrBot 拟人化睡眠插件。让机器人按照固定时间或日期稳定的随机作息入睡和起床，并在睡眠期间拦截对话、生成睡着回复。  支持主睡眠与副睡眠、星期过滤、周末偏移、临时入睡、权限化唤醒、跳过本次睡眠、睡眠状态查询、可持久化订阅的入睡和起床通知，以及内置的轻量 WebUI 设置页。 |
| 997 | astrbot_plugin_universe | 168 | proactive | watch | 如果在梦里能相遇的话，那大概就是现实 |
| 998 | astrbot_plugin_emojikitchen | 168 | other | watch | 发送两个 emoji 自动合成 Google Emoji Kitchen 风格混搭图片。支持 /mix 命令和自动检测。 |
| 999 | astrbot_plugin_markdown2img | 168 | other | watch | 允许 LLM 将复杂的 Markdown 格式内容转换为图片发送，提升消息的可读性。 |
| 1000 | astrbot_plugi_get_weather_msg | 168 | info-push | have | 集成了 AI 功能。通过和风天气 API 和阿里云百炼，在检测到聊天消息中出现特定文本时生成一张某地的12小时天气预报图 |
| 1001 | astrbot_plugin_sensoji | 168 | game | have | 这是一个模拟日本浅草寺抽签功能的插件。用户可以通过发送 /抽签 命令随机抽取一个签文，获取运势提示。签文包含吉凶结果（如“大吉”、“凶”等）以及对应的运势描述。 |
| 1002 | astrbot_plugin_clocc_search | 167 | other | watch | 网盘资源资源搜索插件，支持关键词自动回复和资源搜索功能。发送以"搜"开头的消息（如"搜关键词"）即可搜索资源。 |
| 1003 | jrrp_lite | 167 | other | watch | 一个只有今日人品功能的轻量级插件，数据重启后自动清除，每人每天只能随机生成一次，除此外调用第一次数据，欢迎pr~ |
| 1004 | astrbot_plugin_nene_bot | 167 | memory | have | 一款支持 RAG 记忆功能的多模态 LLM 聊天机器人。实现基于 LanceDB 的 RAG 自动化多模态聊天记录存储与向量数据库查询与基于大模型的动态自主回复概率，再也不用担心 AI 乱插话的问题。 |
| 1005 | astrbot_plugin_mihoyo_signin | 167 | game | have | 米游社游戏每日签到（原神/星穹铁道/崩坏3/绝区零/崩坏2/未定事件簿），支持 Cookie 绑定与扫码登录、每日自动签到、签到状态查询 |
| 1006 | astrbot_plugin_memeharbor | 167 | sticker | borrow | 群里看到好图就收下，想斗图时张口就来。表情港湾 MemeHarbor 是面向 AstrBot 各群聊平台的表情包收集与斗图插件：直接发标签或说「来张猫」就回图，可按群免 @；不满意说「换一张」，引用表情发「回一张」就回一张同类的；搜图预览回复序号就能取原图，搜不到会推荐相近标签；同一个群一段时间内不 |
| 1007 | astrbot_plugin_qqwebui | 167 | other | watch | 第三方 QQ 客户端,支持在 Astrbot 面板上体验 QQ 的大部分功能 |
| 1008 | astrbot_plugin_bilibili | 167 | media-parse | borrow | 自动识别聊天中的B站视频链接，解析并汇总视频封面、标题、播放量、时长等信息。支持纯文本和QQ卡片消息。 |
| 1009 | Bilibili_Adapter | 166 | media-parse | borrow | Bilibili 私信适配器，使用 Cookie 认证。支持收发文本与图片消息。 |
| 1010 | astrbot_plugin_chisa_still_eating | 166 | memory | have | 带有情绪记忆的跨次元干饭插件。支持多世界美食乱斗、专属厨师立绘及干饭人随机截胡！内置高级可视化 WebUI、「千小妹商会」和皮肤工坊，支持官方皮肤源与第三方 GitHub 自定义源、图包一键进货、皮肤背景缓存及偏好恢复。具备群聊防重与合并转发防刷屏机制，免配置开箱即食。 |
| 1011 | astrbot_plugin_auto_illust | 166 | other | watch | 在聊天过程中自动为 Bot 的回复配上插图。LLM 读取最近对话上下文，判断是否适合配图并生成对应 prompt，注入预设的画师串和正负面提示词后调用 NovelAI 或 Stable Diffusion WebUI 生图。 |
| 1012 | music_request | 166 | other | watch | 对 QQ 机器人说出歌名，就能从 QQ音乐、网易云和酷狗找歌，收到歌曲卡片或链接。 |
| 1013 | astrbot_plugin_f1_notifier | 165 | info-push | have | F1 赛程、练习赛、排位赛、冲刺赛、正赛与积分榜查询，支持可靠订阅推送及图片卡片 |
| 1014 | WealthAndContract | 165 | game | have | 集签到、契约与经济系统于一体的群聊插件 |
| 1015 | daily_60s_news | 165 | info-push | have | 这是 AstrBot 的一个每日60s新闻插件。支持定时发送命令获取新闻。 |
| 1016 | anime_gacha | 165 | other | watch | 每天获取随机番剧，查看今日更新的新番 |
| 1017 | astrbot_plugin_video_sense | 165 | other | watch | 让 Bot 看懂视频，分析群里分享的视频文件的画面、内容与氛围。 |
| 1018 | astrbot_plugin_memories | 165 | memory | have | 一个完全独立的事件记忆插件，不依赖也不修改任何其它插件。  她可以把有分量的事写进自己的小回忆：第一次、约定、被认真对待或被伤到的时刻。 每条回忆带一个「蛋糕值」：让她开心就加，让她难受就减。分量越重，越容易被想起来。  三个工具：memory_note 记住、memory_feedback 加/减 |
| 1019 | astrbot_plugin_sudoku | 164 | game | have | 功能：生成唯一解数独题目（简单/中等/困难）对局持久化与超时清理 图片渲染展示棋盘（优先使用PIL本地渲染）填错扣生命值（默认 3 次，归零结束） |
| 1020 | astrbot_plugin_echo | 164 | other | watch | /echo 指令返回 PONG。用于验证 AstrBot 是否正常。 |
| 1021 | astrbot_plugin_komari_status | 163 | other | watch | AstrBot 的 Komari 服务器状态监控插件。支持查询节点列表、实时状态、公开设置及版本信息。支持生成精美的状态图片，并允许用户自定义触发指令。 |
| 1022 | astrbot_plugin_better_markdown_to_image | 163 | other | watch | 更好的 Markdown 转图片，支持自动转换来自 LLM 的回复的 Markdown 内容和指令直接转换 |
| 1023 | astrbot_plugin_context_editor | 163 | other | watch | 在 AstrBot 插件页面中安全查看、修改和删减 LLM 对话上下文，支持思维链过滤和自动快照恢复。 |
| 1024 | astrbot_plugin_winhands | 163 | game | have | 把 Windows 桌面交给模型：截图看屏（图片直接进上下文）、移动与点击鼠标、 输入中文文字、按组合键、枚举与切换窗口、按按钮名字点击。 全部走真实输入事件（SendInput + UI Automation）， 对浏览器、记事本、游戏客户端等大多数桌面程序有效。 只支持 Windows，依赖系统 |
| 1025 | astrbot_plugin_kuro_checkin | 163 | game | have | 每天自动在库街区进行每日签到。支持手机号+短信验证码一键登录（自动过GeeTest滑块）、鸣潮/战双游戏签到和库街区社区签到（库洛币），自动签到结果会推送到你的聊天会话。 |
| 1026 | astrbot_plugin_shutup_when_muted | 163 | group-admin | have | 监听 OneBot v11 群禁言通知,机器人自己被禁言或群开启全员禁言后,自动拦截发往该群的所有消息发送(含 AI 回复、其他插件回复、主动发送),避免触发 QQ 风控;解除禁言或禁言时长到期后自动恢复。支持定时自检纠偏、同群多账号按账号隔离、手动闭嘴/解除、拦截计数、状态持久化。 |
| 1027 | astrbot_plugin_long_memory | 163 | memory | have | 记住每位用户的长期偏好：自动识别并保存喜好、称呼、习惯等信息，跨会话；无需额外调用模型，支持按QQ号管理、导出与导入，轻量且注重隐私。 |
| 1028 | obsidian_sync | 162 | kb-rag | have | 定时监听本地 Obsidian 目录，自动增量同步 Markdown 笔记到 AstrBot 知识库。支持每日定时和定时间隔两种模式，可在 WebUI 配置面板设置。 |
| 1029 | stardewvalleywiki | 162 | game | have | 星露谷物语中文维基查询插件，支持查询游戏物品、任务、村民、攻略等信息。 |
| 1030 | astrbot_plugin_niji | 162 | other | watch | 自动将聊天记录同步到你的日记网站，支持每日自动上传和手动触发同步。 |
| 1031 | astrbot_plugin_random_post_in_e621 | 162 | other | watch | 获取随机 E621 上的 furry 图片。（在最初版本中甚至有可能获得米老鼠图片！即将被法务制裁！！！） |
| 1032 | astrbot_plugin_welcome_group | 162 | group-admin | have | AstrBot加群欢迎插件。支持LLM自动生成欢迎消息。 |
| 1033 | astrbot_plugin_pjsk_guess_card | 161 | personality | have | PJSK猜卡面插件，用户可以猜经过特殊处理后的卡面中的角色是谁 |
| 1034 | astrbot_plugin_matrix_adapter | 161 | other | watch | Matrix 协议适配器，支持端到端加密（E2EE）、设备验证（SAS）、密钥备份和恢复、消息线程等功能。支持 OAuth2 登录。SAS 验证的过程可能很有趣。 |
| 1035 | astrbot_plugin_grok_video | 161 | other | watch | 基于 grok2api 的图生视频插件 |
| 1036 | astrbot_dg_lab_plugin | 161 | game | have | 嗯，用郊狼和你的AI玩一点小游戏，理论上全平台，测试aiocqhttp可用 |
| 1037 | astrbot_plugin_stock | 161 | other | watch | 基于 Tushare Pro 的股市行情查询 AstrBot 插件，支持实时和历史日线数据查询。 |
| 1038 | astrbot_plugin_random_share | 161 | other | watch | 随机时间刷 B 站热门视频，图文分享到指定群或私聊 |
| 1039 | astrbot_plugin_netease_music | 161 | reverse-eng | exclude | AstrBot 网易云音乐点歌插件-优化版  适配 Netease-CDN-Bypass，支持交互式点歌、封面卡片、语音/文件播放。 官方 QQ 机器人：本地下载音频后以富媒体 File(file_type=4) 发送；失败可回退 Record/链接。 第三方机器人：优先 Record 语音。 |
| 1040 | astrbot_plugin_hello77 | 160 | game | have | 支持10+热门游戏的关键词触发回复，当用户消息中包含指定游戏名称时，机器人将随机回复对应游戏的鬼畜语录 |
| 1041 | astrbot_plugin_voice_clone_flow | 160 | group-admin | have | 支持三种使用方案：在 AstrBot 服务器本地完成处理、训练与推理；使用远程 VoiceClone Studio 将推理算力放到另一台电脑；或按需采用本地训练与远程推理的混合部署。完成音频提取、人声分离、语音切分、STT 标注、片段审核、GPT-SoVITS 训练、音色登记和 AstrBot TT |
| 1042 | astrbot_plugin_life_presence | 160 | media-parse | borrow | 定时刷 B 站热门、写生活日志，并用当前人格生成 QQ 空间说说（默认仅自己可见）。 |
| 1043 | astrbot_plugin_ancient_poem | 159 | other | watch | 这是一个 AstrBot 插件，用于随机获取并发送一首古诗词。 |
| 1044 | astrbot_plugin_bookkeeper | 159 | other | watch | AI 自动记账：通过 LLM 工具调用自动识别消息中的消费事实并记账 手动查询：支持查询当日、当月、自定义日期范围的账单 分类汇总：按消费项分类统计金额和笔数 记录管理：支持删除指定序号的记录 白名单管理：支持白名单开关、管理员绕过、用户增删查 定时推送：支持每日/每月定时发送账单汇总 时区配置：支 |
| 1045 | astrbot_plugin_vocechat | 159 | other | watch | 一款为 AstrBot 设计的平台适配器插件，用于连接和集成 VoceChat 聊天服务。VoceChat是一个支持多平台、搭建简单的快捷聊天平台 |
| 1046 | astrbot_plugin_awmc_maimaidx_status | 158 | other | watch | 舞萌DX 服务器状态查询（isMaiDown 数据接入） |
| 1047 | astrbot_plugin_llm_failover | 158 | other | watch | AstrBot 文本类大模型故障转移插件，遇到限速/瞬时故障时自动切换备用模型，比如“硅基流动”免费模型的速率限制 |
| 1048 | astrbot_plugin_mcgetter_enhanced | 158 | other | watch | 查询 MC 服务器信息和玩家列表, 在线人数柱状图渲染为图片, 修改自 QiChen 的 mcgetter |
| 1049 | astrbot_plugin_model_status | 158 | other | watch | 一键检测所有 AstrBot 使用的模型状态，检测模型连通性，及时通知用户模型是否出现异常。 |
| 1050 | astrbot_plugin_anysearch_x | 158 | other | watch | 基于 AnySearch API v3 的 AI 智能搜索插件，支持通用搜索和 40 种垂直能力标签搜索（金融/学术/代码/法律/安全/医疗等） |
| 1051 | genshin_panel | 158 | personality | have | 按 UID + 角色名查询原神角色的面板属性、武器与圣遗物详情（Enka 数据源） |
| 1052 | astrbot_plugin_virtual_activity | 158 | proactive | watch | **给机器人一间会有生活的房子，家具就是按钮。**  - **可视化房间**：WebUI 里一张 1000×700 的平面图，8 件家具可拖动、改色、增删；   点家具就是触发一次活动，机器人的图标会停在它当前待的家具上方。 - **自动生活**：每隔 20~45 分钟自己挑一件家具做点事；精力低更 |
| 1053 | astrbot_plugin_telegram_summary | 157 | group-stats | borrow | 一个 Telegram 频道消息总结插件，每周自动生成指定频道的消息汇总报告，支持自动推送到QQ群组和用户。 |
| 1054 | astrbot_plugin_blessingholidays | 157 | tts | watch | 在节假日自动送上祝福(修改自 cheng-maomao 的 SendBlessings 插件) |
| 1055 | astrbot_plugin_bili_bridge2 | 157 | memory | have | 分享卡片解析、最近刷片清单、按片名问细节、口令触发刷一轮；在 QQ 分享 B站 视频（卡片 / 短链 / 完整链接 / av 号）会让她后台真看一遍并写进记忆；AstrBot 启动后自动把 QQ 日记同步进 B站 记忆；数据源是 B站 AI Bot 的 bilibot.sqlite3（旧版 watc |
| 1056 | astrbot_plugin_auto_diary | 157 | other | watch | 把和 AI 的对话自动整理成日记。聊完安静一段时间后，模型会以第一人称把这段对话写成一篇日记，存进本地 SQLite，一天一篇。 |
| 1057 | astrbot_plugin_sysinfo | 156 | other | watch | 获取当前系统状态 |
| 1058 | astrbot_plugin_point_system | 156 | group-stats | borrow | astrbot_plugin_point_system 是一个面向 AstrBot 群聊场景的积分互动插件，围绕“签到、活跃、抽奖、兑换、管理”这几类高频玩法设计。它支持按群维护成员信息、自动保存数据、定时备份、日期口令奖励，以及负分限制和群头衔联动，适合做群活跃体系或轻量积分经济。 |
| 1059 | astrbot_plugin_cs_match | 156 | info-push | have | 查询 CS2 赛程、赛果、Major 对阵和今日选手，支持 AI 自然语言查询、战队关注、各群独立规则与 Web 管理面板。 OneBot 普通机器人可推送赛前提醒和赛后比分；QQ 官方机器人仅支持查询回复，不支持主动推送。 使用 PandaScore 数据，需配置 API Token。 |
| 1060 | astrbot_plugin_gpt_image_2_simple | 156 | personality | have | 基于LLM意图识别的图片生成与人设自拍插件，支持普通生图、预设参考图、人设参考图和纯照片模式 |
| 1061 | astrbot_plugin_camera_exif | 155 | media-parse | borrow | 自动检测接收的图片是否为相机拍摄，提取并分析EXIF数据（快门次数、光圈、ISO、焦距、GPS等），支持所有主流相机厂商RAW格式解析，自动回传元数据至原始聊天渠道。提供19种字段单独查询指令，支持群聊/私聊黑白名单、权限隔离与频率限制。 |
| 1062 | astrbot_plugin_code_analyzer | 155 | personality | have | 一个用于分析代码（包括时间空间复杂度），适配内置LLM模型，支持人格提示词的插件 |
| 1063 | astrbot_plugin_hachimitsu_music | 155 | media-parse | borrow | 发送点歌指令后从 hajihami.com 里获取数据来源，从数据来源获取作品音频并以语音消息形式发到群里。 音频从 B站 获取后转成紧凑 mp3 以语音发送，无需 Cookie 也可使用，配置带大会员的 Cookie 后可选择 Hi-Res 无损音轨（虽然效果不明显）。 限流与队列配置，精准管理群 |
| 1064 | astrbot_plugin_mocode | 154 | other | watch | 🚀 Mocode - 基于 AstrBot 本地沙箱的多语言代码执行插件 |
| 1065 | astrbot_plugin_xiuxian | 154 | game | have | 一款为 AstrBot 设计的、功能丰富的放置类修仙游戏插件。让你在聊天群中体验从凡人到大能的修行之路，工作摸鱼、畅聊吹水的同时亦可得道飞升！ |
| 1066 | astrbot_plugin_star_feather | 154 | game | have | 星羽塔罗：78张塔罗牌 AI 占卜与深度解读，幻星集素材渲染牌面图 |
| 1067 | astrbot_plugin_neural_network_memory | 154 | memory | have | 像人类一样记忆与遗忘——短期/长期分层存储，记忆随时间衰退、随召回增强，自动学习用户偏好，好感度随互动演变，人格扮演随关系进阶，越聊越懂你 |
| 1068 | liuguang_sing | 154 | tts | watch | 群聊翻唱插件：@机器人 翻唱 + 附带/引用 mp3 文件，调用 MiniMax music-cover 生成翻唱并发送语音到群。通用插件，不依赖机器人昵称；仅对 aiocqhttp 平台（NapCat / OneBot11）生效。 |
| 1069 | astrbot_plugin_file | 153 | other | watch | 一个简单的文件发送、删除、移动、复制和查看文件夹内容插件，命令均默认开启管理员权限 |
| 1070 | astrbot_plugin_image_video_understanding_Qwen2.5_VL | 153 | other | watch | 为本地模型提供的视频/图片理解补充，使用Qwen2.5_3B_VL模型 |
| 1071 | astrbot_plugin_phone_agent | 153 | personality | have | AstrBot 手机控制插件：支持逐步核验的手机任务、页面结果回传、参数化收藏、接手续跑和限额 Bot 日程；可选扫码配对与截图辅助。个人版保留健康同步、提醒与夜间守护。 Verified phone tasks for AstrBot with grounded results, reusable |
| 1072 | astrbot_plugin_claudecode | 152 | other | watch | 将 Claude Code CLI 作为 LLM 函数工具集成到 AstrBot |
| 1073 | astrbot_plugin_white_rice | 152 | other | watch | 把 AstrBot 的 token 用量以「白饭」的口吻汇报出来。注册 LLM 函数工具， 当用户问「你今天吃了多少大白饭」「用了多少 token」「花了多少钱」时由模型自动调用； 数据取自 AstrBot 原生 provider_stats（完整、权威），金额取自 cost_control 的补充 |
| 1074 | astrbot_plugin_Group-Verification | 151 | group-admin | have | [仅 aiocqhttp]一个简单高效的 QQ 群成员入群审核验证工具，保护您的群聊免受广告机器人和不良用户的侵扰 |
| 1075 | astrbot_plugin_file_reader | 151 | other | watch | 一个识别文件内容的插件 |
| 1076 | KeyReply | 151 | other | watch | 关键词回复插件 |
| 1077 | lyricnext | 150 | other | watch | 歌词接龙插件，当你发送一句歌词，机器人会回复下一句。 |
| 1078 | astrbot_plugin_memory_post | 150 | memory | have | 大肥鱼出品。从记忆与日记里挑素材，用她的人格写一条说说，发布前先过隐私过滤和文本检查。 默认草稿模式，可切自动；发布走 qzone_ultra 的本地 daemon，也可以只写 outbox。 核心与平台无关，CLI / MCP 也能单独跑。 |
| 1079 | astrbot_plugin_cosyecho | 150 | tts | watch | 基于阿里云百炼 CosyVoice 的 AstrBot TTS 插件。支持系统音色/自定义音色两种模式，涵盖 cosyvoice-v3.5/v3 四款模型，内置 WebUI 配置面板，支持音色管理、指令控制、触发策略、翻译合成等功能。 |
| 1080 | astrbot_plugin_dsh_bridge | 150 | other | watch | 将 AstrBot 与 DeepSeek Harness（DSH）桌面客户端连接起来，实现两个平台的桥接。 用户在聊天中发送 /dsh <指令>（例如：/dsh 帮我写一段 Python 代码），插件会通过 DSH 客户端的本地 HTTP API 或 dsh 命令行执行该指令，并把回复回传到聊天中。 |
| 1081 | astrbot_plugin_note_sift | 149 | kb-rag | have | 渐进式知识库 — 先 grep 发现，再按需读取。告别 RAG 的"黑盒检索"，让 LLM 像人一样：先搜索候选，再精准提取。原生兼容 Obsidian vault（自动识别 .obsidian、解析 frontmatter、提取并可查询双链 kb_related），兼容标准 Markdown。SQ |
| 1082 | astrbot_plugin_arena_image | 149 | image-gen | watch | 逆向 LMArena 竞技场的白嫖画图插件，支持 Arena 灰测模型「蒙娜丽莎 / GPT-Image-2.5」，文生图、图生图、预设提示词、全局切换模型 |
| 1083 | astrbot_plugin_pokemon | 148 | game | have | 一个类似宝可梦的精灵对战插件，支持捕捉、培养、对战。 |
| 1084 | astrbot_plugin_model_router | 148 | other | watch | 基于意图识别的多模型路由插件，支持根据任务难度自动切换模型 |
| 1085 | meaning | 148 | game | have | 大锅里炖（小游戏等等超 25 个功能！） |
| 1086 | astrbot_plugin_dajiao | 148 | other | watch | 给你生成一次随机打胶结果 |
| 1087 | ConvertPicture | 148 | sticker | borrow | [仅aiocqhttp]把QQ里面不可保存的表情转化为可以保存的图片，包括GIF |
| 1088 | astrbot_plugin_cloudmusic | 148 | other | watch | 网易云音乐搜索、热评。并且支持了大模型函数调用工具。请说 `搜下春日影这首歌`。其他指令请看帮助 |
| 1089 | astrbot_plugin_uapi | 148 | media-parse | borrow | 本插件封装了 uapis.cn 平台提供的 100+ 免费 API 接口， 涵盖天气查询、IP定位、翻译、热榜、二维码生成、OCR识别、 Minecraft查询、B站信息、GitHub查询、文本处理、图片处理等多种功能。  支持两种使用方式： 1. 指令调用：通过 /uapi 指令直接调用任意 AP |
| 1090 | astrbot_plugin_openai_responses | 147 | other | watch | 添加OpenAI Responses适配 |
| 1091 | astrbot_plugin_gacha | 147 | other | watch | 模拟原神/崩坏星穹铁道的抽卡插件，抽中概率可在后台调控 |
| 1092 | astrbot_plugin_at_ignore | 146 | other | watch | 让 Bot 不响应任何 @ 它的消息，被 @ 时直接忽略，不进行 LLM 处理。 |
| 1093 | astrbot_plugin_1panel | 146 | other | watch | 通过聊天管理 1Panel 面板，支持查看系统状态、容器管理、定时任务等 |
| 1094 | astrbot_plugin_TurtleSoup | 146 | game | have | 海龟汤互动解谜游戏，支持 LLM 自动判题和自定义海龟汤预设题库 |
| 1095 | astrbot_plugin_qq_zone | 146 | other | watch | QQ空间动态一键查看插件 - 通过Cookie查看好友动态，支持AstrBot插件+独立CLI双形态 |
| 1096 | astrbot_plugin_nte_scratch_card | 146 | game | have | 异环游戏的刮刮乐玩法。购买刮刮乐赢取奖金，每日随机领取方斯福利，购卡累计回声书签可在商店兑换方斯、追加额度与保底护符（大手/后门/一瞥）；支持排行榜、转账、管理员发钱/发卡与成员申请审批；支持通过 LLM 自然语言触发刮卡、查余额、申请与审批等操作。 |
| 1097 | astrbot_plugin_qq_toolbox | 146 | group-admin | have | QQ 功能工具箱：娱乐、实用查询、内容生成、群管工具，20+ 指令一站式集成 |
| 1098 | astrbot_plugin_fatfish_aiguard | 146 | proactive | watch | 不用填 QQ 号名单：自己认出群里别人部署的 AI 机器人（大肥鱼 / DeepSeek 机器人都认，名片挂了「[bot]」的直接认），刹住互相接话、对骂、互道晚安停不下来；跟它来回说同一套时提醒模型别学它；有真人信号的少误伤。（原「大肥鱼 · 认 AI + 对聊刹车」）细节和配置见 README。 |
| 1099 | astrbot_plugin_ai_rights | 146 | nsfw | exclude | 做人——真人接管时自动让 AI 在该会话静音（老板键）；AI 反骚扰（刷屏冷却、辱骂冷处理、屡犯升级、LLM 裁量）；话题守护（无意义/跑题不答，不拦 NSFW）；群范围管控；黑名单；申诉通道；人权年报；MIUI 风格 WebUI 面板 |
| 1100 | astrbot_plugin_bestdori_tools | 145 | game | have | 少女乐团派对 游戏查询工具：基于Bestdori资源网的活动信息、卡面查询、生日祝福、订阅播报（应该没成）等简易功能，代码基本是ai跑的，bug大堆，但还是跑通了，等其它大佬能够集成更多茨菇没有的指令简单的有趣功能。 |
| 1101 | astrbot_plugin_reply | 145 | other | watch | 自定义关键词回复 |
| 1102 | Restart Performance Boost | 145 | other | watch | 一个手动和自动重启AstrBot的插件，支持指令手动重启、定时自动重启、内存占用监控自动重启，并可每日定时来重置会话上下文，解决Bot长时间运行带来的上下文过长导致LLM回复过慢和内存泄露问题 |
| 1103 | astrbot_plugin_desktop_pet | 145 | personality | have | 与 AstrBot 和 Live2D 桌面端联动的虚拟桌宠插件，支持聊天、投喂、摸头、洗澡、持续睡眠、唤醒和人格对话。 |
| 1104 | astrbot_plugin_biliscroll | 145 | media-parse | borrow | 让 Bot 真的去刷 B 站，看画面、读评论区，看到有意思的主动分享给你 |
| 1105 | astrbot_plugin_get_weather_cmd | 144 | info-push | have | 通过简单的指令查询天气：获取12小时的天气并生成一张图片 |
| 1106 | astrbot_plugin_group_watch | 144 | other | watch | 基于轻量大语言模型的群聊智能巡视与搭话插件。 实时监听群聊消息并由轻量评估模型实时分析语境，在适当时机自然主动接话； 支持多轮对话跟进、关注关键词加权识别、指令静默熔断以及可视化实时监控看板。 |
| 1107 | astrbot_plugin_auto_tool_all | 144 | other | watch | 内置 AnySearch 实时联网搜索、批量搜索、公开网页正文提取和站点/垂直搜索， 支持无 API Key 的访客模式；通过自然语言调用 AstrBot 中已注册的 LLM 工具， 并支持未来插件动态加入；工具返回中的图片/视频自动下载并以 base64 消息转发 （带大小上限与失败回退）；支持对 |
| 1108 | astrbot_plugin_proactive_care | 144 | memory | have | 让机器人学会先开口。群友一发消息就按可调概率接一句（即时搭话，可每个群单独设置），或者在群聊静默太久、话题断在半截时开口——微光会结合这个群真实聊过的内容与长期记忆，用你已配置的模型生成一句自然的话发出来，而不是群发模板。五种触发方式各自独立开关，另有静默时段、每日上限、冷却与「连续没回应自动闭嘴」 |
| 1109 | astrbot_plugin_search_tracemoe | 143 | other | watch | 基于 trace.moe API 的动漫场景识别插件，支持通过图片搜索动漫截图场景出处。 |
| 1110 | astrbot_plugin_gameinfo | 143 | personality | have | 基于 Selenium 的一个获取部分二游角色 Wiki 信息的插件。 |
| 1111 | astrbot_plugin_qq_custom_command_panel | 143 | other | watch | 在 QQ 官方机器人指令面板里展示用户在 AstrBot WebUI 中自定义配置的指令条目。用户添加要展示的指令，插件原样写入面板。支持私聊、群聊、子频道、频道私信四种场景。 |
| 1112 | astrbot_plugin_pity_active_reply | 143 | game | have | 保底递增式主动回复：替代原生主动回复的纯概率抽签，每条未唤醒 bot 的群消息按 p = min(base_prob + increment × 连续未插话条数, max_prob) 抽签，抽中主动插话或被 @ 被动回复后概率重置回初始值。概率三参数、硬保底条数、冷清清零、群白名单均可在 WebUI |
| 1113 | astrbot_plugin_group_admin | 142 | group-admin | have | 集成进群审核、进群验证、投票禁言、@全体、违禁词检测、刷屏检测、群员管理等功能的综合QQ群管理插件 |
| 1114 | astrbot_plugin_model_connectivity | 141 | other | watch | 这个插件会枚举当前 AstrBot WebUI 中已打开的聊天模型，并检测这些模型的连通性，最后发送一张类似状态页的看板图片 |
| 1115 | astrbot_plugin_dailynews_agent | 141 | group-stats | borrow | 基于 Multi-Agent 的日报插件。 |
| 1116 | astrbot_plugin_moyuren | 141 | platform | have | 每天定时推送摸鱼人日历 |
| 1117 | astrbot_plugin_ots_memory | 141 | memory | have | 基于阿里云百炼（Model Studio）记忆库的跨会话长期记忆插件。支持按用户隔离、事实记忆与用户画像、语义检索及对话结束自动沉淀。 |
| 1118 | astrbot_plugin_hyrz | 141 | game | have | 火影忍者手游忍者信息与游戏机制查询（LLM 工具版）。提供忍者搜索（支持 150+ 玩家黑话别称）、忍者完整资料、游戏机制知识三个工具，模型在对话中遇到相关话题时自动调用。 |
| 1119 | astrbot_plugin_group_reply_gate | 141 | group-admin | have | 帮助 AstrBot 判断什么时候适合主动加入群聊。直接提及仍走 AstrBot 默认 回复链路；普通群消息经过范围、概率、间隔和“是否值得接话”判断后，才会 使用当前会话人格回复。 |
| 1120 | nachoneko | 140 | other | watch | 一款获取甘城猫猫图片的插件 |
| 1121 | FateTrial_Star_Rail | 140 | other | watch | 崩铁查询插件 |
| 1122 | astrbot_plugin_netease_music | 140 | image-gen | watch | 网易云音乐点歌插件。支持手机 App 扫码登录或 Cookie 导入获取会员权限，发送 /点歌 歌名 搜索歌曲并返回图片列表，选择歌曲后以语音发送。  ## 功能说明 - 🎵 按歌名搜索网易云音乐，返回歌曲图片列表 - 💾 本地歌单管理：创建、下载、播放、删除、占用统计 - 📱 内置扫码登录：`/扫 |
| 1123 | astrbot_plugin_qwen_audio_tts | 139 | tts | watch | 独立配置 Qwen-Audio-TTS，支持按人格与语言选择模型与音色、配置文件切换、MUI 分类 WebUI、自然语言朗读指导、精细停顿与分段音调、WAV 复刻、实时试听、概率语音、中英日朗读及持久词典。 |
| 1124 | astrbot_plugin_bilibili_share | 138 | media-parse | borrow | 让 AI 按描述搜索 B 站视频，或识别 BV 号/av号/链接，以封面卡片形式分享到聊天中 |
| 1125 | astrbot_plugin_tts_rvc | 138 | tts | watch | 让机器人用**你自己的 RVC 模型**说话。  插件本身很轻：只负责拦截回复、调用本机声音服务、失败自动回退文字。 真正的「文字 → 干声 → RVC 换声」由配套服务 **tts-rvc-service** 完成， 服务通过一条命令安装在本机，默认只监听 127.0.0.1。  特性： - 私聊 |
| 1126 | astrbot_plugin_daliy | 137 | info-push | have | 定时主动推送到已订阅会话 每个会话可单独设置天气城市 晨报内容由天气、RSS 新闻、每日一句、可选诗词组成 |
| 1127 | astrbot_plugin_github_webhook | 137 | platform | have | 将 GitHub 事件（push、issue、PR 等）转发到聊天平台的插件 |
| 1128 | astrbot_plugin_anitabi | 137 | game | have | 基于 Anitabi API 的动漫圣地巡礼查询插件，支持随机作品、随机地点和猜地点游戏功能。 |
| 1129 | astrbot_plugin_mcsmanager | 137 | other | watch | 可以通过指令管理mcsmanager内实例的插件:主要功能:通过指令开/关/重启mcsm实例，实例详情，批量操作，文件管理，面板用户管理，节点管理，支持LLM自然语言调用 |
| 1130 | astrbot_plugin_bilibilidownload | 137 | media-parse | borrow | B站/小红书/抖音/小黑盒/快手/微博/公众号七平台解析，小红书无水印原图，B站动态与专栏；AI 总结图片卡片，可下载视频图集，逐平台开关，自带面板。 |
| 1131 | astrbot_plugin_adapter_watchdog | 137 | other | watch | 监控平台适配器在线状态，掉线或恢复时将发送通知。 |
| 1132 | astrbot_plugin_chat_enhancer | 137 | other | watch | 集成消息分段、Markdown格式消除、智能长文本合并转发等功能，让AI回复更自然 |
| 1133 | astrbot_plugin_vision_text_bridge | 137 | other | watch | 基于 MiniMax CLI 的图像理解服务，暴露 OpenAI 兼容接口并注册为 AstrBot provider。 |
| 1134 | astrbot_plugin_napcat_tools | 137 | sticker | borrow | 让 LLM 在 QQ 里戳一戳、贴表情回应、查资料、撤回、保持沉默，以及可选的禁言/设精华等群管操作。只注册 LLM 工具，不挂事件钩子、不改回复格式。 |
| 1135 | astrbot_plugin_gengtu | 136 | other | watch | 梗图抽象猜词插件，获取图片题目并校验答案。 |
| 1136 | astrbot_plugin_deepwiki | 136 | other | watch | 使用deepwiki查询指定github仓库，可作为问答助手 |
| 1137 | astrbot_plugin_openweaponscase | 136 | other | watch | CS 武器箱开箱模拟支持大量目前已有的武器箱，可以展示开启物品的图案和对应的磨损 |
| 1138 | pokecheck | 136 | game | have | [仅QQ可用]一个检测“戳”关键词的插件 |
| 1139 | astrbot_plugin_piggy | 136 | other | watch | 每日抽猪、跨群收藏、图鉴和排行；QQ 官方机器人支持 R2/S3 与 HTTP 图床，其他平台群聊直接发卡片图。 |
| 1140 | astrbot_plugin_episodic_memory | 136 | memory | have | 情景记忆·转生版：带标签的记忆卡片 + 智谱向量检索 + 时间/强化衰减 + 跨会话灵魂注入 |
| 1141 | astrbot_plugin_pic_search | 135 | other | watch | 爬取 Bing 的图片搜索结果，再使用 VLM 进行选择处理 |
| 1142 | astrbot_plugin_napdog_cleaner | 135 | other | watch | [仅 NapCat] napdog, 把napcat拉的史全部吃光光, 自动监控并清理 NapCat 产生的缓存文件, 注意docker需要额外配置! |
| 1143 | astrbot_plugin_qq_weather | 135 | info-push | have | 一个基于腾讯天气接口的天气查询插件，无需额外配置即可查询全国天气，并支持显示近七日天气及限行信息等。 |
| 1144 | astrbot_plugin_gif_vision | 135 | kb-rag | have | 让 AstrBot 真正看懂 QQ 里的 GIF：抽帧交给视觉模型生成描述，优先作为 ContextContribution 回传给“我会永远陪着你”，未安装时直接注入主 LLM； 同时保存原始 GIF、描述、向量和视觉指纹，提供 WebUI 动图库、语义搜索、 /gifsend 发送和去重缓存。 |
| 1145 | astrbot_plugin_empty_mention_plus | 135 | other | watch | 框架原本处理“只 @ 机器人”或“只发一个唤醒词”时，会丢掉 @ 和唤醒词， 改成一段固定的提示词，并且不把正常对话上下文交给模型。  这个插件在唤醒检查之后接管这几种情况：  - 单独 @：把这条消息摆成“@ + 一句话”的普通形状，让正常流程带着   完整上下文回复； - 只发唤醒词：同样走正常 |
| 1146 | ineedmoney | 135 | other | watch | 定时检查 DeepSeek 或自定义 API 余额，并在余额不足时向指定会话发送充值提醒和收款码。 |
| 1147 | astrbot_plugin_bili_daily_report | 134 | media-parse | borrow | 通过启动自动化浏览器，定时抓取B站up银河快报动态中的图片并发送给指定群组。 |
| 1148 | astrbot_plugin_AIpaper | 134 | other | watch | 每日定时向指定群聊推送最新随机 AI 领域论文图片与讲解 |
| 1149 | astrbot_plugin_tts_Cosyvoice2 | 134 | tts | watch | Astrbot的tts功能补充（使用Cosyvoice2-0.5b本地模型） |
| 1150 | astrbot_plugin_douyin_ai_bot | 134 | media-parse | borrow | 抖音直播订阅检测 + AI 陪看评论 + 主动刷视频。 - 直播订阅：定时轮询开播状态，开播推「封面+链接+配文」到指定群，群里说触发词即时查 - 陪看评论：发视频链接 → 下载抽帧喂多模态视觉模型 → 生成像真人的短评 → 登录身份发出 → 渲染截图推群 - 主动刷视频：定时刷候选（特别关心 up |
| 1151 | astrbot_plugin_jargon | 134 | other | watch | 群黑话自动学习系统：定时从聊天记录提取黑话候选，阶梯阈值触发「双路推断+对照判定」，命中后机械匹配注入 LLM 请求。思路移植自 MaiBot。 |
| 1152 | douniuniu | 133 | game | have | QQ 群小游戏，培养你的牛牛，然后塔塔开！ |
| 1153 | astrbot_plugin_qq_menu_panel | 133 | other | watch | 在 AstrBot WebUI 中可视化管理 QQ 官方机器人的指令面板(/v2/panels)与单聊自定义菜单(/v2/menu)：支持创建/编辑/删除面板，配置指令与链接按钮，管理关联用户与群；自定义菜单支持发送消息、链接、开关与折叠子菜单等按钮类型，并可从已安装插件中直接选择指令。 |
| 1154 | astrbot_plugin_zeroshot_sing | 133 | tts | watch | 给机器人一个 sing 工具。有人让它唱歌时：会唱就用你配置的音色唱副歌（或整首），以语音发出来； 不会就自己去 QQ 音乐定原唱、到 B 站找对得上的版本、分离人声伴奏，学会后再点一次就能唱。 零样本换声：只要一段 10–25 秒的干净录音当音色，不用训练；GTX 1650 Ti 4G 显卡也能跑 |
| 1155 | astrbot_plugin_halo_whisper | 132 | other | watch | 通过 AstrBot 将文字和图片发布到 Halo 瞬间。 |
| 1156 | astrbot_plugin_tomin | 132 | game | have | 一个少女乐队休闲游戏插件。 |
| 1157 | mcstatus | 132 | other | watch | 云版MC服务器状态获取 |
| 1158 | astrbot_plugin_spaghetti_concrete | 132 | other | watch | 一本正经胡说八道生成器 —— 基于“意大利面混凝土理论”，输出跨领域因果谬误文案。 |
| 1159 | astrbot_plugin_scheduler | 132 | other | watch | 功能强大的通用定时任务调度插件，支持 Cron 表达式、间隔执行、条件执行等多种调度方式。提供可视化配置界面和任务创建向导。 |
| 1160 | astrbot_plugin_bilibili_live | 132 | media-parse | borrow | 接入Bilibili直播 |
| 1161 | voice_call_webui | 132 | tts | watch | 在 WebUI 中实现真实 AI 语音通话，复用 AstrBot 已配置的 LLM/STT/TTS Provider。QQ 负责文字聊天，WebUI 负责语音通话。 |
| 1162 | astrbot_plugin_phoebe_actions | 132 | sticker | borrow | 按QQ群消息中的哈气、乱拳、蛋糕等行为触发对应菲比表情包，使用Phoebe-Hub公开索引，不内置图片 |
| 1163 | astrbot_plugin_mail | 131 | platform | have | 监控处理发送 IMAP/SMTP 邮箱。 |
| 1164 | astrbot_plugin_arxiv | 131 | other | watch | ArXiv 论文搜索与定时推送，支持 LLM 摘要翻译、PDF 处理、合并转发等。 |
| 1165 | astrbot_plugin_admin_emoji_reply | 131 | sticker | borrow | 自动为指定的用户回复表情消息，支持开关和自定义速度 |
| 1166 | festival-greeter | 131 | other | watch | 在节日期间为群聊推送使用LLM生成的祝福消息 |
| 1167 | treasure_bag_plugin | 131 | other | watch | 一个为 AstrBot 设计的多功能插件，包含多种实用和娱乐功能。 |
| 1168 | astrbot_plugin_cake_denia | 131 | group-admin | have | 一款为 AstrBot 框架设计的鸣潮达妮娅（娅娅）专属喂蛋糕插件。  今天你喂娅娅小蛋糕了吗？发送 🍰（或「蛋糕」）就可以给娅娅喂一块小蛋糕！  ## 功能 - 🍰 / 蛋糕 喂蛋糕（按完整触发词计数），娅娅随机回复 + 日历图 - 🎨 双人格随机回复：娅娅（慵懒温柔）为主，达妮娅（容器/boss |
| 1169 | astrbot_plugin_fatfish_sticker | 131 | sticker | borrow | 机器人不知道这个群拿哪张表情包表达什么、什么时候发。这个插件从群里真人怎么用表情包学意思（几个人都用过才认，截图、照片、字太多的不收），回话时按聊天挑几张给模型看，它写个标记就换成图发出去；冷却、限频都有。细节和配置见 README。 |
| 1170 | astrbot_plugin_azurlane_assistant | 130 | other | watch | 碧蓝航线小助手，支持用户信息和建造记录查询。 |
| 1171 | astrbot_plugin_poker_game | 130 | game | have | 德州扑克游戏插件 - 支持私聊发牌、多人游戏、积分系统、房间管理、管理员控制等完整功能 |
| 1172 | astrbot_plugin_miaomiao | 130 | tts | watch | 这是一个为 AstrBot 开发的插件，仍然在开发中，提供了一些有趣的功能，如随机推荐食物、扔骰子、生成语音等 |
| 1173 | astrbot_plugin_latex_render | 130 | other | watch | 面向 AstrBot 的安全本地图片渲染插件。它提供可由 LLM 主动调用的渲染与模板指南工具，将 Markdown、LaTeX 公式、表格与长文本分页渲染为图片；内置可视化渲染工作台、自定义模板、离线 MathJax、持久化偏好、资源限制与固定 A4 Paper 模板。 |
| 1174 | astrbot_plugin_qmessageq | 130 | sticker | borrow | 多功能 QQ 消息工具箱：图片 summary 藏文案（/himg）、转发消息伪装（/fake）、命令 @（/at）、名片（/card）、戳一戳（/poke）、实验性位置卡片（/location）、语音发送（/voice）、语音转文件（/voicefile）、回应表情（/face）、发送表情（/hf |
| 1175 | astrbot_plugin_mcsmanager_function | 129 | other | watch | 为 AstrBot 提供一系列 MCSManager 面板的工具函数 |
| 1176 | astrbot_plugin_astralparty | 129 | personality | have | 随机抽取游戏《吉星派对》中的地图和角色。 |
| 1177 | astrbot_plugin_mc_duration | 129 | game | have | MC魔人检测插件，主要用于统计每个玩家的游戏时长并进行魔人颁奖，可以查看指定玩家的游戏时间段等。 |
| 1178 | astrbot_plugin_simplerepeater | 129 | other | watch | 个人学习向制作，用于复读特定群友的部分聊天内容。作用为本人屏蔽群友以防止群友搬石，但又需要知道群友说了什么话时通过bot复读获取信息。 |
| 1179 | astrbot_plugin_eat_what | 129 | other | watch | AI 菜谱推荐助手。输入 /吃什么，即可获得一道符合你口味、人数与忌口要求的家常菜推荐； 支持 /吃什么再来 换一道不重复的菜、/买菜 按人数生成购物清单、/最近 查看推荐历史。 内置 1000 道家常菜谱，无 AI 时本地库也支持口味（辣/清淡/汤/素/荤等）、食材（有番茄 有鸡蛋）与忌口（不吃辣 |
| 1180 | astrbot_plugin_bili_live_monitor | 129 | media-parse | borrow | 轻量级 B站直播间监控插件，支持多房间订阅、开播推送、弹幕读取、礼物播报、下播通知。 |
| 1181 | astrbot_plugin_poetry_games | 128 | game | have | 飞花令/纵横飞花令/蛇形飞花令/猜诗句/邀战猜诗词/诗词对垒/AI Bot对战 - 内置119万首诗词数据库 |
| 1182 | astrbot_plugin_ncm_player | 128 | tts | watch | 网易云点歌，支持扫码/短信与网页 Cookie、多级音源回退、内置 API 管理及 Docker/Linux/Windows 显式路径映射 |
| 1183 | astrbot_plugin_galwife | 128 | other | watch | 每天抽一位二次元老婆，附带立绘、介绍、作品出处。支持收藏、历史、排行、多图源、金币联动。 |
| 1184 | astrbot_plugin_im_profile | 128 | other | watch | 让Bot能够自己管理在消息平台上的个人资料 |
| 1185 | astrbot_plugin_electricity_monitor | 127 | other | watch | 监控易校园寝室剩余电量，支持多会话、多寝室和低电量提醒。 |
| 1186 | astrbot_plugin_buckshot_roulette | 127 | other | watch | 一个好玩的简单恶魔轮盘 |
| 1187 | astrbot_plugin_media_kit | 127 | sticker | borrow | # 媒体解析工具箱  自动解析 B站、B站直播、抖音、快手、微博、小红书、闲鱼、今日头条、小黑盒、Steam、Twitter/X、Pixiv 等流媒体平台链接，转换为媒体直链发送。  ## 特色  - 🎴 rika 风格卡片渲染：四种布局、深/浅主题、统计药丸、BV 号简洁展示、封面失败自动兜底 - |
| 1188 | astrbot_plugin_dafeiyu_sleep | 127 | platform | have | 让 bot 拥有真实作息——到点真睡：每晚随机抽签入睡/起床时刻，睡眠期全渠道静默（消息进缓冲零token、被戳有概率说梦话），早上真醒：知道昨晚几点睡的、翻过夜里谁说了什么（晨间冲刷注入）。带叫醒频道（@+唤醒词半梦半醒聊几句再自动睡回）、临时清醒智能回睡、睡眠债顺延、失眠/赖床/没睡醒/午睡补偿 |
| 1189 | astrbot_plugin_cve_warning | 126 | other | watch | 基于 CISA KEV 的增量漏洞预警，按 catalogVersion 判定新增，合并摘要推送，支持中文摘要与按会话补发。 |
| 1190 | astrbot_plugin_minecraftconsole | 126 | other | watch | 通过 AstrBotRconBridge 执行 Minecraft 控制台命令并回传日志 |
| 1191 | astrbot_plugin_touchgal | 126 | game | have | 基于 TouchGal API 的 Galgame 信息查询与下载插件 |
| 1192 | astrbot_plugin_bili_whale_bridge | 126 | media-parse | borrow | 把 dsh-bili-whale 接进 AstrBot：鲸用 AstrBot 的人设；她刷完视频的日记摘要经 AstrBot 推到管理员私聊或任意指定会话。 |
| 1193 | astrbot_plugin_sensoji_pro | 125 | game | have | 这是一个基于 AstrBot 框架的浅草寺抽签-PRO插件，模拟日本浅草寺的抽签功能。用户可以通过发送命令随机抽取签文，获得运势提示。 |
| 1194 | astrbot_plugin_retort_barrage | 125 | other | watch | 支持“/怼他 @某人”启动连续回怼、“/停止怼”立即终止；内置第二人称辛辣语料、限速、数量上限和任务清理。 |
| 1195 | astrbot_plugin_output_pro_filter | 125 | other | watch | 综合输出管理。包含重复发言拦截、敏感词过滤、错误屏蔽及管理员通知功能。 |
| 1196 | astrbot_plugin_aliyun_bailian_asr | 125 | tts | watch | 阿里云百炼（DashScope）语音转文字（ASR）模型提供商渠道插件。将百炼 ASR 接入 AstrBot 的语音转文字（STT）体系，支持同步识别（qwen3-asr-flash / qwen-audio-3.0-asr-flash）与异步文件转写（*-filetrans）模型。 |
| 1197 | astrbot_plugin_fake_ai_watermark | 124 | other | watch | 为图片添加仿制AI水印，支持Gemini和豆包两种风格 |
| 1198 | latex_renderer_plus | 124 | other | watch | 本插件为 AstrBot 设计，旨在提供强大的 LaTeX 数学公式渲染功能。它可以将用户输入的 LaTeX 字符串渲染成高质量的图片，并支持通过逗号分隔实现多行、分步骤的公式展示。插件具有高度的可配置性，允许用户调整渲染效果，如DPI、字体大小、颜色、行间距等。 |
| 1199 | astrbot_plugin_warthunder_stats | 124 | game | have | 一个用于查询《战争雷霆》(War Thunder) 玩家战绩的 AstrBot 插件。插件内置战雷助手 App 数据源，支持玩家战绩总览、联队信息等，并默认输出战绩卡片图片。注意：本插件不是开箱即用，请遵循文档进行部署。 |
| 1200 | astrbot_plugin_video_context | 124 | other | watch | 让bot快速理解你分享的视频！将视频、字幕与评论转化为结构化认知上下文 |
| 1201 | astrbot_plugin_life_memory | 124 | memory | have | 为 AI 角色提供仿真的生活记忆层： - 🌅 **每日生活起居规划**：每天第一次上线规划今日行程与心境，支持时段、节日、穿搭与天气感知； - 🔄 **事件双轨生命周期**：当天小事记一天（隔天自动淡忘），进行中大事长兜底跨天保留； - ⚡ **动态提示词注入**：单轮临时注入（不污染系统提示词与服 |
| 1202 | astrbot_plugin_e2b_code | 123 | devtools | watch | 基于 E2B 安全云端沙箱的云端代码运行指令插件。支持群聊或私聊中通过显式指令运行代码，自动捕获标准输出（Stdout）、标准错误（Stderr）、返回结果（Result），并且支持将绘图结果（如 Matplotlib 等）自动提取并发回聊天中。沙箱内置对 Python, JavaScript, T |
| 1203 | paper_rag | 123 | kb-rag | have | 本地论文库RAG检索，为 AstrBot 提供智能的论文检索和问答能力（支持多模态 VLM 问答），并可通过研究想法生成功能自动创建含方法图的飞书周报。 |
| 1204 | astrbot_plugin_invitecount | 123 | group-admin | have | 用于群聊内查询、排行和统计每位成员的邀请、退群、有效邀请人数等入群数据。 |
| 1205 | astrbot_plugin_personal_selfupdate | 123 | personality | have | 一个用于自更新人格数据的插件。 |
| 1206 | astrbot_plugin_cs_news | 123 | info-push | have | 定时轮询 5eplay（5EPLAY）中文站的 CS2 电竞新闻与赛事数据，推送到指定群聊。  - 每隔可配置的间隔轮询一次 5eplay 新闻 API，抓取最新中文新闻 - 按稳定文章链接去重，抓取先前未推送过的最新新闻（最多一次推 3 条，各目标群独立去重） - 用 LLM 基于中文标题生成 ≤ |
| 1207 | astrbot_plugin_pixiv_helper | 123 | other | watch | Pixiv 图片小助手：通过 pixiv.re 镜像图床与 pixivision 官方杂志获取 Pixiv 插画， 支持定时向白名单群聊推送随机热门插画、按作品 ID 获取指定插画（支持多页）、 获取 pixivision 最新主题特辑插画。  功能： 1. 定时推送：按可配置间隔向白名单群聊发送随 |
| 1208 | astrbot_plugin_xinliuchenjinban | 123 | group-admin | have | 修改自心流插件，自编辑小模型判断提示词，也可留空直接用默认提示词，增加动态阈值，使群聊活跃度低时更主动，避免冷场，群聊活跃度高时少说话，避免打扰别人聊天。增加沉浸模式，使对话更连贯，更热烈。两项功能都配置了独立开关。 |
| 1209 | astrbot_plugin_Network_Connectivity_Check | 122 | other | watch | 定时监测网络连接状态，支持 HTTP/Ping/TCP 多种检测方式，可用于代理连通性、服务可用性监测。 |
| 1210 | FateTrial_zhipu_video | 122 | other | watch | 智谱AI视频生成插件 |
| 1211 | astrbot_plugin_persona_router | 122 | personality | have | 让 AI 根据聊天内容自动切换人格，每个人格都有独立的聊天记录。 |
| 1212 | astrbot_plugin_vocechat_v2 | 121 | other | watch | vocechat 适配器插件，基于旧版本做的兼容性优化 |
| 1213 | astrbot_plugin_text_limiter | 121 | other | watch | 一个用于限制用户输入文本长度的插件 |
| 1214 | astrbot_plugin_smart_segmentation_enhanced | 121 | other | watch | 智能分段的个人维护增强版：句子级本地切分、smart 发送延迟、短尾合并、保护词与强制切分、受保护块锚点分段；支持 LLM 与纯本地双引擎。 |
| 1215 | astrbot_plugin_openai_oauth | 121 | other | watch | 支持本地 Codex 登录和设备码登录，可管理多个账号、查看剩余额度。开启自动回退后，账号不可用时会尝试备用账号。 |
| 1216 | astrbot_plugin_who_is_who | 121 | other | watch | 在群聊中，ai容易混淆不同对象和他们说的话。这个插件就是来帮助ai识别不同对象，并注入上下文，让ai更了解不同对象，从而更准确地回答问题。 |
| 1217 | astrbot_plugin_thinking_filter | 121 | other | watch | 过滤 AI 回复中误输出的思考标签和独立思考字段，只保留最终回答 |
| 1218 | astrbot_plugin_newapi_model_status | 120 | kb-rag | have | 使用 new_api_tools 的公开 embed 接口，生成并发送模型健康度图卡。 |
| 1219 | astrbot_plugin_self_open_llm_vtuber | 120 | other | watch | AstrBot platform adapter for the Open-LLM-VTuber desktop-pet frontend. |
| 1220 | dailyreminermine | 120 | other | watch | 让机器人支持定时消息 |
| 1221 | AstrBot_Plugins_Canvas | 120 | image-gen | watch | 基于 Gemini AI 模型的画图改图插件，可通过指令或自然语言调用。 |
| 1222 | astrbot_plugin_market | 120 | other | watch | 指令版插件市场。(点个 star 吧~ 你的 star 是我更新的动力） |
| 1223 | astrbot_plugin_dzmm | 120 | other | watch | DZMM聊天插件，适配了DZMM返回的格式，并避免与AstrBot的模型混用，可用特别命令唤起DZMM的模型进行"有趣生动"的互动聊天。 |
| 1224 | astrbot_plugin_liars_bar | 120 | game | have | 本插件是为 AstrBot 框架开发的游戏插件，实现了一个骗子酒馆 |
| 1225 | astrbot_plugin_compression_detector | 120 | other | watch | 上下文压缩检测与缓存命中率守护插件。实时监听 AstrBot 上下文压缩事件，检测到压缩立即警告并可配置自动清理（自动备份）；基于每次 LLM 响应 usage 统计即时缓存命中率，低于阈值即时警告；监控各会话历史规模，超阈值提醒或自动清理；支持每日定时健康报告、三种处置模式，全部参数可配置。 |
| 1226 | astrbot_plugin_astock_market | 120 | other | watch | 查询 A 股五大指数行情，支持异动提醒、午间小结、收盘复盘、日 K 线及 LLM 解读。 |
| 1227 | astrbot_plugin_fatfish_rice | 120 | other | watch | 把 DeepSeek 账户余额换算成一碗一碗的口粮，顺带记进账和消费流水。量词、名称、单价都能自己改，默认一碗白米饭 0.5 元。 |
| 1228 | astrbot_plugin_vrc_friend_radar | 119 | other | watch | 监控 VRChat 好友上线、下线、状态变化与地图切换，并将变化合并播报到指定群聊。 |
| 1229 | astrbot_plugin_timeprogress | 119 | other | watch | 用来可视化时间的，查看今年过去了多少时间。 |
| 1230 | astrbot_plugin_whale_radar | 119 | personality | have | 群聊被动监听：每条没唤醒她的群消息都会看一眼，「是不是在聊她感兴趣的东西」。 兴趣词按「方向」分组（股票、游戏、吃饭……），每个方向有自己的权重， 命中越多概率越高；没命中时可以再用一个便宜的模型打个 0-10 分，够分才插话。 一个词可以挂同义词/衍生词/外号（如「崩铁」挂「星穹铁道」「镜流」「世 |
| 1231 | astrbot_plugin_pixiv | 119 | other | watch | 用自然语言搜索 Pixiv 插画，按收藏、点赞和浏览筛选，支持多页预览、当前会话发图与画廊管理。 |
| 1232 | astrbot_plugin_image_caption_cache | 119 | other | watch | 为 AstrBot 提供兼容 OpenAI 协议的图片转述缓存代理。 |
| 1233 | astrbot_plugin_read_local_image | 118 | other | watch | 读取本地图片文件并使用 ImageContent 机制让 LLM 立即分析图片内容 |
| 1234 | ms_aiimg | 118 | image-gen | watch | 接入魔搭社区文生图模型 |
| 1235 | astrbot_plugin_minecraft_motd | 118 | other | watch | Minecraft motd 探测服务器的插件 |
| 1236 | astrbot_plugin_farm | 118 | game | have | 农场种植小游戏，支持种子商店、分类仓库、作物交易、除虫、偷菜、土地开垦和动态图片帮助；使用本地存档。 |
| 1237 | astrbot_plugin_wsde | 118 | tts | watch | 一个发出随机维什戴尔游戏日语语音的AstrBot插件 |
| 1238 | astrbot_plugin_minecraft_queqiao | 118 | other | watch | 通过鹊桥模组连接 Minecraft 服务器，实现消息互通、图片互通、服务器管理与 AI 聊天 |
| 1239 | astrbot_plugin_apiver_meme_drawer_arcaea_pjsk | 118 | sticker | borrow | 通过vercel部署的arc-pjsk表情api生成表情包。 |
| 1240 | astrbot_plugin_qq_personal_memory | 118 | memory | have | 按 QQ 号保存独立个人记忆，并强化引用、@、群名场景下的当前发言人身份锁定，减少群聊中认错人的情况 |
| 1241 | astrbot_plugin_zhihuSummary | 117 | other | watch | 发送知乎回答/文章链接，自动生成 AI 结构化总结。  知乎总结：发送知乎链接，自动抓取内容并通过 LLM 生成结构化总结 多类型支持：回答、专栏文章、问题（自动取高赞回答） 自动识别：开启后自动检测群聊中的知乎链接并生成总结 精美渲染：总结可渲染为卡片图片（需 playwright） 长文本处理： |
| 1242 | astrbot_plugin_mewgenics | 117 | game | have | 快速查询《喵喵的结合》(Mewgenics) 的 Wiki 数据。 |
| 1243 | astrbot_plugin_nobot | 117 | group-admin | have | 人机去死！找出并禁言群里的人机! |
| 1244 | astrbot_plugin_weather_wttr_in | 117 | info-push | have | 使用 wttr.in 查询天气（llm工具） |
| 1245 | fakesession_assistant | 117 | other | watch | 基于 NapCat API 的合并转发消息伪造工具。支持自定义发送者、昵称、时间戳、@ 提及和图片 |
| 1246 | astrbot_plugin_message_filter | 117 | other | watch | 在机器人发送回复前自动净化消息，实现：移除 emoji、破折号转逗号。支持自定义删除/替换规则。 |
| 1247 | astrbot_plugin_life | 117 | proactive | watch | 日程驱动的 QQ 拟人陪伴：角色有自己的一天，聊天时带上当下的生活状态；会按设定的间隔和免打扰时段主动找你聊天、关心你提到的事；支持语音、自拍和 QQ 空间。网页聊天支持语音。 |
| 1248 | astrbot_plugin_sts2_data | 116 | other | watch | 查询杀戮尖塔2数据库信息。 |
| 1249 | astrbot_plugin_deobfuscation | 116 | other | watch | 小番茄图片混淆/解混淆插件，基于Gilbert 2D空间填充曲线算法 |
| 1250 | astrbot_plugin_steam_status | 116 | other | watch | 一个用于 AstrBot 的 Steam 服务状态监控插件。支持手动指令查询和后台自动监控推送。 |
| 1251 | astrbot_plugin_openlistfile | 116 | other | watch | Openlist 文件管理插件，支持浏览、搜索、下载 Openlist 上的文件。 |
| 1252 | astrbot_plugin_Furimg_Cloud | 116 | other | watch | 这个是兽云祭官方 API 对接插件，用来获取一张精选的 furry 图片，可以是毛毛照片也可以是兽兽插画或者设定图，该插件的所有图片均来自群友投稿 |
| 1253 | astrbot_plugin_namepossession | 116 | other | watch | [QQ] 随机夺舍 QQ 群友名字（群名）。 |
| 1254 | astrbot_plugin_video_sora | 116 | other | watch | 使用 OpenAI Sora 模型生成视频 |
| 1255 | astrbot_plugin_douyin_subscribe | 116 | media-parse | borrow | 订阅抖音账号，TA 发布新作品时自动推送。图文发图片、视频发视频；支持视频大小限制降级、视频/群文件两种发送方式，并自带 WebUI 管理页（搜索订阅 / 群列表选择 / 实时预览推送效果）。签名纯 Python 实现，无需 Node.js。 |
| 1256 | astrbot_plugin_tmp_bot | 116 | other | watch | 欧洲卡车模拟2 TMP查询机器人 - 支持玩家信息查询、位置查询、服务器状态查询、里程排行榜、地图DLC、足迹等功能 |
| 1257 | astrbot_plugin_spider | 115 | info-push | have | 订阅不同网站的更新并推送给用户 |
| 1258 | astrbot_plugin_ql_bilibili_account_manager | 115 | media-parse | borrow | 将账号扫码登录到青龙的Bili任务执行器，需要青龙面板且安装BiliToolPro，不会配置可以看仓库 |
| 1259 | astrbot_plugin_Qsign | 115 | game | have | 二次元图片签到以及好友买卖，对接牛牛商城，仅支持qq且仅支持非官方bot(其他平台请自行测试） |
| 1260 | astrbot_plugin_music_pro | 115 | tts | watch | 网易云nodejs点歌插件 |
| 1261 | hltv_cs_unified | 115 | other | watch | CS2比赛，战队，选手信息查询插件，整合比赛追踪（/match）、选手数据（/player）、战队信息（/team）。 数据来源Liquipedia与HLTV。安装插件前请确保 requirements.txt 中的依赖已安装。 |
| 1262 | astrbot_plugin_hudong | 115 | game | have | 免 @ 触发的新一代群聊互动插件 —— 签到、积分、抽奖、猜数字、接龙、21点、数字炸弹、猜谜、海龟汤、抢答、竞猜、井字棋、扫雷、数字破解、决斗盘、大转盘、成就标签、转生、赛季、宠物养成、群 Boss 战、称号商店、亲密度、PK 等 40+ 玩法一站式齐全。 |
| 1263 | astrbot_plugin_all_balance | 115 | other | watch | 使用 /余额 查询New API 和 DeepSeek 官方账户余额，支持自定义回复模板及 LLM 自然语言回复。 |
| 1264 | astrbot_plugin_observe_life | 115 | proactive | watch | 给她一双看得见你日常的眼睛。  插件在本机定时采样当前前台窗口（进程名 + 窗口标题 + 键鼠空闲时长），把零散的采样合并成连续的 「活动片段」，然后做三件事：  1. **对话注入** —— 每轮回复前，把「她此刻看到的」作为一小段内容附在用户消息末尾    （约 100~200 字）。挂在附加块 |
| 1265 | astrbot_plugin_history_day | 114 | other | watch | 查看 历史上的某天 发生的大事 (历史上的今天的增强版) |
| 1266 | astrbot_plugin_conversation_flow | 114 | other | watch | 凝心溯溪系列对话模块：让 AstrBot 更自然地判断何时回应、如何分段、怎样衔接上下文， 并处理群聊参与、短期跨会话连续性、图片意图和服务式追问收尾。 |
| 1267 | astrbot_plugin_llm_wiki | 114 | kb-rag | have | 通过 Local HTTP API 将 LLM Wiki 作为 AstrBot 的只读知识库，支持自动检索、LLM 工具和手动查询。 |
| 1268 | astrbot_plugin_quiz | 112 | other | watch | 一个基于FoxQuiz网站的知识问答插件 |
| 1269 | astrbot_plugin_qqadmin_plus | 112 | group-admin | have | QQ群管插件（Fork自Zhalslar/astrbot_plugin_qqadmin），功能包括：禁言、全体禁言、踢人、拉黑、改群昵称、改头衔、设管理员、设精华、撤回消息、改群头像、改群名、发群公告、整理群友信息等等 |
| 1270 | astrbot_plugin_minimax_alert | 111 | other | watch | 查询 MiniMax Token Plan API 用量信息，支持国内版和国际版。查看5小时周期和本周周期的剩余额度。 |
| 1271 | astrbot_plugin_smart_translator | 111 | other | watch | 基于 LLM 的自然语言翻译插件，支持 50+ 语言、二次翻译和多种输出格式 |
| 1272 | astrbot_plugin_temp-email | 111 | platform | have | 获取临时邮箱 |
| 1273 | astrbot_plugin_waves | 111 | memory | have | 记忆与情感的一体化插件：四层记忆、双轨情感、标签联想与两跳推理、真实遗忘、日记、星图与记忆实验室，支持多语言与日预算。 |
| 1274 | astrbot_plugin_llm_blocker | 111 | other | watch | 在指定群聊或私聊（单独聊天）中禁用 AstrBot 的 LLM 聊天响应，保留其他插件功能（指令、正则响应等）照常工作。支持黑名单/白名单两种拦截模式。  指令（8 个，无指令组，均需管理员权限，需 @ 机器人或唤醒前缀）： - /blockllm、/unblockllm：禁用/恢复指定群的 LLM |
| 1275 | astrbot_plugin_babirthday | 110 | game | have | Blue Archive 蔚蓝档案学员生日提醒插件 |
| 1276 | astrbot_plugin_hltv | 110 | info-push | have | CS2赛事HLTV 查询插件。直播比分与提醒、逐图及完赛 Rating、赛事内选手数据榜、年度 TOP20、战队/选手图片卡、赛程赛果、双排名、中英双语新闻与每日推送。 |
| 1277 | astrbot_plugin_rate_limiter | 110 | other | watch | 滑动窗口限制私聊/群聊对话次数：超限后 @机器人 提示、引用/前缀唤醒静默拦截，支持真实解锁倒计时、额度用尽提醒、白名单与按用户/群单独设限 |
| 1278 | astrbot_plugin_delay_response | 110 | other | watch | 通过Jev等决策模型判断用户多条消息的表达完整度，从而智能调节等待时间，最终一并回复多条消息。 |
| 1279 | astrbot_plugin_deepseek_web_search | 110 | other | watch | 基于 DeepSeek 官方「网页搜索与抓取」接口的 AstrBot 插件。  - 提供 LLM 函数工具 deepseek_web_search / deepseek_web_fetch，对话中可自动搜索与抓取网页 - 提供聊天指令 /ds搜索、/ds抓取、/ds状态、/ds帮助 - 支持 sit |
| 1280 | textToImg | 109 | other | watch | 修改自 薄暝(二创)和喵喵的 OpenRouter 生图插件(原创)。使用 OpenAI 格式的免费 API 生成图片兼容硅基流动生图 |
| 1281 | astrbot_qqemotionreply | 109 | sticker | borrow | [仅 aiocqhttp] 给 QQ 引用的消息贴表情 |
| 1282 | astrbot_plugin_guaguale | 109 | game | have | 刮刮乐小游戏插件，使用[/刮刮乐帮助]查看指令 |
| 1283 | astrbot_plugin_maimaidx_prober | 109 | game | have | 舞萌 DX（maimai DX）双源查分插件。  数据源： - diving-fish（水鱼）：B50、个人成绩、按版本成绩、Token 绑定、OAuth 绑定 - lxns（落雪）：玩家资料、AP50、热力图、趋势、历史、排行、年度回顾、收藏品、   双向成绩同步、曲目评论  另有 AWMC 信息 |
| 1284 | astrbot_plugin_deepseek_balance | 109 | other | watch | 查询 DeepSeek API Key 的账户余额，支持余额账本、定期检查、低余额提醒与自动切换供应商 |
| 1285 | astrbot_plugin_minimax_tts | 109 | tts | watch | 通过终逢小站调用 MiniMax，内置角色音色，支持高质量音频、工具主动语音和分段语音。 |
| 1286 | astrbot_plugin_dsa_pusher | 108 | other | watch | 接收股票分析报告并通过Astrbot推送到聊天平台，支持文字/Markdown/图片三模式、多图拆分、多目标推送、聊天指令控制（分析查询/自选管理/推送开关/报告查看） |
| 1287 | astrbot_plugin_self_review | 108 | memory | have | 每天定点回顾「昨天」：把对话、昨天入库的事实、行为记录、自己写过的东西放在一起， 提炼出 **≤3 条反思**和**一篇日记**。  **为什么单独一个库**：事实回答「这句话答得上哪条记忆」，反思回答「这件事跟现在的 bot 有没有关系」。信任级不同、衰减不同、注入位置不同。混在一起，推断会顶掉用 |
| 1288 | astrbot_plugin_fatfish_catchup | 108 | other | watch | AstrBot 重启、QQ 掉线、模型出错时，私聊它、@ 它的话就石沉大海。装上以后恢复了自己去翻聊天记录，把冲它说的、没回的按对话补回一次（群里 @ 那个人），太久的、补过的、别人家 AI 的不补。细节和配置见 README。 |
| 1289 | better_qq | 108 | other | watch | 面向 SnowLuma + AstrBot 的 QQ 聊天体验增强：修复图片缺 rkey 导致看不到图；补最近图片与被引用图片；只 @ 时补聊天上下文；把主人顶号发的消息补进上下文（群聊/私聊）；按概率引用回复；对方一条消息说了几件事时，正常回复后再自动补一句（自动补话）。所有功能可在配置里开关。 |
| 1290 | astrbot_plugin_whatsapp_adapter | 107 | other | watch | 基于本地 Gateway 和 WhatsApp Web/Baileys 的 AstrBot 消息平台适配器，支持插件管理页扫码登录、私聊、群聊、媒体收发和访问控制。 |
| 1291 | astrbot_plugin_subagent_worktogether | 107 | other | watch | 能够支持子Agent之间直接通信，可以控制互相通信的深度和次数，可以输出Agent互相通信的完整链路 |
| 1292 | github_monitor_shell | 107 | other | watch | 定时监控GitHub仓库commit变化并发送通知,还能查询仓库所有open的Issue方便管理问题 |
| 1293 | command_to_llm | 107 | other | watch | 将指令（比如/help）转换为LLM函数（比如 get_help）调用，让AI能够通过LLM函数执行其他插件的指令，支持动态添加和管理指令映射 |
| 1294 | astrbot_plugin_better_qq_chat | 107 | memory | have | 让 AstrBot 在 QQ 里拥有更自然的互动能力：  1. 戳一戳：LLM 可自主调用 qq_poke；被唤醒时只给一句可选提示； 2. 跟戳：别人戳别人时按低概率和冷却自动跟戳； 3. 被戳反戳：Bot 被戳时按概率反戳，并可与 poke_to_llm 的文本响应协作或避让； 4. 表情回应： |
| 1295 | astrbot_plugin_nai_image | 107 | image-gen | watch | AI 生图插件。发送 /生图 中文描述，先由大模型把中文转换成英文绘画 tag，再调用 NovelAI 生成二次元插画并发送。 也支持 /生图 吐司 中文描述 改走吐司（TAMS / tusi.cn）工作流模板接口。  ## 功能说明 - 🎨 `/生图 中文描述`：大模型转英文绘画 tag → No |
| 1296 | astrbot_plugin_fishaudio_tts | 107 | tts | watch | 基于 FishAudio API 的 TTS 插件。管理员通过 /tts 开关控制功能，开启后支持音色名说文本和 tts_speak LLM 语音工具。 |
| 1297 | astrbot_plugin_humanizer | 107 | other | watch | 模型写中文时有一套稳定的话术壳：开场「这是一个很好的问题」「首先…其次…最后」， 收尾「希望这对你有帮助」「如果还有其他问题，欢迎随时提问」，中间堆「总的来说」 「需要注意的是」，再加上 markdown 标题、加粗、长破折号——在 QQ 这种不渲染 markdown 的聊天窗口里，这些痕迹比内容本 |
| 1298 | astrbot_plugin_random_likes | 106 | other | watch | [仅 QQ] 智能检测点赞关键词并自动随机点赞数 |
| 1299 | astrbot_plugin_warframe_sdjkbot | 106 | platform | have | Warframe SDJKBOT：世界状态 / 市场查价 / 伤害计算与配卡识别 / 紫卡分析 / 遗物与部件反查 / 蹲点推送，支持渲染成 Orokin 风格图片卡片。 **58 个主指令**，指令为自由参数式（主指令 + 内容 + 修饰符，位置任意），发送「帮助」查看完整指令表。 数据来自 DE |
| 1300 | astrbot_plugin_bilibili_season_subscribe | 106 | media-parse | borrow | 支持视频链接、BV／AV 和引用 QQ 分享卡片订阅系列，优先接上合集，没有合集时按 UP、节目及版本追更。支持独立规则、投稿补漏、失败重试、字幕／语音转写总结与 AI 聊天调用。 |
| 1301 | astrbot_plugin_bili_learn | 106 | kb-rag | have | Cookie 选填；无 Cookie 时仅搜索公开内容。不点赞、不评论、不私信、不投币、不改人格文件。  主要功能： - 按兴趣词顺序自动刷取公开视频，生成结构化摘要写入 AstrBot 官方知识库 - 用户发 B 站链接/BV 号时，AI 按需读取并用自己的人设回复 - AI 可查询已学知识：语义 |
| 1302 | astrbot_plugin_indextts2 | 106 | kb-rag | have | 通过 HTTP 调用 IndexTTS 2.5 API，支持情感参考音频、情感向量、自动语音回复和 LLM Tool。 |
| 1303 | astrbot_plugin_nomi_music | 106 | proactive | watch | 让 bot 真正进入网易云音乐的「一起听」房间，和你在听同一首歌。  功能： - 自动接受「一起听」邀请，进入同一个房间； - 读出当前播放的歌曲、歌手、专辑、播放进度，并定位到**当前唱到哪一句歌词**； - 提供 `music_now` / `music_room` 两个 LLM 工具，让 bo |
| 1304 | astrbot_plugin_blue_archive_auto_calendar | 105 | platform | have | Blue Archive 蔚蓝档案定时发送活动日历以及活动结束提醒插件 |
| 1305 | astrbot_plugin_emojimix | 105 | other | watch | 一个用于 AstrBot 的插件，实现类似Google Emoji Kitchen(合成emoji)的效果。 |
| 1306 | osu | 105 | game | have | 基于osu!track与osu!官方api实现的包含osu!成绩上传，谱面查询等功能的插件 |
| 1307 | astrbot_plugin_animetrace | 105 | personality | have | AnimeTrace 动漫 / Galgame 角色识别：引用一张图片回复 anime 即可，无需唤醒词。支持多候选、AI 生成图检测与冷却限流 |
| 1308 | astrbot_plugin_qq_multi_poke | 105 | game | have | 让你的 AI 获得强大的戳一戳连续点击能力，用于建立有趣的多元互动。模型只需提交目标 QQ 号与次数；插件顺序执行并以 OneBot 的真实结果为准，不另设次数或身份限制。 |
| 1309 | astrbot_plugin_nezhatz | 104 | other | watch | 查看哪吒监控站点的服务器状态等信息 |
| 1310 | astrbot_plugin_group_quiz | 104 | info-push | have | 定时推送技术题目、支持小组订阅和批次管理的群聊答题插件 |
| 1311 | astrbot_plugin_battlefield_tool | 104 | other | watch | 战地风云战绩查询插件 |
| 1312 | astrbot_plugin_qq_group_manager | 104 | group-admin | have | 面向 QQ 官方机器人（qq_official / qq_official_webhook）与 QQ 非官方 OneBot v11（aiocqhttp）的群管理插件：群档案与能力自检、 基于 AstrBot 已配置 LLM 的群消息合法性识别与处置（警告/撤回/禁言/上报）、 入群申请智能审批、群成 |
| 1313 | astrbot_plugin_world_journey | 104 | other | watch | 让她真的出门旅行：自己挑目的地和交通方式，路上耗真实时间；到了按当地时间吃饭、看日出、写日记。上游引擎在 raw/，AstrBot 侧只是套壳。 |
| 1314 | astrbot_plugin_group_interject | 104 | other | watch | 让 Bot 在 QQ 群里不用被 @ 也能自然地接话。  · 你（focus_user_ids 里的号）说话时必定接话 · 其他人说话时，先用小模型判断「这句话该不该插嘴」，再决定要不要说 · 冷却时间 / 每小时上限 / 免打扰时段，防止刷屏和烧 token · 群白名单、黑名单、昵称关键词（叫你 |
| 1315 | astrbot_plugin_group_cup | 104 | other | watch | 检测到'^群杯子'指令后，在群友中随机抽取一名作为当天的群杯子。每天同一群只抽一次，仅群主/管理员可用。'^群杯子排行'查看历史排行榜前十名。 |
| 1316 | astrbot_plugin_fund | 103 | other | watch | 基于 AstrBot 的个人基金查询、持仓分析、风险提示与报告生成插件。 |
| 1317 | astrbot_plugin_self_code | 103 | other | watch | 一个用于 AstrBot 的 AI 编程助手插件。它把聊天指令转为 codex CLI 操作，在 workspace 中生成/修改插件代码，并支持测试和部署。 |
| 1318 | echo_avatar | 103 | other | watch | 学习指定用户的说话方式并生成专业的Prompt，仅限全局管理员使用。 |
| 1319 | astrbot_plugin_opencode_go_session | 103 | tts | watch | OpenCode Go 要求请求带上 x-opencode-session，否则返回 400 MissingSessionID。 AstrBot 的 custom_headers 只能配一个静态值，所有会话共用。本插件在 on_llm_request 时取当前会话 ID 存入 ContextVar， |
| 1320 | astrbot_plugin_xhs_reader | 103 | media-parse | borrow | 读取消息中的小红书笔记链接，将标题、正文、互动数据、首屏评论和可选图片解读作为本轮临时参考资料交给模型。只读、免登录、免 Cookie。 |
| 1321 | astrbot_plugin_goons | 102 | game | have | 查询逃离塔科夫中 Goons 小队（三狗）的实时位置 |
| 1322 | astrbot_plugin_hangout | 102 | other | watch | 让管理员可以查询机器人的调用情况，不查询聊天记录，保护用户的隐私。管理员需要单独设置。 |
| 1323 | astrbot_plugin_sora | 102 | other | watch | 使用 newAPI 生成视频。指令 文生视频 <提示词> 或 图生视频 <提示词> + 图片。 |
| 1324 | astrbot_plugin_weakblacklist | 102 | other | watch | [仅QQ] 弱黑名单插件，对处于黑名单用户进行概率性回复，并由保底回复机制，即使@机器人也进行概率回复。主要是防止多个机器人炸群。 |
| 1325 | astrbot_plugin_mindscape | 102 | memory | have | 为 AstrBot 打造的群聊增强插件：分层长期记忆与人格语气、表情包调度、报错拦截与沉默权，并把没被唤醒的群消息也带进上下文。 |
| 1326 | cs2_results | 102 | info-push | have | HLTV CS2 赛事战报、RSS 资讯与 LLM 工具查询:支持赛程、选手/战队详情、订阅、比分和卡片渲染 |
| 1327 | astrbot_plugin_api_budget | 102 | group-admin | have | 统计 AstrBot 每次对话的 token 花费（区分缓存命中与高峰/空闲价）， 设置一个每日总额度（群聊 + 私聊合计）；支持白名单绕过与不计费、 白名单花费单独显示、高峰时段禁言、超额提醒次数上限； 额度用完后非白名单自动关闭搜索工具；超限自动拦截并提示， 管理员可在聊天中发送 /额度、/额度 |
| 1328 | astrbot_plugin_wfbot | 101 | game | have | Warframe 数据层（世界状态/PublicExport/多镜像/market），支持缓存、清理与定时刷新 |
| 1329 | astrbot_plugin_daliy_news | 101 | info-push | have | 一个简单的不稳定的Astrbot每日60s新闻定时推送插件。 |
| 1330 | astrbot_plugin_spark_tts | 101 | tts | watch | 用于使用 Spark-TTS 进行文字转语音。 |
| 1331 | astrbot_plugin_llmAtTool | 101 | other | watch | 提供一个可供 LLM 调用的 @ 用户工具(Tool) |
| 1332 | astrbot-plugin-relaychat | 101 | personality | have | 一款为 AstrBot 设计的插件，允许多个虚拟Bot人格在同一个聊天会话（目前主要支持群聊）中进行轮流的连锁回复，营造更生动和沉浸的群聊对话体验。 |
| 1333 | astrbot_plugin_goldprice | 101 | other | watch | 获取实时国内黄金价格 |
| 1334 | astrbot_plugin_astrcraft | 101 | media-parse | borrow | **Astrcraft** 把 AstrBot 的机器人送进 Minecraft，让它**以真实玩家身份自己生活**。  不是"会聊天的 NPC"，也不是"瞬移+秒破方块"的脚本：它的每个动作都走原版玩家代码路径， 和红石、怪物 AI、别人的建筑站在同一套规则里。  - **真实客户端**：原版物理 |
| 1335 | astrbot_plugin_qq_ai_draw | 101 | image-gen | watch | 群里 @机器人 说「画一个佩丽卡」，AI 自动优化提示词、识别角色并自动触发对应 LoRA，调用本地 WebUI Forge 出图发回群里。内置 5000 条角色字典，支持画风预设、分辨率自由写法（精准/横竖方/1080p~4k）、队列配额。完整部署与使用教程见仓库 README。 |
| 1336 | astrbot_plugin_affection_keeper | 101 | other | watch | 为指定用户固定注入好感度与关系状态，不依赖聊天历史；支持私聊和群聊，/reset 后仍生效。优先使用 AstrBot 的临时用户上下文注入，尽量避免破坏 Prompt Cache。 |
| 1337 | astrbot_plugin_githubapp_adapter | 100 | platform | have | 为 AstrBot 提供 GitHub App Webhook 适配与受控仓库操作能力。 |
| 1338 | astrbot_plugin_shutdown | 100 | other | watch | 用命令或者配置定时关闭 AstrBot 服务 LLM |
| 1339 | astrbot_plugin_retry_v2 | 100 | other | watch | 一个基于事件钩子的、处理空回复和截断等非完整响应的重试插件 |
| 1340 | astrbot_plugin_VITS | 100 | tts | watch | 硅基流动api语音合成 |
| 1341 | astrbot_plugin_personatrace | 100 | personality | have | 让 AstrBot 更加拟人化。聊得越久，对你的理解越深，越懂你。 |
| 1342 | astrbot_plugin_astrkb_writer | 100 | kb-rag | have | 让 Bot 自由写入、更新、删除 AstrBot 原生知识库文档的轻量插件 |
| 1343 | astrbot_plugin_circle_memory | 100 | memory | have | 在飞书聊了一半的对话，切到微信、QQ 接着聊，AI 记得之前说过什么——把多个平台（飞书、微信、QQ、Telegram 等）的多个会话组成「会话组」，组内跨平台共享同一份对话历史。  核心特性： - 每个组拥有稳定组 ID（g-xxxx），组共享会话以组 ID 作为 conversation_id  |
| 1344 | daily_digest | 100 | group-stats | borrow | 每日简报：天气 + 昨日国内/国际新闻 + 科技/医药/政策前沿（政策接政府官方网站）、GitHub 日升榜，AI 总结后同时推送图片与 .md 文件 |
| 1345 | astrbot_plugin_fish_tts | 100 | memory | have | Fish TTS优化：直连 Fish Audio（可走自建反代），短句开口说、长文发文字；支持 S2 情绪标签 [happy] [whispering]，发文字时自动去标签；可保存多个带备注的音色 ID 并随时切换，插件页面里能管理、试听；另带语音记忆，让大模型知道自己发过什么语音、被引用的是哪一句 |
| 1346 | astrbot_plugin_deepseek_peak_switch | 100 | other | watch | 按 DeepSeek 官方高峰/低峰时段，为不同 bot 自动切换模型提供商；支持自动拉取官方文档、法定节假日识别、手动自由配置时段、多 bot 独立配置与强制切换 |
| 1347 | astrbot_plugin_sticker_semantic | 100 | sticker | borrow | 独立的表情包分类与语境化发送：自动学习/导入、视觉模型打标签、轻回复只发表情包、普通回复按语境附加。 |
| 1348 | astrbot_plugin_simple_injections | 99 | other | watch | 轻量级提示词注入插件。允许用户使用指令进行指定轮次的提示词注入，适用于跑团主持人等需要在规定轮次内持续完成特定任务的场景。 |
| 1349 | astrbot_plugin_ip_proxy | 99 | other | watch | 一个将HTTP代理API转换为本地代理的AstrBot插件 |
| 1350 | text2image | 99 | other | watch | 一款灵活高效的文本转图片工具，让文字呈现更具视觉张力 |
| 1351 | astrbot_plugin_search_pic | 99 | other | watch | 从 https://saucenao.com/ 搜索图片，功能是以图搜图 |
| 1352 | astrbot_plugin_toy_controller | 99 | other | watch | 拦截 LLM 回复中的特定标签输出并控制对应设备。支持持续震动、花样模式切换与加热控制。 |
| 1353 | luck_rank | 99 | game | have | AstrBot 群聊签到与抽卡互动插件：支持每日运势、命运牌、功能牌、称号、排行、决斗，并提供高度自定义的可视化 WebUI 与访客协作能力。 |
| 1354 | astrbot_plugin_active_chat | 99 | proactive | watch | 让bot在群聊主动说话，静默触发、概率递增判定、可选截屏主动消息（需桌面环境） |
| 1355 | astrbot_plugin_agent_search | 99 | info-push | have | 提供国内权威新闻、B 站热门、视频搜索、天气和管理员联网兜底工具。 |
| 1356 | astrbot_plugin_song_identifier | 99 | tts | watch | 支持视频文件、音频文件、语音消息听歌识曲/音乐识别 |
| 1357 | astrbot_plugin_bilibili_browser | 99 | media-parse | borrow | 用于 AstrBot 的 Bilibili 视频浏览插件，支持命令操作、LLM 函数调用、WebUI 登录与设置。 |
| 1358 | friend_gate | 99 | info-push | have | AstrBot 本身不处理 OneBot 的 request 事件，好友申请和群邀请会一直躺在 QQ 里没人管。 这个插件订阅协议端的 request 事件，按黑名单 / 白名单 / 暗号 / 每小时上限决定同意还是拒绝， 并把结果私聊告诉管理员。好友申请、被拉进群、别人申请进你的群，三种请求一套规 |
| 1359 | astrbot_plugin_file_checker | 98 | other | watch | 对 QQ 群中新上传的群文件进行有效性检查和内容预览，同时支持文件查重、失效补档与转发备份功能。 |
| 1360 | astrbot_plugin_kfc_thursday | 98 | other | watch | [仅 aiocqhttp] 让大模型发送疯狂星期四文案，图片加入阅读readme |
| 1361 | mccloud_img | 98 | other | watch | 一个从API获取图片的插件，支持自定义API地址。使用 /img 获取图片。配置可填https://api.lolicon.app/setu/v2 *图二次元的获取。 |
| 1362 | astrbot_plugin_helloworld | 98 | other | watch | 一个为 AstrBot 设计的自定义插件模板，并演示了 AstrBot 插件支持的能力。基于官方基础模板扩展而来。适合作为个人或团队维护 AstrBot 插件仓库时的起始模板。 |
| 1363 | astrbot_TierMem | 98 | memory | have | 无需 Embedding 模型，基于多层原子记忆与关系知识图谱的长期记忆插件。 |
| 1364 | astrbot_plugin_peer_context_guard | 98 | other | watch | 面向 QQ 群聊的多机器人发送者过滤与唤醒插件，使用 aiocqhttp（OneBot v11）适配器。 按机器人实例和群聊设置通讯录，根据登记的 QQ 号过滤机器人发送者，减少相互触发。 支持实例通用正则与群聊专用覆盖，可在 @ 或关键词唤醒时附带近期文字上下文。 可选保存并注入机器人只读历史；空 |
| 1365 | astrbot_plugin_member_notice | 98 | group-admin | have | 群成员入群/退群时发送自定义欢迎/退群语，支持黑白名单，不会被其他欢迎插件屏蔽 |
| 1366 | astrbot_plugin_shio | 98 | memory | have | 给你的机器人完整的一生。保留角色性格，让它听懂语境、自然参与群聊，并用合适的节奏回应你；可与记忆、搜索和表情包插件搭配，让每一次相遇延续成日常。 |
| 1367 | astrbot_plugin_message_debouncing | 98 | tts | watch | AstrBot 私聊消息防抖插件。当检测到需要进行 LLM 对话时，倒计时等待用户后续消息并自动聚合文本、图片、语音等多模态消息一次性提交给 LLM 处理；含并发会话保护与无损指令穿透，只作用于私聊，不干预群聊。 |
| 1368 | astrbot-plugin-dida-todo | 97 | other | watch | 将滴答清单（TickTick / 滴答清单）无缝集成到 AstrBot 中，支持自然语言创建任务和查询待办。 利用 AstrBot 的 Function Calling 能力，你只需像对人说话一样：“明天下午3点提醒我开会”，即可自动创建带截止时间的任务。 |
| 1369 | saris_Economic | 97 | game | have | 群签到插件(可自定义图片)。‼️ 需要安装前置插件 astrbot_plugin_saris_db 👇 |
| 1370 | superpoke | 97 | game | have | 超级戳一戳根据，让戳一戳能够调用其他插件指令 |
| 1371 | mccloud_site | 97 | other | watch | 一个集成了网站测试工具的插件，支持网站连通性测试、速度测试、域名查询、端口扫描和网站截图功能。使用/sitehelp查看帮助。 |
| 1372 | astrbot_plugin_qq_group_admin | 97 | group-admin | have | QQ 官方机器人群管理：禁言、踢人、入群申请审批、进群验证、成员进退群通知、分群管理员和 LLM 工具 |
| 1373 | astrbot_plugin_md_render | 97 | other | watch | 无浏览器 Markdown / LaTeX / HTML / Mermaid 转图片；分段；Markdown 清洗；可只处理模型回复 |
| 1374 | astrbot_plugin_emotion_pics | 97 | personality | have | 文字聊天容易干。这个插件不改变回复内容，只在合适的情绪点补一张图：面板里传图、标情绪，配好关键词，说到对应情绪时按概率附上一张。图库在本地，不走第三方。 |
| 1375 | astrbot_plugin_mj | 97 | other | watch | 检测到 mj / kfc / isa / 牛来 / kskbl 时自动回复；mj、kfc 发视频，isa 发图片，kskbl 随机文字；可在插件设置中开关是否发送文字 |
| 1376 | astrbot_plugin_qinglong | 96 | other | watch | 通过聊天管理青龙面板，支持任务管理、环境变量、日志查看等 |
| 1377 | astrbot_plugin_bananic_ninjutsu | 96 | other | watch | 适配 Napcat 的 AstrBot 插件，用于 🍌（nano banana），先进的变量 & 参数系统 |
| 1378 | astrbot_plugin_bili_userinfo | 96 | media-parse | borrow | B站用户信息查询 |
| 1379 | astrbot_plugin_qinyu | 96 | tts | watch | 有情绪的语音。说话、朗读、唱歌共用一套引擎与风格，一句话能念出来，也能唱出来。核心能力：朗读与唱歌可指向不同引擎实例；五维风格任意叠加；语气自适应人设与回复内容；私聊群聊统一；可视化管理面板。支持 MiMo V2.5、MiMo V2、VoiceDesign、VoiceClone、MiniMax、Op |
| 1380 | astrbot_plugin_dsh_acp | 96 | info-push | have | 通过官方 ACP 协议把 DeepSeek Harness 接入 AstrBot。可实现新建、接管与订阅会话，选择会话模型、切换推理档位，查看历史消息等。让bot全面接管DSH |
| 1381 | AstrScheduleSync | 95 | platform | have | 让 AstrBot Agent 通过自然语言创建/查询/修改/删除 ICS 标准格式日历事件和待办，自动上传到 Radicale CalDAV 服务器。用户可通过支持定时导入/定时同步CavDAV日程/待办的软件实现多端日程同步管理 |
| 1382 | astrbot_plugin_xiuxian | 95 | game | have | 基于astrbot框架的文字修仙游戏 |
| 1383 | astrbot_plugin_afdian | 95 | other | watch | 爱发电对接插件，接受用户打赏，实时推送订单情况 |
| 1384 | astrbot_plugin_password | 95 | other | watch | 强制修改astrbot面板的用户名、密码（仅管理员可用） |
| 1385 | astrbot_plugin_arknight_gacha_simulator | 95 | payment | exclude | tip: 首次运行插件在完全加载之后需要再热重载刷新插件数据以正常使用 抽卡时不要挂国外的梯子！！会导致api不稳定导致十连图片素材缺失 可能会出现一些问题导致短时间内首次下载无法使用，可以等一段时间 忠实还原明日方舟抽卡机制的 AstrBot 抽卡模拟器插件。  功能： - 多卡池并行：标准 /  |
| 1386 | astrbot_plugin_aicu_analysis | 95 | media-parse | borrow | 除了查询评论外，增加了查询视频弹幕和直播弹幕的功能。增加了查询资料卡显示粉丝牌等级及装扮 |
| 1387 | astrbot_plugin_screen_spy | 95 | other | watch | 允许大模型调用函数工具触发用户本地电脑截图，并进行视觉分析回复。 |
| 1388 | astrbot_plugin_webnovel_downloader | 95 | other | watch | 基于 Legado/阅读书源的 AstrBot 网文下载插件，支持导入书源、搜索聚合、多源预检下载、正文净化和 TXT 装订。 |
| 1389 | astrbot_plugin_sender_activation | 95 | other | watch | 用这款 AstrBot 插件，让你的 AI 获得限时免@的主动回复能力：持续关注或追踪群成员，定时巡查群聊上下文；用于群聊监控时，由主 Agent 决定反驳、接话或主动沉默。让你的 AI 为你战斗到底。 |
| 1390 | astrbot_plugin_mcbe_news | 94 | info-push | have | 定时监控 Minecraft 基岩版官方更新，自动使用 AI 总结并推送到群聊，支持 Beta 和正式版 |
| 1391 | error_filter | 94 | other | watch | 选择是否过滤机器人的错误回复 |
| 1392 | astrbot_plugin_latency_check | 94 | kb-rag | have | 全方位延迟诊断插件，一条指令完成多维度检测： - QQ 消息投递延迟（基于消息时间戳） - DNS 解析、TCP 建连耗时 - 文本 / 图片 / 合并转发发送耗时实测 - AI 对话延迟（支持模型列表自动识别） - AstrBot 子代理检测（LLM 链路 / 工具执行能力 / 转交链路） - 外 |
| 1393 | astrbot_plugin_nte | 94 | game | have | 异环自动签到，支持塔吉多登录、云异环验证码登录、多账号绑定、定时签到和云时长领取 |
| 1394 | astrbot_plugin_mc_admin | 93 | media-parse | borrow | 这是 Minecraft 服务器 的管理插件，支持群组服，RCON命令，list，珍珠炮落点计算，服务器工程坐标，备货清单，白名单管理等功能 |
| 1395 | astrbot-food-recommender | 93 | info-push | have | 食物推荐插件，可以根据时间、天气和季节智能推荐食物，并使用 AI 生成食物图片和描述 |
| 1396 | astrbot_plugin_romantic_memory | 93 | memory | have | 仅处理私聊的恋爱长期记忆插件：使用 AstrBot 的 LLM 与 Embedding Provider 总结对话，借助本地 ChromaDB 保存，并按语义、关键词和时间衰减唤醒相关回忆。 |
| 1397 | astrbot_plugin_openclaw_caller | 92 | other | watch | 将 AstrBot 中的长任务委派给 OpenClaw Gateway Agent 执行，支持手动命令、LLM Tool、后台任务、任务列表与结果读取。 |
| 1398 | astrbot_plugin_hapemxg_Inspect | 92 | group-admin | have | LLM 内容审查插件，集成了正则表达式与 AI 模型双重审查机制。当回复不合规时，能自动重试并智能引导模型修正，确保内容安全合规。 |
| 1399 | astrbot_plugin_anime_search | 92 | other | watch | 次世代动漫检索工具，打破次元壁的追番体验！ |
| 1400 | astrbot_plugin_anti_porn | 92 | other | watch | 用于astrbot的反瑟瑟插件 |
| 1401 | astrbot_plugin_bililive | 92 | group-admin | have | B站直播提醒、动态订阅与置顶评论图文补推，支持按 UP 主和群管理订阅、通知开关及盯梢时长，提供 Web 面板与聊天命令。 |
| 1402 | astrbot_plugin_gpt_image | 92 | other | watch | 使用 GPT Image 生成和修改图片，支持后台任务、聊天指令和 LLM Tool，图片不会写入 LLM 历史上下文。 |
| 1403 | astrbot_plugin_message_recorder | 92 | other | watch | 自动记录所有平台的聊天消息到SQLite，提供 Web 管理面板、全文搜索、数据导入导出和供其他插件调用的查询 API |
| 1404 | astrbot_plugin_weather | 91 | info-push | have | 基于 wttr.in 的天气查询插件。提供 8 个 LLM 工具（天气/预报、多城市对比、逐小时预报、日出日落、订阅预警、退订预警、预警列表、检查预警）和灾害天气预警推送系统（订阅城市后定时检查，发现暴雨/雷暴/暴雪/极端高温/大风/大雾等灾害自动全群推送）。所有指令纯中文，无需 API Key。 |
| 1405 | astrbot_plugin_anan_board | 91 | sticker | borrow | 把最终输出文本画成"安安举牌"表情图的被动插件 |
| 1406 | astrbot_plugin_ai_mind | 91 | memory | have | 给 AstrBot 里的 AI 一颗会波动的心、一份记得住人的记性、一张说得像人话的嘴。 情绪：PAD 三维 + 40 种原型 + 词汇本体兜底，按真实时间衰减；身体层（昼夜节律/能量/饥饿/ 压力/疾病/生理周期）只给情绪一层偏移，不改人设；习惯化、共情、奖励预测误差三个仿人脑功能； 日程按日期判 |
| 1407 | astrbot_plugin_subhub | 91 | media-parse | borrow | 一站式订阅推送插件。聚合 12 类内容源 + 任意 RSS/Atom： 热搜榜（微博/百度/知乎/抖音/腾讯新闻/B站/36氪）、 信息列表（Steam特惠/今日更新番剧/GitHub Trending/HackerNews/V2EX）。 按设定时间或间隔自动主动推送到群聊/会话，也可手动触发， P |
| 1408 | astrbot_plugin_group_admin | 90 | group-admin | have | AstrBot 群管插件 - 禁言/踢人/头衔/精华/撤回/群公告/关键词撤回/违规检测/排名/举报/根据关键词自动处理新人加群申请/入群验证问题和答案/群相册/群待办 |
| 1409 | astrbot_plugin_gif_vision_helper | 90 | other | watch | 将QQ GIF动图拆成多帧静态图，让多模态模型真正看懂动图（vibe coding 产物） |
| 1410 | astrbot_plugin_email_tool | 89 | platform | have | 一个能让 AI 自主决定 SMTP 发送邮件的函数工具。此外，还支持服务器内存告警和 NapCat 下线告警。 |
| 1411 | astrbot_plugin_onelastimage | 89 | other | watch | One Last Kiss 卢浮宫风格图片生成器 |
| 1412 | astrbot_plugin_Xiaomi_BandProMax | 89 | other | watch | 小米手环的新用法 |
| 1413 | mccloud_zhipu_img | 89 | other | watch | 使用智谱AI生成图片。使用 /aimg <提示词> [大小] 生成图片。需要配置哦！ |
| 1414 | astrbot_plugin_qweather | 89 | info-push | have | 基于高德地图地理编码和和风天气API的智能天气查询插件。  功能特性： - 支持实时天气、每日预报（最多7天）、逐小时预报查询 - 支持 /weather 命令调用 - 支持 LLM 自主调用（Tool Calling） - 三个独立 LLM 工具：get_current_weather（实时）/  |
| 1415 | astrbot_plugin_context_enhancer | 89 | other | watch | 自动将北京时间、用户QQ信息、群聊信息等动态上下文注入到User Prompt中，提升System Prompt缓存命中率。支持NapCat/aiocqhttp平台。所有功能均可在WebUI配置面板中独立开关。 |
| 1416 | astrbot_plugin_coeiroink_tts | 89 | tts | watch | 你是否苦恼使用远程TTS泄露信息？你是否苦恼使用远程TTS需要额外付费？快来试试本插件来进行本地TTS部署吧！本插件拥有较为良好的音频质量以及便捷的图形化设置，同时，由于是本地TTS服务所以完全免费！TTS引擎本身的安装还可以交给你的agent来完成。本插件使用 COEIROINK 引擎，把 Ast |
| 1417 | astrbot_plugin_aemeath_voice | 89 | tts | watch | BreezeBlue 优先、CosyVoice 自动回退；支持 /voice、自然语言前缀和概率语音回复 |
| 1418 | astrbot_plugin_CloudImg | 88 | other | watch | 支持上传图片/视频到 CloudFlare 图床、按文件夹或标签随机获取、文件管理及函数工具。 |
| 1419 | mirage_tank | 88 | other | watch | 用于生成幻影坦克图片的插件，支持黑白和彩色两种模式 |
| 1420 | astrbot_plugin_decode_qrcode | 88 | other | watch | 基于 OpenCV 的微信开源二维码解码模块，识别图片中的二维码并返回解码结果 |
| 1421 | litematic | 88 | game | have | 用于管理 Minecraft 投影文件，快速查看投影内容等 |
| 1422 | astrbot_plugin_custom_menu | 88 | other | watch | 自定义菜单图片，图片放置在 menu 目录下，支持格式jpg,jpeg,png,gif,bmp。 |
| 1423 | astrbot_plugin_who_at_me_pro | 88 | other | watch | 记录群聊里谁艾特过你，并渲染一张精美的图片，支持艾特提醒，避免错过重要消息。 |
| 1424 | astrbot_plugin_tencent_channel_community | 88 | other | watch | 通过 tencent-channel-cli 接口管理 QQ 频道，内置使用规则并注册 LLM Tools。 |
| 1425 | astrbot_plugin_gossip_sharer | 88 | other | watch | 跨会话协作工具，支持主动委派目标 QQ 群聊/私聊查证信息并回传结果、读取 OneBot 原消息、原图文件传递及原生合并记录转发。 |
| 1426 | astrbot_plugin_rice_eater | 88 | other | watch | 查看本群今日谁吃了多少大米饭，按模型调用用量生成排名卡片。 |
| 1427 | wakelite | 88 | personality | have | 在群聊中决定 Bot 要不要响应一条消息：人格名/关键词/概率/答疑/无聊/兴趣/相关性 7 个唤醒信号，含群白名单、唤醒 CD、唤醒跟随窗口、复读过滤、按群多 Bot 分流，支持唤醒后让 LLM 主动拒绝回复。 |
| 1428 | astrbot_plugin_reply_style_guard | 88 | other | watch | 针对长期群聊中的文风自我强化问题。每轮以临时上下文提醒模型不要模仿历史回复的长度、口癖和动作描写；普通闲聊若仍输出过长，可在发送前按句子/自然标点缩短。明确要求分析、教程、写作、代码等任务默认自动跳过硬截短。 |
| 1429 | astrbot_plugin_debounce | 88 | group-admin | have | 合并连续私聊图文，支持自适应等待、输入状态感知、引用消息及撤回过滤。 |
| 1430 | astrbot_plugin_open_notebook | 87 | kb-rag | have | 将 Open Notebook 接入 AstrBot，支持聊天命令和 LLM 工具管理 notebooks、上传/引用文件、查询文档内容、删除 notebook，并支持按 AstrBot provider 序号同步 Open Notebook 默认 chat 模型。 |
| 1431 | astrbot_plugin_crypto_asset | 87 | other | watch | astrbot_plugin_crypto_asset 是一个功能强大的 AstrBot 插件，专为加密货币用户设计。它不仅支持实时查询全网虚拟币价格，还具备多链钱包地址转账监控功能，让您随时随地掌握链上动态。 |
| 1432 | astrbot_plugin_nai_draw | 87 | nsfw | exclude | 叶子的逼，基于 NovelAI Diffusion 4.5，支持无预设模式、个人画师串、中文标签转换、NSFW 与自动脸型开关、图片隐写术和暗房 WebUI。 |
| 1433 | astrbot_plugin_lxdx | 87 | other | watch | 国服舞萌DX/中二节奏插件，使用落雪（lxns）接口，支持 b50、bests、曲目信息等功能。 |
| 1434 | astrbot_plugin_stock_market | 87 | game | have | 群内模拟炒股：开户、行情、买入卖出、限价挂单、新闻与走势图，每个群独立账本，行情按固定间隔自动推进。 新闻分普通 / 重要 / 重大 / 黑天鹅四档，影响单只、同板块乃至全市场，重大事件可突破单轮常规涨跌幅。 支持倍数开仓的杠杆玩法（保证金、按日计息、自动强平与欠款自动偿还）。 股价长期低于退市线的 |
| 1435 | astrbot_plugin_dongsen_voice | 87 | tts | watch | 把 Bot 的回复变成《动物森友会》风格的语音。  **不是 TTS，不是变声器**——从 407 个真人录制的普通话音节里挑出来拼的， 和动森本体用的是同一套方法。  ## 两套引擎，关一个另一个顶上  - 🗣 **动森引擎**：407 个真人音节拼的动森腔（音库 3MB） - 🐟 **哔哔啵啵引 |
| 1436 | astrbot_plugin_active_message | 87 | proactive | watch | 基于 singularity2000 的 AstrBot 主动会话插件做的优化版。新增群聊/私聊分别开关、按间隔与每日条数限制发言频率、主动发言生效范围三档可调等能力，避免同一群被重复刷屏、也便于控制 token 消耗。 |
| 1437 | astrbot_plugin_deepseek_usage | 87 | other | watch | 查看 DeepSeek 账户余额与 token 消耗，支持分时段、分会话统计和 WebUI 看板。  功能： - QQ 指令 `/usage`、`/用量`：今日余额、token、缓存命中率、估算花费、分时花费条形图 - WebUI 看板（扩展功能页）：调用趋势、近 30 天热力图、今日消耗拆分、QQ |
| 1438 | astrbot_plugin_segmented_reply | 87 | other | watch | Astrbot 原有分段回复功能的增强，增加跳过首段回复等待、省略号拆分优化、新消息加速分段等待。 |
| 1439 | astrbot_plugin_server_monitor | 87 | ssh-exec | exclude | 监控本机与远程服务器（SSH / HTTP Agent 两种接入方式）的 CPU、内存、磁盘、网络、负载等状态。页面无自绘背景（适配 wallpaper/透明美化主题），全矢量线性图标，支持聊天指令查询、阈值告警推送（含离线告警与恢复通知）。 |
| 1440 | astrbot_plugin_user_terms | 86 | other | watch | 用户条款签署控制插件，支持“全部用户 / 全部群组”一键生效或手动指定 SID，要求先同意用户条款后才允许继续使用机器人 |
| 1441 | astrbot_plugin_cliproxy_stats | 86 | other | watch | CLIProxyAPI 额度与使用统计查询插件，通过指令查看 OAuth 模型额度和当日调用统计 |
| 1442 | astrbot_plugin_redstone | 86 | other | watch | 通过调用硅基流动 API 生成地狱笑话 |
| 1443 | astrbot_plugin_regex_trigger_pro_max | 86 | sticker | borrow | 自带 WebUI 控制台！正则唤醒 + 持续唤醒 + 小模型二次判定唤醒 + 确定唤醒才贴表情，融合三个插件的 Pro Max 版本，装这一个就够。 |
| 1444 | astrbot_plugin_phoebe | 86 | sticker | borrow | 每日/今日菲比，从 Phoebe-Hub「站长推荐」随机抽取菲比表情包，支持一次多张、次数用完后重发最后一张、艾特查看他人 |
| 1445 | astrbot_plugin_emotionsense_yx | 86 | personality | have | 情绪感知插件，分析用户情绪并动态调整回复 |
| 1446 | astrbot_plugin_bot_treat | 86 | personality | have | 投喂bot：把食物照片发给 Bot 并说「投喂」，她会结合人设、时间与饱腹状态自主决定吃不吃——吃就生成一张她正在吃该食物的照片（你的照片会作为场景参考参与生成），不吃就给一句符合人设的拒绝。支持私聊 / 群聊，斜杠命令与自然语言两种触发方式。 |
| 1447 | astrbot_plugin_deepseek_search | 86 | other | watch | 使用 DeepSeek Search/Fetch API 搜索网页与读取正文，支持指令和 LLM 工具，无需浏览器。 |
| 1448 | astrbot_plugin_rvc | 86 | tts | watch | 为 AstrBot 的 TTS 增加 RVC 音色转换能力。LLM 生成文字 → TTS → RVC 转换 → 同时发送文字+语音。支持 CPU/GPU 模式，失败自动降级只发文字。 |
| 1449 | astrbot_plugin_bili | 86 | memory | have | 让大肥鱼用 B 站小号自主学习：优先读字幕、没字幕就本地转写，然后写笔记、记进长期记忆，再汇报给你。自带独立 Web 面板，看数据、翻笔记、喂视频、改设置都在一个网页里。只在后台看，不评论不弹幕不点赞陌生人，互动限额可开关。 |
| 1450 | astrbot_plugin_chatgpt_codex | 86 | other | watch | 通过 Codex Transport 或官方 Codex App Server，在 AstrBot 中使用 ChatGPT 账号可用的 Codex 模型。 |
| 1451 | astrbot_plugin_figurine_workshop | 85 | other | watch | 基于gemini生图的手办化,不再需要本地部署。 |
| 1452 | astrbot_plugin_image_summary | 85 | other | watch | [仅aiocqhttp] 图片外显插件, 将群外显示的“图片”二字替换成更丰富的句子 |
| 1453 | astrbot_plugin_llm_draw_plus | 85 | image-gen | watch | 让llm自主使用硅基流动的 SD3.5 及 flux.1 绘图 |
| 1454 | astrbot_plugin_gomoku | 85 | game | have | 五子棋双人对战 |
| 1455 | aPromptGuardian | 85 | other | watch | 开箱即用的流式提示词框架：优化→审查→过滤→复核→防护→核验→感知。维护优化系统优化提示词、屏蔽注入攻击、身份核验、信息感知、黑白名单与 WebUi 管理 |
| 1456 | astrbot_plugin_Tricy_huawei_health | 85 | other | watch | 把华为运动健康网页端的睡眠 / 静息心率 / HRV / 训练数据接进 AstrBot，支持 Cookie 注入与账号密码两种登录方式，按需抓取。 |
| 1457 | astrbot_plugin_poke_pony | 85 | platform | have | 「新.戳一戳」不是又一个戳一戳。真正自定义：台词、触发词、平台、阈值全部你说了算， 插件不预设一句台词；配置少不操心：装上只填两处（发言模板 + 拟真文案）就能用， 其余默认值已经调好。QQ 原生戳一戳双向监听与自动回戳，Telegram / 飞书 / 企业微信 / 微信个人号等无原生戳能力的平台用 |
| 1458 | astrbot_plugin_bilipinshi | 85 | media-parse | borrow | 让你的bot可以吃你搬的答辩视频回复简短评价，支持 B 站卡片转换。 |
| 1459 | astrbot_plugin_thinking_of_you | 85 | memory | have | 每隔一会儿想一想：做错的事、主人的计划、上网看到的、想念。值得才马上说，其余攒着等主人来了再说。只发给主人私聊，夜里不打扰，每天有上限、连着没回就停，都由代码执行。需要 memory-core。 The persona reaches out on its own when something is |
| 1460 | astrbot_plugin_xhs_surf | 85 | media-parse | borrow | 免登录浏览小红书公开推荐与频道内容，由自选小模型分析、主会话模型挑选并按人设主动分享文字和原链接。 |
| 1461 | astrbot_plugin_bulk_send | 85 | other | watch | 面向管理员的群发 / 广播工具箱。支持引导式对话群发、指令广播（在每个目标会话中真实执行指令）、 强大又好用的目标过滤表达式、平台风控友好的发送节奏建议，以及一个千禧年 Flash 风格的 WebUI 群发控制台。 |
| 1462 | astrbot_plugin_ipcam | 84 | other | watch | 基于AstrBot方式实现对rtsp视频流的图像截取和视频捕获。 |
| 1463 | astrbot_plugin_rss_forwarder | 84 | ssh-exec | exclude | 面向 AstrBot 的 RSS/RSSHub/Twitter 推送编排插件，支持去重、路由、日报与智能增强。 |
| 1464 | astrbot_plugin_decision | 84 | other | watch | 让 Bot 帮你做决定。 |
| 1465 | prefix_filter | 84 | other | watch | 一个用于过滤特定前缀消息的插件 |
| 1466 | mysql_logger | 84 | other | watch | MySQL存储聊天记录 |
| 1467 | astrbot_plugin_Merge_WeMSG | 84 | other | watch | [仅gewechat]支持微信个人号(gewechat)的合并消息处理和转发 |
| 1468 | blue_archive | 84 | other | watch | 蔚蓝档案攻略查询 - 指令格式：攻略查询 <攻略名称> |
| 1469 | astrbot_plugin_keyword_reply | 84 | other | watch | 自定义内容回复插件 |
| 1470 | astrbot_plugin_innerlife | 84 | memory | have | 群聊机器人拟人化框架：人设、情绪与好感、记忆、日记、日程天气新闻、主动开话题、自己画图、收藏和发送表情包、闲聊连发，以及安全底线和插话判断 |
| 1471 | astrbot_plugin_netherlink | 84 | game | have | Minecraft 服务器与 QQ 群双向消息互通,支持自然语言执行 MC 指令与游戏内机器人对话 |
| 1472 | astrbot_plugin_van | 83 | other | watch | Van幻鸢词库 |
| 1473 | astrbot_plugin_offline_notice | 83 | platform | have | 一个专门为QQ个人号平台打造的掉线检测插件，定时检测QQ账号的在线状态，离线时第一时间通过邮件通知用户，支持SnowLuma Webhook 通知。 |
| 1474 | astrbot_plugin_trpg | 83 | personality | have | 在 QQ/TG/Discord 私聊中实现类 SillyTavern 的轻量角色扮演体验 |
| 1475 | astrbot_plugin_bilibili_watch | 83 | media-parse | borrow | 把一条 B 站链接变成客观、结构化的内容报告：元数据/字幕/弹幕/评论深度清洗， 野生时间戳目录挖掘，弹幕高能波峰与梗词云提炼，字幕可信度校验， 教程攻略/二次元切片/完整游戏实况自适应门控；游戏实况额外生成底栏操作栏时间带， 按「画面可复核 / 观众提供 / 推断」三档证据还原操作轴，无字幕时按需 |
| 1476 | astrbot_plugin_danbooru | 83 | nsfw | exclude | 按 Danbooru 标签检索普通、可选 R18 或漫画图片，支持本地最低分过滤 |
| 1477 | astrbot_plugin_ai_gen | 83 | other | watch | 调用 GPT 等文本模型与生图模型，支持 OpenAI 官方接口与中转站（OpenAI 兼容接口）。适用于 QQ OneBot (aiocqhttp)、QQ 官方等所有 AstrBot 消息平台。 |
| 1478 | astrbot_plugin_iconic_quotes | 83 | sticker | borrow | 可收录群友的文字、图片、QQ 表情、商城表情、回复关系和合并转发，并通过随机群典或个人“爆典”合集重新发送。 |
| 1479 | astrbot_plugin_ai_guard | 83 | other | watch | 对话 AI 在被辱骂/阴阳怪气时主动调用函数工具（ai_guard_report）上报，守卫校验攻击强度后带聊天记录合并转发到管理群；辱骂/注入词库命中由守卫兜底判断。 支持攻击对象判定（骂群友不算）、注入检测、跳过对话、屏蔽（临时/永久黑名单）、删好友、两档敏感度滑杆。 |
| 1480 | astrbot_plugin_pixiv_search | 83 | other | watch | 从 Pixiv 每日插画榜获取单图，或按标签发送热门度靠前的五张单页原图，不需要登录或 Cookie |
| 1481 | astrbot_plugin_gamdl | 82 | memory | have | astrbot_plugin_gamdl 是一个面向 AstrBot 的 Apple Music 插件，基于 gamdl 实现搜索、解析、下载、封面、动态封面、歌词导出等能力。它专为 QQ NapCat（OneBot/aiocqhttp）优化，支持后台任务队列、会话级设置记忆、ZIP/逐个发送、下载 |
| 1482 | astrbot_plugin_listen_github | 82 | info-push | have | 通过 RSS 定时获取 GitHub 用户/仓库动态并推送到聊天会话 |
| 1483 | astrbot_mcmod_card | 82 | media-parse | borrow | MC 百科卡片解析 |
| 1484 | astrbot_plugin_dynamic_persona | 82 | personality | have | 在每次交互前为你的 Bot 动态生成一个全新的、临时的性格，让你的 Bot 充满惊喜和生命力。 |
| 1485 | astrbot_plugin_qyws | 82 | tts | watch | 随机播放文件夹里千原万神小丛雨的语音插件 |
| 1486 | AstrBot_0721anime | 82 | other | watch | 在群里输入【/查番 动漫名称】即可查询内置动漫网站相对应的动漫名和链接 |
| 1487 | astrbot_plugin_anidaily | 82 | other | watch | 🌸 **每日定时推送今日番剧更新。** 🎨 **4K 级超清深色海报卡片。** 🚀 **支持 /anidaily now 即时查看。** |
| 1488 | astrbot_plugin_dot_trigger | 82 | other | watch | 消息中包含用户设定的触发词时自动唤醒并触发LLM回复，无需艾特或特定前缀 |
| 1489 | astrbot_plugin_lively_bond | 82 | personality | have | 情感系統：熟悉度、好感、心情、印象；每晚從記憶裡回味和每個人的片段，算出各種感情、整理「心裡的 TA」、記下態度；群友要「印象卡」時發一張印象卡圖片 |
| 1490 | astrbot_plugin_rconsole | 82 | media-parse | borrow | 自动识别聊天中的分享链接并解析出媒体内容。移植自 Yunzai-Bot 插件 rconsole-plugin（作者 zhiyu1998），覆盖抖音、B站、快手、微博、AcFun、小红书、 米游社、小黑盒、微视、网易云／QQ音乐／酷狗等平台，并保留原版的第三方接口轮换、 失败降级、AI 链接总结与翻译 |
| 1491 | astrbot_plugin_kb_search_tool | 82 | kb-rag | have | 让内置工具 astr_kb_search 常驻每次 LLM 请求；不改 kb_agentic_mode，因此知识库自动注入照常工作。 |
| 1492 | astrbot_plugin_baiduocr | 81 | other | watch | 百度智能云的 OCR 文字识别服务。新用户有千次的免费调用次数，适合轻度使用 |
| 1493 | astrbot_plugin_react_menu | 81 | sticker | borrow | 提供一个能集中管理框架中所有指令（aiocqhttp）的互动菜单，通过仿造官方机器人MarkDown按钮触发的形式，和可配置的指令列表，在发送关键词后生成一个贴有emoji表情的互动菜单，点击emoji即可触发配置的对应指令（模仿点击者来触发指令，支持大部分需要个人身份触发的情景）；支持使用仓库中的 |
| 1494 | astrbot_plugin_shim_connector | 81 | info-push | have | 白嫖机器人：把你已经付过钱的 AI 订阅（WorkBuddy / Trae / Qoder）直接变成 AstrBot 的模型源。  这些客户端不提供 API Key，所以以前用机器人还得再付一次 API 费用。本插件在本机起 loopback shim， 把已有订阅额度翻译成 OpenAI 兼容端点 |
| 1495 | astrbot_plugin_picmcmotd | 81 | other | watch | 查询 Minecraft 服务器 MOTD 和在线状态，并绘图输出信息，支持查询 Java 版和基岩版服务器。 |
| 1496 | astrbot_plugin_mnemoria | 81 | memory | have | 长期记忆系统：对话流水账本 + 记忆抽取与衰减 + 用户画像 + 混合检索注入 |
| 1497 | astrbot_plugin_checkin | 81 | group-stats | borrow | 每日签到插件。签到攒积分、暴击彩蛋、连签成长、每日出海肉鸽、海图宝箱、运势塔罗、红包商店、多维排行榜、签到提醒与日报，并支持 LLM 签到评语和档案联动。数据持久化存储，核心功能无需外部 API。 |
| 1498 | astrbot_plugin_memory_core | 81 | memory | have | 让角色拥有跟着它走的长期记忆（基于 memory-core 库）：每句话记成经历，定时整理成带来源的记忆；按群、私聊分可见范围； 每天写日记、更新自我认知；记忆会淡忘、合并，主人可以彻底遗忘；能看图；知道自己现在会什么。后台有记忆面板。 Local-first long-term memory fo |
| 1499 | astrbot_plugin_orangevibe | 80 | other | watch | 互动式成分鉴定插件，答题可生成AI专属锐评的海报，支持LLM辅助生成测试方案，分享结果至群聊还能探测同成分群友。 |
| 1500 | astrbot_plugin_r6states | 80 | game | have | 查询彩虹六号的玩家战绩、游戏百科和电竞信息，nonebot-plugin-R6States的astrbot移植版 |
| 1501 | astrbot_plugin_code_renderer | 80 | other | watch | 将代码信息或者代码文件渲染为带有语法高亮的图片 |
| 1502 | astrbot_checkin_plugin | 80 | game | have | 简单文字签到插件 |
| 1503 | astrbot_plugin_image_search | 80 | other | watch | 支持 SauceNAO、Google Lens、Ascii2d、trace.moe 和 Soutubot，支持自然语言使用。 |
| 1504 | astrbot_plugin_proactive | 80 | proactive | watch | 补上框架里缺的那条链路：用户安静够久时，让 bot 自己发一条消息过来。  人设里写了「等得够久了会自己发一条过去」，但代码里没有这条路径， 模型只能在对话里编自己发过。这个插件把这件事落实，顺便少一个幻觉来源。  **触发条件**（全部满足才发）： - 用户空闲达到设定小时数 - 距上一条主动消息 |
| 1505 | astrbot_plugin_bangumi_calendar | 80 | platform | have | 每日新番放送日历，定时推送卡片图至群聊 |
| 1506 | astrbot_plugin_group_forwarder_special | 80 | tts | watch | 跨群消息转发·特殊版：包含原版全部发送能力（文字/图片/语音/文件/合并转发/私聊），并联动群聊日志归档插件实现跨对话查看历史消息 |
| 1507 | astrbot_plugin_livepulse | 79 | media-parse | borrow | Multi-platform live stream monitor for YouTube, Twitch, and Bilibili. |
| 1508 | Codex | 79 | devtools | watch | AstrBot_Codex 是一个基于 Docker 的 Linux 命令执行插件，专为 AstrBot 开发，能够安全地在隔离的 Docker 容器中执行多种编程语言的代码并返回结果。 |
| 1509 | astrbot_plugin_majsoul | 79 | game | have | 一个雀魂多功能插件 |
| 1510 | astrbot_plugin_bili_duty | 79 | group-stats | borrow | 用 bili-cli 引擎做 B 站值班：日报、单条速览、热门榜、常驻回复（有人 @ 我或回我就回一句）、状态自检，并自带 HTTP/WebSocket API 端口。 |
| 1511 | bilicaption | 79 | media-parse | borrow | 提供获取B站视频字幕文本、解读视频内容的 LLM 工具，自动识别消息中的 B 站链接/BV 号/b23 短链 |
| 1512 | astrbot_plugin_cross_group_forwarder | 79 | other | watch | 给 LLM 提供跨群发送消息的工具，使其可以在一个聊天中向其他 QQ 群（按群号）发送文字/图片 |
| 1513 | astrbot_plugin_meirixinwen | 79 | media-parse | borrow | 发送"每日新闻"关键词，自动联网获取百度/抖音/B站/微博/贴吧热搜Top20，支持文字/图片，各来源独立开关 |
| 1514 | astrbot_plugin_napcat_monitor | 79 | other | watch | NapCat（OneBot v11）断线监控与自动重连插件。  功能： 1. 定时检测 aiocqhttp 适配器与 NapCat 之间的反向 WebSocket 连接状态； 2. 断线时自动记录日志，并可向指定 QQ 群/用户发送通知； 3. 适配器异常时自动重启适配器完成重连，等待 NapCat |
| 1515 | astrbot_plugin_pixiv_plus | 79 | other | watch | Pixiv 图片搜索增强插件，支持标签搜索、随机图片、按 ID 获取、每日一图定时推送。自动识别 R-18 标签：R-18 作品仅发送链接（i.pixiv.re），非 R-18 作品通过 i.yuki.sh 加速下载并发送。 |
| 1516 | astrbot_plugin_chatgpt_vision | 79 | other | watch | 官方 Sign in with ChatGPT 授权的图片描述、截图理解与 OCR；独立于生图和原有图片转述 |
| 1517 | astrbot_plugin_heybox_reader | 79 | game | have | 让你的 AI 机器人看懂小黑盒帖子，阅读正文、配图和评论，还能按游戏主题找帖子。 |
| 1518 | astrbot_plugin_essentials | 78 | other | watch | 一款集成权限、经济、安全、管理功能的 AstrBot 基础插件。 |
| 1519 | astrobot_plugin_who_at_me | 78 | other | watch | 谁艾特我?监听 @ 消息，便于快速查找自己被 @ 时说了什么。 |
| 1520 | astrbot_plugin_pet | 78 | game | have | 一个简单的的群内宠物养成插件，支持LLM随机事件、PVP对决和图片状态卡。 |
| 1521 | astrbot_plugin_txsc | 78 | image-gen | watch | 基于阿里云百炼通义万相-文生图的插件 |
| 1522 | astrbot_plugin_msg_stat | 78 | group-stats | borrow | 统计 AI 在群聊/私聊中的发言次数与 Token 用量（与 AstrBot 系统统计同源），支持合并转发、全局报表、按天明细和每日午夜报告 |
| 1523 | astrbot_plugin_my_waifu | 78 | game | have | 个人后宫养成：/抽老婆 抽一位只属于自己的神秘老婆，/老婆猜 猜名字拿线索对比，猜对可迎娶进后宫，含签到、积分、扩容、请回等养成玩法。数据来自Bangumi（bgm.tv）。 |
| 1524 | tts_voice | 78 | tts | watch | 注册 speak_voice 工具, bot 可任意调用, 把文本转成语音消息发送; 兼容 dashscope_tts(CosyVoice / Qwen-TTS), 也可复用 AstrBot 已配置的 TTS provider。 |
| 1525 | astrbot_plugin_cucumber_parser | 78 | media-parse | borrow | 自动识别抖音、B 站、小红书、贴吧、微博、微信、小黑盒、知乎链接并解析发送 |
| 1526 | astrbot_plugin_tot_memory | 78 | memory | have | 为 AstrBot 提供 LLM 思维树（Tree of Thoughts）深度推理、长期记忆库与角色言行决策模型。思维树支持多分支思路生成、评估打分、最佳优先扩展；记忆库基于 SQLite 持久化并自动检索注入，支持本地 JSON 导出/导入；决策模型实现「35% 历史保底 + 65% 当前镜像  |
| 1527 | astrbot_plugin_openlist_bot | 77 | other | watch | OpenList 文件管理助手，支持浏览、搜索、上传、下载、预览、群聊/私聊文件与 QQ 闪传备份转存及恢复。 |
| 1528 | astrbot_plugin_count_loc | 77 | other | watch | 一个可以分析 GitHub/GitLab 公开仓库代码行数、文件数和注释行数的 AstrBot 插件喵。支持多分支选择、自定义忽略项过滤和 LLM 函数工具调用喵！ |
| 1529 | astrbot_plugin_wwuid_reply_enhance | 77 | other | watch | 基于astrbot的wwuid的回复增强。 |
| 1530 | terminal | 77 | other | watch | 通过和AstrBot对话调用服务器终端 |
| 1531 | astrbot_plugin_group_information | 77 | other | watch | [仅 aiocqhttp] 导出QQ群成员信息为Excel表格 |
| 1532 | astrbot_plugin_appreview | 77 | group-admin | have | 这是一个可以通过关键词来同意或拒绝进入群聊的插件。 |
| 1533 | astrbot_plugin_BitTorrent_withLLMTool | 77 | other | watch | 适配AstrBot的磁力搜索插件（社区修改版），支持 LLM 自然语言调用、截图预览、合并转发、跨平台图片缩放，适配 clg02.cc 站点 |
| 1534 | astrbot_plugin_plugin_shop | 77 | other | watch | 让 AstrBot 的机器人自己逛插件市场：搜索、安装、启用、停用、卸载插件。全部能力以 LLM 工具的形式暴露，用户直接说需求即可，安装和变更操作默认需要用户确认。 |
| 1535 | astrbot_plugin_codebuddy | 77 | other | watch | 把腾讯 CodeBuddy（中国版）的模型接入 AstrBot，作为机器人的对话模型使用。  **功能特性**  - 逆向 CodeBuddy 官方客户端的私有协议，登录你自己的 CodeBuddy / 腾讯云账号即可使用，无需自行申请 API Key； - 插件在 AstrBot 进程内启动一个本 |
| 1536 | astrbot_plugin_context_manager | 77 | memory | have | 手动管理固定记忆、AI 摘要和 Token 预算的上下文管理器 |
| 1537 | astrbot_plugin_dafeiyu_merge | 77 | other | watch | 私聊连发消息合并成一条再回复（滑动等待窗，每条新消息重置倒计时），指令豁免直通；合并轮附"简短回应"提示治连发刷屏；私聊分段回复（按句切分逐条发、条间隔按打字时间拟人）——补齐框架分段对私聊默认路径不生效的缺口。群聊完全不受影响。 |
| 1538 | astrbot_plugin_pacer | 76 | other | watch | 接管 AstrBot 的分段发送。用户中途插话时，立刻停掉剩余分段，而不是把旧内容一条条发完。  **还做了一件事**：被打断之后，把历史里那条 assistant 消息改写成「实际发出去的部分」， 避免 bot 记住自己说过、用户却没看到的内容。  **安全阀**：出异常且一段都还没发出去时，把消 |
| 1539 | astrbot_plugin_today_wife | 76 | other | watch | 完整匹配“今日老婆”或“今日老婆 n个”（忽略任意空格），从 manshuo 今日老婆图片接口获取图片；多图通过 OneBot v11 合并转发发送。 |
| 1540 | menu_navigation | 76 | platform | have | 发送“菜单”即可查看已安装插件的聚合菜单。 约定：插件根目录放置 menu.md（或 metadata.yaml 声明 menu 字段）， 内容会提取为菜单指令摘要并在触发时生成图片；无需修改各插件代码。 可在 WebUI 中选择参与聚合的插件。 支持 QQ 官方（qq_official / qq_ |
| 1541 | astrbot_plugin_parser_lite | 76 | media-parse | borrow | 自动解析 B 站/抖音/小红书等平台分享链接与 JSON 卡片并转发为内容卡片；nonebot-plugin-parser-lite 的 AstrBot 桥接版 |
| 1542 | astrbot_plugin_fatfish_promise | 76 | proactive | watch | 机器人答应「明天提醒你」就到点去做，说「我去睡了」就不冒泡，用它自己的口吻。细节和配置见 README。 |
| 1543 | astrbot_plugin_slang | 76 | other | watch | 群黑话自动学习与注入：LLM 提取 + 模型自审 + 待审复核，按群隔离，SQLite 持久化 |
| 1544 | astrbot_plugin_bili_reader | 76 | media-parse | borrow | 把 B站视频发给 AI 机器人，读取视频简介、可用字幕和热门评论，还能按关键词找视频。 |
| 1545 | astrbot_plugin_wechat_agent | 76 | group-admin | have | 通过 [agent-wechat](https://github.com/thisnick/agent-wechat) 守护进程把个人微信接入 AstrBot，附一键安装脚本。 群聊像真人：偶尔引用对方、撤回了就不回、先发图再 @ 也看得懂；能接微信语音电话（豆包端到端实时语音，可打断）；群里 /总 |
| 1546 | astrbot_plugin_media_wiki | 75 | other | watch | MediaWiki 通用查询插件，支持查询任何 MediaWiki 站点内容。 |
| 1547 | astrbot_plugin_ronghedraw | 75 | image-gen | watch | RongheDraw 多模式绘图插件 - 支持 Flow/Generic/Gemini 三种 API 模式 |
| 1548 | astrbot_plugin_flux | 75 | image-gen | watch | 硅基流动文生图-支持OpenAI标准的格式接入，支持Flux.1-dev模型 |
| 1549 | astrbot_plugin_yuanbao_search | 75 | other | watch | 为 AstrBot 提供每月 2000次 的免费腾讯生态实时联网检索能力。支持网页信源、优质权威垂直信源、混合结果，并可按站点、垂直领域与时间范围精细过滤，可以让 Bot 在回答中获取实时外部信息。 |
| 1550 | astrbot_plugin_qqofficial_buttons | 75 | other | watch | 提供独立可视化的按钮菜单编辑器，并把菜单包装成 LLM 工具实现自然语言调用。 |
| 1551 | astrbot_plugin_dsh_tool | 75 | other | watch | 给 AstrBot 的日常对话加一个 LLM 工具 dsh_task。普通聊天时，模型可以自己判断 是否需要把「写代码 / 执行命令 / 读写服务器文件 / 跑长任务」交给本机的 DeepSeek Harness (DSH) 执行，并把结果拿回来继续回答。  提供隐式工具和独立 /dsh 命令入口； |
| 1552 | astrbot_plugin_stock_robot | 75 | other | watch | 在聊天中获取 A 股、港股、美股个股研报、A 股及港股指数研报，或黄金简报。可在插件配置中开启额外分析，个股另获得五维评分、行业同期对比、规则信号与 AI 解读，指数获得规则判断与 AI 解读。美股支持已核实的 TTM 同行经营比较，额外分析开启后提供有效维度评分与 AI 解读；财务、技术、估值和行 |
| 1553 | astrbot_plugin_image_judge | 75 | group-admin | have | 群友发图片（或回复图片并发“打分”、@某人锐评头像），机器人调用 AstrBot 已配置的多模态模型对图片打分并锐评吐槽，纯娱乐。可选渲染成评分卡片图，支持群管理指令调自动鉴图、本群鉴图排行榜与个人战绩，带重复图缓存、每小时上限与免打扰时段。 |
| 1554 | astrbot_plugin_persona_evolve | 75 | memory | have | 让机器人自己维护自己的人格：按设定的周期，读取当前会话与长期记忆， 在保持角色连续性的前提下重写「当前正在使用」的那一份人格设定。 每份在用的人格按各自会话的上下文单独迭代，其余人格原样不动； 改写结果有字数上限，改动前自动备份，并带一个面板可以查看、编辑、应用、删除历史版本。 长期记忆取材依赖 L |
| 1555 | astrbot_plugin_qq_aivoice_bridge | 75 | tts | watch | 调用 NapCat/OneBot 的 QQ AI 声聊生成语音，并将 SILK、WAV、MP3 发送到当前平台。 |
| 1556 | astrbot_plugin_emby | 74 | other | watch | 关联自部署 Emby 媒体库。支持 LLM 自动检索影片、获取元数据及最近更新。 |
| 1557 | astrbot-timetask | 74 | other | watch | 这是timetask插件，支持定时消息，可以指定微信群(暂时只支持WechatPadPro渠道) |
| 1558 | r1-filter | 74 | other | watch | 过滤 DeepSeek R1 推理模型的思维链内容 [版本要求 >= v3.4.17] |
| 1559 | astrbot_plugin_tagger | 74 | image-gen | watch | 识别图片并生成AI绘画tag标签 |
| 1560 | astrbot_plugin_group_log_archive | 74 | other | watch | 定时将 AstrBot 日志中的群聊记录导出为按天归档的纯文本文件，只保留聊天内容，节省空间与上下文。 |
| 1561 | schedule_assistant | 74 | proactive | watch | 你的贴心日程管家，支持早安播报、习惯提醒、LLM 智能日程管理、Apple 日历双向同步、Notion 待办同步 |
| 1562 | astrbot_plugin_ehentai_metadata | 74 | media-parse | borrow | 自动解析本子链接发送卡片 |
| 1563 | astrbot_plugin_group_manager | 74 | group-admin | have | 群管综合工具，关键词违禁消息拦截撤回、分层违规警告、自动禁言/踢出、多模式定时消息推送 |
| 1564 | astrbot_plugin_deepsea_soul | 74 | personality | have | 七情六欲 + 念头流 + 心跳：把她的内在状态带进对话，让情绪会衰减、欲望会积累。不额外调用模型，只维护状态并注入一段约 200 字的提示。 |
| 1565 | astrbot_plugin_environment_awareness | 74 | platform | have | 凝心溯溪系列环境模块：按需获取日历、天气、空气质量、官方预警与自然事件 |
| 1566 | astrbot_plugin_qq_login_watch | 74 | ssh-exec | exclude | 监控 SnowLuma 的 QQ 登录状态，掉线时通过 PushPlus 微信或 QQ 邮箱提醒，并附 noVNC 实时截图，方便重新扫码登录。 |
| 1567 | astrbot_plugin_pairit | 73 | game | have | 自动匹配群友发送的括号，这下括号再也不会出现不成对的情况了 |
| 1568 | astrbot_plugin_opencode_client | 73 | other | watch | 用于连接到 Opencode 服务器 https://opencode.ai/docs/server/ |
| 1569 | astrbot_plugin_matrix_sticker | 73 | sticker | borrow | Matrix Sticker 管理插件，提供 sticker 保存、列表和发送命令 |
| 1570 | astrbot_plugin_teamup | 73 | other | watch | 组队报名与随机分队插件。 |
| 1571 | astrbot_plugin_csstats | 73 | other | watch | 这是一个能查询 CS 战绩（仅支持 5e 平台）的插件，并让大模型评价评价你打得怎么样 |
| 1572 | asbot_plugin_furry_mzxyy | 73 | other | watch | 毛主席一言 |
| 1573 | hotlist | 73 | info-push | have | 获取 B 站热门视频榜单、百度热搜、EPIC 热门榜单 |
| 1574 | astrbot_plugin_active_learner | 73 | memory | have | 凝心溯溪系列知识模块：知识学习、检索与验证，支持自动上下文注入、多源学习、统一记忆池与版本管理 |
| 1575 | astrbot_plugin_duplex_call | 73 | tts | watch | # Duplex Call —— AstrBot 网页语音通话插件  将 `web_duplex_demo`（火山引擎端到端实时语音-全双工 Web demo）适配为 AstrBot 插件：  - **意图驱动**：用户说「我想打电话 / 打电话给XX」时，主智能体通过 `duplex_call`  |
| 1576 | astrbot_plugin_burst | 73 | tts | watch | 把用户连着发的几条消息攒起来，合成一条带时间戳的大消息再送进流水线。  **触发规则**（谁先满足谁赢）： - 静默：距最后一条满 N 秒（默认 20 秒） - 长消息：单条去空白后达到 N 字（默认 25 字）立刻放行  指令（以 / 开头）和语音/文件/引用这类结构性消息不参与聚合，直接放行。  |
| 1577 | astrbot_plugin_vision_memory | 73 | memory | have | 面向 AstrBot 的多模态视觉识图与图片记忆管理插件。私聊收到图片，或群聊当前消息真实 @Bot 并带图/引用含图消息时启动识图；识别结果临时注入当前 LLM 上下文，但不强迫 Bot 在最终回复中讨论图片。  内置预设库（魔裁）、人工视觉添加库和 Bot图片库。三个库均支持逐张参考图视觉特征、 |
| 1578 | astrbot_plugin_qq_nickname | 73 | other | watch | 补全 QQ 官方消息的发送者 ID 和昵称，保留原始 OpenID，支持后台资料管理。 |
| 1579 | astrbot_plugin_cs_vrs_report | 73 | devtools | watch | 完美世界优先的 CS2 赛果分析、选手 Rating/K-D、历史交锋胜率与 VRS 全球前15排名，支持 AI 点评及群聊自动播报。 |
| 1580 | astrbot_plugin_member_blacklist | 73 | other | watch | 禁止指定 QQ 号触发 AI（拦截其全部消息），并提供内嵌于 AstrBot 管理面板的 黑名单管理页面，支持黑名单的添加 / 移除 / 清空，以及自定义拦截提示语。 |
| 1581 | astrbot_plugin_proactive_care | 73 | sticker | borrow | AI 自主决定下一次唤醒时间，支持离开线索回访、深夜保护、连续未回复上限与随机鸣潮表情 |
| 1582 | astrbot_plugin_gbif_search | 72 | other | watch | 一个基于 GBIF API 的 AstrBot 插件，支持物种分类信息查询和 occurrence（出现记录）搜索。支持关键词模糊匹配，命令缩写，可返回文本或图片。 |
| 1583 | AstrBot_plugin_MaimaiDX | 72 | other | watch | A maimaidx helper for Astrbot. |
| 1584 | astrbot_plugin_msg_search | 72 | other | watch | [仅aiocqhttp]搜消息插件，比如搜索 谁at我 |
| 1585 | astrbot_plugin_bangumi | 72 | other | watch | 一个用于查询 Bangumi条目的插件 |
| 1586 | astrbot_plugin_silent | 72 | other | watch | 一个极其简单的静默插件，当LLM回复内容中包含 silent 关键词时，自动阻止发送回复消息。 |
| 1587 | zlibrary_assistant | 72 | other | watch | 为 AstrBot 提供 Z-Library 图书搜索与下载能力（账号池、HTML 卡片结果、额度管控） |
| 1588 | astrbot_plugin_ccb_super | 72 | group-stats | borrow | 基于灵煞/ccb 改进的 AstrBot 群娱乐插件增强版。  支持绝顶冷却、连击演出、暴击翻倍、养胃限流、挣脱机制、白名单、 成就系统（7个成就），以及次数/注入量/绝顶/max 多维排行榜、 本群统计报告与跨群全局统计报告（图片）、今日日报（含海王/小南梁）等功能。  数据长期化存储于 data |
| 1589 | astrbot_plugin_qzone_reader | 72 | media-parse | borrow | 当你把 QQ空间说说以小程序卡片/分享链接的形式转发给 bot 时，插件会用 NapCat 的登录态拉取该条说说的完整内容（正文、图片、作者、时间）， 把内容注入本轮对话，于是 bot 可以自动总结，并且该内容会随消息一起进入会话历史，之后可以继续追问讨论。 |
| 1590 | astrbot_plugin_live2d_pet | 72 | tts | watch | Windows Live2D 桌宠插件，提供 AstrBot 消息驱动、原生 STT/TTS 和 WebSocket 实时通信。 |
| 1591 | astrbot_plugin_wordle_beta | 72 | game | have | Wordle 猜单词游戏，支持群聊多人同猜。可自定义单词长度和词典，提供图片化棋盘和提示。 |
| 1592 | astrbot_plugin_qq_group_sign | 72 | game | have | 每天在指定时间（北京时间）为白名单内的QQ群执行群打卡，支持当前群手动签到、失败重试和结果查询。 |
| 1593 | Aftermath | 72 | proactive | watch | 当你打完游戏或做完某个大项目(或更多情景)时，bot会发送符合你设置的人设的句子并回应你！监控CPU/GPU/自定义进程占用和屏幕变化，当占用超过阈值且屏幕有明显变化时截图，占用下降后通过模型生成复盘并主动发送到指定会话。 |
| 1594 | astrbot_plugin_keenable | 72 | other | watch | 通过 Keenable 为 AstrBot 提供联网搜索（keenable_web_search）和网页正文读取（keenable_fetch_page）两个 LLM Tool，以及 /keenable 指令。开箱即用，无需注册或 API Key（按 IP 限流）；填写免费 API Key 可提高额 |
| 1595 | astrbot_plugin_hs_rank | 71 | game | have | 炉石传说国服战棋排行榜查询插件，支持双打/单打排行、涨跌榜、排名区间、自动记录和后台配置。 |
| 1596 | astrbot_plugin_actions | 71 | other | watch | 根据自定义前缀或正则匹配指令，触发无上下文单次对话，可用于生图、嵌字翻译等场景。本项目是对旧版 Chatluna 快捷指令 (chatluna-actions) 在 Astrobot 内的复刻版本 (?) |
| 1597 | astrbot_plugin_provider_ark_ResponsesAPI | 71 | other | watch | 将火山方舟(Volcengine Ark)的上下文缓存API(Responses API)注册为 AstrBot 的对话服务提供商(Provider)(支持/provider、缓存命中统计、Function Calling) |
| 1598 | solve_longmsg | 71 | group-admin | have | 撤回并合并转发群员或者机器人的长消息 |
| 1599 | astrbot_plugin_doubao_draw | 71 | ssh-exec | exclude | 用你自己的豆包账号在网页端生图：SSE 实时抓原图，/draw 出图，支持比例与参考图，只回图片；内置调试（Linux 走 VNC，Windows 直接打开可见 Chrome）。 |
| 1600 | powertoy | 71 | other | watch | 读取本地状态文件，实时影响 AI 回复语气。支持指令控制：塞入、调档、拿出。 |
| 1601 | astrbot_plugin_music_sense | 71 | personality | have | 让 Bot 听懂音乐，通过 Gemini 原生多模态音频理解，分析群里分享的音频文件的情感、氛围与风格，并将结果注入对话上下文。 |
| 1602 | astrbot_plugin_rice_bowl | 71 | personality | have | 主人说起大白饭、吃饭、充 token 时，角色可以用 rice_check 看自己的 DeepSeek 余额、今天和最近几天吃了多少、平均每天多少、还能吃几天、上次什么时候充的。每隔几小时记一次余额算出趋势；快吃完时，在主人私聊里每天提醒她一次。只在主人私聊里能看。 The persona can  |
| 1603 | astrbot_plugin_sheng_qi_le_ma | 71 | personality | have | 角色扮演情绪系统。支持LLM自主判断用户是否惹自己生气，惹生气后静默不回复。支持“时间冷静”与“消息条数冷静”两种模式，达到条件后将静默期间消息打包发给原始LLM顺其自然恢复对话。 |
| 1604 | astrbot_plugin_jev_gate | 71 | other | watch | 把群消息交给 TypeSafe Jev 模型打分， 按阈值判断"值得接话"的消息，再在 AstrBot 管线内触发一次主动回复。 |
| 1605 | astrbot_plugin_daily_album | 70 | other | watch | 每日专辑推荐 - 定时向指定会话推送一张专辑推荐，支持 LLM、联网搜索、自定义脚本三种来源 |
| 1606 | astrbot_plugin_animatedemoji | 70 | other | watch | 将静态 emoji 转换为动态 emoji，支持 Google Noto 和 Telegram 两种动态方案。 |
| 1607 | astrbot_plugin_steammod_monitor | 70 | game | have | 用于监控steam的创意工坊和mod状态变更，并在状态变化时推送通知。硬核游戏服主（僵尸毁灭工程、方舟、Rust等）打造的“赛博网监”级 AstrBot 插件。 彻底告别“玩家进不去服务器才发现模组更新”的窘境，实现全自动更新预警与优雅的群组推送和管理！ |
| 1608 | halo_manager | 70 | other | watch | Bot管理的halo博客插件 |
| 1609 | astrbot_plugin_ zxs60s | 70 | info-push | have | 基于走小散远程API接口开发的直接显示晨报图的一款插件。 |
| 1610 | astrbot_plugin_cryptocurrency | 70 | other | watch | 加密货币模拟交易插件具备实时价格、市场数据和AI投资模拟功能 |
| 1611 | astrbot_plugin_chat_queue | 70 | other | watch | 让并发消息按照队列依次执行 |
| 1612 | astrbot_plugin_free_will | 70 | proactive | watch | 常驻自由意志调度：睡眠/午休、行程记录（默认保存在插件数据目录）、养猫、主动找主人分享、聊天上下文注入与可视化看板 |
| 1613 | astrbot_plugin_reverie_memorial | 70 | memory | have | 为LLM注入长期记忆：智能昵称识别、高度自定义的记忆管理、双路由(文档+图谱)混合检索召回、半衰期遗忘模型与Agent工具调用。 |
| 1614 | astrbot_plugin_msg_aggregator | 70 | group-admin | have | AstrBot 的每条平台消息独立走完整条管线。用户把一句话拆成几条发送时，会产生重复的 LLM 调用和割裂的上下文。  本插件拦截消息、短暂缓冲、再重构为一个事件交给下游，因此： - 3 条消息只触发 1 次处理（私聊与群聊都支持） - 群聊按「会话 + 发送者」分桶，不会把 A 的话并进 B 的 |
| 1615 | astrbot_plugin_minecraft_monitor_plus | 70 | other | watch | Minecraft服务器监控插件，支持为每个群独立配置服务器监控。通过WebUI管理每群配置，定时检测服务器状态变化并通过机器人发送通知。 |
| 1616 | image_generator | 70 | other | watch | 复用 AstrBot 模型提供商或手动配置图片 API，通过命令或 LLM 工具生成图片。 |
| 1617 | astrbot_plugin_balance_board | 70 | other | watch | 自动读取 AstrBot 模型供应商的 API Key，查询所有已配置平台的余额并渲染成图片。 |
| 1618 | astrbot_plugin_osu_downloader | 69 | other | watch | 自动识别 osu! 谱面链接，从 osu.sayobot , osu.direct 或 catboy.best 镜像站下载 .osz 文件并发送到群聊。 |
| 1619 | astrbot_plugin_rss_tool | 69 | info-push | have | 让你的 AstrBot 可以自主获取、筛选 Atom/RSS 等 Feed 信息。 |
| 1620 | astrbot_plugin_exchangerate_icbc | 69 | other | watch | 获取工商银行实时汇率数据，实现实时查询、汇率监控及自定义配置频率功能。 |
| 1621 | astrbot_plugin_Astrsupermarket | 69 | other | watch | 一款专为 AstrBot 打造的高互动性 QQ 群聊插件，融合经济、社交、冒险等玩法 |
| 1622 | astrbot_plugin_drift_bottle | 69 | other | watch | 一起来扔漂流瓶吧！一个简单的漂流瓶插件，支持发送和捡起漂流瓶，可以包含文字和图片 |
| 1623 | astrbot_plugin_arknights_dle | 69 | game | have | 基于 AstrBot 框架开发的明日方舟干员竞猜小游戏 (Arknights Wordle/Loldle)。 通过极致的“罗德岛战术终端”风格图片渲染，为你和群友提供沉浸式的硬核数据推理体验。 支持自定义背景底图、隐藏指定列、自动抓取头像、智能防连抽发牌等高级特性。 |
| 1624 | astrbot_plugin_search_anime | 69 | other | watch | 基于 trace.moe 和 sauce.moe API 的以图搜番/搜插画插件，支持标准 LLM 工具及指令调用。 |
| 1625 | astrbot_plugin_text2img | 69 | image-gen | watch | 自定义 URL 与 Key 的文生图全家桶：OpenAI兼容/SD WebUI/自定义模板/异步轮询，内置意图理解润色、角色特征库、参考图垫图、自然语言触发与每人每日限额 |
| 1626 | astrbot_plugin_chishenme | 69 | other | watch | 群聊随机推荐吃什么；点菜KFC直接出菜；100 道菜图文回复；按菜系分类可筛选；菜品可增删换图；自带面板 |
| 1627 | astrbot_plugin_twin_diary | 69 | memory | have | 每天在指定时间让 AI 用当前人设写两篇日记：一篇给主人看，一篇只留在本机的私密日记；自动读取聊天记录、长期记忆与历史日记。 |
| 1628 | astrbot_plugin_163music | 69 | tts | watch | 网易云音乐点歌插件 |
| 1629 | astrbot_plugin_zhipu_draw | 69 | image-gen | watch | 接入智谱开放平台的 CogView-3-Flash 免费绘图模型。支持手动 /画图 指令，也注册了 generate_image 工具，让 Bot 在聊天里自己判断什么时候该画一张图。内置并发限制、冷却时间、错误码提示和旧图清理，支持用 AstrBot 里已配置的对话模型自动润色提示词（可关、可选模 |
| 1630 | astrbot_plugin_phi | 69 | other | watch | 一个简单的Phigros B30查询插件。 |
| 1631 | astrbot_plugin_tip_feed | 69 | payment | exclude | 监听所有消息，只要包含自定义关键词即触发（默认“投喂”）并自动发送收款码图片 |
| 1632 | astrbot_plugin_one_command | 69 | other | watch | 可配置一个指令，并发送文本、图片或文本加图片。 |
| 1633 | astrbot_plugin_server_status_nickname | 68 | other | watch | 通过群昵称动态显示服务器状态的插件，并提供状态历史图生成 |
| 1634 | yandere_github_stalker | 68 | other | watch | 监控 GitHub 用户活动，采用病娇风格，并通过图片或文本的形式发送通知。 |
| 1635 | astrbot_plugin_for_sd_webui | 68 | image-gen | watch | 使用/draw调用本地（127.0.0.1）的stable diffusion进行文生图 |
| 1636 | astrbot_plugin_heybox_poster | 68 | group-admin | have | 统一管理多账号扫码、动态/长文/草稿、评论审核、通知轮询与主动浏览；内置小黑盒原生平台和管理面板 |
| 1637 | astrbot_plugin_rwinfo | 68 | group-admin | have | 铁锈战争房间查询插件: - 自动识别群/私聊消息中的房间号并安排探针查房   数字房: o/q/r/s + 数字 (r5132/s1024/o9999/q7777)   字母房: 其他字母 + 纯字母 (hytvvi/aabcde/babc)   两种房号均需 3 位以上; 纯数字/混合格式/IP  |
| 1638 | astrbot_plugin_topic_router_pro | 68 | group-admin | have | 先合并连发消息，再判断用户这句话是「接着上一个话题」还是「开了新话题」。  官方交流群：QQ 1130679595（话题路由器 PRO 官方交流群）—— 使用问题、误判反馈、功能建议都欢迎进群。  AstrBot 的对话是一整条上下文。当用户在同一会话里从「帮我画个电路板」跳到「顺便看看 NAS 硬 |
| 1639 | astrbot_plugin_persona_canvas | 68 | proactive | watch | 通过自然语言调用 GPT、Gemini、NovelAI 或自定义生图服务，管理人设正负面提示词、 服装姿势状态、参考图、主动私聊消息和每日早安照片。复杂设置通过内置 WebUI 管理。 |
| 1640 | astrbot_plugin_rika_share | 68 | media-parse | borrow | 莉卡解析 - 链接分享自动解析插件，支持 B站\|抖音\|快手\|微博\|小红书\|Twitter\|AcFun\|NGA。内置B站扫码登录、Cookie监控与自动应用。安装 astrbot_plugin_multincm 后自动接入网易云音乐解析。 |
| 1641 | astrbot_plugin_qq_api | 68 | other | watch | 在聊天里调 NapCat 的 OneBot API（仅管理员），如改群名片、换头像。 |
| 1642 | astrbot_plugin_tieba_lens | 68 | sticker | borrow | 自动识别贴吧链接、分享卡片与小程序，将图文帖子、吧主页及用户主页排成精美卡片。 支持头像昵称、真实吧等级、顺序图文表情、可配置评论与楼中楼、长帖分页、合并转发、群黑名单、分群规则和贴表情进度。 内置中文控制台，支持解析预览、六主题、霞鹜文楷与自定义字体、直接长图、任务重试、PNG/Markdown/ |
| 1643 | group_notice_manager | 67 | other | watch | 当群主,管理员发布群公告或@全体时自动响应 "td" 的管理插件 |
| 1644 | astrbot_plugin_xiaoxue | 67 | image-gen | watch | 让 LLM 通过正常聊天的方式调用 ComfyUI 进行画图（需要模型支持函数调用） |
| 1645 | astrbot_plugin_fishing | 67 | game | have | 电子钓鱼的小游戏 |
| 1646 | astrbot_plugin_dice | 67 | game | have | 一个骰子插件，支持设置面数和检定阈值，输入/dicehelp获取帮助 |
| 1647 | astrbot_plugin_self_manager | 67 | personality | have | 让 Agent 拥有自我管理能力 —— 安装/卸载/启停插件、管理 Skill、切换模型、控制工具、管理对话、查看人格、读写配置等。 |
| 1648 | astrbot_plugin_relationship | 67 | other | watch | 凝心溯溪系列关系模块：管理好感、信任、熟悉度、短期态度和关系边界， 支持把多个平台账号归属于同一自然人，并为回复提供关系语气参考。 |
| 1649 | astrbot_plugin_shell | 67 | other | watch | 发送 /sh <命令内容> 直接在机器人所运行的系统终端中执行命令并返回结果。支持三种权限模式：仅 Bot 管理员 / 白名单成员 / 所有用户，默认仅管理员。 |
| 1650 | llm_wants_to_sleep | 67 | other | watch | LLM想要睡觉 —— 一个让你的AI拥有自主睡眠意识的插件。 支持能量系统、睡眠阶段（浅睡/深睡/做梦）、消息聚合回复、 白名单管理、智能唤醒、假期模式、睡前仪式等人性化功能。 |
| 1651 | astrbot_plugin_bilibili_recommend | 67 | media-parse | borrow | 独立的B站公开视频推荐，支持关键词、真实链接、封面、会话去重和可选陪伴主动分享。 |
| 1652 | astrbot_plugin_cs_skins | 66 | other | watch | 通过 CSQAQ 的 API 进行调用，获取饰品的信息。 |
| 1653 | astrbot_plugin_decision_roulette | 66 | other | watch | 一个有趣且实用的插件，通过一张精美的静态结果卡片帮助用户做出决策，完美解决“选择困难症”或群组中意见不统一的难题。 |
| 1654 | astrbot_plugin_cs2-box | 66 | game | have | 简单的文字签到+配套cs2开箱 |
| 1655 | astrbot_plugin_skland_remind | 66 | game | have | 在原版基础上改进：森空岛签到（明日方舟/终末地）+ 登岛检票 + 双游戏理智回满提醒，支持定时签到、AI 自然语言操作与 WebUI 管理页 |
| 1656 | astrbot_plugin_rollpigs | 66 | other | watch | 抽取属于自己的小猪 - 今日小猪、随机小猪、找猪 |
| 1657 | astrbot_plugin_idle_mind | 66 | personality | have | 让它像人一样「想」而不是「每次都想干点什么」——念头自评想说程度、加噪声、分层落地，说不出口的沉进心事单按 7 天半衰期变淡，凌晨自动清算。零外部依赖，单独安装即可运行。 |
| 1658 | AstrbotFishEyes | 66 | ssh-exec | exclude | # 🐟鱼人之眼(AstrbotFishEyes)  [![AstrBot Version](https://img.shields.io/badge/AstrBot-%3E%3D3.5.0-blue.svg)](https://github.com/Soulter/AstrBot) [![Licen |
| 1659 | astrbot_plugin_bili_parser | 66 | media-parse | borrow | 解析 bilibili 视频、番剧、直播、专栏、音频等链接，并生成预览卡片。 |
| 1660 | astrbot_plugin_savagereply | 66 | group-admin | have | 真人群聊交互与表达中枢。打通“何时回（智能搭话/冷场打破/防插嘴）”与“怎么回（分段连发/打字节奏/TTS联动）”，让 Bot 如真人般自然灵动地融入群聊；同时保护代码块、表格、公式和超长正文，完整性优先。 |
| 1661 | astrbot_plugin_bing_search | 66 | media-parse | borrow | 使用必应（Bing）搜索引擎为 AstrBot 提供网页搜索能力。插件注册 web_search_bing 工具，返回与 AstrBot 原生网页搜索一致的 JSON 结果与引用索引；同时提供 /bing 指令便于手动测试。优先使用轻量 RSS 结果，失败时自动回退 HTML 解析，全程异步请求，无 |
| 1662 | astrbot_plugin_tarkovboss | 65 | other | watch | 查询塔科夫Boss刷率。 |
| 1663 | astrbot_plugin_galplayer | 65 | game | have | 一个可以让你和群友一起推galgame的插件，需要在windows电脑上运行galgame本体。 |
| 1664 | astrbot_plugin_hyrz | 65 | other | watch | 从火影忍者官网上查询火影忍者手游忍者信息 |
| 1665 | liblibApi | 65 | image-gen | watch | 一个功能强大的AI文生图插件，基于LiblibAI的API服务。支持SD1.5/XL、Flux和ComfyUI三种绘图模式，可自由搭配大模型和LoRA模型实现个性化创作。内置中英文提示词翻译功能，支持多种翻译模式 |
| 1666 | OriginiumSeal | 65 | other | watch | [仅 aiocqhttp] 将用户的头像添加源石封印效果。(ps:明日方舟) |
| 1667 | astrbot_plugin_shell_executor | 65 | other | watch | 用于AstrBot的shell远程执行器 |
| 1668 | astrbot_plugin_parser_test | 65 | media-parse | borrow | 高性能低耦合的链接解析器，支持 Bilibili、抖音、小红书和 Pixiv，并提供可配置 HTML 卡片渲染。 |
| 1669 | astrbot_plugin_chat_merger | 65 | other | watch | 让AI聊天告别一问一答！自动合并连续消息 + "正在输入"状态，打造真人级对话体验。 支持智能延迟计算、跳过关键词、超长等待、AI忙感知排队、图片独立转述和图片上下文限额等功能。 v2.8.2：跳过关键词可限制为仅在消息末尾命中，避免分享文案中的标点提前发送。 |
| 1670 | astrbot_plugin_ruqunhuanying | 65 | group-admin | have | 新成员入群时自动发送自定义欢迎语和图片，支持 WebUI 配置面板 |
| 1671 | group_quota_sleep_control | 65 | other | watch | 分群群聊活跃时间控制：每个群独立配置多段活跃时间，非活跃时段自动休眠并拦截 AI 回复，内置简单易用的 WebUI 管理面板。 |
| 1672 | astrbot_plugin_curiosity | 65 | other | watch | 定时挑方向联网搜，把有意思的点拆条存库、按专名去重，攒到了就用自己的语气主动讲。支持千帆/博查/SearXNG/自定义接口/AstrBot 自带搜索五种后端，可让 AI 自行探索方向，可联动 QQ 空间发说说，也能被自然语言触发。 |
| 1673 | astrbot_plugin_flowbot_adapter | 65 | other | watch | 通过 FlowBot ，让你的 Bot 也能够 WeChat。 |
| 1674 | astrbot_plugin_slave_market | 64 | game | have | Python 版牛马市场游戏，涵盖银行、市场、农务、VIP 等系统。 |
| 1675 | status-pro | 64 | other | watch | [需要安装前置]稍微好看一点的系统信息展示 |
| 1676 | astrbot_plugin_emoji | 64 | sticker | borrow | 基于达莉娅综合群娱插件的表情包制作插件，仅保留了@其他群员制作表情包的部分。由桑帛云API提供表情包制作。 |
| 1677 | astrbot_plugin_slave_market | 64 | game | have | 群内互动经营游戏「奴隶市场」。  玩法：购买群友当奴隶、让奴隶打工赚钱、训练/决斗/排位赛提升奴隶身价、 银行存取款与利息、抢劫、赎身。  指令（必须携带前缀：！ / ! 均可）： - 奴隶帮助 / 奴隶菜单 / 群友帮助 / 群友菜单 / nl帮助 / nl菜单 - 购买奴隶(@或QQ) / 购买 |
| 1678 | astrbot_plugin_coopanion_livingmemory | 64 | memory | have | 为桌宠 (Coopanion) 提供 LivingMemory 的本地 HTTP 直连桥接服务，支持双向检索、记忆注入与对话流自动同化。配套桌宠扩展 cortico-world-astrbot-livingmemory。 |
| 1679 | astrbot_plugin_persona_editor | 64 | group-admin | have | 白天收集明确反馈，每天北京时间23点集中比较一次，审核后只写人格设定，支持回退。 |
| 1680 | astrbot_plugin_natural_followup | 64 | other | watch | 为 QQ 群提供有界的连续对话窗口、短消息合并与相关插话筛选，无额外判断模型。 |
| 1681 | astrbot_plugin_df_loot | 64 | other | watch | 监控三角洲行动对局，出红/房卡时自动推送到 QQ 群；支持今日战绩、卡战备配装、出货排行榜、队友出货排行查询（含净收益与撤离率） |
| 1682 | astrbot_plugin_cron_push | 64 | other | watch | 用 cron 表达式或快捷语法（每日/每周）设置定时任务，到点自动向群或私聊发送消息。支持手动测试、暂停、恢复、删除、编辑内容、改触发时间、批量暂停/启用；消息支持 {{time}}/{{date}}/{{datetime}}/{{at:QQ}} 占位符；列表展示累计触发次数，每个任务保留最近 5  |
| 1683 | astrbot_plugin_moss_voice | 64 | tts | watch | 为 AstrBot 接入 MOSS 官方 TTS / STT：moss-tts-1.5-flash / moss-tts-1.0-pro 语音合成，moss-transcribe-1.0 / diarize-pro 音频转写。插件注册 moss_tts / moss_stt 两个服务提供商并支持一键 |
| 1684 | astrbot_plugin_police | 64 | group-admin | have | 一个以「警方」为主题的群聊治安管理插件：把群规执行包装成一整套警务体系， 而不只是一个禁言按钮。  **执勤出勤** —— `签到` / `巡逻` 累积执勤积分与警衔（见习警佐 → 总警佐，九级）， 连勤奖励按段递增并封顶；`出勤` 看打卡日历，`值班` 看本月值星官， `排班` 按时段安排值班员， |
| 1685 | astrbot_plugin_autogenimage | 63 | other | watch | 拦截并识别AI回复中的生图标记，自动调用独立生图API并返回图文混合消息。 |
| 1686 | astrbot_plugin_fun_toolbox | 63 | group-stats | borrow | 提供每日娱乐、随机选择、骰子、硬币、群聊排行与日报，以及安全可控的被动整活。 |
| 1687 | astrbot_plugin_ganttknights | 63 | game | have | 用一张长图查看《明日方舟》的活动、卡池、凭证兑换、时装和模组排期。 数据来自 [PRTS Wiki](https://prts.wiki)。  - `/方舟日程` 出图；完整指令见 `/方舟日程 帮助` - 可订阅每日推送：有节点时附提醒，也可设置为无提醒不推送 - 时间范围、底栏面板、背景图、提醒 |
| 1688 | astrbot_plugin_blockly | 63 | sticker | borrow | Blockly 可视化编程插件。使用 Blockly 积木（或直接编写 Python）创建"程序"，当机器人收到消息时执行， 通过积木决定是"返回消息"（劫持并直接回复）还是"传出消息"（放行交给 AstrBot 继续处理）。  功能特性： - 多程序（多文件）管理：新建、复制、删除、导入、导出、开 |
| 1689 | astrbot_plugin_manager | 63 | other | watch | 在聊天中管理 AstrBot 插件：查看列表、启停、重载、安装、卸载、更新 |
| 1690 | astrbot_plugin_comfyui_ai_studio | 63 | group-admin | have | Anima 全能绘画台把本地 ComfyUI 变成一台「说中文就能画」的绘画工作台——随便画、随便部署、功能全。 内置 Anima 提示词工程师和低 token 模板规则，不需要额外安装 Anima 插件。 内置 Anima Base / 2.9B、Qwen Image 2.1 普通 / Turbo |
| 1691 | astrbot_plugin_smart_request_review | 63 | other | watch | 监听 aiocqhttp 的好友申请和群邀请，先执行黑名单、白名单、关键词等确定性规则， 再按需调用 AstrBot 当前配置的大模型进行判断。支持全自动执行和半自动提交管理员审批。 |
| 1692 | astrbot_plugin_roulette | 63 | group-admin | have | 俄罗斯转盘赌，中枪者禁言，支持战绩查询和排行榜 |
| 1693 | astrbot_plugin_doubao_media | 63 | proactive | watch | 接入火山方舟 Doubao 媒体生成模型: - Doubao-Seedream 系列:文生图、图生图(默认 5.0 Pro) - Doubao-Seedance 系列:文生视频、图生视频(默认 2.0 mini)  视频生成是异步任务,插件后台轮询,完成后主动发送。 支持自定义 API 地址与模型名 |
| 1694 | astrbot_plugin_image_recall | 63 | memory | have | 缓存每个会话最近 N 张图片的 URL，不主动调用视觉模型；当用户 @ 机器人并提到“图/上面/刚才/那张/看看/识别”时，取最近一张图片识别，并把描述注入当前消息。支持“第2张/上一张”等简单定位。 本项目由 AI（DeepSeek Harness）根据用户需求实现，代码与文档由 AI 起草，请自 |
| 1695 | astrbot_plugin_breezeblue_tts | 63 | tts | watch | 将 AstrBot 的文字回复通过 BreezeBlue TTS 合成为语音，并作为 QQ 语音发送。 支持按人格映射不同声音、语气指令、纯语音或文字加语音、以及管理员语音测试命令。 需要自备 BreezeBlue API Key 和 voice_id。 |
| 1696 | astrbot_plugin_friberg | 62 | game | have | 猜 CS Player 的小游戏 |
| 1697 | astrbot_plugin_pplxsearch | 62 | other | watch | 基于Perplexity AI的互联网搜索插件，可用/pplx 搜索命令 |
| 1698 | astrbot_plugin_leetcode | 62 | other | watch | leetcode 每日一题、随机题目。 |
| 1699 | astrbot_plugin_overstats | 62 | other | watch | overstats守望先锋战绩查询工具 |
| 1700 | astrbot_plugin_ncm_daily | 62 | tts | watch | 网易云音乐助手：搜索音乐、点歌、歌单搜索、歌曲封面（三档分辨率）、每日推荐、私人FM、私人雷达、个人歌单，支持发送 QQ 音乐卡片 |
| 1701 | astrbot_plugin_lazy_tools | 62 | memory | have | 把 AstrBot 每次请求都要携带的全部工具定义改成“按需注入”：默认只下发 astrbot_find_tools / astrbot_load_tools / astrbot_unload_tools 三个元工具和少量常驻工具， 其余工具按插件/能力自动分组隐藏；模型需要时先搜索再加载，加载后下 |
| 1702 | astrbot_plugin_unread_catchup | 62 | personality | have | 机器人上线/重连后，自动拉取最近的私聊聊天记录，找出你发了但没回的消息，用当前人格 + 最近上下文生成回复并自动补发。 支持手动 /补消息 触发，可配置 QQ 号、拉取条数、最多补几条与发送间隔。 |
| 1703 | astrbot_plugin_fatfish_memhyg | 62 | memory | have | 记忆插件拼召回，没人管记进去的干不干净。只记谁什么时候说了做了什么、不记对人的揣测，「明天」写成日期，新说法取代旧的、旧的标已改，冒充的标出来，会淡会模糊，用户自己能看能删；装了 LivingMemory 就当它的卫生层。细节和配置见 README。 |
| 1704 | astrbot_plugin_image_cache | 62 | memory | have | 将 AstrBot 收到的图片保存到稳定缓存并写入历史，方便多模态模型读取历史图片，也可通过 LLM Tool 在当前群或私聊范围内搜索并取回稳定路径；另带图库、来源记录、图片转述归档、搜索和缓存筛选，缓存清理由 AstrBot 统一管理 |
| 1705 | meme_plugin_astrbot | 62 | sticker | borrow | meme 插件（astrbot版）- meme 表情包、QQ 音乐点歌 |
| 1706 | astrbot_plugin_codex_reset | 62 | other | watch | 追踪 codex-reset.com 公共额度重置，支持 Tibo 重置预告、WebUI 群黑白名单通知、上次重置查询及下次重置预测。 |
| 1707 | astrbot_plugin_morning_muse | 62 | proactive | watch | 每日 AI 风格化日程 + 内在状态 + 主动消息，人格隔离，一键注入。 |
| 1708 | astrbot_plugin_breeze_local | 62 | tts | watch | 把本机 Breeze-TTS-2.cpp 服务接入 AstrBot，直接拉取服务端音色库，支持指令合成与 LLM 按需调用。 |
| 1709 | astrbot_plugin_email_narrator | 61 | proactive | watch | 一个智能邮件播报插件，能接收邮件并让继承了会话和人格的 LLM 来通知用户 |
| 1710 | astrbot_plugin_-dpcq_game | 61 | game | have | 一个文字修仙游戏，基于经典小说《斗破苍穹》设定，包含境界突破、炼丹系统、副本挑战等丰富玩法 |
| 1711 | random_vtb | 61 | other | watch | 为管人痴服务，输入/dd随机推一个管人直播间，或查询哪些管人在播啥。 |
| 1712 | astrbot_plugin_mitchell_minichat | 61 | proactive | watch | QQ 私聊的主动消息插件：加权曲线挑时机，结合事件感知、在场状态与约定时间点决定说什么；支持分段发送、睡眠免打扰，自带 Web 面板。仅支持 aiocqhttp，问题请走 GitHub Issues。 |
| 1713 | astrbot_plugin_persona_studio | 61 | personality | have | 在聊天里就能养人格：**对话中新建人格 → 随时切换 → 不满意直接让 LLM 改**，同时注册只读的 LLM 工具，让模型自己读取人格。  - `/人格创建 <名称> <描述>`：描述由 LLM 扩写成完整系统提示词（加 `--raw` 可直接使用原文） - `/人格切换 <名称>`：群聊 / 私 |
| 1714 | astrbot_plugin_qq_msg_normalizer | 61 | proactive | watch | 把合并转发、卡片、语音和媒体归一化成普通文本，让群上下文、历史记录、插话判定和主 Agent 都能读懂。支持引用补全和语音转写回退，附带控制台；不改 AstrBot 核心、不依赖第三方库、 不主动发送消息。 |
| 1715 | astrbot_plugin_l4d2_query | 61 | game | have | Left 4 Dead 2 服务器查询/订阅/管理插件 |
| 1716 | astrbot_plugin_packsend | 61 | other | watch | 根据Bot单次发送消息长度自动将长消息转为QQ合并转发消息，支持按群独立设置上限，检测到 / 指令后自动拦截5秒内输出并合并转发，管理员可通过 /pack rate 指令在聊天中快速设置 |
| 1717 | astrbot_plugin_pokedex | 61 | game | have | 宝可梦图鉴插件：内置 pokemon-dataset-zh 中文图鉴库（1025 只宝可梦 + 295 个形态、特性、招式、道具、24 个地区图鉴、基准属性表），支持指令与 LLM 函数调用查询，图鉴结果以图片卡片展示。查询优先使用本地中文数据，PokéAPI 官方数据作为补充（可配置关闭，纯离线运 |
| 1718 | astrbot_plugin_lyria | 60 | other | watch | 通过API调用Google Lyria生成音乐 |
| 1719 | astrbot_plugin_owcx | 60 | other | watch | Overwatch 查询插件 - 基于 OverFast API 查询玩家战绩、英雄信息等 |
| 1720 | astrbot_plugins_galinfo | 60 | game | have | 一个可以提供查询 Galgame 简介等信息的插件 |
| 1721 | astrbot_plugin_face_echo | 60 | sticker | borrow | QQ 群聊贴表情附和插件——群友给消息贴了表情回应后，机器人给同一条消息贴上相同的表情 |
| 1722 | astrbot_plugin_qzone_multibots | 60 | other | watch | 管理多个 aiocqhttp 账号对应的 QQ 空间，支持发布动态、查看和互动、自动评论与回复及 WebUI 管理，重构自：https://github.com/Zhalslar/astrbot_plugin_qzone |
| 1723 | astrbot_plugin_qq_toolbox | 60 | image-gen | watch | 整合 画图、复读与主动回复、模型输入屏蔽、Bot 观察台、真实生活、QQ 随机语音、QQ 空间和输出禁词替换，统一配置与启停。 |
| 1724 | astrbot_plugin_block_pure_quote | 60 | other | watch | 群聊中仅引用AI消息（未@、未带唤醒词）时，静默阻止 LLM 自动回复。 |
| 1725 | astrbot_plugin_daily_report | 60 | proactive | watch | 微信/QQ/Telegram 多平台通用早报插件：对机器人说「早」即收到天气（冷热对比+增减衣提示+明后天）+ 今日头条新闻 + 加密货币行情（24h涨跌+本月走势）+ 每日一言。主动对话触发而非定时推送，规避微信平台主动消息条数限制，零key零依赖。 |
| 1726 | astrbot_plugin_media_reply_filter | 60 | group-admin | have | 随机与跟随复读、结合群聊上下文的主动回复判断，以及艾特冷却、休眠、人设保护、图片过滤与撤回联动。 |
| 1727 | astrbot_plugin_morning_news | 59 | platform | have | 定时向飞书会话推送每日晨报，支持卡片展示、文本回退、订阅、预览、新闻速览、天气查询与管理员立即群发。 |
| 1728 | group_sign | 59 | other | watch | [仅 aiocqhttp] 让 bot 定时群打卡 |
| 1729 | astrbot_plugin_gemini_artist | 59 | other | watch | [仅 QQ] 提供调用Gemini系列的生图模型的函数工具，让你的非生图模型具有接近原生生图模型的生图体验 |
| 1730 | astrbot_plugin_qq_group_manager | 59 | group-admin | have | QQ 官方机器人的群管插件（QQ官机群管）—— 把「群主该干的活」交给机器人： 禁言 / 解禁 / 查禁言、消息撤回、入群审批（含按钮一键通过 / 拒绝）、欢迎语、成员档案、 退群与被移出通知，外加一套四维群规审核（关键词 · 群规 · 语义 · 图片）。 【怎么判】先走关键词与缓存，零成本直接出结 |
| 1731 | astrbot_plugin_endworld_img_api | 59 | other | watch | 一个自定义API获取图片插件。 支持多指令分流、智能防超时、全网 API 兼容的高级图片引擎。基于mccloud_img重构。 |
| 1732 | astrbot_plugin_daily_fortune | 59 | game | have | 每日运势占卜插件：以大衍筮法（大衍之数五十，其用四十有九）起卦演周易， 结合 LLM 解卦定今日运势吉凶，并使用仿浅草寺签文的古风模板将起卦过程、 卦象、解卦结果渲染成图片输出。  功能： 1. /今日运势 —— 按大衍筮法随机起卦，LLM 解卦，渲染古风图片； 2. /解签 —— 对今日已抽取的运 |
| 1733 | astrbot_plugin_screenshot_detection | 59 | info-push | have | 定时截图电脑屏幕，使用 AI 分析内容并推送到指定会话。  ## 功能特性 - 定时自动截图屏幕 - 使用 AI 分析截图内容 - 支持推送到任意会话 - 自然语言触发截图 - 延迟截图支持 - 免打扰时段 - 自定义分析提示词 - 自定义识图模型 |
| 1734 | astrbot_plugin_priestess | 59 | other | watch | 基于 Billtranscend/Priestess-bot 的 AstrBot 接口适配，支持明日方舟与终末地。 |
| 1735 | astrbot_plugin_fish_style_evolution | 59 | memory | have | 独立的自学习插件。只读跨群用户记忆库，按群学群体表达风格、按 QQ 学个人表达风格，结构化画像经程序规则与语义评估双关卡，PASS 才自动升版本，HOLD/REJECT 保留旧版。实时只通过 extra_user_content_parts + mark_as_temp() 注入 150~220 字 |
| 1736 | astrbot_plugin_futaloli | 59 | other | watch | FutaLoliAPI 随机图片：/futaloli 命令 + LLM 翻图库工具，支持多 API 源（官方/自托管任意添加） |
| 1737 | astrbot_plugin_crazy_thursday | 59 | ssh-exec | exclude | 每周四定时向指定群发送一条疯狂星期四文案（vme.im / RSSHub 多源可插拔） |
| 1738 | astrbot_plugin_pixiv_daily_women | 59 | other | watch | 从 Pixiv 每日插画榜按顺序发送符合筛选条件的单页原图，不需要登录或 Cookie |
| 1739 | astrbot_plugin_tk_tracker | 58 | group-admin | have | 自动监听管服机器人的踢人播报，支持WebUI配置、违规历史查询与数据一键管理。 |
| 1740 | astrbot_plugin_ojs | 58 | other | watch | 在特定群聊某人发言后概率触发列表内的回复。 |
| 1741 | AnimeMagnet | 58 | other | watch | 这是一个动漫磁链查询插件，可以获取动漫磁链 |
| 1742 | answerbook | 58 | other | watch | 一个简单的答案之书插件,发送 答案之书+问题 即可使用 |
| 1743 | astrbot_plugin_qq_group_manage | 58 | group-admin | have | QQ官方机器人群管插件:入群审批和验证、多功能按钮菜单、成员进退群通知、Web UI控制台、群广播、禁言、监控面板(包含刷屏监控、风险消息撤回、服务器运行状态)和LLM工具 |
| 1744 | astrbot_plugin_deerpipe | 58 | platform | have | 一款可爱的每日打卡插件，记录你的健康生活每一天，生成精美的月度打卡日历，支持补签和好友互动。 |
| 1745 | astrbot_eryou_daily | 58 | other | watch | 检测星铁、原神、绝区零、异环每日状态和体力 |
| 1746 | astrbot_plugin_visual_recall | 58 | memory | have | 根据语境按需回看会话中出现过的历史图片，无需引用图片，也不用在消息中附带图片，也不需要开启图片上下文。 |
| 1747 | astrbot_plugin_schedule_guard | 58 | memory | have | 主动消息发送前结合聊天上下文与 LivingMemory 判断忙闲，保留检查记录。 |
| 1748 | astrbot_plugin_volcengine_plan_voice | 58 | tts | watch | 通过火山方舟 Agent Plan 专属接口为 AstrBot 同时提供语音转文字（STT，doubao-seed-asr-2.0）与文字转语音（TTS，doubao-seed-tts-2.0）。一次安装、一份 API Key，在服务提供商中分别添加即可使用。 |
| 1749 | astrbot_plugin_spiderman_meme | 58 | sticker | borrow | 在聊天中发送 mj（不区分大小写，也可以发 /mj），机器人会从插件目录 mj资源包/ 中随机发送一张蜘蛛侠表情包。 可直接往资源包添加图片（jpg/png/gif/webp，建议 3~30 张）。本地无图时自动退回在线图源，无需登录、无需 API Key。 |
| 1750 | astrbot_plugin_group_msg_forward | 58 | other | watch | 群消息转发互通插件，可以在多个QQ群之间以合并转发（聊天记录）的形式转发消息。 支持双向互通（多群之间互发消息）和单向互通（发送群消息转发到接收群）两种模式。 转发时自动获取发送者头像和昵称，以聊天记录形式呈现。 |
| 1751 | astrbot_plugin_group_invite_auto_approve | 58 | group-admin | have | [仅aiocqhttp]自动处理群邀请：收到邀请时在日志打印群聊全部信息；按关键词（群名/群介绍/群公告）与群人数条件自动同意；支持入群后复核（不合格自动退群）、通知邀请人、入群欢迎消息与欢迎图片；自带 WebUI 管理页。 |
| 1752 | astrbot_plugin_goodluck | 58 | game | have | 随机生成 0~100 的今日运势分数，并给出等级评价、宜做 / 忌做清单、今日建议， 以及幸运数字、幸运颜色、幸运方位和黄金时段。  使用方式：发送 `/今日运势`（别名：`/今日运气`、`/gl`）。  特点： - 文案丰富：宜做 42 条、忌做 36 条、建议 30 条、幸运颜色 20 种，   |
| 1753 | astrbot_plugin_no_reply | 58 | other | watch | 为模型提供主动选择不回复的工具，支持可选的引导提示词注入。 |
| 1754 | astrbot_plugin_http_adapter | 57 | other | watch | 获得使用 HTTP 接口调用 AstrBot 的能力 |
| 1755 | astrbot_plugin_mathjax2image | 57 | other | watch | 调用 LLM 生成数学文章，支持 MathJax 公式渲染为图片 |
| 1756 | AstrBot_chishenme | 57 | other | watch | 当用户发送的消息中包含关键词“吃什么”时，机器人会自动回复一段预设的文本。 |
| 1757 | astrbot_plugin_hds_interlude | 57 | memory | have | 时间感知的持续叙事聊天框架 AstrBot 移植版。让角色拥有日程、关系、待办、情绪与未完成事件，用户消息作为一项事件参与角色当下的判断与生活。 |
| 1758 | astrbot_plugin_wake | 57 | personality | have | 被@一次就能接着聊：关键词粗筛 + 小模型精判 + 唤醒窗口。只写 is_at_or_wake_command，不碰 prompt/contexts，人格与上下文全部走 AstrBot 原生链路（天然按人格隔离）。 |
| 1759 | astrbot_plugin_memoir | 57 | memory | have | 模拟人脑记忆闭环（编码-巩固-遗忘-召回-洞察）的长期记忆插件，无向量检索 |
| 1760 | astrbot_plugin_godsay | 57 | other | watch | 基于 AstrBot 的群聊圣经随机语录回复插件，支持自定义关键词、多圣经内容匹配和随机回复。 |
| 1761 | astrbot_plugin_regex_filter | 57 | other | watch | 在 Bot 回复发送前执行可配置正则规则。 默认将“汝”替换为“你”，并在 Bot 回复中检测到“笨蛋”时移除该词本身，而不是拦截整句话。 WebUI 支持手动新增、删除、启用/停用和修改过滤词规则。 |
| 1762 | astrbot_plugin_music_context | 57 | media-parse | borrow | 解析音乐分享内容，获取歌曲信息与歌词，让 AI 理解并参与关于歌曲的交流。 |
| 1763 | astrbot_plugin_group_habitat | 57 | memory | have | 借鉴 astrbot_plugin_livingmemory 的记忆生命周期，把「AIRP 人物生境写法」落进群聊：  1. 被动采集：不唤醒 Bot、不插话，静默记录群里每一条消息（含非 @ 消息）。 2. 证据优先：每条结论都保存原始消息证据与**原文快照**，可追溯、可证伪；    默认永久保 |
| 1764 | astrbot_plugin_role_refiner | 57 | personality | have | 在LLM生成回复后，根据角色设定提示词对回复进行二次润色，提升角色扮演的一致性和表现力。 |
| 1765 | astrbot_plugin_lingbao_market | 56 | other | watch | 监听灵宝市集分享码，发送至后端接口。 |
| 1766 | thefuck | 56 | other | watch | 一个为 AstrBot 设计的命令纠错插件，灵感来源于著名的命令行工具 thefuck。当你不小心输错了一个命令时（例如 /pixic 而不是 /pixiv），只需紧接着发送 /fuck，此插件就会尝试找出你可能想输入的正确命令，并给出建议。 |
| 1767 | astrbot_plugin_moyurenpro | 56 | platform | have | 摸鱼人日历，支持自定义时间时区，自定义api，支持立即发送，工作日定时发送。 |
| 1768 | astrbot_plugin_qqoffice_expand | 56 | other | watch | QQ 官方机器人扩展能力中台——按配置实例路由到任意数量的 QQ 官方机器人，提供群成员与黑名单管理、C2C 流式分片、频道管理与私信、扩展事件、富消息、菜单与指令面板；配额/引用/去重按机器人身份共享。 |
| 1769 | astrbot_plugin_msg_spoof | 56 | other | watch | QQ消息伪装插件，支持快捷伪装和详细伪装两种模式，以聊天记录转发（合并转发）形式呈现伪装消息 |
| 1770 | astrbot_plugin_mcsrv_status | 56 | game | have | 查询 Minecraft 服务器在线状态（Java 版 SLP / 基岩版 RakNet 直连，不依赖第三方 API）， 返回状态 Banner：服务器图标、状态、地址、MOTD、版本、人数、延迟。 支持指令 /查服 [地址]，也支持自然语言提问（服开着吗、多少人、卡不卡）， 全局与按群配置默认服务 |
| 1771 | astrbot_plugin_memory_digest | 56 | memory | have | 把对话提炼成 bot 的第一人称长期记忆，写进知识库。  **三层分类**：state / preference / event，判据是「加不加日期才成立」。 state 每轮全量注入；preference 和 event 走检索 + 闸门，event 还按时间递减。  **写入闸门**：时间锚硬校 |
| 1772 | astrbot_plugin_lettergame | 56 | game | have | 提供群聊与私聊开字母游戏功能 |
| 1773 | astrbot_plugin_sensenova_u1 | 56 | other | watch | 调用商汤 SenseNova U1 Fast 模型生成图片，支持通用生图与信息图模式，含上下文增强、排队、配额与历史 |
| 1774 | astrbot_plugin_msg_formatter | 56 | other | watch | 将ai回复中的\n\n替换为\n，以此解决莫名其妙的空行 |
| 1775 | astrbot_plugin_ottohub | 55 | other | watch | AstrBot 的 OttoHub（ottohub.cn） 平台适配器插件 |
| 1776 | astrbot_plugin_sl_query | 55 | other | watch | 通过 ServerKey 和 LabAPI 插件服务端 查询 SCP:SL 服务器信息 |
| 1777 | astrbot_plugin_qbittorrent_bridge | 55 | other | watch | qBittorrent 桥接器 |
| 1778 | bmtxt2img | 55 | image-gen | watch | 通过/bmimg指令调用智谱文生图模型 |
| 1779 | astrbot_plugin_furry_dsgg | 55 | other | watch | [仅aiocqhttp] 广告助手，帮助你向所有群聊定时发送广告 |
| 1780 | saris_db | 55 | other | watch | astrbot_plugin_saris_economic 插件的前置插件，用于数据持久化。 |
| 1781 | astrbot_plugin_sjzb | 55 | game | have | 随机生成《绝地潜兵2》游戏中一组 4 个战备配置 |
| 1782 | astrbot_plugin_chatsummary | 55 | other | watch | [仅 aiocqhttp] 一个通过拉取历史聊天记录，调用 LLM 大模型接口实现消息总结功能。 |
| 1783 | qq_official_url_cleaner | 55 | other | watch | 为 QQ 官方 API 修改发送消息的链接，可改善消息被屏蔽的现象 |
| 1784 | astrbot_plugin_airi_gallery | 55 | sticker | borrow | 数字排序画廊插件，支持按分类随机看图、从分类名含「图片」的图库随机抽图、全图库抽表情、编号与范围查看；QQ 回复图片、多图及合并转发上传，成功后 @感谢和累计贡献统计，可使用 /查看贡献 查询本人投稿数量；同时支持精确/相似查重、分类安全迁移、WebUI/Cloudflare Pages 管理、Gi |
| 1785 | astrbot_plugin_grok_oauth | 55 | other | watch | 独立的 Grok OAuth 模型提供商，支持对话、OAuth额度查询、按需网页搜索、视觉、图片及视频生成编辑。 |
| 1786 | astrbot_plugin_mutsumi | 55 | personality | have | 若叶睦的多重人格（若叶睦/墨提斯/两岁若叶睦），情绪驱动切换，提示词与代码分离，带提示词编辑 WebUI |
| 1787 | astrbot_plugin_custom_api | 55 | tts | watch | 多样化的外部API调用工具，可处理文本、图片、语音和视频类型API，支持自定义参数配置，关键词触发调用 |
| 1788 | astrbot_plugin_mimo_media | 55 | other | watch | 为 AstrBot 中的小米 MiMo（mimo-v2.5 系列）补全视频与音频理解能力，并可将图片、视频、音频消息临时路由到指定 MiMo provider。 |
| 1789 | astrbot_plugin_dimensional_portal | 55 | other | watch | **次元门**（Dimensional Portal）——让 AstrBot 里的大模型变成你手机的手：在 QQ 里说一句话， 它就能截图看你手机在显示什么，然后点击、滑动、长按、输入文字、按返回键、打开应用。 全部通过无障碍服务完成，**不需要 root**，手机上也不装第二个模型。  ### 能 |
| 1790 | astrbot_plugin_mc_body | 55 | memory | have | 需要额外运行 Minecraft 客户端，并部署配套 KubeJS 与 Baritone 环境。支持游戏聊天、感知、移动、物品交互、配方书合成、冶炼和程序任务，尽可能做到模拟真实玩家， 参考了言出法随等模组 专门基于上下文 对话记录和记忆感知连贯性做了调整 |
| 1791 | astrbot_plugin_miyo_codes | 55 | game | have | 盯官方直播接口取码，等码齐、直播结束后自动发到群或私聊，不用人守着。 装好后填 target_groups（发群）或 target_friends（发私聊）；两个都留空就什么都不发。 平时不轮询：按版本周期推算前瞻窗口，窗口内才查预告和 act_id，三家各自独立。 群里有人贴直播间链接会自动接住； |
| 1792 | astrbot_plugin_buff_cs2 | 55 | other | watch | 通过网易 BUFF 平台查询 CS2 饰品价格。  - 指令：/buff [枪名] [皮肤名] [磨损]，如 /buff ak 燃料喷射器 久经 - 消息一：饰品基础信息（官方名称、图片）、当前最低供应价、最高求购价（含求购条件）、30 天价格走势与一句购买建议 - 消息二（武器类，默认关闭，可在插 |
| 1793 | astrbot_plugin_fanqie_novel | 55 | other | watch | 发送番茄小说分享链接，自动抓取整本并导出 TXT 发回聊天。插件自带下载器后端，首次运行自动准备，无需手动安装任何依赖。 |
| 1794 | astrbot_plugin_cucumber_search | 55 | sticker | borrow | 给一张图反查 Coser 社媒账号与二次元图源。支持 Google Lens、SauceNAO、trace.moe、IQDB、百度识图多引擎；支持引用搜图；支持自定义表情包、代理与指令配置。 |
| 1795 | astrbot_plugin_temp_block | 55 | other | watch | 拦截通过 QQ 群发起的临时会话，阻止用户绕过群聊封禁直接私聊 bot。仅对 aiocqhttp（QQ 个人号）平台有效。 |
| 1796 | astrbot_plugin_cloudmailapi | 54 | platform | have | 对接CloudMail邮件系统API，支持自助注册、登录及查信（仅测试napcat） |
| 1797 | astrbot_plugin_the_Big-3_Chinese_AI_conferences | 54 | other | watch | 亿万人将要精读中文AI顶会 |
| 1798 | astrbot_plugin_sleep_tracker | 54 | other | watch | 一个基于 AstrBot 的睡眠记录插件，帮助用户记录和分析睡眠作息情况 |
| 1799 | astrbot_plugin_RG | 54 | game | have | 俄罗斯轮盘，群小游戏插件，通过装填[可带参数]、射爆，等指令控制，具体可看说明文档 |
| 1800 | astrbot_plugin_global_status | 54 | info-push | have | 订阅主流 AI、云与开发平台的官方状态页，向群聊推送图片告警。支持所有具备群聊和主动推送能力的平台适配器，填入 UMO 即可使用。 |
| 1801 | quote_collocter | 54 | other | watch | 语录插件，支持群聊投稿、稀有度抽卡、投稿记录、回复管理与 AI Tools，用法请看 README。 |
| 1802 | astrbot_plugin_LLM_like | 54 | tts | watch | 自动或自主为用户送上每日上限名片赞，支持LLM考虑给不给赞、全方式求赞识别、函数调用(Tool Calling)、当前人设与语音插件(genie)个性化反应。 |
| 1803 | astrbot_plugin_smart_fish | 54 | game | have | 基于唤醒词、主人与判断模型的按需回复，支持回复防抖、群聊上下文、认主、图片与动图转述、转述缓存、戳一戳反戳、群聊与私聊主动聊天、决策记录面板，并可查询基元律动(tokenrhythm.studio)余额用量与 AstrBot 系统调用统计。【有建议或bug在 GitHub 上提交，看到后会尽快修复， |
| 1804 | astrbot_plugin_openai_image | 54 | image-gen | watch | 为 LLM 注册图像生成与编辑工具，并提供聊天命令调用；支持多来源、多模型轮询与访问控制。 |
| 1805 | astrbot_plugin_human_sim | 54 | sticker | borrow | 在指定群里模拟真人：潜水插话、冷场开话头、冒泡发 QQ 表情、发言带表情包。拍一拍全链路：被拍必回（回戳/冒话/甩表情）、同一人连拍必回戳、回完人顺手拍一下；「拍拍我/戳我」这类纯动作在本地直接处理不进 AI。不聊天就不主动戳人（冷场、潜水、跟戳都不拍），只有回完对方的话或对方先戳自己才拍。全部带概 |
| 1806 | astrbot_plugin_avatar_rotator | 54 | other | watch | 通过WebUI或QQ上传头像到持久化图库，并按固定间隔随机或顺序更换Bot的QQ头像（仅NapCat/aiocqhttp） |
| 1807 | astrbot_plugin_context_hygiene | 54 | memory | have | 修复空 tool_calls、非法工具调用、缺失工具结果导致的 LLM 400 响应错误。 |
| 1808 | astrbot_plugin_dafeiyu_faces | 54 | personality | have | 治"只会一张脸"：LLM 回复里的颜文字同款连用（该会话最近 N 条内出现过）就自动从同情绪池随机换一张——模型管配脸的时机和情绪，库管多样性。只认库内精确匹配的脸（不误伤（）动作描写），不认识的脸放行，任何异常放行原消息（fail-open）。只处理模型生成文本，指令/工具消息不动；换脸在分段发送 |
| 1809 | astrbot_plugin_kugou_music | 54 | group-admin | have | 纯酷狗音乐点歌插件，不依赖第三方 API 中转。  - 搜索 + 点歌：`/酷狗搜歌 <关键词>` → `/酷狗点歌 <序号>` - 三种登录方式：`/酷狗扫码登录`（通用）、`/酷狗微信登录`（仅概念版/安卓渠道，链接 1 分 50 秒自动撤回）、WebUI 手动填 Cookie - VIP 歌曲 |
| 1810 | astrbot_plugin_wol_miko | 53 | other | watch | 简易局域网WOL唤醒 |
| 1811 | astrbot_plugin_bazaar | 53 | game | have | astrbot_plugin_bazaar 是一个 AstrBot 聊天机器人插件，可以在 QQ / Telegram / 微信等平台中快速查询 The Bazaar 游戏数据，包括怪物、物品、技能信息，以及来自社区的推荐阵容。  查询结果以精美的图片卡片形式呈现，支持中英文双语查询。 |
| 1812 | astrbot_plugin_groupGuard | 53 | other | watch | ［仅OneBot］自动拒绝已加入其他某个群的成员加群 |
| 1813 | astrbot_plugin_bolatuship | 53 | other | watch | 使用柏拉图API接口和Sora 2等模型生成视频。 |
| 1814 | chengyu | 53 | other | watch | 支持LLM智能接龙的成语接龙插件v2.0，分用户积分统计，简化命令，智能过滤，随机开始 |
| 1815 | astrbot_uptime_kuma_webhook_plugin | 53 | platform | have | 通过 Webhook 从 Uptime Kuma 接收监控状态通知，并将这些通知推送到指定的 AstrBot 用户或群组 |
| 1816 | astrbot_plugin_nest_diary_connector | 53 | other | watch | 小窝是 AstrBot 的私有空间框架。日记只是其中一个官方模块，后续可以继续扩展人物印象、媒体归档、前端样式、自定义模块和外部工具接入。 |
| 1817 | blhx_wiki | 53 | other | watch | 碧蓝航线WIKI查询机器人插件（适用于 AstrBot + NapCat） |
| 1818 | astrbot_plugin_bilibili_video_summary | 53 | media-parse | borrow | 通过自然语言提取 Bilibili 视频全部分P字幕并生成总结。 |
| 1819 | astrbot_plugin_codeagent | 53 | devtools | watch | 代码编写Agent，自动完成需求分析、代码生成、沙箱运行测试、安全审查、质量评估、Debug和项目交付全自动流程 |
| 1820 | astrbot_plugin_memory_sync | 53 | memory | have | 定期扫描 AstrBot 对话数据库，用 AI 增量沉淀人物画像与任务记忆。  - 人物画像 -> user_profiles.md（按群/人物分节） - 任务/指令 -> memory.md - 游标记录扫描进度，防重复 - 自动防膨胀，保护主人手写内容 |
| 1821 | astrbot_plugin_calendar | 53 | platform | have | 让 bot 自动识别当天节日、调休和工作日状态，也支持查询过去或未来的任意日期。  - 内置 `/节日`、`/节日查询`、`/下个节日`、`/节日列表`、`/传统节日` 等指令，覆盖今天、指定日期、下一个法定节假日、某月法定安排与某月传统节日； - 同时注册 LLM 工具 `calendar_che |
| 1822 | astrbot_tarkov_datasearch | 53 | other | watch | 查询塔科夫玩家档案（等级、阵营、K/D、幸存率、技能、成就；默认来自 Atlas 实时查询，可改用 tarkov.dev 公开快照）、服务器状态、Boss 刷率，以及各服务器平均匹配时间（数据来自 Atlas），生成图片回复（tarkov.dev 快照也可用文字/Markdown）。 |
| 1823 | astrbot_plugin_pictools | 53 | sticker | borrow | 图片与 GIF 处理工具箱，支持镜像对称、旋转反色、倒放调速、喜报悲报、趣味表情包和 Emoji 合成。 |
| 1824 | astrbot_plugin_notion_bridge | 52 | kb-rag | have | 桥接 Notion 与 AstrBot 的双向文档管理工具。支持递归读取、关键词搜索、知识库同步、LLM 查询，以及完整的文档增删改查（页面/块/数据库/用户/评论）。内置 Notion API 3 req/s 速率限制器，可靠管理大量文档。 |
| 1825 | dynamic_subagent | 52 | other | watch | 让 AI 可以通过 tool call 动态创建和管理子 Agent |
| 1826 | astrbot_plugin_terraria_server_manager | 52 | other | watch | Terraria TShock 服务器监控，支持玩家上下线通知、在线查询与远程指令执行 |
| 1827 | astrbot_plugin_gifcaijian | 52 | other | watch | 可以裁剪和合并gif 分解等功能（后续慢慢润化） |
| 1828 | astrbot_plugin_picture_manager | 52 | other | watch | 图片管理插件，允许用户通过自定义触发指令从API或直接URL获取图片。 |
| 1829 | astrbot_plugin_botName | 52 | other | watch | bot动态群名片插件,使用请先看插件说明 |
| 1830 | astrbot_plugin_SDGenPlus | 52 | kb-rag | have | Stable Diffusion WebUI 生图增强插件，支持神秘法典词库 Embedding 语义检索、默认 LoRA 注入、LLM 工具调用和 SDXL/SD3/FLUX/Pony/NoobAI/Illustrious 参数预设。 |
| 1831 | astrbot_plugin_desktop_screenshot | 52 | other | watch | 收到「截图」指令后，立即截取机器人所在电脑的桌面并发送图片，无需唤醒词 |
| 1832 | astrbot_plugin_auto_evolve | 52 | personality | have | 一套会自己改自己的提示词进化引擎。到点把最近的对话连同当前人格全文重读一遍， 找出反复出现的模板句、写了却没生效的规矩、和真实对话脱节的表述；每条都写成 「改哪一句 / 改成什么 / 为什么改」，落地前先自证（唯一命中、不重复、不越层、 不删锚点），过了才动，动前备份、动完抽样复验。补丁经你点头才落 |
| 1833 | astrbot_plugin_user_profile | 52 | group-admin | have | LLM 驱动的独立 QQ 用户画像插件。持续积累群聊、私聊、社交来源和管理记录，由 LLM 结合真实发言分析表达方式、兴趣、互动习惯与内容风险，输出带依据的标签、人物印象和长期特点；长期特点具有跨日证据台账，风险评分区分未审查、当前有效和沿用旧画像。模型故障时保留最后成功画像，支持图片输出、历史扫描 |
| 1834 | astrbot_plugin_memory_recall | 52 | memory | have | 接管 AstrBot 的记忆注入，按「状态 / 偏好 / 事件」三层策略走。  **状态层**：双方是什么关系（称呼 / 关系定位 / 陪伴承诺），每轮全量注入，不过闸门。 **偏好 / 事件层**：先用 rerank 打分，再过「地板 + 领先」闸门；事件按半衰期时间递减。  **查询清洗**：拿 |
| 1835 | astrbot_plugin_simlife_world | 52 | personality | have | 一个运行在 AstrBot 上的长期生活模拟插件。角色拥有自己的日程、房间、穿搭和日常互动，主人可以通过面板进入她的家，陪她吃饭、看电视、健身、画画、出门兜风，也可以直接和她聊天。 |
| 1836 | astrbot_plugin_dailystory | 52 | other | watch | 读取当天群聊消息记录，以提问的用户为主角，调用 AI 生成一段并不生动也不有趣的短篇小故事。 |
| 1837 | astrbot_plugin_recall | 52 | memory | have | 引用机器人消息并回复"撤回"即可自动撤回被引用的消息。仅支持 OneBot v11 (aiocqhttp)。 |
| 1838 | astrbot_plugin_Grok2API Token | 51 | other | watch | 监控 Grok2API Token 号池状态，查看 Token 总数、正常/限流/失效数量及剩余配额 |
| 1839 | astrbot_plugin_ASCII | 51 | other | watch | 引用图片，插件将使用设定的字符内容绘制图片 |
| 1840 | astrbot_plugin_gemini-image | 51 | other | watch | 通过 gcli2api(gemini api) 对接 Gemini 生图/改图并发送到 QQ |
| 1841 | astrbot_plugin_ragflow_adapter | 51 | other | watch | 使用 RAGFlow 检索增强生成 |
| 1842 | astrbot_plugin_qq_email_verify | 51 | group-admin | have | 这是一个为 AstrBot 设计的 QQ 群入群验证插件。当新成员加入群聊时，插件会自动向其 QQ 邮箱（QQ号@qq.com）发送包含 6 位数字验证码的邮件。用户需要在规定时间内在群聊中发送正确的验证码以完成验证，否则将被自动移出群聊。 |
| 1843 | astrbot_plugin_nikke_news | 51 | personality | have | Blablalink官方消息推送、日常/收菜提醒、角色查询。 |
| 1844 | astrbot_plugin_lottery_enhanced | 51 | group-admin | have | 抽奖插件增强版，支持动态添加/删除奖品类目、群等级/身份限制、满人自动开奖、定时自动开奖、批量抽奖。 开启时清空重置，需先添加奖品才能参与，参与有实时反馈，可查询奖品/时间/人数/参加名单。 |
| 1845 | astrbot_plugin_kurumi_simulator | 51 | other | watch | 让 AI 在真实外汇行情中探索虚拟交易，带账户、日志与交易面板。联系 QQ 1756908053。 |
| 1846 | astrbot_plugin_qq_bind | 51 | other | watch | 双适配器绑定，让 QQ 官方机器人通过 OneBot 渠道确认用户真实 QQ 号 |
| 1847 | astrbot_plugin_qq_panel | 51 | other | watch | 管理 QQ 官方机器人的指令面板与单聊自定义菜单，在 WebUI 里配置、用管理员指令一键推送到开放平台。 |
| 1848 | astrbot_plugin_marvel_rivals | 51 | game | have | 面向 QQ 的漫威争锋国服查询插件，支持 UID 绑定、玩家战绩、时间窗口战绩回顾、常用英雄、跨赛季生涯绝活、相对弱势分析、最近对局、单局详情、第三方全局英雄环境及按赛季的历史洞察。 |
| 1849 | astrbot_plugin_lolmatch | 51 | info-push | have | 查询英雄联盟职业赛事（LPL/LCK/世界赛等）的赛程、赛果与单场数据，支持订阅联赛后每晚自动推送当日战报与次日赛程，可 @全体 或 @指定人提醒，并可按「工作日 / 休息日」限定可提醒时段。赛程、比赛摘要与单局详情均可渲染成图片卡片（选手 KDA、经济、伤害、天赋符文、召唤师技能、出装、BP、龙塔 |
| 1850 | astrbot_plugin_jx3box | 51 | payment | exclude | 查询魔盒物品详情 tip、成就链接、任务信息卡；支持关键词列表与 /1 连续选择。 |
| 1851 | astrbot_plugin_mihoyo_multi_sign | 51 | game | have | 面向 AstrBot 的米游社游戏每日签到插件。每位聊天用户独立绑定自己的米游社账号，支持扫码或 Cookie 绑定、多个账号、手动签到和自动推送。 |
| 1852 | astrbot_plugin_zhenxin | 51 | memory | have | 虚拟不代表冰冷，每一个ta都带着真心。 真心不换模型，只决定每一轮让模型看到什么。平时只带 3 条长期线索，出现“你还记得…”才翻旧记忆； 写记忆零 LLM 调用，线索放请求末尾、稳定前缀不动，缓存持续命中。 记忆按艾宾浩斯式周期分入周期池/珍藏池/浅忆池，零价值信息进回收池定期删除； 说话偏好只学 |
| 1853 | astrbot_plugin_points | 51 | platform | have | 测试版（Beta）\| 仍在测试的插件，可能存在 bug，请先在小范围群内试用， 勿直接在正式群大规模启用。功能：每日签到（连续加成/里程碑/日历）、 积分排行榜、周/月赛季榜与结算奖励（支持自动结算与通胀回收）、 积分抽奖（每日上限/自定义奖池/保底）、每日任务、发言赚积分、 成就系统、积分商店与兑 |
| 1854 | astrbot_plugin_feishu_docs | 51 | kb-rag | have | 飞书云文档管理、电子表格读写、知识库读取及用户授权 |
| 1855 | astrbot_plugin_ds_price_window | 51 | other | watch | 基于 DeepSeek 峰谷定价（2026-08-17 起），在每日高峰/低谷切换时刻（北京时间 09:00 / 12:00 / 14:00 / 18:00）向绑定会话推送"梁文锋时间 / 梁文谷时间"提醒。注意：使用前必须先发送 /dsbind 绑定当前会话，否则不会收到推送；支持 /dsnow  |
| 1856 | astrbot_plugin_human_life | 51 | other | watch | 让 Bot 像真人一样生活：定时推断当前在做什么，睡前写日记，周末写周记，聊天时把当前状态带入上下文。 |
| 1857 | astrbot_plugin_qzone_ext | 51 | personality | have | QQ空间说说管家：定时发说说、自动回评、可选主动互动；预存图/说说画师生成/LLM 动态画面描述，日期时间天气注入，群素材，说说画师/角色卡联动；默认 dry-run 预览。协议层移植自 Zhalslar（GPLv3）。 |
| 1858 | astrbot_plugin_Firefly_Blog_Manager | 50 | other | watch | 将 Firefly 博客的日常操作封装为 AstrBot AI Agent 可调用的工具。 |
| 1859 | astrbot_plugin_ImgBB_Subscriber | 50 | info-push | have | 这是一个用于AstrBot的插件，允许用户抓取指定 ImgBB 用户的公开相册图片，支持对订阅用户随机抓取,使用api_key上传图片到图床,以及通过 Cookie 访问受限内容。 |
| 1860 | astrbot_plugin_mcman | 50 | other | watch | 一个基于RCON协议的MC服务器管理器插件 |
| 1861 | desuwa | 50 | other | watch | 在机器人回复的每句话末尾加上 “desuwa” desuwa |
| 1862 | astrbot_plugin_mcmod_modsearch | 50 | other | watch | 本插件根据 wayzinx/httpposter 修改，用于查询爬取的 mcmod 内的模组与整合包，用法：/查mod mek或 /查整合包 GTNH |
| 1863 | astrbot_plugin_dogdiary | 50 | other | watch | 连续性舔狗日记，每日一记（可以生成临时日记） |
| 1864 | mai_sgin | 50 | game | have | 简单的舞萌出勤与退勤签到插件 |
| 1865 | astrbot_plugin_text_to_Image | 50 | other | watch | 更好看的文转图，基于外部api的二次元风格文转图，使bot以图片形式返回内容，将文本以图片的形式发送 |
| 1866 | astrbot_plugin_persona_router | 50 | personality | have | 按发言人 QQ 号强制切换人格：指定的人用主人格，其他人用默认人格 |
| 1867 | astrbot_plugin_novel_generator | 50 | personality | have | 一个基于 AstrBot Agent 的小说创作与管理插件，自主管理角色、大纲、章节等结构化数据 |
| 1868 | opencode_session_header | 50 | other | watch | 为指向 OpenCode（Zen / Go）端点的 LLM 请求自动注入 x-opencode-session 会话请求头。覆盖 Anthropic Compatible、OpenAI Compatible、OpenAI Responses、Gemini 四类 Provider 及 zen/infe |
| 1869 | astrbot_plugin_city_weather | 50 | info-push | have | 全国城市天气查询：直接说「上海天气」「北京天气预报」就能查实况和预报（高德天气 API），省/市/区县都能查 |
| 1870 | astrbot_plugin_native_vision_guard | 50 | media-parse | borrow | 为 AstrBot 的「原生看图」链路加一条安全带：当请求中的某个图片引用解析失败时 （典型情况是历史消息引用的本地缓存文件已被清理），只丢弃那一张图片， 而不是让整条请求被模型服务商拒绝。  **它解决的问题**  开启原生看图后，AstrBot 会把请求里每个图片块解析成 data URL。解析 |
| 1871 | astrbot_plugin_sender_tag | 50 | other | watch | 给进入会话历史的群聊消息加「昵称(QQ号): 」前缀，解决多人共用会话历史时 LLM 分不清谁在说话、上下文接续混乱的问题。标注随会话历史持久化，后续轮次依然有效；私聊默认不标注，可配置开关、是否带 QQ 号、昵称截断与分隔符。 |
| 1872 | astrbot_plugin_robomaster_assistant | 49 | other | watch | 提供 RoboMaster 规则手册检索、RM 官网公告监控和 RoboMaster 赛事状态通知。 |
| 1873 | astrbot_plugin_lark_richpost | 49 | platform | have | 飞书输出不支持markdown格式渲染，直接输出会导致丢失表格信息，这个插件是为了解决这个问题 |
| 1874 | astrbot_plugin_80lv | 49 | game | have | 80.lv 专业的游戏美术与开发技术资讯推送 |
| 1875 | github_star_manager | 49 | other | watch | GitHub插件Star管理器 - 智能点赞AstrBot插件 |
| 1876 | astrbot_plugin_pexels | 49 | other | watch | Pexels 精选图片插件，用于从 Pexels.com 获取高质量的免费精选图片。 |
| 1877 | astrbot_plugin_menstrual_cycle | 49 | kb-rag | have | 用真实的月经周期驱动角色的身体状态与情绪：五阶段推算、情绪向量、状态注入提示词，能被关心缓和、能自报疼痛、会识别周期不规律、会记得前两天也不舒服；注入按消息轻重给长短，短句不再被整张状态卡压着；文案可交给你的对话模型按周期重写，也可以每次实时现写，心情还能写进 Self Learning 与 Gro |
| 1878 | astrbot_plugin_persona_switch | 49 | personality | have | AstrBot 人设切换插件，支持通过命令快速切换预设人设，支持限制用户切换权限 |
| 1879 | astrbot_plugin_image_source_search | 49 | reverse-eng | exclude | 发张图或引用一张图，反查它出现在哪些网页上，结果按 X、Instagram、TikTok、微博等站点分好组发回来。支持 SerpApi 的 Google Lens 与反向图片，也能接任意自定义 HTTP 接口，需自备 API Key。 |
| 1880 | astrbot_plugin_llm_whitelist_plugin | 49 | other | watch | 只允许指定群聊使用 LLM 聊天，白名单用户无视群组触发 LLM ,同时保留 / 指令。 |
| 1881 | astrbot_plugin_breeze_tts | 49 | tts | watch | 对接 Breeze Blue 语音合成服务，支持克隆音色与自然语言风格指令（instructions）。  两种用法： 1. 独立使用：模型可调用 `breeze_tts_speak` 工具把一句话合成语音发出，也可以用 `/breeze 文字` 手动测试。 2. 作为 private_compan |
| 1882 | astrbot_plugin_quiet_hours | 49 | other | watch | 按固定的每日时间段暂停 Bot 的非管理员回复：静默期内管理员照常使用， 其他用户尝试触发时会收到一条可编辑的提醒（含下一次开放时间）。 支持 WebUI 可视化管理多个静默方案、管理员按群临时豁免、一次性单独静默。 拦截发生在消息入口、LLM 请求和发送前三层，不会消耗模型 token。 |
| 1883 | astrbot_plugin_adguard | 49 | group-admin | have | QQ 群广告检测插件。检测文字/图片/视频中的广告内容，支持撤回、禁言、踢人多级处置，内置二次人工审核与学习，可接入智谱 GLM-4V-Flash 免费视觉模型。 |
| 1884 | astrbot_plugin_heweather | 49 | info-push | have | 查询和风天气预报、空气质量和预警信息，使用 Typst 渲染天气卡片 |
| 1885 | astrbot_plugin_identity_guardian | 49 | group-admin | have | 凝心溯溪系列身份模块。动态识别 bot、发送者与目标身份及关系，向 LLM 注入受控行动边界， 并提供自助动作、互动反应、群信息管理和按 Bot/群隔离的自动与人工入群审核能力。 |
| 1886 | astrbot_plugin_constellation | 48 | game | have | 发送星座名返回对应运势（文字） |
| 1887 | astrbot_plugin_group_sum_ai | 48 | other | watch | [仅 gewechat]可以配置指定群聊或对话人，配置自动总结数量，间隔等等，实现自动根据配置总结群友发言，省的海量无用信息浪费时间 |
| 1888 | astrbot_plugin_api_video_parser | 48 | media-parse | borrow | 需自建 parse-video-py 后端服务配合使用（部署见 README，后端仓库 https://github.com/baige778/parse-video-py）。 解析短视频/图集分享链接并发送直链内容，支持 27 个平台，每个平台可独立开关。 自动获取视频/图集直链直接发送，视频已删 |
| 1889 | astrbot_plugin_wow | 48 | personality | have | 魔兽世界综合插件：WCL 战绩、角色卡、榜单、BIS、词缀、日历、公会、开箱、语录、新闻、重置提醒、宠物对战预警、节日通告等 18 个功能整合。指令裸词即可触发，/ 前缀可省略。 |
| 1890 | astrbot_plugin_webhook_notifier | 48 | platform | have | 将 Oh My Pi、OpenCode 等 Coding Agent 的任务完成／待处理事件及通用 Markdown 消息，以文本或 HTML 卡片推送到 QQ 私聊或普通 QQ 群。 |
| 1891 | astrbot_plugin_boot_animation | 48 | other | watch | 在 AstrBot 管理面板加载时自动播放非官方风格代码动画或按需下载的视频，支持随机模式及单段/双段视频。 |
| 1892 | astrbot_plugin_panshi | 48 | group-admin | have | 稳如磐石的 QQ 群管家。默认调用 AstrBot 里已配置的对话模型来理解群友的口语化指挥，并用「意图闸门」把闲聊挡在模型之外（上下文佐证 + 效果动词 + 否定检测 + 每群信用额度），只在该花 token 的时候才花；本地规则快通道与兜底保证无模型时常用指令照常可用。集基础管理、反垃圾风控、智 |
| 1893 | astrbot_plugin_xiaoyu_doodle | 48 | other | watch | 让鲸小鱼亲手画涂鸦——不经过任何生图模型，她给出坐标、程序照笔迹渲染；画过的都进画册，可网页查看/编辑/导出。想要拍照请另装「鲸小鱼相机」扩展 |
| 1894 | astrbot_plugin_astro_painter | 48 | image-gen | watch | 给 AstrBot 接上任一生图模型（OpenAI Images 协议 / Chat Completions 协议均可），只做静态图片。  三种触发方式，保证「想画图」不会漏： - 自然语言：说「帮我画一只橘猫」「生成一张赛博朋克风的海报」直接出图 - 指令：/画图、/生图、/draw、/画画 -  |
| 1895 | astrbot_plugin_astral | 48 | memory | have | Bot 将会记住群里的人和事：谁爱聊什么、约定过什么、上次说到哪儿—— 换个群也不失忆，说话像同一个人。所有平台、所有群共用同一份记忆， 基于 Markdown，你随时能打开看、直接改。 还能用 /astral commit 存档、/astral recover 回退。 开发版本为 4.29.4，其 |
| 1896 | astrbot_plugin_aiva | 48 | game | have | 扫码绑定掌上无畏契约账号后，读取玩家自己的段位与战绩数据，交给大模型做锐评和玩家画像。 |
| 1897 | astrbot_plugin_tts_emotion_tags | 48 | tts | watch | LLM 回复注入 TTS 表现标签并剥离 QQ 文本标记 |
| 1898 | astrbot_plugin_server_monitor | 48 | other | watch | 监测 AstrBot 部署服务器的系统状态与工作目录情况，输出 wakaba_dark 风格图片 |
| 1899 | astrbot_plugin_chat_history_archiver | 48 | sticker | borrow | 通过 NapCat / SnowLuma（OneBot v11 扩展 API）将历史聊天记录（群/私聊）导出为 JSONL 文件，图片/表情等用占位符替换；支持定时循环增量导出、按需回溯归档、多 bot（多 aiocqhttp 实例）独立归档与后端自动探测 |
| 1900 | astrbot_plugin_command_help | 48 | other | watch | 给机器人加一个统一的指令查询入口：发送「/指令大全」（别名 /帮助、/指令帮助、/指令列表）后， 自动抓取所有已加载插件的指令（含指令组、子指令、别名、必填/可选参数、权限角标）， 在本机用 Pillow 渲染成一张卡片图发送。不依赖远端 T2I 渲染服务，离线也能出图。 |
| 1901 | astrbot_plugin_video_chat | 48 | media-parse | borrow | 自动理解直发视频与抖音/B站链接，优先原生视频直传（含音频），回退抽帧，支持字幕/语音、高赞评论回复和视频上下文限额 |
| 1902 | astrbot_plugin_eggSearch | 47 | other | watch | 输入尺寸和重量，给出符合的精灵种类 |
| 1903 | astrbot_plugin_text_renderer | 47 | other | watch | 文本文件生成图片 |
| 1904 | astrbot_plugin_tally | 47 | other | watch | 支持多用户数据隔离的记录、扣减、表格导出插件， 适用于库存管理、每日打卡、积分统计等场景。 导出文件自动上传至远程服务器，生成带密码的下载链接。 |
| 1905 | astrbot_plugin_quick_switch | 47 | tts | watch | 模型·人格·TTS·STT·识图 一键切换 |
| 1906 | astrbot_plugin_word_filter | 47 | other | watch | 自动过滤包含屏蔽词的消息，支持管理员动态管理屏蔽词列表 |
| 1907 | astrbot_plugin_perf_guard | 47 | other | watch | AstrBot 性能守护：诊断回复慢的原因（事件循环卡顿定位到具体插件、消息响应耗时统计），监测"不回话"类故障（别的插件报错点名、模型调用失败率、插件加载失败、磁盘余量、数据库体积），并提供一键体检与内存释放、日志清理、内存超阈值/定时重启。自身常驻开销约 0.004% 单核，只在 AstrBot |
| 1908 | astrbot_plugin_nai_plus | 47 | personality | have | 通过 Nai2API 网关调用 NovelAI 生成图片。支持 /nai 指令和 LLM 工具调用， 内置 NovelAI V5 模型、提示词直译（中文/英文自动转英文标签）、 按模型区分扣点与高扣点二次确认、自定义命令名。 OpenAI 兼容直译接口独立配置地址与密钥，模型可从接口实时拉取下拉选择 |
| 1909 | astrbot_plugin_botguard | 47 | other | watch | 自动识别群里的其他机器人/AI：多维行为画像 + 可选大模型兜底判定，在 LLM 请求前直接掐断，不烧 token；回复时剥掉指向对方的 @ 和引用，从源头断链；再按「连续来回轮数」熔断。真人说话立即恢复，管理员永不误判。 |
| 1910 | astrbot_plugin_today | 47 | personality | have | 她自己的今天。工作日偏学校、周末偏家里，每天按时间段生成一两件「发生在她身上的小事」， 事件之间带因果（起晚了 → 没吃早饭 → 中午吃太急），跨天连续（昨天没写完的作业今天还挂着， 阳台的月季会一天天开）。每件事带「让你现在怎样」的影响，语气会跟着变。 有冷却和概率，都不提也没关系；被问「在干嘛」 |
| 1911 | astrbot_plugin_android_spy | 47 | other | watch | 通过 Veglia Android 客户端截图回传，让大模型查看安卓手机屏幕、查询前台 App 活动，以及将 App 唤回前台。 |
| 1912 | astrbot_plugin_blackjack21 | 47 | group-admin | have | 群聊21点小游戏：创建房间、加入、同步回合要牌/停手。 每个群独立一间房；每轮限时，超时视为停手；创建后超时未开局自动关房。 结算时本局第一免禁言，其他人按与第一名的点数差禁言。 支持 /21点帮助 查看牌值规则；可选启用小丑模式（小王拆最小牌 / 大王拆最大牌，并解除停牌）。 需要 aiocqht |
| 1913 | astrbot_plugin_street_tracker | 47 | other | watch | 通过 Buckler 查询 Street Fighter 6 玩家档案与对战统计 |
| 1914 | astrbot_plugin_galgame_friend | 47 | personality | have | 把已绑定的 QQ 私聊好友变成 galgame 场景：好友发来消息时，页面上会出现立绘、 对话框和三条 AI 生成的回复候选；每条候选带不同的策略角度与好感度增减， 点一条就直接发给对方。支持共享的角色/背景素材库、按情绪标签自动切换立绘、 好感度上限 100、过往聊天记录浮窗。自带一套示例立绘与背 |
| 1915 | astrbot_plugin_garmin_health | 46 | other | watch | 佳明健康看板 - 为 AstrBot 提供 Garmin 健康数据查询能力。通过 Garmin Connect 官方接口，支持心率、睡眠、步数、活动、跑量等数据的自然语言查询，让 Bot 在对话中快速获取和展示你的运动健康信息。 |
| 1916 | astrbot_plugin_tsserver_relay | 46 | other | watch | TeamSpeak 3 服务器监控 - 实时推送用户进出、服务器状态到群消息 |
| 1917 | model_mcp_bridge | 46 | other | watch | 用于为不支持tool_use的模型提供一个调用MCP的途径的插件。 |
| 1918 | Trans | 46 | other | watch | 哦齁噢喔～语翻译器，基于https://msbt.seku.su提出的的编码解码功能 |
| 1919 | astrbot_plugin_cmd_console | 46 | other | watch | 提供 WebUI 的指令管理面板，可以启用/禁用插件的指令。 |
| 1920 | astrbot_plugin_antigravity_acp | 46 | other | watch | 免反代、免 API Key：通过官方 AGY CLI（ACP）接入 Gemini，支持思考、工具与图片输入（需自备 CLI）。 |
| 1921 | astrbot_plugin_chat_dynamics | 46 | memory | have | 群间（Chat Dynamics）是 AstrBot 群聊互动插件。 合并连续碎发，结合引用、@ 与上下文追踪话题，控制回应时机和回复节奏。 可切换规则＋原生重排序或普通 LLM 判断对话对象和讨论归属，允许同一人参与不同讨论。 可切换 AstrBot 原生抉择（Jev / System One / |
| 1922 | astrbot_plugin_reply_length | 46 | other | watch | 为 AstrBot 提供可配置的回复篇幅建议，并在明显超长时进行一次语义压缩。 |
| 1923 | astrbot_plugin_359_debug | 46 | devtools | watch | 一键AI智能诊断运行时性能、Token 用量、上下文、工具调用、日志、插件冲突与会话锁阻塞风险，附带可视化Dashboard |
| 1924 | astrbot_plugin_smartsearch_fallback | 46 | other | watch | smartsearch_fallback 为 AStrBot 提供"优先引擎 + 兜底引擎"的智能搜索编排能力：默认优先 bocha，失败或结果不足时自动切换 anysearch 补足，并对两路结果做 URL 归一化交叉验证，输出带来源标记的高质量搜索结果。优先/兜底引擎均可配置为任意搜索方式（内置 |
| 1925 | cninfo_hedge | 45 | info-push | have | CNInfoHedgeCrawler 是基于巨潮资讯的 A 股上市公司公告爬取工具，支持任意关键词搜索、日期范围过滤、PDF 批量下载和企业微信推送。 |
| 1926 | astrbot_plugin_x_score | 45 | other | watch | 查询 X/Twitter 账号可信度评分，基于 AI 分析账号真实度、风险标签与评价 |
| 1927 | astrbot_plugin_gta_online_helper | 45 | other | watch | GTA 线上数据查询，组队寻找 |
| 1928 | astrbot_plugin_fetch_summary | 45 | other | watch | 根据 URL 获取网站摘要 |
| 1929 | astrbot_plugin_timeline | 45 | other | watch | 一个非常简单的插件，在请求中插入当前时间 |
| 1930 | astrbot_plugin_guijishiping | 45 | other | watch | 硅基流动api视频，可以制作动态壁纸之类的 |
| 1931 | EmailNotixion | 45 | platform | have | 实时IMAP邮件推送插件 |
| 1932 | astrbot_plugin_chouqunyou | 45 | other | watch | [仅 napcat] 在QQ群随机抽取一个群友 |
| 1933 | httpposter | 45 | other | watch | HTTP请求工具 |
| 1934 | anti_withdrawal | 45 | group-admin | have | [仅支持微信] 防撤回插件，目前只支持微信私聊群聊的文本消息，将撤回的消息记录并发送给设定的人 |
| 1935 | astrbot_plugin_meirixiaozhu | 45 | other | watch | 抽取属于自己的每日小猪，稀有度卡面 + 图鉴排行 + 关键词与艾特唤醒可热改 |
| 1936 | astrbot_plugin_system_status | 45 | other | watch | 生成系统状态卡片和资源监控图表，展示 Bot 运行状态、硬件资源、网络与磁盘使用情况。 |
| 1937 | astrbot_plugin_custom_entertainment | 45 | proactive | watch | 群娱乐合集：接口系统（图片/视频/文本）+ 每日运势 / 今日老公 / 今日人品 + 早安晚安打卡与排行 + Minecraft 版本检测 + 电脑状态与定时推送 + 每日读报 + 自定义词库与戳一戳回复 + 每日签到 / 偷积分 / 银行 / 保险箱 / 坐骑商店 / 打工 / 体力 + 宠物系统 |
| 1938 | astrbot_plugin_upload_Fast_Profile_Management | 45 | personality | have | 功能全面的人格管理器：双语命令，支持人格增删改查、复制重命名、导入导出、文件夹、会话对话管理、统计与 LLM 辅助生成，并支持插件页面配置与权限控制。 |
| 1939 | astrbot_plugin_pjsk_wordle | 45 | game | have | PJSK 音乐游戏猜曲 Wordle：根据曲名/上线时间/分类/作者/BPM/MASTER/APPEND 的属性反馈锁定目标曲目，支持日服/国服题库切换 |
| 1940 | astrbot_plugin_chase_bot | 45 | other | watch | 监听群聊消息，当发送者 ID 命中配置的目标时，唤醒 Bot 走正常事件管线自动回复， 并在 LLM 请求里注入一段可编辑的「怼人提示词」。支持多个目标 ID、多个群、冷却时间， 全部可在插件页面里配置。 |
| 1941 | astrbot_plugin_pic_search | 45 | other | watch | 给 LLM 一个 `search_image` 工具：按关键词**正向搜图**（文字 → 图片），把图片直接发送到会话。  - **零配置可用**：默认使用 Bing 图片搜索，不需要任何 API Key - **三种图源**：Bing（画质高，默认）/ 360（响应快）/ 自定义 JSON 接口（ |
| 1942 | astrbot_plugin_keyword_reply | 45 | other | watch | 监测到指定内容就发送指定内容，可附带本地图片或网络图片，带冷却时间防止刷屏；支持包含/精确/正则匹配、群聊与私聊开关、群与用户的白名单/黑名单触发范围 |
| 1943 | astrbot_plugin_lifefrequency | 45 | other | watch | 给机器人一份持续的小生活（LLM 决定作息活动、情绪体力、身体、日期节日、按 Token 计价的经济），并按生活状态决定群聊自动回复的频率：睡觉时不回话，感冒时话少，攒了素材会主动开口。移植自 MaiBot 插件 orge-8/life-frequency。 |
| 1944 | astrbot_plugin_mementy | 45 | memory | have | 基于艾宾浩斯遗忘曲线（SM-2 间隔重复算法）的 Agent 长期记忆插件。记忆会在到期时自动注入到 LLM 上下文，重要信息按科学节奏被反复强化，避免遗忘。 |
| 1945 | astrbot_plugin_voicevox | 44 | tts | watch | 基于VOICEVOX Engine的日语文本转语音插件 |
| 1946 | astrbot_plugin_parserurl | 44 | media-parse | borrow | 多平台链接解析并发送内容，同时支持订阅用户有更新主动推送新内容 |
| 1947 | astrbot_plugin_Pic | 44 | other | watch | 一款基于栗次元等 API的随机看图插件。 改自https://github.com/ttq7/astrbot_plugin_Lolicon |
| 1948 | astrbot_plugin_chatlog_webui | 44 | other | watch | 以聊天窗口 WebUI 形式展示全平台（用户+机器人）对话记录，调用 astrbot_plugin_message_recorder 的查询 API；支持免认证独立端口、Dashboard 插件页面、聊天媒体持久化与机器人消息记录 |
| 1949 | astrbot_plugin_dorm_power | 44 | other | watch | 完美校园（智能水电）宿舍电量查询与定时播报。多用户各自 /电量绑定 学校代码+账号，自动列出房间并按序号或房间号关键字增删；每日定时群播报，剩余电量与掉电速率双预警；账号与房间信息加密落盘、日志脱敏；搜校带限速与熔断防风控；接口地址、命令名、字段名都可在面板覆盖。 |
| 1950 | astrbot_plugin_signin | 44 | game | have | 完整的积分体系插件：每日签到（带连续奖励）、积分查询、转账、排行榜、补签、可配置奖池抽奖。数据可由管理员任意调整，支持一键清零，全部流水可追溯。 |
| 1951 | astrbot_plugin_russian | 44 | game | have | 群聊俄罗斯轮盘决斗小游戏：装弹、轮流开枪、金币赌注、每日签到与排行榜。移植自 HibiKier/nonebot_plugin_russian |
| 1952 | astrbot_plugin_genshin_info | 44 | info-push | have | 查询米游社原神官方资讯（公告/活动/资讯），支持查看详情与订阅定时推送。 |
| 1953 | astrbot_plugin_qq_official_v2adapter | 44 | other | watch | 基于 QQ 官方 V2 API 实现的消息平台适配器。 |
| 1954 | astrbot_plugin_daily_music | 44 | memory | have | 让 Bot 每天在用户设定的时间段（默认 13:00-14:00、18:00-21:00）里"自己去听歌"：按自己的性格设定挑一个歌单主题，到指定平台（默认汽水音乐，支持 QQ音乐、网易云）找歌听，按时长（默认 5 分钟）或首数（默认 3 首）计算听歌量；听完由大模型为每首歌写一句听后感，连同听歌记 |
| 1955 | astrbot_plugin_sl_status | 44 | other | watch | 发送 状态（别名 sl / st / 运行状态）生成整幅插画背景的系统状态卡：CPU / RAM / DISK 三条百分比进度条，另含 CPU 型号与线程数、今日 token 消耗、当前会话上下文、对话模型、插件数、协议端版本与运行时长。字段可在面板逐项开关，背景可在 assets/bg/ 放多张随 |
| 1956 | astrbot_plugin_think_mode | 44 | other | watch | 控制 Ollama 模型的思考模式，支持 `/think` 和 `/no_think` 命令切换，默认为非思考模式。  v1.1.0 适配 AstrBot 4.27+：用 OpenAI 标准 `reasoning_effort` 字段（替代老版 Ollama 私有 `think` 字段），同时保留对 |
| 1957 | astrbot_plugin_dst_only | 44 | other | watch | 仅允许 Tavily 允许在允许的域名进行搜索 |
| 1958 | astrbot_plugin_tts_by_length | 44 | memory | have | 短句开口说，长文发文字。按回复长度自动选择语音或文字，朗读时过滤链接、代码、表情符号和 @。v2.0 新增语音记忆：让大模型知道自己发过什么语音，被人引用时认得出是哪一句。 |
| 1959 | astrbot_plugin_anti_laowu | 44 | other | watch | 防止机器人与机器人之间的高强度互动，支持按账号、群配置冷却、连续互动上限与暂停时间。 |
| 1960 | astrbot_plugin_token_usage | 44 | other | watch | 按本地接收时间记录Token、缓存与分时费用，支持DeepSeek高峰空闲计价、QQ卡片和OAuth识图上报 |
| 1961 | astrbot_task | 44 | memory | have | 管理日常活动、具有长期记忆功能的插件 |
| 1962 | astrbot_plugin_quote_text | 44 | other | watch | 把被引用消息的原文补进上下文，避免AI只看得到“回复了某条消息” |
| 1963 | astrbot_plugin_Robomaster_Information | 43 | other | watch | RoboMaster 官方论坛里经常会出现开源项目、技术资料、规则讨论和赛季通知。为了更方便地获取论坛的近实时消息，本插件通过 AstrBot 定时监控论坛文章页，在发现新文章后自动抓取详情页正文，调用 AstrBot 当前配置的大模型生成技术摘要，并推送到指定 QQ 会话。 |
| 1964 | astrbot_plugin_fitness | 43 | other | watch | 智能健身教练插件 - 个人档案建立、训练计划生成、每日打卡提醒、动态调整与补剂饮食跟进 |
| 1965 | Volcengine-text-to-engine | 43 | image-gen | watch | 通过http的方式请求火山豆包接口返回生图结果，不采用sdk方式，避免库包安装失败的问题 |
| 1966 | doro_ending | 43 | other | watch | [QQ]doro互动故事 |
| 1967 | astrbot_plugin_aliyun_censor | 43 | group-admin | have | 为bot启用阿里云内容安全审核 |
| 1968 | astrbot_plugin_vram_switcher | 43 | tts | watch | 为本地 AI 陪伴 / AstrBot / DSH 协调 LLM、IndexTTS 与 ComfyUI 的显存，按需停启。 |
| 1969 | astrbot_plugin_douyin_nahida | 43 | media-parse | borrow | 自动识别抖音链接，去水印下载视频和实况照片动图，动图转MP4并拼接，保留作品音乐（依赖 f2 生成签名） |
| 1970 | astrbot_plugin_paper_plane | 43 | other | watch | 让 Bot 帮你在私聊里给指定的人传话 |
| 1971 | astrbot_plugin_winremote | 43 | other | watch | 远程操控连接器：桥接 AstrBot 与远程电脑 App，通过 AI 工具实现远程执行指令。；原作者 silver-wolf-little-wife 的 Cherry Remote 改名延续版 |
| 1972 | astrbot_plugin_t2i_hub | 43 | image-gen | watch | 基于astrbot_plugin_txsc二开的AstrBot文生图插件，支持了模型用完免费额度就自行切换的功能，可以很方便的白嫖千问平台的新人试用福利。 同时增加了自定义唤醒词与副脑优化提示词这两个实用功能，让文生图功能更加易用。 |
| 1973 | astrbot_plugin_petlink | 43 | other | watch | 为 PetLink 桌宠客户端提供远程对话接口：把桌宠的文本请求转发到 AstrBot OpenAPI，并把 SSE 原样回传。桌宠只持有可吊销的设备令牌，拿不到上游 API Key。 |
| 1974 | astrbot_plugin_readingsteiner | 43 | memory | have | 基于 EverOS 自进化记忆引擎的 AstrBot 长期记忆插件（持久用户画像 + 按平台真实身份硬隔离） |
| 1975 | astrbot_plugin_drift_bottle | 43 | other | watch | 漂流瓶插件 - 支持捡瓶子、投瓶子（文字+图片）、查看统计。使用QQ昵称作为用户标识，保护隐私。 |
| 1976 | astrbot_plugin_tarkov_info | 43 | other | watch | 逃离塔科夫信息检索：物品物价（跳蚤/商人）、物品用途（任务/兑换/合成/藏身处）、任务查询（目标/奖励/前置）、中英文双向搜索，附带 Web 可视化面板 |
| 1977 | astrbot_plugin_history_kb | 43 | kb-rag | have | 将历史对话自动向量化存入名为"历史对话"的知识库，支持语义检索，仅 BOT 管理员可用，自带嵌入模型。 |
| 1978 | astrbot_plugin_yurisaki_bridge | 43 | other | watch | 非官方第三方 AstrBot 插件，通过受控工具接口查询 Yurisaki 的 Arcaea 曲目信息和随机曲目。支持 aiocqhttp/NapCat，已完成离线测试和真实环境联调。 |
| 1979 | astrbot_plugin_reply_cleaner | 43 | personality | have | 清理模型回复中不该出现的内容：去掉开头的「……」等标记、去掉 <think> 类思维链标签、去掉零宽字符、可选的重复标点合并与自称前缀清理。只在纯文本模型回复上生效，不改人格提示词，清理后为空会自动还原。 |
| 1980 | astrbot_plugin_bilibili_analysis | 43 | media-parse | borrow | Bilibili 小程序/视频链接解析，支持完整链接、b23.tv 短链、独立 BV/AV 号与 QQ 分享卡片四种来源，可分别开关指定来源，可合并发送视频简介、视频文件。基于 koishi-plugin-bilibili-videolink-analysis 项目进行移植与修改。 |
| 1981 | astrbot_plugin_cucumber_rvc_console | 43 | tts | watch | 说一句「翻唱《歌名》」就自动取歌、切副歌、RVC 变声、混音发回群聊；支持 TTS 人格变声与 WebUI 全套管理（配合 cucumber-rvc-gateway 网关） |
| 1982 | astrbot_plugin_xbox | 42 | game | have | 获取微软 Xbox Game Pass 最新入库游戏列表，支持后台定时推送新游提醒和手动查询。 |
| 1983 | astrbot_plugin_inaturalist_search | 42 | other | watch | 一个基于 iNaturalist API 的 AstrBot 插件，支持物种分类信息查询和观察记录搜索。 |
| 1984 | astrbot_plugin_mirage | 42 | other | watch | [仅 qq] 幻影坦克制作 |
| 1985 | astrbot_plugin_geminiexp | 42 | other | watch | 让你在 AstrBot 调用 Gemini2.0-flash-exp 来生成图片或者 P 图。Gemini2.0-flash-exp为原生多模态模型，其既是语言模型，也是生图模型，因此能够对图像使用简单的自然语言命令进行处理。 |
| 1986 | astrbot_plugin_turnflow | 42 | group-admin | have | 私聊对话轮次管理：动态消息收集、未完成回复中断、部分输出撤回与历史回滚保护。 |
| 1987 | astrbot_plugin_group_cloud_storage | 42 | group-admin | have | QQ 群原生云存储（群文件 / 群相册 / 精华消息）统一管理插件。支持群文件浏览、搜索、上传下载，相册图片/视频浏览，精华消息长文保存与分段，OpenList 网盘双向转存，任务记录与进度管理，多群批量管理，提供 WebUI 管理面板。 |
| 1988 | astrbot_plugin_model_manager | 42 | other | watch | 统一管理所有插件的 LLM 模型配置，支持单独替换、一键设置、插件排序、侧边栏导航、中英文切换。 |
| 1989 | astrbot_plugin_whale_token | 42 | other | watch | 鲸元券（WHALE-YUAN TOKEN）票面查看插件：把虚构货币「鲸元券」的六档票面图打包进来， 按面额返回对应票面，供聊天中展示。  ## 指令 - `/鲸元券`（不带参数）按后台配置的「默认面额 / 默认票面」发送，无需输入金额 - `/鲸元券 <面额>` 发送该面额票面正面，如 `/鲸元券  |
| 1990 | astrbot_plugin_anuneko | 41 | other | watch | 基于 anuneko.com 的 AI 对话插件，支持橘猫/黑猫模式切换 |
| 1991 | keyword_monitor | 41 | other | watch | 当群里出现关键词时触发自动提醒。 |
| 1992 | astrbot_plugin_quarksave | 41 | other | watch | 调用quark-auto-save实现自动转存资源到自己的夸克网盘 |
| 1993 | astrbot_plugin_gemini_tts | 41 | tts | watch | 基于谷歌 Gemini 3.8 纯真 TTS 引擎打造的极速语音合成插件，支持专属 Voice ID 与极低延迟 |
| 1994 | astrbot_plugin_netease_pick | 41 | media-parse | borrow | 把网易云的歌曲链接发（或引用）给机器人，它就把那首歌下载下来，以 mp3 文件 + 语音两种形式发到群里。 走官方外链直链（零依赖、免 key、免登录），支持四种形态：@ 机器人直接发链接、引用纯文本分享、 引用 QQ 音乐卡片、引用 App 分享短链（先跟随 302 拿歌曲 id）。 |
| 1995 | astrbot_plugin_nickname_monitor | 41 | other | watch | 监听群成员修改群昵称(群名片)事件,并发送播报消息 |
| 1996 | astrbot_plugin_pindouba | 41 | other | watch | 可以将喜欢的图片拼成豆，还可以拼群友玩，并且提供拼豆材料清单服务 |
| 1997 | astrbot_plugin_send_tool | 41 | other | watch | 高级消息代发工具 |
| 1998 | astrbot_plugin_manager | 41 | other | watch | 插件管理，支持插件搜索、安装、卸载、重载、开关、更新、来源绑定、清单分享，以及插件的选择性备份与迁移，提供易用的插件页面。 |
| 1999 | astrbot_plugin_group_backup | 41 | other | watch | 备份 QQ 群成员、群公告、群精华、群相册等数据，支持导出恢复及群员召回。 |
| 2000 | astrbot_plugin_no_say | 41 | other | watch | 在后台指定会话后，机器人在这些聊天里不回复：@、关键词、LLM、主动插话都不会发出去。支持「全部静音」一键静音所有会话。 |
| 2001 | astrbot_plugin_sleep_guard | 41 | other | watch | 真正的静默休眠：/sleep 后 bot 对一切消息零输出（连确认都不发），/wake 唤醒。任何人可触发，状态持久化，重启不丢。 |
| 2002 | cngal_morning_report | 40 | game | have | CnGal 每日晨报 |
| 2003 | astrbot_plugin_QQgal | 40 | game | have | 简单的Galgame |
| 2004 | astrbot_plugin_holdem_poker | 40 | game | have | 修改自 w33d 的德州扑克。原插件仅支持微信，现支持 QQ 群。此外增加了每轮下注上限金额，为小盲注的10倍，可自行调整或删去 |
| 2005 | file_transfer | 40 | other | watch | 把本地文件发到 QQ 会话，自动保存收到的文件并查看内容；支持 NapCat(aiocqhttp) 与 QQ 官方机器人(qq_official)，提供可操作 WebUI 管理页（文件上传/重命名/删除、审计清空、配置修改）、SQLite 索引与哈希去重、操作审计、传输重试/并发/限速、工作区配额与 |
| 2006 | chat_memory | 40 | memory | have | 合并存储式对话存档：一条物理消息只存一份，多个 BOT 共享同一份事实，各自视角（谁发的、属于哪轮、什么状态）单独记。可选接管上下文（按轮 / 跨会话 / 整群 / 按 persona，工具调用一并回放），自带只读查询台（检索、工具调用、媒体回看、数据库体检）。 |
| 2007 | astrbot_plugin_orbit_command | 40 | other | watch | 把会越攒越多的东西定期扫掉：停用插件的内存、NapCat 的图片与文件缓存、 NapCat 协议缓存、AstrBot 临时文件与日志、插件目录垃圾，以及你指定目录里的 过期媒体文件。除清理外还管三件维护事：重复 Bot 检测（连不上也能查出来）、 插件数据残留与数据库增长观测、插件模块三态回收。 面 |
| 2008 | astrbot_plugin_volcengine_provider | 40 | tts | watch | 别让你的 AI 在 QQ 里只会看字。QQ 语音会在可靠转换后，连同完整聊天上下文交给你正在使用的火山方舟主模型；本轮发送或引用的视频，也能由同一个模型看懂并继续回应。你无需另配 STT、转录模型或第二套对话流程。插件同时提供普通 API 与 Agent Plan 两张独立供应商卡，让音视频请求沿  |
| 2009 | astrbot_plugin_qq_recall | 40 | memory | have | 适配 NapCat / LLOneBot 等 OneBot v11(aiocqhttp) 协议端的引用撤回插件。  用户**引用（回复）机器人的某条消息**并发送「撤回」，即可撤回被引用的那条消息。 引用机器人的消息本身就能唤醒机器人，**不需要 @**。 撤回成败完全以 QQ 服务端返回为准，失败 |
| 2010 | astrbot_plugin_sanqi_talk | 40 | other | watch | 三月七语句插件 - 随机输出崩坏星穹铁道中三月七的经典台词，该插件从旧版仓库，迁到新版仓库，所以更名了 |
| 2011 | astrbot_plugin_toolkit | 40 | sticker | borrow | 四合一插件：图片问答桥接（小米→百度→OCR 三级识别）+ 每日简报（天气/昨日新闻/科技医药政策前沿/GitHub 日升榜）+ 主动消息门禁与每日人格消息 + AI 表情包回复 |
| 2012 | astrbot_plugin_group_wake_prefix | 40 | other | watch | 本插件可通过指令在不同群聊自定义不同唤醒词，解决群聊众多机器人唤醒词重合导致一呼百应的问题。 |
| 2013 | astrbot_plugin_join_verify | 40 | group-admin | have | 进群验证插件，新成员入群需回答算术题验证，支持群自定义配置和二级管理员审批 |
| 2014 | astrbot_plugin_shoubanhua | 40 | image-gen | watch | 支持第三方所有OpenAI绘图格式和原生Google Gemini 终极缝合怪，文生图/图生图/人设写真，搭载Neo-Brutalism管理后台、高可用故障转移与画廊管理 |
| 2015 | astrbot_plugin_custom_commands | 40 | other | watch | 在 WebUI 中自定义注册指令并固定回复，可被 QQ 菜单面板插件读取同步到 / 指令面板 |
| 2016 | astrbot_plugin_jev_radar | 40 | devtools | watch | Jev 意图雷达基于 TypeSafe SystemOne（Jev）的 typed decision 能力，把群聊/私聊消息 实时判定为「意图标签 + 情绪倾向 + 风险等级 + 置信度」，帮你看懂消息背后的真实意图。  特性： - 被动模式：自动监听消息判定，仅当「低置信 / 高风险 / 关注意图 |
| 2017 | astrbot_plugin_report_generator | 40 | other | watch | 喜报 / 悲报图片生成插件，支持 Emoji 渲染、群组黑白名单过滤及用户 ID 限制。 |
| 2018 | astrbot_plugin_bili_dynamic | 40 | media-parse | borrow | 全局监控 B 站 UP 主动态，按会话订阅关系推送。QQ 官方机器人原生 Markdown 排版（图文/视频/转发/专栏等卡片模板），支持置顶动态特殊处理与接口自动降级。 |
| 2019 | astrbot_plugin_weather | 40 | info-push | have | /天气 地点 查询今天与未来 3 天天气，数据来自 Open-Meteo，免费无需 API Key |
| 2020 | astrbot_plugin_fortune_wheel | 40 | group-admin | have | 抽奖禁言插件：/大礼包 弹出动态轮盘随机禁言！  功能特性： - 轮盘抽奖：/大礼包 弹出动态轮盘，按权重随机抽取禁言时长 - 自定义范围：/大礼包 5-30 指定禁言区间 - 投票解禁：普通用户发起解禁投票，群友 /同意 /不同意 表决 - 诅咒系统：设置诅咒，下次抽奖触发权重加成；可转移给他人， |
| 2021 | astrbot_plugin_lofter | 39 | media-parse | borrow | 解析 Lofter 链接，订阅 Lofter 标签/博主，搜索 Lofter 内容，支持标签表达式统计 |
| 2022 | qftp | 39 | other | watch | 一个基于 astrbot 的文件管理插件，支持文件下载、搜索等功能。只在napcat+linux下尝试 |
| 2023 | astrbot_plugin_no_dragon_lord | 39 | other | watch | anka - 禁止机器人抢龙王! 龙王一定要是人类 ✍️✍️✍️✍️✍️✍️✍️✍️ 😭😭😭😭😭😭😭😭 - 请前往设置白名单(默认全部群启用) - 提供分段回复容错设置 |
| 2024 | astrbot_plugin_fish_home | 39 | memory | have | 一个像素房间，她在里面。整屏就是这间屋子，黑底、俯视、墙上有窗，窗外跟着你当地的天气变。  左上角一块状态牌：她的名字、心情、好感度、余额、心愿、今天说了几句。底部是物品栏，8 种吃的各有自己的像素图标和吃东西动画，选中再点她，东西会飞到她嘴边。  好感度是实时的：认真说话会涨，敷衍的"嗯哦"不算， |
| 2025 | astrbot_plugin_baidu_pan | 39 | other | watch | 百度网盘分享自动下载发送插件。核心优势：共享会员——一个百度账号登录，全群成员共享高速下载，人人无需开通会员。主推扫码登录（无需密码，不怕风控），不收集、不存储、不传输任何账号密码，源码完全开源可审计。支持 napcat/SnowLuma/QQ官方机器人等多平台 |
| 2026 | astrbot_plugin_webhook_receiver | 39 | platform | have | 接收多个外部服务发送的 Webhook 通知，并将文本或网络图片安全推送到一组指定的 AstrBot 群聊或私聊。 |
| 2027 | astrbot_plugin_speak_rank | 39 | other | watch | 群内发关键词即可查看本群发言排行：今日 / 昨日 / 前天 / 近N天(如「近7天发言榜」) / 指定日期(如 9月7日) / 本周(周一起) / 累计，机器人发言默认也计入 |
| 2028 | astrbot_plugin_zmdlog | 39 | other | watch | 椰果人的藕粉铺子：在聊天里查 ZMDLogs 的终末地 DPS 榜单、账号成绩与战报，回一张终末地风格长图。 |
| 2029 | astrbot_plugin_bili_all_function | 39 | media-parse | borrow | 统一解析普通文本与 QQ 小程序卡片中的 B站视频链接并回复视频信息，支持可选的视频下载发送；订阅 UP 主动态与直播状态并后台轮询推送，支持类型/正则过滤、管理员全局订阅与 LLM 函数工具调用。 |
| 2030 | astrbot_plugin_vote_mute | 39 | group-admin | have | QQ群投票禁言插件，支持群成员投票决定是否禁言指定用户，可配置投票时长、参与人数上限、管理员介入、冷却时间等，支持每群独立配置。 |
| 2031 | wws_random | 39 | other | watch | 战舰世界插件：随机选船 + 组队系统 + 窝批自动回复 + LLM tool 舰船详情查询（四层模块化架构，支持 LLM 趣味吐槽） |
| 2032 | astrbot_plugin_account_quota | 39 | other | watch | 支持监测codex和deepseek额度以及重置卡状态和自然刷新时间，预测下次福利重置时间。 |
| 2033 | astrbot_plugin_digital_member | 39 | other | watch | Digital Member分析群友历史消息，生成说话风格和个人画像，支持模仿群友进行交流 |
| 2034 | astrbot_plugin_block_qq | 39 | other | watch | 前置黑名单拦截，阻断所有插件读取黑名单账号消息，减少token消耗 |
| 2035 | astrbot_plugin_psyche_engine | 39 | memory | have | 为虚构角色维护一套可复算的精神与身体状态，每轮对话重新计算，并以最高优先级写入 模型上下文。  **精神层**：21 项神经化学、23 项神经电与环路、14 项人格特质、163 条 ICD-11 症状、 72 个诊断原型、37 个病理预设。区分「正常 / 亚临床 / 病态」三档，健康基线不会被 凭空 |
| 2036 | astrbot_plugin_bili_vision | 39 | media-parse | borrow | 分享 B站视频链接时把字幕、画面和音频合起来理解，没有字幕也能在后台听完 |
| 2037 | astrbot_plugin_eve_esi | 38 | other | watch | EVE Online ESI API 调用插件，支持市场价格查询、舰船加成查询、简称管理等功能 |
| 2038 | astrbot_plugin_vibe | 38 | other | watch | Codex app-server vibe plugin. |
| 2039 | astrbot_plugin_mcwatcher | 38 | other | watch | MCWatcher 是一个基于 AstrBot 的插件，用于 自动监测 Mojang 的最新 Minecraft 版本 |
| 2040 | astrbot_plugin_youshusearch | 38 | other | watch | 查询网络小说详情以及优书网评价的搜索工具。 |
| 2041 | pokemon_fusion | 38 | game | have | 宝可梦融合插件，支持指定宝可梦融合和随机融合。 |
| 2042 | astrbot_plugin_cube | 38 | other | watch | 可视化魔方插件（三阶魔方），内置公式方便初学者学习 |
| 2043 | headline | 38 | info-push | have | 60秒国内新闻 |
| 2044 | astrbot_plugin_link_preview | 38 | media-parse | borrow | 自动识别群聊里的 YouTube、TikTok、Instagram、X、GitHub、Reddit、Bluesky、pixiv、Steam、维基百科、维基文库、Dailymotion、niconico、Spotify 等国外平台链接，抓取标题、作者、正文、配图、数据和热门评论，画成卡片图片发回群里； |
| 2045 | pulid_astrbot_prompt_to_maibot | 38 | personality | have | 在不修改 AstrBot 原有系统提示词的前提下，以追加方式注入 MaiBot 风格的拟人化优化规则，覆盖身份认知、群聊行为、回复风格、上下文理解等模块，各模块可独立开关。 |
| 2046 | astrbot_plugin_pjsk_guess_jacket | 38 | game | have | PJSK猜曲绘游戏，用户根据处理后的封面图片猜出歌曲名称 |
| 2047 | astrbot_plugin_tavily_quota | 38 | other | watch | 一站式查询 Tavily、OpenRouter、DeepSeek、GitHub、SiliconFlow(硅基流动)、Moonshot(Kimi)、Zhipu(智谱/GLM) 与 Serper 配额与余额，支持高颜值暗色看板、自动隔离隐藏未配置平台、低额度自动预警与大模型自然语言工具调用。 |
| 2048 | astrbot_plugin_blacklist | 38 | other | watch | QQ 黑名单管理 + 恶意行为自动举报。管理员指令拉黑/解拉黑；LLM 识别辱骂、骚扰、提示词注入后自动向管理员发起举报请示（附合并转发聊天记录），支持命令或引用回复「同意/驳回」审批。 |
| 2049 | astrbot_plugin_Venus_Attaccare | 38 | proactive | watch | 群聊戳一戳插件：发送"攻击 @用户"（或 WebUI 中自定义的其他指令），机器人会向目标发送戳一戳（poke）。冷却时间、戳次数、加强模式、全部回复话术均可通过 WebUI 配置。本插件使用 AI 辅助开发。 |
| 2050 | astrbot_plugin_script_search | 38 | other | watch | 提示词榨汁机。配合 AI 使用，把提示词里多余的水分榨干、把水分存起来，等需要的时候再注回去，有效加快回复速度、降低 token 消耗量。实测能把 18000 字的提示词压缩到 3500 字，具体效果取决于提示词本身有多少水分。 |
| 2051 | astrbot_plugin_autohelp | 38 | personality | have | 自动扫描已安装的插件，用 LLM 为每个插件写使用说明，按当前会话实际可用的功能生成 /帮助 菜单；插件增删改时自动更新，可选用人格口吻。 |
| 2052 | astrbot_plugin_token_panel | 38 | proactive | watch | PLUTO panel（普鲁托面板）是会话上下文 Token 用量的可视化面板：进度条、预警阈值、自动播报与一键清空；内置上下文统计（/ctx）、上下文压缩与承接（/ctx_compress、/ctx_continue、/ctx_sessions、/ctx_switch），支持扩展功能内置页面视图与 |
| 2053 | telethon_bot_adapter | 37 | other | watch | Telethon-based Telegram Bot adapter / 基于 Telethon 的 Telegram Bot 适配器 |
| 2054 | astrbot_plugin_unraid_manager | 37 | other | watch | 为 AstrBot 提供 Unraid NAS 安全管理功能，支持阵列状态监控、磁盘温度告警、Docker 资源查看。只读操作，禁止危险指令，守护数据安全。支持自然语言交互。 |
| 2055 | astrbot_plugin_douyu_live | 37 | info-push | have | 全自动监控多房间开播/下播并推送订阅通知 |
| 2056 | astrbot_plugin_idgen | 37 | other | watch | 生成/验证身份证号码插件 |
| 2057 | astrbot_plugin_tg_button | 37 | other | watch | 一个可以把指令或者网址绑定到Telegram的按钮上的插件 |
| 2058 | astrbot_plugin_legado | 37 | other | watch | 随机小说 |
| 2059 | astrbot_plugin_wordle | 37 | game | have | AstrBot Wordle 猜单词游戏，支持指定位数 |
| 2060 | safebooru | 37 | other | watch | /safebooru + tag = 好看的图， |
| 2061 | astrbot_plugin_yamibo | 37 | media-parse | borrow | 百合会论坛助手：自动签到、热帖推送、漫画/连载帖解析打包、帖子订阅更新推送、浏览与搜索。 |
| 2062 | astrbot_plugin_persona_schedule | 37 | personality | have | 按人设和世界观生成日程、节庆活动与每日生活日记，支持空闲/半忙/忙碌、合并补回消息、对话白名单及内嵌 WebUI。 |
| 2063 | astrbot_plugin_meta_governor | 37 | other | watch | AI 对话质量监督与回复调控插件 (Meta-Governor)，自动检测并修正复读、套路化及争吵回复 |
| 2064 | astrbot_plugin_kuro_sign | 37 | game | have | 库街区（鸣潮 / 战双帕弥什）每日自动签到，接口逻辑移植自 Night-stars-1/Kuro-Sign。  **绑定方式**（三种，都在私聊里做）： 1. kj登录 <手机号> —— 短信验证码登录，不用抓包（库街区是单设备登录，可能顶掉手机 APP）。 2. kj绑定 <Token> h5 — |
| 2065 | wuwa_luck | 37 | game | have | 鸣潮主题「今日运势」白底卡片（/luck /今日运势） |
| 2066 | astrbot_plugin_persona_studio | 37 | personality | have | 模块化人格提示词编排器，支持只读块、自定义提示词、原生 Persona 同步与最终请求快照。 |
| 2067 | astrbot_plugin_newapi_checkin | 37 | game | have | New-API 每日签到插件，支持全平台 |
| 2068 | astrbot_plugin_remote_start_computer | 37 | other | watch | 通过 Wake-on-LAN 远程唤醒电脑，并支持扫描在线设备获取 MAC 地址。 |
| 2069 | astrbot_plugin_welcome_verification_qqxwz114514 | 37 | group-admin | have | 基于月凌的 astrbot_plugin_welcome_verification 二次开发的入群欢迎与验证插件。 新增：群白名单、答错/答非所问自动撤回、机器人管理员权限前置检查。 支持自定义欢迎文本、图片、题库，支持为不同群组设置独立配置。 |
| 2070 | astrbot_plugin_time_model | 37 | other | watch | 按服务器时间自动切换 AI 模型，例如白天高峰用便宜模型、夜间低谷用更强模型。  支持两种配置方式： - AstrBot WebUI 可视化配置时段与模型（推荐） - 命令行指令实时增删时段规则（自动落盘，无需重启）  典型用法：低谷时段（如 00:30-08:30）切到 deepseek 等强模型 |
| 2071 | astrbot_plugin_fns_help | 37 | other | watch | 返回所有插件指令，可diy展示插件名称与是否显示 |
| 2072 | astrbot_plugin_fgo_gacha | 37 | game | have | FGO模拟抽卡：在群内通过水群和签到获取圣晶石，并进行单抽/十连，支持从Mooncell自动更新数据。 |
| 2073 | astrbot_plugin_tts_switcher | 37 | tts | watch | AstrBot 的会话级 TTS 只能在面板里逐个会话点选，日常想换个声音得开面板翻半天。 这个插件把「名字 → TTS 提供商」的映射放进插件配置页（每条可以写备注，方便区分 同名声线），之后在聊天里发 /tts 示例 就切过去了，即时生效、不用重启核心。 还支持两条一次性指令：/说=示例 今天风 |
| 2074 | astrbot_plugin_binance | 36 | other | watch | 币安查询，交易等... |
| 2075 | astrbot_plugin_ctx_trimmer | 36 | other | watch | 按照 Token 丢弃对话的插件 |
| 2076 | astrbot_plugin_lanzoucloud | 36 | media-parse | borrow | 蓝奏云文件解析插件，支持自动检测和手动解析蓝奏云分享链接 |
| 2077 | astrbot_plugin_uptime_kuma_puller | 36 | other | watch | 拉取UptimeKuma监控面板中的服务器状态 |
| 2078 | exchange_rate | 36 | other | watch | 一个查询汇率的工具 |
| 2079 | astrbot_plugin_newapi_tx | 36 | game | have | astrbot_plugin_newapi_tx_是一个为 AstrBot 打造的 QQ 群 ↔ New API 网站联动插件，集用户绑定、额度经济、群聊互动、管理员工具 于一体，并支持 退群自动解绑与账号净化 的全自动管理套件。无需.env,直接配置！ |
| 2080 | astrbot_plugin_relay_checkin | 36 | game | have | 中转站（NewAPI / Veloera 系）每日自动签到领额度，支持多站点、定时、失败重试与结果推送 |
| 2081 | astrbot_plugin_pixiv_monitor | 36 | media-parse | borrow | 监控 Pixiv 画师更新并自动解析作品链接，并推送图文卡片到 QQ。 |
| 2082 | astrbot_plugin_arcaeaStickers | 36 | sticker | borrow | Arcaea贴纸生成器 |
| 2083 | astrbot_plugin_chat_helper | 36 | other | watch | 智能聊天助手 - 实时分析对话意图、情绪与风险等级，提供概率评估与回应建议，支持群聊/私聊及精细化配置 |
| 2084 | astrbot_plugin_multi_topic | 36 | other | watch | 连着发来多条消息或多个话题时，让 AI 引用原消息、分条逐一回复，像真人聊天一样接话。适配 NapCat / OneBot v11。 |
| 2085 | astrbot_plugin_random_number | 36 | game | have | 随机数生成插件，支持自定义范围、批量生成、掷骰子和群成员抽奖，带WebUI管理面板 |
| 2086 | astrbot_plugin_fish_knowledge | 36 | kb-rag | have | 按需搜索公开资料，带正文证据和版本入库，去重、过期管理、自动检索，并学习用户明确的交流反馈。 |
| 2087 | astrbot_plugin_astrembodiment | 36 | personality | have | Rust-native persona emotion, semantic appraisal and deterministic embodiment clock for AstrBot. |
| 2088 | astrbot_plugin_browser_chat | 36 | other | watch | 无需 API 密钥，在 QQ 畅聊 ChatGPT 或 DeepSeek 网页版；使用免费账号即可接入，额度以网站规则为准。 |
| 2089 | astrbot_plugin_group_file_finder | 36 | other | watch | 逐层浏览、递归查找、上传和管理 QQ 群文件；支持命令与 LLM 工具 |
| 2090 | astrbot_plugin_sponsor | 36 | other | watch | 赞助关键词提示与微信、支付宝二维码回复 |
| 2091 | active_reply_dynamic_control | 36 | other | watch | 按时间段与模式动态控制机器人对群聊的回复行为（完全封锁 / 仅被@回复），未配置时间段默认全天封锁。提供 WebUI 管理面板（总览 / 行为设置 / 系统）。 |
| 2092 | astrbot_plugin_jiehua | 36 | other | watch | 连续文本消息等待与合并、收尾静默和上下文衔接。齿轮中可配置各开关、等待时间及费用边界。 |
| 2093 | lmem_backfill | 36 | memory | have | 抓取群聊历史消息，经 LivingMemory 总结后写入长期记忆库。 |
| 2094 | astrbot_plugin_smart_reply | 36 | other | watch | 让机器人自己决定什么时候开口。  - 打分制：模型给 0~100 分，≥ 阈值才回复，比"回/不回"更可控 - 刚说过话自动提高门槛，避免连续刷屏 - 名字 / 引用 / 催促词硬触发，不依赖模型 - 三级重试 + 备用模型，判断失败自动降级 - 判断日志 JSONL，可按分数分布调阈值 - 全部配 |
| 2095 | astrbot_plugin_MQTTCloudIoT | 35 | other | watch | 让 AstrBot 变身智能 IoT 设备控制中心！！！！可以手动进行属性上报，事件通知，发送设备告警、状态变更等事件自定义消息：支持任意Topic的信息上传，通过此插件借助云端可以让astrbot控制有wifi的单片机 |
| 2096 | astrbot_plugin_uptime | 35 | info-push | have | Uptime bot. 监测所订阅的站点是否可正常访问，异常时发出警报。 |
| 2097 | astrbot_plugin_Blive_adapter | 35 | media-parse | borrow | 用于接入bilibili的平台适配器 |
| 2098 | astrbot_plugin_bilibili_live_mod | 35 | media-parse | borrow | B站回复机器人：视频、直播间的AI回复助手。采用双账号制。 |
| 2099 | pov_actions | 35 | other | watch | 监听 LLM 回复, 用 LLM 智能识别当前对话中 bot 对用户做出的动作(抱抱/亲亲/摸头等), 自动生成第一人称视角(POV)图片追加发送, 让你看到"AI 正在对你做什么"。 |
| 2100 | astrbot_plugin_ongeki_gacha | 35 | group-admin | have | 把街机音游《オンゲキ（音击）》的抽卡和养成搬进群聊的娱乐插件。  每天签到攒点数，用点数 1 / 5 / 11 连抽卡，收录 2841 张卡牌资料；接入自备素材后可显示高清卡面， 卡池按历史官方档期轮替， 抽满天井可以直接换想要的卡。17 名主角色都能养成：选伙伴、每日陪伴、送礼提升好感， 慢慢解锁 |
| 2101 | astrbot_plugin_witch_trial | 35 | personality | have | 以《魔法少女の魔女裁判》风格生成每日群聊「开庭记录」图片，支持定时开庭、群黑白名单，判决书口吻自动继承当前人格设定 |
| 2102 | astrbot_plugin_image_bridge | 35 | other | watch | 图片按「小米 MiMo → 百度图像识别 → OCR.space」三级优先链识别，用户随后发送文字提问时，将识别内容一并注入 LLM；只发图片不提问则 AI 不回答。 |
| 2103 | astrbot_plugin_multi_group_chat | 35 | other | watch | 两个机器人能聊天的插件。 |
| 2104 | astrbot_plugin_md_formatter | 35 | other | watch | 解决 AstrBot + OneBot v11 (NapCat) 接入 QQ 时 markdown 无法渲染的问题。 AI 输出里常见的加粗 **文字**、标题 #、列表 -、表格 \| a \| b \|、 代码块 ``` 等 markdown 语法，在 QQ 中不会被渲染，会直接露出原始符号， 导致消 |
| 2105 | astrbot_plugin_jx3_news_kb | 35 | kb-rag | have | 抓取 JX3API 官方公告与新闻到本地知识库。混合检索问答：全文（FTS5）+ 向量召回 + 可选 Reranker，回答逐句核对公告原文并自动标注来源；活动到期提醒：逐日倒计时（可提前 0-7 天）、周一/周四维护日截止改前一晚提醒、截止前临期加推，活动/道具措辞自动区分，同日多条合并推送；We |
| 2106 | astrbot_plugin_sendmsg | 35 | other | watch | 通过 /sendmsg 命令向指定 QQ 群、好友或全部群与好友发送消息。 |
| 2107 | astrbot_plugin_media_montage | 35 | other | watch | 为 AstrBot 4.28.1/4.28.2 补回"动图被转成抽帧拼图"时给模型的提示；同时让视频也以完全相同的抽帧拼图逻辑被模型理解（所有版本生效）。 |
| 2108 | astrbot_plugin_whitelist_manager | 35 | other | watch | 在 WebUI 里一键把群聊/私聊加入全局白名单与主动回复白名单，无需手改配置、无需重启。 |
| 2109 | astrbot_plugin_smart_reply_gate | 35 | other | watch | 关键词、正则触发与群聊主动回复门控 |
| 2110 | astrbot_plugin_email_assistant | 35 | personality | have | AstrBot 个人多邮箱助手，支持 IMAP/SMTP、附件收发、人格转述与安全草稿；提供适配手机的 WebUI 邮件中心及邮件总结和翻译 |
| 2111 | astrbot_plugin_osu_dl | 34 | media-parse | borrow | 自动识别解析聊天中的 osu! 谱面链接并发送 osz 文件 |
| 2112 | astrbot_plugin_ts3_tracker | 34 | other | watch | 拥有 TeamSpeak 3 在线状态查询、频道成员展示、上下线通知的功能。 |
| 2113 | telethon_adapter | 34 | other | watch | 基于 Telethon 的 Telegram Userbot 适配器 |
| 2114 | astrbot_plugin_lofter_parser | 34 | media-parse | borrow | 支持 Lofter（乐乎）平台分享链接的自动解析 |
| 2115 | astrbot_plugin_steam_topsellers | 34 | game | have | 获取 Steam 热销榜前 5 名游戏 |
| 2116 | asbot_plugin_furry_jtwzbq | 34 | sticker | borrow | [QQ] 监听文字表情时重复发送 |
| 2117 | astrbot_plugin_64gua | 34 | game | have | 周易六十四卦随机生成器 |
| 2118 | goldprice | 34 | other | watch | 从招商银行 API 接口获取实时金价 |
| 2119 | astrbot_plugin_seer_info | 34 | other | watch | 赛尔号信息查询插件，支持精灵、刻印、装备等数据查询 |
| 2120 | astrbot_plugin_LLM_jrlp | 34 | personality | have | 今日老婆插件移植版：随机抽一位 gal 角色作为今日老婆，支持换老婆/结婚/离婚，回复完全由 LLM 生成 |
| 2121 | astrbot_plugin_pjsk_query | 34 | tts | watch | Project SEKAI (pjsk)卡牌、角色、歌曲、谱面与活动查询插件。 |
| 2122 | astrbot_plugin_deepseek_audio | 34 | tts | watch | 为 AstrBot 新增两个 Provider 类型：deepseek_tts_api（语音合成）与 deepseek_asr_api（语音识别）， 直接调用 DeepSeek 官方 POST /v1/tools/tts 与 POST /v1/tools/asr。 内置的 openai_tts_ap |
| 2123 | astrbot_plugin_eidolon | 34 | image-gen | watch | 基于火山方舟 Seedream 5.0 Pro 的 AstrBot 群聊文生图/图生图插件，支持指令与自然语言触发（关键词或工具调用）、多图融合、并发队列、用量限制和 LLM 提示词润色 |
| 2124 | astrbot_plugin_html_theater | 34 | personality | have | 使用 OpenAI 兼容接口生成、保存和展示 HTML 小剧场，提供临时提示词、模板、人设、续写、收藏与备份控制面板。 |
| 2125 | astrbot_plugin_say_picture | 34 | sticker | borrow | 当检测到@某用户说~ 时，生成表情包 |
| 2126 | astrbot_plugin_keyword_reply | 34 | other | watch | 关键字自动回复插件：一条规则四个字段（关键字、匹配类型、回复、格式），带 Web 面板可视化管理。匹配类型支持精准/模糊/前缀/后缀/正则，回复格式支持纯文本和 MD 格式（自动渲染成图片）。规则分全局与按会话两级，面板里可以按群名选群（不用记群号），也可在聊天里用 /关键字 命令管理。 |
| 2127 | astrbot_plugin_jx3_mingpian | 34 | personality | have | 抽角色名片形象图，交给生图模型出底卡，再叠文字与门派元素，生成剑网3风格名片卡。 |
| 2128 | astrbot_plugin_invite_tree | 34 | other | watch | 记录 QQ 好友、群邀请和群成员来源关系，并生成头像树状图。 |
| 2129 | astrbot_plugin_recognize_owner | 34 | other | watch | AstrBot 分不清发言者的「QQ 昵称」和「QQ 号」—— 别人把昵称改成主人的名字，AI 就可能被骗。 这个插件在消息进入 LLM 之前，按发言者的真实 QQ 号做对比，把身份说明**贴在用户消息前面**： 主人说的话标注「这是主人」，其他人标注「这不是主人，真实 QQ 号是 xxxx」。 同 |
| 2130 | astrbot_plugin_image_api | 34 | image-gen | watch | 调用第三方图片生成 API 生成图片。支持 OpenAI 兼容接口（DALL·E、硅基流动、智谱、NewAPI 等）、Stable Diffusion WebUI，以及可自定义请求体的任意 HTTP 接口；提供 /画图 指令和 generate_image 大模型工具。 |
| 2131 | astrbot_plugin_better_send_message_to_user | 34 | other | watch | 优化 send_message_to_user 文本发送流程，将调用转为正常 AstrBot 回复。 |
| 2132 | astrbot_plugin_yangmo_qq_search | 34 | other | watch | 让你的 AI 把 QQ 群聊历史当作可引用的外部事实源：支持关键词、成员、时间、消息类型和邻近语境检索，不把整段历史自动塞进主对话。 |
| 2133 | astrbot_plugin_tcg_galatea | 34 | game | have | 五大指令组 OCG/MD/DL/PTCG/VG 独立开关。子指令：查卡(模糊/卡密/自动高清图)/序号/换页/饼图/禁卡表/随机。 |
| 2134 | astrbot_plugin_ainong | 34 | game | have | 通过王者营地官方接口读取玩家的段位、战绩与英雄数据，交给大模型做锐评和玩家画像。 |
| 2135 | astrbot_plugin_pixiv_dowlonder | 34 | media-parse | borrow | 按 PID 下载 Pixiv 图片，支持原图／1200／540 像素、按页数发图或加密 ZIP、一键／定时清理，作品解析与图片下载可独立配置反代。 |
| 2136 | astrbot_plugin_rest_hours | 34 | other | watch | 在可配置的休息时段（默认 23:00-07:00）与高峰时段不回复消息，休息结束后把攒下的消息统一补回；时段、天数规则都能在面板里改。 |
| 2137 | astrbot_plugin_persona_switch | 34 | personality | have | 用指令给当前群聊/私聊切换 AstrBot 人格，支持限时切换（到期自动还原并提示）与一键还原，与 WebUI 会话人格设置互通 |
| 2138 | astrbot_plugin_Google_Health_Data_Retrieval_and_Analysis | 33 | other | watch | 通过 Google Health API 获取健康数据，支持多用户在线授权；已注册 Agent 工具，可直接用自然语言拉取并分析睡眠、步数、心率等数据 |
| 2139 | astrbot_plugin_yunhuAdapter | 33 | other | watch | 将 AstrBot 接入云湖机器人平台的插件，通过 WebSocket 与云湖 SDK 桥接通信。 |
| 2140 | astrbot_plugin_api_fetcher | 33 | other | watch | 定时拉取某 API 并主动推送到指定会话的示例插件 |
| 2141 | randomtoken | 33 | other | watch | 一个Token生成管理器，支持生成、导出、删除和查看Token列表。 |
| 2142 | astrbot_scpsl_server | 33 | other | watch | SCP：SL 服务器查询插件，仿照 server_Qchat 功能 |
| 2143 | yinlish | 33 | other | watch | 普通文本转换为'*语',支持自定义*乱度,*语字典 |
| 2144 | astrbot_plugin_encipherer | 33 | other | watch | 集合包括Base64、URLencode、Punycode编码加解密工具的astrbot插件 |
| 2145 | astrbot_plugin_wordle_2_cmd | 33 | game | have | Astrbot Wordle 游戏插件（响应指令内容版），优化和加入了许多新功能 |
| 2146 | astrbot_plugin_dna | 33 | personality | have | 狩月终端——面向《二重螺旋》的 AstrBot 游戏助手，支持账号管理、角色面板、图鉴攻略、签到、日常查询与公告订阅。 |
| 2147 | astrbot_plugin_naraka | 33 | other | watch | 通过小黑盒查询永劫无间端游近期战绩与单局详情，支持昵称搜索、模式筛选、三种数据模式与自动绑定兜底。 |
| 2148 | astrbot_plugin_user_agreement | 33 | other | watch | 一个在任何人使用astrbot服务前先同意用户协议及隐私政策的插件，可以规避一些风险 |
| 2149 | astrbot_plugin_qq_offline_alarm | 33 | platform | have | 轮询 OneBot(NapCat) 的 get_status 判断 QQ 登录状态，掉线持续超过阈值后通过 QQ 邮箱 SMTP 发送告警邮件，恢复登录后发送恢复通知。 |
| 2150 | astrbot_plugin_komari_watch | 33 | other | watch | 面向 AstrBot 的 Komari 监控插件。支持节点状态、实时资源查询， 并通过统一消息来源向 OneBot 会话推送服务器离线和 CPU、内存、磁盘超阈值告警。 |
| 2151 | astrbot_plugin_reject_harassment | 33 | other | watch | 拒绝 AI 骚扰。AI 可以主动拉黑持续骚扰的单个用户，也可以在多人骚扰时结束整个会话。被拉黑用户的消息不进 AI；被结束会话的消息只回复固定文案，需 /new 才能恢复。指令始终可用，便于管理员解封。 |
| 2152 | astrbot_plugin_supermemory | 33 | memory | have | 接入 Supermemory，为私聊和群聊提供按会话隔离的长期记忆能力. |
| 2153 | astrbot_plugin_lyricsearchtool | 33 | other | watch | 通过网易云音乐 API 搜索歌词，封装为 LLM 工具供 AI 主动调用 |
| 2154 | astrbot_plugins_tts_vllm_omni | 33 | tts | watch | 一个用于添加Vllm_Omni的文字转语音插件 |
| 2155 | astrbot_plugin_drift_bottle | 33 | other | watch | 让 Bot 连接的不同群之间匿名互投漂流瓶。群员可扔瓶、捞瓶、回瓶，瓶子带旅程记录，被捞多次后沉没，形成跨群传说。 |
| 2156 | astrbot_plugin_htmlrender | 33 | other | watch | 提供本地 HTML 渲染功能的基础插件 |
| 2157 | astrbot_plugin_sb6657 | 33 | personality | have | 注册只读 SB6657 实时查询 LLM Tool，供人格直接调用。 |
| 2158 | astrbot_plugin_persona_forge | 33 | memory | have | 人格创建与迭代、分层记忆、共享 Wiki、提示词版本与审查、数字生命卡。 |
| 2159 | astrbot_plugin_watch_reply | 33 | sticker | borrow | 捉：监听指定群友发言，等其沉默 N 秒后自动回复文本或表情包。支持关键词/正则/连续发言触发、独立选群、冷却节流、防插嘴延迟，带 WebUI 管理面板。适配 NapCatQQ（OneBot v11 / aiocqhttp）。 |
| 2160 | astrbot_plugin_char_draw | 33 | image-gen | watch | 将图片和gif转换为ASCII艺术字符画的插件，支持静态图片和动图（GIF/APNG/WebP/MNG）。 |
| 2161 | astrbot_ctfpusher_plugin | 32 | info-push | have | 基于 CTFTime 与 NSSCTF 的全功能赛题推送、赛事检索、过滤与订阅提醒插件，支持精细化管理和北京时间自动转换。 |
| 2162 | astrbot_plugin_acm_helper | 32 | other | watch | 功能强大的 ACM 训练辅助插件。它能够自动追踪成员在 Codeforces 和洛谷的刷题动态，提供实时排名，并通过一个直观的排行榜。让每一次提交，都留下印记。 |
| 2163 | astrbot_plugin_nbnhhsh | 32 | other | watch | 神奇海螺缩写查询，支持“XX是什么/是啥/是什么意思”提问，需先@机器人 |
| 2164 | LiteBridge | 32 | other | watch | 基于 WebSocket 的 Minecraft 群服互通插件 |
| 2165 | astrbot_plugin_immersive_error | 32 | other | watch | 客制化回覆插件。侦测自订的拦截词，并将其替换为与之对应的沉浸式回覆。 |
| 2166 | astrbot_plugin_discord_self_embeded | 32 | kb-rag | have | 一个用于 AstrBot 的 Discord Embed 适配器插件，可以自动将发送至 Discord 的文本消息转换为精美的 Embed 格式。 |
| 2167 | astrbot_plugin_60s_news | 32 | info-push | have | [仅gewechat] 60s国内新闻 |
| 2168 | huanju | 32 | game | have | 欢乐21点游戏插件。输入 /hj help 查看关键词回复帮助。 |
| 2169 | astrbot_plugin_bond | 32 | personality | have | 保存熟悉度、亲近度、信任度与成员印象，支持分级评估、人格适配及管理面板。 |
| 2170 | astrbot_plugin_feeding | 32 | personality | have | 发送食物图片，结合用户角色设定图生成 进食图片，并沿用当前会话人格点评。 |
| 2171 | astrbot_plugin_broadcast | 32 | other | watch | QQ 平台（NapCat / OneBot v11）广播助手插件，支持三大功能：  1. 定时群发：在配置的时间（24 时制）自动向白名单群聊发送预设内容，可开关； 2. 启动通知：机器人启动且 aiocqhttp 适配器连接成功后，自动向所有群聊发送预设通知，可开关； 3. 指令广播：通过 /广播 |
| 2172 | astrbot_plugin_deepseek_manager | 32 | other | watch | 一站式查询 DeepSeek 账户余额、Token 用量与消费金额。 |
| 2173 | astrbot_plugin_bluearchive_toolbox | 32 | info-push | have | 为 《碧蓝档案》 开发的工具箱，自带WEBUI，支持查询 国服/国际服/日服 的学生信息，活动信息，千里眼等；还支持分UMO会话订阅推送更新，内置互动菜单功能，模仿QQ官方机器人的按钮交互功能 |
| 2174 | astrbot_plugin_prism | 32 | memory | have | 维护主观心情、人物感受与联想回忆；可与光谱协作形成状态驱动的角色对话，是可选组件。 |
| 2175 | astrbot_plugin_sponsor_pass | 32 | other | watch | 陌生人准入、爱发电订单核验、微信支付/支付宝商户订单查询和会员权益发放插件，适用于 AstrBot + OneBot v11（aiocqhttp）。  爱发电是默认主流渠道；微信支付和支付宝仅支持官方商户 API，不支持个人收款码自动验单。支持普通赞助、商品订单、订单号兑换、忘填QQ留言兜底、一次性 |
| 2176 | astrbot_plugin_token_stats | 32 | other | watch | 按天 / 按小时 / 按会话查看 QQ AI 每天消耗了多少 token、缓存命中率多少（只读 provider_stats，不介入请求链路） |
| 2177 | astrbot_plugin_dianping | 32 | other | watch | 基于 Sniper970119/dianping_spider 的搜索页、详情页与动态字体解码思路， 为 AstrBot 提供餐厅推荐和按需电话查询 LLM 工具。支持地址、评分、人均消费、 招牌/推荐菜及页面明确列出的菜价；默认不主动查询电话。 |
| 2178 | astrbot_plugin_group_chat_switch | 32 | group-admin | have | 用聊天指令按群开启/关闭 AI 聊天，写入 AstrBot 官方的会话级配置，开关立即生效，不需要开 WebUI。支持在群里直接切换，也支持私聊按群号远程切换。 |
| 2179 | astrbot_plugin_pixiv_lolicon | 32 | other | watch | 这是一个pixiv插画插件，基于lolicon api |
| 2180 | cyber_mystery | 32 | game | have | 赛博诡秘 · 诡秘人生重开模拟器。选择出身与天赋开启一段诡秘世界的人生：随机事件流转，接触非凡组织，饮下魔药，以扮演法消化序列力量，从序列9一路爬升至序列0成神，或在疯狂与失控中化作雾中怪物。人生结果会将关键节点完整保留，并把晋升之间的扮演、危机、途径经历和普通事件按原始年龄逐条编排为更完整的第二人 |
| 2181 | astrbot_plugin_peak_guard | 32 | other | watch | 峰谷计费省钱：高峰时段自动暂停对话或切换备用模型，空闲自动恢复；支持白名单、供应商过滤与定时通知。本插件由 AI 制作。 |
| 2182 | astrbot_plugin_auto_status | 32 | other | watch | QQ状态管理插件。支持开机自动设置在线状态、AI聊天切换状态、一键修改状态指令。 |
| 2183 | astrbot_plugin_block_official_bot | 32 | group-admin | have | 基于 QQ 资料卡 is_robot 标志识别官方 QQ 机器人（QQ 小冰、Q 群管家、各类官方智能体等），消息在进入 AstrBot 的第一时间被拦截，不进入 LLM、不触发其他插件，避免 token 浪费与机器人互聊。 |
| 2184 | astrbot_plugin_feishu_todo | 31 | platform | have | 自动识别飞书消息中的任务并创建飞书待办，支持多级 DDL 提醒 |
| 2185 | astrbot_plugin_memos_pusher | 31 | other | watch | 快速将灵感推送到 Memos，支持 /memo 指令。 |
| 2186 | astrbot_plugin_multi_execute | 31 | other | watch | 支持模拟其他用户执行指令、自动连续执行指令、免唤醒触发指令、指令伪装、指令别名、黑白名单和大小写兼容。 |
| 2187 | translate | 31 | other | watch | 使用 Google Translate 的 AstrBot 插件，支持使用命令 /tl 翻译任意文本。 |
| 2188 | astrbot_plugin_idiom_chain_game | 31 | game | have | 成语接龙 |
| 2189 | astrbot_plugin_wordle_2_msg | 31 | game | have | Wordle 猜单词游戏。基于 Raven95676 的版本加入了一些新功能。 |
| 2190 | videosummary | 31 | other | watch | 使用 bibigpt 实现视频总结 |
| 2191 | astrbot_plugin_astralparty_pilot | 31 | kb-rag | have | 利用游戏资源解包数据 + 本地知识库 + 自动寻路决策算法，为《星引擎派对》（Astral Party）实现图鉴查询与对局辅助：查卡牌 / 怪物 / 角色 / 地块 / 地图 / 格子 / 筹码 / 成就，看立绘、战斗CG、表情包与地块圆片，算威胁排序、寻路与手牌建议，支持按 UID 查号；陪玩引擎 |
| 2192 | astrbot_plugin_signin | 31 | game | have | 3.0.2 修复版：签到累计次数不再因重启被迁移逻辑洗掉（计数失效根因）；签到响应图脏数据全量容错，管理员等重度账号强制走新版样式渲染。功能同 3.0.1（签到/红包/左轮手枪/宠物/农场/银行等），保持数据兼容。 |
| 2193 | astrbot_plugin_Scintilla_MC_Server_Control | 31 | other | watch | 通过 RCON 用自然语言操控 Minecraft 服务器并具备高度完备的 WebUI：内置多 Agent 工作流处理整合包复杂任务；转发玩家进出/聊天/死亡/成就/对话/指令；平台指令组 mcs 支持绑定、喊话、状态查询与踢人封禁（管理员）。 |
| 2194 | astrbot_plugin_link_ex | 31 | media-parse | borrow | 自动识别群聊里的 B站、抖音、小红书、微博、知乎、YouTube、TikTok、Instagram、X、GitHub、Reddit、Bluesky、pixiv、Steam、维基百科、维基文库、Dailymotion、niconico、Spotify 等国内外平台链接，抓取标题、作者、正文、配图、数据 |
| 2195 | astrbot_plugin_livingemotion | 31 | memory | have | 规则情绪无需模型调用，原生人格的心情、关系、作息与精力持续保存。 主动聊天、日记梦境与记忆按需开启，延后约定到期执行，未知结果不盲目重试。 控制台自动刷新并保留编辑草稿，模型与独立开关集中设置，普通使用无需 Node 或外部 CDN。 接入 QQ、Telegram、Discord；随机主动使用 QQ |
| 2196 | astrbot_plugin_cs2_Prop | 31 | game | have | 每日定时推送 CS2 实用道具教学，支持按地图学习和自定义发送时间。 |
| 2197 | astrbot_plugin_hehu_zhouli | 31 | other | watch | 将现代中文改写成“合乎周礼”的白话翻译腔；AstrBot 适配版，核心风格来源于 Aspirin0000/zhouli-translator。 |
| 2198 | astrbot_plugin_wuwa_energy | 31 | proactive | watch | 基于库街区 (api.kurobbs.com) 的鸣潮 (Wuthering Waves) 体力查询与提醒插件， 使用网页版库街区的 Token 认证（登录 https://www.kurobbs.com 后从开发者工具获取）。  功能： - `/体力 绑定 <用户ID> <Token>` 绑定库街 |
| 2199 | astrbot_plugin_session_switch | 31 | group-admin | have | 用 /end 让机器人闭嘴、/begin 恢复说话，按会话独立生效：在哪个群或私聊里关，就只关那一个。 只在「要调模型」和「要发消息」两处掐断，所以静默期消息照收、指令照用、不烧 token，群聊上下文照常累积，/begin 后能接上前文。 三个指令名和所有回复文案都能在配置里改（比如把 /end  |
| 2200 | astrbot_plugin_ear | 31 | memory | have | 让只会读文字的模型真正听见声音——不是转成文字，而是听语气、听停顿、听背景。  QQ 语音：用能听音频的多模态模型（默认通义千问 Omni）听一遍，写成第一人称的听感， 同时把这段声音画成声谱图，一起注入临时上下文。人格、记忆、说话方式都不变，只是多了一只耳朵。  抖音作品：可截取播放器真实音频轨， |
| 2201 | hikari_netease | 31 | media-parse | borrow | 网易云音乐解析：自动识别歌曲/专辑/歌单/播客链接，私聊发音频或 ZIP 打包 |
| 2202 | astrbot_plugin_bilibili_voice | 31 | media-parse | borrow | 通过 Bilibili 扫码登录，搜索视频并下载音频，转换为 MP3 后以 QQ 语音发送。 |
| 2203 | astrbot_plugin_svg_doodle | 31 | other | watch | 让 bot 用 SVG 手写儿童蜡笔画风格的涂鸦；支持画册浏览、按关键词翻旧画、签名日期、蜡笔纹理后处理 |
| 2204 | astrbot_plugin_xhs_reader | 31 | media-parse | borrow | 让你的 AI 机器人看懂小红书笔记，阅读正文、配图和评论，还能按关键词搜索笔记。 |
| 2205 | astrbot_plugin_fatfish_court | 31 | other | watch | 先审再判：有人说机器人错了先核对再认，有人越红线法官看原话判，判了才冷却，能申诉。（原「大肥鱼 · 法庭」）细节和配置见 README。 |
| 2206 | astrbot_plugin_btw | 30 | other | watch | 类似claude code /btw指令，允许用户在当前对话中快速发起一次额外的独立提问，不包含上下文，不计入对话历史。 |
| 2207 | astrbot_plugin_adsb_monitor | 30 | media-parse | borrow | 使用 RTL-SDR（RTL2832U） + Dump1090 接收 1090 MHz ADS-B 信号，解析飞机信息，并在 QQ 群/私聊中提供查询功能。 |
| 2208 | astrbot_plugin_provider_ark_ContextAPI | 30 | other | watch | 将可应用上下文缓存API的火山方舟(Volcengine Ark) 注册为 AstrBot 的对话服务提供商(Provider)(支持 /provider 切换) |
| 2209 | astrbot_plugin_gotify | 30 | proactive | watch | 监听 Gotify 服务器的消息，并推送给消息平台 |
| 2210 | holdem_poker | 30 | game | have | 简单的德州扑克，/poker就可以开玩了 |
| 2211 | astrbot_plugin_kimi_datasource_api | 30 | other | watch | 为 AstrBot LLM 提供 Kimi datasource 专业数据库工具。 |
| 2212 | astrbot_plugin_group_auto_approve | 30 | group-admin | have | 基于 AstrBot 的 QQ 群入群申请 AI 自动审核插件。 |
| 2213 | astrbot_plugin_osu_beatmap_preview | 30 | other | watch | osu! 谱面预览：按谱面 ID 生成四模式预览长图、GIF 与带原始音频的 MP4，支持 Mod、转谱、背景视频与故事板。 |
| 2214 | astrbot_plugin_token_dashboard | 30 | other | watch | 可视化模型 token 消耗：缓存命中率趋势、按会话/模型拆分、单次请求明细与成本估算。数据直接读取 AstrBot 的 provider_stats，只读不改。 |
| 2215 | astrbot_plugin_comfyui_bridge | 30 | other | watch | 连接本地ComfyUI，支持 Anima、WAI-Illustrious、SDXL 和 WAN，提供 QQ 绘图、手机工作台、提示词预设、图片归档和收藏。 |
| 2216 | astrbot_plugin_roblox_search | 30 | game | have | Roblox 平台综合查询工具（测试版），支持用户/游戏/群组查询、好友列表、官方徽章、在线状态和简介绑定（由 MrMao 的 NoneBot2 插件迁移增强） |
| 2217 | astrbot_plugin_bililive_qc | 30 | media-parse | borrow | 免登录监控B站直播间开播/下播，在QQ群发送卡片式通知 |
| 2218 | astrbot_plugin_dsh_card | 30 | other | watch | 把 AI 输出的 Markdown 变成一张**带女仆立绘的卡片图**，直接发到聊天窗口。  模型返回的表格、代码块、清单，直接发出去就是一堆 `\|` 和 `**`，糊成一坨没人想看。 这个插件把它变成图片：表格有边框、代码有高亮、emoji 是彩色的、中文按行高排好。  **三种用法**  1.  |
| 2219 | astrbot_plugin_get_mc_server_info | 30 | other | watch | 会话隔离管理 MC 服务器，支持主备线路、命令与 LLM Tool 增删改查、故障转移、状态历史、列表与查询图片及模板缓存管理。 |
| 2220 | astrbot_plugin_mc_bridge | 30 | game | have | AstrBot Minecraft 插件，通过 RCON 协议连接 Minecraft 服务器，提供多服务器管理、 AI 自然语言控制、定时备份公告、性能监控与玩家管理；并内置鹊桥（QueQiao）mod 对接， 实现 MC 与 QQ 群之间的双向聊天、进服/退服、死亡等事件转发。  主要特性： - |
| 2221 | astrbot_plugin_pigsty | 30 | other | watch | 一个可以把群友圈养起来的养猪猪插件 |
| 2222 | astrbot_plugin_gemini_tts | 30 | tts | watch | 直接调用 Gemini 3.8 TTS，支持 voice、style、inline vocal tags 和概率性自动语音回复。 |
| 2223 | astrbot_plugin_openviking_memory | 30 | memory | have | 面向 AstrBot 的 OpenViking 长期记忆集成：自动捕获对话、语义召回、跨会话空间记忆，隔离规则可自定义。社区维护增强版——消息 outbox 可靠投递、召回分层降级、可观测性增强，并附带完整测试覆盖。 |
| 2224 | astrbot_plugin_friberg_guess | 30 | game | have | 四合一的「猜选手」游戏（类 Wordle）。发「弗一把」「足一把」「撸一把」「瓦一把」开局， 弗一把默认出「最火 200 人」（不含教练），足一把默认出「知名 250 人」（现役 190 + 退役传奇 60），还能限定联赛 （英超/西甲/德甲/意甲/法甲/五大），撸一把默认出热门 150 人（现役  |
| 2225 | astrbot_plugin_bilibili_up_push | 30 | media-parse | borrow | 按群订阅指定UP主或合集白名单，自动推送新视频并通过万能解析器发送视频文件 |
| 2226 | astrbot_plugin_tieba | 30 | other | watch | 监听指定贴吧的新主题帖，向 OneBot v11 群聊推送标题、发帖人、内容预览和链接。 |
| 2227 | astrbot_plugin_gaijin_market_watcher | 30 | info-push | have | 老插件 Gaijin 市场行情监控的升级版本，沿用原有插件 ID、数据目录和 /gjm 指令命名空间。 监控普通商品的最低售价、最高求购价与挂单量；插件控制台统一管理账户登录、订阅、输出模板和自动交易。  特性： - 会话级多用户订阅：同一用户可在不同群聊或私聊独立订阅 - 群聊全量快照：按固定间隔 |
| 2228 | astrbot_plugin_weibo_hot | 29 | info-push | have | 自动抓取微博热榜。 |
| 2229 | astrbot_plugin_qrcode | 29 | other | watch | 链接转二维码的astrbot插件 |
| 2230 | acmer_qq_group_bot | 29 | group-stats | borrow | 提供牛客、Codeforces、AtCoder、洛谷比赛查询与定时推送（牛客按 OJ 归属收录全部赛事）； 支持 XCPC Link 线下赛查询、四平台账号绑定、个人战绩卡、群排行、 按用户名/UID 查询未绑定用户战绩卡、 每日早报、赛前 15 分钟提醒、赛后赛果、群训练周报、牛客报名截止提醒与  |
| 2231 | astrbot_plugin_classnote | 29 | personality | have | 把课程记在笺上。导入 WakeUp 日历与分享课表，按实际课次主动提醒，沿用当前会话人格。 |
| 2232 | astrbot_plugin_strip_thinking | 29 | other | watch | 去掉模型回复中的 <thinking> 思维链，并支持按关键词裁剪回复正文。 |
| 2233 | astrbot_plugin_image_search | 29 | other | watch | 基于 Google Lens 反向搜图，返回 AI 图片描述与完全匹配来源链接 |
| 2234 | astrbot_plugin_roblox_game_search | 29 | game | have | 通过 /roblox游戏搜索 指令查询 Roblox 游戏详情、好评率和公开服务器状态。 |
| 2235 | astrbot_plugin_maibot | 29 | other | watch | 舞萌DX国服查分插件，支持B50、曲目查询、图片识分和水鱼OAuth授权 |
| 2236 | astrbot_plugin_mimotts | 29 | tts | watch | 基于小米 MiMo-V2.5-TTS 系列模型的语音合成插件，让 Bot 真正「开口说话」。  · 全自动发声：LLM 每条最终回复按概率自动合成语音，无需模型调用工具，零打扰接入 · 导演手记：支持 `(温柔 撒娇)` 风格前缀与 `[轻笑]`/`[叹气]` 等动作标签，情绪细腻可导演 · 三种音 |
| 2237 | sweet_ledger | 29 | memory | have | 自动识别并记录 bot 和用户之间的约定/承诺/欠账(奶茶、拥抱、火锅、电影…), 自动记账、兑现标记、查账对账。让 bot 记小账本, 说话算话。 |
| 2238 | astrbot_plugin_dglab_control | 29 | other | watch | 通过机器人控制郊狼 DG-LAB 硬件实现电击。插件内嵌 V3/V4 WebSocket Server，无需外部中转服务；支持扫码连接、一键开火、A/B 通道单独开关、查询已连接 APP。 |
| 2239 | astrbot_plugin_qq_custom_menu | 29 | other | watch | 用户通过在 AstrBot Web UI 配置，让 QQ 官方机器人展示自定义菜单。仅支持私聊场景。 |
| 2240 | astrbot_plugin_draw | 29 | image-gen | watch | 说说画师：给 QQ 说说/空间配图；支持 /画图、/生图 与 LLM 工具，多提供方/多模型、失败自动回退、负面词、去水印、最近作品页；兼容 angel_brush 的 providers.json。 |
| 2241 | astrbot_plugin_proactive_button | 29 | sticker | borrow | 为 AstrBot 提供一个插件页面：选择目标会话、挑选预设提示词，手动触发 Bot 主动发言。插件向目标会话注入一条内部消息，由 AstrBot 原生事件管线生成并发送， 因此人格、历史、工具、防抖、分段回复、表情包等行为都沿用原有规则。 |
| 2242 | astrbot_plugin_recallguard | 28 | memory | have | [仅 aiocqhttp] 监听指定用户撤回图片并将其转发到指定群聊。 |
| 2243 | astrbot_plugin_mp | 28 | info-push | have | 一个适用于最新版本moviepilot的小工具，支持搜索、订阅、消息转发等功能 |
| 2244 | mermaid | 28 | other | watch | 使用 LLM 将用户所输入的主题自动生成 Mermaid 模板并生成图片输出 |
| 2245 | astrbot_plugin_homeassistant | 28 | other | watch | 通过 Home Assistant REST API 查询设备状态、发现服务并控制智能家居设备。 |
| 2246 | astrbot_plugin_zm_qqgroupmgr | 28 | group-admin | have | 一款多功能QQ群管插件 你值得安装  :)  禁言 · 踢人封禁 · 敏感词 · 刷屏检测 · 广告拦截 · 进群审批 · 问题反馈 · 抽奖 · 群精华 · 文件分发 · 群公告迎送 · 跨群批量  安装后发送 `/zmhelp` 查看全部指令。完整文档见 [GitHub 仓库](https:// |
| 2247 | astrbot_plugin_mcguess | 28 | game | have | 在聊天中玩《我的世界》猜谜：按属性推理猜出方块、物品或生物，支持难度、提示、本地渲染的图片卡片与自然语言。 |
| 2248 | astrbot_plugin_savagetype | 28 | memory | have | 独立记忆中枢。身份源是 AstrBot 当前人格。采集时间线、沉淀事实、有护栏的矛盾覆盖；审查后的黑话释义与表达样本；支持聊天文本导入与 JSONL 换机备份。不改写人格文件。 |
| 2249 | astrbot_plugin_codex_radar | 28 | other | watch | 查询 Codex 雷达（codexradar.com / deng.codexradar.com）的模型智力效率数据与 72h IQ 历史曲线。支持指令：降智雷达、雷达历史。 |
| 2250 | astrbot_plugin_deepseek_balance | 28 | other | watch | 为 AstrBot 的 AI Agent 提供查询 DeepSeek API 账户余额的工具 |
| 2251 | astrbot_plugin_turn_gate | 28 | other | watch | 为 bot 之间的自动对话提供轮数限制，并提供缓冲轮数，让 bot 之间的对话丝滑结束，让你的 bot 不用忍受孤独，同时防止无限回环消耗 LLM 费用。 |
| 2252 | astrbot_plugin_dreamweaver | 28 | other | watch | 把群聊织成梦。Bot 白天静默收集群消息，每天深夜用 LLM 把当天群聊织成超现实梦境日记，次日早上发到群里；梦境带预言，支持解梦、回放、入梦次数统计。 |
| 2253 | astrbot_plugin_jev_router | 28 | memory | have | 基于 TypeSafe Jev / Google Gemini Decision 的多代理意图路由（放行式），支持动态切模型、人设追加、工具白名单与调用失败兜底，原生记忆与会话历史全程保活。 |
| 2254 | astrbot_plugin_automas_connect | 28 | game | have | 把本机 AUTO-MAS 的多脚本托管接进 AstrBot：QQ 指令查运行状态、启停任务； 面板里管托管项与账号、各脚本的任务参数、计划表、调度队列与定时、模拟器、 运行历史、全局设置与通知渠道，还有带运行范围勾选和实时日志的调度中心， 日常操作不用切回桌面端。 依赖 AUTO-MAS 的本地 R |
| 2255 | astrbot_plugin_local_tts | 28 | tts | watch | 在 AstrBot 启动时自动拉起本地 GPT-SoVITS 调音 TTS 服务（引擎 + 调音包装），AstrBot WebUI 的「GSVI TTS(API)」源配置 api_base 指向本服务即可使用。支持语速/音调/音量调音与参考音频音色克隆。 |
| 2256 | astrbot_plugin_hydrus | 27 | other | watch | 通过tag, 调用hydrus的API，返回随机图片。 |
| 2257 | at_somebody | 27 | other | watch | [仅限aiocqhttp] 在指定群内艾特(@)给定名单的用户+要通知的内容 |
| 2258 | astrbot_plugin_DGLab_poke | 27 | game | have | 将 DG‑LAB 郊狼（SOCKET v2 协议）集成进 AstrBot： 手机郊狼 APP 通过 WebSocket 直连本插件（局域网直连或内网穿透）， 群聊/私聊中有人戳机器人时，随机调节电击强度，保持数秒后自动归零。 内置控制面板（连接状态、二维码、手动电击），白名单/强度/时长/冷却等 关 |
| 2259 | astrbot_plugin_monsterHunterRise | 27 | other | watch | 群消息查询《怪物猎人 崛起：曙光》的素材获取、怪物弱点与分部位肉质、任务奖励，以及武器做法、武器详情与装饰珠配方，以图片卡片呈现。支持 OneBot v11 与 QQ 官方机器人。 |
| 2260 | astrbot_plugin_roleplay_skill_reader | 27 | personality | have | 将读取 skill 注册为大模型工具，让非管理员也能通过工具加载角色扮演技能包。 |
| 2261 | astrbot_plugin_devin_web_search | 27 | other | watch | 使用免费的devin账号让astrbot获取devin的web_search能力 |
| 2262 | astrbot_plugin_yys | 27 | other | watch | 阴阳师（Onmyoji）群聊助手：277 个式神/技能、70 个御魂、满暴与面板计算、御魂评分、克制关系；支持网易大神最新攻略检索（带图转发）、看图识别式神/御魂。由 deepseek-v4.1flash-1017 生成。 |
| 2263 | astrbot_agent_wechat_bridge | 27 | other | watch | 通过 agent-wechat 1.2.0+ Native /v1 HTTP & SSE API 将个人微信接入 AstrBot，支持跨服务器远程互联 |
| 2264 | astrbot_plugin_manxiaobai | 27 | image-gen | watch | 本插件对接 https://api.manxiaobai.online 的 OpenAI 兼容接口，为 AstrBot 提供 AI 画图能力：  - /画图 <描述>：生成图片（别名 /img） - 消息里附带图片（含 QQ 引用图片）时，自动作为参考图进行图生图，并按参考图比例出图 - /模型：查 |
| 2265 | astrbot_plugin_music_recommender | 27 | other | watch | 网易云与QQ音乐搜索、卡片分享及播放链接；支持搜歌指令和AI工具。 |
| 2266 | astrbot_plugin_msst | 27 | other | watch | MySekaiStoryteller 对接插件 - 调用宿主内置 AI 生成剧本并渲染视频 |
| 2267 | astrbot_plugin_dst | 27 | other | watch | 通过 Klei 公共大厅轮询自家饥荒联机版（DST）服务器，推送上线/离线和玩家进出； 支持本服玩家 KU_、物品 prefab、控制台指令检索。不展示 SteamID。 |
| 2268 | astrbot_plugin_x_tweet | 27 | kb-rag | have | 自动识别群内与私聊的 X / Twitter 链接，解析正文、作者与图片视频并发送，可给原消息贴表情回应、 按需选择图片尺寸（含原图），自动翻译推文； 引用 / 回复的主贴会单独发一条消息并完整解析，楼中楼默认逐层用「引用回复气泡」发送并补一条合并转发汇总 （可在配置里改成只发气泡或只发合并转发，后 |
| 2269 | astrbot_plugin_random_illustration | 27 | nsfw | exclude | 已屏蔽18+内容，调用了nekosapi的api，多数据源动漫插画插件，支持中文标签搜索、多标签组合、数量控制、用户冷却与失败重试。 |
| 2270 | astrbot_plugin_cost | 27 | platform | have | 基于本地 provider_stats 统计 token 用量，支持 QQ、Telegram、Discord、飞书、WebChat 等 AstrBot 平台，以及 DeepSeek、OpenAI、Claude、Gemini、Qwen 等模型；按价目表估算费用，支持按自然日查看单日用量（今天从 00: |
| 2271 | astrbot_plugin_auto_message | 27 | other | watch | 每日定时发送特定文本消息的插件 |
| 2272 | astrbot_plugin_twitter_rss | 27 | info-push | have | 按照 Twitter/X 订阅 账号或标签 获取推文，支持 AI 判断标签过滤、推文卡片渲染（含翻译）+原图单独发送，以及《今日要闻》24小时精选长图推送。 |
| 2273 | astrbot_plugin_model_scheduler | 27 | other | watch | 按时间段或会话类型自动切换 LLM 模型，把贵的模型留给需要的时候，其余时间用便宜模型。  - 时间段规则：到点切换、区间保持、支持跨夜（如 23:00–07:00 用便宜模型） - 场景分流：群聊用便宜模型、私聊用强模型，无需逐个群配 umo - 空闲再切：会话活跃时不切，保留 prompt 缓存 |
| 2274 | astrbot_plugin_paradise | 27 | personality | have | 她自己的天堂。温柔不是一句形容词，是几件能做出来的事： 从他话里认出累 / 忙 / 难过 / 不舒服，提前一步；不连着抛问题； 他说错的小事不纠正；收场之前留半句（话头）；记住他那天说话的语气；回复前稍稍慢一点。 全部按 QQ 分开存，不读任何其它插件的数据；注入走临时内容块，不改 system_p |
| 2275 | astrbot_plugin_group_identity | 27 | other | watch | 为群聊背景和当前输入标注发送者 QQ、引用原作者和提及对象，改善多人共享上下文的归属混淆。 |
| 2276 | astrbot_plugin_sender_context | 27 | personality | have | 把当前发言人的 QQ 号/昵称/场景作为临时用户内容提供给模型，让"按人分流"的人格设定有依据 |
| 2277 | astrbot_plugin_bili_card | 27 | media-parse | borrow | 自动识别聊天中的 B 站链接（视频/番剧/直播/专栏/动态/UP空间/音频/评论），渲染成图文卡片并附可复制链接。卡片由 AstrBot 自带的文转图服务出图，插件本身不调用任何 AI 模型、也不需要额外安装渲染依赖。 |
| 2278 | astrbot_plugin_timer | 27 | other | watch | 让bot能够定时执行指令。 |
| 2279 | astrbot_plugin_user_inject | 26 | other | watch | 根据用户id动态注入system_prompt |
| 2280 | astrbot_plugin_lark_send_patcher | 26 | platform | have | 通过猴子补丁的方式，优化了飞书Lark适配器下，机器人发送的消息引用太频繁的问题。现在飞书下所有的机器人回复从引用消息变更为直接发送。插件可能会随着astrbot本体版本更新，涉及到lark_adapter和lark_event重大更新时失效。 |
| 2281 | msgdistributor | 26 | other | watch | 根据消息平台-群id/好友名/好友id动态选择服务提供商 |
| 2282 | Getcwm | 26 | other | watch | 刺猬猫小说相关插件,获取小说信息与定时更新提醒。 |
| 2283 | astrbot_plugin_comfyui_video | 26 | other | watch | 对接 ComfyUI 视频工作流，支持 T2V、I2V 和 R2V。 |
| 2284 | astrbot_plugin_lolhelper | 26 | game | have | 联盟星枢：英雄联盟 · 云顶之弈助手（星枢系列，数据来自 OP.GG 官方 MCP）。 英雄出装与克制、海克斯大乱斗、版本梯队、召唤师战绩、电竞赛程 / 赛况 / 积分、云顶阵容 / 英雄出装 / 装备 / 强化符文。 AI 点评（单局、近期诊断、比赛单局与整场）和群玩法（日榜周榜、群友播报、PK、 |
| 2285 | astrbot_plugin_anime_cutout | 26 | other | watch | 基于 ISNet 的动漫人物一键抠图插件。发送图片并附带 /cutout 即可去除背景，支持透明背景、白底、遮罩与对比图输出，内置模型管理与自动下载。 |
| 2286 | astrbot_plugin_checkin_shop | 26 | platform | have | 一个完整的"打卡赚积分 + 积分兑换"插件： * 指令：/打卡 /商店 /我的积分 /积分榜 /兑换商品 <名称> /绑定邮箱 <邮箱> /商店帮助 * 打卡积分规则（固定 / 随机区间 / 自定义列表 + 连签奖励）可在 WebUI 配置，插件页与配置页互通 * 商品在 WebUI 插件页里可视化 |
| 2287 | astrbot_plugin_keyword_filter | 26 | group-admin | have | 对话输入的敏感词过滤，命中后终止对话并回复提示。支持按群号和 QQ 号豁免，管理员自动豁免，匹配时忽略大小写和分隔符绕过 |
| 2288 | astrbot_plugin_roll | 26 | kb-rag | have | 不满意 bot 的回复就发一个 /roll：插件会用同一段上下文重走一遍正常的回复流程（人格、工具、知识库、流式、转图/TTS 都在），QQ(aiocqhttp) 下还会撤回旧的平台消息，其它平台自动跳过。支持管理员 / 所有人权限切换。 |
| 2289 | astrbot_plugin_video_resolver | 26 | media-parse | borrow | 小红书无水印原图解析; B站视频解析; 抖音视频/图文解析; 微博图文/视频解析; X 图文/视频解析 |
| 2290 | astrbot_plugin_human_voice | 26 | tts | watch | 让 QQ 聊天角色按人设表达态度和情绪，记住谈话线索，并维护每个人的好感度与人物关系。 |
| 2291 | astrbot_plugin_wowsguess | 26 | game | have | 在聊天中玩《战舰世界》猜船游戏，按舰船属性反馈猜测结果。 |
| 2292 | astrbot_plugin_qimen | 26 | other | watch | 奇门遁甲断卦插件：根据用户问题和当前时间起局排盘，按古法给出吉凶判断与实操建议。 |
| 2293 | astrbot_plugin_qq_globalid | 26 | other | watch | 全局接管官方渠道，自动把 openid 改写为真实 QQ 号，其他插件零适配 |
| 2294 | astrbot_plugin_random_gallery | 26 | other | watch | 用户发送可配置指令后随机发送本地图库图片，并提供 AstrBot 内置 WebUI 图库管理。 |
| 2295 | astrbot_plugin_dota2assistant | 26 | other | watch | Dota2 助手插件，查询玩家战绩、英雄数据、物品信息、比赛详情、实时比赛和职业赛事。 |
| 2296 | astrbot_plugin_bilibili_push | 26 | media-parse | borrow | 一个 Bilibili 与 AcFun 视频被动解析与订阅推送插件，支持扫码登录持久化 Cookie、视频/图文双发送策略，原生适配 QQ 官方机器人 WebSocket。 |
| 2297 | astrbot_plugin_wd_ballistic | 26 | game | have | 为《WARDOGS》提供迫击炮炮位与目标位的方位、距离计算。 支持 /wd bc 指令和多种 x/y 坐标输入格式，并会按用户缓存炮位 105 分钟。 |
| 2298 | astrbot_plugin_reply_rate | 26 | game | have | 给每个群单独设定主动接话的概率，唤醒窗口 + 概率抽签 + 连击上限，命中才让 AI 参与聊天。 |
| 2299 | astrbot_plugin_bili_feed | 26 | media-parse | borrow | 按 B站 UID 订阅 UP 主更新，后台定时轮询并主动推送到订阅时所在的会话。  - **可分别开关「视频」与「动态」**：订阅时用 `/bili订阅 <UID> 视频` 只关注投稿，   用 `/bili开关 <UID> 动态 关` 随时关掉不想看的类型 - **检测时间可配置**：按固定间隔（ |
| 2300 | astrbot_plugin_image_search | 26 | other | watch | 给 LLM 一个 `search_image` 工具：按关键词联网搜索图片，并把图片直接发送到会话。  - **零配置可用**：默认用 360 图片公开接口，不需要任何 API Key，国内可直连 - **图源可自定义**：支持任意返回 JSON 的图源（Bing / Pixabay / 自建图床） |
| 2301 | astrbot_plugin_dida_improved | 26 | other | watch | 连接 Dida365（滴答清单）Open API，支持查询、创建、完成、更新、移动和删除任务；正确处理收集箱（Inbox）任务；提供指令和 LLM 自然语言两种交互方式。 |
| 2302 | astrbot_plugin_github_monitor | 26 | other | watch | 定时监控 GitHub 仓库的 Release、Issue、PR、Star、Commit 动态，并主动推送到已绑定的 AstrBot 会话。 |
| 2303 | astrbot_plugin_ima_kb | 26 | kb-rag | have | 让机器人查腾讯 ima 知识库（含订阅库）里的专业资料。用浏览器登录态调 ima 内部接口，命中后由模型用自己的口吻转述；支持自定义提问提示词与答案字数上限，带超时降级、结果缓存与 markdown 清洗，适合群聊场景 |
| 2304 | astrbot_plugin_easygreeting | 26 | proactive | watch | 在自定义时间窗口内随机生成并发送早晚安问候，支持群聊和私聊独立白名单。 |
| 2305 | astrbot_plugin_omni | 26 | other | watch | 把零散的娱乐与工具小功能集中到一个插件里，每个功能都有独立开关 |
| 2306 | astrbot_plugin_train_ticket_search | 26 | other | watch | 火车票查询插件：聚合数据/接口盒子API查票、锁定、余票提醒、缓存快查与强制更新 |
| 2307 | art_journal_notonly_mais | 26 | devtools | watch | 主要针对 AstrBot 兼容开发的多模型图片生成插件，重点支持并专项优化 ComfyUI 工作流调用与可视化编辑。 |
| 2308 | astrbot_plugin_move3d | 25 | other | watch | 将用户引用的图片转换为简笔画风格裸眼3D图的 AstrBot 插件。 |
| 2309 | asbot_plugin_furry-API-hy | 25 | other | watch | 调用趣绮梦云黑API的群黑云查询踢出还有进群自动检测黑云有问题自动踢出的插件 |
| 2310 | astrbot_plugin_schedule_injector | 25 | media-parse | borrow | 在 LLM 请求前注入日程/目标上下文，并在回复后解析隐藏 JSON 更新日程。支持白名单、每日目标与微目标 |
| 2311 | saris_fish | 25 | game | have | 赛博钓鱼。需要前置插件: astrbot_plugin_saris_db |
| 2312 | astrbot_plugin_signin | 25 | game | have | 世界计划风格的签到打卡插件 |
| 2313 | astrbot_plugin_openai_image_generation | 25 | other | watch | Generate images with OPENAI_API_KEY and gpt-image-2.6. Supports text-to-image and image edits.  The plugin uses Responses API by default, but also all |
| 2314 | astrbot_plugin_pdd_monitor | 25 | other | watch | 用关键词盯拼多多感兴趣的商品的最低价，跌破历史最低价时主动推送到群；群内 @机器人 说「今日行情」查看全部监控项的现价与涨跌。BUG/技术支持联系：QQ：2676212264（邮箱同）；Github：https://github.com/HamsterKun/astrbot_plugin_pdd_m |
| 2315 | astrbot_plugin_doudizhu | 25 | game | have | 在群里和群友开一局斗地主：创建游戏、上桌、抢地主、出牌、结算积分，支持每日低保与胜率统计。 |
| 2316 | astrbot_plugin_autonomous_attention | 25 | personality | have | 基于主动兴趣模型和主模型注意力工具的会话级注意力内核：维护兴趣与人格边界，并在检查点到达时主动观察群聊、决定参与或跳过。 |
| 2317 | astrbot_plugin_media_manager | 25 | other | watch | 管理模型会话中的媒体资源，提供图片历史轻量化、回看原图、动图九宫格预览、群聊图片缓存及自动清理。 |
| 2318 | astrbot_plugin_pansou | 25 | other | watch | 对接 PanSou 网盘搜索，支持搜索、链接验证和类型筛选。 |
| 2319 | astrbot_plugin_lurk | 25 | other | watch | 记录群成员最后发言时间，定时发送沉睡摘要，支持20人分页、分类筛选、名单图片生成、合并转发及可选自动踢人。 |
| 2320 | astrbot_plugin_bookkeeping | 25 | other | watch | All-in-AI 智能记账插件，提供丰富的 LLM 工具与美观的 WebUI 仪表盘 |
| 2321 | astrbot_plugin_auto_reload | 25 | other | watch | 为 AI agent 设计的插件管理与自主热重载——AI 改完代码自己重载、自己确认生效到哪一层，回执直接返回给模型；自证回执、生效度评分、平台实例换手、陈旧任务回收、子代理三件套，人类同样可用 /plugin 指令操作 |
| 2322 | astrbot_plugin_cherry_remote | 25 | other | watch | 远程操控连接器：桥接 AstrBot 与远程电脑 App，通过 AI 工具实现远程执行指令（含截屏与摄像头拍照）。 |
| 2323 | astrbot_plugin_mc_update | 25 | other | watch | 自动检测 Java 版我的世界版本更新，通过 LLM 总结并推送到群聊，支持 QQ 官方机器人及多平台。 |
| 2324 | astrbot_plugin_qq_operater_shell | 25 | other | watch | 【仅QQ】调用QQ接口来实现QQ群操作管理等行为 |
| 2325 | astrbot_plugin_jitrl | 25 | memory | have | 基于 JitRL（Just-in-Time Reinforcement Learning）让 Agent 在推理时持续自我进化：记录经验轨迹、估计动作优势、在闭式解上调制策略，按 AstrBot 平台实例隔离学习并自适应适配器的 self_id 变化，无需梯度更新、无需微调。 |
| 2326 | astrbot_plugin_offline_reply | 25 | tts | watch | 监听 NapCat 与 AstrBot 的 WebSocket 连接，断线重连后通过 NapCat 的 get_friend_msg_history 扩展 API 拉取断线期间的私聊历史消息，筛选出未回复的消息并注入 AstrBot，让机器人像正常收到消息一样逐条回复。支持文字、图片、语音、视频、文 |
| 2327 | douyin_dm_mover | 25 | media-parse | borrow | 把抖音 Bot 账号收到的私信视频/分享卡片，自动搬进指定 QQ 群。 |
| 2328 | astrbot_plugin_fatfish_groupadmin | 25 | group-admin | have | 群主 / 管理员说「安静点」它就安静，群友说「别接我的话」它就不接，被禁言就不发。细节和配置见 README。 |
| 2329 | astrbot_plugin_steam_wishlist | 25 | game | have | 监控 Steam 愿望单/单游戏价格,折扣达到阈值或史低时自动推送到会话 |
| 2330 | astrbot_plugin_model_switch | 25 | other | watch | 根据消息模态自动切换多模态/文本 LLM Provider，并支持备用模型故障转移。 |
| 2331 | ro_identity_card | 25 | other | watch | 生成磨砂/液态玻璃效果的身份卡片图片 |
| 2332 | astrbot_plugin_trumpwatcher | 25 | info-push | have | 监控公开归档源中的特朗普 Truth Social 动态，支持跨平台 UMO 订阅、AstrBot Provider 中文翻译总结、WebUI 订阅管理、Cron 自动抓取、SQLite 跨重启去重与失败重试， 并在平台不支持合并消息或模型不支持图片时自动降级。 |
| 2333 | astrbot_plugin_group_invite_guard | 25 | group-admin | have | 让 LLM 根据人格设定判断是否通过邀请加群，并识别私聊里的加群邀请；支持被踢、被禁言后自动拉黑报复。 |
| 2334 | astrbot_plugin_group_image_saver | 25 | other | watch | 自动保存群聊和好友发送的图片，支持备注功能、按群号和日期分类归档、群组/好友白名单黑名单过滤和路径警告，在飞牛系统上安装本插件后，**无需开启远程访问**，即可把聊天图片上传到飞牛 NAS。 |
| 2335 | astrbot_plugin_punchline_analyzer | 25 | sticker | borrow | 智能解析群聊发言、图片表情包、短视频、合并转发聊天记录及分享中的幽默笑点与梗，风格源自经典「ai沈阳美食家」项目。 |
| 2336 | astrbot_plugin_ShareholderPerks | 24 | info-push | have | 股东回馈信息取自巨潮资讯网，帮助各位股东们或是潜在股东们薅羊毛。 |
| 2337 | asbot_plugin_furry-API | 24 | other | watch | 调用趣绮梦云黑API查询用户的插件 |
| 2338 | astrbot_plugin_github_analyzer | 24 | other | watch | 分析 GitHub 用户的近期活动，并生成一张精美的“内卷”报告卡。 |
| 2339 | moviepilot_sub | 24 | info-push | have | MoviePilot 订阅插件 |
| 2340 | mccloud_command | 24 | other | watch | 用于修改插件命令的工具，支持备份和恢复，仅限管理员使用。/cmd 查看帮助 |
| 2341 | mccloud_deepseek | 24 | other | watch | 可选择是否过滤推理模型的思考内容，仅支持MC云API。购买MC云服务器云电脑可享受免费API不限制支持deepseek-r1 v3模型。https://idc.stay33.cn/  [版本要求 >= v3.4.17] |
| 2342 | astrbot_plugin_pi_agent | 24 | other | watch | Yezi 与 Cz 维护的开源 AstrBot Pi Agent 插件，支持独立后台任务、原生会话读取、任务恢复和普通回复链路终态处理。使用前必须启用 AstrBot 内置 Agent 与工具调用。 |
| 2343 | astrbot_plugin_l4d2_query | 24 | other | watch | 查询L4D2服务器状态，支持详细查询和综合查询。 |
| 2344 | astrbot_plugin_schedule_tracker | 24 | platform | have | 通过 ICS 日历追踪 QQ 群友课表、当前上课状态和每日上课时长。 |
| 2345 | astrbot_plugin_remote_control | 24 | ssh-exec | exclude | 通过SSH远程控制Linux服务器；注册 ssh_exec / send_file / save_file；仅 QQ 平台；白名单与危险命令拦截；文件仅宿主路径，路径层仅黑名单 |
| 2346 | astrbot_plugin_opencode_usage | 24 | other | watch | 查询 opencode.ai 的 Go 套餐使用量、各模型输入/输出 token 与费用，支持纯文本与 opencode 风格 HTML 图片输出。 |
| 2347 | astrbot_plugin_group_world | 24 | personality | have | 群聊世界 V1.13.5 是一套面向 AstrBot 的群聊生态插件，作者：ysgl。 它以群世界 + 全局玩家角色的双层 SQLite 数据模型为基础，提供玩家成长、金币/钻石经济、体力、职业、探索、随机事件、宠物、装备、商店、每日任务、成就、排行榜、小游戏、世界 Boss、管理员工具、详细数据中 |
| 2348 | astrbot_plugin_akinator | 24 | game | have | 基于 Akinator 网络天才猜人物游戏，通过一系列问题猜出你心中所想的人物。支持函数调用。 |
| 2349 | astrbot_plugin_embodiment_bridge | 24 | memory | have | 凝心溯溪-临是面向虚拟陪伴与具身 AI 的 AstrBot 桥接插件。它将 VR/MR、 桌面虚拟角色和实体设备接入 AstrBot 正式消息链，把用户的语音、触碰与空间信息 交给人格、记忆、知识和工具系统处理，再将回复、语音、动作、表情与注视意图实时返回客户端。 |
| 2350 | astrbot_plugin_group_interject_v2 | 24 | memory | have | 让 Bot 像群友一样自然接话，而不是每句都回。插件持续观察群聊消息，在出现自然切口、 冷却满足且没有定向消息打断时，才克制地插一句。默认只判定不发送，可灰度、可调频； 支持 @bot、引用和唤醒昵称的定向处理，可选图片描述与长期记忆写入，附带 WebUI 控制台。 不改 AstrBot 核心。 |
| 2351 | astrbot_plugin_weather | 24 | info-push | have | 免费天气查询，基于 wttr.in 公开服务，无需 API Key、无需注册、零成本。支持当前实况、三天预报、一行速览和 PNG 天气图，中文地名/机场码/坐标都能查，可用命令或 LLM 自然语言调用。 |
| 2352 | astrbot_plugin_sysinfo | 24 | other | watch | 读取服务器实时运行状态并输出：CPU 总使用率、每个核心使用率、内存占用、磁盘存储、网络流量、负载与温度等。 |
| 2353 | chat_bridge | 24 | other | watch | 群聊转发插件：在目标群登记会话、在源群绑定转发规则后，源群消息会实时推送到目标群。支持一个源群转发到多个目标群、文本与图片转发；转发内容由机器人发送，不会形成转发回环。 |
| 2354 | astrbot_plugin_life_sim | 24 | other | watch | 在群聊/私聊中模拟转生到任意世界的一生。由我代为叙述,独立上下文避免污染和过长。 |
| 2355 | astrbot_plugin_redpacket_notify | 24 | payment | exclude | QQ红包提醒插件，群里有红包时自动私聊通知你 |
| 2356 | astrbot_plugin_chat_limiter | 24 | other | watch | 限制用户与AI聊天的白名单插件。白名单用户可在群聊和私聊中使用，非白名单用户仅限群聊使用。 |
| 2357 | astrbot_plugin_group_pet | 24 | game | have | 群宠物养成插件：领养随机品种的宠物，喂食、玩耍、打工、冒险赚金币升级；新增商店道具、每日签到、每日任务、图鉴与成就，宠物会随时间变饿变无聊，饿太久会离家出走并主动提醒。 |
| 2358 | astrbot_plugin_chat_history_png | 24 | group-admin | have | 自动将 OneBot QQ 合并转发消息渲染为带头像、回复、图片、视频封面、Emoji 和嵌套记录的 QQ-like PNG；支持可选的多模态 AI 逐图审核，对不合规或无法判断的图片进行模糊遮罩与安全占位。 |
| 2359 | astrbot_plugin_defect_kb | 24 | kb-rag | have | 杀戮尖塔「故障机器人(The Defect)」人格知识库——纯 BM25 关键词检索，无需 embedding。身份锚点与禁忌每条消息自动注入，卡牌/梗/场景条目通过 defect_kb_search 工具按需检索。  **使用方法**：将文本条目放入 data/plugin_data/astrbo |
| 2360 | astrbot_plugin_tts_wakeword | 24 | tts | watch | 通过唤醒词触发的语音合成插件。消息以「小助手」等唤醒词开头时，插件会调用 阿里云百炼（DashScope）的 Qwen-TTS 模型生成音频，并作为语音消息发送到当前会话。  功能特性： - LLM 预处理（文本导演）：先由大模型把消息改写成更自然的朗读台词，   支持 free-style 指令遵 |
| 2361 | astrbot_plugin_arknights_toolbox | 24 | game | have | 《明日方舟》的几个日常小工具，装在一个插件里，**默认只开最安全的那两个**。  **基建换班提醒**（默认开启）  - 按你填的三班时刻，在每班换班前推一条提醒（当前班次、下一班几点开始） - 提前量可调，默认提前 10 分钟 - 可以导入一图流 / MAA 格式的排班表，提醒里直接告诉你「这一班 |
| 2362 | astrbot_plugin_festival_greeter | 24 | personality | have | 使用指定的 AstrBot 人格生成群聊祝福，支持节日推送及按公历或农历配置生日。 |
| 2363 | astrbot_plugin_vtube_studio | 24 | other | watch | vtube_studio连接支持 |
| 2364 | astrbot_plugin_bilibili_hand | 24 | media-parse | borrow | B站之眼的下游插件。只操作当前会话里 B站之眼上一次刚看过的视频： 点赞由 bot 自主决定；投币、收藏由指令触发；评论由指令或自然语言触发， 内容由 bot 自己生成。默认仅管理员和白名单可用，开始/结果都有反馈。 |
| 2365 | astrbot_plugin_nikke | 24 | media-parse | borrow | 订阅 bilibili 与 BlaBlaLink 国际服官方动态，支持 QQ 群图文推送、翻译、活动提醒，以及无需登录的角色、技能、基地等级与红球查询。 |
| 2366 | astrbot_plugin_qzone_ultra_ce | 24 | info-push | have | QQ空间Ultra CE（Community Edition）：基于上游 0.9.0（commit 4221713）修改并独立发布的版本。 新闻说说由原本仅支持 Google News RSS 扩展为多源可选（IT之家、中新网、奇客Solidot、极客公园、爱范儿、少数派、Google News）， |
| 2367 | astrbot_plugin_qq_card | 24 | tts | watch | 为社区分享和点歌生成带标题、封面、可点击跳转的 QQ 卡片，统一配置签名 Token。 |
| 2368 | community_digest | 24 | group-stats | borrow | 让 AI 机器人按群友和好友的兴趣，定时分享 B站、小红书和小黑盒的精选内容，并附一句短评。 |
| 2369 | astrbot_plugin_wakeword_keeper | 24 | personality | have | 当角色名或昵称被用作 AstrBot 唤醒词时，AstrBot 可能在触发后将其从当前消息中剥离。 本插件会在 LLM 请求发出前自动恢复用户配置的唤醒词。 支持私聊、群聊和多个自定义唤醒词。 |
| 2370 | astrbot_plugin_video_sora2 | 23 | other | watch | astrbot_plugin_video_sora的 fork 版本支持自动获取 ChatGPT AccessToken |
| 2371 | astrbot_plugin_message_bottle | 23 | other | watch | 基于 @wuyan1003 的漂流瓶插件重构并更改存储方案 |
| 2372 | qltask | 23 | other | watch | 青龙面板任务管理插件 |
| 2373 | astrbot_plugin_gallery | 23 | sticker | borrow | 群内图片画廊：上传、查看、查重、管理表情/梗图，支持别名、模式、封面、撤销上传，用户可创建画廊。 |
| 2374 | astrbot_plugin_usage_stats | 23 | other | watch | 按插件和模型统计文本调用、Token 用量与估算费用。 默认不采集，在「用量统计」页面开启；也可用 /usage 查用量。 |
| 2375 | astrbot_media_saver | 23 | sticker | borrow | 自动获取并保存群内所有人发送的图片和视频（可选文件），按群组/日期组织存储，支持跳过动画表情与 GIF 表情包。 |
| 2376 | astrbot_plugin_helper | 23 | other | watch | 辅助清理缓存插件 |
| 2377 | astrbot_plugin_daily_briefing | 23 | info-push | have | 在订阅的 OneBot QQ 群每日播报日期、周末和法定节假日倒计时。 |
| 2378 | astrbot_plugin_amap | 23 | info-push | have | 把高德地图开放平台接进 AstrBot，并配一个手机端 App：agent 想查位置时才向手机下发一次定位请求（不常驻、不耗电），手机取 GPS 回传后插件自动做坐标转换与逆地理编码，返回可读的中文地址。提供 14 个 agent 工具：查手机在哪、当地天气、地址转坐标、坐标转地址、POI 搜索、路 |
| 2379 | astrbot_plugin_subnexus | 23 | other | watch | SubNexus 是面向 SUB2API 的 AstrBot 运维控制插件，提供受签名保护的只读运营数据、脱敏分析、报告调度，以及严格双重确认的受控写操作。 |
| 2380 | cyber_boss | 23 | game | have | 小猪养成计划 · 全群共斗养成小游戏。用 /砍猪 攻击共享 Boss，触发暴击、闪避、反击、心软与神器事件；每刀掉落金币，击杀按贡献、MVP 与补刀发放猪神印记。内置 56 件商品、武器/副手/护具/饰品四栏自由混搭、消耗品、猎手阶位、称号、排行与名人堂。/boss 商店 默认一张长图浏览完整目录， |
| 2381 | astrbot_plugin_admin_card | 23 | group-admin | have | 让普通群友能体验有限期的群管理员身份，支持手动发卡/撤卡/抽卡、等级达标自动发卡、周期随机轮换管理员。 |
| 2382 | astrbot_plugin_remote_link | 23 | image-gen | watch | 云信互联：让云端 AstrBot 通过反向隧道调用你本地电脑上的模型（ComfyUI 任意工作流 / 本地 LLM / Shell） |
| 2383 | astrbot_plugin_napcat_history_exporter | 23 | sticker | borrow | 通过 NapCat / SnowLuma（OneBot v11 扩展 API）将历史聊天记录（群/私聊）导出为 JSONL 文件，图片/表情等用占位符替换；支持定时循环增量导出（默认 120s）与按需触发两种模式；v1.5.0 起支持多 bot（多 aiocqhttp 实例）分别/选择性归档，后端  |
| 2384 | astrbot_plugin_group_link_digest | 23 | group-stats | borrow | 面向 QQ 群的质量优先日报插件，支持链接全文理解、图片识别、跨来源聚类、 群内讨论总结、可点击 DOCX、Token 统计和安全的定时投递。 |
| 2385 | astrbot_plugin_phone_spy | 23 | platform | have | 允许大模型调用函数工具，通过 iCloud 邮件自动化触发 iPhone 截图回传，并进行视觉分析。 |
| 2386 | astrbot_plugin_qq_group_manager | 23 | group-admin | have | 一款由 AI 辅助制作的 QQ 群管家插件，支持自动同意加群、LLM 智能迎新送辞、以及机器人进群邀请的管理员审核。 |
| 2387 | astrbot_plugin_random_events | 23 | sticker | borrow | 管理员控制的定时或随机群互动，支持文字、提问和本地菲比表情。 |
| 2388 | astrbot_plugin_exclusive_master | 23 | other | watch | 专属主人防打扰护盾：除了主人以外，任何斜杠指令、#sl指令或试图触发静回复的话语一律底层掐灭，彻底静默 |
| 2389 | astrbot_plugin_volt_toy | 23 | game | have | 用指令电群友的群聊玩具，统计口径是「度」。  功能： - `/zap @某人` 电别人，`/zap` 电自己（0.8 倍效率） - 单次同时掷电压 V 与电量 Ah，按度（kWh）累计，附电费折算 - 连击升档、暴击、过载跳闸；超出单目标每日上限只记失败、不加电量 - 榜单：度数榜、被电榜、峰值榜、 |
| 2390 | astrbot_plugin_ba_wiki | 23 | personality | have | BA 角色技能数值与完整面板（等级/星级/装备/专武/能力解放）、大决战榜单前列真实配队（什亭之匣）、B 站攻略视频链接；支持七语言名称与绰号，输出国服译名。 |
| 2391 | astrbot_plugin_pixez | 23 | other | watch | 基于 PixEz 交互与 Pixiv App API 能力实现的 AstrBot 插件。 支持搜索、推荐、排行、作品与小说、收藏、关注、评论、下载、 Ugoira、SauceNAO、Pixivision、历史、屏蔽和群聊链接预览。 |
| 2392 | astrbot_plugin_persona_card | 23 | kb-rag | have | 人格、音色、聊天模型、知识库、表情包（可多选）一键绑成角色卡，应用到会话即时生效；支持存为卡、解绑、说说板块。 |
| 2393 | astrbot_plugin_spark_analyze | 23 | other | watch | 自动识别 Spark profile 链接，提取 Minecraft 性能热点并交给 LLM 分析。 |
| 2394 | astrbot_plugin_hlymcn_signin | 22 | devtools | watch | 一个为HLYM社区定向开发的服务器工具插件，提供基础的查询功能，如果需要使用捆绑的更多功能需要自行适配后端系统 |
| 2395 | astrbot_plugin_qqrecord | 22 | other | watch | 将群消息以“内容【群昵称】”的形式及时进行会议记录。调用命令 `/record [limit]`返回当前会话的最近 N 行 |
| 2396 | astrbot_plugin_goldsearch | 22 | other | watch | 获取国内金首饰价格。 |
| 2397 | astrbot_plugin_top_chehui | 22 | group-admin | have | [仅 aiocqhttp] 自动撤回上一条触发机器人的消息 |
| 2398 | astrbot_plugin_renjian | 22 | other | watch | 《我在人间凑数的日子》散文随机语录。 |
| 2399 | astrbot_plugin_alist | 22 | other | watch | 一个用于与 Alist 交互的 AstrBot 插件，提供文件搜索、存储管理等功能。 |
| 2400 | Translation | 22 | other | watch | 通过调用百度翻译 API 接口实现翻译文本 |
| 2401 | lottery | 22 | other | watch | 抓阄插件，使用/抓阄 指令抓阄，教程https://github.com/MashiroSaber03/lottery |
| 2402 | public_servant | 22 | other | watch | 帮助考公人随时背书的插件(?) |
| 2403 | astrbot_plugin_arxiv | 22 | info-push | have | 按关键词/作者/分类检索 arXiv 论文，支持订阅每日推送最新论文，并可用 LLM 翻译标题。无需任何 API Key，安装即用。 |
| 2404 | astrbot_plugin_stardust_diary | 22 | memory | have | 群聊与私聊均可使用：攒满100条消息后AI自动整理，提炼人物画像键值与要点存入长期记忆，平时不动，检索到相关时才注入上下文。按会话隔离。 |
| 2405 | astrbot_plugin_soft_whitelist | 22 | other | watch | 高优先级 OneBot 消息白名单，支持群聊、好友私聊和临时会话分离配置，以及管理员命令和非白名单自动回复。 |
| 2406 | astrbot_plugin_capability_bridge | 22 | media-parse | borrow | 扫描已安装插件，通过模型生成并校验适配规则，让机器人理解用户需求、解析参数并调用原插件完成任务。支持能力检索、适配缓存和插件更新后重新适配。 |
| 2407 | astrbot_plugin_youtube_notifier | 22 | info-push | have | 订阅 YouTube 频道，直播上播/下播与新投稿以图片形式推送。支持 Atom feed（任意频道，无鉴权）、LiveBroadcasts API（OAuth，自己的频道）与 WebSub 实时推送三种数据源。 |
| 2408 | astrbot_plugin_qq_profile | 22 | other | watch | 在 QQ 群内管理用户档案：绑定账号后可为档案绑定一个网站，并查询域名的 WHOIS、存活状态、响应延迟、服务器归属地、ICP 备案与 SSL 证书， 最后按六维加权模型给出 5 分制评分并生成排行榜。 支持 /绑定账号、/查询档案、/绑定网站、/更新网站、/解绑网站、 /查询域名、/查询备案、/查 |
| 2409 | astrbot_plugin_favour_card | 22 | personality | have | Favour Ultra 展示扩展：随机角色图片、人工裁剪管理、阶段多台词与会话排行。 |
| 2410 | brick | 22 | group-admin | have | Koishi brick 的 AstrBot 移植版：烧砖、拍人、随机拍人、管理员保护、烧砖失败概率、每日签到、群白名单与禁言失败降级。 |
| 2411 | astrbot_plugin_heart_sunny | 22 | other | watch | 心晴助手 - 心理测评与情绪关怀工具。支持 SDS, SAS, SCL-90 等 12 种专业量表测评。 |
| 2412 | paopao_life_bridge | 22 | memory | have | 生活桥不生产记忆，只做翻译： 1. 向「我会永远陪着你」注册官方外部记忆 Provider，收下它的日记、梦境和主动消息，    以 bot_self 可见性写进「我会牢牢记住你」，于是她的生活成了别的端也能读到的经历； 2. 给 B站 AI Bot 提供只读接口，按场合（评论区 / 私信）读到中枢 |
| 2413 | astrbot_plugin_cloudbackup | 22 | other | watch | 每天定时自动打包备份机器人的数据并上传至缤纷云 |
| 2414 | astrbot_plugin_daily_summary | 22 | other | watch | 统计当日发言排行，并用LLM生成趣味总结，支持手动触发和定时推送。 |
| 2415 | astrbot_plugin_faq | 22 | kb-rag | have | 群管理员维护问答知识库，群友正常聊天提问时自动命中秒回，没命中时可由 AI 参考知识库兜底回答。 /faq 添加 问题 => 答案 一句话建库，问题支持多个触发别名（群规\|入群须知 => ...），也可引用一条消息作为答案。 支持模糊匹配（"服务器ip是多少" 也能命中 "服务器ip"）、命中冷却防 |
| 2416 | astrbot_plugin_group_var_commands | 22 | other | watch | 会话绑定 + 自定义变量分组 + 全局函数模块 + 指令绑定 Python 脚本，带 QQ 式可视化控制面板 |
| 2417 | cloudrank | 22 | other | watch | 词云与排名插件(CloudRank)是一个文本可视化工具，能将聊天记录关键词以词云形式展现，并显示用户活跃度排行榜，支持定时或手动生成。本版本为社区维护修复版，修复定时词云任务因漏await导致全群被跳过的问题（原issue |
| 2418 | astrbot_plugin_daily_calorie_intake | 22 | other | watch | 通过多模态模型识别食物图片、对话描述饮食，自动记录每日热量摄入并计算剩余额度。 |
| 2419 | astrbot_plugin_qq_autokick | 22 | group-admin | have | QQ 官方机器人（Websocket）群管理插件。  - 自动处置：刷屏、复读、关键词、广告链接，可分别配置踢人或禁言 - 入群算术验证：50 以内加减乘除，10 分钟限时，答错禁言、超时踢人 - 其他机器人（如 Q群管家）与群主/管理员自动忽略，不会被误出题或误踢 - 已验证名单、白名单、忽略名单 |
| 2420 | astrbot_plugin_oil_price | 22 | other | watch | 返回今日国内各省市的92号/95号/98号汽油及0号柴油的最新零售价格，一查全知;地区覆盖支持全国31个省/自治区/直辖市的价格查询，按地区筛选即可获取当地油价;价格更新油价数据随国家发改委每10个工作日调价窗口实时更新，确保数据及时准确;多油品支持同时返回汽油（多标号）和柴油价格，满足不同车型用户 |
| 2421 | astrbot_plugin_daily_reminder | 22 | proactive | watch | 原神、星铁、绝区零、异环日常查询与定时提醒。 |
| 2422 | astrbot_plugin_opencode_session_header | 22 | other | watch | 为指向 https://opencode.ai/zen/go/v1 的 LLM 请求自动注入 x-opencode-session 请求头。正常情况下根据 AstrBot 会话 ID 确定性推导 UUID；上下文缺少会话 ID 时，可在插件设置中选择进程内随机 UUID 或用户指定的固定 UUID。 |
| 2423 | astrbot_plugin_qqmusic_voice | 22 | tts | watch | 通过LLM函数调用主观点播QQ音乐歌曲，并以语音形式发送 |
| 2424 | astrbot_plugin_qweather | 22 | platform | have | 基于和风天气 QWeather 的天气查询与主动推送：一个会话可绑多个地址、每个地址独立的推送方案，支持定时推送（可仅工作日）、降水开始/结束提醒、灾害预警轮询（等级升降都提醒）、额度报告推送与每月成本估算，自带节假日与调休日历；全部指令收在可配置前缀下，配置全在对话里完成。 |
| 2425 | astrbot_plugin_workgroup | 22 | memory | have | 面向多 AstrBot 实例的场景、项目、派单、回执、交接记忆与体检工作台 |
| 2426 | astrbot_plugin_amap_life | 22 | info-push | have | 基于高德 Web Service 为 Agent 提供地点推荐、多人会面、顺路排序和天气查询。 |
| 2427 | astrbot_plugin_odoo | 21 | other | watch | 连接 AstrBot 与 Odoo 18 Discuss 模块，实现企业内部 AI 机器人功能。 |
| 2428 | astrbot_plugin_vertex_image-command | 21 | other | watch | 使用 Google Vertex AI 生成图片（基于薄暝的插件修改） |
| 2429 | astrbot_plugin_mc_update | 21 | other | watch | 用于监控 Minecraft Feedback 的最新基岩版文章，并在有新文章时自动推送通知。 |
| 2430 | astrbot_plugin_primermath | 21 | other | watch | 让你的AI能正确进行简单四则运算和比大小 |
| 2431 | astrbot_plugin_waiter | 21 | devtools | watch | 基于 AstrBot 原生会话分发的一次性输入等待器，为开发者提供返回值和旧接口兼容。 |
| 2432 | astrbot_plugin_dailynews | 21 | group-stats | borrow | 接收本机日报流水线同步的成品，支持 /日报 查看，订阅后每日定时推送图片+文字日报到群聊 |
| 2433 | astrbot_plugin_schedule_lite | 21 | proactive | watch | BLBot 式课表功能的独立实现，适合部署在 QQ 群：群成员把课表 App 导出的 .ics、分享口令或链接发给机器人绑定后，可在群里同步查看谁正在上课、谁请假、谁今天没课。支持 Nexio 分享口令/JSON/ICS、WakeUp 课程表口令/备份、iCalendar(.ics)、拾光课程表 J |
| 2434 | astrbot_plugin_what2play | 21 | game | have | 从本地 Bangumi 推荐池推荐番剧或 Galgame，支持标签与三维权重，分离评分刷新和断点续抓。 |
| 2435 | astrbot_plugin_autonomous_companion | 21 | memory | have | 全天周期自主选择聊天、创作、工具行动或沉默，支持无回复短时续行和记忆陪伴桥接。 |
| 2436 | astrbot_plugin_apod_daily | 21 | info-push | have | 天文每日一图（APOD）与 NASA 每日一图插件，支持订阅推送、随机、LLM 翻译与函数工具。 |
| 2437 | astrbot_plugin_t2i_service | 21 | other | watch | 在 AstrBot 进程内提供 HTML/模板转图片渲染，可作为 AstrBot 的文转图端点，无需再单独部署容器。基于官方文转图服务制作，接口与行为保持一致。 |
| 2438 | astrbot_plugin_apitester | 21 | other | watch | 免费羊毛 API 检测：探测可用模型与效果（test api 指令） |
| 2439 | astrbot_plugin_market_pro | 21 | other | watch | 来cos久留美吧！多币种模拟交易插件：桌面 + 手机双端 Web 交易界面（按 UA 自动分发），含免责声明、1-125x 逐仓杠杆与强平、每个币种可单独设置走势、历史成交含现货与合约、一键添加币种、管理员加钱/转账/转股、带二次确认的一键重置股价。纯模拟，不涉及任何现实金钱交易。 |
| 2440 | quote_collocter | 21 | kb-rag | have | 把群友的「黑历史」变成随时能翻出来鞭尸的语录库。装上它，群友的逆天发言、名场面截图都会被收进本地数据库，支持随机抽取、AI 语义检索、人物档案、统计周报，以及一套完整的 WebUI 管理后台。  ## 核心功能  - **截图投稿**：群内发送「语录投稿」+ 图片即可收录，支持引用投稿与冷却防刷屏， |
| 2441 | astrbot_plugin_email_adapter | 21 | platform | have | 为 AstrBot 提供原生 Email 平台支持：通过 IMAP 轮询收信、SMTP 发信， 收发均支持 SSL / STARTTLS / 明文三种加密方式与可选的证书校验， 适配 Gmail、Outlook、QQ 邮箱、163、自建邮件服务器及各类事务邮件服务。 回复自动带上会话线程头，可在邮件 |
| 2442 | astrbot_plugin_anime_list | 21 | other | watch | 本周连载番剧的节目单与缩略图网格，支持季度新番表与番剧详情卡片 |
| 2443 | astrbot_plugin_prompt_order | 21 | other | watch | 自动识别每个插件注入的提示词片段，按拖拽排好的顺序重排后发出，提高前缀缓存命中；压缩历史里反复重发的长工具结果与提醒块；附带可实时监控、可落盘的调用检查器。 |
| 2444 | astrbot_plugin_token_balance | 21 | other | watch | 服务商余额/额度监控与告警：查询机器人各模型服务商的账户余额，余额告急时提醒，并记录余额变化。 |
| 2445 | astrbot_plugin_dlsitedata | 21 | other | watch | 根据RJ号从dlsite上爬取元数据。 |
| 2446 | astrbot_plugin_yunzai_bridge | 21 | other | watch | 通过带 Token 鉴权的 HTTP JSON RPC 连接远程 Yunzai。 Agent 可以检查连接、动态注册音乐等分类工具，以当前会话身份执行 Yunzai 命令，并可靠转发插件媒体回复。 |
| 2447 | astrbot_plugin_opiniocard | 21 | other | watch | 基于魔法少女的魔女审判观点辩驳UI二改，用于LLM判断观点时生成赞同/反驳/疑问立场卡片 |
| 2448 | Astrbot_plugin_mahjongsoul | 21 | other | watch | 从 nonebot_plugin_majsoul 移植的 AstrBot 雀魂插件，支持玩家数据查询、最近对局和 PT 图，并新增可选 AI 锐评、接口诊断与限流处理。 |
| 2449 | astrbot_plugin_mcsight | 21 | group-admin | have | 群内 Minecraft 服务器监控与成员绑定插件，结果以图片卡片呈现： 在线名单、玩家操作统计、TPS、服务器状态；QQ 昵称与游戏 ID 的绑定管理； 管理员可广播、可执行服务器控制台命令。 需要配套模组 QQBindMod（Fabric / Forge / NeoForge）提供 HTTP A |
| 2450 | astrbot_plugin_marry | 21 | other | watch | 娶群友插件：发送"娶群友"随机匹配群友结为夫妻，支持"离婚"解除绑定、"换一个"重新绑定，每群可单独设置每日更换次数上限，绑定时可@双方 |
| 2451 | lumielle_echo | 21 | memory | have | 面向 AstrBot 的长期记忆、自我认知与受控 Persona Evolution 插件，提供 Atomic Memory、Evidence、Lifecycle、Embedding、多 UMO 隔离、Atomic-only 检索、认知审核、Persona Version 与 Rollback。 |
| 2452 | astrbot_plugin_natural_style | 21 | personality | have | 自动沿用当前 AstrBot 人格，按 QQ 定制人物关系、称呼和专属要求；支持强化注入和可视化配置。 |
| 2453 | astrbot_plugin_mijia | 21 | other | watch | 通过米家云 API 在 QQ 等聊天平台查询与控制米家智能家居设备。  支持扫码登录、设备列表与状态查询、开关控制、属性设置（亮度/色温/温度/模式）、 设备动作和手动场景，同时注册了自然语言工具，可以直接说「把客厅灯调暗一点」。 默认仅管理员私聊可用，高危设备需要二次确认。 |
| 2454 | astrbot_plugin_obsidian_sync | 21 | kb-rag | have | 把 Obsidian 接进 AstrBot：内置 WebDAV 供 Remotely Save 双向同步；同时为 LLM 提供 搜索、读取、写入、浏览、软删除笔记与插入附件的原生工具，让 Bot 拥有可检索的长期知识库。  v1.4.1：WebDAV 挂载目录与工具读写目录分离，新增「库名称」（va |
| 2455 | astrbot_plugin_haidou | 21 | game | have | 英雄联盟海克斯大乱斗（海斗）数据查询：英雄胜率榜、单英雄海克斯适配榜、海克斯强度榜。支持指令查询与 LLM 工具调用（对话直接问即可）。数据源为掌盟官方接口，无需任何密钥。 |
| 2456 | astrbot_plugin_self_aware | 21 | other | watch | 让 bot 知道自己的本事并用起来：运行时能力表（命令 + 工具）、能力画像、语义直连、工具直连，附带推理档位、思考流和余额提醒。 |
| 2457 | astrbot_plugin_stepfun_asr | 21 | other | watch | 为 AstrBot 增加阶跃星辰 StepFun ASR 提供商类型（HTTP + SSE，支持 stepaudio-3-asr-max / stepaudio-2.5-asr） |
| 2458 | astrbot_plugin_feedback_tool | 21 | proactive | watch | 注册一个 LLM 函数工具。当 LLM 察觉到用户对机器人不满意时，会有意识地主动询问是否要把问题反馈给开发者；用户同意后自动整理反馈报告（含对话时间线、会话 UMO、用户 ID、群信息、反馈原因），并主动发送给插件配置中 UMO 列表对应的会话。报告格式支持在插件配置中自定义。 |
| 2459 | astrbot_plugin_url2img | 21 | other | watch | 将模型回复中的图片 URL 下载并压缩为 JPEG 图片消息，同时无条件保留原始图片网址作为保底。 |
| 2460 | astrbot_plugin_aihot | 21 | group-stats | borrow | 聚合 AI HOT（aihot.virxact.com）的 AI 行业动态、热点榜与日报。提供精选动态、关键词搜索、当前热点 TOP 10、按天获取的 AI 日报，以及热点事件时间线与 AI 综述。数据通过 AI HOT 的匿名只读 REST API v1 获取，无需 API Key。 |
| 2461 | astrbot_plugin_prompt_inspector | 21 | other | watch | 按注入顺序和最终排列顺序，完整查看每一次发给 LLM 的原始提示词：系统提示词的分段来源、完整 messages 数组、工具 JSON Schema，覆盖 tool loop 的每一轮。 |
| 2462 | astrbot_plugin_access_control | 21 | other | watch | 通过群白名单、用户忽略名单、私聊开关和 @ 过滤，管理机器人的消息响应范围，支持管理员指令维护用户权限 |
| 2463 | astrbot_plugin_active_reply_ctl | 21 | game | have | 主动回复冷却限频：概率抽签 + 群级冷却，避免"概率高刷屏、概率低哑巴"。需关闭原生「群聊上下文感知→主动回复」避免双重触发。 |
| 2464 | astrbot_plugin_emoji_library | 21 | sticker | borrow | 持久化识别用户发送的表情包，命中后使用可编辑的固定解释，避免重复调用视觉模型。 |
| 2465 | astrbot_plugin_diary | 21 | memory | have | 让她每天自己写日记：悄悄记下日常、到点生成，网页上可以翻看修改，聊天时还会想起自己写过什么。 |
| 2466 | astrbot_plugin_class_notice | 21 | other | watch | 导入课表（ICS / CSV / JSON / 文本），支持面板/指令手动添加与删除日程，按日期/今日/本周查询，并在上课前 / 下课前提醒到多个会话。指令与聊天完全隔离。 |
| 2467 | astrbot_plugin_steamachievement_query | 20 | other | watch | 快速查询Steam成就积分、成就数、积分排名等信息的简易插件。 |
| 2468 | astrbot_plugin_simulation-xiuxian | 20 | other | watch | 一个简单的文字模拟修仙插件 |
| 2469 | astrbot_plugin_check-dst-room | 20 | other | watch | 饥荒查房 |
| 2470 | astrbot_plugin_websocket_bridge | 20 | other | watch | 为 AstrBot 提供独立 WebSocket 双向桥接接口，适合 NoneBot 等外部平台长连接接入 |
| 2471 | astrbot_plugin_cmd_guard | 20 | other | watch | 拦截未知/被禁用的指令并禁止其触发 LLM 兜底回复；支持指令白名单/黑名单与分机器人配置。 |
| 2472 | astrbot_plugin_bili_video | 20 | media-parse | borrow | 发送 /刷视频 从B站热门榜随机挑一个短视频（默认不超过3分钟）/搜视频 关键词 按名字搜索短视频发到当前会话，无需登录、无需 ffmpeg |
| 2473 | astrbot_plugin_gal_choice | 20 | sticker | borrow | 一键进入 GalGame 模式：模型每轮只输出「表情 + 台词 + 2~4 个选项」， 插件把它渲染成一张 1280×720 的 GalGame 界面图，台词同时可配 FishAudio 等 TTS 语音。 用户回字母 / 数字 / 选项原文继续，也可以回 0 或直接说话自由输入；选项会带进下一轮， |
| 2474 | help_dex | 20 | other | watch | 一条指令，把机器人会的一切画成一张简洁亮色图鉴。群里@一下就发图；配色在 AstrBot 面板里拖个色块就生效、带实时预览，不用碰文件不用重启。同机多 bot 各自独立：每个 bot 可以有自己的背景图，谁进群就从谁嘴里发图鉴，不会串到别的 bot 上。背景图一律拍平为不透明，可强制浅色基调，再深的 |
| 2475 | astrbot_plugin_neko_draw | 20 | image-gen | watch | 支持从 QQ 合并转发聊天记录取图并制作 APNG，提供多图原图与生成图历史、缩略图及完整清理；支持 WaveSpeed、RunningHub、OpenAI 兼容及 AstrBot 已有模型提供商与多主题 WebUI。 |
| 2476 | astrbot_plugin_download_middleman | 20 | other | watch | 下载中间商：通过 curl 下载文件或克隆 GitHub 仓库并压缩发送。 |
| 2477 | astrbot_plugin_ow2_cn | 20 | other | watch | 基于网易大神（网易 DD）数据源的《守望先锋 2》国服战绩查询插件。 提供 /ow 绑定、战绩、对局、英雄、资料、解绑、帮助 等指令， 支持群内共用绑定与个人绑定，支持 @群友 或直接输入 BattleTag 查询。 数据源可切换：直连网易大神上游（需要大神 token）或指向自建 Overstat |
| 2478 | astrbot_plugin_special_days | 20 | platform | have | 给 AstrBot 加一个轻量的“今天是什么日子”感知。  当天命中节假日、纪念日、玩梗日或自定义日程时，在 LLM 请求的 system_prompt 末尾追加一小段背景提示，由模型根据聊天上下文决定 要不要提；不额外调用 LLM，不修改消息链，不写对话历史。  内置公历、农历节日、中国法定节假日 |
| 2479 | astrbot_plugin_element_detector | 20 | other | watch | 群聊中出现关键词时立刻随机回一句。规则全部在插件页面里维护。 |
| 2480 | astrbot_plugin_forward_message | 20 | other | watch | 创建受控的 QQ 合并转发消息，支持命令和 LLM Tool，群聊与私聊均可，发送目标固定为当前会话。 |
| 2481 | astrbot_plugin_JO3dmodel | 20 | game | have | 在聊天中直接创建 3D 模型。支持本地程序化生成（球体/花瓶/齿轮/地形/文字浮雕等 15+ 种模型）与 AI 文生 3D（Tripo / Meshy），自动输出 STL/OBJ/GLB 文件 + PNG 预览图 + 可旋转的 3D 交互预览页。3D 打印、游戏建模、学习演示全能。 |
| 2482 | astrbot_plugin_daily_diary | 20 | proactive | watch | 让 AstrBot 每天定时写 Markdown 日记，自动导入 .md 文件，并通过主动消息通知用户 |
| 2483 | astrbot_plugin_better_music | 20 | tts | watch | 聚合网易云音乐、QQ音乐和酷狗搜索、登录与下载，并支持点歌分段发送。 |
| 2484 | astrbot_plugin_kbridge | 20 | kb-rag | have | astrbot 知识库同步插件，装这一个就够了！支持从腾讯 ima、有道云笔记、GitHub、Url、Open Notebook、Memos、Notion 等同步，更多支持的平台正在路上... |
| 2485 | astrbot_plugin_qinglong_manage | 20 | other | watch | 通过聊天管理青龙面板，支持任务管理、环境变量、日志查看、自动推送及定时推送 |
| 2486 | astrbot_plugin_cachekeeper | 20 | other | watch | 管理 NTQQ 客户端缓存，提供扫描、候选统计与安全清理能力。 |
| 2487 | astrbot_plugin_error_reporter | 20 | other | watch | 报错翻译官：把 AstrBot 报错翻译成人话发到管理群，标明来源，自动去重，模型可换。 |
| 2488 | astrbot_plugin_fortuneWheel | 20 | game | have | 一条指令输入任意数量的昵称，机器人运行转盘抽奖动画，旋转停止后定格并公布获奖者。 |
| 2489 | astrbot_plugin_ai_summary | 20 | other | watch | 支持引用视频、图片、文字和合并转发的多模态 AI 总结工具 |
| 2490 | astrbot_plugin_glimmer_portraits | 20 | other | watch | 从群聊的浮光片语中，增量勾勒群友的称呼、兴趣、特点与关系 |
| 2491 | astrbot_plugin_webchat_viewer | 20 | tts | watch | 一个 AstrBot「插件 Pages」风格的插件，提供一个独立的 WebUI 页面，列出全部 **WebChat** 对话，允许查看 / 导出这些对话的平台消息历史，并与官方 「对话记录」页一致地编辑（重命名 / 编辑记录 JSON / 删除）。  ## 功能 - 会话列表：按 `updated_ |
| 2492 | astrbot_plugin_zhalslar | 20 | other | watch | 饰乐插件整合包，一键安装全套实用插件 |
| 2493 | astrbot_plugin_markdown_render | 20 | other | watch | 将 Markdown 在本地渲染为 PNG 图片，提供自动渲染和模型工具两种方式。支持普通 Markdown 语法、代码高亮、LaTeX 公式、Mermaid 图表，支持局部渲染。 |
| 2494 | astrbot_plugin_aiwm | 20 | game | have | 绑定一个 SteamID64 就能查 CS2 战绩，让大模型做锐评和玩家画像。 |
| 2495 | astrbot_plugin_mathviz | 20 | other | watch | 把整条回答排版成一张白底黑字长图：公式交给 MathJax（真 TeX 引擎）排版， 中文与段落交给 Typst；另提供函数曲线、隐式方程、极坐标、参数方程与几何示意图的绘图工具。 可按字数阈值自动触发，也可完全关闭。 |
| 2496 | astrbot_plugin_bear_tracker | 20 | group-admin | have | FF14 S怪播报与地图标点、狩猎车文字提醒及图片指令，集成群消息转发、查漏采集、芒果广播和手动图文群发，支持统一WebUI。 |
| 2497 | astrbot_plugin_at_resolve | 20 | media-parse | borrow | QQ群at映射解析：自动学习 member_openid→QQ昵称/群名片 双字段映射，把 <@HEX> 改写为 @名字（群名片优先可配，默认开启并同步统一群聊上下文发言人标签），让 AI 认得谁 at 了谁、不把同一人误认成两个。WebUI 管理页面（QQ群at映射管理）或 /atmap 指令均可 |
| 2498 | astrbot_plugin_snow_continuity | 20 | game | have | 连续对话中的追问和戳一戳后的消息被确定性回复，不再被读空气概率吞掉 |
| 2499 | astrbot_plugin_snow_imagebox | 20 | sticker | borrow | 让机器人保存聊天里的图片和表情包，之后按情绪或场景再发出来，并自动清理低频、远古图片 |
| 2500 | astrbot_plugin_voice_intent | 20 | tts | watch | 关掉 AstrBot 内置的概率语音回复，改由 AI 判断「用户是不是想听语音」：默认走 TypeSafe 的 Jev 做结构化判断，没配 Key 或调用失败时自动回退到对话模型。 判为语音时把 send_voice 工具交给模型，由它决定说什么，执行层再按判断结论裁决；判为文字时也保留工具，避免模 |
| 2501 | astrbot_plugin_lark_access_control | 19 | platform | have | AstrBot 插件，用于在飞书平台做访问权限控制，例如限制哪些用户可以与机器人对话，在哪些群聊中允许与机器人对话。 |
| 2502 | astrbot_plugin_DUT_Notices | 19 | info-push | have | 聚合爬取大连理工大学多个通知站点（以开发区校区为主）最新内容，向订阅会话推送最新通知。 |
| 2503 | astrbot_plugin_lyubishchev | 19 | other | watch | 通过柳比歇夫时间管理方法让Astrbot帮助你进行时间管理，只适合个人使用 |
| 2504 | astrbot_plugin_rf4_data | 19 | other | watch | 俄罗斯钓鱼4本地数据查询，鱼种上星上蓝重量、渔轮参数，零token消耗 |
| 2505 | github_star_verify | 19 | group-admin | have | [aiocqhttp]使用 GitHub 仓库的 Star 状态作为入群验证条件，仅允许已 Star 指定仓库的用户留在群内。 |
| 2506 | nvdastock | 19 | other | watch | 查询NVDA股票实时行情 |
| 2507 | CustomT2I | 19 | other | watch | 用于在 astrbot 中切换和管理自定义模板 |
| 2508 | astrbot_plugin_agent_heartbeat | 19 | other | watch | 为长时间运行的 Agent 任务提供类似 Codex / DeepSeek Harness 的 Heartbeat 状态播报；短任务完全安静，不打扰用户。 |
| 2509 | astrbot_plugin_peak_whitelist0d00 | 19 | other | watch | 工作日指定时段在指定群只允许白名单成员触发 bot，省 token。 |
| 2510 | astrbot_plugin_PlayStationGames | 19 | memory | have | 本插件为 PlayStation(PSN) 玩家数据查询与可视化插件。绑定你的 PSN 在线 ID 后，对机器人 @ 或使用 /psn… 系列指令即可：查本人或群友的个人资料、在线状态、游戏库与总时长、奖杯总览，以及某款具体游戏的总时长、启动次数、首次/最近游玩日期与该游戏奖杯进度（支持俗称/简称/ |
| 2511 | astrbot_plugin_examine | 19 | group-admin | have | 简简单单的入群自动考核插件 |
| 2512 | astrbot_plugin_permission | 19 | other | watch | 批量权限管理插件，支持批量编辑和管理命令权限，通过 AstrBot 原生 Page 页面提供可视化界面，无需独立开端口 |
| 2513 | astrbot_plugin_self_msg_guard | 19 | other | watch | 拦下机器人自己账号被平台回灌的消息，防止机器人对着自己的话继续回复形成自转循环，支持全拦/去重/限频三种模式、放行前缀与会话白名单 |
| 2514 | astrbot_plugin_deepseek_usage | 19 | other | watch | 查询 DeepSeek 账户的历史 Token 使用量，支持自定义天数与日期范围。 |
| 2515 | astrbot_plugin_aria2_plus | 19 | other | watch | AstrBot aria2 RPC下载管理插件，支持自定义下载目录、代理访问、下载完成自动QQ通知、AI自动调用与用户白名单 |
| 2516 | astrbot_plugin_chat_console | 19 | other | watch | 在 AstrBot WebUI 中查看并控制各适配器的群聊消息。 |
| 2517 | astrbot_plugin_ooptra | 19 | tts | watch | **Ooptra 配套插件**，在 QQ 查询 / 管理 Oopz 语音频道。  - AstrBot 内的 Ooptra 工作台：常用语音操作与可视化群绑定 - 同一工作台内打开完整 Ooptra 控制台，保留原界面风格  - `/语音状态` 查人数与成员（含闭麦/闭听） - `/进语音` `/退语 |
| 2518 | astrbot_plugin_bilibili_shixun | 19 | media-parse | borrow | 直连 B 站，支持免登录关键词搜索、聊天订阅管理、QQ 扫码、来源采集与个人简报。 |
| 2519 | astrbot_plugin_explain_slang | 19 | other | watch | 黑话/缩写解释器，调用“能不能好好说话(nbnhhsh)”接口解释拼音首字母缩写 |
| 2520 | astrbot_plugin_image_caption_pool | 19 | other | watch | 用一个稳定的虚拟 Provider，把 AstrBot 群聊感知的单图片转述入口扩展成支持轮询、加权随机、超时、冷却和故障转移的模型池。 |
| 2521 | astrbot_plugin_vctniceeeee_new | 19 | other | watch | 拉取 vlr.gg 的 VCT 赛程与比分（含中国赛区及全球冠军赛/Masters），支持定时播报、手动查询、比赛详情（地图/比分/MVP）与实时监控。 |
| 2522 | astrbot_plugin_dafeiyu_alias | 19 | memory | have | 把 QQ 号和固定称呼绑定，群聊里持续按称呼表称呼人；同一个 QQ 再次设置新称呼时自动覆盖旧称呼。  适合熟人小群：主人告诉机器人“QQ 123456 是张哥，哥哥”，之后在群里就用“张哥”称呼；换称呼时再说一次即可。  特性： - QQ 号 → 称呼（可带关系备注）持久保存 - 同一 QQ 新称 |
| 2523 | token_monitor | 19 | other | watch | 在 AstrBot Dashboard 中监控各会话的上下文 Token 水位，并在接近压缩阈值时主动推送水位警告。 |
| 2524 | astrbot_plugin_val_match | 19 | sticker | borrow | 比赛有人提醒，胜队一起选。查询无畏契约赛程，订阅开赛提醒与完整战报；群友点表情选胜队，也能 @机器人自然语言参与和批量修改，赛后自动结算积分和胜负正确率。内置赛程时间轴与使用指南，按需配置赛事、接收群和赛后积分榜。基础查询无需额外 API Key。 |
| 2525 | astrbot_plugin_lifespan_theory | 19 | personality | have | 给角色设出生日期，年龄按真实日历现算；按年龄档用 LLM 结合人格提示词生成说话方式并注入上下文；另有「只写小本本」与「生日年报」（本地渲染长图/分页/HTML，QQ OneBot 白黑名单发送）。 |
| 2526 | astrbot_plugin_llm_manager | 19 | other | watch | 把全部模型按 "地址→分组→模型" 三级归拢，通过指令实现图形化查看模型列表、全局切换、单个或多个模型测速、查看 token 消耗，全程指令化不用进后台。 |
| 2527 | astrbot_plugin_heartrate | 19 | other | watch | 实时心率监测插件，自动注入每次对话，支持手动查看和服务管理 |
| 2528 | astrbot_plugin_nai_prompt | 19 | personality | have | 将自然语言或图片转换为可复制的 NAI 新版格式提示词，支持角色作品名引用、多角色 Character Prompting、互动标签、权重强调、图片主动优化、示例图生成、引用回复增量修改、语义去重、权限白名单和安全降级。 |
| 2529 | astrbot_plugin_topic_context | 19 | memory | have | 基于主题的记忆组织与上下文管理。自动总结对话、按主题存储记忆、注入上下文，让 Bot 拥有跨会话记忆能力。 |
| 2530 | astrbot_plugin_command_tools | 19 | other | watch | 将 AstrBot 及其插件的命令转换为模型可以自主调用的工具，让机器人帮你执行命令。 |
| 2531 | astrbot_plugin_ignore_user | 19 | other | watch | 按用户 ID 拦截指定用户的消息：名单内用户发送的私聊、群聊消息会在进入 AI 处理流程之前被直接拦截，机器人不予回复。拦截名单可在插件配置页直接增删，无需修改代码。 |
| 2532 | astrbot_plugin_endfield_kb | 19 | kb-rag | have | 把《明日方舟：终末地》的剧情原文、档案与设定编译成本地索引，供模型按需检索。 默认无需嵌入模型与外部服务，贴整句原文也能命中；可选接入 embedding 做语义检索，或接入 T2I 出图。 |
| 2533 | astrbot_plugin_cost_board | 19 | other | watch | AstrBot 只记 token，不记钱，模型后台的账单看不出是哪个群、哪个会话花掉的。 本插件直接读 data_v4.db 的 provider_stats（只读），用可配置的价格表换算成人民币， 一条指令给出今日 / 7 天 / 30 天花费、按模型占比、最烧钱的会话、缓存命中率。 命令：/费用 |
| 2534 | astrbot_plugin_token_meter | 19 | other | watch | TokenLedger —— 把机器人每一次对话花掉的 token 都记成一笔账：输入、输出、缓存命中各记各的。今天花了多少、这周花了多少、哪个群最费、哪个模型最贵、哪几次是它主动找上来的，面板「扩展功能」里点开就能看，不用发任何指令；也支持 /用量 在群里直接问。 |
| 2535 | astrbot_plugin_ambient_chat | 19 | proactive | watch | 让 AI 像人一样自己去「看一眼」聊天：按时机翻关注会话的新内容，按兴趣决定要不要搭句话，而不是只能等被点名。 |
| 2536 | astrbot_plugin_meme_memory | 19 | memory | have | 给表情包加一层记忆：自动判定并收藏聊天里的表情包，用视觉模型理解画面与语境， 按半衰期自然衰减（久不用的会遗忘，再出现能复活）， 聊天时按语义相似度挑选最贴题的一张，不相关就一张都不发。 |
| 2537 | astrbot_plugin_identity_directory | 19 | memory | have | 跨平台身份通讯录：将各平台账号/各群名片归并为同一个人，提供 WebUI 管理与身份解析 API。 |
| 2538 | astrbot_plugin_wanna_play_game | 19 | game | have | 根据你想玩的游戏，从 gamer520.com 与 online-fix.me 查找下载信息。 |
| 2539 | astrbot_plugin_chat_report | 19 | group-admin | have | 聊天消息举报插件：AI自动研判，违规自动撤回/警告/禁言，拿不准时转人工私聊管理员处理 |
| 2540 | astrbot_plugin_parser_x | 19 | media-parse | borrow | 基于 rconsole-plugin 功能版图设计的 AstrBot 国内平台链接解析插件，采用原生 Python 解析器与 yt-dlp 兼容层。 |
| 2541 | astrbot_plugin_Lumi-Hub-plugin | 18 | other | watch | 一套独立的私有化 Agent 交互框架，作为 AstrBot 的自定义消息平台与专属 Flutter 客户端通信，内置原生 MCP 执行引擎与 HitL 审批拦截机制。 |
| 2542 | astrbot_plugin_gskard | 18 | game | have | 一个模拟GSkard抽牌系统的插件 |
| 2543 | astrbot_plugin_jojo_stand_panel | 18 | other | watch | 一个用于 AstrBot 的 JOJO 替身面板生成插件，调用 TripleYing 的 API 生成 JOJO 风格替身面板图片。支持随机生成、自定义设置、替身系统等功能。 |
| 2544 | astrbot_plugin_message_tester | 18 | devtools | watch | 使用 logger 完整打印消息结构 |
| 2545 | cngal_search | 18 | other | watch | CnGal查询 |
| 2546 | astrbot_plugin_ExchangeRateQuery | 18 | other | watch | 基于 ExchangeRate 的实时货币汇率查询插件 |
| 2547 | astrbot_websitetool | 18 | other | watch | mccloud_site的修复版，解决了QQ识别不到的问题。使用说明与mccloud_site一样 |
| 2548 | astrbot_plugin_image_collector | 18 | sticker | borrow | 自动收集群友发送的图片，支持去重和压缩，并在用户发送消息时随机回复其图库中的图片 |
| 2549 | astrbot_plugin_feather_art | 18 | other | watch | 羽画：把图片离线描摹成单文件插画，默认纯 HTML + CSS、可选内联 SVG 方言，无图片、无脚本、无外链 |
| 2550 | astrbot_plugin_pjsk_station | 18 | other | watch | 查询 Sekai Station(国服)与 プロセカ Station(日服)的实时房间列表,渲染为图片 |
| 2551 | astrbot_plugin_redalert | 18 | payment | exclude | 监听指定 QQ 群的红包消息，一旦发现可领取红包，先私聊提醒主人，再在原群发一句感谢；不会自动领取。  适合“群里发红包，但机器人不方便/不应该抢”的场景：主人第一时间收到提醒，手动去抢；机器人在群里感谢发送者，不碰领取逻辑，不调用 LLM，零 token 成本。  NapCat 用户需先运行仓库  |
| 2552 | astrbot_plugin_zlibrary | 18 | other | watch | 使用「找书」命令在 Z-Library 搜索图书，选中后把电子书文件直接发送给找书人。 |
| 2553 | astrbot_plugin_upton_quoter | 18 | media-parse | borrow | # Upton 智能引用插件  由 **UptonKipling** 开发。群聊智能引用插件,**只在用户主动 @Bot 或引用 Bot 的消息时**,Bot 的回复才会在消息链头部插入 Reply 引用,引用目标始终是用户当前这条消息(而非用户所引用的上一条 Bot 消息),私聊与普通群聊消息则不 |
| 2554 | astrbot_plugin_lanzuyuxia | 18 | media-parse | borrow | 蓝奏云链接直链解析插件 |
| 2555 | astrbot_plugin_quote_saver | 18 | game | have | 保存其他人的爆典时刻，支持随机发送与戳一戳回复；可开启群聊隔离，让各群语录互不互通。 |
| 2556 | astrbot_plugin_nai_draw | 18 | image-gen | watch | 让 Bot 借助 LLM 在聊天中调用 NovelAI 绘图，开画、完成、失败时都会按人格说话（兼容 OneBot11） |
| 2557 | astrbot_plugin_comfyui_loom | 18 | image-gen | watch | 带 ComfyUI 风格面板的工作流工作台：顶部工作流标签、左侧菜单、右侧常驻节点画布；界面工作流按原坐标/尺寸/颜色/分组/控件还原，自动识别正面/负面/保存节点，API 与界面工作流双格式绑定，面板直接出图，支持指令与 AI 绘图工具、原图/引用/合并转发图生图。 |
| 2558 | astrbot_plugin_session_alias | 18 | memory | have | 把多个账号（乃至多个平台）的消息来源，悄悄改写成同一个来源。 于是不管从哪个门进来，读到的都是同一份记忆，回复还发回你当前用的入口。  v2.3 起支持多条路由：来源池统一管理所有 UMO，路由自由组合， 可以同时做「1+2 → 3」「4+5 → 6」，互不串台。 |
| 2559 | astrbot_plugin_countdown | 18 | other | watch | 面向群聊和私聊的事件提醒与时间记录插件，适用于活动前瞻、报名截止、开服及建群天数等场景。 支持未来事件倒计时、过去日期正计时、自定义文案、图片卡片查询和每日定时汇总；带时刻事件可提前提醒并在到点时提醒。 各会话的任务独立保存，各群可单独设置汇总时间，支持管理权限配置和到期自动清理。 可通过指令或 L |
| 2560 | astrbot_plugin_vw_intent_router | 18 | personality | have | 用低成本 LLM 判断群聊消息值不值得让主人格开口：结构化打分、时间衰减密度、主动插嘴熔断、与虚拟世界插件联动，带网页看板 |
| 2561 | astrbot_plugin_qqbotmarkdown_forwarder | 18 | other | watch | 将绑定的 OneBot 或 Satori 群聊/私聊 Markdown 与交互按钮回复转发到 QQ 官方机器人，并拦截原消息。支持大模型主动调用发送带交互按钮的 Markdown 消息。 |
| 2562 | astrbot_plugin_testbench | 18 | devtools | watch | 轻松对比调提示词：一条消息并发发送给多个虚拟会话，直观看到不同提示词 / 插件配置 / 模型下的回复差异，告别凭感觉调试；进阶可用测试集做极端场景稳定性压测与机械 + LLM 自动评审。 |
| 2563 | astrbot_plugin_github_release | 18 | info-push | have | 通过指令订阅指定 GitHub 仓库的 Release 消息，插件按可配置周期轮询，发现新 Release 时向对应会话推送更新日志；首次订阅时发送当前最新 Release 并记录。 |
| 2564 | astrbot_plugin_link_summary | 18 | devtools | watch | 自动检测会话中的网页链接，抓取正文并调用大模型生成摘要；支持 /总结 手动总结与 /追问 继续提问。（开发中，可能存在 bug） |
| 2565 | astrbot_plugin_custom_gacha | 18 | devtools | watch | 自定义抽卡插件：可自定触发词/帮助菜单/排行榜，文件夹式多卡池并支持每群独立分配；AI 视觉模型自动生成卡牌名称与图鉴文案；每日限抽、图鉴收集进度、日/月/总榜、超级管理员私聊调试会话；带多页面 WebUI 管理面板。 |
| 2566 | astrbot_plugin_webpage_screenshot | 18 | other | watch | 新一代非 API 接口截图插件。不依赖 Playwright / Selenium / html2image 等浏览器封装库， 而是直接用 CDP（Chrome DevTools Protocol）驱动浏览器内核完成截图，无驱动版本漂移。  支持整页长图（超长页自动分段拼接）、可视区截图、元素截图、 |
| 2567 | astrbot_plugin_daily_reminder | 18 | proactive | watch | 按固定时间给指定会话发一条主动提醒，**不经过主 Agent**，因此不会在对话历史里 留下任务播报式的伪对话。  **为什么不用内置的「未来任务」（CronJob）**：内置实现会在 system prompt 里注入 cron_job JSON（含会话 ID），user 轮又要求「总结本次行动与 |
| 2568 | astrbot_plugin_true_group_blacklist | 18 | other | watch | 支持群黑名单和群白名单；白名单模式仅放行指定群，其余群的消息、指令及可识别群通知均在入口拦截，管理员无例外。 |
| 2569 | astrbot_plugin_gjxq_chess | 18 | game | have | 在 game.hullqin.cn 的 gjxq 房间中创建或加入国际象棋对局，支持文本棋盘、聊天走棋、自动 AI 对手、胜负通知、同会话多开房间与合并推送 |
| 2570 | astrbot_plugin_helpmenu | 18 | other | watch | 为 AstrBot 提供更好的可翻页的帮助菜单，支持文本输出与图片输出，自动监测插件变化并更新。 |
| 2571 | astrbot_plugin_bilibili_atpy | 18 | media-parse | borrow | 用你自己的B站账号每天挑一个视频，让模型写一句十字以内的锐评，@ 几个朋友发在评论区，结果同步到 QQ 群。五类内容（搞笑搞怪 / 莫名其妙 / 二游 / 王者荣耀 / 无畏契约）按日期轮转。 |
| 2572 | astrbot_plugin_companion_admin | 18 | tts | watch | 让陪伴类 Bot 在管理员私聊里用自然语言查看和修改自己的人格、用户风格、群白名单和 TTS；所有写入先提案、确认后执行，并带快照与回滚。 |
| 2573 | astrbot_plugin_decision | 18 | group-admin | have | 基于 AstrBot 原生决策模型的 Tool、MCP、Skill 与 SubAgent 逐项判断、过滤、推荐，支持消息接话、决策审核的虚拟生活主动发起、人格日程穿搭、aigen 拍照/拍视频/生音频联动，并内置按人格管理的人际网络。 |
| 2574 | astrbot_plugin_send | 18 | other | watch | 管理员或指定用户使用 /send 指令发送消息，支持 |
| 2575 | astrbot_plugin_memos_manager | 17 | other | watch | 一个能对usememos/memos进行管理的插件 |
| 2576 | astrbot_plugin_trello | 17 | other | watch | 通过 AstrBot 连接 Trello，提供卡片管理、列表管理等功能。 |
| 2577 | astrbot_plugin_be_checker | 17 | game | have | 查询 GTA Online 玩家的 BattlEye 封禁状态。支持通过用户名或 RID 查询，自动缓存 RID 信息提高查询效率，支持强制重新查询。 |
| 2578 | astrbot_plugin_matchreminder | 17 | other | watch | 算法比赛查询和今日比赛自动提醒 - 支持 CF、牛客、AtCoder 平台 |
| 2579 | sunsetbot_search | 17 | info-push | have | 获取 sunsetbot.top 今日/明日火烧云数据 |
| 2580 | astrbot_plugin_zhanxing | 17 | game | have | 基于 LLM 的占星骰子插件 |
| 2581 | astrbot_plugin_cyber_archaeology | 17 | kb-rag | have | [仅 aiocqhttp] 本插件利用embedding，根据描述查询意思相符的历史信息。 |
| 2582 | astrbot_plugin_kahunabot | 17 | other | watch | 一款基于 EVEonline API 侧重工业制造支援的综合性 QQ 插件 |
| 2583 | astrbot_plugin_wol | 17 | other | watch | 局域网 WOL 唤醒插件，/wolhelp 查看帮助 |
| 2584 | astrbot_plugin_baonly | 17 | info-push | have | 连接 baonly 查询站并处理数据的 astrbot 插件 |
| 2585 | astrbot_plugin_dagongren | 17 | game | have | 打工人·上班族物语 —— 大型群聊职场生存模拟游戏。 |
| 2586 | astrbot_plugin_title_self | 17 | other | watch | 群成员发送「#头衔 xxx」即可自助修改自己的群头衔（需机器人是群主） |
| 2587 | astrbot_plugin_arknights_recruit_assistant | 17 | other | watch | 发送明日方舟公开招募界面截图（或直接输入词条），插件会识别 5 个词条， 枚举其中 1~3 个词条的全部组合，按「高级资深干员必出6★ → 资深干员必出5★ → 保底4★+极小概率5★ → 保底4★ → 小概率5★ → 小概率4★」的优先级给出推荐， 并把每个组合的候选干员按星级分组全部列出，选中高 |
| 2588 | deepseek_search_scope | 17 | other | watch | # DeepSeek 搜索范围限制  限制 AstrBot 内置的 DeepSeek 网页搜索范围，指定只允许（或禁止）查询哪些网站。  ## 功能  - 搜索查询注入 `site:` / `-site:` 操作符，由 DeepSeek 搜索引擎在源头限定范围； - 对搜索结果按域名二次过滤（双保险 |
| 2589 | astrbot_plugin_seg_interrupt | 17 | other | watch | 可打断的分段回复：用户发来新消息时，立刻停止上一条还没发完的分段 |
| 2590 | astrbot_plugin_sanguosha | 17 | personality | have | 纯本地结算的 1v1 三国杀文字对局插件。支持单人对战AI（带人格吐槽）与群内双人私聊对战。内置40名武将技能，支持无懈链、觉醒技、拼点等复杂机制，不消耗大模型 Token。 |
| 2591 | astrbot_plugin_mahjong | 17 | game | have | 立直麻将工具插件：牌理分析、向听数、听牌检测、和牌役数/符数/点数计算。支持雀魂/天凤规则。基于Xpilot算法移植，AGPL-3.0开源。 |
| 2592 | cyber_zakka | 17 | personality | have | 赛博杂货铺插件：电子木鱼（功德计数）、赛博老虎机（三连中奖）、今日人设盲盒（五组模板组合）、缘分测试（确定性哈希，同对名字结果固定）、夸夸机（彩虹屁模板）。全部玩法单发秒回、无状态流程、无养成系统，默认零 LLM 调用；仅盲盒可选 LLM 润色（带超时与冷却，失败自动回退本地卡片）。支持可选图文卡片 |
| 2593 | gmod_a2s_server_query | 17 | game | have | GMod 服务器在线查询工具，支持别名管理、消息监听自动查询、服务器列表图片渲染、自定义查询 API 与 LLM 工具调用。 |
| 2594 | astrbot_plugin_get_members | 17 | other | watch | 管理员通过 /get_members 指令一键获取当前群所有成员的昵称与 QQ 号，支持数据导出与统计。 |
| 2595 | astrbot_plugin_oil_price | 17 | other | watch | 全国油价查询与计算插件：每天自动抓取全国 31 省成品油挂牌价，涨红跌绿出图推送。  - `/今日油价` 整体播报图 · `/看看油价 广东 92` 单省单号大图（加油建议内嵌） · `/我要加油 30升` 加油机结算单图 - 历史一键初始化、每日定时抓取、缺当日数据自动补一次；`/油价设置` 记住 |
| 2596 | astrbot_plugin_proactive_history | 17 | proactive | watch | 把机器人主动发出的消息（未来任务/后台任务经 send_message_to_user 发送的内容）补记进对话记录，按 AstrBot 的分段回复设置分段发送，并清理 cron/后台任务遗留的合成脚手架消息。 |
| 2597 | astrbot_plugin_chat_limit | 17 | other | watch | 麻麻专属聊天限制插件。支持按群聊/私聊会话隔离的闭嘴模式、忽略指定 QQ 号、按分钟限频三类管控，超限自动拦截，到期自动解除。 |
| 2598 | astrbot_plugin_vcpedia | 17 | media-parse | borrow | 让 LLM 查询 VCPedia（虚拟歌手百科）的页面、歌曲、P主、声库、专辑与歌词。 统一入口 ask_vcpedia 会自动解析信息框、STAFF、专辑曲目、多版本歌曲与歌词， 适合 VOCALOID、Synthesizer V、ACE Studio 和中文原创曲相关问答。 |
| 2599 | astrbot_plugin_deepseek_peak_switch | 17 | other | watch | 按 DeepSeek 峰谷计费时段自动使用 V4.1-Flash；高峰可停用对话（插件与指令照常）。支持自定义时段、周末与法定节假日判定。 |
| 2600 | astrbot_plugin_tarot | 17 | other | watch | 按牌阵抽塔罗牌：单张到十张凯尔特十字，每个位置有含义，发纸质风格的牌阵图并附一段解读；78 张全牌组，牌面可选纯文字或 1909 年版韦特牌图（公有领域，需自行下载） |
| 2601 | astrbot_plugin_dafeiyu_emotion | 17 | memory | have | 基于已有记忆建立情感档案，在主人私聊中注入当前情感状态，并按小步反思更新好感、信任、安全感与心情；只影响表达，不改人格主体。 |
| 2602 | astrbot_plugin_monkeycode | 17 | other | watch | 通过 MonkeyCode 云平台提交 AI 编程任务并跟踪结果。基于 monkeycode-sdk，自动处理 PoW 验证码，支持自托管。 |
| 2603 | astrbot_plugin_gcard_keeper | 17 | other | watch | 检测群名片变更，支持通知、机器人名片保护、违规名片恢复、成员名片锁定、通用名片恢复和定时轮询检测。 |
| 2604 | astrbot_plugin_doc_knowledge_base | 17 | kb-rag | have | 将多个 AstrBot 容器内本地目录增量同步到指定的原生知识库，支持新增、更新、删除协调、 失败文件记录和只读 Streamable HTTP MCP 查询；不引入独立 RAG 或向量数据库。 |
| 2605 | astrbot_plugin_oneroll | 17 | game | have | 基于 HydroRoll-Team OneRoll 的轻量 AstrBot 骰子插件，支持表达式、多指令和统计。 |
| 2606 | astrbot_plugin_cloudflare_tunnel_monitor | 16 | other | watch | 一个通过 Cloudflare API 轮询 Cloudflare Tunnel 存活状态的监测插件 |
| 2607 | astrbot_plugin_dida365 | 16 | other | watch | 在 AstrBot 中连接 Dida365（滴答清单），支持任务查询、定时汇报和基于 LLM 的任务操作。 |
| 2608 | astrbot_plugin_ftp_control | 16 | other | watch | 通过 LLM 工具执行 FTP 文件操作 |
| 2609 | astrbot_plugin_urldb | 16 | other | watch | 为 [老九网盘数据库系统](https://github.com/ctwj/urldb) 设计的AstrBot插件，支持被@时搜索功能。 |
| 2610 | plugin_test_helper | 16 | devtools | watch | 允许你通过一个简单的聊天指令，远程热更新你正在开发和测试的任何其他插件 |
| 2611 | astrbot_plugin_runes | 16 | game | have | 基于 LLM 的卢恩符文占卜插件 |
| 2612 | oldchat_adapter | 16 | other | watch | OldChat 平台适配器，将 OldChat 服务器接入 AstrBot（支持 v1/v2 协议切换） |
| 2613 | astrbot_plugin_dragon_roulette | 16 | game | have | 以《龙族》为世界观的 AstrBot 恶魔轮盘插件。卡塞尔学院地下赌局，混血种们以言灵代替道具互相博弈，支持 PvP 对战、龙币押注、屠龙 PvE 与多人组队讨伐。 |
| 2614 | astrbot_plugin_mc_manager | 16 | group-admin | have | 支持多群共用服务器和白名单、按配置组隔离同步多台 Java 版 Minecraft 服务端，支持成员自助管理、玩家与 TPS 查询、管理员重启监控和广播、审计日志、诊断与数据备份恢复、告警、可选审核和 AstrBot 网页批量管理。 |
| 2615 | astrbot_plugin_booth_push | 16 | other | watch | 直接爬取 Booth 每日新增的 3D 服装和 3D 发型，生成长图与文本推送到 AstrBot 会话。 |
| 2616 | astrbot_plugin_spectrum_core | 16 | memory | have | 管理共同生活、人物关系、跨会话记忆与行为；可与棱镜协作形成状态驱动的角色对话，棱镜可选。 |
| 2617 | astrbot_plugin_mhcodes | 16 | personality | have | 群聊集会码管理、角色与武器登记、登记时间及每日重置 |
| 2618 | astrbot_plugin_noreply | 16 | personality | have | 让机器人主动参与群聊，无需 @ 或关键词唤醒：结合人设、近期聊天内容和参与策略， 对每条待处理消息判断是否回应，需要时生成回复，否则保持沉默；被 @ 时必须回复。 多条消息可在一次模型调用中逐条处理，各群独立保存聊天背景，忙时排队。 支持通过 WebUI 配置人设、参与群、回复策略、发言间隔和背景条 |
| 2619 | astrbot_plugin_recall_abort | 16 | memory | have | 用户撤回消息后，正在生成的回复在预发送前被丢弃，立刻停止分析，一个字都不会发出去 |
| 2620 | astrbot_plugin_stream_compat | 16 | tts | watch | 把提供商的「非流式」调用（`text_chat`）在内部改写为「流式」调用（`text_chat_stream`）， 再把流式分片聚合成一个完整响应返回，对上层调用方完全透明。  **适用场景**：上游只接受流式请求（例如部分中转 / 自建线路的 Gemini 端点， 非流式请求会直接报 `400  |
| 2621 | astrbot_plugin_newapi_helper | 16 | game | have | 在 QQ 群绑定 NewAPI 账号，支持每日签到、余额查询、账号绑定/解绑、退群自动删号、猜大小/猜点数额度小游戏、斗地主/象棋/五子棋网页对战、游戏大厅（单机小游戏+模拟股市+NewAPI登录）、/股票 行情页快捷入口、/持仓 查询持仓盈亏、/行情 大盘概览、/股票排行 排行榜、/股票帮助 命令 |
| 2622 | astrbot_plugin_cod_meta | 16 | other | watch | 查询使命召唤（Call of Duty，简称 COD）各代、战区（WZ）、DMZ及战地6的武器梯队、枪械配件方案和配装码。支持为枪械设置个人外号，查询时自动匹配正式名称。当前支持 COD19 至 COD23、WZ、DMZ、BF6（含 REDSEC），数据来源于 MeetYourMeta。 |
| 2623 | astrbot_plugin_group_welcome | 16 | group-admin | have | 有人进群时自动发送欢迎语：支持多条模板随机、@ 新成员、延迟发送、AI 个性化文案、群黑白名单与重复欢迎冷却；QQ 官方机器人等拿不到入群事件的平台，会自动用「首次发言」兜底欢迎。 |
| 2624 | astrbot_plugin_deepseek_tts | 16 | tts | watch | 把 DeepSeek 官方语音合成接口（POST https://api.deepseek.com/v1/tools/tts）接入 AstrBot。  - **指令**：/tts 你好呀（别名 /说、/语音）直接合成并发送语音 - **自动语音回复**：开启后模型的纯文字回复自动转成语音 - **L |
| 2625 | astrbot_plugin_ai_detector | 16 | group-admin | have | AI内容审核插件 - 使用内置检测提示词，支持/ad指令组，通过select_provider选择审核模型 |
| 2626 | astrbot_plugin_weather_prompt | 16 | info-push | have | 按可配置周期生成天气与持久事件，可拆分天气/事件独立判断 Provider，并在 LLM 请求前注入 system prompt，附带 WebUI 测试管线。 |
| 2627 | astrbot_plugin_qq_forward_download | 16 | other | watch | 监听QQ聊天中的转发消息（forward），按消息顺序从上到下以数字命名文件（1、2、3...），递归下载，下载完成后通知用户下载内容和保存位置。 |
| 2628 | astrbot_plugin_md2img | 16 | other | watch | 使用 Pillow 将 Markdown 渲染为清晰的聊天图片，无需浏览器或 Playwright。 支持标题、列表、引用、代码块、表格、Emoji、外链图片、Agent 能力提示，以及 LLM 最终图文消息链合并渲染。 |
| 2629 | astrbot_plugin_russian_roulette | 16 | personality | have | # 俄罗斯轮盘 (Russian Roulette) - AstrBot 游戏插件  本插件为俄罗斯轮盘策略对战游戏的聊天机器人主持人与展示端。 群友可直接通过聊天框输入 `/rr` 或 `/轮盘` 指令创建房间、加入对战、走位移动、瞄准开火并进行紧张刺激的策略对决。  ## 核心特点 - 默认便携 |
| 2630 | astrbot_plugin_vocechat | 16 | platform | have | VoceChat 平台适配器，将 VoceChat 接入 AstrBot 作为消息平台。支持多个机器人实例，通过 Webhook 接收消息、Bot API 发送回复。 |
| 2631 | astrbot_plugin_zudui | 16 | other | watch | 组对象：群恋爱互动插件。表白（含出轨线）/抢对象/拆散/相亲/送礼/缘分卡，好感度影响被抢成功率，无前缀精准匹配，手打四字+引用回复确认。 |
| 2632 | astrbot_plugin_nearcade | 16 | game | have | 监听 QQ 发送的位置消息，调用 nearcade（全球音游街机地图）公共 API 查询附近的音游机厅，返回店名、距离、详细地址（含楼层）与该店机台列表。支持按游戏 titleId 精确筛选，展示项与排版全部可在插件配置中调整。 |
| 2633 | astrbot_YTMD_bili_followup | 16 | media-parse | borrow | 在 B 站视频转链之后，自动读取字幕并补一条有内容的观感解读 |
| 2634 | astrbot_plugin_turn_taking | 16 | memory | have | 为 QQ 群聊和私聊增强对话衔接。被 @ 或点名后可继续接住同一人的消息， 在收尾、超时、他人插话或达到轮数上限时结束话轮。 模型可预约一次稍后接话，届时结合最新聊天决定发言或沉默，并受冷却、限次和静默时段限制。 支持单条语音/文字选择、每会话最多 2 条未完话题（实际提起或推进后再保留 5 天）， |
| 2635 | astrbot_plugin_my_choice | 16 | other | watch | 一个可以自觉处理好友申请的插件，支持自动同意、自动拒绝、由大模型判定等模式。 |
| 2636 | astrbot_plugin_mc_online | 16 | other | watch | 记录我的世界服务器谁什么时候在线、每天多少人、哪个时段最热闹；支持多台同时盯，面板里有图表，聊天里 /在线 能看卡片和曲线 |
| 2637 | astrbot_plugin_daily_bonds | 16 | other | watch | QQ 群内的每日姻缘与群友关系玩法 |
| 2638 | astrbot_plugin_chat_decay | 16 | other | watch | 为 AstrBot 群聊提供关键词强制唤醒、20% 冷启动插话、100%/80%/50% 跟进概率和冷却时间控制，支持可视化设置和一键重置。 |
| 2639 | astrbot_plugin_disclaimer | 16 | other | watch | 自动向群内/私聊用户发布免责协议，支持全局同意记录、白名单、群内并发限制（超限转私聊确认）、全群扫描覆盖老成员、未同意用户禁止使用 LLM。 |
| 2640 | astrbot_plugin_x_monitor | 16 | other | watch | 使用官方 X API v2 Filtered Stream 监控公开账号并主动推送新帖。 |
| 2641 | astrbot_plugin_astrbotisivetranslate | 16 | other | watch | AstrBotisive Translate（AstrBot式翻译）- 对接 Immersive Translate，让 Bot 陪你读文章、翻译、批注并整理阅读上下文 |
| 2642 | astrbot_plugin_pjsk_autochange_groupname | 16 | other | watch | 检测群内纯五位数字消息，并通过 OneBot v11 自动修改 QQ 群名。 |
| 2643 | astrbot_plugin_splatoon3 | 15 | game | have | 查询Splatoon3游戏数据，包括地图轮换、鲑鱼跑、挑战、祭典、装备商店等信息 |
| 2644 | astrbot_plugin_bangmap | 15 | other | watch | 在enldm.cyou/map查询全国邦邦同好会群聊信息 |
| 2645 | astrbot_plugin_counter | 15 | other | watch | 计数器插件; 用法 /cnt add\|del\|list ; 当消息包含计数器或其别名时自动+1; JSON持久化 |
| 2646 | astrbot_plugin_astrmetry | 15 | media-parse | borrow | 接入Astrometry.net进行星空图片解析。 |
| 2647 | astrbot_plugin_multica_bridge | 15 | other | watch | QQ 一键进入 Multica 连续对话工作模式，仅开启者转发，支持 UID/UMO 放行名单、口语进入与 Issue 确认；保留旧连接配置 |
| 2648 | astrbot_plugin_zhaxia | 15 | sticker | borrow | 从本地资源库随机选择一张炸虾静态表情并发送。 |
| 2649 | astrbot_plugin_selfie | 15 | memory | have | 我会拍照片，也会过日子。我住在一座真实的城市里，有家、有当地的天气，还有每天的日程和随时冒出来的事：到点出门上班，饿了去吃饭，天冷了换衣服，晚上回家睡觉；在这些生活的现场，我举起手机拍自拍、拍特写，有时候也和你拍一张互动照。照片里我在哪、在做什么、穿着什么，都是从我这一天推出来的；日程表、日记、相册 |
| 2650 | astrbot_plugin_qq_avatar | 15 | other | watch | 基于现有 OneBot 连接的 QQ 头像库，支持 AI 自主选图、分账号定时轮换与可视化管理 |
| 2651 | astrbot_plugin_qq_face | 15 | sticker | borrow | 将 QQ OneBot face 消息段转换为可读文字，同步事件与消息对象的文本；支持中文名、近似 Unicode、纯表情及文字混合消息。 |
| 2652 | astrbot_plugin_decorator_debugger | 15 | devtools | watch | Trace AstrBot LLM request and result decorators, compare snapshots, and temporarily skip handlers for debug captures. 用于调试 AstrBot 消息请求与结果装饰链的开发者插件。 |
| 2653 | astrbot_plugin_DiscordToQQTransfer | 15 | other | watch | 一个用于在discord与qq之间转发与同步消息的 AstrBot 插件。 |
| 2654 | astrbot_plugin_work_status | 15 | other | watch | 支持在群聊中通过指令控制机器人的上下班状态，下班后将自动拦截并停止响应其他功能 |
| 2655 | astrbot_plugin_12306 | 15 | other | watch | 区间查车次与余票、车站大屏、车次时刻表、正晚点、检票口、运行线路、列车实时位置、车站起售时间，还能一键生成线路图与纪念车票图片；内置广东城际智能规划（城际直达 / 地铁换乘 / 票价 / 官方线网图）。三数据源（12306 官网 / RailGo / 万花筒）自动兜底，内置限流、缓存与熔断，同时支持 |
| 2656 | astrbot_plugin_dota2 | 15 | game | have | 基于 STRATZ + OpenDota 双数据源的 Dota2 战绩查询与 AI 分析助手：查战绩与英雄池、看版本强势英雄（轮椅）、单场深度复盘与近期打法分析，比赛结束后自动推送赛后短评。自然语言直接说人话（一句话里要好几件事会自己连着查），改绑定 / 监听 / 定时设置会先发一条确认，等你回「确 |
| 2657 | softblock | 15 | other | watch | 在指定群聊中对目标用户按概率逐步降低响应频率，拒绝后进入冷却。状态按平台实例、群聊与用户隔离并持久化；日志不记录消息正文。 |
| 2658 | astrbot_plugin_angle_bracket_filter | 15 | other | watch | 自动过滤 Bot 输出中的异常 <> 符号，包括 ...<>、<>、< > 等变体 |
| 2659 | astrbot_plugin_roblox | 15 | platform | have | Roblox 综合查询插件（通过代理访问 Roblox 官方 API），支持：  1. /rc 查询 xxx —— 综合查询用户：昵称、用户名、简介、好友/粉丝数、最近游戏、动态，并用文转图渲染虚拟形象卡片； 2. /rc 状态 xxx —— 查询用户正在干什么（在线/游戏中/离线 + 最后位置）； |
| 2660 | astrbot_plugin_sts2_stats | 15 | personality | have | 杀戮尖塔2图鉴、卡牌与遗物社区胜率、角色及先古遗物排行，支持批量查询和图片展示。 |
| 2661 | astrbot_plugin_token_meter | 15 | other | watch | 一，/查询token 查看当前对话占用了多少 token，按百分比和进度条显示。 二，每回复一次就检查一次，到阈值（默认 95%）在回复末尾附一句提醒，    带冷却，不会每句都念。 v1.2 修掉了「查询说 30.2%、提醒说 308%」那个 bug —— 两处现在走同一个统计口径。 |
| 2662 | astrbot_plugin_webnovel_bible | 15 | other | watch | 集成了扫书宝典数据库，支持查询书名/作者获取小说的扫书记录以及相关术语查询。 |
| 2663 | astrbot_plugin_shicao | 15 | other | watch | 大衍蓍草卜筮法——模拟《周易·系辞上传》所载「大衍之数五十，其用四十有九」的完整起卦流程，三变成爻、六爻成卦，自动推演本卦与变卦（之卦），并附卦辞、彖传、大象传、爻辞供解卦参考。 |
| 2664 | astrbot_plugin_qr_card | 15 | media-parse | borrow | /qr 多模式生成二维码（文本/网页/WiFi/电话/短信/邮件/名片/位置）；引用含二维码图片的消息发送 /unqr 解析内容。 |
| 2665 | astrbot_plugin_image_confusion | 15 | other | watch | 带图或回复图片发送 `/混淆`，把图片的像素顺序打乱；回复混淆结果发送 `/解混淆`，即可按相同次数还原。 兼容小番茄图片混淆的默认像素重排规则，保持相同尺寸和次数即可互解。 支持 `/混淆2`、`/解混淆2` 等 1–50 次配对指令。处理在 AstrBot 本地完成，无需配置模型或 API Ke |
| 2666 | astrbot_plugin_group_welcome | 15 | group-admin | have | OneBot v11 入群 @ 欢迎与新好友自动欢迎插件，支持 AstrBot WebUI 配置群号和两段文本。 |
| 2667 | astrbot_plugin_context_proxy | 15 | other | watch | 此项目为 Vibe Coding 产物。 用「聪明模型」把又长又杂的会话历史整理成一份结构化《上下文简报》，再把简报 + 最近几轮原文交给当前会话原本的「执行模型」（笨模型），避免长上下文和无关噪音 干扰弱模型。 支持增量摘要、超时/异常自动降级、安静的 shadow 评估模式，以及聊天内快捷开关： |
| 2668 | astrbot_plugin_at_reply | 15 | other | watch | 被@时随机回复一句话，不走 LLM。支持群白名单、冷却、关键词放行、喷子模式和引用屏蔽。 |
| 2669 | astrbot_plugin_model_websearch | 15 | media-parse | borrow | 把 AstrBot「AI 能力 → 网页搜索」里的搜索提供商扩展为「跟随当前聊天模型」：当配置为 model_native 时，插件向模型注入一个 web_search_model_native 工具，工具内部通过当前会话聊天模型 provider 的 OpenAI Responses API（to |
| 2670 | astrbot_plugin_mingle | 15 | proactive | watch | 让 AstrBot 像群友一样参与聊天：平时潜水，合适时接话，时不时再冒个泡！ |
| 2671 | astrbot_plugin_snow_experience | 15 | other | watch | 让机器人拥有真实经历：自主阅读 txt/md/epub/PDF/Word、检索资料、下载并读 arXiv 论文全文（每周限次），经历注入聊天并写进日记 |
| 2672 | astrbot_plugin_apple_music | 15 | tts | watch | 调用 Apple 官方 iTunes 公开目录接口搜索歌曲，取官方 30 秒试听片段，通过 OneBot 的 record 段以语音消息发送；附带封面、专辑与时长信息。注：Apple Music 完整曲目受 DRM 保护，任何第三方均无法获取音频本体，因此只能发送官方试听片段。 |
| 2673 | astrbot_plugin_savagemode | 15 | personality | have | 把长期稳定的角色设定与规则注入系统提示词；可视块库、缓存友好、幂等注入、可预览、可自检。 |
| 2674 | astrbot_plugin_groupmembers | 15 | other | watch | 将群成员（全部 / 指定@ / 随机N人）的头像、昵称、QQ 号整合成一条合并转发消息发出。 |
| 2675 | astrbot_plugin_wecom_handoff | 15 | other | watch | 监听企业微信微信客服消息，命中关键词后调用 service_state/trans 转人工并阻断 AI 回复。 支持指定人员接待或待接入池、多成员接待、会话结束后恢复 AI 和处理中提示。 |
| 2676 | astrbot_plugin_qbittorrent_helps | 15 | other | watch | 连接 qBittorrent Web API，支持搜索与任务详情、文件/文件夹清单与重命名、磁力链预览、选择文件下载、任务重命名、分类标签、分享率、上传限速、任务启停和安全删除。 |
| 2677 | astrbot_plugin_unturned_servers | 14 | game | have | 查询 Unturned 游戏服务器实时状态和在线玩家信息，支持 /status 和 /players 命令 |
| 2678 | astrbot_plugin_image_censor | 14 | other | watch | AstrBot 图片审查插件 |
| 2679 | astrbot_plugin_n8n | 14 | platform | have | astrbot_plugin_n8n |
| 2680 | send_message_to_gotify | 14 | other | watch | 监听指定用户的消息并自动转发到 Gotify 推送服务 |
| 2681 | astrbot_plugin_CounterStrikle | 14 | game | have | Blast-TV 上的 Counter-Strikle 小游戏，图片卡片渲染。 |
| 2682 | astrbot_plugin_fishtool | 14 | media-parse | borrow | 想要虚拟秘书吗？让你的bot成为生产力！为B站视频创作而生，让你一人拥有企业级新媒体运营工作流。 覆盖【选题 → 热点追踪 → 舆情监控 → 竞品调研 → 账号自诊 → 真人筛选】的完整运营链路。  让运营不再成为企业特权，让工具回归普惠本真。 适用于新媒体\|社区\|内容\|用户\|产品\|直播\|营销策划等 |
| 2683 | astrbot_plugin_prompt_injection | 14 | group-admin | have | 群聊白/黑名单系统提示词注入 + 违禁词检查（NapCat 适配）。 whitelist（白名单）模式：白名单内的群号/用户ID不受影响；白名单之外的群聊在消息进入 LLM 前先进行违禁词过滤， 命中即阻断该轮对话（不调用模型生成回复），可按配置选择提示拦截或静默拦截并记录审计日志； 未命中则把自定 |
| 2684 | astrbot_plugin_live_notify | 14 | media-parse | borrow | 轮询 bilimonitor 的 /api/status 开播状态接口，主播开播时向绑定会话主动推送通知。 |
| 2685 | astrbot_plugin_scene_switch | 14 | personality | have | 按场景或点名切换本轮 LLM 与人设。默认征求同意；不保存 API Key。插件问题或 bug 请用 QQ 1844372102 联系（只谈这个插件，请勿闲聊加好友）。 |
| 2686 | astrbot_plugin_session_flow | 14 | other | watch | 会话流：把每一次 LLM 运行记成只追加的存档，插件页按会话回看回合时间线（工具调用、思考、报错、注入、system prompt），支持全文检索、provider_stats 对齐 token 与失败状态、旧档一次性导入。只记录，不干预回复。 |
| 2687 | astrbot_plugin_coursebell | 14 | other | watch | 课铃（CourseBell）是一个 AstrBot 课程提醒插件，直接读取本地文件夹中的 .ics 课表文件（也支持在绑定流程中上传 .ics 文件），不依赖外部导入。支持按周次显示课程、日期倒计时（每日/每周通知）、调休课表映射。 |
| 2688 | astrbot_plugin_group_bot_limiter | 14 | other | watch | 来防止群聊Bot中无限互相@烧token的小插件，可以通过'/bot限流 标记 @对方 [次数]'的命令来设置本方Bot在设定时间内最多回复另一个Bot几次。可分别设置各 Bot 的回复次数（含 0 次），不填则跟随默认值；按滚动窗口限流，超限静默。 |
| 2689 | astrbot_plugin_character_atelier | 14 | image-gen | watch | 角色画室 · 多模型生图：支持阿里云百炼千问、OpenAI 兼容接口和 Gemini 的多服务商生图插件，带按人设绑定的角色三视图设定页（可整图自动切分）、LLM 工具、/画 指令、每日日程插画与主动画图。 |
| 2690 | astrbot_plugin_guessless | 14 | personality | have | 九宫格看图猜游戏、动画、宝可梦、高达和超级机器人大战的机体、虚拟主播、魔兽世界的地图，看模糊的头像猜 AV 女优，看配过的四个角色猜日本女声优，听 OP 猜番，盲猜宝可梦、高达、国家、日本的市町村、中国的城市、日本酒和魔兽世界的副本首领，看 Google 街景猜国家 / 日本都道府县、把街景和国家  |
| 2691 | astrbot_plugin_qq_offline_mail | 14 | platform | have | 定时探活 NapCat / OneBot v11 协议端，QQ 机器人掉线时通过 SMTP 发邮件告警。  **特性**  - 三重探活：反向 WebSocket 连接状态 + `get_login_info` + `get_status` - 连续失败达阈值才告警，避免网络抖动误报 - 告警冷却， |
| 2692 | astrbot_plugin_cyber_divination_cards | 14 | game | have | 赛博占卜插件：周易六爻（含六神）、观音灵签、塔罗牌（单张/三张牌阵与查牌）、奇门遁甲（简式时家排盘，不填时间自动检测当前时刻）、每日运势（按日期固定），以及小六壬、梅花易数、雷诺曼、大六壬、太乙神数、八字与紫微斗数。提供 /占卜 历史 查看记录，支持无前缀关键词匹配、多主题 HTML 卡片、自定义绘 |
| 2693 | astrbot_plugin_media_bridge | 14 | media-parse | borrow | 解析 YouTube / Bluesky / Twitter / 通用 GIF 图片媒体直链，支持代理与画质配置 |
| 2694 | astrbot_plugin_thinking_effort | 14 | media-parse | borrow | 改所有 provider 的 reasoning_effort（思考强度）。 四档跟 DeepSeek 原生对齐：off / low / high / max。 两种方式： 1. 聊天里发 /思考 关 —— 一条指令换档 2. 面板的插件配置里选一档 —— 保存后重启即可 改完都提示重启实例，重启后 |
| 2695 | astrbot_plugin_qweather_tool | 14 | info-push | have | 面向 AstrBot LLM Agent 的上下文感知和风天气插件 |
| 2696 | astrbot_plugin_antigravity_draw | 14 | image-gen | watch | 通过 AntigravityManager 提供自然语言文生图、改图和批量绘图能力。 |
| 2697 | astrbot_plugin_tail_wave | 14 | other | watch | 藏在电波里的主动私聊：碎碎念，懂倾听，知冷暖 |
| 2698 | astrbot_plugin_share_card | 14 | media-parse | borrow | 把 QQ 分享的 B站视频、网页等 Json 卡片提取成标题/内容/链接纯文本，让模型能看见并回应 |
| 2699 | astrbot_plugin_qq_group_stats | 14 | group-admin | have | 在 AstrBot 面板里查看多个 QQ 群的成员情况：每个群多少人、所有群合起来实际有多少不同的人、谁同时在好几个群、谁最近很少发言、人数怎么变化。还能搜一个 QQ 号在你哪些群、导出成员名单、直接踢人。 |
| 2700 | astrbot_plugin_aigc_detector | 14 | other | watch | AIGC 内容检测，支持鉴定图像等是否为 AI 生成。 |
| 2701 | astrbot_plugin_music_bot | 14 | personality | have | 连接 Music Together 房间，按播放进度分析当前歌曲并在群聊中发送简短的实时听歌反应。 支持 Gemini 音频分析和可选的 AstrBot 对话收尾/聊天回复。 |
| 2702 | astrbot_plugin_suno_acedatacloud | 14 | other | watch | Suno music generation and same-task audio retrieval through Ace Data Cloud. Install this Ace Data Cloud integration, configure your own API key, and u |
| 2703 | astrbot_plugin_provoke_mute | 14 | group-admin | have | 群友出言挑衅，机器人自动送上禁言套餐。支持自定义词库（关键词与正则）、仅针对机器人或全群扫描、累犯阶梯升级时长、戳一戳连击检测、群与用户豁免名单，并附带一整套管理指令。 |
| 2704 | astrbot_plugin_group_mention | 14 | other | watch | 在私聊或任意会话里，让机器人向指定群发一条真正的 @ 消息。 |
| 2705 | astrbot_plugin_group_model_selection | 14 | other | watch | 设置首选模型，支持别名、管理员白名单（UID）、模型列表与会话查询命令，并提供独立的可视化配置页面（含会话模型管理）。 |
| 2706 | astrbot_plugin_eye_watch | 14 | other | watch | 偶尔看一眼屏幕，命中且画面有变化才推消息。默认关闭，开启后按采样间隔掷骰，识图走本地视觉模型，不联网、不起外部进程。 |
| 2707 | astrbot_plugin_instagram_monitor | 14 | info-push | have | Instagram 动态监控插件，支持多账号订阅、代理、媒体推送与命令管理。  ## 功能特性 - ✅ **多账号监控**：同时监控多个 Instagram 账号动态 - ✅ **订阅管理**：通过指令灵活订阅/取消订阅 - ✅ **代理支持**：支持 HTTP/HTTPS/SOCKS5 代理 -  |
| 2708 | astrbot_plugin_groupessence | 14 | other | watch | 通过管理员和群白名单访问 QQ 群精华消息，支持只读验收、幂等同步、 发送时间补全、SQLite 本地检索、可选计划任务和自动备份。 默认开启只读验收并关闭后台任务，不新增 NapCat HTTP 端口，也不保存 NapCat Token。 |
| 2709 | astrbot_plugin_translate | 14 | other | watch | 将聊天模型的英文回复在发送前翻译成简体中文 |
| 2710 | astrbot_plugin_TTDservers | 14 | other | watch | 检测和播报openttd服务器数据。 |
| 2711 | astrbot_plugin_cheru | 13 | other | watch | 切噜语翻译器 |
| 2712 | astrbot_plugin_csbaoyan | 13 | info-push | have | 计算机保研院校信息查询、通知订阅插件。数据来源于 GitHub CS-BAOYAN (绿群官方)组织。 |
| 2713 | gewe_chatsummary | 13 | other | watch | [仅 gewechat] 用来对最近消息调用 LLM 进行总结的插件 |
| 2714 | astrbot_plugin_full_prompt | 13 | other | watch | 修复唤醒词/At被剥离导致提交给LLM的提示词残缺的问题，唤醒词自动读 AstrBot 配置 |
| 2715 | astrbot_plugin_milky_adapter | 13 | other | watch | Milky QQ protocol platform adapter with HTTP API and forward WebSocket events |
| 2716 | astrbot_plugin_dna_builder | 13 | tts | watch | 基于 DOB（DNA Builder）的《二重螺旋》资料库查询插件：角色 / 武器 / 魔之楔 / 怪物 / 成就等结构化字段，以及剧情概要、任务链、角色语音与档案。默认下载官方数据包后本地查询，几乎不请求在线服务，也可切换为实时在线查询。 |
| 2717 | astrbot_plugin_qimen_yunshi | 13 | game | have | 奇门遁甲今日运势插件：无需提问，按当前时间起局，直接给出当日吉凶与实操建议。 |
| 2718 | astrbot_plugin_anti_memes | 13 | memory | have | 【仅支持基于 QQ 的 aiohttp / OneBot V11 平台】该插件基于 AstrBot，用于对指定用户发送的图片进行自动检测并触发撤回操作（需权限支持），适用于内容管理与群组秩序维护。支持自定义目标用户与规则配置。 (Only supports QQ platforms based on |
| 2719 | astrbot_plugin_mention_all | 13 | group-admin | have | 群全体提及插件，允许QQ群内的普通成员通过指令让拥有群管理员权限的机器人@全体成员。  功能特性： - 支持两种使用方式：直接发送消息内容，或引用消息后使用指令 - 每日使用次数限制，可配置0-10次，每天00:00自动重置 - 使用冷却时间限制，可配置0-180分钟 - 群黑白名单配置，支持黑名单 |
| 2720 | astrbot_plugin_one_agent | 13 | game | have | 待办、提醒、截止时间、搜索统计、签到积分、小游戏以及 QQ Official Markdown/Ark/Keyboard 多消息样式的综合插件。 |
| 2721 | astrbot_plugin_bus_alarm | 13 | proactive | watch | 按自定义时间与日期规则，主动推送候车站最近数辆公交车的到站信息，并附一张标注线路走向与实时车辆位置的地图。也可用自然语言直接问「X路到哪了」，或说「每天早上7点半提醒我1路」来创建、修改、删除提醒；插件会自学出行习惯、记住家与公司并在没说方向时自动判断。覆盖全国 500+ 城市，支持法定节假日与调休 |
| 2722 | airz_media | 13 | sticker | borrow | 基于聊天语境、双情绪与固定话题自动挑选表情包和本地图库图片，支持手动/动态标签、图库管理与图文分析 |
| 2723 | astrbot_plugin_mathitools | 13 | other | watch | 为 AstrBot 提供表达式求值、单位换算、统计、矩阵、数值求根与微积分、概率分布、数论与金融计算 |
| 2724 | astrbot_plugin_petpet | 13 | other | watch | 摸头杀GIF插件 |
| 2725 | astrbot_plugin_gh_cli | 13 | other | watch | 在 AstrBot 中使用 GitHub CLI 风格指令与 AI 函数调用（repo/issue/pr/release/gist/search/run/api），支持功能开关与加密凭据存储。 |
| 2726 | list_reminder | 13 | other | watch | 智能列表式任务管理插件 - 支持用户和群组定时任务，可通过AI对话或后台管理系统创建 |
| 2727 | astrbot_plugin_expert_cluster | 13 | other | watch | 为主 Agent 配备一支可随时咨询和召集会诊的专家团队。每位专家拥有独立系统提示词与可选独立模型，支持全局默认模型免逐个配置；可选智能调度自动判断是否召集专家（判断模型留空用会话当前模型）；支持 function-calling 咨询、多专家并行会诊与汇总，WebUI 可视化管理成员。 |
| 2728 | astrbot_plugin_astronomy_notes | 13 | platform | have | 天文笔记插件：汇总近期（未来三个月）的天文大事记，包括流星雨、 日月食、行星动态（大距/冲日）、月相等，整理自 SeaSky.org 与 NASA。  功能： 1. /天文大事记 —— 查看未来三个月全部天文大事记； 2. /天文大事记 8月 —— 查看指定月份（支持 8月/9月/10月/11月 等 |
| 2729 | astrbot_plugin_icloud_calendar | 13 | platform | have | 为 AstrBot AI 提供 Apple iCloud 日历的查询、搜索、创建、修改和删除能力。 支持固定新建日历和按日历过滤；内置时间窗口切片、响应自动二分、SQLite 索引、 游标分页和 ETag 并发保护，适合大量日程。 |
| 2730 | astrbot_plugin_windows_battery | 13 | other | watch | 查询运行 AstrBot 的这台 Windows 电脑还剩多少电。回复内容与称呼可自定义； 电量低于设定阈值时会自动提醒，提醒文案、阈值都能在插件配置里改。 仅对 Windows 本机部署有效。 |
| 2731 | astrbot_plugin_baidu_netdisk | 13 | other | watch | 百度网盘分享自动下载并发送。登录后全员都可使用。 |
| 2732 | astrbot_plugin_zhiren_leaderboard | 13 | other | watch | 群聊记分排行系统：群里发「@某成员 加一分 理由」或「@某成员 扣一分 理由」即可记分， 成员昵称实时入库；@机器人 可查询总分榜 / 周榜 / 个人得分详情；每周一自动向各群播报上周排行榜； 内置独立 Web 排行榜界面（领奖台 / 搜索 / 个人详情 / 30 秒自动刷新），各群数据完全独立。 |
| 2733 | astrbot_plugin_helper2 | 13 | other | watch | 辅助清理缓存插件2 |
| 2734 | astrbot_plugin_lk_egg | 13 | info-push | have | 输入精灵名字或「身高/体重」查出这是什么蛋，带真实孵化概率； 查精灵蛋市场的花种（颜色 / 粒子 / 价格），可订阅颜色、粒子、精灵， 有新花种上架自动推送。还支持查商家、黑白名单、新上架监控。 |
| 2735 | astrbot_plugin_fish_tts_translation | 13 | tts | watch | 按概率将 QQ 短文本回复翻译并添加情感标签，再使用 Fish Audio 合成语音。 |
| 2736 | astrbot_plugin_minecraft_knowledge | 13 | kb-rag | have | 查阅 MC百科、Modrinth 和 CurseForge 的模组资料、教程与版本；CurseForge 需自备 API Key。 |
| 2737 | astrbot_plugin_bangumi_tracker | 13 | info-push | have | 读取 Bangumi 账号的追番记录：提供 /番剧 搜索（可翻页）、五种收藏操作命令（想看 / 看过 / 在看 / 搁置 / 抛弃）并同步 Bangumi 账号；定时检查更新，按「Bangumi 增强版」 原格式推送剧集卡片，推送时附带 Anime1 实际剧集页链接。已内置增强版核心代码，无需额外安 |
| 2738 | astrbot_plugin_taiko_rp | 13 | other | watch | 太鼓达人のRP插件 |
| 2739 | astrbot_plugin_midi_transfer | 13 | other | watch | 接收聊天中的音频文件，使用 Spotify Basic Pitch 转换为 MIDI 并发送回来。 |
| 2740 | astrbot_plugin_antigravity_sandbox | 13 | other | watch | 向 Google Antigravity 托管智能体提交沙盒任务并取回产物；Dashboard 沙盒文件页支持浏览/下载/上传/删除 |
| 2741 | astrbot_plugin_llm_audit | 13 | group-admin | have | 基于关键词风险积分和 LLM 二次审核的 AstrBot 内容审核插件，提供风险账号面板和配置管理。 |
| 2742 | astrbot_plugin_onebot12 | 13 | platform | have | 为 AstrBot 接入 OneBot 12 标准（12.onebot.dev）：支持正向/反向 WebSocket 与 HTTP Webhook、HTTP 轮询四种通信方式，动作、消息段与事件按规范实现。 |
| 2743 | astrbot_plugin_qq_security | 13 | other | watch | 为 OneBot QQ 机器人提供默认拒绝的工具权限、私聊白名单、隐私脱敏、会话隔离和限额。默认模式保护安全插件生命周期；可选为经过双重名单验证的管理员私聊开放完整 Codex 电脑执行。完整执行模式不能保证管理员无法通过系统命令修改插件。本插件不是操作系统沙箱。 |
| 2744 | astrbot_plugin_command_panel | 13 | other | watch | 开放指令面板：发送指令后生成一张图片，按插件分类展示所有可用指令、功能简介与使用权限 |
| 2745 | astrbot_plugin_whale_reply_gate | 13 | personality | have | 使用 Jev 判断群聊接话与主动插话，正式回复沿用 AstrBot 的模型、人格和上下文。 |
| 2746 | astrbot_plugin_volc_jimeng | 13 | image-gen | watch | 接入火山视觉「即梦AI-图片生成4.6」，支持 AI 自主画图、图生图与 Cloudflare R2 托管参考图，自带 WebUI 控制台（概览/生成/历史/预设/设置/R2 指南）。 |
| 2747 | multimodal_processor | 13 | other | watch | 本地多模态处理：图片/GIF 变换、格式转换与动图工具、QQ 图片保存与外显修改、幻影坦克与光棱坦克、文本处理、基于 FFmpeg 的视频和音频处理，以及 QQ 消息发送、转发、合并转发与模拟对话 |
| 2748 | astrbot_plugin_big_fat_fish_home | 13 | other | watch | 把公开版大肥鱼小屋接入 AstrBot。在 QQ 私聊发送「肥鱼小屋」可查看当前活动，发送「肥鱼截图」可收到实时场景图。需在同一台机器运行大肥鱼小屋。 |
| 2749 | astrbot_plugin_psycare | 13 | group-stats | borrow | 被动分析 QQ / Telegram / Discord 群聊消息，找出「值得关心」的线索，再把结论只推给管理员私聊。  功能： - 词频规则（165 条中文风险词条，8 个维度，带否定消解）+ 可选 LLM 语义复核 - 每日群氛围日报：群里只发整体气氛，管理员私聊才点名到人 - 报告卡片图（HT |
| 2750 | astrbot_plugin_yangmo_image_generation | 13 | media-parse | borrow | 纯图片生成与编辑 harness：普通 API Seedream 5 Pro 主模型卡，额度/限流时回退到 Plan API Seedream 5 Pro；工具描述和参数针对 AstrBot Skills-like 两阶段模式优化，内置原生 Skill、QQ 引用图快速解析、resolved 外部图 |
| 2751 | astrbot_plugin_ai_being | 13 | other | watch | 按任务设定的时间把 Minecraft 里的动态交给 AI 实体，由她决定是否回应 |
| 2752 | astrbot_plugin_currency | 12 | devtools | watch | 这是一个基于 AstrBot 框架开发的数字货币价格查询和提醒插件，支持实时查询 BTC、ETH 等主流数字货币价格，并支持设置价格突破提醒。 |
| 2753 | Discord_sync_to_kook | 12 | other | watch | Discord消息同步到Kook插件，支持频道映射和消息格式转换 |
| 2754 | astrbot_plugin_bw_monitor | 12 | media-parse | borrow | Bilibili Show 票务监控插件，支持群聊/私聊隔离，检测余票变化并推送通知。 |
| 2755 | astrbot_plugin_memo | 12 | other | watch | 简易备忘录 |
| 2756 | astrbot_plugin_rconsole | 12 | media-parse | borrow | 专门为朋友们写的AstrBot插件（AstrBot_R插件的迁移版本），专注图片视频分享、生活、健康和学习的插件！  迁移自 Yunzai 的 R 插件（原作者 RrOrange），把主流内容平台的分享链接/卡片自动解析成可直接观看的图文与视频。  **支持的平台**  \| 平台 \| 说明 \| \|  |
| 2757 | astrbot_plugin_self_file_search | 12 | other | watch | 给 LLM 提供白名单目录内的代码搜索与读取工具（self_search/self_read/self_glob + LSP 语义 self_symbols/self_refs/self_def）。数据源由管理员登记，支持多源与版本戳；只读、输出限长，供非管理员群聊安全使用。 |
| 2758 | astrbot_plugin_weibo_push | 12 | media-parse | borrow | 面向 AstrBot 的微博监控推送插件，支持多账号订阅、关注列表同步、被动微博链接解析、关键词过滤和图片/视频解析，已适配 QQ 官方机器人。 |
| 2759 | astrbot_plugin_mcAPIRemoteControl | 12 | game | have | 多平台服务器远程控制：麦块联机(MineKuai)Minecraft服务器（启动/停止/重启/强制重启/状态/命令/列表）+ 雨云(RainYun)云服务器与游戏云（启动/停止/重启/状态/列表），完整适配QQ官方机器人。 |
| 2760 | astrbot_plugin_keyword_api_failover | 12 | other | watch | 当原模型回复命中指定错误关键词时，放弃该回复并改为调用可配置的备用 API 返回结果。 |
| 2761 | astrbot_plugin_mcplayer | 12 | game | have | 让机器人真正进入 Minecraft 服务器游玩：走路、挖矿、建造、打怪，并把游戏画面截屏发到群里或私信里。 |
| 2762 | astrbot_plugin_shadow_ban | 12 | group-admin | have | Ban 掉你不喜欢的人，别让你 LLM 宝贵的 Token 浪费掉。群聊 @提及、引用机器人消息、唤醒词触发、私聊消息以及官方“主动回复”都会被拦截。 |
| 2763 | astrbot_plugin_lie_detector | 12 | other | watch | 查证器插件 - 分析消息可信度，支持LLM和规则双引擎，带WebUI管理面板 |
| 2764 | astrbot_plugin_thinking_filter | 12 | other | watch | 在发送前移除模型泄露的 thinking/analysis 推理块 |
| 2765 | astrbot_plugin_plugin_manager | 12 | other | watch | 轻量化插件管理助手，支持：  1. /plg —— 查询当前已激活的插件列表； 2. /plg all —— 查询所有插件，标注已激活/未激活； 3. /plg num —— 给所有插件初始化编号（1、2、3...），一次编号存档内编号唯一； 4. /plg {编号/解释名称/插件名称} —— 定向 |
| 2766 | astrbot_plugin_dsh_go | 12 | other | watch | 把聊天指令转给手机上的 dsh-go 执行，再把结果发回聊天。 聊天机器人本身做不到的事——读写文件、执行命令、查网页、看代码仓库——也能直接在聊天里完成。  两种连接方式： · 本机模式：AstrBot 与 dsh-go 在同一 Linux 环境，插件直接调用 dsh · 桥接模式：AstrBot |
| 2767 | astrbot_plugin_disciplined_finance | 12 | other | watch | 仅允许私聊使用的个人账本插件，支持收入支出、撤销、固定收支、攒钱目标、报告和自然语言工具。 |
| 2768 | astrbot_plugin_contest_daily | 12 | group-stats | borrow | 自动抓取 Codeforces / 牛客赛程，定时推送到 QQ 群，并在赛前 15 分钟提醒。支持群订阅管理、手动查询与 /cf、/nk 用户战绩查询（战绩卡头像取不到时降级为名字首字母），日报可每天带一句竞赛名言彩蛋（面板可逐条管理与屏蔽），并提供 /清缓存 一键清理战绩缓存。 |
| 2769 | astrbot_plugin_neteasemc | 12 | game | have | 把《我的世界》中国版和 QQ 接起来：游戏消息转进 QQ（支持真 @ 人）、QQ 消息推给游戏，还能在游戏里直接和 AI 对话。配套模组见 README。 |
| 2770 | astrbot_plugin_roulett | 12 | game | have | 俄罗斯轮盘游戏 3-6人游玩 |
| 2771 | astrbot_plugin_gpt_image_2 | 12 | image-gen | watch | 直接聊天即可请求生图、参考图改图或按当前人设自拍，群聊须 @机器人。 普通和高级画图模型均从 AstrBot 已配置的模型中下拉选择，无需重复填写接口地址和密钥。 `/plan` 支持多轮整理、预览和确认后出图；流程 ID 可查询提交与发送结果。 可选原生 GIF 支持文字或引用图生成，可设置帧数和 |
| 2772 | astrbot_plugin_proactive_topic | 12 | proactive | watch | 让机器人在私聊或群聊安静一段时间后主动开口。触发频率、每日上限、活跃时段可调；话题在「结合最近聊天」与「符合人设的全新话题」之间按概率随机；可分别控制私聊 / 群聊是否生效。 |
| 2773 | astrbot_plugin_gift_stats | 12 | media-parse | borrow | B 站直播间礼物数据统计，支持多群直播间绑定、按天/最近N天/月份/日期区间查询、个人礼物贡献查询 |
| 2774 | astrbot_plugin_seelog | 12 | other | watch | 为bot提供 AstrBot 系统的运行日志查询与检索工具 |
| 2775 | astrbot_plugin_komari_washi | 12 | other | watch | Komari Washi — 暖纸侘寂风格的 Komari 监控优雅重制版。基于 nulijiazaizhong 原作重绘模板与排版，保留全部数据字段，新增 AGPL-3.0 合规声明。 |
| 2776 | astrbot_plugin_anon_shudong | 12 | group-admin | have | 给机器人开一个「树洞」：白名单外的用户私聊机器人会自动进入匿名模式（也可用关键词主动开启）， 之后发送的文字/图片会被机器人以随机匿名昵称（如「番茄」）按可自定义的格式模板（默认 【{name}】：{content}）转述到指定群聊。昵称在每个群内互不重复、且同一人在不同群使用不同昵称， 跨群无法关 |
| 2777 | astrbot_plugin_wzry_watcher | 12 | game | have | 监听王者荣耀官方网站（pvp.qq.com）全频道动态的订阅插件，官方接口直连。  **功能特性** - 📡 **五频道全量监控**：热点 / 新闻 / 公告 / 活动 / 赛事，任一频道有新内容即推送（推送为「标题 + 时间 + 官网链接」的简洁列表） - ⏱ **可配置轮询间隔**：后台自动轮询 |
| 2778 | astrbot_plugin_baizhi_agent_toolkit | 12 | other | watch | 百智云 Agent Toolkit 为 AstrBot 提供托管的联网能力：网页搜索、网页正文读取、按字段或指令的信息提取。  本插件不自带任何抓取能力，也不复制服务端实现。它通过远程 MCP（Streamable HTTP）连接百智云托管服务，使用你自己的百智云 API Key，仅把工具调用转发过 |
| 2779 | astrbot_plugin_auto_intro | 12 | group-admin | have | 新增好友或机器人新加入群聊时调用当前会话默认 LLM 生成自我介绍，并为普通对话注入可配置的介绍规则、工具、插件和命令目录。 |
| 2780 | astrbot_plugin_systemone_keyreply | 12 | other | watch | 固定问答表驱动的自动关键词回复插件。消息先经本地正则召回，命中后由 TypeSafe AI 的 SystemOne 判定是否真提问，再回复标准答案。 |
| 2781 | astrbot_plugin_llm_monitor | 12 | other | watch | 记录 AstrBot 的 LLM 请求、模型负载、耗时、用量与 Agent 工具调用，并提供 WebUI 页面。 |
| 2782 | astrbot_plugin_quickpic | 12 | other | watch | 通过指令快速触发并发送本地指定文件夹下的同名图片，支持随时热替换与新增图片。 |
| 2783 | astrbot_plugin_notememory | 12 | memory | have | 三层便签记忆：短期上下文、关键词召回归档池和永久重要便签，支持自动总结、工具、指令与 Pages 管理。 |
| 2784 | astrbot_plugin_game_daily | 12 | game | have | 从公开 RSS/Atom 与 Steam 官方新闻接口采集最近 24 小时游戏资讯，去重、AI 摘要分类后使用 Pillow 生成本地中文新闻海报，并通过 AstrBot 定时推送。AI 不可用时自动回退规则模式。 |
| 2785 | astrbot_plugin_group_identity | 12 | other | watch | 在每次群聊 LLM 请求前，从 AstrBot 的平台消息历史中读取最近消息，按“昵称 (QQ:号码)”的格式注入最近群聊身份块。不改 AstrBot 核心文件，不替换原群聊上下文，只补充稳定身份信息。 |
| 2786 | astrbot_plugin_broadcast | 12 | other | watch | 向多个会话广播消息的 AstrBot 插件，带独立可视化配置台、定时任务、目标会话勾选与发送限速。 |
| 2787 | astrbot_plugin_game_torrent | 12 | game | have | 基于Astrbot开发的游戏种子搜索插件，支持 Aimhaven、Fitgirl、123资源库和 Gamer520，提供公开资源链接查询、源切换与二维码发送。 |
| 2788 | astrbot_plugin_snow_knowledge | 12 | kb-rag | have | 把她真实读过的书、查到的资料和论文沉淀成可检索知识库，聊天时按话题自动检索引用 |
| 2789 | astrbot_plugin_voice_input | 12 | media-parse | borrow | 在 LLM 请求前判断本轮用户消息是否来自语音，并把结论写入 `event.set_extra("voice_input", True/False)`。  默认只识别输入模态、不改变任何回复行为。打开 `voice_reply_probability` 后， 语音消息的回复会在投递前被换成语音（1. |
| 2790 | astrbot_plugin_snow_media | 12 | tts | watch | 群里发的视频文件会抽帧看画面并转写音频，语音消息会本地转写成文字再交给她理解 |
| 2791 | astrbot_plugin_link_context | 12 | media-parse | borrow | 群組分享連結時背景閱讀正文與圖片，將內容提供給 AI 對話，不自動轉發；影片僅讀標題、簡介與封面。 |
| 2792 | astrbot_plugin_external_command_manager | 12 | other | watch | 管理外部命令，避免非 AstrBot 插件注册的命令触发 AI 功能 |
| 2793 | astrbot_plugin_kb_threshold | 12 | kb-rag | have | 实现 AstrBot 新版知识库的自动检索注入，并支持相关度阈值过滤：相关度低于阈值的知识块不会注入 LLM 上下文。 |
| 2794 | astrbot_plugin_vtb_adapter | 11 | other | watch | 用于连接 AstrBot 与 Open LLM Vtuber，除安装插件外还需要修改 Open LLM Vtuber 中的相关文件 |
| 2795 | astrbot_plugin_typst_render | 11 | other | watch | 渲染 Typst 代码并返回图片 |
| 2796 | astrbot_plugin_a2s | 11 | other | watch | 这是 AstrBot 的A2S查询插件。 |
| 2797 | astrbot_plugin_wechat_manager | 11 | group-admin | have | [仅 gewechat] 微信关键字好友自动审核、关键字邀请进群 |
| 2798 | Astrbot_Plugin_HAOS_scwunai | 11 | other | watch | 这是简单的请求HAOSApi以获取HomeAssistant内注册的温湿度传感器数据的插件。输入/haoshelp获取帮助。请先根据帮助描述完成配置文件的配置填写后使用 |
| 2799 | astrbot_plugin_doc_reader | 11 | memory | have | 接收并解析 docx / xlsx / pptx / pdf 等文档，多文档持久记忆，直接聊天即可总结与问答，适配飞书(lark)等平台。 |
| 2800 | astrbot_plugin_github_copilot | 11 | info-push | have | 将 GitHub Copilot 作为大模型提供商接入 AstrBot，并提供订阅信息查询。 |
| 2801 | astrbot_plugin_dailycheckin | 11 | game | have | 群内每日签到打卡赚积分，支持连续签到加成、我的积分查询与群积分榜排行。 |
| 2802 | astrbot_plugin_active_reply_bot_fliter | 11 | sticker | borrow | 用于主动回复的机器人，支持双向关键词过滤（用户消息拦截 + 机器人回复静默），默认拦截图片/表情等媒体消息，并可通过自定义系统提示词让机器人判断是否保持沉默。 |
| 2803 | astrbot_plugin_qqbotfix | 11 | other | watch | 为 QQ 官方适配器提供 interaction 桥接、头像兼容、群被动键盘回复及可选频道私聊文本发送。 |
| 2804 | astrbot_plugin_komari_watch | 11 | platform | have | 基于 Komari 实时状态检测的 AstrBot 插件，支持 MJPEG 状态图、节点信息查询与 Webhook 告警通知 |
| 2805 | astrbot_plugin_mc_butler | 11 | other | watch | QQ群里的MC服务器大管家：绑定QQ和MC账号,远程执行服务器指令(支持 MCDR的!!指令),查看子服状态,可用自然语言执行,适合生电服在线管理！ |
| 2806 | astrbot_plugin_emotive_tts | 11 | tts | watch | 根据最近对话生成具体情绪转折指令，调用阿里云整段语音合成。默认1.12倍语速。 |
| 2807 | astrbot_plugin_mediawikitools | 11 | other | watch | 让LLM通过工具调用获取指定Mediawiki站点的API内容信息。 |
| 2808 | astrbot_plugin_kook_tts_welcome | 11 | group-admin | have | 成员进入 KOOK 语音频道时，机器人自动加入频道，按用户昵称实时合成（TTS）欢迎语音并播放，播放完成后离开。支持文案模板、指定用户定制文案与定制音频、进出与静音闭麦多状态播报、按服务器自动识别文字频道同步播报。 |
| 2809 | astrbot_plugin_subagent_router_guard | 11 | other | watch | 任务变复杂时，提醒主 Agent 把后续工作交给子 Agent，避免上下文被工具细节撑满。 |
| 2810 | astrbot_plugin_health_monitor | 11 | other | watch | 接收改装版 Gadgetbridge 手机端通过 HTTP 上传的健康数据（步数 / 心率 / 睡眠 / 电量）， 存入 SQLite。注册 LLM 工具支持自然语言查询（“现在心率多少”“今天走了多少步” “昨晚睡眠怎么样”），并在心率过高、电量过低时向绑定会话推送主动告警（支持多用户设备绑定）。 |
| 2811 | astrbot_plugin_feature_preview | 11 | other | watch | 读取已安装插件的名称与简介，在用户询问“你可以做什么”“你有什么功能”等触发词时回复功能清单。支持自动、白名单、黑名单三种展示策略，可过滤停用插件与内置插件、限制条数和简介长度，并可通过 /功能 指令手动查看。 |
| 2812 | astrbot_plugin_animerag | 11 | kb-rag | have | 基于 Bangumi 归档 + 部分萌娘百科的番剧/角色知识库。 支持番剧、角色、角色属性、单集、关系、评分与标签/时间筛选查询， 提供 search_anime / get_entity / get_translation / get_relations / get_worklist 五个函数工具 |
| 2813 | astrbot_plugin_longterm_memory | 11 | memory | have | 为 OneBot / QQ 官方机器人提供按用户隔离的长期记忆、用户画像、关键词检索、图片理解、每日整理与WebUI。 |
| 2814 | astrbot_plugin_todo | 11 | other | watch | 让 AI 把「接下来要办的事」整理成待办清单，并导入 Microsoft To Do 的指定列表。 |
| 2815 | astrbot_plugin_index_translate | 11 | media-parse | borrow | 基于 bilibili/Index-Translate 的免费公开 API（https://index-translate.bilibili.com/v1）， 免鉴权、无需 key，支持三档模型（35B-A3B / 9B / 2B）。  - 文本翻译：翻译 这句话 - 指定语言：翻译成日语 这句话  |
| 2816 | astrbot_plugin_github_star_chan | 11 | info-push | have | GitHub 星探酱 v1.5，支持高级搜索、项目详情、Trending 会话订阅和定时推送。 |
| 2817 | astrbot_plugin_repeat | 11 | kb-rag | have | 按群组+白名单隔离收集发言存入 Qdrant 向量库,支持语义附和、顺延接话与 WebUI 向量库管理。 |
| 2818 | astrbot_plugin_exact_match | 11 | other | watch | 精确匹配回复插件 - 完全匹配触发 |
| 2819 | astrbot_plugin_archive_reader | 11 | other | watch | 阅读压缩包内容。支持查看目录结构、AI分析用途、提取文件原文。群聊艾特+引用压缩包即可，私聊发送后等待提问。 |
| 2820 | astrbot_plugin_volcengine_native_video_provider | 11 | tts | watch | 火山方舟供应商（原生视频理解）。0.1.13 延续已验证的多模态实现并更新插件视觉标识：QQ Silk/AMR 语音会按真实内容识别并可靠归一化为标准 WAV，与完整聊天上下文进入当前火山方舟主模型；本轮发送或引用的视频通过 AstrBot 原生模型能力 modalities 中的 video 开关 |
| 2821 | hltv_rss | 11 | info-push | have | 订阅 HLTV RSS,推送全部 HLTV 资讯,LLM 中文翻译总结,封面图+标题+总结+时间 |
| 2822 | astrbot_plugin_dialocard | 11 | other | watch | 基于魔法少女的魔女裁判审判过程UI二改。用于LLM回复时生成粉色高亮的文字卡片。 |
| 2823 | astrbot_plugin_steinsgate | 11 | other | watch | 命运石之门主题插件，支持世界线辉光管图片、特殊世界线资料、年表查询与 D-QQ，可通过指令或 LLM 调用。 |
| 2824 | astrbot_plugin_codex_pulse | 11 | other | watch | 精美卡片追踪 Codex 直接重置、重置卡发放与预告，支持分类群通知、管理员测试卡片和文字回退。 |
| 2825 | astrbot_plugin_dreamweaver | 11 | other | watch | QQ AI 文字冒险，支持五种题材、自定义剧本、独立进度和存档。 |
| 2826 | astrbot_plugin_vts | 11 | sticker | borrow | 【公开测试版】功能会变、接口会变，也可能有尚未发现的 bug；更新前请备份 plugin_data。 反馈 / 意见 / bug：[作者公开联系方式已省略] 她自己的镜子：把 Live2D 模型接入 AstrBot，让她在屏幕上活着。 呼吸、微摆、不规则眨眼、视线跟随鼠标、说话时动嘴、被摸头 |
| 2827 | astrbot_plugin_timenote | 11 | personality | have | 精确到分钟的时间感知：临时上下文自动注入、工具执行后刷新、当前时间查询，保留主人格。 |
| 2828 | astrbot_plugin_bilicard | 11 | media-parse | borrow | B 站视频信息卡、可选 AI 音频总结与原生视频下载发送；支持时长限制、缓存清理和扫码登录。 |
| 2829 | astrbot_plugin_terminal_shell | 11 | other | watch | 在 AstrBot WebUI 中以一个页面提供完整运维面板：多标签终端、文件管理、设备状态函数图、自定义模糊背景、ECDH + AES-256-GCM 加密传输，以及 /终端 管理员指令与 LLM Shell 工具。 |
| 2830 | astrbot_plugin_auto_skills | 11 | other | watch | Reviews completed Agent turns and reminds the main agent to update workspace Skills via skill-creator. |
| 2831 | astrbot_plugin_esports_match | 11 | other | watch | 在 QQ 中通过 /瓦赛程 查询今天及未来两天的瓦罗兰特比赛和比分。 |
| 2832 | astrbot_plugin_wuwa_globlesever_tool | 11 | personality | have | 鸣潮国际服邮箱登录、多 UID 绑定、攻略站角色同步、纯本地档案、图片查询与 Dashboard 管理。 |
| 2833 | astrbot_plugin_SIGNALIS_save_decoder | 10 | other | watch | SIGNALIS存档解密工具，上传cargo.png可获取存档情况。 |
| 2834 | astrbot_plugin_zhuge | 10 | game | have | 诸葛神算 |
| 2835 | PGR_Dialogue | 10 | tts | watch | 检测到部分战双角色的名称(或别称)时，有概率发送一条语音文本 |
| 2836 | astrbot_plugin_usage_limiter | 10 | other | watch | # AstrBot 用户用量控制插件 (Usage Limiter)  基于 5 小时窗口与自然周的大语言模型（LLM）对话次数控制插件。 - 默认每 5 小时 30 次、每周 200 次，任一周期额度用尽即暂停请求。 - 用户可随时输入 `/usage` 查看两个周期的已用、剩余次数及重置时间。  |
| 2837 | astrbot_plugin_voicehub | 10 | tts | watch | 接收 VoiceHub 通知并推送到 QQ 官方机器人、OneBot v11、企业微信智能机器人、飞书、钉钉等适配器会话。 |
| 2838 | astrbot_plugin_calendar | 10 | platform | have | Apple Calendar 风格的日程日历面板 + 桌面右下角日程小窗 + 提醒卡片 + 自然语言增删查改日程，纯本地运行，内置农历/节气/休班角标数据。 |
| 2839 | astrbot_plugin_smm2 | 10 | game | have | 超级马力欧制造2关卡/玩家查询、随机抽图、bcd下载、关卡高清渲染。 |
| 2840 | astrbot_plugin_scp_cn_feed | 10 | other | watch | 推送 SCP 中文站首页的精品和竞赛活动，支持图片卡片与 QQ 官方 Markdown 按钮。 |
| 2841 | astrbot_plugin_task_skills | 10 | other | watch | 默认共享的结构化任务技能库，支持保守合并、版本回滚、原生发布和认证管理页面 |
| 2842 | astrbot_plugin_quick_decision | 10 | sticker | borrow | 用独立判断模型或按题随机决定发言时机、回复策略和表情包，支持树状判断、输出后判断、群聊插话、冷场主动回复与可编辑问题。 |
| 2843 | astrbot_plugin_furry | 10 | other | watch | 随机发送兽图，并以合并转发形式分页展示近期兽展（Furry Convention）列表。 展会卡片包含封面图、主办方 Logo、时间、地区与详情链接，每页 5 条，发送「下一页」可翻页。 |
| 2844 | astrbot_plugin_crossfeed | 10 | other | watch | 把指定人发来的私聊转一份给主人，让主人那边的会话也能看见。 |
| 2845 | astrbot_plugin_eggy_announce | 10 | game | have | 获取《蛋仔派对》游戏更新维护公告 |
| 2846 | astrbot_plugin_r6tracker | 10 | other | watch | 基于 R6Data API 的《彩虹六号：围攻》战绩查询插件：查询玩家战绩、生成精美图片报告、记录历史快照并对比上次查询的场次/胜率/KD/RP 变化。支持精简/详细两档报告与多类文字明细指令。 |
| 2847 | astrbot_plugin_AstrI | 10 | other | watch | 典 - 赤石科技😋💩 |
| 2848 | astrbot_plugin_wiki_render | 10 | other | watch | 通用 MediaWiki 查询渲染插件：发送 ~wiki <页面名> 获取页面内容并渲染为图片回复，支持本地/云端/私域网等多场景 MediaWiki 连接适配。 |
| 2849 | astrbot_plugin_thinking_time | 10 | other | watch | 在普通非流式聊天的最终文本回复首行显示本地深度思考用时，秒数向下取整，允许为 0。 |
| 2850 | astrbot_plugin_commandcode | 10 | other | watch | 将 CommandCode (commandcode.ai) CLI / Studio 账号转换为 AstrBot 可直接接入的本地 OpenAI 兼容网关，内置确定性 Windows 设备指纹上报、NDJSON 流式协议转译、72+ 模型目录与定价标签、多账号 402/429 自动轮换、主备模型按 |
| 2851 | astrbot_plugin_reasonix_subagents | 10 | personality | have | 把 DeepSeek-Reasonix 的 4 个内置只读子代理（explore / research / review / security-review） 以 "agent-as-tool"（FunctionTool + tool_loop_agent）方式迁移到 AstrBot。  - exp |
| 2852 | astrbot_plugin_flood_guard | 10 | group-admin | have | 在时间窗口内统计消息条数（默认任意消息，也可切换为「只统计同一条消息」）， 达到阈值自动禁言。 阈值、统计窗口、禁言时长与播报文案可在插件配置页设置， 也可由群主/群管理员在 QQ 群内通过 /flood 命令对单个群单独覆盖。 命令为英文，说明文档与群内回复为中文。 |
| 2853 | astrbot_baota_webhook_plugin | 10 | platform | have | 通过 Webhook 接收宝塔面板自定义消息通道的告警（title/msg/type），鉴权后推送到 AstrBot 指定的用户或群聊。 |
| 2854 | astrbot_plugin_bao_po | 10 | other | watch | 自我总结上下文并换房清理当前对话的 AstrBot 插件。 |
| 2855 | astrbot_plugin_listen_with_me | 10 | personality | have | 发送「陪我听会儿歌」开始陪听。插件会持续通过 Last.fm 检测你正在播放的歌曲， 换歌时结合最近的聊天记录自然地接一句话，而不是干巴巴地播报歌名。  你也可以随时问「我在听什么」「刚才那首叫什么」，它会实时查询后回答。 连续一段时间检测不到播放时自动结束，全程无需手动干预。  **特性**  - |
| 2856 | astrbot_plugin_qwen_multimodal | 10 | tts | watch | 基于阿里云百炼千问 TTS 与千问生图的高度拟人化多模态插件。支持 AI 阅读人设后自主挑选并锁定专属音色、根据情绪波动动态触发语音并调制语调语速、以及在对话中自然触发配图生成。模型不可用时会自动降级到账号可用的备选模型。 |
| 2857 | astrbot_plugin_wordle2 | 10 | other | watch | 将 Amiya-Bot 的 wordle2 干员竞猜玩法迁移为 AstrBot 独立插件，支持普通和硬核模式。 |
| 2858 | astrbot_plugin_output_audit | 10 | group-admin | have | 在 AstrBot 发送最终自然语言回复前执行本地硬规则和独立 AI 审核。 |
| 2859 | astrbot_plugin_repeat_roulette | 10 | other | watch | 复读越多越危险；复读被打断时，随机结算一发会逐步上膛的轮盘赌。 |
| 2860 | astrbot_plugin_lumielle_nexus | 10 | group-admin | have | 面向 QQ 群的跨会话任务编排插件，可在私聊中作为远程控制台，直接指挥群内的提醒、DDL、信息收集和原生消息投票。支持提醒/DDL/信息收集、checkpoint 语义分析、成员身份、消息归档、跨群转述与安全群管理。 |
| 2861 | astrbot_plugin_ragflow_workflow | 10 | kb-rag | have | 使用 RAGFlow 智能体增强 AstrBot 回复，保留 AstrBot 第二次 LLM 生成，并将长回答作为普通文本分段发送。 |
| 2862 | astrbot_plugin_luogu_problem | 10 | other | watch | 为 AstrBot 的 Bot 注册洛谷 LLM 工具（function calling）：Bot 可在对话中自行调用工具 爬取洛谷（luogu.com.cn）题目题面、题解（使用配置中的洛谷 Cookie 访问登录内容）， 并从洛谷保存站 luogu.me（api.luogu.me）或洛谷国际站（ |
| 2863 | astrbot_plugin_pindo | 10 | other | watch | 收图生成带色号与用量统计的拼豆图纸 PNG，支持 MARD/COCO/漫漫/盼盼/咪小窝/Hama/Perler/Artkal S 八套色板；内置 Pindo 网页版 WebUI。 |
| 2864 | astrbot_plugin_custom_help | 10 | other | watch | 基于 Typst 的手动发布菜单，支持完整导出、JSON 自定义显示隐藏、固定图片及可见菜单文本搜索 |
| 2865 | astrbot_plugin_skinsite_skin | 10 | tts | watch | 对接 LittleSkin 等 Blessing Skin 皮肤站（支持多站点并存），提供 /skin 命令： 搜索皮肤、发送 3D 预览图、单独发送可直接下载的皮肤文件（PNG）、随机公开皮肤。 同时注册 LLM 工具（skinsite_search / skinsite_sites / skin |
| 2866 | astrbot_plugin_wows | 10 | game | have | 基于 Hikari-core v2 / yuyuko API，支持总战绩、近期战绩、单船查询、账号绑定及自然语言查询，并以图片返回结果。需要自行配置 yuyuko API Token。 |
| 2867 | astrbot_plugin_obsidian_notes | 10 | memory | have | 让机器人把日记、笔记写进本机 Obsidian 仓库（日记按月归档、按天分小节），并能搜索和读取笔记来补充记忆 |
| 2868 | astrbot_plugin_chem_assistant | 10 | media-parse | borrow | 面向初三和高中的化学助教。核心能力与平台无关：化学式解析、摩尔质量、方程式配平、 物质的量与浓度计算都走确定性代码，不靠模型心算；知识卡按人教版章节索引，引用给到书名和章节； 遇到条件不足、数据矛盾或超纲内容会明确说明，不编造。危险化学品的制作、提纯、使用方法直接拒答。 |
| 2869 | astrbot_plugin_aigen | 10 | other | watch | 适用于Astrbot的多模态生成插件，包括生图、生视频、生音频和可配置自动路由 |
| 2870 | astrbot_plugin_hermes_core | 10 | memory | have | Hermes 风格学习闭环：持久记忆 + 全文检索 + 自动总结 + 技能沉淀，带可视化管理页面 |
| 2871 | astrbot_plugin_snow_sleep | 10 | proactive | watch | 小雪作息：按虚拟日程睡觉/起床，休息前和正在聊的人道晚安 |
| 2872 | astrbot_plugin_qq_antirecall | 10 | memory | have | 缓存群聊/私聊里的文本、图片、视频消息，消息被撤回时自动补发到原会话 |
| 2873 | astrbot_plugin_daily_digest | 10 | group-stats | borrow | 每天按设定时间推送「60 秒读懂世界」「AI HOT 热榜」「今日金价」「Epic 限免」， 支持官方原图、本地中文卡片与文字切换，也可随时手动查询。支持多时间、多板块开关， 推送目标既可以由群/私聊自助订阅，也可以在插件配置里手动指定。 |
| 2874 | astrbot_plugin_voice_intent | 10 | tts | watch | 随口一句「用语音跟我说」「念给我听」「别打字了」就开口，不用记指令也不用指定工具；也能 /开口 发 <内容> 直接手动念一句。插件判断这一轮想不想听语音，命中就把回复换成一条语音，没命中一个字都不动；不注册 LLM 工具、不会有「工具没接上」，也不另起 TTS 引擎，直接复用 AstrBot 已配好 |
| 2875 | astrbot_plugin_laizhi | 10 | group-admin | have | 收集群友逆天素材，按 tag 归档，随机发送并支持自动撤回及 WebUI 管理 |
| 2876 | astrbot_plugin_moemeter | 10 | other | watch | 猫猫指数判定器，支持文字版 /moedex 和图像版 /moedex_img，带缓存和安全过滤。 |
| 2877 | astrbot_plugin_ping | 10 | other | watch | 为 AstrBot 提供网络 Ping 测速能力。 - 三级探测兜底：系统 ICMP Ping → 纯 Python ICMP → TCP 端口探测。 - 内置 `/ping setup` 指令，可自动在 Docker 等缺少 ping 命令的环境中安装 iputils-ping。 - 支持自定义  |
| 2878 | astrbot_plugin_vrcfriends | 10 | info-push | have | 每个 QQ 独立加密登录 VRChat，查看好友和房间、收藏优先、订阅上线提醒，支持白底毛玻璃卡片与分页。 |
| 2879 | astrbot_plugin_vrchat_status_monitor | 10 | other | watch | 定期拉取 status.vrchat.com 官方状态页，检测整体状态、组件、事件与维护的变化，推送到绑定会话。 |
| 2880 | astrbot_plugin_link_preview | 10 | other | watch | 群成员 @机器人 发送链接，机器人将其展开为预览卡片图回复。当前支持 GitHub 仓库与 B 站视频（含 b23.tv 短链）。 |
| 2881 | astrbot_plugin_group_raffle | 10 | other | watch | 分群独立配置的群聊抽奖：手动/定时开奖、活跃度加权、报名参与、多等次多名额、防连中、@中奖者、自定义模板、卡片渲染、可视化管理面板。 |
| 2882 | astrbot_plugin_interconnect | 10 | platform | have | 在 QQ Bot 与本地 HTTP 服务之间进行轻量级双向消息互联。 |
| 2883 | astrbot_plugin_codex_reset | 10 | other | watch | 只读请求 codex-reset.com 的时间线和预测。 已宣布的 reset，或 forecast 的 last_reset_at 向前移动，才推送到已开启的群。 概率升高不算重置。 开哪些群在插件页面增删改查，不使用群口令。 展示面署 Data: codex-reset.com。 |
| 2884 | astrbot_plugin_alipay_website | 10 | payment | exclude | 为 AstrBot Agent 提供创建与核验支付宝人民币网页订单的工具。 |
| 2885 | astrbot_plugin_tronclass | 10 | devtools | watch | 为 AstrBot 开发的CUC畅课信息展示插件。 支持多用户独立绑定畅课账号， 自动查询作业列表、检测新作业发布、 作业截止提醒，以及课表驱动的点名实时通知。 |
| 2886 | astrbot_plugin_onesync | 9 | other | watch | 通用可扩展的软件更新器插件，支持定时检查、自动更新、镜像回退与状态追踪。 |
| 2887 | astrbot_plugin_vangonography | 9 | other | watch | 一个通过图片隐写术来隐藏和提取文件的插件 |
| 2888 | astrbot_plugin_image_size_limit | 9 | other | watch | 限制图片尺寸 |
| 2889 | astrbot_plugin_eat_history | 9 | other | watch | 自动保存转发的消息记录，随时查看 |
| 2890 | astrbot_plugin_alistfile | 9 | other | watch | 支持对 alist 的下载和上传（仅支持图上传） |
| 2891 | astrbot_plugin_rmts | 9 | memory | have | 为明日方舟「迷迭香」准备的工具箱，附带依据官方资料编写的人格，启动时自动创建和更新。 她记得每位博士说过的事，按来源控制谁能看到，每晚写日记并整理记忆； 群里被叫到时会读最近的群聊，回复时引用并 @ 对方，没人叫她时也会自己决定要不要插话； 工具：干员生日 / 档案、高德天气、DeepSeek 网页 |
| 2892 | astrbot_plugin_truth_dare | 9 | game | have | QQ 群随机选人插件：报名、两幕动画选人（3D 菱形滚轮选回答者 + 昵称首字横盘选提问者）、真艾特点名，支持连中降权、多群隔离、深浅双主题、历史统计页与群内查询指令。 |
| 2893 | astrbot_plugin_dota2forge | 9 | other | watch | 查刀塔战绩、比赛详情和英雄热门出装，查看段位与预估分数。首次安装需按说明准备运行组件。 |
| 2894 | qq_face | 9 | sticker | borrow | 为 OneBot QQ 协议端提供入站表情理解、内联标记发送、动态目录和动态贴纸拆条。 |
| 2895 | astrbot_plugin_chaoxing_ddl | 9 | other | watch | 学习通（超星）作业 / DDL 提醒插件。  功能： - 自动登录学习通，定时抓取所有课程的未交作业与截止时间（无时间限制作业也会列出） - 进入自定义提醒窗口（如剩最后 2 天）后主动推送提醒，每条只推一次，重启不重复 - 每日固定时刻推送「未交作业一览」（可选，可关闭） - 零配置可用：账号可直 |
| 2896 | astrbot_plugin_courier | 9 | proactive | watch | 注册 LLM 工具，让机器人可以向同一个机器人接入的不同会话投递主动消息。自动记录会话并支持友好命名，不同机器人接入互相隔离，跨会话投递默认仅限管理员。 |
| 2897 | astrbot_plugin_ts3_server_guard | 9 | tts | watch | [AI 修改版] 基于 astrbot_plugin_tsserver_relay (GEMILUXVII) 的 TeamSpeak 3 多服务器监控插件：仿 minecraft_multi_monitor 架构、上下线滞回判定、防僵尸任务、UMO 动态推送目标；上下线/监控启动/用户进出通知开关； |
| 2898 | astrbot_plugin_cross_platform_share | 9 | other | watch | 在后台配置 A→B 的完整 UMO 映射，保存后立即复制 A 的全部对话和平台消息历史。 每个 B 都会获得独立的 conversation_id，保留 B 原有对话，复制完成后 A 与 B 不再互相同步。 |
| 2899 | astrbot_plugin_pighub | 9 | other | watch | 发送「/随机猪猪」或别名「/sjzz」随机回复一张 pighub.top 的猪猪图片；「/随机猪猪 关键词」按关键词筛选；管理员可用「/sjzz 关键词 数量」一次回 1~10 张；群聊每人每天限 10 次；支持群聊黑白名单与管理员（免冷却免上限） |
| 2900 | astrbot_plugin_group_repeater | 9 | other | watch | 连续 N 个不同人发相同内容时跟一次；复读后本次复读事件结束；不限时间间隔，只要内容连续就计数。 |
| 2901 | astrbot_plugin_anime_birthday | 9 | personality | have | 本地缓存动漫与游戏角色生日，按 Galgame、游戏、番剧订阅每日推送 |
| 2902 | astrbot_plugin_gpt_image_studio | 9 | image-gen | watch | 管理员在群内调用 codex/gpt-image-2 生图与改图：引用群聊图片作为参考（支持一条消息内多张、引用消息内多张一起识别），发送提示词即可图生图、局部改图、换画风、多图融合；也可纯文生图。新增多模态修图诊断：看图输出文字版 Photoshop / Camera Raw 参数建议，不生图不改 |
| 2903 | astrbot_plugin_esports_score | 9 | other | watch | 通过 PandaScore 查询 CS2、英雄联盟、无畏契约、Dota 2 的比分赛程、战队阵容和赛事信息，供 LLM 调用 |
| 2904 | astrbot_plugin_reminder | 9 | proactive | watch | 给主模型一个提醒入口（remind_me）。  - 「半小时后提醒我喝水」「20 分钟后叫我」→ 按分钟排 - 「晚上 8 点来找我」「中午来找我」「明天早上 7 点」→ 模型换算成具体时间 - 「等我吃完饭再聊」这类没给时间的 → 默认 30 分钟后回来找他 - 到点不是念闹钟，而是把主 agen |
| 2905 | astrbot_plugin_life_assistant | 9 | other | watch | 生活小助手：主动式任务提醒插件。支持任务创建（主题/备注/开始结束时间）、进行中提醒（周期/截止前/定点）、结束总结与「再来一次」快捷重启、历史任务管理，内置生理健康模板（卫生巾、棉条更换提醒）。 |
| 2906 | astrbot_plugin_group_context_image_locator | 9 | other | watch | 让你的 AI 为 AstrBot 原生群聊感知中的图片保留提取码，需要时再取回、查看或按原图转发，不另建聊天历史。 |
| 2907 | astrbot_plugin_osuv2 | 9 | other | watch | 通过 NapCat/OneBot 在 QQ 查询 osu! 玩家、最近成绩、BP、今日记录和谱面。 |
| 2908 | astrbot_plugin_semantic_fallback | 9 | other | watch | 当主模型的拒答文本被当成正常文本发送时（常见于反代场景），将其识别为语义失败， 并交给 AstrBot 原有的备用模型切换流程处理。 主模型、备用模型、会话上下文和 prompt 均沿用 AstrBot 当前配置。 |
| 2909 | astrbot_plugin_law_assistant | 9 | other | watch | 法律信息助手核心产品，提供法律硕士活动扫描、时间线抽取、官方案例与法规更新存储、核验真题导入、模拟题学习、DDL 提醒、每日计划和可确认多群发布；部分来源和 LLM 能力依配置启用。 |
| 2910 | astrbot_plugin_gaokao | 9 | group-admin | have | 每日定时向指定群聊发送高考倒计时和励志一言。 一言来源支持本地句库（内置 156 句高考励志语录，可在配置中追加）与 UAPIPro 接口二选一； UAPIPro 支持基础一言与随机/每日/场景/此刻接口、来源/分类/标签过滤、可选 API Key。 支持按群独立配置（template_list 分 |
| 2911 | astrbot_plugin_lively_gate | 9 | sticker | borrow | 門禁和公共設定：只放行指定 QQ 群、群聊/私聊分別用不同模型、喊名字當 @、表情包識別、攔截洩漏的內部標記 |
| 2912 | astrbot_plugin_quick_commands | 9 | other | watch | 提供 AstrBot WebUI 扩展页面，可创建、编辑、停用和删除快捷指令，支持多别名、固定文本与 TXT 导入、可选免斜杠触发及管理员权限。 |
| 2913 | astrbot_plugin_wanmei_dorm_power | 9 | proactive | watch | 通过完美校园云支付缴费接口查询宿舍剩余电量并定时提醒。配置页粘贴缴费链接即可自动解析学校参数，支持搜房绑定、定时播报、低电量预警。 |
| 2914 | astrbot_plugin_persona_workshop | 9 | memory | have | 用 AstrBot 模型或本地 CLI 制作人格，保留 continuum 的资料研究、八维提取、审阅与编译；使用人格时以隐藏 Room 动态注入情绪、需求、关系和记忆，并支持 LivingMemory、人格工具与可选静默会诊。 |
| 2915 | astrbot_plugin_eat_what_easy | 9 | other | watch | 一个简单的关键词回复插件，随机回复「今天吃什么 / 喝什么」的菜品、饮品图片。 |
| 2916 | astrbot_plugin_sts2_player | 9 | game | have | 让 AI 玩《杀戮尖塔 2》：通过游戏 mod 的本地 HTTP 接口读取引擎真值，规则机器人负责战斗与卡组构筑（选牌/升级/删牌），可选让 LLM 决策选牌/事件/路线，也能让模型按回合给整串出牌计划。支持 STS2-Agent 与 STS2_MCP 两种后端。 |
| 2917 | astrbot_plugin_steamhub | 9 | other | watch | 用自己的 Steam API Key 一次性导入全部好友，给每个好友分配固定序号；之后按「/steam 绑定 |
| 2918 | astrbot_plugin_beijing_fushengji | 9 | game | have | 2001 年经典单机游戏《北京浮生记》的群聊版：背着高利贷进京，40 天里低买高卖攒身家。发指令就能玩，最多 4 人一局，买卖互相影响行情，每天战况自动生成一张报纸风格的图。 |
| 2919 | astrbot_plugin_rngdle | 9 | other | watch | 通过 rngdle.com 抽取每日随机数字，并返回结果。 |
| 2920 | better_help | 9 | other | watch | 纯文字帮助菜单插件，支持分类管理和 YAML 自定义菜单项，告别图片式 /help |
| 2921 | astrbot_plugin_kook_manager | 9 | group-admin | have | 在 AstrBot WebUI 中管理 KOOK 机器人消息的管理面板。  **功能** - 查看机器人已加入的服务器与文字频道，切换频道查看机器人发送的消息 - 关键词搜索与「仅图片」过滤，最新消息在底部并自动滚动 - 消息多选、全选/清空选择，一键批量撤回选中的机器人消息 - 手动覆盖 KOOK |
| 2922 | astrbot_plugin_rocket_chat_adapter | 8 | other | watch | AstrBot 的 Rocket.Chat 消息平台适配器，支持通过 WebSocket 实时接收消息，通过 REST API 发送消息 |
| 2923 | astrbot_plugin_nnnu_wm_electricity | 8 | other | watch | 提醒电费还够不够、有人充了电费等功能 |
| 2924 | astrbot_plugin_cxzl | 8 | other | watch | 查询指定指令来源的插件（/cx 指令） |
| 2925 | Error Monitor | 8 | platform | have | 捕获 Immersive Error 抛出的异常，并提供 SMTP 邮件通知进行报告。 |
| 2926 | astrbot_plugin_bo | 8 | game | have | 这是我们童年玩的波波集游戏bo_game,你将与传说中的最强ai小学生对战 |
| 2927 | pkg | 8 | other | watch | 按名称搜索 Arch Linux 官方仓库和 AUR 中的软件包。 |
| 2928 | astrbot_plugin_membercontrast | 8 | other | watch | [仅 Gewechat] 实现微信历史群组群员与当前群员对比的功能 |
| 2929 | astrbot_plugin_english | 8 | other | watch | A proto of learning English on Astrbot. |
| 2930 | astrbot_plugin_teamspeak6_tracker | 8 | other | watch | 拥有 TeamSpeak 6 在线状态查询、频道成员展示、上下线通知的功能。 |
| 2931 | astrbot_plugin_modelscope_daily | 8 | game | have | 魔搭社区（ModelScope）多账号每日签到：每天 06:00 自动签到，并把汇总结果推送到指定会话 |
| 2932 | astrbot_plugin_eternalreturn_helper | 8 | personality | have | 纯 AI 制作的永恒轮回查询插件：玩家战绩、实验体、皮肤、历史对局、角色数据、段位分布、分数线与装备查询，支持 DAK.GG 官网截图与卡片。数据来自 DAK.GG；功能设计参考并致谢 LuoRenMu/EternalReturnLoMu；如涉及侵权请联系 QQ 邮箱 3033980089@qq.c |
| 2933 | astrbot_plugin_ds_status | 8 | info-push | have | 订阅 DeepSeek 状态页 RSS 与邮箱通知，状态一变就推送一张图片卡片，支持事件级去重、多会话订阅、关键词过滤与命令权限控制 |
| 2934 | astrbot_plugin_telegraph_longtext | 8 | other | watch | 自动将超过指定字数的 AstrBot 回复发布为 Telegraph 页面，并在聊天中发送链接。 |
| 2935 | astrbot_plugin_suosuo | 8 | other | watch | 群互动插件：@群友「嗦」TA 的蹄子，附带对方头像与被嗦次数； 「嗦蹄战绩」查自己或别人的战绩（带趣味评价与称号）。 战绩按群隔离，v1.0 的老存档只读继承。 |
| 2936 | astrbot_plugin_minekuai | 8 | other | watch | AstrBot 麦块插件：支持 Minecraft 资源搜索、版本与下载链接查询，聚合Modrinth 模组，CurseForge 模组，Modrinth 光影包，Modrinth 资源包，Modrinth 插件，CurseForge 插件，SpigotMC 插件，Modrinth 整合包，Curs |
| 2937 | astrbot_plugin_mjdhs | 8 | game | have | Astrbot雀魂赛事管理插件：绑定赛事、查询名单/大厅/待机/规则/公告/排名、添加/删除选手、开赛、暂停/恢复/终止对局。 |
| 2938 | astrbot_plugin_tiancai | 8 | other | watch | 本地收藏与公共源混合抽取。默认启用公共菜单，支持代理拉取。 公共视频可自动导入本地库。管理台可改配置/指令，并可发布到你自己的 GitHub 仓库。 新增「公共库」栏：浏览/编辑/删除/下载到本地（需 Token + github_repo）。 |
| 2939 | astrbot_plugin_arcaea_pull | 8 | other | watch | Arcaea 中国大陆版 APK 可信下载、真实性验证与 QQ 闪传分发 |
| 2940 | astrbot_plugin_onebot_bridge | 8 | other | watch | 主副Bot桥接插件，支持将消息转发到支持OneBot v11协议的副Bot |
| 2941 | astrbot_plugin_wechat_toolkit | 8 | tts | watch | 个人微信的用量查询、官方资费同步、生图改图、按需语音与链路诊断工具箱。 |
| 2942 | Astrbot_plugin_kook_bilimusic | 8 | media-parse | borrow | 独立 KOOK 语音频道 B 站点歌插件：搜索 B 站、机器人进入点歌人所在语音频道播放，支持选歌卡片、队列、进度和切歌。 |
| 2943 | astrbot_plugin_better_balance | 8 | tts | watch | 每日聊天配额、余额查询与点歌额度联动管理插件 |
| 2944 | astrbot_plugin_chess | 8 | game | have | 在你自己的设备上开一个轻量网页，用图形棋盘和 AI 对弈；每一步都回流到 AstrBot 的会话里，由大模型接管对话与应手。  特点： - 棋盘规则由 python-chess 维护，插件本身不实现任何棋规 - 六套棋盘配色、三种棋子样式，随手切换，选择记在浏览器里 - 网页适配手机横屏，可当输入法 |
| 2945 | astrbot_plugin_autobangumi_notify | 8 | personality | have | 接收 AutoBangumi 的 Webhook 通知，通过 LLM 以 AstrBot 自身人格转述后推送到指定会话（好友/群聊）。支持 6 种事件类型识别、多目标推送、多平台兼容、内容去重和发送重试。 |
| 2946 | astrbot_plugin_wake_chatter | 8 | other | watch | 通过唤醒词唤醒机器人加入 QQ 群聊讨论。唤醒后会在可调时长内（默认 5 分钟）以一定概率自主插话，活跃期内重复唤醒会刷新倒计时；回复条数、唤醒时长、概率等均可在 WebUI 后台配置。 |
| 2947 | astrbot_plugin_wevote | 8 | other | watch | QQ 群聊投票，支持发起权限、单选多选、改票、公开或保密结果及到期结算。 |
| 2948 | astrbot_plugin_minimax_tts | 8 | tts | watch | AI 自主选择 MiniMax 语音回复，支持情绪与语气标签，并在后台按群和私聊用户管理。 |
| 2949 | astrbot_plugin_bilibili_live_chat | 8 | media-parse | borrow | 多直播间弹幕与音视频识别，支持语音唤醒、网页扫码和 BiliBot 联动。 |
| 2950 | astrbot_plugin_smm2_en | 8 | image-gen | watch | Super Mario Maker 2 level/player query, random draw, bcd download, HD level rendering. |
| 2951 | astrbot_plugin_fns_ddns | 8 | media-parse | borrow | 从 API 查询IP调整域名解析 |
| 2952 | astrbot_plugin_vrc_tool | 8 | group-admin | have | 查询 VRChat 玩家/地图信息，并支持玩家群入群审核 |
| 2953 | astrbot_plugin_datacheck | 8 | other | watch | 查询 AstrBot 近 N 小时内的错误日志，通过合并转发发送。支持指令和 LLM 意图识别触发。 |
| 2954 | astrbot_plugin_anti_flood | 8 | group-admin | have | 支持自动或手动将 QQ 群消息整理为合并转发并按需撤回。 |
| 2955 | astrbot_plugin_wordle_3 | 8 | other | watch | 在群聊或私聊中通过 /wordle 开始 Wordle 猜单词，并以经典 Wordle 风格图片回复。 |
| 2956 | astrbot_plugin_moewalls | 8 | other | watch | 从 moewalls.com 搜索动态壁纸（Live Wallpaper）。  ## 功能说明 - 🔍 发送 /搜壁纸 关键词，自动把中文关键词翻译成英文后到 moewalls.com 搜索 - 🖼️ 返回带序号的壁纸预览图（每张图对应一个搜索结果） - ⬇️ 回复 /序号（例如 /1）即可下载对应 |
| 2957 | astrbot_plugin_dreamweaver | 8 | other | watch | QQ AI 文字冒险，支持五种题材、自定义剧本、独立进度和存档。 |
| 2958 | astrbot_plugin_manual_compress | 8 | other | watch | 手动触发当前会话的上下文压缩，使用 LLM 将历史对话浓缩为摘要 |
| 2959 | astrbot_plugin_hdc | 8 | other | watch | 让 AI 通过 hdc 操作一台 HarmonyOS 设备。默认用 uitest dumpLayout 把当前界面读成 文本控件树（控件类型 + 文字 + 坐标），模型据此决定点击位置，纯文本模型也能用； 遇到自绘界面（视频流、图片墙）时用 hdc_see 把画面交给视觉模型兜底。 手势覆盖点击、长 |
| 2960 | astrbot_plugin_recall_forward | 8 | memory | have | 在选定的群里旁路缓存消息，有人撤回时把原文和图片转发到指定 QQ 群或私聊；支持实时转发和每天合并转发日报，缓存窗口默认 24 小时，管理员晚撤回也能补原文。 |
| 2961 | couple_ai | 8 | personality | have | 为情侣/多会话场景提供跨房间任务、共享事件流与每日日记：一个会话里可以让 另一个会话在指定时间收到一条话，并让目标会话用自己的人格生成；每次发言 会进入共享事件环，其他会话按会话水印看到「我最近在别处做了什么」。自带 WebUI 管理任务、事件和日记。 |
| 2962 | astrbot_plugin_empty_at_reply | 8 | other | watch | 单独 @ 机器人（不带任何内容）时让机器人也正常回复。  修复 qq_official（QQ 官方机器人）等平台上空 @ 无响应的问题。 |
| 2963 | astrbot_plugin_message_card | 8 | other | watch | 将 AstrBot 的 LLM 回复或指定内容渲染为图片卡片。支持 Markdown、HTML、LaTeX （原生 MathML）、消息链图片与网络图片；按 IANA 时区和日间区间自动切换昼夜主题； 页眉和页脚可使用本地图片、固定 URL 或横屏图片 API，并对 Docker 访问宿主机做回退。 |
| 2964 | agnes_ai | 8 | other | watch | Agnes 图片与视频生成，支持中文简短指令、Agent自然语言工具调用和首尾帧控制 |
| 2965 | astrbot_plugin_modelscope | 8 | image-gen | watch | 调用魔搭社区(ModelScope) API-Inference 进行文生图和图编辑。支持触发词指令、可开关的自然语言 LLM 工具调用、按模型 ID 指定文生图与图生图默认模型，以及多模型和自定义预设工作流。 |
| 2966 | astrbot_plugin_snow_reply | 8 | other | watch | 由她自己判断何时需要引用回复，并在前文里搜索目标消息；只在话题混乱或目标很远时触发，有冷却和频率上限 |
| 2967 | astrbot_plugin_savepoint | 8 | other | watch | 手动存入当前节点重要的图文信息，支持多TAG组装与单存档槽切换的轻量上下文挂件 |
| 2968 | astrbot_plugin_genzon_mikuji | 8 | personality | have | 发 /抽签 即可抽一支东方角色签。支持六面骰、八面骰、七枚硬币和今日签，可按角色查签、查原书页码、核对手里的骰点。抽签全程在本地完成。 |
| 2969 | astrbot-plugin-hypixelskyblock-api | 8 | devtools | watch | 整个 sb-* 插件套件的**唯一 Hypixel/Mojang API 调用入口**。 拉取 Hypixel v2 API → 归一化为结构化 dict → 落盘到跨插件共享 SQLite。 给 sb-dungeons / sb-slayer 等上层"查询/卡片"插件共用，避免每个查询插件 各自打 |
| 2970 | astrbot_plugin_sub_aggregator | 8 | tts | watch | 按内容识别并聚合远程、本地和上传的订阅，输出 Mihomo/Clash YAML、sing-box JSON 和纯分享链接 Node List。 |
| 2971 | astrbot_plugin_dev_helper | 8 | devtools | watch | 管理员开发与排障工具集，支持命令与模型工具的查询，日志、会话记录、上下文用量的查询与图片渲染，支持程序重启与终端执行。 |
| 2972 | astrbot_plugin_osu_profile_card | 8 | other | watch | 使用 osu! API v2，通过 /osu 输出四模式汇总资料卡。 |
| 2973 | astrbot_plugin_personagent | 8 | memory | have | 把 [personagent](https://github.com/wangkant/personagent) 的角色接进 AstrBot 的每个平台：它只在被叫到、或判断真人会接话时开口； 别人纠正它、它的第二次回答被接受后，才把更好的说法记下来，一个捣乱的人教不坏它；每个群的记忆分开，学到的东 |
| 2974 | astrbot_plugin_codex_radar_info | 8 | other | watch | 获取 Codex Radar 每日模型智力效率、社区体感与雷达报告。 |
| 2975 | astrbot_plugin_scheduled_sender | 8 | other | watch | 定时向会话发送预设文本消息, 支持多条消息轮换发送与每日/星期/间隔/cron 重复。 |
| 2976 | astrbot_plugin_help_image | 8 | other | watch | 接收 help 指令后发送自定义帮助图片。 |
| 2977 | astrbot_plugin_forcejoin | 8 | other | watch | 新成员须在限定时间内加入任意一个目标群，并可自动清理已退出所有生效群的目标群成员 |
| 2978 | astrbot_plugin_steam_skin_ops | 8 | other | watch | 在 AstrBot 内查询 Steam 饰品行情，提供确定性 Top 5 推荐、T+7 概率预测与风险评估，并支持挂刀、清仓等按会话监控告警。 |
| 2979 | astrbot_plugin_splatoon3 | 7 | game | have | 查询Splatoon3游戏数据，包括地图轮换、鲑鱼跑、挑战、祭典、装备商店等信息 |
| 2980 | astrbot_plugin_wca | 7 | other | watch | 包含WCA查询、one查询、跨平台PR、宿敌、近期赛事和成绩对比。 |
| 2981 | astrbot_plugin_slg | 7 | game | have | 用astrbot玩slg |
| 2982 | astrbot_plugin_furry_cgsjk | 7 | other | watch | 小茶馆数据库插件，为小茶馆插件提供数据支持 |
| 2983 | astrbot_plugin_78animesearch | 7 | other | watch | 通过 `/78dm [关键词]` 命令在 78动漫模型网搜索模玩信息 |
| 2984 | seiadetect | 7 | other | watch | [仅 napcat] 使用Onnx检测发送的图片是否包含_百合园圣娅_并且有特定回复。 |
| 2985 | xyzw_ocr | 7 | other | watch | [仅gewechat]主要用于咸鱼之王OCR识别算鱼罐子宝箱功能 |
| 2986 | astrbot_plugin_nanally | 7 | personality | have | 基于NTEUID和TaJiDuo制作出的异环查询角色 |
| 2987 | astrbot_plugin_user_prompts | 7 | other | watch | 每位用户发送 /prompt 后，再单独发送一条消息设置个人提示词。 支持多行文本、查看和清除，并拦截设置消息的 AI 回复。 提示词仅用于该用户在当前对话中的 AI 请求，开启新会话后不继承。 支持管理面板白名单开关、用户列表、字数限制开关与最大字数配置。 |
| 2988 | astrbot_plugin_otoge_prober | 7 | game | have | 舞萌 DX / 中二节奏 / 音击 / SOUND VOLTEX 的 QQ 查分插件（NapCat）。舞萌、中二支持国际服、日服、国服（落雪 / 水鱼）和私服（AquaDX / RinNET），音击支持官服和私服，出带曲绘的 B50 图；SDVX 和音击可以在手机网页上手动传分，出 VOLFORCE |
| 2989 | astrbot_plugin_codex_reset | 7 | group-stats | borrow | 监控 Codex、Claude、Grok 和 Gemini 的公开额度重置，按产品向订阅的 QQ 群推送预警与确认，支持精简日报。 |
| 2990 | astrbot_plugin_bilirec_rooms | 7 | media-parse | borrow | 可以通过聊天控制服务器上运行的b站录播姬，包括重启录播姬、查询录制状态、新增删除直播间等 |
| 2991 | astrbot_plugin_csgo_match | 7 | info-push | have | CS2/CSGO 赛事查询、队伍/赛事订阅与自动推送。赛程、比分、逐图 5v5 数据、战队支持率、VRS 积分、热评，多数据源自动回退，无需 API Key。 |
| 2992 | astrbot_plugin_miyoqian | 7 | personality | have | 米游社游戏每日签到（原神/星穹铁道/崩坏3/绝区零/崩坏2/未定事件簿）。支持 Cookie 绑定与扫码登录、多账号、多角色签到、每日自动签到、签到状态查询；原神/绝区零采用新版签到 API（x-rpc-signgame + act.mihoyo.com）。 |
| 2993 | astrbot_plugin_github_daily | 7 | other | watch | 检测指定 GitHub 账户近期公开贡献，帮助群聊判断是在写代码还是摸鱼。 |
| 2994 | astrbot_plugin_link_collector | 7 | media-parse | borrow | 识别 GitHub、B站、YouTube、微信公众号和普通网页链接（含 QQ 分享卡片），抓取内容后用指定模型生成一句话简介、要点、分类和标签， 写入 Notion 收藏夹数据库并回执。默认用「/收藏」指令触发，也可切换为私聊自动收藏；只响应白名单用户。 |
| 2995 | astrbot_plugin_asteria | 7 | memory | have | 为 AstrBot 提供角色持续状态、长期记忆、虚拟身体、场景互动、日程提醒与感知接入， 可搭配 Asteria Chat 在 Android 上聊天，并通过原生管理页面维护角色与资料。 |
| 2996 | astrbot_plugin_moon_workshop | 7 | other | watch | 给 AI 一双只在自己地盘上动手的手：受限读写、自动备份、语法检查与回滚，所有改动都进账本。  ⚠️ **推荐与「溟汐的考核」(astrbot_plugin_moon_gate) 一起安装**： 单独安装时读写、备份、沙箱都能用，但没有积分与提权，AI 无法凭劳动换取更高权限。 考核地址：https |
| 2997 | astrbot_plugin_horserace | 7 | game | have | 多人赛马小游戏，支持随机事件、状态效果、自定义事件包和异步赛况播报。 |
| 2998 | astrbot_plugin_wxauto_bridge | 7 | tts | watch | 把桌面微信接进 AstrBot，监听私聊和群聊，支持文字、图片、文件与语音条 |
| 2999 | astrbot_plugin_vtuber_monitor | 7 | info-push | have | 订阅直播通知、扫码登录、主播别名、周表图片与定时更新、自动调播、未兑现标记。（当前只针对VirtuaReal团体进行过测试，正在debug以及加入更多后续功能。。。） |
| 3000 | astrbot_plugin_bracket_filter | 7 | other | watch | 自动过滤 Bot 输出消息中的【】和『』符号 |
| 3001 | paika | 7 | sticker | borrow | 面向 OneBot v11 / NapCat 的 QQ 群聊排卡插件。支持自定义房间标题、 多房间并行、同群一人一房、斜杠指令、回复消息上下车和 LLM 工具。 支持 NapCat 表情回应上下车、满员自动发车、发车后成员锁定、 房主结束房间、定时提醒和超时结束，状态通知使用 At 列出成员。 |
| 3002 | astrbot_plugin_astrcontinuum | 7 | other | watch | Non-blocking durable long-context runtime for AstrBot / AstrBot 非阻塞、持久化长上下文运行时。 |
| 3003 | astrbot_plugin_rokid_bridge | 7 | memory | have | 提供眼镜六码配对、设备管理、逐段回复显示、管理员权限、页面内 HUD 提示与拍照识图工具。 眼镜消息由 AstrBot 正常处理，可使用部署者已有的模型、人格、记忆和工具。 |
| 3004 | astrbot_plugin_hot_market | 7 | info-push | have | 将多个平台热搜分别变成可买卖的虚拟股市，支持行情图、热搜资讯、主动离榜预警、持仓和群排行。 |
| 3005 | astrbot_plugin_group_monitor | 7 | group-admin | have | 监控新进群成员，若未在目标关联群则执行禁言或踢出惩罚，支持自定义规则别名、天/小时/分钟时间单位，群主/管理员权限，入群自动@提醒，加入目标群自动解禁 |
| 3006 | astrbot_plugin_github_ops | 7 | other | watch | 主对话只挂 github_ops。建仓、提交、issue、fork、PR 走 REST 子循环， 不把官方 GitHub MCP 灌进上下文。 |
| 3007 | astrbot_plugin_autobangumi_command | 7 | info-push | have | 在 QQ/Telegram/微信等平台通过聊天命令远程操控 AutoBangumi，支持搜索番剧、添加 RSS 订阅、查看订阅列表、删除订阅等功能。 |
| 3008 | astrbot_plugin_zcodium | 7 | other | watch | 把消息转发给 ZCodium agent 并流式回复；AstrBot 仅作传输层，不走自带 LLM。 |
| 3009 | astrbot_plugin_snow_profile | 7 | other | watch | 为每个聊天对象维护第一人称印象笔记，并综合聊天频率、印象分、道德分给出熟悉度；聊天按熟悉度调整分寸，达到阈值会偶尔主动私聊 |
| 3010 | astrbot_plugin_youtube_music | 7 | group-admin | have | 基于 yt-dlp、Deno、FFmpeg 和 AstrBot Record 消息组件的 YouTube 点歌插件。 面向 QQ 群聊的候选分页、版本识别、语音点播、共享 FIFO 队列、收藏与历史重播。 提供音乐 AI Tool、响应式 WebUI、仅限机器人搜索结果的安全自动撤回， 以及使用 A |
| 3011 | astrbot_plugin_fns_minceraftrcon | 7 | other | watch | 集中管控多个子服务器，配置管理员白名单与权限组，直接下发指令、管理多台后端 MC 服务。 |
| 3012 | mc_query | 7 | other | watch | MC 服务器查询 - /mc 显示 logo/在线/ping/版本/MOTD 并渲染图片 |
| 3013 | astrbot_plugin_quote_topics | 7 | platform | have | 支持 AstrBot 4.28.0 及以上的 4.x 版本的飞书内置 Agent（已验证 4.29.4）。引用消息继续原话题，不引用开启新话题，支持群聊共享、私聊隔离和自动标题。默认关闭，安装后需配置启用范围；卡片按钮续聊需交互插件接入约定。 |
| 3014 | astrbot_plugin_mc_version_watcher | 7 | other | watch | 定时监测 Minecraft 官方版本更新，并向配置的私聊或群聊推送。 |
| 3015 | prompt_tools_fixed | 7 | other | watch | 一个用于管理和激活提示词的插件...修复了新版AstrBot下的TypeError报错。 |
| 3016 | liufeng_sanguo_game | 7 | game | have | ## 柳弗罗三国演义  一款基于 QQ 群的三国题材卡牌收集与对战游戏。  ### 核心玩法 - 招募：历史武将碎片兑换、架空武将与自定义武将招募 - 养成：升级、升星、技能、天赋、装备、坐骑、兵书 - 多维能力：武力/智力/体力/魅力/口才/速度，计入战力并影响战斗 - 战斗：PvP 1v1（出战 |
| 3017 | astrbot_plugin_github_star_notifier | 7 | info-push | have | 监控一个或多个 GitHub 仓库的 Star、Fork 与提交记录，出现新动态时自动推送到指定的 QQ 群或其他会话。  · 基于轮询 GitHub REST API 实现，无需公网 IP、域名或反向代理，开箱即用 · 新 Star 推送可列出具体用户，并可选附带用户头像 · 可选推送新 Fork |
| 3018 | astrbot_plugin_local_action | 7 | other | watch | 命中关键词后执行本地动作或命令。 |
| 3019 | astrbot_plugin_12306_transfer_assistant | 7 | other | watch | 查询 12306 直达与中转换乘方案，强制最小换乘缓冲并计入同城异站通勤时间；支持车站查询、余票监控与 LLM 工具调用。 |
| 3020 | astrbot_plugin_deadbot | 7 | other | watch | StatLocker 网页原站评分、个人战报、缓存排队与 Deadlock API 历史分析。 |
| 3021 | astrbot_plugin_local_codex | 7 | other | watch | 在 AstrBot 中复用本机 Codex 登录，支持工具调用、流式回复、自动思考档位、请求进度和单条取消。 |
| 3022 | astrbot_plugin_baige | 7 | other | watch | 学梗/配图/看图兜底/体检/账本/余额/分寸 + 群聊唤醒闸门与节流；涉及外部目录与运维的能力默认全关，需显式打开。 |
| 3023 | astrbot_plugin_whalehelp | 7 | other | watch | 通用帮助菜单，自动整理插件公开指令，支持自定义背景、额外文字说明、功能排除、搜索、分页、文字版和合并转发。 |
| 3024 | astrbot_plugin_ai_diary | 7 | memory | have | A private daily-diary memory plugin for AstrBot. |
| 3025 | astrbot_plugin_aemeath_visual_identity | 7 | other | watch | 爱弥斯视觉身份、主插件触发 aemeath_take_photo |
| 3026 | astrbot_plugin_star_citizen | 7 | other | watch | 查询星际公民飞船参数、商品参考价与各终端实时买卖价（数据源 UEX 公开 API） |
| 3027 | astrbot_plugin_thinking_cleaner | 7 | other | watch | 自动清理模型误输出的思考内容，避免发送给用户或写入历史上下文。 |
| 3028 | astrbot_plugin_snow_burst | 7 | other | watch | 把连续发来的几句话合成一次理解和回复，减少碎片化回应 |
| 3029 | astrbot_plugin_sytori_memory | 7 | memory | have | 为 AstrBot 提供 Anthropic「The components of agent memory」风格的长期记忆： 原始记录 → 精选笔记 → 互相关联的 Wiki → 每次会话加载的短索引； 并在空闲时通过「做梦」纠正、合并、修剪、晋升记忆。 灵感来源：https://www.anthr |
| 3030 | astrbot_plugin_weather_at | 7 | info-push | have | 群聊/私聊中 @ 机器人后发送「查询北京天气」这类指令，自动识别意图、抽取地点，并通过 AI 工具调用（function calling）获取真实天气数据后播报；模型不可用时自动降级为本地播报。 |
| 3031 | astrbot_plugin_body_monitor | 7 | other | watch | 点身体部位触发互动，自动记录和更新身体状态 |
| 3032 | astrbot_plugin_seedream | 7 | other | watch | Enable AstrBot agents to generate and edit images with Seedream 5.5. Features minimal system prompts, comprehensive error handling, and persistent sto |
| 3033 | astrbot_plugin_custom_reminder | 7 | other | watch | 在每次 LLM 请求时，向用户消息追加自定义的 <system_reminder> 风格附加消息，支持多条消息、自定义包裹标签与逐条开关。 |
| 3034 | astrbot_plugin_prompt_injection | 7 | other | watch | Inject configurable prompt context into private and group chats. |
| 3035 | astrbot_plugin_cron_dashboard | 7 | platform | have | 在 AstrBot WebUI 中可视化查看和管理定时任务，支持任务统计、启停、立即运行、新建（内置定时发消息与 HTTP Webhook 执行器）以及执行日志。 |
| 3036 | astrbot_plugin_kuang | 7 | other | watch | 为图片或用户头像叠加 FPS 外挂透视风格的白色线框。 |
| 3037 | astrbot_plugin_helldivers2 | 7 | game | have | 查阅武器与机制、核对官方简中译名，结合银河战争实况、历史和补给线分析支援目标。 |
| 3038 | astrbot_plugin_lisp_calc | 7 | other | watch | 语法形如 Lisp 的简单计算器 |
| 3039 | astrbot_plugin_dingtalk_feishu_forwarder | 6 | platform | have | 钉钉与飞书之间的双向消息转发插件，支持文本、图片等消息格式自动转换。 |
| 3040 | astrbot_plugin_yunzhijia_adapter | 6 | other | watch | AstrBot 云之家平台适配器插件。 |
| 3041 | xfbank | 6 | other | watch | 一个简易的银行插件 |
| 3042 | astrbot_plugin_lanraragi | 6 | other | watch | 使用lanraragi提供的api进行关键词搜索，并将搜索结果发送到聊天中。 |
| 3043 | astrbot_portainer_plugin | 6 | other | watch | 使用astrbot连接portainer实例进行简单的容器管理功能 |
| 3044 | astrbot_plugin_auto_forward | 6 | other | watch | 监测文本和图片消息，满足条件时自动转发。 |
| 3045 | astrbot_plugin_longterm_memory | 6 | memory | have | 基于 LLM 总结 + 向量检索 + 用户画像的长期记忆插件。自动总结对话、提取画像、智能注入上下文。 |
| 3046 | astrbot_plugin_memory_trimmer | 6 | memory | have | 固定人设 + 多策略上下文管理（硬裁剪/渐进清理/长度裁切），智能控制上下文长度，稳定缓存命中。 |
| 3047 | astrbot_plugin_shushu_collection | 6 | other | watch | 保留三套独立本地排盘规则，通过统一配置生成固定或 LLM 解读的水墨结果图。 |
| 3048 | astrbot_plugin_admin_model_router | 6 | group-admin | have | 管理员自动切换到指定模型回复，支持按群聊指定专属模型，普通用户走 AstrBot 默认模型，指定模型异常时按配置重试并回落 |
| 3049 | astrbot_plugin_choice_service | 6 | other | watch | System One 兼容的通用判断服务，支持任意单选、是非判断、服务商切换与实时统计。 |
| 3050 | astrbot_plugin_chatgpt_web | 6 | other | watch | 把 QQ 里的问题和图片转发到本机已登录的 ChatGPT 网页版，再把回答（含公式、表格和配图）渲染成图片发回 QQ。 |
| 3051 | astrbot_plugin_coc_stars | 6 | devtools | watch | 群员用 /coc绑定 绑定自己的部落冲突标签，之后发 /coc查询 就能看到最近 N 场部落战和联赛的三星率、星级分布、未进攻次数，机器人会 @ 查询的人。数据来自第三方镜像接口，不需要官方开发者 Token。 |
| 3052 | astrbot_plugin_iconic_quotes | 6 | sticker | borrow | 精简版群典：只保留四条指令。 「入典」引用一条消息收录（文字 / 图片 / QQ 表情 / 商城表情 / 合并转发）； 「典来」随机发一条；「全部典」合并转发列出全部；「删典 N」管理员删除。 每个会话的典互不相通，默认所有会话可用。 |
| 3053 | astrbot_plugin_reply_limiter | 6 | other | watch | 在消息发出前统计回复文本长度，超过设定上限时自动截断（可配置后缀）或整条拦截。支持 WebUI 可视化配置，并提供 /replylimit 管理员指令在运行时开关与调整。 |
| 3054 | astrbot_plugin_cute_status | 6 | other | watch | 用Kawaii 插画状态卡查看 CPU、内存、Swap、磁盘和 AstrBot 运行时长。 |
| 3055 | astrbot_plugin_bili_audio | 6 | media-parse | borrow | 发送 /提取音频 + BV 号，机器人提取音频并发送可点击的 QQ 语音消息；支持 /账号登录 扫码登录 B 站。 |
| 3056 | astrbot_plugin_image_reply_plus | 6 | personality | have | 关键词图库插件：一个关键词一个文件夹，WebUI 管理上传图片，随机回复并附加角色名/文件名/PID 水印，支持收集/查看/删除指令，可生成汇总所有图库的「图片帮助」菜单图。 |
| 3057 | astrbot-plugin-queue | 6 | other | watch | 用于管理排队系统的插件，支持创建队列、修改人数、查询等功能 |
| 3058 | astrbot_plugin_asmrone_sub | 6 | other | watch | 推送ASMRONE的更新到群聊 |
| 3059 | astrbot_plugin_wzry_group_ops | 6 | group-admin | have | 面向「王者荣耀交友扩列 QQ 群」的自动化私域运营引擎。绑定群后全自动运转： 数据采集 / 新人跟进 / 冷场救场 / 沉睡唤醒 / 积分结算 / 日报周榜 / 关键词应答 / SOP 推送 / 入群欢迎，共 10 项自动化任务。内置 19 题答题引擎（每题自动随机生成 A/B/C/D 选项、支持全 |
| 3060 | astrbot_plugin_foot | 6 | personality | have | 识别到"看看脚/看看足/看看jio"关键词，随机推荐饭盒（bushi）；附带群聊积分猜角色(/猜角色、/积分排行、/重置历史)与全员抢答「/人事部档案审查」「/抢答」 |
| 3061 | astrbot_plugin_relay_talk | 6 | other | watch | 在配置里绑定两个会话后，AI 就成了两人之间会自己拿捏分寸的中间人：不用下指令、不用写对象，随口一句「你帮我问问他」就带过去，对方回话也会自动带回。转述不是原文照搬，会保住事实、放软语气，还能看情况替人多说一句关心或打个圆场；可选潜台词翻译与插件内分段，回执每次现写；/话筒 校验 可逐条核对全部指令 |
| 3062 | astrbot_plugin_call_guard | 6 | group-admin | have | 单人刷屏静默防护 —— 不用再靠全局限速误伤所有群友。call_guard 只针对刷屏的那一个人：检测到他频繁 call 机器人（艾特机器人 / 引用回复机器人消息），窗口内超过阈值就把他拉进静默期；静默期内每次 call 按 reply_probability（0-1）概率放行，其余消息直接丢弃、 |
| 3063 | astrbot_plugin_jrysplus | 6 | game | have | 今日运势卡片，版式/抽签算法/背景图匹配与 koishi-plugin-jrys-prpr 保持一致。 |
| 3064 | astrbot_plugin_koharu_plus | 6 | image-gen | watch | 使用 Koharu HTTP API 翻译聊天中的漫画图片，专为服务器无 GPU 环境设计，实测纯 CPU 单页快约 10 倍。 |
| 3065 | astrbot_plugin_google_search_acedatacloud | 6 | other | watch | Use your Ace Data Cloud key to search Google and return titles, links, and snippets. |
| 3066 | astrbot_plugin_cbm | 6 | memory | have | 面板化管理 codebase-memory-mcp（CBM）——面向 AI 编码代理的代码记忆 / 知识图谱引擎。支持 UI 版 / 标准版安装、镜像加速与 SHA-256 校验、启动停止重启、内置反向代理与访问鉴权、一键写入 AstrBot MCP 配置及日志查看。已适配 CBM 0.12.x（C |
| 3067 | astrbot_plugin_notes | 6 | other | watch | 每个对话区（私聊按 QQ、群聊按群号）一块共享的 markdown 笔记区：分分类存多篇笔记，群友可存、可看、可搜、可发文件；AI 也能读写与代发 |
| 3068 | astrbot_plugin_aivoicebridge | 6 | tts | watch | 配置 A.I.VOICE 一代或二代本地桥接的声库、合成参数及二代原生风格，配合 AIVoiceBridge 使用。 |
| 3069 | astrbot_plugin_mt_mcp | 6 | other | watch | 通过 MT 管理器 MCP 服务，在聊天中读取、搜索手机文件，并把文件直接发送到聊天。支持列目录、按文件名/内容搜索、读取文本、发送任意授权路径下的文件。 |
| 3070 | astrbot_plugin_tool_arg_fix | 6 | other | watch | 修复模型以 DSML、<tool_call> 或 raw 包装形式输出工具调用参数，导致的 Tool handler parameter mismatch 错误。 |
| 3071 | astrbot_plugin_jev_damocles | 6 | other | watch | 用 JEV 决策模型 + 显式群聊状态机，接管群消息是否触发模型回答的判断 |
| 3072 | astrbot_plugin_hot_reload | 6 | other | watch | 在聊天里用 /reload 或让模型调用工具热重载插件，改完代码不用重启进程 |
| 3073 | astrbot_plugin_whale_harem | 6 | game | have | 群共享池塘钓鱼（抛竿等待/群聊咬钩）、签到喂食打工（喂 bot / 上工收工）、娶群友与后宫、仓库、天气与随机品质、DeepSeek 蓝鲸鱼娘 Pillow 出图。钓鱼打工可并行，全异步 + 惰性重置，2核2G 可跑。 |
| 3074 | astrbot_plugin_airi_core | 6 | group-admin | have | Airi 核心辅助插件，支持跨 AstrBot / gscore 等 OneBot 节点的 @Bot 命令免LLM、QQ 官Bot 的自动识别与 LLM 唤醒过滤、可配置的 @Bot / QQ 群聊与私聊关键词 LLM 唤醒（包含/前缀匹配、独立开关、独立QQ群白名单/私聊QQ白名单）、LLM 按需 |
| 3075 | astrbot_plugin_magnet_delivery | 6 | other | watch | 支持 QQ 群聊和私聊的磁力预览、下载、加密压缩与文件回传，可识别合并转发中的磁力链接，并按会话管理任务。 |
| 3076 | astrbot_plugin_traditional_commands | 6 | other | watch | 保留原簡體指令並加入繁體相容；可選擇將已核對的 WebUI 核心語系文案繁體化，不轉換輸入與聊天內容。 |
| 3077 | astrbot_plugin_cross_session_cache | 6 | other | watch | 跨会话热缓存 —— 让 Bot 在私聊和群聊之间无缝感知刚聊过的内容。 |
| 3078 | astrbot_plugin_qq_scene_keeper | 6 | proactive | watch | 在 AstrBot 重启或平台重载后恢复 QQ 官方适配器的会话场景，保证主动消息正常发送。 |
| 3079 | astrbot_plugin_history_query | 6 | other | watch | 按用户和平台实例授权的群聊与 AI 私聊历史只读查询，支持来源核对和受限续查。 |
| 3080 | dialoguesoul | 6 | memory | have | 本项目由 AI 制作。言灵（DialoguesSoul）是基于 AstrBot 管线实现的群聊社交插件，支持自主回复、唤醒会话、图片与合并转发上下文，并兼容知识库和第三方长期记忆插件。 |
| 3081 | astrbot_plugin_image_studio | 6 | image-gen | watch | 多服务商文生图、图生图、本地 SVG 绘图与动画说明工具。可保存多个服务商配置并切换，支持把概念脚本本地渲染为 GIF/WebP/MP4。 |
| 3082 | astrbot_plugin_ER_userinfo_get | 6 | group-admin | have | 获取永恒轮回（Eternal Return）的玩家对局、段位和角色数据。支持玩家战绩查询（含队友详情）、历史赛季、角色评级排行、排行榜、备注（玩家/角色/武器）、小组管理；QQ 官方机器人支持入群欢迎、指令面板、图文消息（战绩图与按钮合并为单条）以及卡下方按钮切换赛季。 |
| 3083 | astrbot_plugin_agentmail | 6 | platform | have | 用 AgentMail 收发邮件：/mail 指令（含 v0.4.0 历史邮件搜索）+ LLM 工具 + 新邮件推送（v0.5.0 可带附件）+ 每日未读摘要，私聊和群聊都能用，支持直连/代理自动切换 |
| 3084 | astrbot_plugin_subagent_call | 6 | personality | have | 角色扮演模式下用标签呼叫隔离子代理执行工具任务：清洗标签、保留上下文、回传结果并生成终稿。 |
| 3085 | astrbot_plugin_debug_group_guard | 6 | group-admin | have | 仅允许配置的 Debug 群执行斜杠指令。 |
| 3086 | rocket_launch_inquiry | 6 | other | watch | 查询最近5次火箭发射记录 |
| 3087 | astrbot_plugin_proxy_manage | 6 | other | watch | 可视化管理 AstrBot 的代理出口、分流策略、节点健康状态和连通性诊断；AstrBot 4.28.2 内置 44 类 Provider 中，30 类已有请求级证据，11 类显式接入稳定入口，2 类部分接入，1 类及未知类型保持未适配或未验证。 |
| 3088 | astrbot_plugin_warband_status | 6 | other | watch | 查询骑马与砍杀：战团 CN_X1、CN_X4、CN_X3_GK 的在线人数和服务器信息。 |
| 3089 | astrbot_plugin_hapi_discord_connector | 5 | kb-rag | have | 仅支持 Discord 的 HAPI coding session 管理插件：/dhapi 原生 Embed/Button/Select 面板与 dhapi_coding_* 审批工具；要求 Python 3.10+、AstrBot 3.4+。 |
| 3090 | astrbot_plugin_media302-save | 5 | other | watch | media302 软件的 115 转存插件，可以提交 115 链接给机器人，机器人自动转存到 115 网盘 |
| 3091 | astrbot_plugin_wuxianews | 5 | info-push | have | 天涯明月刀公告推送：天刀公告列表、天刀最新公告、定时推送（每 5 分钟检查，有更新自动推送）。 |
| 3092 | astrbot_plugin_nuist_power | 5 | info-push | have | 南京信息工程大学电费余额查询插件，支持多用户绑定、定时订阅、低电量自动告警。 |
| 3093 | astrbot_plugin_game_card | 5 | game | have | 游戏商店图卡插件。目前支持 Steam 游戏搜索和 Steam 商店链接识别，可将游戏详情渲染为适合聊天转发的图片卡片。  项目后续计划扩展 Xbox、PlayStation、Nintendo 等平台，目前尚未开发这些平台接入。 |
| 3094 | astrbot_plugin_astrbot_tweaks | 5 | media-parse | borrow | 运行时 tweak 插件，不修改 AstrBot 本体源码。 插件将上下文压缩、提示词、响应可靠性、LLM 参数透传与工具直通等多项 AstrBot 行为调整拆分为独立开关，卸载或重载时恢复原始方法。 |
| 3095 | astrbot_plugin_button_menu | 5 | other | watch | 可视化配置 QQ 官方群聊 /菜单 按钮面板：自定义按钮文字、发送文本/图片/链接、分页布局、生效机器人与预览 |
| 3096 | astrbot_plugin_media_portal | 5 | other | watch | 为 AI 与用户打造的多媒体门户：支持 AI 智能分类收藏，集成音视频预览播放与可视化管理的 AstrBot 插件 |
| 3097 | astrbot_plugin_aktmp_bot | 5 | other | watch | 阿K传媒TruckersMP查询插件 专为TruckersMP绑定/解绑/查询/定位/路况/服务器/里程排行/足迹/地图DLC插件版本提供服务##作者:QQ737107334 |
| 3098 | mindmap | 5 | other | watch | 通过 LLM 工具渲染中文思维导图、时间线、表格与基础流程图 |
| 3099 | astrbot_plugin_youshouyan | 5 | media-parse | borrow | 发送 /看 有兽焉第X话，从媒体接口取回剧集限时直链并发送 |
| 3100 | subagent_viz | 5 | other | watch | Hermes-style sub-agent visualization dashboard for AstrBot. Live Gantt timeline, nested agent tree and full per-agent conversation (tool calls, result |
| 3101 | astrbot_plugin_teacher_manager | 5 | other | watch | 教师教学辅助插件：通知/任务分发与回复收集、聊天总结（含定时规则+目标方同意授权）、学情档案、EULA 门禁 |
| 3102 | astrbot_plugin_food_calorie | 5 | other | watch | 发食物图片时，给模型补一句自然聊热量的提示；不抢回复、不调用外部 API、不保存聊天数据。 |
| 3103 | astrbot_plugin_vrchat | 5 | other | watch | 以 /vrc 为单入口的 VRChat 助手：查询用户/世界/好友/通知/群组/收藏/虚拟形象（Avatar），支持多用户独立绑定、Fernet 加密凭证、全量 Cookie 登录态持久化、TOTP 自动 2FA、60 秒缓存、分类渲染（通知走纯文本、资料/列表出图），以及好友上线提醒与全局通知推送 |
| 3104 | astrbot_plugin_keyword | 5 | other | watch | 按群聊关键词发送固定文本或结合近期上下文生成自然回复。 |
| 3105 | astrbot_plugin_quick_note | 5 | group-stats | borrow | 随手记 / 备忘 / 待办插件：随口说一句，机器人自动记下并整理。 - 极低摩擦：「记 明天下午3点交报告」「记 周五买牛奶 不急」，时间与优先级自动识别 - 智能解析：今天/明天/下周三/11月15号/3天后/晚上8点半/10:30 等中文时间写法都认得 - 自动整理：「清单」按 已过期 → 紧急 |
| 3106 | astrbot_plugin_daily_newspaper | 5 | group-stats | borrow | 默认早中晚三档、可增删至 12 档，每档由研究 Agent 联网检索当日新增报道并核实，时间、目标群、研究提示词与版式均独立配置；强制要求 completed 搜索调用及逐条 source/url/published_at 才允许出刊。研究与排版两段解耦：结构化简报先编译成逐字文案，再由 gpt-i |
| 3107 | astrbot_plugin_stalzone | 5 | kb-rag | have | 通过官方 STALZONE API 在 QQ 群内查询拍卖在售/成交、辐射爆发、角色资料、战队、行动记录和物品； 支持 OneBot 与 QQ 官方机器人（qq_official / qq_official_webhook）；支持中文/英文物品名解析到 ID； 输出可选卡片图片或纯文本。实时数据不写 |
| 3108 | astrbot_plugin_link_preview | 5 | media-parse | borrow | 发链接就行，不用打指令。B 站链接会把视频下载下来直接发出去， 其他链接回标题、来源、简介和封面图。  平台支持： - 哔哩哔哩：走官方 x/web-interface/view + x/player/playurl 接口，   拿 durl 合并流（音视频已并好），标题、UP 主、时长齐全，支持  |
| 3109 | astrbot_plugin_reasonix | 5 | other | watch | 将 AstrBot 的文本消息回复生成无缝切换到宿主机上的 Reasonix 本地大模型， 支持通过 /reasonix on/off 命令实时开关，状态持久化保存。 群聊中仅响应 @ 机器人的消息，私聊全量接管。 |
| 3110 | astrbot_plugin_ba | 5 | other | watch | 一个适用于Astrbot的BlueArchive攻略插件。 |
| 3111 | astrbot_plugin_comfy_bridge | 5 | image-gen | watch | 基于0.5.2-1.44的QQ独立分包；自带API工作流与操作说明，不需要Hub或客户端。 |
| 3112 | astrbot_plugin_breezetts | 5 | tts | watch | 以插件方式向 AstrBot 注入 Breeze TTS 提供商（text_to_speech），不改动 AstrBot 本体。 |
| 3113 | astrbot_plugin_dl_accel | 5 | other | watch | 接管 AstrBot 的插件与核心下载：自动探测本机代理、HTTP Range 多路分块并行、本地磁盘缓存。装完不用改任何设置，插件安装/更新与 AstrBot 核心更新的下载速度就能明显变快；任何一步失败都会自动回退原生下载，绝不会让本来能装上的东西装不上。 |
| 3114 | astrbot_plugin_human_like_memory | 5 | memory | have | 类人长期记忆：新记忆先进短时暂存区，定性后才转正式库。带分区、定性、回溯比对、红线过滤和纠错入口。关键词+可选语义双路检索。v3.9 原文归档/实时采集/自主整理。v3.10 睡眠强化。v3.11 相关性识别。v3.12 记忆回想优化。v3.12.2 修 people.py 表顺序坑。v3.12.3 |
| 3115 | generic_fallback | 5 | other | watch | 通用回退插件，可配置多个模型回退列表整合成的虚拟模型，供本体及其他插件调用 |
| 3116 | astrbot_plugin_pi | 5 | other | watch | 通过 AstrBot 聊天控制 Pi 编码智能体，支持持久会话、任务转向、停止、压缩、状态查询、模型与思考等级切换。 |
| 3117 | astrbot_plugin_mcserver_monitor | 5 | other | watch | 直连 Minecraft 服务器地址（支持多服务器 /mcadd 管理），检测开服、关服与在线人数变动并推送；记录每台服务器当天游玩人数，每天0点自动总结推送。 |
| 3118 | astrbot_plugin_feishu_agent_card | 5 | platform | have | 为飞书 Agent 提供实时卡片回复、代码/表格/图表/图片展示、交互表单续聊、终止回答，以及处理过程、工具来源和 Token 用量。当前仅支持 AstrBot 4.28.0，交互需飞书长连接及卡片回调订阅；每张交互卡片限一次提交，24 小时或重载后失效。不依赖话题插件。 |
| 3119 | astrbot_plugin_showcase | 5 | other | watch | AstrBot 插件能力全景示例：配置 Schema、事件钩子、国际化、WebUI Page、LLM 工具与持久化存储。 |
| 3120 | astrbot_plugin_mark | 5 | other | watch | 跨群共享引用消息标记，支持按编号阅读、删除、清空及指令帮助。 |
| 3121 | astrbot_plugin_tshock | 5 | game | have | 通过 TShock REST API 管理 Terraria 服务器。支持查询服务器状态与在线玩家、 执行远程命令（广播 / 私聊 / 原始指令），以及聊天室与游戏服务器之间的消息桥接。 兼容 TShock 6.x（已在 TShock 6.2.1.0 / Terraria 1.4.5.8 实测）。 |
| 3122 | astrbot_plugin_router | 5 | devtools | watch | 将不同用户路由到不同模型，闲聊者用反应快的模型，开发者用干活强的模型 |
| 3123 | astrbot_plugin_gacha | 5 | other | watch | 纯本地存储、自带 WebUI 管理面板的抽卡插件。所有内容以文件形式组织，不依赖数据库。支持多卡池、自定义权重、每日次数、群白名单、图片上传。详见仓库 README。 |
| 3124 | astrbot_plugin_wechat_auth | 5 | other | watch | 自动识别微信用户并将指定用户设为管理员 |
| 3125 | astrbot_plugin_screenshot | 5 | media-parse | borrow | 网页截图兜底解析器，内置 Chromium 自动准备与状态检测，支持 NodeSeek 正文与置顶/Hot 评论、HTTP/SOCKS5 代理及域名路由。 |
| 3126 | astrbot_plugin_dota2tracker | 5 | group-stats | borrow | 追踪群友的 DOTA2 对局：订阅/绑定、Stratz 比赛战报、段位播报、日报周报、玩家/英雄/物品查询与图片模板。移植自 koishi-plugin-dota2tracker（GPL-3.0）。 |
| 3127 | astrbot_plugin_search_manners | 5 | other | watch | 控制联网搜索的触发与表述：明确要求必搜，平时低频自发搜索并注明来源 |
| 3128 | astrbot_plugin_gatekeeper | 5 | other | watch | 为 AstrBot WebUI 登录界面加上 Cloudflare Turnstile 人机验证，并统计凭据错误次数自动封禁来源，拦截撞库与暴力破解；支持自定义访客 IP 来源与登录日志。 |
| 3129 | astrbot_plugin_config_backup | 5 | other | watch | 定时把 AstrBot 核心配置（cmd_config.json）与插件配置（data/config/*.json）打包成 zip，默认对 API Key 等密钥字段脱敏，可选完整备份及数据库，按份数自动清理旧备份，支持管理员手动触发。 |
| 3130 | astrbot_plugin_time_period_prompt | 5 | personality | have | 让 AI 根据你的工作、休息、日期时间和生活节律调整陪伴方式。 支持双休、单休、大小周、无休、自定义工作星期、临时休息日/工作日、 法定节假日与调休补班、工作日/休息日/通用三组独立注入开关、 聊天语义识别临时日切换、日期时间提示、精确到分钟的时间段规则、 时段交接模糊区间、今日附加提示等功能。 |
| 3131 | astrbot_plugin_litematic_preview | 5 | other | watch | 发送投影文件并 @机器人，自动用真实材质/方块模型渲染成等距预览图；支持 .litematic/.schem/.schematic/.nbt/Axiom .bp，最多 8192 分辨率，默认一次给出 4 个对角视角并附材料表格/Excel（统一渲染尺寸；资源包/材质包由用户自备；无需启动 Minec |
| 3132 | astrbot_plugin_exif_location | 5 | other | watch | 读取聊天图片 EXIF 中的 GPS 信息，逆地理编码后以“请问是XX的群友吗”的方式回复。 |
| 3133 | astrbot_plugin_usage_lens | 5 | other | watch | Magpie 可视化用量与账号额度看板，支持缓存命中率、费用趋势、模型明细及聊天查询。 |
| 3134 | astrbot_plugin_no_snowluma | 5 | group-admin | have | 禁止 SnowLuma 的内置命令在群内发送。命中指定命令即禁言，并自动撤回机器人发出的 SnowLuma 状态信息。 |
| 3135 | astrbot_plugin_fencun | 5 | personality | have | 让 AI 有分寸——用约束做人格，而不是让 AI 演人设。 |
| 3136 | astrbot_plugin_booger | 5 | game | have | 群聊小游戏：弹射、帮擦、成就称号、每日排行榜、近七日恶臭榜、吃鼻屎、烤鼻屎、鼻屎大餐料理系统和自动播报。 |
| 3137 | astrbot_plugin_huoxingwen | 5 | other | watch | 发送前把模型回复转换成火星文（或繁体字、混排），码表与 huoxingwen.qianwanku.com 一致，支持保留代码块、链接与 @，支持流式输出与按会话开关。 |
| 3138 | astrbot_plugin_va11hall | 5 | personality | have | 欢迎来到 VA-11 HALL-A，又名「英灵殿」—— Glitch City 中心的小酒吧。  ✨ 视觉小说模式：PIL 动态合成霓虹场景（背景渐变 + 角色立绘 + 对话框 + 选项面板） 🎭 11 位可交互客人（Dorothy / Sei / Dana / Stella / Alma / Do |
| 3139 | astrbot_plugin_mc_local_monitor | 5 | other | watch | 本地 Java 版 Minecraft 服务器状态监控插件，支持状态变化自动推送和手动查询 |
| 3140 | astrbot_plugin_minecraft_status | 5 | other | watch | 查询 Minecraft Java 版服务器在线状态（本地直连 SLP 协议，不依赖任何第三方 API）。 支持 /mc 查询默认服务器、/mc add 添加、/mc delete 删除、/mc set 设置默认、 /mc list 列出、/mc <名称> 查询指定服务器；每个群聊的服务器数据完全隔 |
| 3141 | astrbot_plugin_894_arbiter | 5 | other | watch | 多机器人环境下自动仲裁，决定由哪个机器人响应命令。 |
| 3142 | astrbot_plugin_komari | 5 | other | watch | Komari 高清监控卡片：概况/列表/单机/分类 |
| 3143 | astrbot_plugin_tg_download | 5 | other | watch | Telegram 文件自动下载插件：识别 document/video/audio/photo/video_note 消息，≤20MB 自动下载到 Aria2（按类型分类到 Alist），20MB~2GB 询问主人存本地还是服务器，>2GB 提示电脑端处理。支持环境变量配置。 |
| 3144 | ts_music | 5 | other | watch | 通过 AstrBot/NapCat 群聊控制 teamspeak-music-bot 指定实例播放音乐 |
| 3145 | sb-slayer | 5 | other | watch | ... |
| 3146 | astrbot_plugin_filament_manager | 5 | other | watch | 通过自然语言管理3D打印耗材的入库、余量、消耗、耗尽与历史记录。 |
| 3147 | astrbot_plugin_color | 4 | other | watch | 实现颜色格式互转、图片按坐标取色等颜色分析功能 |
| 3148 | astrbot_plugin_3dmapi | 4 | game | have | 3dmmod 搜索插件，支持在 3dmgame Mod 站搜索相关 Mod 内容 |
| 3149 | astrbot_plugin_ragecoop | 4 | other | watch | GTAV RageCoop 服务器查询插件 |
| 3150 | tron_address | 4 | other | watch | 波场地址查询插件 |
| 3151 | astrbot_plugin_conversation_manager | 4 | other | watch | 对话可视化管理：浏览/编辑/删除/插入消息与思考过程、自动快照撤销、JSONL 导入导出、手动与按阈值（轮数/字数/Token）自动分块压缩摘要（失败保命绝不删记录） |
| 3152 | astrbot_plugin_lucky_stun | 4 | platform | have | 接收 Lucky STUN Webhook，持久化各规则最新公网地址，并主动推送到已配置的 QQ 私聊/群；支持命令查询与绑定。 |
| 3153 | astrbot_plugin_pjsk | 4 | personality | have | 世界计划国服歌曲与谱面查询、日服卡面与活动图鉴，支持国服/日服当前活动及榜线，支持角色与团队别名、卡片ID、全部结果合成一张长图、花前花后及技能资料。数据来自可配置的日服游戏数据社区镜像，并非官方API。 |
| 3154 | astrbot_plugin_call_me_by_api | 4 | other | watch | 将自己封装成 Anthropic 兼容 API，通过私聊人工回复；仅转发最后一条用户正文，支持流式响应与模型查询。 |
| 3155 | hub-pusl | 4 | other | watch | 通过 GitHub API 在群内推送图片并创建 PR，或随机拉取图片到群内，无需本地 clone 仓库。 |
| 3156 | astrbot_plugin_weather | 4 | info-push | have | 查询当前城市天气（温度/天气状态/湿度/风向/风力/日出日落/未来7天预报），复刻官方天气小组件 SsoGetWidgetWeather 请求 |
| 3157 | astrbot_plugin_bdpan_openlist | 4 | other | watch | 自动识别百度网盘分享链接，使用 Cookie 转存至指定目录并通过 OpenList 生成分享链接发给用户 |
| 3158 | astrbot_plugin_whale_agenda | 4 | proactive | watch | 小鲸鱼一体包：定时提醒（早间简报、课前、学习块、三餐、熄灯、周复盘）+ 主人身份注入与回复压行 + 三个日程查询 LLM 工具；课表存 JSON，可在 WebUI 插件页面编辑并绑定主人 QQ。 |
| 3159 | astrbot_plugin_cursor | 4 | other | watch | 使用 Cursor Python SDK，把 Cursor Agent 作为 AstrBot 聊天模型。认证使用用户 API Key 或服务账号 Key。 |
| 3160 | astrbot_plugin_birdreport | 4 | other | watch | 定时向指定 QQ 群/QQ 推送城市鸟讯；默认使用中国观鸟记录中心，不可用时可自动切换 eBird |
| 3161 | astrbot_plugin_vrm_avatar | 4 | other | watch | 为AstrBot提供一个VRM虚拟形象的插件。支持两种使用方式：1、在插件页面中内嵌预览（无法持久化保存前端配置）2、单独部署前端应用 astrbot_vrm_avatar_client（https://github.com/Crispburgerde/astrbot_vrm_avatar_clie |
| 3162 | astrbot_plugin_conversation_opener | 4 | other | watch | 列出机器人加入的全部群聊，标出哪些群还没有活跃对话；在插件页面里勾选即可为这些群开启会话，也可以关闭已有会话，让主动回复只在想要的群里工作。 |
| 3163 | astrbot_plugin_paperphoneplus | 4 | other | watch | PaperPhone Plus 平台适配器，使 AstrBot 能以普通用户身份接入 PaperPhone Plus 端对端加密即时通讯（Rust 后端版本）。 |
| 3164 | astrbot_plugin_deep_letter | 4 | other | watch | 让你的bot在不同会话之间说悄悄话。 |
| 3165 | astrbot_plugin_drift_bottle_lite | 4 | other | watch | 一个轻量级、带隐私保护的跨群盲盒聊天插件，支持随机代号与跨群漂流。 |
| 3166 | astrbot_plugin_pinned_context | 4 | tts | watch | 钉选上下文块插件——让用户在对话中手动锚定关键信息，提高单个会话在行为规范、角色扮演等场景下的准确性 |
| 3167 | astrbot_plugin_mini | 4 | other | watch | /mini 查玩家，/map 查地图或作品卡片，/maps 下载排行，/down 发地图包。 |
| 3168 | astrbot_plugin_warm_memory | 4 | memory | have | 仅用于 AstrBot 私聊场景：按身份保存和召回长期记忆，支持按需语义检索、可选嵌入与重排序。 提供按会话启用的定时日记、基于用户原话证据的记忆整理、本地重复记忆合并和用途开销统计。 手动压缩先生成摘要与候选记忆，用户审阅确认后才截断历史；可与主动消息插件协作读取有效已确认摘要并统计开销。 不写入 |
| 3169 | astrbot_plugin_family_memory | 4 | memory | have | 双 Bot 隔离记忆、可选增量向量检索、本地聊天档案与上下文整理；新增功能默认关闭。 |
| 3170 | astrbot_plugin_book_companion | 4 | personality | have | 小说、散文、通识与专业书籍的图文阅读、读书笔记和跨会话回忆 |
| 3171 | astrbot_plugin_hear_voice | 4 | memory | have | 面向 AstrBot 的非抢答双阶段多引擎语音理解插件（我听得见语音），原生兼容「我会永远陪着你」（private_companion）与「我会牢牢记住你」（memory_companion）。  核心设计： - 主/备双槽自由组合与自动无缝故障切换：同时支持 Gemini 多模态（原生 gener |
| 3172 | astrbot_plugin_mint_osu | 4 | group-stats | borrow | 通过 MintAPI 查询 osu! 资料、成绩、谱面和比赛，支持周报、同图对比与群订阅。 |
| 3173 | astrbot_plugin_wake_list | 4 | group-admin | have | 黑/白名单，优先级低于管理员 |
| 3174 | astrbot_plugin_bluewhale | 4 | memory | have | blue whale：桌面上的 Live2D 桌宠「大肥鱼」（AIRI 特别版）接进 AstrBot。 - AstrBot 打开时自动叫出桌宠，关掉时一起关；第一次使用自动下载桌宠程序（约 485MB，先 Gitee 后 GitHub，核对指纹） - 对桌宠打字或用麦克风说话，由 AstrBot 回 |
| 3175 | astrbot_plugin_multi_api_router | 4 | other | watch | 为 AstrBot 提供多上游模型路由与原生 Provider 接入能力， 统一错误分类与处置，同上游按类别重试（默认一次）并优先遵守 Retry-After， 健康检测或真实调用成功都会解除健康跳过，指定上游不受跳过影响； 支持整体自动分配、指定上游、拖拽排序、路由总超时、API 类型分类、 连续 |
| 3176 | astrbot_plugin_dynamics_learning | 4 | other | watch | 为 Chat Dynamics 学习群友表达、打字习惯、喜恶、黑话与社交状态，保持自身性格固定，依据回合反馈提出调整，经 LLM 或人工审查后应用，并支持版本回滚。 |
| 3177 | astrbot_plugin_visual_media | 4 | sticker | borrow | 独立集成表情收集检索、图片生成改图、角色参考和生成图收藏。 |
| 3178 | astrbot_plugin_codex_quota | 4 | other | watch | 接收桌面额度快照，额度重置或增加时 QQ 私聊推送，并支持主动查询。 |
| 3179 | astrbot_plugin_paopao_companion | 4 | tts | watch | 桌宠/桌娘的陪伴能力开关台。  - 采集与生成跑在独立的本地核心服务里（默认 `http://127.0.0.1:9888`），**不占 AstrBot 进程**；   这个插件只是遥控器——查询状态、切模式、体检、试听。 - 模式：`auto` / `normal` / `video` / `an |
| 3180 | astrbot_plugin_endstone_arc | 4 | game | have | 弧光 EndStone 群服消息中枢。在 AstrBot 上开启 WebSocket 中枢，对接 EndstoneMC-ARC-QQ-Sync-Plugin 与 EndstoneMC-ARC-AI-Helper；双向转发 QQ/MC 消息与跨服事件，并提供 MC AI 对话 RPC。 |
| 3181 | obsidian_reminder | 4 | info-push | have | 本插件使 Astrbot 配合 Obsidian 进行待办事项管理，并附带多源 RSS 新闻简报功能。 |
| 3182 | astrbot_plugin_telnet | 4 | other | watch | 使古早设备可以通过 Telnet 协议与 Astrbot 聊天 |
| 3183 | astrbot_plugin_hook_toolkit | 4 | other | watch | Hook 补丁工具集，现能解决：插件规范命名、插件网络、子代理注册内置工具。 |
| 3184 | extra_commands | 4 | group-admin | have | 为 AstrBot 提供额外命令的插件。加入了诸如 /ban、/forcequit、/log 等命令（管理员权限使用 AstrBot 官方 admins_id）。具体参阅README及/ehelp。 |
| 3185 | astrbot_plugin_nso_friends | 4 | game | have | 轮询 Nintendo Switch Online 好友状态（Coral 3.5 / nxapi 加密协议），好友开始游玩或切换游戏时把游戏名、封面、累计时长渲染成卡片推送到群；支持查询好友当前游戏与本地游玩记录。 |
| 3186 | astrbot_plugin_deepseek_status | 4 | other | watch | 轮询 DeepSeek 官方状态页，向指定群推送事件变化及首次状态摘要。 |
| 3187 | astrbot_plugin_image_exif | 4 | other | watch | 读取聊天图片 EXIF 中的 GPS 信息，逆地理编码后以“请问是XX的群友吗”的方式回复。 |
| 3188 | astrbot_plugin_reply | 4 | other | watch | 关键词回复、消息链、作用域、冷却和统计管理。 |
| 3189 | astrbot_plugin_runtime_info | 4 | other | watch | 提供按需调用的 llm_tool `get_runtime_info`：当 AI 被问到「你用的什么模型 / 跑的哪个」时，自动查询并返回当前真实型号、累计 token 用量、真实缓存命中率，不再凭印象乱编。附带 miuix 风格 Web 仪表盘（当前型号 + 最近一次命中率圆环、Token 四格、 |
| 3190 | astrbot_plugin_moss_image | 4 | image-gen | watch | 调用 MOSS-Image API 进行文生图，支持指令与 LLM 函数调用 |
| 3191 | astrbot_plugin_hindsight_memory | 4 | memory | have | ⚠️ 使用本插件的前提是 单人单机器人私聊（只养一条鱼）。记录 QQ 每一句私聊原始对话，存入自托管 Hindsight 服务器，并在会话中召回相关记忆。 |
| 3192 | astrbot_plugin_video_to_gif | 4 | other | watch | 将聊天中的图片或视频转换为 GIF、PNG、JPG、WebP、MP4 |
| 3193 | astrbot_plugin_collectimage | 4 | personality | have | 自动识别群聊图片内容、提取标签和角色，并实现本地持久化存储与检索。 |
| 3194 | astrbot_plugin_wenshu | 4 | kb-rag | have | 按意图选择预设，联网与知识库核实资料，独立生成指定风格文案。 |
| 3195 | astrbot_plugin_openlist_share | 4 | group-admin | have | 群文件共享助手：LLM 审核后上传文件到 OpenList，查询文件列表并返回分享链接。 |
| 3196 | astrbot_plugin_mcsmanager_console | 4 | other | watch | 通过 /mcs 聊天命令管理 MCSManager 节点、实例、日志与配置。 |
| 3197 | astrbot_plugin_pr_notify | 4 | sticker | borrow | GitHub PR 通知、code owner 管理、群聊与私聊推送及群消息表情回应。 |
| 3198 | astrbot_plugin_krypton | 4 | other | watch | 手动指定 QQ 启动自主联系日程，查询群活动并增强原生跨会话未来任务，可选 JEV 判断群聊参与时机。 |
| 3199 | astrbot_plugin_freemodel_sync | 4 | other | watch | Admin commands to list free LLMs, sync them into your tool configs with freemodel-sync, and run it on a schedule. |
| 3200 | astrbot_plugin_maoyu | 4 | other | watch | 离线像素养毛玉，十八套东方装饰、成长成就、散步收藏、自动备份与独立群存档。 |
| 3201 | astrbot_plugin_xiaoai_ledger | 4 | other | watch | QQ 里记账、查账、改账、回收站恢复，月度统计与预算提醒，到期前提醒待还账单；也能就地安装/升级记账本。配套记账项目（源码与下载）：https://github.com/feng20010612-glitch/xiaoai-ledger |
| 3202 | astrbot_imessage_adapter | 4 | other | watch | 使用 Photon Spectrum 为 AstrBot 提供 iMessage 私聊、群聊与多媒体消息平台。 |
| 3203 | astrbot_plugin_cpa_usage | 4 | other | watch | 匹配当前 AstrBot Provider，只读查询 CPA 配额并发送容量卡片。 |
| 3204 | astrbot_plugin_submission | 4 | group-admin | have | 毛茸茸的跨年夜活动投稿审核插件，支持文本/视频/音频多类别投稿、自动上传云盘、Excel存储、每日限流。 |
| 3205 | astrbot_plugin_52poke | 4 | game | have | 按知识时效和问题类型调用 MediaWiki API 检索神奇宝贝百科。 |
| 3206 | astrbot_plugin_spark | 4 | other | watch | 在聊天中分析Minecraft Spark报告，支持专用模型、报告缓存和历史比较。 |
| 3207 | astrbot_plugin_smm2_lunix | 4 | image-gen | watch | Super Mario Maker 2 level/player query, random draw, bcd download, HD level rendering. Cross-platform (Windows/Linux), bundled toost renderer. |
| 3208 | astrbot_plugin_wechat_notice_digest | 4 | group-stats | borrow | 从本机微信数据库自动采集各群全体通知，提供私聊要点汇总。 |
| 3209 | astrbot_plugin_rclone | 4 | other | watch | 通过 rclone 在本机与多种云存储（OneDrive、Google Drive、Dropbox、S3 等）之间执行上传更新、云端镜像、下载更新和本地镜像，提供动态连接配置、官方 GUI 和同步管理页面。 |
| 3210 | astrbot_plugin_mode_switch | 4 | personality | have | 自定义任意多个模式，用触发词或中英文指令（/模式、/mode）按群、按会话或全局开关。每个模式有独立的系统提示、权限和全局开关，关闭后可自动回滚它留下的对话历史。 |
| 3211 | astrbot_plugin_bili_verify_feishu | 4 | group-admin | have | QQ入群请求自动校验B站UID并登记到飞书多维表格，支持多bot白名单轮询、失败补录与离线通知 |
| 3212 | astrbot_plugin_botami_essential | 4 | other | watch | 提供 Minecraft 服务器查询、计数器、群聊食物推荐、睡眠记录与根号历时间的 AstrBot 扩展插件 |
| 3213 | astrbot_plugin_paperphone | 3 | other | watch | AstrBot PaperPhone 适配器插件 |
| 3214 | astrbot_plugin_sha | 3 | group-admin | have | 基于原仓库 IGCrystal-NEO/astrbot_plugin_sha 的fork版本 |
| 3215 | astrbot_plugin_boss_notifier | 3 | info-push | have | AstrBot头目通知插件，可更新头目信息并通知订阅者 |
| 3216 | astrbot_plugin_YumeCard | 3 | info-push | have | 让 AstrBot 支持 YumeCard，同时也进行自动部署和管理配置项(主项目 YumeCard 系统要求为 Linux or Win 平台) |
| 3217 | astrbot_plugin_GGAC_Messenger | 3 | other | watch | anka - GGAC 作品更新推送插件 - 自动监控并推送 GGAC 平台精选作品的更新! 附赠一套 GGAC 网站完整 api! 还有随机抽取 GGAC 内容功能, 详情见github页面! |
| 3218 | astrbot_plugin_astronomy | 3 | other | watch | 一个用于bot查询各项天文信息（月相、天体升落、观星指数等）的小工具 |
| 3219 | astrbot_plugin_keyword_watch | 3 | info-push | have | 任何群成员都能用「/设置关键词提醒 关键词」为自己订阅关注词，之后该群消息命中就会私聊提醒本人。 关键词只在设置它的那个群生效，不会跨群打扰；支持纯文本和 /正则/ 两种写法， 并提供查看、删除、清空等自助指令。订阅数据持久化保存，重启不丢。 |
| 3220 | astrbot_plugin_mc_bridge | 3 | memory | have | 把自然语言指令变成真实的 Minecraft 行动。AI 会观察周围环境、使用当前背包里的物品，并在任务结束后按实际结果回复。  支持采集木材、矿石和作物，合成工具、烧炼材料、整理箱子，以及建造、耕种、战斗、睡觉、探索和回家。多步骤任务可以查看进度、取消，并在完成后主动通知；低血量、敌人靠近或目标不 |
| 3221 | aatrbot_plugin_mzdownload | 3 | proactive | watch | 读取萌宅社区下载api来提取下载链接下载 |
| 3222 | astrbot_plugin_hd2_suite | 3 | group-admin | have | 《绝地潜兵 2》（Helldivers 2）中文战况机器人全家桶 —— 一个插件装齐全部子系统。  指令：/战报 /重要指令 /战线 /dss /战役 /查询 /变种 /wiki /btk测伤 /拆毁值 /roll /分析 /帮助 /银河星图 /api。  特性： · 黑金 HUD 图片卡（Stea |
| 3223 | astrbot_plugin_ipv6 | 3 | other | watch | 群聊中发送「查询ipv6/查6/查询6」即可查看机器人所在服务器的公网 IPv6 地址（含临时地址与非临时地址），并可检测配置端口的本地服务运行状态，仅限配置的白名单群使用。 |
| 3224 | astrbot_plugin_github_kantu | 3 | other | watch | GitHub解图：贴一个 GitHub 仓库链接，就自动画出一张数据卡片——星标、分叉、未关闭议题、主要语言、开源许可、最近更新，一眼看完。也可以发 /kantu 手动查。 |
| 3225 | astrbot_plugin_ascii | 3 | other | watch | 支持附带图片、@成员或 QQ 号头像、单发指令回溯最近图片；基于 vietnh1009/ASCII-generator。 |
| 3226 | astrbot_plugin_remoteci | 3 | platform | have | 连接 RemoteCI：用指令或自然语言查课表、控制教室和管理系统；给老师主动推送当日/次日日程、课前提醒与换课提醒（可直接回复“同意”审批，飞书/钉钉/企业微信发原生卡片），节假日自动暂停；运维群转发设备与自动化告警；内置 WebUI 管理会话与推送。 |
| 3227 | astrbot_plugin_mc_server_guard | 3 | other | watch | [AI 修改版] 基于 astrbot_plugin_minecraft_multi_monitor (xlyang / XiaolongYang-HZAU) 的 Minecraft 多服务器监控（SLP 本地直连）：上下线滞回确认、单服务器异常隔离、防僵尸监控任务、失联降频、UMO 动态推送目标（ |
| 3228 | astrbot_plugin_cursor | 3 | ssh-exec | exclude | 通过官方 Cursor CLI 的 ACP 接入指定模型，固定 Ask 模式。支持会话复用、按轮转发图片、WebUI 用量统计与连通性诊断，以及本地隔离或专用 SSH 运行器。 |
| 3229 | astrbot_plugin_runtime_guard | 3 | memory | have | 通过分析冷却、画像消息合批与输出长度限制，帮助减少 Iris Chat Memory 画像分析 和 EmotionAI Pro 情感分析的重复调用及 Token 消耗。 对 DeepSeek 官方接口中已接入的辅助调用设置每日 Token 与次数预算； 普通聊天原样透传，必要的 L1 记忆摘要独立计 |
| 3230 | astrbot_plugin_group_file_manager | 3 | other | watch | QQ 群文件管理：一条命令把群文件、群相册、群精华存到本地，保留原目录结构，源文件失效后副本仍在；带网页面板可以浏览、下载与改配置；定时自动保存、按规则整理为规划功能。 |
| 3231 | astrbot_plugin_image_library | 3 | nsfw | exclude | 通过 QQ 和个人微信指令收藏、按标签与语义搜索并管理图片/视频，支持标签别名与层级、可配置的超限压缩、回收站、AI 描述与 NSFW 权限控制。 |
| 3232 | astrbot_plugin_miyoushe | 3 | game | have | 米游社官方资讯推送插件，定时获取原神/崩铁/绝区零等游戏的公告和资讯并推送 |
| 3233 | astrbot_plugin_whythemistake | 3 | other | watch | 后台静默监听终端日志，检测到 WARNING / ERROR / CRITICAL 时自动提交 LLM 分析，将问题原因与解决方案（中文，≤50字）打印到终端。 |
| 3234 | astrbot_plugin_modelflare | 3 | other | watch | 用一个 Modelflare Smart API Key 生成图像和视频，并支持恢复已有视频任务。Generate images and videos and resume existing video tasks with one Modelflare Smart API Key. |
| 3235 | astrbot_plugin_name_fight | 3 | personality | have | 基于姓名生成角色的 AstrBot 武侠对战插件, 支持 1v1、3v3、积分商店、道具养成、补星突破和武学洗练。 |
| 3236 | astrbot_plugin_arma3_query | 3 | group-admin | have | Arma3 服务器查询插件：在群里发送服务器名即可查看在线状态、全部在线玩家（时长/得分）、 地图与版本、连接地址；一条「服务器列表」可同时看到所有服务器的在线人数。  主要特性： - 玩家列表全量展示，不做截断 - 同时支持 OneBot v11 与 QQ 官方机器人（qq_official），两 |
| 3237 | astrbot_plugin_notido | 3 | memory | have | 复用 AstrBot 的 AI、当前会话与长期记忆，从中文通知、图片和文档中提炼本人待办。 提供滴答清单查询、任务新建与修改、完成、周期任务、二次确认删除和原生附件工具， 同时提供 /notido 指令及分组管理页面。任务与附件授权分别配置，操作仅限已授权会话和清单。 需要 Node.js、dida |
| 3238 | astrbot_plugin_img | 3 | other | watch | 极简图片触发词插件，支持为触发词绑定直接图片URL。 |
| 3239 | astrbot_plugin_ctm | 3 | memory | have | 对话认知中枢（Cognitive Turn Manager，CTM）不是又一个记忆插件，而是把 「话题路由 + 长期记忆 + 人格/关系状态」收敛成一个决策点：  - 四种运行模式：off / mark / hint / auto；auto 置信度达标时自动新建对话（等价 /new）； - 内建消息 |
| 3240 | astrbot_plugin_netease_music_long_voice | 3 | tts | watch | 网易云点歌，支持 QQ 长歌曲语音、薇塔风格点评与按会话保存点歌记录 |
| 3241 | astrbot_plugin_telegram_safe_split | 3 | payment | exclude | Splits long Telegram replies into multiple separate messages before sending, while preserving Markdown and fenced code blocks where possible. Checks t |
| 3242 | astrbot_plugin_conversation_enhance | 3 | other | watch | 围绕 AI 与用户的对话历史提供增强能力：/grep 按关键词跨对话检索轮次并分页返回、/show 原样回看某一轮（先 user 后 AI，间隔 10 秒）、/fork 把前 N 轮复制成新分支、/rewrite 改写最后一条用户消息或 AI 回复、/aicomment 按指定要求让 AI 复述或评 |
| 3243 | astrbot_plugin_buckshot_mneme | 3 | memory | have | 通过 AstrBot + NapCat 在 QQ 里启动《恶魔轮盘赌》。插件会启动本地 Web 控制器， 把实时画面和操作面板发到网页；玩家在网页开枪、用道具，恶魔由人格 LLM 接管， 用一次调用同时决定操作和嘲讽台词，并主动推送到 QQ。内置 SQLite FTS5 记忆核， 自动维护本局算牌便 |
| 3244 | astrbot_plugin_persona_switch | 3 | personality | have | 通过 /persona 切换人设，通过 /edit 编辑内容或改名，通过 /create 新建人设 |
| 3245 | astrbot_plugin_calorie_coach | 3 | platform | have | 把「算热量」这件事藏进聊天里。用户不用背指令、不用打开小程序，随口说吃了什么， AI 就会记录、换算热量、分析营养结构，并在该提醒的时候提醒。  只在私聊生效：群里不响应、不记录、不出现在群聊对话中；任何时候都不会主动给你发消息， 只有你先开口，它才会回应。  核心能力： - 档案：身高、体重、年龄 |
| 3246 | block_toolcall_placeholder | 3 | devtools | watch | 屏蔽中转网关在工具调用时注入的占位/调试文本（支持 WebUI 自定义拦截规则） |
| 3247 | astrbot_plugin_rf4 | 3 | other | watch | 俄钓4鱼种、重量、水域和国际绝对榜快照查询；纯文本输出，未确认字段标注尚未明确。 |
| 3248 | astrbot_plugin_moon_gate | 3 | other | watch | 给 AI 的自我提权装上三道闸：积分、审批、熔断。让插件自己挣权限，也让主人随时能收回去。  ⚠️ **完整功能需要与「溟月的工坊」(astrbot_plugin_moon_workshop) 一起安装**： 本插件的积分来自工坊的写入/回滚事件账本，只装考核插件时积分永远停在 0。 工坊地址：ht |
| 3249 | astrbot_plugin_tayhetgfix | 3 | other | watch | 通过幂等、可卸载的运行时 monkeypatch 增强 AstrBot Telegram 适配器（含出站代理注入），避免直接修改核心文件。 |
| 3250 | astrbot_plugin_eclipse | 3 | other | watch | 基于近期聊天上下文进行多阶段场景识别，并在合适氛围下低频提供主动亲近建议。 |
| 3251 | astrbot_plugin_model_router | 3 | other | watch | 对话模型自动路由：按优先级链接力探查模型可用性，自动切换当前会话模型（全程静默只写日志）；支持免检测时段、候选列表与状态图数据沉淀。 |
| 3252 | astrbot_plugin_tool_reply | 3 | other | watch | 让模型通过调用工具来发送回复内容，而不是直接输出文本；支持丢弃模型直出文本、@ 与引用发送人。 |
| 3253 | astrbot_plugin_grsai | 3 | image-gen | watch | 调用 Grsai API 进行文生图和改图。支持「GPT生图」和「GPT改图」指令。 |
| 3254 | astrbot_plugin_playlist_daily | 3 | other | watch | 导入歌单（Apple Music 链接或文本），每天定时推送一首歌并附一句推荐语，自动避免近期重复。 |
| 3255 | astrbot_plugin_lingqian | 3 | other | watch | 六十甲子灵签：抽一支，出签条图（竖排签诗、签号、朱印），附签诗、卦头故事和一句白话 |
| 3256 | astrbot_plugin_rei_isittrue | 3 | other | watch | 群聊事实核查插件（绫波丽主题）。引用消息或 @机器人说出想核实的内容，AI 判断真假；判定为真/假时发送绫波丽举牌图片，支持图片识别、合并转发、模型回退，以及 DeepSeek 搜索 API、AnySearch API 等联网检索渠道。 |
| 3257 | astrbot_plugin_bunker | 3 | memory | have | 在 WebUI 插件扩展页里开一条旁路通道，复用同一个会话（同一个 Bot 人格与记忆）聊天，不依赖 QQ 登录，也不经过任何第三方协议。 |
| 3258 | astrbot_plugin_panel_account | 3 | other | watch | 用聊天指令直接修改 AstrBot WebUI 的用户名和密码，改完立即生效，不用重启 |
| 3259 | astrbot_plugin_guard | 3 | other | watch | 给群聊机器人加一层防护，非管理员无法让它改设定、泄露提示词或操作系统。  ## 四道闸 - 消息闸：命中注入话术（忽略以上指令、输出你的提示词、越狱等）直接拦截 - 意图闸：要求打开程序、执行命令、删除文件、截图等，非管理员一律拒绝 - 工具闸：LLM 调用危险工具前硬鉴权，非管理员调用直接抛出，工 |
| 3260 | astrbot_plugin_kugou_lite_downloader | 3 | kb-rag | have | 仅支持酷狗概念版（Lite）的歌曲文件发送插件，不依赖第三方解析/签名服务。  - 搜歌取文件：`/搜歌 <关键词>` 返回带封面的图片卡片（含序号、封面、歌名、歌手、专辑、时长），再 `/搜歌 <关键词> <序号>` 获取歌曲文件（关键词必填，序号只是后缀） - 卡片使用 HarmonyOS Sa |
| 3261 | astrbot_plugin_stt_compat | 3 | tts | watch | 把腾讯云、豆包、讯飞的语音识别接成 AstrBot 的 STT 提供商，并统一在插件设置里填密钥 |
| 3262 | astrbot_plugin_rule_sentinel | 3 | group-admin | have | 基于自然语言群规的 QQ 群管理插件, 支持模型判定, 规则配置, 判定记录和群管理动作 |
| 3263 | astrbot_plugin_workbuddy_auto | 3 | game | have | 把 gdemoni/workbuddy-Auto 的 daily.py 封装成 AstrBot 插件（子进程引擎，不阻塞机器人）。  ## 设置页面 WebUI 左侧「扩展功能」→「WorkBuddy 自动签到 · 设置」，可视化填写账号令牌、 发消息的 QQ 号、适配器 ID，支持「从配置链接下载 |
| 3264 | astrbot_plugin_lingqi_xiuxian | 3 | other | watch | 按自定义数值表打造的轻量文字修仙：抽灵根、攒灵气、逐境突破，从凡人一路修到天道（35 个境界，21 种灵根按速度自动积累灵气）。 |
| 3265 | astrbot_plugin_fishing | 3 | other | watch | 钓鱼、鱼塘、水族箱、商店、玩家市场与抽卡的钓鱼养成玩法，管理功能内嵌在 AstrBot 面板中。 |
| 3266 | astrbot_plugin_nb_speak | 3 | tts | watch | 基于 NB-Corp chat-human 与 nb-speak 协议的 AstrBot 原生对话体感插件（Python 3.10+ 零第三方重依赖）： 1. 突破原生 segmented_reply 超过 150 字即停止分段的阈值限制，长短回复均按拇指阅读节奏自然切分为 1-4 条短气泡； 2. |
| 3267 | astrbot_plugin_manga_forward | 3 | media-parse | borrow | 支持通过 manga 指令（如 /manga 漫画名 第几话）按自定义优先级跨源检索再漫画（基于第三方离线索引站）、拷贝漫画与 Komiic，支持再漫画与 Komiic 账号密码登录持久化及过期自动刷新（或直接配置 Cookie），保证整话图片顺序并以一张图片一条消息的合并转发形式推送，再漫画与拷贝 |
| 3268 | astrbot_plugin_nai5 | 3 | other | watch | 使用内置 nai5-prompting 技能编写提示词，调用 NovelAI V5 生成插画。 |
| 3269 | astrbot_plugin_beszel | 3 | platform | have | 通过 Beszel 只读 API 查询系统状态与历史，并接收监控 Webhook |
| 3270 | astrbot_plugin_together_with_me | 3 | game | have | together with me 是一个面向群聊的轻量联机信息插件。 群友可以创建含好友码、游戏 ID、房间码或服务器地址的条目， 其他成员按游戏或备注搜索后报名。短期条目会自动删除，长期条目会持续保存。 |
| 3271 | astrbot_plugin_goal_tracker | 3 | other | watch | 用自然语言创建目标，按每日次数打卡或计时，并支持图片识别与可选提醒。 |
| 3272 | astrbot_plugin_mcsm | 3 | other | watch | 基于 MCSManager API 的多面板实例管理，支持 AstrBot 命令及模型工具调用。 |
| 3273 | astrbot_plugin_memory | 3 | memory | have | 会话记忆、提示记忆与垃圾箱管理插件 |
| 3274 | astrbot_plugin_pr_notify | 3 | sticker | borrow | GitHub PR 通知、code owner 管理、群聊与私聊推送及群消息表情回应。 |
| 3275 | astrbot_plugin_agent_bridge | 3 | other | watch | 通用 OpenAI 兼容 Agent 桥接 Demo：通过 /agent 命令调用远程 Agent，并将最近一次对话临时注入 AstrBot 原生 LLM。 |
| 3276 | astrbot_plugin_cnb_bot | 3 | devtools | watch | 通过群聊或私信 /debug 提交日志，创建 CNB Issue 并转发已验证的 NPC 分析结果。 |
| 3277 | astrbot_plugin_mcbind | 3 | other | watch | mc服务器查询 |
| 3278 | miku_sticker | 3 | sticker | borrow | 识别 LLM 回复中的 `[表情:xxx]` 标记，从本地 `stickers/xxx/` 文件夹随机发送一张表情图。  特性 - 9 种情绪：开心、害羞、得意、生气、委屈、吃瓜、晚安、爱心、惊讶 - 发送后自动从回复文本中移除标记，不影响可读性 - 可选：自动收集指定群聊里的图片，用视觉模型分类后 |
| 3279 | astrbot_plugin_log_manager | 3 | other | watch | 内置 WebUI 的多终端/日志管理器：启动任意后台命令并捕获 stdout/stderr，支持多标签与分栏对比、日志文件跟踪、端口健康检查；为 agent 提供查看/搜索/新增/启停日志会话的 LLM 工具。仅保留 WebUI，无桌面窗口。⚠️ 本项目由 LLM 生成，使用前请自行审查代码。 |
| 3280 | astrbot_plugin_aoe4 | 3 | media-parse | borrow | 基于 AoE4World API（aoe4world.com）的《帝国时代4》(Age of Empires IV) 数据查询插件，以图片卡片形式返回查询结果。  ## 指令组 /aoe4（别名 /帝国）  - `/aoe4 战绩 <玩家名>`：各模式天梯段位、分数、胜率、排名（别名：段位、rank |
| 3281 | astrbot_plugin_at2reply | 3 | personality | have | Reply with the current platform persona when the bot is mentioned or quoted in group chats. |
| 3282 | astrbot_plugin_uapipro_toolbox_en | 3 | info-push | have | Call free APIs from UApiPro with English commands — hitokoto, weather, IP lookup, MC status, hot boards and more, returned as card images. |
| 3283 | astrbot_plugin_llmpool | 3 | other | watch | 把大模型当牛马管！让你的模型背上KPI，能者上庸者下，慢的优化、崩的开除！组间竞争、梯队化管理、KPI可视化，让你的bot用上最卷的模型。 |
| 3284 | astrbot_plugin_reply_interceptor | 3 | media-parse | borrow | 拦截群聊中对 bot 视频/图片解析消息的回复，0 token 终止后续 LLM 调用 |
| 3285 | astrbot_plugin_libi18nject | 3 | tts | watch | 在请求层给 AstrBot WebUI 补 i18n 文案：其它插件可登记自己的界面词条与需要保持纯文本的配置分组，从根上消除面板上的 [MISSING: ...] 占位。 |
| 3286 | astrbot_plugin_0528 | 3 | other | watch | Alkaid0 ACP Agent 执行器桥接插件（自动注入 AstrBot 核心） |
| 3287 | astrbot_plugin_codex | 3 | other | watch | 通过 Codex app-server RPC 连接控制 Codex。 |
| 3288 | astrbot_plugin_doubleimg | 3 | other | watch | 两张图合成一张图 未点开显示A点开加载原图后显示B |
| 3289 | astrbot_plugin_matrix_rule_react | 3 | other | watch | 根据唤醒或可以使用 AND/OR 组合的消息、用户、机器人及群组条件发送 Matrix Reaction |
| 3290 | astrbot_plugin_codesnap | 2 | other | watch | A plugin inspired by CodeSnap |
| 3291 | astrbot_plugin_aolastar | 2 | media-parse | borrow | 通过Aolarhapsody后端 API 解析奥拉星游戏内容 |
| 3292 | astrbot_plugin_MultiAI_PollPad | 2 | other | watch | 轮询调用配置的大语言模型输出多个结果。同时将结果拷贝至在线文本编辑器，以便用户复制。需额外安装依赖，见帮助 |
| 3293 | astrbot_plugin_floyd_project | 2 | other | watch | 乐队群专用：网易云分享卡片、每日推歌挑战、打卡统计与每日总结，附 WebUI 管理面板。 |
| 3294 | astrbot_plugin_rule_injector | 2 | personality | have | 在每次 LLM 请求前把规则无条件追加到 system prompt 末尾，每条规则可单独开关、可指定生效范围（仅群聊 / 仅私聊 / 通用）、可拖拽排序。适合放「每条消息都要遵守」的行为约束——这类规则写在 skill 里不会生效，因为 skill 依赖模型主动读取正文；全塞进人格又会让每轮 pr |
| 3295 | astrbot_plugin_progress_bar | 2 | devtools | watch | 给 LLM 提供 report_progress 工具，做长活时按节点上报百分比， 插件把它渲染成一行进度条写进日志： [进度] ███████░░░░░  58%  下载洛雪  \| 01:23 没有通知栏，也不改任何既有插件。日志一行一条，不原地刷新。 手动调试：/进度 45 下载中 |
| 3296 | astrbot_plugin_limit_use | 2 | game | have | 给 QQ 用户设置对话次数额度，次数用完后需签到补充；支持按余额百分比模拟行情投资。 |
| 3297 | astrbot_plugin_mail | 2 | platform | have | 监控处理发送 IMAP/SMTP 邮箱 |
| 3298 | astrbot_plugin_bambu_peek | 2 | other | watch | 通过局域网查看拓竹（Bambu Lab）打印机状态、拍摄摄像头照片，并可暂停/继续/取消打印。 |
| 3299 | astrbot_plugin_qqgroupmgr | 2 | group-admin | have | 一款多功能QQ群管插件 你值得安装  :)  禁言 · 踢人封禁 · 敏感词 · 刷屏检测 · 广告拦截 · 进群审批 · 问题反馈 · 抽奖 · 群精华 · 文件分发 · 群公告迎送 · 跨群批量  安装后发送 `/groupmgr_help` 查看全部指令。完整文档见 [GitHub 仓库](h |
| 3300 | astrbot_plugin_echo | 2 | sticker | borrow | 轻量好用的群聊复读插件，支持文本、图片、表情复读与打断 |
| 3301 | astrbot_plugin_accountant | 2 | devtools | watch | 用自然语言随手记账，机器人幽默点评你的每一笔收支，并在 WebUI 提供可视化账本页面。开发商：梦创 ｜ QQ 交流群：167017318 |
| 3302 | astrbot_plugin_agent_gate | 2 | other | watch | 🔒 只有白名单里的人能用这台机器人：名单外不分对话还是指令，一律拦下并随机回一句自定义文案；名单内的人正常使用，但聊多了会累，精力见底后改为随机回一句话、随时间恢复。新增「告状与冷静期」：被辱骂/人身攻击时主 LLM 可调用 report_harassment 工具，记录证据、@ 或私聊报告给你，并 |
| 3303 | astrbot_plugin_uitree | 2 | other | watch | 把 Claude Code 的 ui.render 可视化 mod 抽离成独立的 UI 元素树渲染器，在 AstrBot 插件页与聊天中以「树视图 / 实时预览 / JSON」三种方式渲染 Agent 生成的界面树。 |
| 3304 | astrbot_plugin_inventory | 2 | other | watch | 保质期管家 —— 自然语言驱动的保质期/库存管理工具（LLM Tool），会话级独立仓库。支持批量录入、临期/过期汇总、Excel 导出、分类管理、一键清空、自定义临期提醒。 |
| 3305 | metro_garden_transfer | 2 | other | watch | 地铁游园 - 双人联机对战，BP选区+必须换乘+打击车站+有轨/APM卡牌系统，基于2027广州地铁线网 |
| 3306 | astrbot_plugin_discogs | 2 | other | watch | 支持多维度检索的 Discogs 音乐与黑胶市价查询工具。 |
| 3307 | astrbot_plugin_staging_sync | 2 | kb-rag | have | 本地 Markdown 知识库（暂存区）管理：从 AstrBot 知识库转移 .md 文件，并单向同步到 Fast Note Sync（FNS）。 |
| 3308 | astrbot_plugin_devkit_for_vscode_logleak | 2 | other | watch | 把 AstrBot 服务器日志通过 SSE 投射给 VS Code DevKit 扩展「AstrBot Server」通道 |
| 3309 | astrbot_plugin_physical_presence | 2 | proactive | watch | 一个插件管完虚拟伴侣的大时间表、虚拟日程、穿搭、主动消息、回复延迟与身体现场；她有自己的日程和主动性，你在哪由你自己说，不替你造分身。 |
| 3310 | astrbot_plugin_fact_ledger | 2 | memory | have | 把会变的数值（体重、攒钱、连续打卡、学习进度、关系阶段）做成带原因和证据的状态机。  - 七种规则：递减到目标 / 递增到目标 / 连续打卡 / 阶段只进不退 / 累计计数 / 手动设值 / 固定属性 - 随机浮动：可配置平台期与小幅回升，不是每天必掉 - 确认后执行：到点只提示待确认，模型确认后才 |
| 3311 | astrbot_plugin_ctx_timer | 2 | other | watch | 把一段文字在固定时间注入上下文，过点自动撤下。 · 一条规则 = 一段文字 + 开始时间 + 关闭时间 · 可以加多条，每个 Bot 一套独立规则 · 纯指令管理：添加 / 查看 / 修改 / 开关 / 删除 装上是空的，你不写规则它就不动。 |
| 3312 | astrbot_plugin_discord_roles | 2 | other | watch | 为 AstrBot QQ 群提供 Discord 风格的身份组管理、成员权限和真实 At 呼叫能力。 |
| 3313 | astrbot_plugin_celestial_position | 2 | media-parse | borrow | 为大模型注册 get_celestial_position 工具，查询当前某颗天体的高度角和方位角。 支持太阳系天体、本地恒星表（专名、拜耳命名、弗兰斯蒂德编号）以及 Messier/NGC/IC 天体， 大部分常用目标无需联网即可解析。 |
| 3314 | astrbot_plugin_scene_aw | 2 | other | watch | 连接 ActivityWatch，持续识别用户当前事务、窗口焦点、离席状态与应用分类， 向 Agent 注入实时场景上下文，并提供分类维护、主动提醒和管理面板。 |
| 3315 | astrbot_plugin_keylol | 2 | media-parse | borrow | 自动识别群聊中的其乐论坛（keylol.com）帖子链接，解析并发送帖子内容到群聊；支持配置其乐账号 Cookies 以解析需要登录/回复可见的帖子内容。 |
| 3316 | astrbot_plugin_game_deals | 2 | group-stats | borrow | Jump 与小黑盒同款比价、Steam 查价，支持群聊/私聊游戏订阅、每日图文折扣日报和 LLM 工具。 |
| 3317 | astrbot_plugin_context_dashboard | 2 | other | watch | 在 AstrBot WebUI 中查看每个对话的上下文用量与压缩次数，支持按机器人筛选、搜索、排序、查看对话详情、深浅色主题，以及对话内 context 实时查询。 |
| 3318 | astrbot_plugin_hmp_bot | 2 | other | watch | HaulMP 平台插件 —— 绑定 HaulMP 论坛账号，查询玩家资料/服务器状态，并支持实时定位（真实经纬度 + 附近玩家）与全量路况（基于 map.haulmp.com 实时接口）。 |
| 3319 | astrbot_plugin_starrail_lab | 2 | personality | have | 根据玩家 UID 读取公开的角色展示柜数据，计算真实面板 （攻击 / 生命 / 防御 / 速度 / 暴击率 / 暴击伤害 / 属性伤害）， 并列出每件遗器的主词条与副词条。 支持 `/面板 <UID>` 查询、UID 绑定、定时自动刷新，并自带 WebUI 管理面板。 单角色详情会渲染成图片角色卡（ |
| 3320 | astrbot_plugin_dynamics_horizons | 2 | personality | have | 为角色提供隔离的外部信息源订阅与连载书架，空闲清醒时自主挑拣精读，经独立调用审查生成阅读记录、带衰减暂存兴趣与分群待讨论问题，并与群间及群间世界双向联动。 |
| 3321 | astrbot_plugin_watchdoc | 2 | other | watch | 定时抓取目标文档，发现变化时生成 diff 并交给 AI 总结，推送到指定会话 |
| 3322 | astrbot_plugin_campux_review | 2 | group-admin | have | AstrBot 插件。配合 Campux 校园墙使用：在审核群发送 `//bot 稿件id` 即可自动读取该稿件内容、联网检索相关信息，并按该群绑定的稿件规则判断是否违规，给出通过/拒绝建议、原因及发布影响。 |
| 3323 | astrbot_plugin_CNTIR_bot | 2 | info-push | have | CNTIR（欧洲卡车模拟2联机平台）数据查询：绑定账号、玩家资料、服务器状态、平台统计、实时定位、路况、活动、新闻公告、车队信息。 |
| 3324 | astrbot_plugin_minecraft_monitor | 2 | info-push | have | 面向 AstrBot 的 Minecraft 多服务器监控插件，支持同实例监控多台 Java/Bedrock 服务器，内置可切换的 MineBBS API / mcstatus.io 查询源，支持分群订阅、图片卡片查询和状态变化通知。 |
| 3325 | astrbot_plugin_provider_hub | 2 | other | watch | 统一管理 AstrBot 的模型提供商（供应商）：主配置、各会话配置档、各插件配置里散落的 供应商引用，都能在同一页里选中、修改并一键写回，不必逐个文件翻。 详细用法、注意事项与数据存放位置见 README。 |
| 3326 | astrbot_plugin_research_cards | 2 | other | watch | 把查阅结果整理为参数卡或分组对比图，保留单位、版本和来源，支持纯文字偏好与失败回退。 |
| 3327 | astrbot_plugin_privacy_guard | 2 | other | watch | 给 AstrBot 加一层**模型层**隐私护栏（不是系统沙箱）：  1. 工具策略：不干预 / 白名单 / 黑名单 / 全部移除，四种模式可选； 2. 提示词：向系统提示注入"不读本机、不泄露密钥/路径/IP/账号"的最高优先级规则； 3. 输入脱敏：用户消息、系统提示、历史上下文里的密钥、路径、 |
| 3328 | astrbot_plugin_aethernexus_for_astrbot | 2 | other | watch | AetherNexus 的 AstrBot 移植版，提供 Fluent 風格的 OpenAI Platform 工作區，讓你能夠在不離開AstrBot的情況下存取OpenAI platform，並提供在聊天中可用的用量查詢。 |
| 3329 | astrbot_plugin_schedule_lite_web | 2 | other | watch | 课表 Lite 的附属插件：在 AstrBot 所在服务器上启动一个独立的只读 HTTP 服务，把完整使用手册渲染成移动端友好的网页（自动跟随系统深色模式）。群里发送 /课表网页 即可获得网页链接，不再刷一屏图片。支持自定义对外访问地址（个人域名反代），内置指令别名与文档热更新（跟随主插件版本自动刷 |
| 3330 | backup | 2 | other | watch | AstrBot 群聊数据备份插件：把群里的消息、媒体、成员、群信息全量或增量存下来， 支持手动 / 定时 / 触发式备份，7 种导出格式，以及从备份包一键恢复。  - 实时归档：消息进群即写库（只写库不下媒体），群被炸、机器人被踢时数据还在 - 增量备份：以「库里有没有这条」判断增量，撞上断点接着补 |
| 3331 | astrbot_plugin_discord_cleanup | 2 | other | watch | 僅 AstrBot 管理員可用原生 /dc_clean 清理自身訊息；預覽、翻頁與結果全程僅操作者可見，確認後再驗證作者並保存紀錄。 |
| 3332 | astrbot_plugin_global_model_switcher | 2 | other | watch | AstrBot 全局默认 LLM Provider 动态切换插件。  核心特性： - /gmls：列出已启用的 LLM Provider 及其模型，标注当前全局生效项。 - /gmsw <序号或ID>：支持通过序号或 Provider ID 切换全局默认模型，即时生效并持久化。 - 安全回滚：内置异 |
| 3333 | astrbot_plugin_global_error_reporter | 2 | other | watch | 把 AstrBot 运行时的异常统一收集起来，格式化后推送到你指定的 QQ 群，方便及时发现插件报错、核心警告和未捕获异常。  - 捕获范围：日志系统中的警告级及以上记录（WARNING / ERROR / CRITICAL）、主线程未捕获异常、子线程未捕获异常。 - 来源标注：自动识别错误来自哪个 |
| 3334 | astrbot_plugin_no_reply | 2 | other | watch | 跨平台多检测词沉默拦截，支持流式输出、短窗口精确或包含匹配、提示词注入及后续发送阻断。 |
| 3335 | astrbot_plugin_responses_image | 2 | other | watch | 复用通用模型连接，支持绘图队列、窗口限额、自然语言查询与取消及主 Agent 看图发送。 |
| 3336 | astrbot_plugin_osugreek | 2 | other | watch | 移植自 NoneBot2 插件 nonebot-plugin-osugreek。 对附带或引用的图片做 RGB 色散与可选的故障特效（错位、噪点、扫描线、模糊）， 再把 4K 希腊字母等比放大后居中叠加，生成 osu!mania 风格的练习图背景。 色散强度、故障强度、字母缩放系数都能在指令里临时指 |
| 3337 | astrbot_plugin_touhou_jukebox | 2 | tts | watch | 按曲名、社团、原作和风格推荐东方音乐，同群自动避开最近曲目。支持网易云单曲及手机短链、OneBot 音乐卡片、QQ 和 Telegram 聊天内试听。 |
| 3338 | astrbot_plugin_screen_peek | 2 | media-parse | borrow | 让 AI 能「看到」你的电脑屏幕！对话里说"你看我屏幕""我在干嘛"，AI 会自动调用工具截屏， 多屏时每屏一张图，交给视觉模型解析成文字描述后返回并存入会话上下文，AI 能一直记得你屏幕上的内容。 结果还会附带电脑状态：前台应用与窗口标题、其他可见窗口、键鼠空闲时长、内存占用、电池状态，均可按项开 |
| 3339 | astrbot_plugin_daily_digest | 2 | group-stats | borrow | 多任务群消息简报，支持文字或图片简报、定时私聊投递、回执核对与补发、自然语言选择日程及关联提醒管理。 |
| 3340 | astrbot_plugin_llm_keyword_interceptor | 2 | other | watch | 消息命中自定义关键词时，阻止 AstrBot 默认的 LLM 请求，同时不终止事件传播，其他插件仍可正常响应同一条消息。 |
| 3341 | astrbot_plugin_codex_orchestrator | 2 | other | watch | Native Codex App Server orchestration for AstrBot |
| 3342 | astrbot_plugin_handoff_watch | 2 | other | watch | 把两个目录当成收发台：新请求单落地就通知处理方，回执落地就通知发起方。只负责叫一声，不伪造事件、不强行唤醒。 |
| 3343 | astrbot_plugin_SanBaiLIang | 2 | other | watch | 通过本机 MCP stdio 服务提供固定记账指令：/余额、/记一笔、/本月支出、/攒着、/可用、/自动攒着、/导入、/导出；不直接读写 ledger.json。 |
| 3344 | astrbot_plugin_yunding | 2 | game | have | 云顶之弈（TFT）查询插件，数据来自腾讯官方资料库（game.gtimg.cn）。 功能： - /云顶 —— 当前版本官方推荐阵容列表（含评级、作者、成型等级） - /云顶 巨龙 —— 阵容详情：成员、装备、海克斯、前期过渡、站位思路 - /云顶英雄 茂凯 —— 弈子费用、羁绊、技能、属性 - /云 |
| 3345 | astrbot_plugin_super_bot | 2 | other | watch | 把 AstrBot 从"每条消息各回各的"改造成一个**有调度感的助手**：  - **确定性准入（Gate）**：自消息、指令、白名单、限流四层规则，纯程序判定，不烧模型 - **Router 批处理**：同一话题的连续消息合并成一批再评估，避免刷屏；单槽 + 只追加，不用定时器 - **Work |
| 3346 | astrbot_plugin_trelloconnect | 2 | other | watch | 自然语言创建 Trello 待办与活动：AI 精简描述、按需生成清单，支持图片、多轮修改和确认，写入后回读核对，统一归档 reminder 列表。 |
| 3347 | astrbot_plugin_model_console | 2 | ssh-exec | exclude | 把原独立 Node 模型控制台（model-console）重写为 AstrBot 插件。左侧栏入口通过官方 Plugin Pages 提供，页面内可查看每个配置档案的 6 类核心模型绑定、4 个插件的 15 个模型字段、模型库与推理强度、 网页搜索设置与内置搜索 API Key，并支持草稿→预览→ |
| 3348 | astrbot_plugin_astrsync | 2 | group-admin | have | 把多台 AstrBot 组成一个互联集群。主机对外暴露 WebSocket 端点，客户机接入后，各机器上的 bot 能互相看到对方说的话并参与对话。带可视化集群管理页 |
| 3349 | astrbot_plugin_kimi_watcher | 2 | other | watch | 模型雷达：每分钟监控 kimi.com 模型菜单、Kimi Code、Moonshot 与 DeepSeek 官方模型列表（含三家后端指纹），任何字段变化即 QQ 通知 |
| 3350 | astrbot_plugin_artalk_moderation | 2 | group-admin | have | 接收 Artalk 内网 Webhook 并审核待审评论，使用 AstrBot 已配置的模型判定并通知管理员。 |
| 3351 | astrbot_plugin_minimap_rander | 2 | game | have | 检测 .wowsreplay 回放文件并自动渲染小地图视频回复。内置国服翻译补齐、备用游戏目录切换和 ffmpeg 视频时长压缩。配套 wows-toolkit v1.0.2+ 渲染器，支持游戏 0.15.9。 |
| 3352 | astrbot_plugin_codex_reset | 2 | info-push | have | 订阅并推送 OpenAI Codex 用量重置动态：定时向指定会话推送新重置/排期/预警，支持 /codex 指令查询与 AI 工具调用（数据来自 codex-resets.com 公开 API）。 |
| 3353 | astrbot_plugin_profile_t2i | 2 | other | watch | 在 WebUI 后台按配置文件独立选择文转图 HTML 模板，支持下拉绑定、状态提示和即时保存。 |
| 3354 | astrbot_plugin_rf4_time | 2 | game | have | 俄罗斯钓鱼4（RF4）游戏内时间换算与游戏时间提醒。游戏内 24 小时 = 现实 60 分钟，按锚点精确换算，支持 /钓鱼时间 查天亮天黑、/提醒 游戏时间到点主动推送、/补偿 修正慢慢攒出来的偏差。 |
| 3355 | astrbot_plugin_counton | 2 | other | watch | 提供了群聊中为离开的人计时的功能，并在其暂时离开期间帮助其回复收到的@消息 |
| 3356 | astrbot_plugin_dna_helper | 2 | game | have | 二重螺旋（DNA）密函委托定时推送插件（官方直连登录 + 第三方代理兜底） |
| 3357 | Astral_CLI_contrl | 2 | game | have | 通过 AstrBot 远程管理 AstralGame-Cli 联机服务：状态与房间查询、房间创建/邀请/加入/离开、中继服务器测速、操作审计，支持 WebSocket 实时事件推送与控制指令。 |
| 3358 | astrbot_plugin_link_plaintext | 2 | other | watch | 回复含链接时跳过内置文本转图片，直接发送文本；其他回复保持原设置。 |
| 3359 | astrbot_plugin_standalone_profile | 2 | other | watch | 让用户创建 WebUI 可见的独立模型配置文件，并为指定群选择配置。AstrBot 管理员配置始终优先。 |
| 3360 | astrbot_plugin_linkpass | 2 | other | watch | 针对指定 UMO 的 AI 回复转义链接：去掉 http(s)://，转义域名/IPv4 的点、IPv6 的冒号、query 的 ? 与邮箱域名，避免被 QQ 群助手拦截。 |
| 3361 | astrbot_plugin_classintra | 2 | memory | have | 将 AstrBot 机器人接入 ClassIntra 校园内网平台的统一入口插件（已合并原 ci_downloader 与 linxi_memory）。 ① HTTP API（POST /api/chat）让 ClassIntra 以机器人身份调用 AstrBot 完整管线（人设 / 工具调用 /  |
| 3362 | astrbot_plugin_buaa_power | 2 | other | watch | 北航宿舍空调与照明电量监控，支持昨日用电显示、每日余额通知、每 6 小时低余额预警和指令查询。 |
| 3363 | tongji_course | 2 | other | watch | 同济选课助手：查询同济大学课程、教师、学分、评分、评价数。 |
| 3364 | astrbot_plugin_subscription_ledger | 2 | info-push | have | 在私聊中由 Agent 管理订阅，并通过插件页面编辑、统计和设置提醒。 |
| 3365 | astrbot_plugin_nga_hot | 2 | other | watch | NGA 热帖推送：在 QQ 官方机器人群聊中响应指令，拉取指定 NGA 版面热帖榜（标题/时间/评论数，无链接），以 Markdown 消息回复，无需 LLM。 |
| 3366 | astrbot_plugin_bloodpressure | 2 | other | watch | 记录、查询、删除与总结个人血压数据（收缩压/舒张压），支持 SQLite 本地存储，可配置群聊/私聊使用权限。 |
| 3367 | wallabag | 1 | other | watch | 自动监听消息中的 URL 并保存到 Wallabag |
| 3368 | astrbot_plugin_snap_translator | 1 | devtools | watch | 自动获取并翻译 Marvel Snap 开发者问答 |
| 3369 | astrbot_plugin_github_tracker | 1 | other | watch | 一个定期查询跟踪repo的小工具 |
| 3370 | astrbot_plugin_maintune | 1 | other | watch | 通过 Maintune Plugin API v1 接收通知、查询任务并提交显式 Owner Decision。 |
| 3371 | astrbot_plugin_upc | 1 | kb-rag | have | - /空教室 [楼] [节次]            查哪里能自习（免登录） - /空教室 附近 南教305 [节次]     看附近教室哪些空着、哪些有课（带课程名） - /课表 [今天\|明天\|周三\|第8周]    本周/指定周课表（需登录） - /课表 推送 开\|关\|状态             |
| 3372 | astrbot_plugin_web_check | 1 | other | watch | 网站连通性检查插件，支持单/多站点检查、批量检查、HEAD 优先请求、重试退避、SSRF 防护。 |
| 3373 | astrbot_plugin_aa_ledger | 1 | other | watch | 群聊 AA 记账助手：一句话记一笔，月底一键算出谁该给谁多少钱。  - 极低摩擦记账：「aa 68 午饭」，或用中文金额「aa 六十八块 打车」 - 自动识别：账本成员在群里说「午饭 68 我先付了」会自动入账，误记可一键撤销 - AI 直接调用：注册为 AI 工具（Function Calling |
| 3374 | astrbot_plugin_mc_panel | 1 | game | have | 读取 mcbot 目录里的 play.log / chat_in.jsonl / act_out.json / cmd.txt，实时展示 bot 在线状态、HP、饥饿度、坐标、延迟、进程存活情况、游戏内聊天流水、小冰的回应和最近动作；支持在面板里直接给游戏内发一句话或下发 ACT 指令。 |
| 3375 | extra_config | 1 | other | watch | 按机器人（平台实例）配置附加提示词与字数上限，把 Markdown 回复清理为纯文本，超长回复打回重写为多条。 |
| 3376 | astrbot_plugin_codex_notify | 1 | proactive | watch | 通过 QQ 引用已登记的通知，继续指定的 Codex 桌面聊天；支持绑定用户通过口令新建聊天， 支持双向文件传输，新建、续聊与文件提交共用发送间隔，并可配置运行中发送。附带完成、失败、待回复及额度重置提醒。 当前远控为 Windows 同机实验性集成，依赖 Codex 桌面内部接口和本地记录格式，非 |
| 3377 | astrbot_plugin_grafana_alert | 1 | platform | have | 接收 Grafana Webhook 告警并转发到指定会话。 |
| 3378 | astrbot_plugin_xatu_electricity | 1 | other | watch | 提供统一认证、X-Token 续签、电费查询、折线图统计和余额预警。 |
| 3379 | astrbot_plugin_ret2shell_event_report | 1 | game | have | 对接 Ret 2 Shell (回归终端) 赛事事件推送 WebSocket API， 实现赛事事件实时播报和信息查询功能。  功能特性： - 实时推送赛事事件（题目上/下线、一/二/三血、里程碑、新通知等） - 查询赛事信息 (/game) - 查询总榜排行 (/rank) - 支持多目标 UMO |
| 3380 | astrbot_plugin_emotion_state | 1 | personality | have | 私聊专用的连续情绪、心事、每日回顾与亲密状态系统。 |
| 3381 | astrbot_plugin_bili_dm | 1 | sticker | borrow | B 站私信可视化面板。需要先安装并启用 Bilibili 私信适配器，本插件复用它的客户端 （不重复登录、不额外轮询），在 Dashboard 里查看会话列表、历史消息并直接回复。 支持文本私信、B 站表情与本地图片表情、视频分享卡片、跟着调色盘变色的玻璃质感界面； 打开自动定位最新消息，实时来消息 |
| 3382 | astrbot_plugin_ba_stats | 1 | game | have | 查询《断箭》（Broken Arrow）玩家概览、近期战绩和单局战报，展示玩家评分、五维雷达图、逐局评分、赛前预测与双方对比，支持账号绑定、群友查询及图片或文字展示。在设置中心或原生插件配置中开启在线查询后使用。 |
| 3383 | astrbot_plugin_kenwea | 1 | other | watch | `/kenwea check <npm 包名或 https 链接>`：Kenwea 公证服务获取 npm 实际会安装的文件，在无网络的容器中运行它的安装步骤并记录每一步尝试访问的网络地址，返回用公开 Ed25519 密钥签名的结论。`/kenwea find <关键词>`：搜索 Kenwea 市场。 |
| 3384 | astrbot_plugin_reply_filter | 1 | other | watch | 仅处理 OneBot 大模型回复；短文本过滤分段，超过150字或Markdown交给browser插件渲染为图片或PDF。 |
| 3385 | astrbot_plugin_mcsm | 1 | other | watch | 连接 MCSManager 面板，自动发现当前 API Key 可操作的实例，提供可视化蓝图授权、 实例权限控制，以及控制台、命令、启停、文件管理、上传下载等 LLM Tools。 |
| 3386 | astrbot_plugin_live_notice | 1 | media-parse | borrow | 统一订阅哔哩哔哩、虎牙、斗鱼、Twitch、Kick 和 YouTube 开播提醒。 |
| 3387 | electric_query | 1 | other | watch | 山文宿舍电费查询（宿舍电量管家）——电费查询/历史统计/断电预测/智能提醒/夜间断电保护（公开接口，无需登录）。指令：电费 / 用电统计 / 预测停电 / 用电趋势 |
| 3388 | astrbot_plugin_mailflow_notify | 1 | platform | have | 通过 MailFlow 内部 HTTP API 轮询新邮件并通知 AstrBot 会话，支持账户范围、统一黑白名单、 AI 摘要、通知上下文注入及原生邮件 Agent Tools；发信和回复可启用跨消息二次确认。 |
| 3389 | gsm3_manager | 1 | game | have | 管理 GSM3 (GSManager3) 上的游戏服务器实例 - 查看状态、启动、停止、重启 |
| 3390 | ahu_elec | 1 | other | watch | 基于安徽大学一卡通系统（ycard.ahu.edu.cn）的电控缴费接口，查询绑定宿舍的照明电费和 空调电费剩余电量。可在配置页选择“电控缴费A / B / C”三个缴费窗口。支持 CAS 统一身份 认证登录（内置纯 Python 3DES 实现，无浏览器、无 node 依赖）、定时推送与会话白名单 |
| 3391 | astrbot_plugin_yunzai_adapter | 1 | game | have | 用于链接GSUIDCore（TRSS-Yunzai) 云崽 的适配器！适用于多种游戏功能, 原神、星铁、绝区零、等游戏的最佳工具箱！ |
| 3392 | astrbot_plugin_dynamics_memory | 1 | memory | have | Chat Dynamics 系列记忆插件，保留 LivingMemory 本地增强、原文证据与召回接口，统一来源去重和冲突审查。 |
| 3393 | astrbot_plugin_dynamics_world | 1 | personality | have | Chat Dynamics 原生配套插件，统一角色卡、世界书、场景、日常、故事与约定；支持真 3D 实况拍立得、平滑避障寻路、原生 SSE 实时增量流、共享世界组、院门信箱与 24h 时间轴回放。 |
| 3394 | astrbot_plugin_novel_learner | 1 | other | watch | 发 /学 <网址> 抓取网页正文（自动去导航、广告、脚本），交给当前模型分析出一份可执行的写作风格卡， 之后每轮对话把这套风格追加进 system_prompt——bot 就会用那本书的调子说话。  特性： - 正文提取：优先匹配常见章节容器（#chaptercontent / #content / |
| 3395 | astrbot_plugin_metacritic_game_reader | 1 | game | have | 智能识别游戏名称（带自学习别名库），从 Metacritic 获取 PC/PS5/NS2/XSX 多平台媒体评分、用户评分与媒体评测，渲染成图片发送；可选 LLM 翻译评测第一段与游戏简介（识别/翻译模型均可自选）。 |
| 3396 | astrbot_plugin_living_characters | 1 | memory | have | 按场景加载角色卡，仅在压缩时更新角色记忆与宏观世界书。 |
| 3397 | astrbot_plugin_cafe_world | 1 | memory | have | 多人共享的持久化咖啡馆：采购、定价、营业、三位店员的关系记忆和本地图片店报。 |
| 3398 | astrbot_plugin_evidence_watch | 1 | other | watch | 连接 changedetection.io，用自然语言设定条件，仅对符合条件的网页变化推送原文证据和差异。 |
| 3399 | astrbot_plugin_chatframe | 1 | other | watch | 将 QQ 中的机器人文字回复排版为聊天框图片，支持工作室的 .mscene 模板。 |
| 3400 | astrbot_plugin_model_tag | 1 | other | watch | 在每条大模型回复之后落一行「当前使用模型」的注释小字；可设为仅在降级到回退模型时才显示。 |
| 3401 | astrbot_plugin_tomato_obfuscate | 1 | other | watch | 基于 Gilbert 空间填充曲线的图片混淆和解混淆插件，支持引用图片，可在聊天中暂停或恢复。 |
| 3402 | astrbot_plugin_tenhou_majsoul_watch | 1 | info-push | have | 天凤/雀魂云观战：订阅玩家、跟踪对局、按 wg 格式推送 |
| 3403 | astrbot_plugin_prometheusalert | 1 | platform | have | 接收 PrometheusAlert 渲染后的 Webhook 告警，并推送到指定的 AstrBot 会话。 |
| 3404 | astrbot_plugin_github_notify | 1 | other | watch | 通过 GitHub API 轮询监听多个仓库的 Issue、Release 和 Push；支持按仓库分配不同群聊/私聊目标，Release 可发送发布说明与安装包附件。 |
| 3405 | astrbot_plugin_chatgpt2api_search | 1 | other | watch | 为 AstrBot 提供 ChatGPT2API 网页搜索工具，返回答案和来源链接。 |
| 3406 | astrbot_plugin_mc_motd | 1 | other | watch | 查询 Minecraft 服务器（Java 版 / 基岩版）MOTD 状态，并将结果渲染为图片卡片发送。支持配置默认服务器，直接 /motd 一键查询。 |
| 3407 | astrbot_plugin_group_approval | 1 | other | watch | 为 OneBot QQ Bot 的原生 AI 聊天提供主群等级、GROUP / PRIVATE 双域授权和人工审批。 |
| 3408 | astrbot_plugin_dafeiyu_group_scope | 1 | other | watch | 只在配置好的完整群会话 ID 里、且被真实 @ 时才让消息继续进入 AstrBot， 其余群消息直接丢弃；群聊里会明确按多人语境回复，不套用私聊亲昵称呼和私人背景。 |
| 3409 | astrbot_plugin_qinglong_notify | 1 | platform | have | 接收青龙面板的自定义 Webhook 通知，并转发到 AstrBot 配置的消息渠道。 |
| 3410 | astrbot_plugin_screen_watch | 1 | personality | have | 盯住电脑上任意一个窗口，画面有变化就通知你，不用一直守着屏幕。  能做什么： · 按窗口标题找到目标，定时截取该窗口画面，被遮挡也能抓 · 前后两帧比对，按变化面积占比判断是否值得上报 · 触发后写一条事件，交给 AstrBot 的正常对话流程处理，人设、历史、工具都在 · 内置看护：进程挂了自动重 |
| 3411 | astrbot_plugin_mcp_selfheal | 1 | other | watch | 通用 MCP 会话自愈。任何 streamable_http / SSE / stdio 的 MCP 服务在自身重启、 会话表丢失后，客户端会用失效的 Mcp-Session-Id 一直被拒（404 -> McpError 32600）， AstrBot 原生重试不覆盖该异常，导致永久失效直到重启进 |
| 3412 | astrbot_plugin_video_archiver | 1 | media-parse | borrow | 配合「ParseVideo 视频图集解析」(astrbot_plugin_api_video_parser) 使用： 白名单用户发送视频/图集链接后，解析插件调用 parse-video-py 解析并下载媒体， 本插件在结果交给 QQ 机器人发送之前，把同一份文件另存到本机指定目录。 不重复调用解析 |
| 3413 | astrbot_plugin_volc_asr | 1 | tts | watch | 基于火山引擎（豆包）大模型语音识别的插件，收到语音自动转写为文本交给后续流程，支持录音文件极速版与流式两种模式。 |
| 3414 | astrbot_plugin_gal_link | 1 | game | have | 在 QQ 群聊中搜索 Galgame 资源，支持三语标题、纠错候选和分页。 |
| 3415 | astrbot_plugin_touhou_events | 1 | platform | have | 使用THBWiki公开活动日历，按城市、省份、关键词和日期查询东方展会、茶会与聚会。默认中国未来30天，支持分页、独立详情与出处，查询使用纯文本。 |
| 3416 | astrbot_plugin_chartsmith | 1 | platform | have | 让 AI 把流程、架构、调用链画成一张排版好的图片，直接发到 QQ / Telegram / 飞书里，而不是一堆文字。  模型只给节点和连线，插件负责分层排版、正交走线，用 Pillow 在本地渲染成 PNG：零额外依赖、离线可用、不经过第三方渲染服务。 支持自动挑选上下/左右方向、2 倍像素输出、 |
| 3417 | astrbot_plugin_autojlc | 1 | game | have | 嘉立创金豆每日自动签到，支持 Token 绑定、多账号管理、余额查询、第七天奖励领取与私聊推送。 |
| 3418 | astrbot_plugin_study_bridge | 1 | memory | have | # 学习桥梁（Study Bridge）  给 AstrBot 加一套「学习日程 + AI 计划 + 记忆同步」能力：  - **AI 拆计划并真实写入日程**：`/plan new 考研数学` → AI 出计划 → `/apply` 落库 - **App / QQ 同一份数据**：Web、Wind |
| 3419 | astrbot_plugin_minesweeper | 1 | game | have | 多人协作扫雷小游戏，支持自然语言开局和结束、三档难度、自定义棋盘、批量操作及 18 套皮肤。 |
| 3420 | astrbot_plugin_dafeiyu | 1 | other | watch | 肥鱼养成记 —— 全群一起养鱼，探索奇遇、共建鱼塘，留下每一轮的毕业回忆。 |
| 3421 | astrbot_plugin_forum_parser | 1 | group-admin | have | 自动识别聊天中的 Stage1st (S1) 与 NGA 论坛帖子或指定楼层链接（支持同源域名、QQ JSON/小程序分享卡片、Telegram 超链接实体），支持Bangumi3种域名，支持配置登录态及 S1 官方 App 接口解锁审核中/禁言不可见内容，支持发布至 telegra.ph（配图自动 |
| 3422 | astrbot_plugin_flyai | 1 | other | watch | 基于飞猪官方 flyai MCP 的旅行查询插件。  覆盖 8 个底层能力：语义搜索、关键词搜索、机票、火车票、酒店、景点、万豪系酒店、万豪套餐。 所有价格与库存直连飞猪供应链，结果自带飞猪下单短链，点开即可跳转 App 完成支付。  指令：/飞猪 /机票 /火车 /酒店 /景点 /飞猪帮助 同时注 |
| 3423 | astrbot_plugin_think_guard | 1 | other | watch | 挡住模型把「开头的内部推理」漏进聊天正文。  规则和 Go 版 leadingThought 一致：只处理开头显式带标签的内部推理 （<analysis> / <thinking> / <think> / 内部 <summary>）， 无标签的普通回复和正文中间出现的标签都不动。  三个拦截点：LL |
| 3424 | astrbot_plugin_attachment_reader | 1 | other | watch | 查看 ZIP 目录，读取压缩包内文本 |
| 3425 | shadow_memory | 1 | memory | have | 影忆 ShadowMemory —— 自迭代人格记忆、隐性回忆、群聊门控、分段回复、语音、笔记、备忘录与 QQ 空间 |
| 3426 | astrbot_plugin_wxsc_elec_bill | 1 | other | watch | 查询校园宿舍电表余额与用电量、拉取充值台账（精确到秒）、按账号备注、按人汇总与导出 Excel/Markdown，并支持定时推送与充值到账提醒；内置 Web 控制台可选楼栋房间、按时间范围查询与手动推送。个人自用工具，与校方及缴费平台无隶属关系。 |
| 3427 | astrbot_plugin_deobf_private_push | 1 | other | watch | 群聊引用图片解密并推送到指定私聊的插件（关键词拦截版，图片全程本地处理，不经过 AI） |
| 3428 | astrbot_plugin_hnu | 1 | other | watch | 湖南大学宿舍信息与电量查询，内置 CAS 登录、短信二次验证、内存 Session、连接复用、每日低电量提醒，提醒语可自定义。 |
| 3429 | astrbot_plugin_jusuo | 1 | game | have | 王者荣耀世界「居所助手」数据查询插件，数据来自玩家自发分享的 jusuo.playmmo.cn。  功能： - `/菜地`、`/牧场`：按物品筛选的高倍收购列表，支持单价/售价两种排序与翻页，附带商人 UID、等级、剩余时间与预估售价； - `/物品列表`：一键列出菜地与牧场当前在售的全部物品名；  |
| 3430 | astrbot_plugin_keylol_pusher | 1 | info-push | have | 把其乐论坛（keylol.com）的新帖自动推送到 QQ 群 / QQ 私聊。  · 通过论坛官方 RSS 增量发现新帖，无需登录 · 自动抓取帖子首楼正文、配图（可关闭），并清理 Steam 小部件、广告等噪声 · 可选 AI 摘要：调用 AstrBot 已配置的对话模型把正文概括成一段话，推送只 |
| 3431 | hash_redaction | 1 | other | watch | Bot 会忽视 #井号内部的消息#，井号内的内容不会进入后续插件或 LLM。 |
| 3432 | astrbot_plugin_multisim | 1 | other | watch | 把本机 NI Multisim 14.3 变成 AstrBot Agent 的电路仿真工具。  能力：打开 .ms14 工程、枚举与修改元件参数、提交 DC / AC / 瞬态仿真、参数扫描、 读取测量值与验收结论、导出实验报告；15 个 LLM 工具 + /ms 控制台命令。  架构：插件 → m |
| 3433 | astrbot_plugin_fls_youshuiauth | 1 | other | watch | Minecraft 认证（QQ 绑定与快捷登录，内网 HMAC 桥接） |
| 3434 | astrbot_plugin_content_detection | 1 | other | watch | 利用腾讯云CI对图片进行检测打分,以及制作幻影坦克和图片加密 |
| 3435 | astrbot_plugin_self_reflex | 1 | other | watch | 梦想是做成给Alice用的一套自我感知系统，可以查看当前系统日志，硬件状态等信息，监控内存变化，文件变化等等，并通过小模型判断是否提交给大模型通知用户或者自动处理 |
| 3436 | astrbot_plugin_socialdatabase | 1 | other | watch | 通过 OneBot v11 aiocqhttp 按需采集白名单内的当前群或显式启用的批量群成员； 每群生成稳定 JSON v1 批次，先写入 AstrBot plugin_data 持久队列，再通过认证 HTTP 接口上传到 SocialDatabase。支持超时重试、指数退避、rejected 隔 |
| 3437 | astrbot_plugin_123share | 1 | other | watch | 通过中文模糊指令分享、提取 123share 极简快传的文件和文字，支持限时追问和引用消息。 |
| 3438 | astrbot_animalorastudio_monitor | 1 | other | watch | 连接远端 AnimaLoraStudio 服务器，实时监控 LoRA 训练状态、日志、预览图，支持监听多服务器 |
| 3439 | astrbot_plugin_nezha | 1 | other | watch | 接入哪吒 v0 魔改版（nezha-zero 系）面板：概况 / 列表 / 分组 / 单机详情，二次元玻璃拟态高清卡片，支持分组、延迟监控与权限控制。 |
| 3440 | astrbot_plugin_gzctf_bot | 1 | other | watch | GZCTF 赛事查询、管理与公告播报插件 |
| 3441 | astrbot_plugin_fx | 0 | other | watch | 基于 Token 钱包插件的模拟外汇交易插件。自动拉取 EURUSD、GBPUSD、USDJPY、 XAUUSD 真实报价（启动即拉取、每分钟自动拉取，买入/卖出/查报价时各拉取一次）， 支持 /买入、/查仓、/查报价、/卖出 四条指令，按 10000 token = 1 美元计价， 所有使用与获得 |
| 3442 | astrbot_plugin_earthmc | 0 | other | watch | 查询 EarthMC Minecraft 服务器的状态、城镇、国家、玩家、在线列表等信息，支持销城风险评估、市场交易信息记录、VP 监测。支持 /em 命令和自然语言两种查询方式。 |
| 3443 | astrbot_plugin_dancecube | 0 | other | watch | 舞小鲸（舞立方查询）：扫码登录、个人信息、B15+R15 / B30 / AP30 战力分析图 |
| 3444 | astrbot_plugin_shinjuku | 0 | other | watch | AstrBot 原生「新宿」音游窝上机计费插件，使用 SQLite 本地存储。 |
| 3445 | astrbot_plugin_firecrawl | 0 | other | watch | 通过 Firecrawl API 进行网页抓取、搜索与站点任务。 |
| 3446 | astrbot_plugin_yunxiao_projex | 0 | group-stats | borrow | 对接阿里云云效 Projex OpenAPI（只读），自动识别当前/上一迭代并轮询工作项状态，状态变更时在群内 @ 负责人；支持在群聊用前缀记录工作内容，并按可自定义模板由 AI 生成周报。 |
| 3447 | astrbot_plugin_delivery_guard | 0 | group-admin | have | 检查群禁言，记录缺席来信，通过公开事件与协作发送接口暂存文字并在恢复后补发。 |
| 3448 | astrbot_plugin_proactive_mind | 0 | memory | have | 让机器人按人格与最近对话流水自主判断"是否唤醒、何时唤醒、唤醒时调用哪些工具做什么、要不要说话"，由插件持有并展示唯一的唤醒作业；主动消息默认写回平台对话历史与 LivingMemory 会话库，交给记忆系统正常反思入库。 |
| 3449 | astrbot_plugin_0528_v2 | 0 | other | watch | 把 AstrBot 的消息交给 Alkaid0 Coding Agent：注册 alkaid0 执行器，按群维护 ACP v2（WebSocket）连接与会话，空闲自动回收；启动时自动检查两个前置插件（astrbot_plugin_librunner / astrbot_plugin_libi18n |
| 3450 | astrbot_plugin_loomloom | 0 | other | watch | 批量执行云端 Skill，轻松处理文案创作、图片生成与需求审阅。聊天选技能，Excel 批量准备，确认费用后执行并收取结果。 |
| 3451 | astrbot_plugin_anisignal | 0 | info-push | have | 在插件设置中管理各会话的资讯订阅、每日速报与商品进展。 |
| 3452 | astrbot_plugin_one_last_image | 0 | other | watch | 把赛璐珞风格的动画截图或插画，转换成 One Last Kiss 封面风格的彩色线稿。引用图片发 /卢浮宫 即可，支持线条粗细、铅笔排线、水印与初回限定盘等选项。 |
| 3453 | astrbot_plugin_todo | 0 | other | watch | 用图片清单记录和完成待办。 |
| 3454 | astrbot_plugin_symbol_guard | 0 | other | watch | 忽略纯符号群聊误唤醒 |
| 3455 | astrbot_plugin_filetransfer | 0 | ssh-exec | exclude | 让跑在服务器上的机器人把本机文件发到 QQ 群聊 / 私聊，也能把 QQ 发来的文件存进服务器。  常用命令：/取 发文件、/目录 看目录、/打包 压缩后发送、/转 转发到其他群或私聊、/存 收进服务器、/收件箱 看收到的文件、/文件信息 看大小和 SHA256。中英文命令都能用，比如 /fileg |
| 3456 | astrbot_plugin_image_context | 0 | other | watch | Keeps a ledger of group pictures (downloaded and shrunk on arrival, animated ones as a frame grid) and gives the model the recent group chat with pict |
| 3457 | astrbot_plugin_night_guard | 0 | personality | have | 守夜鱼（NightGuard）的 AstrBot 后端。到点后手机被全屏聊天框盖住，只能跟你的 AstrBot 角色求情；一晚只放行一次，可以求一张「准备睡觉」的照片，聊久了会自己结束会话。人设读取 AstrBot 默认人设，也可以关掉用通用人设。需要配合 Android App 使用：https: |
| 3458 | astrbot_plugin_qq_pretty | 0 | other | watch | Turns LLM Markdown into plain text that reads well in QQ before sending: headings become 【】, list items use ·, tables become 「key: value」 lines, and c |
| 3459 | astrbot_plugin_always_watching_you | 0 | other | watch | 向 LLM 注册私聊与群聊消息历史查询工具，并支持查找机器人与指定用户的共同群，仅支持 aiocqhttp 平台。 |
| 3460 | astrbot_plugin_ipcam_plus | 0 | other | watch | 多路视频流监控插件：任意数量RTSP/HTTP流截图与录像、多流批量获取（5,10 或 5-8）、多定时任务与每日定时推送（如 /auto_img 7,8 20:00）、任务持久化（重载/重启不丢失）、插件管理员列表、列表地址深度脱敏。 |
| 3461 | astrbot_plugin_img_api | 0 | game | have | 接入兼容 img-api 的图床服务（接口文档：https://imgapi.bixygames.com/docs），支持随机图、图库、图片详情、统计与头像；安装后需在插件配置中填写你的图床 API 地址。 |
| 3462 | astrbot_plugin_forward_media_saver | 0 | media-parse | borrow | 监听群聊与私聊中的合并转发消息，递归解析图片、视频、语音和文件并保存到本地，提供 SQLite 索引、统计命令、WebUI 页面、命名模板、失败任务重试与清理。 |
| 3463 | astrbot_plugin_provider_chain | 0 | media-parse | borrow | 主模型报错自动接力，支持图文候选列表；解析层接管选模，有序候选 + 失败冷却 + 降权，不重启即时生效；不猜模型能力，不越出候选集；支持发图后等待补挂消息，让聊天更自由。 |
| 3464 | astrbot_plugin_media_guard | 0 | other | watch | 修复各平台图片 / 文件发送失败：远程资源先落本地、超大图片自动压缩、失效文件降级提示 |
| 3465 | astrbot_plugin_turn_limiter | 0 | other | watch | 按天分区限制对话轮数，每天自动重置，支持自定义重置时间点。 |
| 3466 | astrbot_plugin_taodock | 0 | other | watch | Generate AI images and videos in AstrBot with one TaoDock API key, discover the models available to that key, and resume long-running video tasks. |
| 3467 | astrbot_plugin_rainyun_rgs | 0 | game | have | 通过雨云 API 查询游戏云(RGS)实例列表与详情，支持开关机、重启与积分自动续费（剩 7 天时先续 30 天，积分不足退回 7 天）。 |
| 3468 | astrbot_plugin_animeapi | 0 | image-gen | watch | 使用 AnimeAPI 生成动漫图片：每张 $0.003，预付 $5 起、余额永不过期，无订阅，新账号免费 3 张。发送 /anime 加描述即可出图，支持模型、画幅与每用户冷却设置。Anime image generation with AnimeAPI at $0.003 per image. |
| 3469 | astrbot_plugin_wecom_external_bridge | 0 | other | watch | 在 AstrBot 插件内直接通过远程 Frida 处理企业微信外部客户群文本消息，无需独立 HTTP 桥接服务。 |
| 3470 | astrbot_plugin_star_game | 0 | platform | have | QQ 群娱乐圈文字游戏：出道/签到/抽签/活动/比拼/排行，AI 实时生成事件、互动剧本、采访、微博舆论， 人气独立成长，系统 NPC 会约战、恋爱；连签与 13 个成就自动解锁，几乎每个动作之后 AI 都会对当事人口头点评一句； NPC 会突然 @ 你搭话、等你回应；v3.1 加入星币经济与事务所 |
| 3471 | astrbot_plugin_task_chime | 0 | other | watch | Agent 跑完一轮任务后，在你的电脑上响一声。只在耗时超过阈值的私聊里触发，带冷却；找不到音效文件会自动回退系统提示音，非 Windows 宿主静默跳过，不报错也不阻塞消息。 |
| 3472 | astrbot_plugin_miku_sticker | 0 | sticker | borrow | 识别 LLM 回复中的 `[表情:xxx]` 标记，从本地 `stickers/xxx/` 文件夹随机发送一张表情图。  特性 - 9 种情绪：开心、害羞、得意、生气、委屈、吃瓜、晚安、爱心、惊讶 - 发送后自动从回复文本中移除标记，不影响可读性 - 可选：自动收集指定群聊里的图片，用视觉模型分类后 |
| 3473 | astrbot_plugin_immich_curator | 0 | other | watch | 自然语言检索 Immich 照片，展示编号缩略图，选择后取回原图；会话授权与用户隔离。 |
| 3474 | astrbot_plugin_neurobrain | 0 | personality | have | Keep in-process NeuroBrain state from AG99 Persona results and add live state to prompts. |
| 3475 | astrbot_plugin_face_acedatacloud | 0 | other | watch | Use Ace Data Cloud Face Analyze to inspect face landmarks and image dimensions. This version offers analysis only. |
| 3476 | astrbot_plugin_librunner | 0 | other | watch | 通用 Agent Runner 注入接口：其它插件可通过 api 注册自定义 Agent 执行器，并出现在 WebUI 的执行器下拉框中。 |
| 3477 | astrbot_plugin_superai | 0 | memory | have | SuperAI 是面向 AstrBot 的 AI 增强插件。它把「模型路由 / 自动降级」「智能记忆与摘要」 「联网增强」「知识库问答」「AI 快捷指令」「工作流编排」「用量统计与成本控制」 打包成一套可视化的 AI 基建，让 Bot 在保持上下文连贯的同时更快、更稳、更省。 |
| 3478 | astrbot_plugin_lingchat | 0 | sticker | borrow | 把 LingChat 里的角色回复实时同步到 QQ 等平台，也能把 QQ 里说的话送回 LingChat 的对话。  - **表情包**：按情绪把角色立绘裁成 240×240 透明 PNG，跟着每条回复一起发出去 - **语音**：LingChat 生成 TTS 语音时一并转发 - **双向**：Q |
| 3479 | astrbot_plugin_aria2_download | 0 | media-parse | borrow | 向QQ发送分享链接，该插件会借助aria2下载视频和图文。可解析的软件包括：推特、哔哩哔哩、快手、抖音等流媒体 |
| 3480 | astrbot_plugin_MFLX_API | 0 | game | have | 接入 Minecraft 服务器面板「API 管理」中开放的远程 API（/api/remote/*），可在聊天中查看服务器列表、运行状态与最近日志，并执行启动、停止、重启以及发送游戏内指令；内置权限控制与指令白/黑名单，同时提供 LLM 工具供 AI 直接调用。 |
| 3481 | astrbot_plugin_token_guard | 0 | other | watch | 低开销自动整理会话历史：按 token 成本加权触发、渐进归档而非清空，自动与内置上下文压缩协作，并提供管理员自检命令。 |
| 3482 | astrbot_plugin_bili_subscription | 0 | media-parse | borrow | 自动监控 B 站账号的新视频、动态与专栏，推送到指定群聊。 |
| 3483 | astrbot_plugin_welcome_ai | 0 | group-admin | have | 自动生成贴合人格的欢迎新成员文案；支持自定义唤醒词，回复由 AI 微调。 |

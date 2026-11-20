# 第十三批参考评估：LangBot 全家桶（19.1k★）× AstrBot 新件 × 框架工程参照

30 个目标（28 仓 + 1 组织页 + 1 官网），2026-11-21。侦察：机制级事实采集；
判定层沿用四类判例（SSH 执行器/逆向/自动发布/自迭代）+ ToS/反爬 + 跨端信任级 +
宿主完整性边界。头牌是 LangBot——同赛道最成熟的平台，本批的核心价值是**对表**
（同构确认 + 差异定位），不是找新点子。

## 一、本批构成

| 组 | 内容 |
|---|---|
| LangBot 生态 | LangBot 本体、lbctl CLI、new-api 派生、plugin-sdk（已归档迁入主仓）、plugins（归档）、docs（归档）、powercontext（归档）、官网（云服务/定价/安全卖点） |
| AstrBot 新件与工具 | builtin_commands_extension、**AstrBot-desktop**、bilibili_live、qq_custom_menu、AstrBot-Go-Android、easy-live2d、dsh-backup、FishTool、abceed-ai-translator、claude-ui-skills |
| 框架与工程 | crewAI 61k、langflow 157k、vllm 97k、ai-engineering-from-scratch 79.7k、ContractGuard/CoreCoder/RepoWiki/GitSense、layerfs 2.8k、rea、chatless |

## 二、头牌对表：LangBot（19.1k★，Apache-2.0，活跃）

### 2.1 平台本体

机制（原样）：13+ IM 平台矩阵（QQ 个人+官方、微信/企微、Discord、TG、Slack、LINE、
飞书、钉钉、KOOK、Satori、Email、Matrix 桥接 WhatsApp/iMessage 等）；事件驱动插件 +
MCP；多流水线（不同场景不同 bot）；部署形态全家桶（Cloud 零部署 / install.sh / Docker
/ K8s / 宝塔）；官网商业化分云服务版 + 独立环境版，安全卖点含通行密钥、两步验证、
插件审核、转人工客服。

判定：**已有同构为主，广度不是目标**。soapbot 的四端策略（QQ 双适配器 + web/app/
desktop 强弱执行端分层）与 LangBot 的"平台数量矩阵"是两条路线——广度不跟进；
多流水线 = persona-per-group 已有同构；组织近期 monorepo 归整（docs/plugins/sdk 全
并入主仓）与 soapbot 的独立市场仓对照——保持独立仓（插件逐个安装语义），不变。

### 2.2 插件 SDK：隔离 worker 的独立路线验证（本批最有价值的确认）

langbot-plugin-sdk（2026-11 归档并入主仓 sdk/）的形态（原样）：
- **Plugin Runtime（lbp rt）＝插件宿主进程，经 stdio 或 WebSocket 桥接 LangBot**——
  与 soapbot 隔离 worker（子进程 + 长度前缀帧协议 + 宿主侧重查每个回调）**同构**。
  两条独立路线收敛到同一架构，这是 #99/#101 两轮契约修复的架构正确性的外部佐证。
- 六类组件抽象：Command / Tool（LLM 可调用）/ EventListener / KnowledgeEngine
  （RAG 可插拔检索）/ Parser / **Page（嵌入管理面板的自定义网页）**。
- 统一 ExecutionAPI facade（72 项能力，api.execution.invoke/stream）。
- Box Runtime（lbp box）：Docker/nsjail/E2B 三后端的**插件代码执行沙箱**。

判定与设计输入：
- **同构确认**（架构正确性佐证，无需改动）。
- ExecutionAPI 72 项统一 facade vs soapbot 逐面窄授权：**保持 soapbot 模式**——
  逐面授权 + 每次调用重查能力是跨端信任级审计（#94）的基石，统一 facade 会把
  授权粒度摊平。不跟进。
- Page 组件（插件嵌入面板网页）：**观察登记**——信任面大幅扩张（面板 XSS 面 +
  插件 UI 即宿主 UI），与宿主完整性边界冲突；除非出现强需求，不排期。
- Box Runtime 代码沙箱：**不跟进**——插件无任意代码执行面是 soapbot 有意边界
  （同 admin-mode 判例）；登记为"形态参照"，说明业界用 nsjail/Docker 做到什么程度。
- KnowledgeEngine 可插拔 RAG 组件抽象：**观察**——soapbot kb 面已有；插件自定义
  检索器是合理的扩展位，登记 kb 面设计输入。

### 2.3 lbctl CLI（Go）

操作者 CLI：status/doctor、install/upgrade/autostart、bot/pipeline/kb/provider/
plugin/skill/mcp-server CRUD、monitoring、api get/post、assistant chat；本地认证走
Core API。判定：**借鉴候选（低优先）**——soapbot CLI 只有 start/token/doctor/setup/
migrate，CRUD/监控走面板；CLI 化运维是补全面不是缺口，登记观察。

### 2.4 powercontext 与官网安全卖点

powercontext（归档）：纯集成插件——PromptPreProcessing 阶段调独立 PowerContext
Server（POST /v1/context/prepare），只注入**有界**返回上下文（系统消息 + "不可信
历史"边界标记）；scope 用 SHA-256 会话/发言者绑定；fails open（增强层故障不阻塞
主链路）；远程 HTTP 默认拒绝。判定：**同构确认**——"有界注入 + 不可信边界标记 +
scope 哈希钉死 + fails open"与 soapbot 召回面/注入屏幕的设计直觉一致，独立路线
再验证，无需改动。

官网安全卖点（通行密钥/两步验证/插件审核/操作日志）：面板已登录态 + 审批总线 +
审计日志同构；**"认证插件"市场分层登记观察**——soapbot 市场用 digest 锚定 + CI
装载冒烟，"认证"分层（维护者审查标记）是远期候选；llms.txt（Agent 可读文档索引）
是**零成本借鉴项**，登记。

## 三、AstrBot 新件与周边工具

### 3.1 AstrBot-desktop（1.1k★）——桌面壳同构 + 更新通道参照

Tauri 2.10 + **打包 CPython 3.12 后端运行时 + WebUI（127.0.0.1:6185）**；stable/
nightly 双通道，nightly 自动跟随上游构建；AppImage 应用内更新；数据迁移工具。
判定：**与 soapbot 桌面壳几乎同构**（Tauri + sidecar 打包后端 + 面板托管；连端口
选择都一致）。**借鉴候选**：发布双通道与应用内更新——soapbot dist-test 目前手动
分发 + SHA256SUMS，更新通道是分发成熟度差距；登记 dist 分发设计输入（低优先）。

### 3.2 builtin_commands_extension——核心指令瘦身参照

AstrBot 主程序只留 6 个核心指令（/sid /stop /reset /new /dashboard_update /help），
其余（/llm /plugin /op /model /history /persona /set）迁入官方扩展插件、可在面板
停用。判定：**设计输入（观察）**——soapbot 核心命令面的安全命令（/panic /act-grant
等审批链）必须留在核心；功能性命令是否迁插件是"核心面最小化"的同款课题，登记
待议（不排期）。

### 3.3 bilibili_live——B 站直播面（借鉴候选）

内嵌二次开发 blivedm（开源弹幕协议库，WS 连接），接收弹幕/礼物/SC/点赞/进场/
上舰，三模式（仅转发 / LLM 聊天后转发 / 回调接口发送）；上下文记录 + 随机丢弃。
判定：**借鉴候选（登记 bili 面设计输入）**——直播弹幕是公开数据 + 开源协议库 +
WS 客户端，与 soapbot UA/robots/只读纪律兼容；直播面（看播/播报）是 bili 只读面
的自然延伸。长连接与消息洪流需要独立限频面（随机丢弃是现成参照）。不排期，
待 bili 面拍板时合并考虑。

### 3.4 qq_custom_menu——官方菜单面（待拍板附带项）

QQ 官方开放平台 API v2（GET/PUT /v2/menu，C2C 单聊菜单），AppID+Secret 鉴权、
乐观并发版本号、可视化 Dashboard。判定：**借鉴候选（待拍板附带项）**——与 batch12
§3.2 QQ 资料管理同域（人格"外在形象"），走官方接口完全合规；随 qq_official 面的
启用拍板一起考虑。

### 3.5 easy-live2d——人格可视化维度（借鉴候选）

Pixi.js 8 封装的 Live2D Web SDK（MIT，223★）：官方 Cubism 5 Core、动作/表情 API、
playVoice 口型同步、鼠标跟踪/物理/命中检测、参数直控。判定：**借鉴候选（登记
人格生态设计输入）**——batch12 §3.2「人格外在维度」的 Web 形态：面板聊天页给
人格卡挂 Live2D 形象（表情随状态、口型随语音）。模型资产版权（Cubism 模型授权）
在实现时核对。不排期，进人格生态待拍板材料。

### 3.6 dsh-backup——soapbot 的备份缺口（借鉴候选，高价值缺口）

tar.gz + SHA-256 边车、可选口令加密（scrypt + AES-256-GCM）、恢复前自动快照、
--dry-run、失败回滚、保留 7 份轮换、**进程外 rescue 脚本**（备份目录自带零依赖
恢复器，不依赖本体）。判定：**借鉴候选（本批排期首位）**——soapbot 的 data/
（SQLite + 存档 + 插件 + secret.key）**没有任何备份面**。形态映射：`/backup` 面板
按钮或 CLI 子命令 → data/ 打包（凭据默认脱敏）→ sha256 → 本地轮换（可选异地
推送后置）；恢复前自动快照 + dry-run 照搬。进下批排期。

### 3.7 其余工具（快判）

- **FishTool（264★）**：B 站 UP 主运营工具（热点/评论监控/抽奖筛选/AI 伪人巡检 +
  WBI 签名 + **Cookie 池** + 扫码登录态）。判定：**排除**——Cookie 池与登录态批量
  采集踩反爬纪律（同 local-search 判例）；"AI 伪人巡检"踩人格欺骗灰区。可取残留：
  评论负面预警的产品形态可作为 bili 面只读子集参照（只看自己账号的官方通知）。
- **AstrBot-Go-Android**：PRoot + Debian 13 + Python 3.12 在手机本地跑完整 AstrBot。
  判定：**排除跟进，登记为对照反例**——手机端跑完整后端 = 弱设备变强执行面，
  与 soapbot 跨端信任级（手机=弱执行端，只做视图）直接相悖；其"所有安装仅按钮
  显式触发"的多实例管理细节本身做得干净，反例价值在于边界立场差异。
- **abceed-ai-translator**：Tampermonkey 学习网站增强脚本。判定：无机制交集，不评。
- **claude-ui-skills**：Claude 风格 React19 + Tailwind4 组件库（scoped 主题、无
  Preflight 不污染宿主、Playwright 回归）。判定：**观察（UI 批参照）**——深度 UI
  改版时的组件级参照（主题作用域隔离与宿主样式互不污染的做法值得抄）。

## 四、框架与工程参照

| 仓 | stars | 机制 | 判定 |
|---|---|---|---|
| crewAI | 61.1k | Crews（角色化协作）+ Flows（事件驱动、装饰器、Pydantic 状态）；hierarchical 有 manager 委派；**human input / human review / checkpointing**；MCP/A2A | **观察（HITL 确认）**——多 agent 动态编排不跟进（单人格陪伴 + 宿主完整性）；其 HITL/checkpointing 与 soapbot 审批总线同构，是"人介入点是一等公民"的市场级确认 |
| langflow | 157k | 可视化流程编排 + 流程导出为 MCP server；分步调试 playground | **观察**——形态相反（审查代码 vs 搭流程图），不跟进 |
| vllm | 97.3k | PagedAttention/连续批处理/量化/OpenAI 兼容 API | **已有同构**——providers 直连外部端点；vllm 是端点背后的引擎，自托管时经 openai_compat 接入即可 |
| ai-engineering-from-scratch | 79.7k | 542 节 AI 工程课程 + skills 形态 | **观察（资料）**——非机制对象 |
| ContractGuard | 152 | 合同审查 CLI：Parse→Detect→**LLM Analyze→确定性 statute checklist Verify**→A+~F 评分→Report；jurisdiction 参数 | **同构确认 + updatepilot 输入**——"LLM 提议 + 确定性清单复核"双通道与 updatepilot（AI 审查 + 确定性降级规则）同构；statute checklist 的确定性复核层可对照 updatepilot 的 verify 增强 |
| CoreCoder | 1.9k | 1.5k 行极简 coding agent（while loop + 8 工具 + 三层上下文压缩 + sub-agent 以 withholding 隔离） | **观察（教学参照）**——与 soapbot 无直接交集；"sub-agent 隔离 = 不给工具"与插件 worker 的窄面同思路 |
| RepoWiki | 307 | 仓库→wiki：依赖图 + **PageRank 排序文件重要性** → LLM 四步分析；diff 按 importance + blast radius 排序 | **同构确认 + updatepilot 输入**——audit 的 critical-first 排序同思路；"blast radius 排序 diff"是 updatepilot 审查排序的增强参照 |
| GitSense | 91 | issue/贡献匹配 + Radar 仓库健康度打分（合并速度/CI 健康/发布节奏） | **观察**——updatepilot 对上游依赖仓的健康度评估可参照 |
| layerfs | 2.8k | FUSE + CoW + 内容寻址的多 agent 共享文件系统（单 SQLite 存 branch/commit） | **观察**——soapbot 插件存储是 per-plugin 加密 KV 命名空间，无共享 FS 需求；分支/checkpoint 语义是"会话状态分叉"的远期参照 |
| rea | 471k（页面数字异常，待核） | 逆向工程 MCP 聚合（二进制/应用/抓包 → RL 环境） | **排除**——逆向类判例直接命中（与 ToS/合规边界冲突） |
| chatless | 310 | Tauri 2.0 + Next.js 本地优先客户端；WebDAV 同步含 tombstone 删除策略 | **观察**——与 soapbot 桌面壳同栈不同形态（纯客户端 vs 打包后端）；tombstone 同步是数据面远期参照 |
| LangBot 官网 | — | 云服务版 + 独立环境版 + 认证插件 + llms.txt | **观察 + llms.txt 借鉴（零成本）**——商业化分层不做，文档 llms.txt 可直接加 |

## 五、排除清单（本批新增判例）

| 机制 | 对象 | 判例 |
|---|---|---|
| 逆向工程聚合 | rea（MCP 逆向二进制/应用/抓包） | 逆向类判例 |
| Cookie 池批量采集 | FishTool（WBI 签名 + Cookie 池 + 扫码登录态） | 反爬/ToS 纪律（同 local-search 判例） |
| 弱端强执行 | AstrBot-Go-Android（手机 PRoot 跑完整后端） | 跨端信任级：手机是弱执行端，只做视图 |
| 插件代码执行沙箱 | LangBot Box Runtime（Docker/nsjail/E2B） | 宿主完整性：插件无任意代码执行面（同 admin-mode 判例） |
| 插件嵌入面板页 | LangBot SDK Page 组件 | 宿主完整性：插件 UI 即面板 UI = XSS 面扩张 |
| LLM 网关自托管跟进 | langbot-new-api（AGPL 派生） | 形态不符（providers 直连 + budget 面已覆盖） |

## 六、结论与排期

1. **同构确认清单（本批最大价值）**：LangBot Plugin Runtime（stdio/WS 宿主进程桥）
   ≅ soapbot 隔离 worker；powercontext（有界注入 + scope 哈希 + fails open）≅ 召回面
   设计；AstrBot-desktop ≅ soapbot 桌面壳；ContractGuard 双通道 ≅ updatepilot 审查；
   RepoWiki 重要性排序 ≅ updatepilot audit 排序；crewAI HITL ≅ 审批总线。六条独立
   路线收敛，边界设计未被市场证伪。
2. **下批改编候选（新增）**：**备份面**（dsh-backup 模式，data/ 无备份是真实缺口，
   排期首位）> bili 直播面（bilibili_live，待 bili 拍板合并考虑）> Live2D 人格可视化
   （easy-live2d，人格生态待拍板材料）> QQ 官方菜单（qq_custom_menu，随 qq_official
   拍板）> 桌面壳更新通道（dist 分发设计输入）> llms.txt（零成本随手项）。
3. **设计输入登记**：核心指令瘦身（builtin_commands 参照）、KnowledgeEngine 可插拔
   RAG（kb 面）、认证插件分层（市场）、CLI 运维面（lbctl 参照）、claude-ui-skills
   主题作用域（UI 批）。
4. **排除判例新增**：弱端强执行（手机 PRoot 跑后端）——第五类判例成立，后续同类
   形态直接引用。
5. 逐仓安全审查未做（本批只到机制级）；任何进入改编排期的仓库需先过 Mimosa +
   云鼎双工具的装前审计（既有纪律）。

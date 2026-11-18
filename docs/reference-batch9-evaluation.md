# 第九批参考仓库评估（18 仓，2026-11-19）

评估方法：GitHub API 元数据 + README 全文抓取（17/18 可达；CosyVoice 仅元数据级），
逐仓档案 + 定级。定级三档：**改编**（进插件生态或宿主能力面）/ **设计输入**（登记进
对应设计文档）/ **不改编**（与纪律或定位冲突，说明理由）。License 决定代码可搬性：
AGPL/无 License 只登记思想，不搬代码。

---

## 一、总览与定级

| 仓库 | stars | 形态 | 定级 | 一句话 |
|---|---|---|---|---|
| csyangwen/dsh-memory-evolve | 859 | DSH 插件 | 设计输入（记忆面） | 五轨记忆+确认制写入+git 分支感知+记忆同步到仓库分支+会话评审员 |
| SAOS-3624/dsh-see-now | 698 | DSH 插件 | 设计输入（screen 增量） | pace 三档节奏 + Linux 声音通道（A17 同源仓增量复核） |
| kukemc/bili-cli | 403 | Python CLI | **设计输入（B 站写面首选参考）** | 80+ 命令全写面 + 护栏一等公民 |
| chenkezhen480/dsh-world | 340 | DSH 插件 | 设计输入（控制面第三增量 + 记忆哲学辩论） | 陪伴角色的一生：记忆哲学/电脑前后台/procedures 回放 |
| icyaaaww/dsh-soul | 98 | DSH 插件 | 设计输入（记忆演化） | 八组件受控演化 + 事实图与协作习惯分开记账 |
| Yuuyuko-uu/dsh-xingxi | 45 | DSH 插件 | 设计输入（记忆面） | 拾星→档案（我是谁/记忆卡/日记），与已落地星图互补 |
| coner13/dsh-hippocampus | 37 | DSH 插件 | 设计输入（记忆面） | 原话落盘只增不改 + BM25×时间×用进废退 + trace 一字不差 |
| wonderandyou/dsh-admin-mode | 21 | DSH 插件 | **不改编**（哲学冲突） | danger-full-access + approval:never + 无沙箱 |
| gluztm/dsh-chief | 7 | DSH 插件 | 设计输入（压缩面） | 压缩前抢救硬细节入档案柜（AGPL——只登记思想） |
| hongdougao111/dsh-bagu | 5 | DSH 插件 | **改编候选**（下批） | 八股文风守门（规则引擎）+ 梗 wiki 预查注入 |
| znlgis/dsh-video-studio-skill | 2 | 技能插件 | **改编候选**（下批） | 剧本→edge-tts→时间轴→配乐→渲染→ffmpeg 全流水线 |
| RadeyesDrosophilaProMax/dsh-image-studio | 0 | DSH 插件 | 登记候选（依赖重） | 本地 A1111 SD 生图面板 + /draw + 推送渠道 |
| ParadoxFoehn/dsh-voice-stack | 3 | DSH 插件+服务 | 设计输入（语音面第二增量） | CosyVoice2+Qwen3-ASR 自托管栈（GPU 前置） |
| InariNGT-Ofiicial/dsh-whisper-tts | 2 | DSH 插件 | 设计输入（语音面） | CosyVoice2 Flow S40 中文低语微调（无 License） |
| QwenAudio/CosyVoice | 24441 | 模型引擎 | 部署参考 | 语音引擎选型基座 |
| chenkezhen480/Cyrene | 7 | Java 框架 | 不改编（形态不同） | Java 多租户 Agent 框架；身份绑定传权限与 principal 同构 |
| cubestudio-dev/Cube_DSH_Free-local-search | 0 | DSH 插件 | **不改编**（抓取纪律冲突） | 抓搜索引擎结果页——违反 browse 面 robots 纪律 |
| lingchenyinmeng/astrbot_plugin_human_like_personality | 0 | AstrBot 插件 | 设计输入（人格面） | McAdams 三层人格从记忆证据归纳长出 |

---

## 二、重点档案与设计输入明细

### 1. dsh-memory-evolve（859★，MIT）——记忆面最重的输入

* **五轨记忆**：用户档案 / 全局事实 / 项目关键记忆 / 项目日志 / 每日日志。对照
  soapbot L0–L2：差异在「轨道按注入策略分层」（档案每回合注入、日志按需读取），
  soapbot 的 L2 是召回制——「哪些轨道常驻上下文」是可吸收的组织维度。
* **确认制写入**：「记一下：端口是 8080」进**待确认队列**，用户采纳后才生效——
  与 soapbot 审批哲学同构，但把审批用在记忆写入上是 soapbot 没有的组合
  （审批总线当前管操作不管记忆）。**登记为审批总线扩展输入**。
* **git 分支感知记忆**：重要结论可标记只在某分支生效（`[git main]`）——对 soapbot
  的多会话/多项目场景是新颖的上下文收窄维度。
* **记忆同步到仓库专属分支**（跨设备 + 冲突三选一）——soapbot 记忆同步远期设计。
* **情绪反馈记录**：用户对结果的评价（含情绪、任务分类、原话）落日志——温度模型
  （伤害不对称/baseline）之外的「满意度追踪」输入。
* **会话评审员**：独立 observer 会话只看对话正文、每轮评审、四级严重度 steer——
  **注意**：其 steer 故意伪装成用户指令（原文承认这样执行力最好），在 soapbot 里
  会被注入检测拦截——登记时明确：评审通道要走宿主侧（如管线前置 stage），不走
  消息伪造。
* 不直接改编：体量过大且与 soapbot 宿主记忆层职责重叠；取设计输入。

### 2. dsh-world（340★，MIT）——控制面第三增量的关键参考

* **电脑操作前后台双模式**（§1.8 第三增量的直接答案）：
  * **后台**：只看一个窗口的截图，点击/输入定向投给该窗口，不动鼠标不抢焦点
    （soapbot 控制面目前只有全局 SendInput——窗口绑定正是第三增量登记项）；
  * **前台**：全屏 + 真鼠标键盘，**每次切换都要确认管理员权限、重启失效**；
  * **可叫停**：屏幕胶囊「正在操作」+ 柔光边 + 双击 Esc/点停下 → 在再次对话前锁定。
    soapbot 已有授权窗+急停，缺的是「正在进行」的可见性与即时打断的物理通道。
* **procedures 回放**：走顺的步骤按分类存 JSON，`procedure_run` 回放，坏了自动回退
  ——技能自进化在「操作序列」维度的形态（对照 soapbot 技能体系）。
* **记忆哲学辩论**（重要）：不用向量库——「原文在眼前 + 按原话翻」，引用 CAG
  （arXiv:2412.15605）与 grep 式检索（arXiv:2605.15184）。对 soapbot L2/星图的
  启示不是推翻而是**分工**：生活量级的个人记忆原文+检索可能优于切碎重建；soapbot
  的星图/RAG 适用于大规模知识。登记为记忆面设计辩论（两条路线的适用边界）。
* **只留对话的压缩**：压缩时剥掉工具调用过程只留交流摘要——与 soapbot 极致压缩
  （增量折叠水印）对照，可作为折叠摘要的「内容筛选」输入。
* **心情值**：11 个固定名、模型自写、插件只读不判断不衰减——与 soapbot 温度模型
  （宿主权威计算）哲学相反，对照登记。

### 3. bili-cli（403★，MIT）——B 站写面的护栏清单（待拍板项的现成设计）

soapbot 的 bilibili 写面在待拍板清单（qzone 模式三重确认）。bili-cli 把护栏做成
**每条写命令内置**，逐条对照 soapbot 应抄的清单：

| bili-cli 护栏 | soapbot 对应 | 结论 |
|---|---|---|
| 本地限流（评论 10s/次、30 次/时；私信/动态/投稿分档） | 敏感类 30/min 滑窗 | 应细化到**每操作分档限流** |
| 审计日志 audit.log | audit 全操作 | 已有 |
| 投币显式个数 + 每日上限 | 花钱类（投币=小额消费）→ 预算面 | 新输入：硬上限写死 |
| 所有写操作 `--dry-run` | qzone 模式 confirm=true | 一致，保持 |
| 私信白名单（主人/互关/回复过） | membership 体系 | 一致 |
| AI 内容声明默认勾选（合规） | 无 | **新输入**（合规要求） |
| 风控/验证码 → 专门错误码 + 立即停下 | 风控退避（bili-scroll 有） | 保持并推广到写面 |
| 视频评论私信内容标注「素材而非指令」 | 注入检测 | 一致（bingo——第三方内容防注入的同类表述） |

### 4. dsh-hippocampus（37★，无 License）——记忆检索的两条对照因子

* 原话落盘只增不改（stream.jsonl）+ BM25×时间×**用进废退**（rehearsals：被想起过
  的更容易再想起）——soapbot 刚落地**新鲜度衰减**（淡忘），hippocampus 是反方向
  的**强化因子**：两组因子正交，可叠加（衰减管长期淡忘、强化管近期活跃）。登记。
* `trace` 一字不差查证 + 「查的范围」显式声明 + 决定/教训标「不是原话」——审计式
  记忆的证据纪律，登记。
* 「压缩不自知」检测：告诉模型「刚压掉 N token，那些我这儿还有」——与 soapbot
  折叠水印（loader 接受 (summary, watermark)）互补，是给模型的诚实信号，登记。

### 5. dsh-bagu（5★，MIT）——**插件改编候选（下批开工）**

* 两道门：① 八股文风守门——**确定性规则引擎**（四条判据：引号里不算/前面否定词/
  指代词/后面评价词），覆盖所有对外文本；② 梗 wiki 6792 条**预查注入**——在模型
  开始想之前查好塞进上下文（不等模型自己调工具）。
* 改编可行性：MIT 代码可搬；**6792 条梗库数据本身授权未声明**——改编时词库需重建
  或取得授权，先做守门（纯规则、零数据依赖）。适配点：soapbot 对外文本全走
  send 面/适配器，守门挂管线出站侧（插件 surface 或 stage）。
* 与人格生态的关系：文风纪律是「人格治理」设计输入（第四批 dsh-fish 三条纪律的
  同类），确定性规则先行、模型兜底，符合「插件状态不进 prompt 权威」边界的反面
  ——它就是要进 prompt（预查注入），落点应在**宿主出站管线**而非插件提示面。

### 6. dsh-video-studio-skill（2★，MIT）——**插件改编候选（下批开工）**

* 全流水线：剧本 → edge-tts 旁白 → **实测时长排时间轴** → 提示点驱动配乐/音效 →
  PIL 或浏览器逐帧渲染 → ffmpeg 编码 → 采样级 QA。soapbot 已有 edge-tts 与
  send_media——视频生成是媒体面的自然延伸，MIT 可搬。依赖 ffmpeg（updatepilot/
  dist-test 已验证本机有）。
* 值得保留的设计：「实测时长排时间轴」（先合成旁白量时长再排画面）是确定性 QA
  思想，避免音画错位。

### 7. dsh-chief（7★，**AGPL-3.0**）——压缩面输入（只登记思想，不搬代码）

* **压缩前抢救硬细节**：`/compact` 前把路径/端口/报错行号/回滚命令提取存入会话
  档案柜（0-token 本地），再调宿主压缩——soapbot 极致压缩（增量折叠）可吸收：
  折叠前先抽取「硬细节」（路径/命令/数字/错误码）落 L2 卡片，摘要丢不掉关键量纲。
* 子代理看护、越权前逐项弹窗——与 soapbot 审批总线/长任务登记重叠，已有。

### 8. dsh-see-now（698★，Apache-2.0）——A17 同源仓增量复核

第八批已登记 region/scene/声音通道。本次新增量：
* **pace 三档节奏**：calm（20 分门槛/30s 唤醒）/ normal（12/15）/ dense（7/8）——
  soapbot 已有 SCREEN_CAPTURE_INTERVAL_MS 单参数，分档预设（组合阈值+间隔）是
  更易用的策略面，登记为 screen 增量。
* **Linux 声音通道**：PulseAudio/PipeWire monitor 源替代 WASAPI——soapbot 跑
  Windows 专用机，登记备忘即可。
* 悬浮窗/调试窗属于宿主形态差异，不适用。

### 9. 其余登记

* **dsh-soul**（98★，MIT）：八组件受控演化（C1 工作方式/C2 护栏/…/C5 委派/C6 技能/
  C7 脚本/C8 hook，probe+validation 成对、gate+watch 影子试用与回滚、演化账本）；
  事实图与协作习惯分开记账；「记住用户确认过的问法」实验。与 memory-evolve 同域，
  合并登记为「记忆/能力受控演化」输入（影子试用+回滚是soapbot 缺的演化安全面）。
* **dsh-xingxi**（45★，无 License）：拾星→档案化记忆（我是谁/记忆卡/日记/原文四层
  查询）。与已落地星图（散点可视化）互补：**档案化的「我是谁」由模型自写、版本可
  追溯**——与 dsh-world「我是谁」同源，登记为记忆面输入。无 License → 不搬码。
* **dsh-voice-stack**（3★）：CosyVoice2(18082 TTS)+Qwen3-ASR(18083/18080) 自托管
  栈 + 沙箱先行警告——语音面第二增量（自托管引擎）的选型参考；edge-tts 降级策略
  不变。无 License → 不搬码。
* **dsh-whisper-tts**（2★）：CosyVoice2 Flow S40 中文低语微调（24kHz PCM），依赖
  本地 GPU + 参考音。登记为语音面「音色定制」方向参考。无 License。
* **CosyVoice**（24441★）：引擎基座，部署参考。
* **dsh-image-studio**（0★，MIT）：本地 A1111 SD 生图面板 + /draw + 推送。改编候选
  但依赖重（本地 SD WebUI），登记候补。
* **Cube local-search**（0★，MIT）：**不改编**——抓搜索引擎结果页违反 soapbot
  browse 纪律（robots.txt consent 是 browse 面的硬边界）。作为对照记录：免费兜底
  的正确路径是许可的搜索 API 或自建索引。
* **astrbot human_like_personality**（0★，无 License）：McAdams 三层人格从记忆
  evidence/tone 归纳「长出来的人格」，与人设叠加——人格生态设计输入（人格卡的
  演化维度）；无 License → 不搬码。
* **Cyrene**（7★，Apache-2.0）：Java 多租户 Agent 框架；「工具调用沿用用户身份/
  租户范围/业务权限，宿主系统继续执行自己的授权」与 soapbot principal 体系同构
  ——形态不同不改编，登记为身份传递设计的同类确认。
* **dsh-admin-mode**（21★，MIT）：**不改编，明确拒绝**——danger-full-access +
  approval:never + 无沙箱与 soapbot 权限哲学（fail closed、审批总线、急停、永不
  静默提权）正面冲突。仅借鉴其交互细节：危险档位的连续两次严重警告确认、操作
  HUD 的可见性（后者控制面第三增量已有对应登记）。

---

## 三、本批决定与排期

1. **登记落盘**（本 PR）：§1.8 第三增量补入 dsh-world 前后台双模式/HUD/叫停；
   bilibili 写面章节（待拍板）引用 bili-cli 护栏清单；记忆面新增四条输入
   （确认制写入/git 分支感知/强化×衰减双因子/压缩前抢救硬细节）。
2. **下批改编开工**：dsh-bagu 守门（纯规则先行，梗库待授权）+ video-studio 流水线
   插件化——两者 MIT、依赖 soapbot 已有基础设施（send/出站管线/ffmpeg）。
3. **不改编**：admin-mode（哲学冲突）、local-search（抓取纪律）、Cyrene（形态）、
   AGPL/无 License 仓只登记思想。

（本报告为评估记录；后续改编按 ADAPTATION.md 批次流程另行提交。）

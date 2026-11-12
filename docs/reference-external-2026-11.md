# 外部仓库分析（2026-11-12）：看了什么，改了什么，没抄什么

> 本文延续 `docs/reference-ecosystem.md` 与 `docs/reference-dsh-ecosystem.md` 的口径：
> **只读评估、不引入源码/依赖/运行时**，每条对照都要落到本仓库一处具体改动或一条明确的
> 「不改」理由。三个链接里有两个原始地址不可用，核实过程与证据一并写在下面，不猜内容。

## 0. 地址核实（先把链接弄对，再谈分析）

| 用户给的链接 | 核实结果 | 采用的地址 |
| --- | --- | --- |
| `github.com/zuho-kai/bothouse` | **404**。GitHub 用户主页搜索定位到正确拼写是 `zuiho-kai`；其 pinned repo 里确有 `bothouse` | [`zuiho-kai/bothouse`](https://github.com/zuiho-kai/bothouse) |
| `github.com/mearihaka/dsh-linging` | **404**。`gh api users/mearihaka` 返回用户存在、`public_repos=1`；`users/mearihaka/repos` 给出唯一仓库 | [`mearihaka/dsh-longing`](https://github.com/mearihaka/dsh-longing)（`longing`，不是 `linging`） |
| `github.com/Fangi8` | **404**。`gh api users/Fangi8` 返回 `Not Found`，网页搜索也未定位到该账号或同名仓库 | **待用户提供正确地址**；本文不编造内容 |

`Fangi8` 这一项是本轮唯一真正阻塞的外部依赖：没有可核实的对象，写出来的「分析」只会是
想象。其余两项已按纠正后的地址做了公开 README / 仓库元数据的只读评估。

---

## 1. `zuiho-kai/bothouse`：多 CLI 协作层

**它是什么**（公开 README，Apache-2.0，Go + 前端面板）：把用户已登录的多个 AI CLI
（Claude Code / Codex / Gemini CLI / DSH…）放进同一个群聊；一个 lead 角色按技能与配额
拆活，大任务交给独立 workspace（handoff 带上原话、范围与「完成」的定义），结果要带证据
回来，**只有需要人拍板的决策才回到聊天**；所有角色共享一份 Markdown 记忆，夜间复盘会
把当天记错的东西修好，重复的纠正先变成「规则草稿」，**人批准后才生效**。
支持 Discord / 飞书 / QQ 官方 / DSH，另有 Web 面板与手机访问。

**值得学，且本仓库已经有对应物**：

| bothouse 的机制 | soapbot 已有的落点 | 判断 |
| --- | --- | --- |
| 只有需要人的决策回到聊天 | `APPROVAL_BUS` → QQ / Webhook / 手机三通道；面板与手机都能点批准 | 同一治理目标，形态不同，不移植 |
| 结果要带证据、夜间复盘纠错 | 每条 CHANGELOG 写「原来错在哪」；门禁把否定式不变量写成可执行断言 | 学的是「把边界写成可验证的契约」 |
| 规则草稿需人批准才生效 | 插件能力逐项批准 + `manifest_digest` 钉住被评审的确切字节 | 已有更严格的形态 |
| 共享 Markdown 记忆、Git 追踪 | `docs/` 内 Markdown + `check_doc_links.py` / `check_test_gaps.py` 校验 | 不搬 Git 同步与中心化 wiki |

**明确不移植**：多 CLI 团队、workspace 交接、任务板、夜间复盘、角色包与插件市场。
soapbot 是单进程 QQ 机器人，插件是**进程隔离、逐能力审批**的，引入「一个 lead 把活派给
其它 AI」等于给不可信的模型输出一个跨插件派单通道；`docs/plugin-security.md` 已经把
「插件间互相调用」列为刻意不做。**本轮没有为此写任何代码。**

## 2. `mearihaka/dsh-longing`：被算出来的角色状态

**它是什么**（仓库元数据 + README 摘要 + 目录结构；README 约 87 KB，本轮只读评估，
未逐行复刻）：给 AI 角色装一层会自己流动的欲望状态——七维数值互相牵制，被一句话推动，
没人理就慢慢回到日常。MIT，JavaScript/TypeScript，topics 含 `deepseek-harness` /
`plugin` / `state-machine` / `roleplay`；目录有 `src/`、`test/`、`tools/`、
`CHANGELOG.md`、`注意事项.md`。

**与本轮温度模型的关系**：它想解决的现象（「没人理就慢慢回到日常」）和
`docs/qq-autonomy-design.md` §4 的温度衰减是同一类直觉。但两者的**写入权**相反：

| | dsh-longing | soapbot |
| --- | --- | --- |
| 状态由谁算 | 状态机被一句话推动，数值随交互流动 | `ai/autonomy.py::compute_warmth` 纯函数，只吃「成功归档的回复数」与空闲时长 |
| 谁能写 | 角色状态自身持续演化 | 只有 `PersistReplyStage` 在归档成功后记一次；模型与插件都**不能**写 |
| 跨会话持久 | 角色状态长期存在 | 纯内存 7 天窗口，重启从 0 开始，刻意不编造亲密史 |
| 暴露给插件 | 插件读写同一份状态 | `session.view` 只多一个只读 `warmth` 标量 |

**结论：不移植七维状态机。** 理由与 `docs/reference-dsh-ecosystem.md` §4.1 一致：让模型
输出成为跨会话持久化的写入口，会成为提示注入的落点；而本项目的人格卡是人工审批的
持久实体。我们把它改写成**一个只读观察者插件**：
`src/soapbot/examples/plugins/warmth-observer/` 用 `ctx.session.warmth` 和人格卡
`autonomy` 白名单报告当前会话是否「够热」，不写状态、不主动发言、不申请 `send`。
这是「被算出来的状态」在本仓库能安全落地的形态。

## 3. 去 AI 味 skill：按本仓库口径改写，不安装第三方 SKILL.md

**参考了什么**（只读）：[`lifelonglazylearner/qu-ai-wei`](https://github.com/lifelonglazylearner/qu-ai-wei)
的 SKILL.md。它的方法论里真正值得搬的是三条**约束**，不是它的输出模板：

1. 处理正文前先做敏感信息门检，疑似凭证立即停止、不复述、不先掩码再继续；
2. 冻结信息账本（数字、术语、引语、归因、限定、证据强度），改写不得补事实、不得把
   不确定说成确定、不得把相关性升级成因果；
3. 不把 AI 写作症状当作者身份鉴定，也不为了「人味」添加错别字、emoji、第一人称。

**没抄什么**：它的八族模式目录、门检/终稿/打磨报告三段式输出契约、内嵌模式、品牌语体
判断、按平台调阈值的整套参考文件。soapbot 的文档不是待发布的公众号文章，套一个
「【门检】判断：…」的产物反而会让 CHANGELOG 变成模板填充。

**改成什么**：`docs/writing-style.md` 是把上述三条约束翻译成本仓库口径的写作规范——
「写清原来错在哪」「不假装修了」「未实测标未验证」「数字同步」「事实 / 命令 / 边界」
四块；另配 `scripts/ai_flavor_scan.py`，一个纯标准库的**可选**扫描器：只检查
`docs/` 与 `CHANGELOG.md` 里几类无争议的填充（空洞升华、整齐收尾、模糊归因、
`不是…而是…` 三连、同义反复），不鉴定作者、不改文件、默认不进 CI。
它的用途是让人在提交前自己跑一遍，不是一个会自动变绿的门禁。

---

## 4. 一句话总结

能搬的是「只有需要人的决策回到人面前」「规则改动要人批准」「边界写成可验证的契约」；
不能搬的是「让模型自己决定长期状态」和多 agent 派单。三条链接里两条拼写已纠正、
一条仍不可用；已纠正的两条都只做了只读评估与一份示例插件改写，**没有引入任何外部
依赖、源码或运行时**。

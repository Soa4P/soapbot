# 清单取舍、代码库检查与四层落地范围

> 回答三个问题：这份安全研究清单里**哪些该落实、哪些没有用**；代码库**有没有本地未推送**；
> 四层（框架后端 / 全栈接口 / UI 面板 / 桌面端产物）**实际存在什么问题、本轮改什么**。
>
> 判定基于逐文件取证，不基于概念相似度。上一轮的逐条覆盖度判定见
> `docs/semantic-authorization.md`；本文只做**取舍**与**落地范围**。

## 0. 取舍口径

| 档位 | 含义 | 本轮动作 |
|---|---|---|
| 该落实 | 本仓有真实对象，存在可验证缺口，改动不推翻架构 | 落地 + 回归测试 |
| 没有用 | 概念针对的表征空间 / 评估体系在本仓不存在，或只是重复粘贴 | 不落地，写明理由 |
| 不适用 | 本仓根本没有该实体（单进程单租户，无多 Agent / 结算 / 委托） | 不落地，也不写成「已通过」 |
| 已具备 | 已有实现与阻断门禁，重复造轮子是净负担 | 不动，或只补一条静态断言 |

**清单里有 2 条重复粘贴**：「防御单元从单 Agent 权限上移到交互组合能力闭包…」与
「学习成分仅做提议/排序…确定性安全护盾…」各出现两次。重复不产生新要求，合并判定。

## 1. 逐条取舍表

| # | 条目（简写） | 取舍 | 证据与理由 |
|---|---|---|---|
| 01 | mandate→签名→settlement→服务效果链强制语义单调不放大；签名有效性≠授权合规性 | 不适用 | 全仓无 mandate / settlement 实体；`src/soapbot/security/tokens.py` 是管理面板 JWT，`src/soapbot/budget/policy.py` 是花费配额。原则本身已由 `src/soapbot/security/provenance.py` 的「解析只建立结构、授权独立裁决」局部体现 |
| 02 | 巩固前做独立于内容的表征结构验证（几何稳定性 / 拓扑一致性），而非内容过滤；语义漂移在单条记忆层面不可见 | 没有用 | 本仓检索是 BM25 + 余弦向量（`src/soapbot/memory/store.py`），没有表征空间几何稳定性或拓扑一致性评估对象；`src/soapbot/memory/handoff.py` 的 `well_formed` 是结构合法性，不是几何验证 |
| 03 | 显式度量模拟-真实校准误差和覆盖缺口；未评测维度标记为未知风险而非通过 | 已具备 | `docs/semantic-authorization.md` 已有「未知」档（D20）并由 `tests/test_semantic_authorization_review.py` 锁定；本仓不做模型校准，模拟-真实误差无测量对象 |
| 04 | 证据工件（mandate / receipt / settlement / 工具输出）间做类型化语义映射校验，而非结构邻接等价 | 不适用 | 无前述工件；本仓只有 `src/soapbot/security/provenance.py` 的 `ToolArguments` / `Provenance` 与 `src/soapbot/memory/handoff.py` 的 `Handoff` 三元组，属类型化数据结构而非跨协议映射 |
| 05 | 推理层之外建立独立语义参照系；执行前校验解析出的操作含义与批准时定义一致 | 该落实（局部） | 独立参照系无实体；但「操作含义与批准时一致」在本仓有真实对象：`src/soapbot/plugins/dispatch.py` 工具名前缀未校验、`src/soapbot/mcp/client.py` 的 `list_tools()` 只清洗不算摘要。落地为网关前缀硬化 + 工具元数据摘要 |
| 06 | 每次加载时与批准快照比对工件哈希 / 端点 / 能力；静默变化触发重新批准 | 该落实 | 哈希与能力已有（`src/soapbot/plugins/loader.py` 的 `digest_tree` / `grant_for`）；端点未比对，`warn` 模式在 `:539-557` 记 `outcome="allow"` 后照常加载。本轮落地了 MCP 工具元数据的批准摘要与不匹配拒绝；插件 `warn` 模式的显式标红**未做**，见 §5 |
| 07 | 翻译边界维护显式语义映射；下游缺失语义视为不可知而非默认安全 | 该落实（局部） | 无翻译层；但「缺失语义不可默认为安全」在本仓有真实缺口：`src/soapbot/security/provenance.py:110-112` 对未打标签的 dict 返回 `Admission(True, "host_constructed")`。落地为外部工具分支要求非默认允许 |
| 08 | 证据在插件信任域之外产生；与工件哈希和策略版本绑定；参照 TRACE / VOLT 格式而非自研 | 没有用 | `src/soapbot/plugins/attestation.py` 首行自述「detectably tamper-evident, not cryptographically signed」；同进程无外部信任根，加 HMAC 不改变信任域，只增加密钥管理面。TRACE/VOLT 不是本仓格式 |
| 09 | 跨层失效路径维护可更新的残余风险度量；修复清单 ≠ 风险归零 | 已具备 | `docs/security-model.md` 与 `docs/semantic-authorization.md` 均有残余风险披露；本轮补一份「落地了什么、仍缺什么」即可 |
| 10 | 每次更新后量化边界稳定性；对漂移超阈值实施安全回归测试，而非仅验证准确率 | 该落实 | `src/soapbot/plugins/approvals.py` 的 `drift()` / `code_drift()` 是 report-only；`src/soapbot/plugins/attestation.py` 的 `verify()` 有漂移判定但 `verify_attestation` 无生产调用点。落地为接线 + 回归断言 |
| 11 | 真实基准治理作为纪律；验证层不能完全由 AI 驱动；长会话约束保持确定性检查 | 该落实 | 确定性门禁齐备（`.github/workflows/ci.yml` 的十余个 `check_*.py`）；`scripts/ai_review.py:4-9` 与 `:449` 明说「不是 gate、只作参考」，但**没有静态断言锁住这句话**。本轮落地了门禁断言；长会话跨轮确定性的专项回归**未做**，见 §5 |
| 12 | Agent 依赖的知识源视为供应链信任边界；对从知识继承的信任做显式验证 | 已具备（局部） | `src/soapbot/memory/handoff.py` 的 `HandoffGate.decide` 重校验结构 / data-only / 置信度 / 受众反单调；`src/soapbot/security/provenance.py` 的 `mark_vetted` 仅宿主可调。跨 Agent 知识继承无实体 |
| 13 | 网关层强制工具名一致性、内存来源标记、跨客户端隔离、默认拒绝审批 | 该落实（2 / 4） | ②来源标记（`src/soapbot/ai/stages.py` 的 `ToolArguments(origin=MODEL)`）与③会话隔离（`src/soapbot/plugins/dispatch.py` 的 `CallerContext`）已具备；①`register_source` 无重名 / 前缀校验、④参数侧默认允许是真实缺口 |
| 14 | 纵向评估安全属性在累积和复用中的存活，而非一次性测量 | 没有用 | 全仓无纵向评估体系；`scripts/check_security_boundaries.py` 是本仓自己的 20 项静态门禁，不是跨层纵向评估 |
| 15 | 防御单元上移到交互组合能力闭包；跨 Agent 遥测端到端因果链；Ensemble Trifecta 不变量门控（原文重复 2 次） | 不适用 | 单租户单进程、无跨 Agent 通信；`docs/progress/progress.json` 的 `ph17-t1` 已记录这一判断。重复粘贴不产生新要求 |
| 16 | 每次调用边界检查数据类别与目标司法管辖区允许性；「数据驻留」≠「主权合规」；知识 / 推理发生地纳入评估 | 不适用 | `jurisdiction` / `data_category` / 数据类别 / 司法 在 `src/soapbot` 零命中；`docs/semantic-authorization.md` 的 F28 已判不适用 |
| 17 | 学习成分仅做提议 / 排序；确定性安全护盾执行时过滤 fail-closed；保证来自护盾而非模型（原文重复 2 次） | 已具备 | `src/soapbot/security/provenance.py` 的确定性 deny、`src/soapbot/security/injection.py` 的 canary 与 `src/soapbot/plugins/dispatch.py` 的 `leaked_canary()` quarantine。重复粘贴不产生新要求 |
| 18 | 签名方案可版本化替换；长期承诺考虑后量子 / 哈希基；「先收集后解密」纳入威胁模型 | 该落实（文档） | `src/soapbot/plugins/attestation.py` 的 `SCHEMA_VERSION` 已支持版本化；后量子在本仓无落地对象（`src/soapbot/security/crypto.py` 用 Fernet、`src/soapbot/security/tokens.py` 用 HS256），但「harvest-now-decrypt-later」值得写进 `SECURITY.md` 的残余风险，成本近乎为零 |
| 19 | 编排层将危险标记与执行中止硬接线；验证每个框架的 Pe 是否非零 | 已具备 | `scripts/check_security_boundaries.py` 的 s20 锁 4 个文件共享 `INVISIBLE` 表；`src/soapbot/plugins/dispatch.py` 的 `leaked_canary()` → quarantine。系统级 Pe 无实体；局部 `src/soapbot/memory/handoff.py` 的 `residual_unsafe_rate` 是观测值而非归零假设 |
| 20 | 监控、告警路由和强制其生效的测试置于 Agent 写作用域之外；Agent 自我叙述不作为证据 | 该落实（局部） | `src/soapbot/plugins/surfaces.py` 的 `log.write` 标注「Deliberately ungated」且无审计；本仓无 Agent 写作用域概念，但「自我叙述不作证据」可落为静态断言（AI 评论不进阻断判定） |
| 21 | 写回边界审计状态差异，对授权漂移和工具使用升级做选择性回滚，而非仅过滤内容 | 该落实 | 选择性回滚部分**不适用**：`scripts/restore.py` 只有整库恢复，无按调用 / 轨迹的回滚。该落实的是前半句：授权漂移与完整性变化显式审计并在面板标红 |
| 22 | 运行时拉取的提示 / 工具 / schema 纳入与代码同等的完整性校验；不依赖容器扫描 | 该落实 | `src/soapbot/mcp/client.py` 的 `pinned_version` 只在 `initialize` 握手生效；`list_tools()` 的描述与 `inputSchema` 只清洗 + 审计，无哈希。落地为元数据摘要 |
| 23 | 安全评估单元从单 Agent 上移到系统级涌现行为；不假设个体安全推出集体安全 | 不适用 | 单租户单进程，无组合拓扑；`docs/semantic-authorization.md` 的 F25 已判不适用 |
| 24 | 事件级监控之上维护轨迹级可恢复性信号，而非仅检查单次动作合法性 | 该落实 | `src/soapbot/core/trace.py` 的 `summary()` 已有 `historical: False`（显式不可恢复标记），缺的是重启前后不可区分。落地为 `boot_id` + `recoverable` 信号，不重复造标记、不做持久化 |
| 25 | 不假设框架提供委托遏制；显式实现 authorization broker 或等价组件 | 不适用 | 无委托 / 经纪实体；裁决在宿主进程内直接发生（`src/soapbot/plugins/dispatch.py`） |
| 26 | 区分「未运行」与「已退役」；休眠 Agent 凭证衰减；对保留内容进入后续可计费上下文设确定性边界 | 该落实（凭证生命周期） | Agent 休眠无实体；但令牌固定 72h、`src/soapbot/api/auth.py` 的 `/refresh` 重签满 72h 且不撤销旧 jti，是真实的可落地对象。本轮落地了刷新撤销旧 jti；按活跃度的 idle 衰减**未做**，见 §5 |

**汇总**：26 条中，该落实 12、没有用 3、不适用 6、已具备 5（含局部判定按主档计）。
原文含 2 处重复粘贴，已合并。这组数字由
`tests/test_optimization_triage.py` 与判定表交叉校验，改任一行的档位都会变红。

## 2. 本地未推送检查结论

只读取证（2026-11-11）：

- `HEAD = master = origin/master = 2e5289a`；`git rev-list --count origin/master..HEAD = 0`；
  `git stash list` 为空 → **没有任何未推送的提交**。
- 但工作区有 **63 个未提交改动**（55 个已修改 + 8 个新增），即前几轮加固成果全部只存在于
  本地工作区，任何一台按 `git pull` 更新的机器都拿不到。
- 当前分支 `fix/public-deployment-and-pr-guidance` **无 upstream**。
- `CONTRIBUTING.md` 当时规定走 PR、不直推 master，master 有分支保护与 6 道必需检查。
  因此本轮推送目标是**新建功能分支并推同名远端分支**，不动 master、不 force push。
  （2026-11-11 规则已变更：所有者可直推或 `--admin` 合并，其他人仍需 PR 且不能自批；
  依据是 Repository Ruleset，见 `CONTRIBUTING.md` 的「谁能做什么」。）

**结论**：真正需要担心的不是「未推送的 commit」，而是「63 个根本没提交的改动」。

## 3. 四层代码问题清单（按严重度）

下表记录的是**本轮取证时**的状态；除明确标注「已具备 / 未做」的条目外，均已在 §4
落地并补了回归测试。保留原始问题描述，是为了让「当时为什么改」不被结果覆盖。

取证范围：`src/soapbot/`、`src/soapbot/api/` ↔ `webui/src/api/client.ts`、`webui/src/`、
`desktop/`，以及 CI / 门禁脚本。

| 层 | 级别 | 问题 | 证据 |
|---|---|---|---|
| 交叉 | 高 | `ruff check src tests scripts` 当前 **4 个 error**，CI 的 lint 步骤会红 | `src/soapbot/plugins/sandbox.py:230` N818；`tests/test_auth_cookie.py:27` F401；`tests/test_ops_readiness.py:334` RUF043；`tests/test_pipeline_trace.py:410` F401 |
| 后端 | 高 | 解密失败静默回落 `default`，密钥轮换 / 密文篡改后 fail-open | `src/soapbot/plugins/sandbox.py:331-337` |
| 后端 | 高 | 工具名前缀可伪造、重名无检测；`mcp__` 前缀被抢先路由 | `src/soapbot/plugins/dispatch.py:353-360, :362-387, :447`；`src/soapbot/mcp/client.py:54, :490` |
| 后端 | 高 | 多 MCP source 的循环被第一个异常中断，后续 source 永不尝试 | `src/soapbot/plugins/dispatch.py:399-411` |
| 后端 | 中 | `verify_attestation` 已定义但零生产调用点，漂移检测只跑在测试里 | `src/soapbot/plugins/loader.py:617-628`；`tests/test_runtime_attestation.py:134-137` |
| 后端 | 中 | `warn` 完整性模式下代码变更记 `outcome="allow"` 后照常加载，面板无感 | `src/soapbot/plugins/loader.py:539-557` |
| 后端 | 中 | refresh 无限续期：旧 jti 仍有效 72h，无 idle / last_activity | `src/soapbot/api/auth.py:509-545`；`src/soapbot/security/tokens.py:113,135` |
| 后端 | 中 | `log.write` 无能力检查、无速率上限、无审计 | `src/soapbot/plugins/surfaces.py:227-236` |
| 后端 | 中 | MCP 工具描述 / inputSchema 无完整性摘要，`pinned_version` 只覆盖握手 | `src/soapbot/mcp/client.py:287-351, :448-496` |
| 后端 | 中 | 远程 blocklist 网络异常时 fail-open（本地 shipped 块仍生效） | `src/soapbot/plugins/loader.py:653-660` |
| 全栈 | 中 | 无全局 CSRF / Origin middleware，写路由靠逐路由声明依赖；新路由漏挂即失守 | `src/soapbot/app.py:551-642`；`src/soapbot/api/auth.py:272-289, :327-329` |
| 全栈 | 中 | s12 静态门禁只覆盖 5 个 API 文件，`src/soapbot/api/settings.py` 与 `src/soapbot/api/auth.py` 的内联角色门槛不在断言内 | `scripts/check_security_boundaries.py:373-380` |
| 全栈 | 低 | 前端类型与后端响应字段一致、无调用不存在端点（已有阻断门禁） | `webui/src/api/client.ts:493-527`；`webui/scripts/check-api-paths.mjs`；`ci.yml:227-228` |
| UI | 低 | `window.confirm` 残留为零、`v-html` 仅本地生成二维码、i18n 双目录与 a11y 均有阻断门禁 | `scripts/check_a11y.py`；`webui/scripts/check-i18n.mjs`；`scripts/check_security_boundaries.py:312` |
| UI | 低 | 面板产物与 `webui/src` 时间戳一致，中文标题 UTF-8 完好 | `src/soapbot/webui/dist/index.html:12`；`webui/index.html:12` |
| 桌面 | 低 | CSP 非通配、spawn 规则、sidecar `--add-data`、48.5 MiB exe 已被 gitignore | `desktop/src-tauri/tauri.conf.json:24-32`；`desktop/src-tauri/src/main.rs:67-75`；`.gitignore:60,65-66` |
| 桌面 | 低 | `sidecar/build.py:144` 注释写 `bundle.resources` 指向具体 exe，实际配置是 `["binaries/"]` | `desktop/sidecar/build.py:144`；`desktop/src-tauri/tauri.conf.json:32` |
| 桌面 | 低 | `Cargo.toml` 版本浮动，但 `Cargo.lock` 已提交且 CI `cargo check --locked` | `desktop/src-tauri/Cargo.toml:10,13-16`；`ci.yml:269-273` |

**两处已排除的误判**（写下来避免以后重复排查）：

- PowerShell `Get-Content` 显示 dist 与 `webui/vite.config.ts` 的中文为乱码，是终端代码页问题；
  用 UTF-8 读取确认 `<title>soapbot 控制台</title>` 与 em dash 完好，**不是产物编码损坏**。
- `src/soapbot/webui/dist` 与 `webui/src` 时间戳同为 `2026/11/10 0:33:10`，不构成「产物过期」证据。

## 4. 本轮落地范围

按「该落实」收敛，四层各有实际改动，且每项都有回归测试（**本轮已全部落地**）：

1. **框架后端**：解密失败 fail-closed；网关前缀 / 重名硬化；`_invoke_external` 改 `continue`；
   `verify_attestation` 接入生产；refresh 撤销旧 jti + idle 上限；MCP 工具元数据摘要；
   轨迹 `boot_id` + `recoverable` 信号；`log.write` 审计；完整性漂移显式标红。
2. **全栈接口**：新增一个只读状态端点，把证明重验结论、元数据摘要、完整性漂移状态汇到一处；
   `webui/src/api/client.ts` 补对应类型；s12 与「AI 不替代阻断门禁」补静态断言。
3. **UI 面板**：安全页增加状态块展示上述信号，双目录 i18n 补齐，重建并提交
   `src/soapbot/webui/dist`。
4. **桌面端**：修正 `sidecar/build.py` 注释漂移，复核 CSP / spawn / 产物排除链路，
   尝试重建 sidecar exe（被 gitignore，不进提交）；失败则如实标注「待构建」，不假称成功。

**明确不做**：不新增第 21 条安全契约（会连锁改动 10 份文档的 `COUNT_CLAIMS` needle）；
不引入新依赖；不实现 mandate / settlement / broker / Ensemble / 后量子 / 司法管辖区等无实体组件；
不把 PowerShell 显示乱码或 dist 时间戳当缺陷；不改 20 项契约编号。

## 5. 仍存在的残余风险

- 同进程插件仍可绕过 surface facade 读取进程内密钥，这是 `docs/plugin-security-review.md`
  已披露的架构边界，本轮不声称解决。
- 语义层无法判定「这次调用是否正当」；网关硬化解决的是名称与来源标记，不是语义正当性。
- 运行时证明依旧不是密码学签名；`signature` 恒空的事实保留，不因接线而改口。
- 跨调用数据驻留仍判「未知」：静态扫描证明不了运行时不存在隐式残留。
- 备份恢复仍是整库覆盖，没有按调用 / 轨迹的选择性回滚。
- **本轮取舍后明确未做的三件**：插件 `warn` 完整性模式的显式标红、按活跃度的
  idle 凭证衰减、长会话跨轮确定性的专项回归。前两件需要改加载状态与令牌生命周期
  的对外契约，第三件需要可控时钟；都不属于「确定性小修」，留作独立工作，不在此
  声称已解决。
- 「先收集后解密」只写进了 `SECURITY.md` 的威胁模型，**没有**改变任何密码学能力：
  Fernet 与 HS256 都不是后量子方案，也没有前向保密。

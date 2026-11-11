# 语义授权与证据链：逐条判定

> 写给审计者：这篇文档不证明「系统安全」，只回答一个更窄的问题——
> 一份面向多 Agent / 授权经纪 / 结算系统的安全研究清单，落在本仓库这个
> **单进程 QQ 机器人 + 插件 + MCP 工具调用**上时，哪些条目真的有实现、哪些只是
> 长得像、哪些根本没有对应实体。
>
> 结论先行：28 条主张中，**已覆盖 2 条、部分覆盖 15 条、不适用 10 条、未知 1 条**。
> 本仓库不是 Agent-Ensemble，不加载模型权重，也没有授权委托、服务结算或独立的授权
> 经纪层。把这些概念上相近的东西写成「已通过」是这份文档最需要避免的错误，所以
> 每一行都给出可点开的路径，且由 `tests/test_semantic_authorization_review.py`
> 解析校验。

## 0. 判定口径

四档，**只允许**这四个取值：

| 档位 | 含义 | 允许写「已通过」吗 |
|---|---|---|
| 已覆盖 | 该能力本体存在，且在执行路径上有断言锁定 | 可以，但必须给出执行点 |
| 部分覆盖 | 有相近实现或局部机制，**不等于**满足该主张 | 不可以，必须写明缺口 |
| 不适用 | 本仓库没有该实体，主张在此处无对象 | **绝对不可以** |
| 未知 | 静态证据不足以判定，需运行期或外部测量 | **绝对不可以** |

**「不适用」不是「已通过」**。一个单租户进程里没有跨 Agent 结算链，意思是这条主张
在此处无法评估，而不是这条防线已经建好。同理，「未知」意味着我们承认测量手段不够，
不是默认它安全。凡是判「不适用」的行，证据列都指向
`tests/test_semantic_authorization_review.py` 的静态缺失断言；判「未知」的行则写明
缺的是哪种测量手段。前者读者可以自己重跑。

判定表列顺序固定为「条目 / 判定 / 证据 / 残余风险」，由同一测试校验表头；
改坏表头、抹掉证据路径、或把不适用项改写成已覆盖，都会让门禁变红而不是静默空转。

## 1. 取证方法与边界

- 逐文件核实 `src/soapbot/` 下 `security/`、`plugins/`、`memory/`、`core/`、`api/`、
  `mcp/`、`ai/` 的实现与调用点，以及 `scripts/`、`tests/` 与 `docs/` 的书面披露。
- 大小写不敏感扫描全仓关键词，区分「真实实体」与「散文注释 / `Promise.allSettled` /
  `_settle_stderr` 之类同形词」。
- 引用仓库自己的诚实披露，而不是替它美化：
  `docs/plugin-security-review.md` 已写明「语义层未覆盖（无法判定这次调用是否正当）」
  与「正则类注入 / 脱敏必然可被绕过」；`docs/progress/progress.json` 的 `ph17-t1`
  已把「六类要求因单租户、无跨 Agent 通信、不加载模型权重而不适用」记录在案。
- **边界**：这是静态取证。它不能证明运行时不存在隐式数据残留，也不能证明某段代码
  在所有调度下都不可绕过。需要动态测量的条目，本文判「未知」而不是猜一个结论。

与既有文档的分工：[security-model.md](security-model.md) 讲本仓库自己的威胁模型，
[security-boundaries.md](security-boundaries.md) 的 20 项契约是可执行的静态门禁，
[plugin-security-review.md](plugin-security-review.md) 是插件侧残余风险。
本文只做清单映射，**不新增运行时逻辑，不改动那 20 项契约**。

## 2. 判定表

### A. 语义授权链

| 条目 | 判定 | 证据 | 残余风险 |
|---|---|---|---|
| A1 mandate → 签名 → settlement → 服务效果完整链路 | 不适用 | 全仓无对应实体；`src/soapbot/security/tokens.py` 签发的是管理面板 JWT，`src/soapbot/budget/policy.py` 是花费配额，二者都不是结算；零命中见 `tests/test_semantic_authorization_review.py` | 本仓无授权委托与效果结算对象；任何「链已闭合」的说法都无载体 |
| A2 语义单调不放大 | 部分覆盖 | `src/soapbot/memory/handoff.py` 的 `HandoffGate.decide` 要求受众只收窄，`src/soapbot/memory/stages.py` 接线，`src/soapbot/security/provenance.py` 的 `mark_vetted` 只允许宿主调用 | 这是受众集合与来源标签的单调性，不是「授权语义在翻译中不被放大」的证明；本仓没有语义翻译层 |
| A3 翻译边界 | 部分覆盖 | `src/soapbot/security/provenance.py` 明确「解析只建立结构、授权独立裁决」，`src/soapbot/memory/handoff.py` 的 `parse_handoff` 不作授权判定，`docs/progress/progress.json` 的 `ph21-t2` 记录同一切分 | 有解析与裁决的分离边界，但没有「语义翻译」实体，也没有翻译边界规范或类型化契约 |
| A4 类型化语义映射 | 部分覆盖 | `src/soapbot/security/provenance.py` 的 `Provenance` / `ToolArguments` / `RESOURCE_PARAMETERS`，`src/soapbot/memory/handoff.py` 的 `Handoff` 三元组，`src/soapbot/plugins/manifest.py` 的版本与内容摘要 | 只有类型化数据结构，没有语义映射规则表；结构合法不等于语义授权成立 |
| A5 authorization broker（独立授权经纪层） | 不适用 | 全仓无对应实体；`src/soapbot/plugins/surfaces.py` 的 `SurfaceRouter` 是插件能力回调路由，不是授权经纪；零命中见 `tests/test_semantic_authorization_review.py` | 裁决在宿主进程内直接发生，没有可被独立核验的第三方经纪层 |
| A6 独立语义参照系 | 不适用 | 全仓无对应实体；`src/soapbot/memory/store.py` 的 `MemoryLayer.SEMANTIC` 只是记忆分层枚举；零命中见 `tests/test_semantic_authorization_review.py` | 无独立参照系，语义判定只能依赖模型输出与宿主规则，二者不互相校验 |

### B. 表征与校准

| 条目 | 判定 | 证据 | 残余风险 |
|---|---|---|---|
| B7 表征结构验证 | 部分覆盖 | `src/soapbot/memory/handoff.py` 的 `Handoff.well_formed`、`src/soapbot/security/provenance.py` 的 `Provenance.well_formed`，`src/soapbot/memory/stages.py` 在解析后仍重校验，`src/soapbot/plugins/manifest.py` | 结构校验齐备且明确「结构不等于授权」，但没有独立的表征验证体系，也产不出覆盖率报告 |
| B8 校准误差与覆盖缺口 | 不适用 | 全仓无对应实体；`src/soapbot/memory/handoff.py` 的 `HandoffStats` 只统计残余不安全率，不是置信度校准；零命中见 `tests/test_semantic_authorization_review.py` | 本仓不加载模型权重、不做语义置信度校准；下游任何依赖置信度阈值的决策都没有校准保证 |
| B9 危险标记硬接线 | 部分覆盖 | `src/soapbot/security/injection.py` 的注入模式表与提示标记，`src/soapbot/core/text.py` 的不可见字符共享表，`scripts/check_security_boundaries.py` 的 `s20` 静态门禁 | 表是硬编码且有门禁，但 `docs/plugin-security-review.md` 已承认正则可绕过、语义层未覆盖；硬接线不等于判得准 |
| B10 残余风险度量 | 部分覆盖 | `src/soapbot/memory/handoff.py` 的 `HandoffStats.residual_unsafe_rate`，`src/soapbot/memory/stages.py` 写入 `recall_residual_unsafe_rate`，`tests/test_memory_handoff.py` | 只覆盖记忆召回准入这一个切面，不是系统级残余风险；其余切面仍靠文字披露 |
| B11 漂移回归 | 部分覆盖 | `src/soapbot/plugins/attestation.py` 的 `verify()` 区分策略漂移与工件变更，`src/soapbot/plugins/approvals.py` 的 `drift()` / `code_drift()`，`src/soapbot/plugins/loader.py` 的加载前完整性强制，`tests/test_runtime_attestation.py` | 有内容 / 策略漂移检测，但 `verify_attestation` 无生产调用点（测试只做字符串断言），且没有漂移回归基线与趋势评估 |

### C. 加载期证据

| 条目 | 判定 | 证据 | 残余风险 |
|---|---|---|---|
| C12 加载时哈希 / 端点 / 能力比对 | 部分覆盖 | `src/soapbot/plugins/loader.py` 批准时 `digest_tree`、加载前 `compare_integrity_async`、`grant_for` 生成能力授予，`src/soapbot/plugins/approvals.py` 双摘要，`src/soapbot/plugins/sandbox.py` 取声明与批准的交集，`src/soapbot/mcp/client.py` 握手 `pinned_version` | 哈希 + 能力交集 + 版本 pin 齐备；没有「端点」级比对清单（只有 URL 白名单），pin 留空即不强制，且这些是比对不是签名 |
| C13 插件信任域外证据 | 部分覆盖 | `src/soapbot/plugins/attestation.py` 首行自述「detectably tamper-evident, not cryptographically signed」，含 `ExecutionEvidence` / `RuntimeAttestation` 与 `verify()` | 证明记录可移植，但仓库自己承认无签名、无外部信任根、硬件根证明超出范围；同进程内证据不能自证清白，`docs/plugin-security-review.md` 亦如此披露 |
| C14 可版本化签名 | 部分覆盖 | `src/soapbot/plugins/attestation.py` 的 `SCHEMA_VERSION`、`_policy_version` / `signable_payload` | `signature` 字段恒为空、无密钥后端；有版本化记录与可签名字节，但**没有签名** |
| C15 Agent 知识源供应链 | 部分覆盖 | `src/soapbot/mcp/client.py` 的 `pinned_version` 与 `serverInfo.version` 校验，`src/soapbot/plugins/approvals.py` 双摘要，`src/soapbot/plugins/index_client.py` 自述「不是信任源，不能批准 / 安装 / 加载任何东西」 | 有 MCP 实现版本 pin 与插件审批摘要，但没有 Agent、没有知识源签名或来源证明；索引明确不作为信任根 |
| C16 运行时提示 / 工具 / schema 完整性 | 部分覆盖 | `src/soapbot/mcp/client.py` 的 `list_tools()` 对描述与 `inputSchema` 做清洗与可疑元数据审计，`src/soapbot/security/injection.py` | 有边界清洗与告警，**没有**对提示 / 工具 / schema 的哈希或签名完整性校验；清洗不等于完整性 |

### D. 执行级门控

| 条目 | 判定 | 证据 | 残余风险 |
|---|---|---|---|
| D17 execution-level 门控 | 已覆盖 | `src/soapbot/plugins/dispatch.py` 的 `invoke()` 在角色校验与两条分发路径之前执行 `vet_arguments`，`src/soapbot/ai/stages.py` 的 `_run_tools` 打 `ToolArguments(origin=MODEL)`，`src/soapbot/security/provenance.py` 注明检查紧邻分发，`tests/test_parameter_provenance.py` | 检查与执行在同一函数、无 check-then-act 窗口；但门控依据是来源标签与注册表准入，不判定「这次调用在语义上是否正当」 |
| D18 确定性安全护盾 fail-closed | 部分覆盖 | `src/soapbot/security/provenance.py` 对不可用校验器 / 伪造标签 / data-only 来源一律 deny，`src/soapbot/plugins/context.py` 与 `src/soapbot/plugins/surfaces.py` 无主密钥抛 `StorageUnavailable`，`src/soapbot/plugins/sandbox.py` 的 `EncryptedPluginStorage`，`src/soapbot/security/revocation.py` 损坏文件即拒绝 | 多处确定性 deny 已落地，但没有统一「护盾」抽象；`EncryptedPluginStorage.get` 解密失败仅记 warning 并返回调用者给的默认值，不是抛错；语义层与正则可绕过性仍按 `docs/plugin-security-review.md` 计为未覆盖 |
| D19 网关一致性 | 已覆盖 | `src/soapbot/plugins/dispatch.py` 的 `register_source` 让 MCP 与插件共用同一注册表、`available_for` 统一过滤、单入口 `invoke` 对两类工具统一 `vet_arguments`；`src/soapbot/ai/stages.py` 是唯一调用点，`docs/progress/progress.json` 的 `ph21-t2` 记录「接线点唯一」 | 一致性只覆盖模型参数进入工具调用这一条路径；插件侧还有独立 surface 通道，不在此网关内 |
| D20 跨调用数据驻留 | 未知 | `src/soapbot/core/session.py` 的 `SessionStore` 按会话键隔离并带 TTL，`src/soapbot/memory/stages.py` 的受众收窄，`src/soapbot/ai/compressor.py` 的摘要隔离，`src/soapbot/plugins/sandbox.py` 的命名空间存储 | 静态扫描能确认**没有**显式驻留策略，但无法证明运行时不存在隐式残留（内存 trace 环、日志环、插件命名空间、会话缓存都可能跨调用持有数据）。这需要动态污点追踪或进程内存快照，本轮没有该测量，故不判已覆盖也不判不适用 |

### E. 监控与可恢复性

| 条目 | 判定 | 证据 | 残余风险 |
|---|---|---|---|
| E21 日志 / 告警置于 Agent 写作用域外 | 部分覆盖 | `src/soapbot/logging_setup.py` 只有 stdout 与内存 ring handler、无 FileHandler，`src/soapbot/security/audit.py` 是内存队列加统一脱敏，`src/soapbot/plugins/surfaces.py` 的 `log.write` 标注「Deliberately ungated」，`docs/plugin-security-review.md` | 宿主日志不落盘、STORAGE 能力没有文件写入面，但插件可无门控写宿主日志流，且同进程隔离模式并不构成进程地址空间隔离；本仓也没有「Agent 写作用域」这个概念 |
| E22 只做选择性回滚 | 不适用 | 全仓无对应实体；`scripts/restore.py` 是整库 allowlist 恢复并把旧库改名为 `.pre-restore-<stamp>`，`scripts/backup.py` 提供逐文件校验和，`deploy/restore.sh` 验证后整体替换；零命中见 `tests/test_semantic_authorization_review.py` | 只有全量备份恢复，`--no-config` 只是「不覆盖配置文件」，仍覆盖整库；无法按某次调用或某条轨迹回滚 |
| E23 轨迹级可恢复性 | 部分覆盖 | `src/soapbot/core/trace.py` 明确「重启即丢失，在这里是正确取舍」、容量上限与 `recent()`，`src/soapbot/core/bus.py` 说明无队列、无历史、每个订阅者 await 完才返回 | 只能查看最近若干条轨迹，没有 replay / restore 接口；重启后不可恢复，`EventBus` 也不提供可回放事件流 |
| E24 休眠 Agent 凭证衰减 | 不适用 | 全仓无对应实体；`src/soapbot/security/tokens.py` 与 `src/soapbot/config.py` 的 TTL 是固定 72 小时，`src/soapbot/api/auth.py` 的 `/refresh` 用仍有效的旧令牌重签，不按活跃度变化，`src/soapbot/security/revocation.py` 是人工应急的全局时间点；零命中见 `tests/test_semantic_authorization_review.py` | 没有 Agent 休眠实体，也没有 idle 衰减或 revoke-on-idle；refresh 反而延长有效期，`docs/progress/progress.json` 的 `ph17-t1` 已把「撤销后立即重签」列为未修缺口 |

### F. 跨 Agent 组合

| 条目 | 判定 | 证据 | 残余风险 |
|---|---|---|---|
| F25 系统级涌现安全 | 不适用 | 全仓无对应实体；`docs/progress/progress.json` 的 `ph17-t1` 已记录「单租户、无跨 Agent 通信」；零命中见 `tests/test_semantic_authorization_review.py` | 无组合拓扑，也就没有组合涌现风险的评估对象；不能据此推断「组合已安全」 |
| F26 Agent-Ensemble / Ensemble Trifecta | 不适用 | 全仓无对应实体；零命中见 `tests/test_semantic_authorization_review.py` | 无 Ensemble 编排实体，本仓是单进程单租户 |
| F27 纵向评估 | 不适用 | 全仓无对应实体；`scripts/check_security_boundaries.py` 是本仓自己的 20 项离线静态门禁，不是跨层纵向评估体系；零命中见 `tests/test_semantic_authorization_review.py` | 没有跨层 / 跨版本的纵向评估，只有常规回归与静态门禁；勿把那 20 项误当成这套清单的通过证据 |
| F28 司法管辖 / 后量子 | 不适用 | 全仓无对应实体；`src/soapbot/security/crypto.py` 用 Fernet，`src/soapbot/security/tokens.py` 用 `HS256`；零命中见 `tests/test_semantic_authorization_review.py` | 无辖区策略，密码学是常规对称加密与 HMAC，不具备后量子属性 |

## 3. 不适用实体名单

判为「不适用」的 10 条主张：A1、A5、A6、B8、E22、E24、F25、F26、F27、F28。
判为「未知」的 1 条主张：D20。这两组编号由 `tests/test_semantic_authorization_review.py`
与判定表交叉校验：把其中任意一行改成「已覆盖」都会让门禁变红。

以下标识符在 `src/soapbot/**/*.py` 中做大小写不敏感精确匹配，由
`tests/test_semantic_authorization_review.py` 断言**零命中**。测试文件不参与扫描：
它们必须引用这份名单才能断言其缺席，把测试算进去等于检查自己的词汇表；
真正的运行时实体只会出现在 `src/` 下：

```
mandate, settlement, ensemble, trifecta, broker, credential_decay, jurisdiction, post_quantum, calibration, semantic_frame
```

两个容易误报的地方，先写清楚：

- `dormant` 有 2 处命中，但都在散文注释里（`src/soapbot/memory/db.py` 提到一个休眠的列、
  `src/soapbot/adapters/qq_official.py` 提到休眠维护），**不是** Agent 休眠逻辑，因此不列入
  上面的零命中名单。
- `settle` 词根的命中全不是结算实体：`Promise.allSettled`、子进程 `_settle_stderr`，
  以及 `docs/progress/progress.json` 里对同名方法的描述。

**没有「已通过」可写**：这 10 个词对应的 10 条不适用主张，判定列一律是「不适用」，
全文任何位置都不得把它们与「已通过 / 已覆盖 / verified」连在一起。该约束同样由测试锁定。

## 4. 残余风险汇总

1. **语义层未覆盖是有书面依据的既定事实**，不是本轮新发现：
   `docs/plugin-security-review.md` 已写明无法判定「这次调用是否正当」，也无法阻止
   正则类注入 / 脱敏被绕过。D17 的执行级门控挡的是来源与注册表，不是语义正当性。
2. **证据在信任域内**：`src/soapbot/plugins/attestation.py` 自述不是密码学签名、
   `signature` 恒为空；同进程插件可绕过 surface facade。任何「域外可信证据」的说法
   在本仓都不成立。
3. **可恢复性是全量而非轨迹级**：`scripts/restore.py` 只能整库回滚，
   `src/soapbot/core/trace.py` 重启即丢失，没有 replay。
4. **一处静态测量盲区**：D20 的跨调用数据驻留判「未知」。静态扫描既证明不了隐式
   残留不存在，也不能把「没有显式策略」写成「已满足」。要收敛它，需要运行期污点追踪，
   属于新工作，本轮不做也不假装做了。
5. **固定 TTL 令牌**：`src/soapbot/security/tokens.py` 的 72 小时 TTL 与
   `src/soapbot/api/auth.py` 的 `/refresh` 意味着长期闲置的凭据不会自动衰减；
   这是 E24 判不适用的附带事实，也是运营上仍需人工轮换的理由，见
   `SECURITY.md` 的「凭据轮换」。

## 5. 自锁校验

`tests/test_semantic_authorization_review.py` 只读文档与源码文本，不启动服务、不碰数据库：

- 解析六张判定表，校验表头、四档取值、行数下界；
- **每一行**（含不适用与未知）的证据列都必须含至少一个真实存在的仓库相对路径，
  不适用行还必须指向静态缺失断言本身；
- 交叉校验不适用 / 未知编号与判定列，并断言名单里的每个词在源码与测试中零命中；
- 禁止把不适用实体与「已通过 / 已覆盖 / verified」写在同一句；
- 含反向用例：篡改判定、把证据路径换成不存在的文件、改坏表头、删掉一行，
  解析器都必须报错。

这锁住的是**判定的诚实性**，不是系统安全性。文档可以更新，但把「不适用」悄悄改成
「已通过」会立刻让测试变红。

相关：本仓库自身的威胁模型见 [security-model.md](security-model.md)，
20 项可执行契约见 [security-boundaries.md](security-boundaries.md)。

# 安全策略

## 报告漏洞

**不要开公开 issue。**

优先用 GitHub 的私密漏洞报告（仓库 Security 标签页 → Report a vulnerability）。
若不适用，发邮件给维护者，标题以 `[SECURITY]` 开头。

请包含：

- 受影响的版本（`soapbot version` 输出）
- 复现步骤或最小复现脚本
- 实际影响（能读到什么 / 能执行什么 / 需要什么前提）
- 你希望的披露时间线

**不要**在报告里附带真实的密钥、数据库或聊天记录。用你自己构造的样本。

## 响应时间

| 阶段 | 目标 |
|---|---|
| 确认收到 | 3 天内 |
| 初步判断（是否成立、严重级别） | 7 天内 |
| 修复或缓解措施 | 视严重级别，通常 30 天内 |

这是个人维护的项目，时间为尽力而为。若漏洞已公开在野利用，请直接说明，我会优先处理。

## 安全模型

理解下面这些边界，有助于判断一个问题是不是漏洞。

### 信任边界

| 组件 | 信任级别 | 说明 |
|---|---|---|
| 群成员消息 | **不可信** | 一律当作攻击者可控输入。见 `sanitize` 与 `injection_screen` 阶段 |
| 插件 | **不可信** | 默认进程隔离运行；能力逐项授权；`manifest_digest` 钉住被评审的确切字节 |
| Provider 响应 | **不可信** | 模型输出可能包含指令注入载荷，进入工具循环前需过滤 |
| 知识库文档 | **不可信** | 以 `wrap_untrusted(kind="knowledge")` 包裹后进入提示词 |
| MCP 服务 | **不可信** | 只允许 `config/mcp.yaml` 中显式声明的命令；禁止从网络取命令；子进程只继承白名单环境变量，拿不到主密钥与 provider 密钥 |
| 公开网页正文 | **不可信** | `browse` 能力面抓取的标题、描述、正文与价格都是攻击者可在页面上布置的文本。只作确定性规格提取与限额预检的输入，绝不作为授权依据、不直接拼进提示词的系统段；金额必须能回指页面上的 `product:price:amount` 或 ¥ 数字 |
| 管理员 | **可信** | 但操作仍需审计，且配置写入走 diff 确认 |

### 明确不防的事

诚实地列出边界，比声称「已加固」更有用：

- **不防拥有宿主机 root 的攻击者**。能读 `data/` 就能读数据库与密钥。
- **不防 Provider 作恶**。你把自己的密钥交给第三方 API，它能看到全部提示词与上下文。
- **不防提示词注入的语义后果**。过滤器拦已知模式，不能保证「模型一定不照做」。
  因此真正的防线是能力最小化：即使模型被说服，工具层仍然校验角色与参数。
- **不防拒绝服务**。消息洪泛会使服务变慢；限速是缓解，不是防护。
- **不防供应链中的恶意代码**。依赖版本已钉死；CI 用 `pip-audit` 对照已知漏洞库
  扫描，Dependabot 每周提议升级。但这只覆盖「已公开的 CVE」，不审计依赖源码，
  也不防投毒或仿冒的上游包。

## 已知的加固措施

- 引导令牌一次性消费，文件权限 `0600`；未消费时跨重启复用同一值，兑换成功后
  删除文件并留下 `init_token.redeemed` 标记（重启不会自动重新开放登录，需
  `soapbot token --reset`）
- 插件密钥用 Fernet 加密，**没有主密钥就拒绝存储**：`ctx.storage` 抛
  `StorageUnavailable`，隔离路径的 `storage.set` 抛同一异常，两条路径行为一致。
  早期版本在缺密钥时回落到明文存储并只打一条告警——这是错的：从插件侧看两者
  无法区分，密钥会静默落进数据库，等到备份被拷走才发现。现在缺密钥是**立即失败**，
  可观测，且不会产生任何明文行
- 审计日志记录操作与字段名，**不记录值**
- 配置写入：`base_hash` 乐观锁 + `approved_hash` 二次确认，防止覆盖他人改动
- 插件安装：zip slip 规范化、体积/数量上限、临时目录 + 原子移动、
  `manifest_digest` 由服务端重算
- 插件 IPC：**不用 pickle**，长度前缀 JSON；每次调用一个随机 correlation id，
  `result` 与 `call` 帧都必须绑定它，伪造/迟到帧丢弃且未绑定的回调不进入授权层；
  能力与会话 scope 的判定始终在父进程
- 插件 IPC 预算：父/子两端入站与出站、一次性 runner 的请求与回包共用同一个
  `MAX_FRAME_BYTES`；超限错误带上限与实际字节；stdout 由常驻 reader 排空，
  帧洪水会终止进程树而不是撑大宿主内存
- 插件子进程环境：`sanitize_env()` 白名单，不继承宿主凭据；`SOAPBOT_PLUGIN_*`
  是唯一可转发前缀
- 插件进程治理：`SOAPBOT_MAX_PLUGIN_WORKERS`（默认 16，范围 1..64，0 非法）、
  退出看护 reap、关闭时统一 `stop_all()`；熔断只能显式重置
- 离线门禁与巡检：`make ipc-audit` / CI `Plugin IPC audit` 固化否定式不变量；
  `plugin-worker-guard.timer` 每 5 分钟**只读**报告 worker 数、僵尸态与健康接口，
  绝不自动重启
- 容器：non-root（uid 10001）、只读根文件系统、`cap_drop: ALL`、
  `no-new-privileges`、宿主机侧仅绑定 loopback
- 会话凭据：`HttpOnly` + `SameSite` Cookie，页面脚本读不到；写操作另需
  `X-CSRF-Token` 与同源 `Origin`。脚本/CLI 仍可用 Bearer，两者共用同一套撤销与过期
- 认证分级：管理路由按 `OWNER / ADMIN / MEMBER` 声明最低角色；回环只读不再等于
  owner，写操作一律要凭据（`SOAPBOT_STRICT_LOOPBACK_AUTH` 默认开）
- 错误响应：全局 `AppError` 映射，只回稳定短句与类别标签，完整异常进服务端日志；
  响应不含堆栈、不含异常原文
- 日志出口：`json.dumps` 序列化，控制字符（含换行）转义后再写；结构化字段带
  `trace_id` / `message_id` / `plugin` / `provider`；日志环不含 traceback
- 日志内容：Provider 响应正文不进 `last_error`、不进日志环；用户消息正文不写日志；
  慢调用按 `SOAPBOT_SLOW_CALL_MS` 告警，成功调用降为 DEBUG
- 输入与上传：正则入口先按 `SOAPBOT_MAX_REGEX_INPUT_CHARS` 截断；上传校验 zip
  魔数与条目后缀白名单；`doc_id` 由统一函数校验
- 第三方子进程环境：插件与 MCP 服务共用 `core/proc_env.py` 的同一份白名单，
  只转发 `SAFE_ENV_KEYS` 与显式声明的变量；门禁禁止任何子进程继承 `os.environ`
- 不可见字符：注入检测、记忆校验、工具文本清洗与 id 归一化共用 `core/text.py` 的
  **一张**表（含 Unicode isolate `U+2066–U+2069`）；门禁禁止任何模块自建副本
- 备份：`scripts/backup.py` 用 SQLite 在线备份 API 取一致性快照（WAL 下直接拷文件
  会漏掉未 checkpoint 的页），归档带 `manifest.json`（逐文件 sha256、格式版本、
  生成时间），写入时先建 `0600` 临时文件再 `rename`；`deploy/backup.sh` 在 app 镜像
  内跑同一脚本（`--network none --cap-drop ALL --security-opt no-new-privileges`，
  数据卷只读挂载）
- 恢复：`scripts/restore.py` 先解到 staging 逐项校验（成员路径白名单、sha256、
  `PRAGMA integrity_check`）再原子替换；旧库降级为 `soapbot.db.pre-restore-<stamp>`
  而不是删除；恢复出的 `*.key` 一律 `chmod 0600`；任一校验失败则不动生产文件
- 归档即凭据：里面含 `data/secret.key`、`data/jwt.key` 与 `data/.env`（否则库内
  `enc:v1:` 值无法还原）。归档必须按密钥管理：`0600`、不放共享目录、不进对象存储
  的公开桶、不随工单附件传递
- 20 项契约：`scripts/check_security_boundaries.py` 在 CI 双矩阵与 `make check`
  中运行，逐条打印证据行

20 项逐条证据与残余风险见 [docs/security-boundaries.md](docs/security-boundaries.md)，
认证行为见 [docs/security-model.md](docs/security-model.md)。

## 部署基线

```bash
soapbot doctor --strict
```

返回非零表示存在高危配置。`--strict` 适合放进部署脚本作为门禁。

生产环境必须做：反向代理终止 TLS、面板仅监听 loopback、`SOAPBOT_MASTER_KEY_FILE`
指向独立密钥文件（或确保 `data/` 权限受限）、定期备份。

## 凭据轮换

删除一个含硬编码口令的文件**不会**让那个口令失效。Git 历史、镜像层、CI 日志和
别人克隆的仓库里都还有它。凡是曾经以明文出现在仓库或脚本里的口令，都按「已泄漏」
处理：

- 立刻在源头改口令（路由器 / NAS / SSH 账号 / 面板账号），不要在仓库里「改成新值」
- 本仓库历史上随部署脚本一起删除的口令，同样必须轮换；不要依赖 force-push 或
  改写历史来「清理」——推送过的内容要当作已被复制
- 新口令只出现在 `.env`（`0600`，不进 git）或 `env:VAR` 引用里，不要回到脚本
- 主密钥（`data/secret.key`）轮换后，库里的 `enc:v1:` 值需要重新加密；不要直接
  替换文件，否则旧密文全部解不开

## 提示可被提取的假设

系统提示、人格卡与工具说明都按「**提示最终会被提取**」来设计：模型可以复述、改写，
或被注入内容诱导吐出片段。安全设计因此**不依赖提示保密**——凡是不能公开的内容（密钥、
口令、别人的数据），从一开始就不放进提示。

已经做到的：系统提示不写入日志、`MessageTrace`、数据库与插件上下文（见
`docs/security-model.md` 的「已验证的不外泄路径」）；`providers/router.py` 在 provider
错误体里只保留 `kind + HTTP status`。

**不承诺的**：输出侧过滤（注入筛查、canary 边界标记）只是兜底，不是保证。它能降低
「一次明显的泄露被原样发出去」的概率，挡不住编码、改写或分片外带。

## 轨迹、审批记录与成本预算的边界

这三件事常被混成一句「有完整审计」，实际是三个位置、三种强度：

| 能力 | 实际位置 | 强到什么程度 |
|---|---|---|
| 决策轨迹 | `src/soapbot/core/trace.py` 的进程内环 | 容量上限 500 条，**重启即丢**；`summary()` 明确 `historical: false`、`recoverable: false`，并带 `boot_id`。**不满足 6 个月保留**，也**不可回放** |
| 人类审批记录 | `src/soapbot/security/audit.py` 的审计流；支付审批另在 `src/soapbot/budget/store.py` 的 SQLite 账本 | 记录谁在何时批准或拒绝了什么，可按 `request_id` 查；与轨迹用 `trace_id` 关联，不是一个对象 |
| 支付成本预算 | `src/soapbot/budget/store.py` 的 `_totals(session_key, period)` | 按会话 + 周期累计 `committed` 与 `reserved`，剩余额度 = 上限 − 已提交 − 已预留 |

日志上下文（`src/soapbot/core/log_context.py`）同时绑定 `request_id`、`trace_id` 与
`message_id`，所以一次请求的日志、轨迹与审批记录可以交叉定位——但这靠三个字段拼起来，
不是靠一个统一的事件存储。

两处**真实缺口**，不写成已覆盖：

- **轨迹没有持久化，也没有 6 个月保留**。要回答「谁在什么时候审阅了哪一次决策」并保留
  ≥6 个月，需要把轨迹（或至少审批与工具调用事件）落到数据库并加保留策略；本轮没有做。
- **模型 token 没有会话累积上限**。`src/soapbot/providers/router.py` 的 `ProviderStat`
  只统计调用次数、失败次数与延迟，不累计 token，也就没有「一次会话最多花多少 token」
  的拒绝路径；本轮没有做。

## 流入信息的完整性校验

参数来源标签、结构合法性与资源校验都在 `src/soapbot/security/provenance.py` 的
`vet_arguments()` 里独立于语义解析执行：重新校验 `well_formed()`（来源必须在已知集合、
已验参数名必须非空），拒绝 `forged_provenance` 与 `data_only_origin`，模型来源的资源
参数必须由宿主注入的 `resource_check` 返回真——校验器缺失或抛错都算拒绝，
`mark_vetted` 只能由宿主调用。记忆侧 `src/soapbot/memory/handoff.py` 的
`Handoff.well_formed` 与解析后重校验同构。

**边界**：这证明「标签没被伪造、结构没坏」，不证明「这次调用在语义上正当」。

## 长期保密与「先收集后解密」

本仓库的静态加密是 Fernet（对称）与令牌签名 HS256（HMAC），都不是后量子方案，也
没有前向保密。这意味着一条**今天被复制走、今天解不开**的密文，可能在多年后因为
密钥泄漏或算力变化而被解开。因此：

- 备份归档含 `secret.key`、`jwt.key`、`.env` 与整个数据库，必须按**凭据**而非
  普通文件管理（`0600`、加密存放、限定保留期）；归档泄漏等价于当下明文泄漏
- 长期敏感内容不要只指望「现在加密了」：缩短保留期、到期删除，是这里唯一能真正
  降低该风险的控制
- 若将来引入签名方案，优先选择可版本化替换、且能迁移到哈希基签名的格式；
  `plugins/attestation.py` 的 `SCHEMA_VERSION` 与 `signable_payload()` 保留了这个
  迁移点，但**当前 `signature` 恒为空，不是签名**，不要把它当作抗抵赖证据
- 这条威胁在 `docs/optimization-triage.md` 中被判为「后量子不适用、但先收集后解密
  值得进威胁模型」，属于文档级落地，不代表密码学能力升级

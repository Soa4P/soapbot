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
| MCP 服务 | **不可信** | 只允许 `config/mcp.yaml` 中显式声明的命令；禁止从网络取命令 |
| 管理员 | **可信** | 但操作仍需审计，且配置写入走 diff 确认 |

### 明确不防的事

诚实地列出边界，比声称「已加固」更有用：

- **不防拥有宿主机 root 的攻击者**。能读 `data/` 就能读数据库与密钥。
- **不防 Provider 作恶**。你把自己的密钥交给第三方 API，它能看到全部提示词与上下文。
- **不防提示词注入的语义后果**。过滤器拦已知模式，不能保证「模型一定不照做」。
  因此真正的防线是能力最小化：即使模型被说服，工具层仍然校验角色与参数。
- **不防拒绝服务**。消息洪泛会使服务变慢；限速是缓解，不是防护。
- **不防供应链**。依赖版本已钉死，但不审计依赖源码。

## 已知的加固措施

- 引导令牌一次性消费，文件权限 `0600`；未消费时跨重启复用同一值，兑换成功后
  删除文件并留下 `init_token.redeemed` 标记（重启不会自动重新开放登录，需
  `soapbot token --reset`）
- 插件密钥用 Fernet 加密；无密钥时**降级为明文并告警**（这一条是刻意的：
  密钥文件读不到时不静默失败，否则运维会以为加密生效了）
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
- 18 项契约：`scripts/check_security_boundaries.py` 在 CI 双矩阵与 `make check`
  中运行，逐条打印证据行

18 项逐条证据与残余风险见 [docs/security-boundaries.md](docs/security-boundaries.md)，
认证行为见 [docs/security-model.md](docs/security-model.md)。

## 部署基线

```bash
soapbot doctor --strict
```

返回非零表示存在高危配置。`--strict` 适合放进部署脚本作为门禁。

生产环境必须做：反向代理终止 TLS、面板仅监听 loopback、`SOAPBOT_MASTER_KEY_FILE`
指向独立密钥文件（或确保 `data/` 权限受限）、定期备份。

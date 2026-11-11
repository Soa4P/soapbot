# 使用说明

README 只放启动命令。这里放装好之后要用的东西。

## 一条消息走完的顺序

```text
dedup → guard → whitelist → wake → strip → sanitize
      → injection_screen → persist → skip_reply → authorization
      → command → plugin_cmd → plugin_hook
      → persona → recall → knowledge → model(+tools) → safety
      → reply → persist_reply → memory_write
```

顺序就是边界：`guard` 必须先于白名单，白名单才能判断谁在哪儿说话；`command` 排在
准入之后，没权限的人碰不到它。改顺序等于改安全模型，细节在
[architecture.md](architecture.md)。

`persist` 排在 `skip_reply` 前面：先记事，再决定要不要开口。所以「只在 A 群采集、
在 B 群回复」才成立——没被 @ 的消息照样进记忆，只是不会得到回复。

## 面板 13 页

编号固定，加了新页面也不重排，所以「第 04 页」这个说法可以一直用。

| 页 | 内容 |
|---|---|
| 01 总览 | 进程 / 适配器 / 流水线三层状态 |
| 02 运行状态 | 运行时、调度器、启动错误 |
| 03 插件 | 批准 / 撤销 / 加载 / 卸载 |
| 04 安全审计 | 审计事件、拒绝记录、权限矩阵 |
| 05 记忆与知识库 | 会话、时间线、知识入库 / 删除 |
| 06 额度审批 | 账本与二次审批 |
| 07 模型与人格 | Provider 可视化编辑（带 diff 确认）+ 人格卡只读 |
| 08 运行日志 | 结构化日志 |
| 09 流水线追踪 | 22 个环节的拓扑、逐环节耗时、中止点、换序沙箱 |
| 10 运行指标 | 延迟分位、累计计数、结果分布 |
| 11 插件包安装 | 上传 zip 安装（不等于批准）、能力风险分级 |
| 12 系统设置 | 界面语言、回复语言、语音、MCP 连接状态、运行时信息 |
| 13 聊天存档 | 登录、会话列表、消息流、备注；账号与邀请码在[存档文档](chat-archive.md) |

## 只在哪些群说话、在哪些群记事

默认全开：进哪个群就在哪个群回，也把消息记进记忆。收窄去第 12 页 → 群范围：

- **回复群**：只在列出的群回话。留空 = 全都回。
- **采集群**：只在列出的群存档、写记忆。留空 = 全都记。

两行互相独立，可以让它在热闹的大群里只听不说，或者只回某几个群但不记东西。
改动写进 `.env`，重启后生效。`PRIVATE_ALLOWLIST` 的语义相反：留空 = 谁都不行。

## 语音

语音转写和语音回复都已实装，默认关着。开关在第 12 页 → 语音，两个开关分别管
「听懂语音」和「用语音回答」，音色也可选。合成失败自动退回文字，不让整条回复丢掉。
缺后端时页面会写明缺什么，不静默降级。环境变量见
[configuration.md](configuration.md)。

## 聊天存档与多人查看

第 13 页是**只读**存档：QQ 仍是消息来源，这一页只负责回看。它有一套独立于面板令牌的
账号体系，因为面板令牌是「拿到就全见」，不适合给第二个人。

| 你是谁 | 怎么进来 | 看得到什么 |
|---|---|---|
| 所有者 | 用邀请码注册的 owner 账号，或首次在服务器本机用 bootstrap 令牌建的第一个账号 | 全部会话 |
| 成员 | 所有者发的一次性邀请码注册 | 只有被授权的那几个会话 |

三个要点：

- **输入只写备注**，落库 `role=note`、`adapter=web`、`delivered=false`，整条路径不 import
  适配器。所以页面上写的东西对方在 QQ 里永远看不到；这不是提示语，是代码结构。
- **越权返回 404 而不是 403**：403 等于确认「这个会话存在」，把别人的群名也漏出去了。
- **端开关**：`SOAPBOT_CHAT_WEB_ENABLED`（默认开）、`SOAPBOT_CHAT_APP_ENABLED`、
  `SOAPBOT_CHAT_DESKTOP_ENABLED`（默认关）。全关时 `/api/chat/*` 404，像没装过。

邀请码怎么发、账号怎么停用、会话怎么授权，见 [chat-archive.md](chat-archive.md)。

## 远程看面板

服务器上的面板只绑 `127.0.0.1`，这是安全默认，不是缺陷。用 SSH 隧道映射，
而不是把端口开到公网：

```bash
ssh -N -L 6185:127.0.0.1:6185 user@your-server
# 本地打开 http://127.0.0.1:6185
```

Windows 仓库里的 `open-remote-panel.bat` 做同一件事。

## 第一次登录

本机读页面不用凭据；改状态需要。浏览器拿到的是 `HttpOnly` Cookie，登录后由
服务端下发，前端不保存 token。脚本和 CLI 仍可用 Bearer：

```bash
curl -X POST http://127.0.0.1:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"init_token": "把 init_token.txt 里那一串粘到这里"}' \
  -c cookies.txt
```

**令牌文件在哪、怎么读、重启后找不到怎么办**，见
[部署 · 第一次登录](deploy-quickstart.md)：那里有 Windows 云服务器上可直接复制的
PowerShell 命令，以及用 `/api/auth/status` 查真实路径和状态的方法。三条要点：

- 没用过时重启不会换值；登录成功一次后文件**立刻删除**，留下 `init_token.redeemed`，
  重启**不会**自动重新发放。
- 文件不存在或登录返回 401 时，在服务器本机执行
  `python -m soapbot.cli token --reset`，它会打印一枚新令牌，然后**必须重启服务**。
- 服务化安装只给路径；本机 `start-panel.bat` 会在启动窗口直接显示令牌值。

登录响应里的 `access_token` 是给脚本和 CLI 用的，面板忽略它。登出会撤销 token
并清除 Cookie；cookie 会话的写操作要带 `X-CSRF-Token`，值取 `soapbot_csrf`。
角色门槛与回环读写分离的准确行为见 [security-model.md](security-model.md)。

## 更多文档

| 想看什么 | 去哪 |
|---|---|
| 从零接上 QQ：NapCat 怎么起、二维码怎么扫、连不上怎么查 | [qq-napcat-setup.md](qq-napcat-setup.md) |
| 人格卡怎么写、怎么绑到某个群 | [personas.md](personas.md) |
| MCP 是什么、要不要开、怎么配 | [mcp.md](mcp.md) |
| 每一个环境变量、配置文件、依赖 | [configuration.md](configuration.md) |
| 架构、模块划分、一条消息走完全程 | [architecture.md](architecture.md) |
| 部署、备份、故障排查、升级 | [operations.md](operations.md) |
| 写插件、能力授权、进程隔离 | [plugins.md](plugins.md) |
| 每个平台支持什么、群管命令 | [capabilities.md](capabilities.md) |
| 多用户账号、邀请码、只读存档、端开关 | [chat-archive.md](chat-archive.md) |
| 20 项边界逐条证据 | [security-boundaries.md](security-boundaries.md) |
| 参考了哪些外部设计、有哪些没抄 | [reference-ecosystem.md](reference-ecosystem.md) |
| 威胁模型与已加固项 | [security-model.md](security-model.md) |
| 借鉴来源与版权边界 | [provenance.md](provenance.md) |

## 免责

- 个人号接入风险：通过 OneBot 协议（NapCat / Lagrange 等第三方协议端）接入 QQ
  个人账号，存在被平台风控、限制甚至封号的风险。本项目只实现协议客户端，不内置
  协议逆向代码，风险由使用者承担。
- 官方机器人审核：接入 QQ 官方开放平台需自行注册并通过审核；群聊场景还要额外
  申请开通。
- B 站数据：开放平台协议禁止以自动程序获取平台数据。默认走 L1 静默模式（仅免签名
  公开元数据），升到 L2 需自行确认合规性。L3（登录态）未实现。
- 支付：不持有支付凭据、不调用支付 API、不自动扣款。

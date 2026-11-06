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

## 面板 12 页

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
| 09 流水线追踪 | 20 个环节的拓扑、逐环节耗时、中止点、换序沙箱 |
| 10 运行指标 | 延迟分位、累计计数、结果分布 |
| 11 插件包安装 | 上传 zip 安装（不等于批准）、能力风险分级 |
| 12 系统设置 | 界面语言、回复语言、语音、MCP 连接状态、运行时信息 |

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
  -d '{"init_token": "<data/init_token.txt 里的值>"}' \
  -c cookies.txt
```

引导令牌存在 `data/init_token.txt`（权限 0600）。没用掉之前重启服务不会改变它；
用掉之后文件被删除，磁盘上不留凭据。再要一枚，在服务器本机执行
`python -m soapbot.cli token --reset`，重启后生效。

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
| 18 项边界逐条证据 | [security-boundaries.md](security-boundaries.md) |
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

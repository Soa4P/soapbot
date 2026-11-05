# soapbot

QQ 群里的 AI 机器人。有人 @ 它，它就用人格卡设定的语气回话；回话前会翻本群历史、长期记忆和知识库；图片会真的送进视觉模型；花钱的操作要你点头；第三方插件跑在独立进程里，权限一项一项给。

**它不做什么**：不含任何 QQ 协议逆向代码；不持有支付凭据、不调用支付 API。

---

## 这东西到底怎么跑的

一个 Python 脚本调一次模型不叫机器人。这里每条消息要过一条流水线：

```text
dedup → guard → whitelist → wake → strip → sanitize
      → injection_screen → persist → skip_reply → authorization
      → command → plugin_cmd → plugin_hook
      → persona → recall → knowledge → model(+tools) → safety
      → reply → persist_reply → memory_write
```

**顺序就是安全边界**：`guard` 必须先于白名单，白名单才能判断「谁在哪儿说话」；`command` 排在准入之后，没权限的人永远碰不到它。改顺序等于改安全模型——细节在 [docs/architecture.md](docs/architecture.md)。

`persist` 特意排在 `skip_reply` 前面：**先记事，再决定要不要开口**。这样「只在 A 群采集、在 B 群回复」才成立——没被 @ 的消息照样进记忆，只是不会得到回复。

---

## 三步跑起来

需要 Python **3.12+**。只在你要改面板时才需要 Node 20+；面板产物已随包发布，clone 下来直接能开。

**1. 装**

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"        # Windows: .\.venv\Scripts\python.exe ...
```

Windows 也可以直接双击 `start-panel.bat`：它自己建 venv、装依赖、健康检查通过后开浏览器，任何一步失败都会停在窗口里说明原因。

**2. 起面板**

```bash
python -m soapbot.cli start        # → http://127.0.0.1:6185
```

没有浏览器？`python -m soapbot.cli setup` 用交互向导配模型和 QQ 接入，校验不过不写盘。

**3. 在面板里填两样东西**

第 07 页填「模型 Key」和「QQ 接入」，两行各点一次「测试」，两个都变绿，回群里发一句话。

不用手改任何 YAML。`config/` 里是模板，首次启动播种到 `data/config`，之后面板改的都是 `data/config` 那一份，所以 `git pull` 不会把你的配置改回去。

### 它只在哪些群说话、在哪些群记事

默认全开：进哪个群就在哪个群回，也把消息记进记忆。想收窄，去**第 12 页 → 群范围**填两行群号：

- **回复群**：只在列出的群回话。留空 = 全都回。
- **采集群**：只在列出的群存档、写记忆。留空 = 全都记。

两行互相独立，所以可以让它在热闹的大群里只听不说，或者只回某几个群但不记东西。改动写进 `.env`，**重启后生效**。

### 语音是真的能用的

语音转写（把群友的语音变成文字）和语音回复（把回复合成语音发出去）都已经实装，默认关着。在哪开：**第 12 页 → 语音**。

两个开关分别控制「听懂语音」和「用语音回答」，另外可以选音色。合成失败会自动退回文字，不会让整条回复丢掉。它需要系统里有可用的语音合成后端；缺了会在第 12 页直接告诉你缺什么，而不是静默降级。

### 面板在别的机器上

服务器上的面板只绑 `127.0.0.1`（安全默认，不是缺陷）。要远程看，用 SSH 隧道把它映射过来，而不是把端口开到公网：

```bash
ssh -N -L 6185:127.0.0.1:6185 user@your-server
# 然后本地打开 http://127.0.0.1:6185
```

Windows 仓库里有 `open-remote-panel.bat`，做的是同一件事。

### 第一次登录

本机访问不用令牌。从别处访问要先换一张：

```bash
curl -X POST http://127.0.0.1:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"init_token": "<data/init_token.txt 里的值>"}'
```

令牌存在 `data/init_token.txt`（权限 0600）。**没用掉之前重启服务不会改变它**；用掉之后文件会被删除，磁盘上不留凭据。再要一枚得在服务器本机执行：

```bash
python -m soapbot.cli token --reset    # 重启服务后生效
```

面板的登录框里有这几个路径和命令的复制按钮，不用记。

---

## 面板有 12 页

编号是固定的，不会因为加了新页面就重排。所以「第 04 页」这个说法可以一直用。

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
| 11 插件包安装 | 上传 zip 安装（**不等于批准**）、能力风险分级 |
| 12 系统设置 | 界面语言、回复语言、语音、MCP 连接状态、运行时信息 |

---

## 坏了先看这里

**收到消息但不回复。** 按顺序查三件事：模型端点通不通（`GET /api/providers`）；有没有 @ 它或说唤醒词（唤醒词在人格卡里）；`GET /api/runtime` 的 `metrics.halted` 涨没涨——中止原因会写进日志，`reason=not_woken` 和 `reason=private_not_allowed` 的处置完全不同。

**私聊没反应。** 默认谁都不能私聊。把 QQ 号加进 `SOAPBOT_PRIVATE_ALLOWLIST`，或显式设 `SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true`。

**插件显示「已启用」但不干活。** 看「已授权」是不是「部分」——清单新增了能力而批准没覆盖就会这样。`GET /api/plugins` 里 `approval.manifest_changed` 为 `true` 说明清单在批准后被改过。

**QQ 掉线了，扫码也扫不进去。** 先确认协议端还活着：`GET /api/protocol/napcat/status`。如果它显示 `logged_in: false` 且二维码很久没变，说明 NapCat 的登录已经过期（它自己不会换新码）——重启 NapCat 会出一张新的。这张卡片现在会写明码的年龄和上次失败原因，不再假装在刷新。

**控制台白屏。** `GET /` 返回的是指引文字而不是 HTML，说明 `src/soapbot/webui/dist/` 缺失。clone 自带该产物，只有手动清理过才需要 `make ui`。

**`SettingsError: error parsing value for field ...`** 列表型变量写坏了。用 `a,b`、`a;b` 或 `["a","b"]` 都行。

**NapCat 每 72 小时准时掉一次。** Windows 计划任务默认 `ExecutionTimeLimit=PT72H`，到期会把 NapCat 连同 QQ 一起杀掉。用 `scripts/install_napcat_task.ps1` 注册，它设成 `PT0S` 并加开机自启。

---

## 安全默认值

- 管理 API 对非本机来源要求签名令牌；本机免令牌只是便利，不是边界。
- 私聊默认拒绝。一条没被记录的私聊就是一条免费的数据外泄通道。
- 插件需要显式批准，权限按能力逐项授予，默认在独立进程中运行。
- Provider 配置写入需要 ADMIN 权限，并且必须走「读取 → diff → 确认 → 写入」；diff 由服务端用**与启动同一套解析器**校验后计算，审计日志只记字段名，不记值。人格卡仍只读。
- 审批不能由发起人完成；额度、配置、群管、记忆读写是**四个独立权限**。
- 模型输出若复述了不可信内容的 canary，整条回复丢弃，而不是尝试清洗。

部署前跑一次 `python -m soapbot.cli doctor --strict`，它会检查绑定地址、密钥来源、文件权限、插件隔离模式和上游端点。上线前请读 [docs/security-model.md](docs/security-model.md)。

---

## 更多文档

按你想做的事找：

| 想看什么 | 去哪 |
|---|---|
| 从零接上 QQ：NapCat 怎么起、二维码怎么扫、连不上怎么查 | [docs/qq-napcat-setup.md](docs/qq-napcat-setup.md) |
| 人格卡怎么写、怎么绑到某个群 | [docs/personas.md](docs/personas.md) |
| MCP 是什么、要不要开、怎么配 | [docs/mcp.md](docs/mcp.md) |
| 语音转写与语音回复怎么开 | [docs/configuration.md](docs/configuration.md) 的语音一节 |
| 架构、模块划分、一条消息走完全程 | [docs/architecture.md](docs/architecture.md) |
| 每一个环境变量、配置文件、依赖 | [docs/configuration.md](docs/configuration.md) |
| systemd / 容器 / Windows 计划任务 / 反向代理 / 升级 | [docs/deployment.md](docs/deployment.md) |
| 写插件、能力授权、进程隔离 | [docs/plugins.md](docs/plugins.md) |
| 每个平台支持什么、群管命令 | [docs/capabilities.md](docs/capabilities.md) |
| 威胁模型与已加固项 | [docs/security-model.md](docs/security-model.md) |
| 借鉴了哪些外部设计、版权边界 | [docs/provenance.md](docs/provenance.md) |

---

## 免责声明

- **个人号接入风险**：通过 OneBot 协议（NapCat / Lagrange 等第三方协议端）接入 QQ 个人账号，存在被平台风控、限制甚至封号的风险。本项目只实现协议客户端，**不内置任何协议逆向代码**，风险由使用者承担。
- **官方机器人审核**：接入 QQ 官方开放平台需自行注册并通过审核；群聊场景还要额外申请开通。
- **B 站数据**：哔哩哔哩开放平台协议禁止以自动程序获取平台数据。默认走 L1 静默模式（仅免签名公开元数据），升到 L2 需自行确认合规性。L3（登录态）**未实现**。
- **支付安全**：**不持有任何支付凭据、不调用支付 API、不自动扣款**。

## 许可证

MIT，见 [LICENSE](LICENSE)。其中说明了与 AstrBot（AGPL-3.0）的关系：参考其分层思路，未包含其代码。

变更记录见 [CHANGELOG.md](CHANGELOG.md)。

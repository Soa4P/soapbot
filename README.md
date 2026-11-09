# soapbot

QQ 群里的 AI 机器人。Python 3.12 / FastAPI / Vue3。第三方插件跑在独立进程里，
能力一项一项批准。

不内置 QQ 协议逆向代码，不持有支付凭据，不调用支付 API。

## 启动：按你的机器选一条

| 你的机器 | 用哪条 | 前提 |
| --- | --- | --- |
| Windows（已装 Python） | `scripts/install.ps1` | Python 3.12+ |
| Windows（没装 Python） | `deploy/windows-bootstrap.ps1 -Start` | 管理员 PowerShell；脚本自己下载并静默安装 Python 3.12 |
| Linux | `scripts/install.sh` | Python 3.12+ |
| Linux（容器加固版） | `deploy/docker-compose.yml` | Docker；**这条只有 Linux 能用** |

两条 Windows 路径注册的是**同一个**计划任务 `SoapbotBot`（SYSTEM、开机启动），默认目录
都是 `C:\soapbot`，可以互相覆盖升级；先用哪条只看这台机器上有没有 Python。

**为什么 Docker 那条 Windows 用不了**：不是 Docker Desktop 装没装的问题。容器配置用了
`user: 10001`、`read_only`、`cap_drop: ALL`、`seccomp`、`tini` 和 `0600` 权限位，全是
Linux 内核语义；验收脚本还要读 `/proc/1/comm`、跑 `systemctl`。逐条原因见
[部署文档](docs/deploy-quickstart.md)。Windows 的等价交付是 PowerShell 脚本（原生进程 +
计划任务），**它不带这些容器加固**，这个差别在部署文档里写明了。

**桌面端** `desktop/` 能打出 Windows 安装包（NSIS），**包里自带后端**：装完不需要单独
装 Python，双击就是托盘入口。它是**未签名**的，SmartScreen 会提示「未知发布者」，点
「更多信息 → 仍要运行」即可；原因与证书方案见[桌面端签名](docs/desktop-signing.md)。
构建命令与 CI 触发方式见[部署文档](docs/deploy-quickstart.md)。

```powershell
# Windows 已装 Python，管理员 PowerShell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 | iex

# Windows 没装 Python，管理员 PowerShell。下载后运行而不是管道执行：
# 这个脚本带 param() 块和 -Start 开关，直接 iex 会把参数吃掉。
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/windows-bootstrap.ps1 -OutFile "$env:TEMP\soapbot-bootstrap.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-bootstrap.ps1" -Start
```

```bash
# Linux
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.sh | bash
```

```bash
# Docker（仅 Linux）
docker compose -f deploy/docker-compose.yml up -d
```

装完打开 `http://127.0.0.1:6185`，一次性登录令牌在 `data/init_token.txt`（Docker 里是
`docker compose -f deploy/docker-compose.yml exec soapbot cat /data/init_token.txt`）。
脚本不会把令牌打进终端。

从源码跑（改代码时用）：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"      # Windows: .\.venv\Scripts\python.exe
python -m soapbot.cli start                      # http://127.0.0.1:6185
```

Windows 也可以双击 `start-panel.bat`：建 venv、装依赖、健康检查通过后开浏览器，
任何一步失败都停在窗口里说明原因。没有浏览器用 `python -m soapbot.cli setup`
走交互向导，校验不过不写盘。

## 装完之后：三步让机器人能回话

1. 打开 `http://127.0.0.1:6185`，用上面那个令牌登录。
2. 进**第 07 页「模型与人格」**，点一下你那家模型厂商的名字（接口地址和模型名已经
   预填好），粘贴 API Key，点同一行的**「测试」**，出绿灯再点**「保存」**。
3. 同一页填「QQ 接入」，也点一次「测试」。

不用改代码，不用手改 YAML：`config/` 是模板，首次启动播种到 `data/config`，`git pull`
不会覆盖你的那份。

**十家厂商的预填值、表里没有的厂商（MiniMax / 混元 / seed / Nemotron / Llama 等）怎么
自己加、本地模型怎么配、401 / 404 / 超时分别怎么读**，全在
[模型接入指南](docs/model-providers.md)。

三条路径的细节、常见失败、验证命令和卸载在
[部署文档](docs/deploy-quickstart.md)。面板 12 页、群范围、语音、远程访问和登录在
[使用指南](docs/guide.md)。

## 边界

- 面板只绑 `127.0.0.1`。远程看用 SSH 隧道，不要把 6185 开到公网。
- 回环客户端可以读，写操作需要凭据。会话是 `HttpOnly` Cookie，页面脚本读不到；
  写操作另需 CSRF 头与同源 `Origin`。Cookie 挡不住已经在页面里执行的 XSS，
  CSP 和输出转义各管各的那一段。
- 私聊默认拒绝。插件要显式批准，批准不等于自动加载。模型输出复述了不可信内容的
  canary，整条回复丢弃，不尝试清洗。
- 配置写入走「读取 → diff → 确认 → 写入」，diff 由服务端用与启动同一套解析器算。
  审计只记字段名，不记值。错误响应只给稳定短句和类别标签，完整异常进服务端日志。
- Provider 响应正文不进 `last_error`、不进日志环；用户消息正文不写日志。
- 正则匹配前截断输入，不是硬超时：标准库 `re` 没有超时参数，我们没有为此加依赖。
- 插件熔断不自动恢复，worker 巡检只读报告，不重启进程。
- 个人号经第三方协议端接入有被平台风控的风险，本项目只实现协议客户端。
  官方机器人审核、B 站数据合规、支付边界见 [SECURITY.md](SECURITY.md) 与
  [docs/provenance.md](docs/provenance.md)。

20 项边界逐条证据在 [docs/security-boundaries.md](docs/security-boundaries.md)，
认证与威胁模型在 [docs/security-model.md](docs/security-model.md)。

## 门禁

```bash
make check          # CI backend 的全部本地可跑门禁 + pytest（差集只有两项，见下）
cd webui && npm run verify
python -m soapbot.cli doctor --strict      # 部署前
```

`make check` 跑的是 CI `backend` 任务里**能在本机跑的全部**门禁：lint、version、
check-deps、console-encoding、deploy-check、contrast、a11y、gaps、doclinks、
ipc-audit、boundary-audit、desktop-check、pytest。只有两项不在其中，原因是它们
依赖本机没有的东西——`check_secrets.py --committed` 要读待审提交的 git 历史，
`pip-audit` 要联网。这个差集由 `tests/test_gate_parity.py` 断言，两边再漂移就会红。

三个静态门禁值得单独说：`scripts/check_plugin_ipc.py` 守插件进程边界，
`scripts/check_security_boundaries.py` 守 20 项安全与错误日志契约，
`scripts/check_desktop.py` 守桌面壳的 CSP、单实例与「不自己拉起后端」。它们只读
源码、打印证据行，失败就退出非零。

桌面壳在 [desktop/](desktop/)，构建需要 Rust 与 WebView2，`make desktop` 出安装包。
它只负责打开面板，不启动后端：进程生命周期归计划任务或 systemd，两个监管者抢
6185 端口是没人想调的故障。

## AI 审查

PR 会多一条由 `scripts/ai_review.py` 生成的评论，判 `safe` / `needs_review` /
`malicious` 并给出理由。它**只评论、只打标签，不批准也不合并** —— 合并决定始终由
上面那组确定性门禁和维护者做出。

判断不了的时候它说「判断不了」：模型超时、非 200、返回非法 JSON、或 diff 超过上限
被截断，一律降级为 `needs_review`。截断过的 diff **不会**被判成 `safe`，因为那等于
对没读过的文本下结论。

工作流用 `pull_request_target`（fork PR 才拿得到 secret），因此把 checkout 钉在
base commit、只通过 `gh pr diff` 读文本，从不执行 PR 里的代码。

配置：仓库 secret `DEEPSEEK_API_KEY`（必需）；variable `AI_REVIEW_MODEL`（可选，
默认 `deepseek-chat`）。没配 key 时它会在 PR 上写明「本次没有审查」，而不是装成
审查过、没问题。

部署、备份、巡检、故障排查和升级在 [docs/operations.md](docs/operations.md)。

MIT，见 [LICENSE](LICENSE)。变更记录见 [CHANGELOG.md](CHANGELOG.md)。

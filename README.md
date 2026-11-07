# soapbot

QQ 群里的 AI 机器人。Python 3.12 / FastAPI / Vue3。第三方插件跑在独立进程里，
能力一项一项批准。

不内置 QQ 协议逆向代码，不持有支付凭据，不调用支付 API。

## 启动

三条命令，选一条。Windows 和 Linux 只需要 Python 3.12+，Docker 连 Python 都不用装。

```powershell
# Windows，管理员 PowerShell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 | iex
```

```bash
# Linux
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.sh | bash
```

```bash
# Docker
docker compose up -d
```

装完打开 `http://127.0.0.1:6185`，一次性登录令牌在 `data/init_token.txt`（Docker 里是
`docker compose exec soapbot cat /data/init_token.txt`）。脚本不会把令牌打进终端。

从源码跑（改代码时用）：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"      # Windows: .\.venv\Scripts\python.exe
python -m soapbot.cli start                      # http://127.0.0.1:6185
```

Windows 也可以双击 `start-panel.bat`：建 venv、装依赖、健康检查通过后开浏览器，
任何一步失败都停在窗口里说明原因。没有浏览器用 `python -m soapbot.cli setup`
走交互向导，校验不过不写盘。

启动后在面板第 07 页填「模型 Key」和「QQ 接入」，两行各点一次「测试」。不用手改
YAML：`config/` 是模板，首次启动播种到 `data/config`，`git pull` 不会覆盖你的那份。

三条路径的细节、常见失败和卸载在 [docs/deploy-quickstart.md](docs/deploy-quickstart.md)。
面板 12 页、群范围、语音、远程访问和登录在 [docs/guide.md](docs/guide.md)。

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

18 项边界逐条证据在 [docs/security-boundaries.md](docs/security-boundaries.md)，
认证与威胁模型在 [docs/security-model.md](docs/security-model.md)。

## 门禁

```bash
make check          # lint / contrast / a11y / gaps / doclinks / ipc-audit / boundary-audit / desktop-check / pytest
cd webui && npm run verify
python -m soapbot.cli doctor --strict      # 部署前
```

`make check` 与 CI 的 backend 双矩阵跑的是同一组命令。三个静态门禁值得单独说：
`scripts/check_plugin_ipc.py` 守插件进程边界，`scripts/check_security_boundaries.py`
守 18 项安全与错误日志契约，`scripts/check_desktop.py` 守桌面壳的 CSP、单实例与
「不自己拉起后端」。它们只读源码、打印证据行，失败就退出非零。

桌面壳在 [desktop/](desktop/)，构建需要 Rust 与 WebView2，`make desktop` 出安装包。
它只负责打开面板，不启动后端：进程生命周期归计划任务或 systemd，两个监管者抢
6185 端口是没人想调的故障。

部署、备份、巡检、故障排查和升级在 [docs/operations.md](docs/operations.md)。

MIT，见 [LICENSE](LICENSE)。变更记录见 [CHANGELOG.md](CHANGELOG.md)。

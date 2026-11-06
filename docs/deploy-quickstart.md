# 部署

三条命令，选一条。前提只有 Python 3.12+（Docker 那条连 Python 都不用装）。

## Windows

在管理员 PowerShell 里：

```powershell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 | iex
```

它会做五件事：找 Python 3.12、建 `.venv`、装依赖、注册计划任务 `SoapbotBot`、等到
`/api/health` 返回 200 才算完成。默认装在 `C:\soapbot`。

改目录和端口：

```powershell
.\install.ps1 -Dir D:\soapbot -Port 7000
```

重复执行是安全的：已有 `data\` 不动、已有 `.venv` 复用、已有计划任务不覆盖（要替换加
`-Force`）。

## Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.sh | bash
```

默认 `/opt/soapbot`，以 root 运行时注册 `soapbot.service` 并 `systemctl enable --now`。
非 root 或加 `--no-service` 时只把服务放到后台并写 `panel.log`。

```bash
./install.sh --dir ~/soapbot --port 7000 --no-service
```

## Docker

```bash
docker compose up -d
```

容器只在宿主机回环上发布 `6185`，根文件系统只读、非 root、`cap_drop: ALL`。数据在
命名卷里，升级前先 `python scripts/deploy_remote.py ... --backup`。

## 装完之后

打开 `http://127.0.0.1:6185`。第一次登录要一枚一次性令牌：

- Windows：`C:\soapbot\data\init_token.txt`
- Linux：`/opt/soapbot/data/init_token.txt`
- Docker：`docker compose exec soapbot cat /data/init_token.txt`

脚本不会把令牌打进终端——它会留在终端记录里，而令牌是一次性的。

## 出问题

**提示没有 Python 3.12。**

- Windows：从 python.org 装 3.12+，装的时候勾上 “Add python.exe to PATH”。
- Debian/Ubuntu：`sudo apt install python3.12 python3.12-venv`
- RHEL/Fedora：`sudo dnf install python3.12`

**端口被占用。** 换一个：`-Port 7000` / `--port 7000`。面板只绑 `127.0.0.1`，远程看
用 SSH 隧道，不要把端口开到公网。

**装完打不开。** 先看健康接口：`curl http://127.0.0.1:6185/api/health`。
Windows 看 `C:\soapbot\panel.log`，Linux 看 `journalctl -u soapbot -n 50`。

**保存设置后没生效。** 名单类设置写进 `data/.env`，要重启才读。面板会把当前平台的
正确命令显示在保存成功的提示下面；不用自己猜任务名或 unit 名。

## 更新

重跑同一条安装命令。脚本不会覆盖 `data/`，所以数据库、配置、插件都在。

## 卸载

```powershell
# Windows
Unregister-ScheduledTask -TaskName SoapbotBot -Confirm:$false
Remove-Item C:\soapbot -Recurse -Force
```

```bash
# Linux
sudo systemctl disable --now soapbot
sudo rm /etc/systemd/system/soapbot.service
sudo rm -rf /opt/soapbot
```

删目录之前先把 `data/` 里的 `soapbot.db` 和 `secret.key` 备份走——后者丢了，加密过的
插件密钥就解不开了。

## 从源码跑

改代码时不用上面的脚本：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m soapbot.cli start
```

`uvicorn` 与 `soapbot start` 的区别只在参数，`soapbot start` 会把日志配置和关闭超时
一起设好。

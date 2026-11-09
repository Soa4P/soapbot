# 部署

Windows 和 Linux 各有自己的一键命令，都是「一条命令装完」；Docker 是额外的容器加固路径，
目前**只支持 Linux**。三者选一条，不要混着用。

| 你的机器 | 用哪条 | 前提 |
| --- | --- | --- |
| Windows | [Windows](#windows) | Python 3.12+，管理员 PowerShell |
| Linux | [Linux](#linux) | Python 3.12+ |
| Linux（容器加固） | [Docker](#docker) | Docker |

> 三条路径的差别不只是「用什么装」：容器路径有非 root、只读根、`cap_drop: ALL`、
> seccomp、tini、`0600` 权限位；Windows / Linux 原生路径是普通进程 + 计划任务 /
> systemd，**没有这些内核级加固**。需要强隔离时选 Docker（仅 Linux）。

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

compose 文件在 `deploy/` 下，**不在仓库根目录**，所以必须带 `-f`：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

容器只在宿主机回环上发布 `6185`，根文件系统只读、非 root、`cap_drop: ALL`。数据在
命名卷里，升级前先 `python scripts/deploy_remote.py ... --backup`。

### 为什么 Docker 这条 Windows 用不了

这不是「装个 Docker Desktop 就行」，容器链路是按 Linux 内核写的：

| 依赖 | 位置 | Windows 上 |
| --- | --- | --- |
| Linux 基础镜像 | `deploy/Dockerfile:14,37` `python:3.12-slim`，`:59-63` `apt-get tini` + `groupadd/useradd` | Windows 容器模式平台不匹配 |
| 内核加固 | `deploy/docker-compose.yml:20,23-45` `user: 10001:10001`、`cap_drop: ALL`、`no-new-privileges`、`seccomp=builtin`、`read_only` + `tmpfs` | 无对应语义，键被忽略或直接报错 |
| POSIX 权限位 | `Dockerfile:80,84` chown、`compose:81,119` `0600` / `0400` | `os.chmod` 在 Windows 只切只读位，真实控制是 NTFS ACL（`src/soapbot/security/files.py:14-18`） |
| `/proc` 与 systemd | `docs/deploy-layer.md:412` `cat /proc/1/comm`、`scripts/deploy_remote.py:299` `systemctl is-enabled` | 命令不存在，`--verify` 相关项判 FAIL |
| bash 安装脚本 | `deploy/install.sh:1` shebang、`:28-44` flock dpkg、`:70-84` apt PPA | PowerShell 无法执行 |

所以 Windows **不是降级版 Docker，而是另一条同等地位的一键路径**：`install.ps1` 用原生
Python 进程 + 计划任务，功能一致，但不含上述内核加固。这条差别不能藏起来。

`scripts/check_deploy.py` 里那条已知告警是 `image.mirror-unknown`（没配镜像加速、直连
Docker Hub 超时），与 Windows 无关。

## 装完之后

打开 `http://127.0.0.1:6185`。第一次登录要一枚一次性令牌：

- Windows：`C:\soapbot\data\init_token.txt`
- Linux：`/opt/soapbot/data/init_token.txt`
- Docker：`docker compose -f deploy/docker-compose.yml exec soapbot cat /data/init_token.txt`

脚本不会把令牌打进终端——它会留在终端记录里，而令牌是一次性的。

### 验证装好了

```bash
python -m soapbot.cli doctor            # 逐项检查配置与上游连通性
python -m soapbot.cli doctor --strict   # 有 critical/high 未解决时退出码 2
```

容器部署还能跑远程验收：`python scripts/deploy_remote.py --host <IP> --port 443
--key <私钥> --verify`（14 项，全部走 SSH + Linux 命令，同样只适用于 Linux 目标）。

## 桌面端（Windows 双击即用）

`desktop/` 能打出 **Windows 安装包**，包里自带后端，装完不需要单独装 Python。

本机 Windows 实测：

```
npm run build
→ desktop/src-tauri/target/release/bundle/nsis/soapbot_0.1.0_x64-setup.exe  (47.48 MiB)
```

47.48 MiB 不是空壳的体积——空壳约 4 MiB。`installer.nsi` 第 688 行把冻结后的后端写进
安装目录：

```
File /a "/oname=binaries\soapbot-backend.exe" "...\binaries\soapbot-backend.exe"
```

三段拼起来：

| 阶段 | 命令 / 文件 | 实测结果 |
| --- | --- | --- |
| 冻结后端 | `python desktop/sidecar/build.py` | onefile 46.3 MiB；启动后 `/api/health` 200、`/` 200 |
| 打包安装包 | `cd desktop && npm run build` | NSIS 47.48 MiB，含 `binaries/soapbot-backend.exe` |
| 运行时托管 | `desktop/src-tauri/src/main.rs` | 先探测 6185；已监听不启动第二个，端口空才 spawn，退出 `taskkill /T` |

完整构建顺序（改代码时）：

```bash
cd webui && npm ci && npm run build      # 面板产物
python desktop/sidecar/build.py          # 冻结后端并 staging 到 src-tauri/binaries/
cd desktop && npm ci && npm run build    # 出 NSIS 安装包
```

冻结与托管这两段各踩过一个坑，写在代码注释里：SQLAlchemy 的 `sqlite+aiosqlite` dialect
按 URL 字符串动态加载，不加 `--collect-submodules sqlalchemy.dialects.sqlite` 会在
`create_async_engine` 处启动失败；onefile 的 bootloader 会派生一个子进程，只杀父进程会
留下孤儿并占住端口，所以关闭必须 `taskkill /T`。

CI 里有一个 `desktop-bundle` job（Windows runner）做同样的事，**只在
`workflow_dispatch` 或 `v*` tag 时触发**——每次 push 都跑会多花几分钟，而 PR 里没人下载
安装包。手动触发：`gh workflow run ci`。

### 未签名意味着什么

安装包**没有代码签名**，Windows SmartScreen 会显示「未知发布者」，用户要点「更多信息 →
仍要运行」两次。不影响功能、不影响自动更新（Tauri 的更新签名是另一套密钥）、不影响 CI。
企业环境里 AppLocker 或组策略可能直接拦未签名 exe，那就必须签名。

证书的几条路、费用量级、以及 CI 用不了 USB 硬件令牌这件事，见
[桌面端签名](desktop-signing.md)。

两条 Windows 路径（`install.ps1` 与 `windows-bootstrap.ps1 -Start`）现在注册**同一个**
计划任务 `SoapbotBot`（SYSTEM、开机启动），触发器与设置也一致；令牌策略统一为只给
`data\init_token.txt` 的路径，不把一次性令牌打进终端。`start-panel.bat` 是前台本地路径，
会把令牌 `type` 出来——它没有服务化，也没有别的地方能拿到，这条差异是有意保留的。
卸载或重启前不必再猜任务名，命令见本文末尾「卸载」。

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

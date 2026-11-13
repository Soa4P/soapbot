# 部署

Windows 和 Linux 各有自己的一键命令，都是「一条命令装完」；Docker 是额外的容器加固路径，
目前**只支持 Linux**。三者选一条，不要混着用。

| 你的机器 | 用哪条 | 前提 |
| --- | --- | --- |
| Windows（已有 Python） | [Windows](#windows) | 管理员 PowerShell、Python 3.12+ |
| Windows（没有 Python） | [Windows 无 Python](#windows-无-python) | 管理员 PowerShell |
| Linux | [Linux](#linux) | Python 3.12+ |
| Linux（容器加固） | [Docker](#docker) | Docker、Git |

> 三条路径的差别不只是「用什么装」：容器路径有非 root、只读根、`cap_drop: ALL`、
> seccomp、tini、`0600` 权限位；Windows / Linux 原生路径是普通进程 + 计划任务 /
> systemd，**没有这些内核级加固**。需要强隔离时选 Docker（仅 Linux）。

## Windows

### Windows 已安装 Python

在管理员 PowerShell 里：

```powershell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 -OutFile "$env:TEMP\soapbot-install.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-install.ps1"
```

要可复现安装（固定到某个发布 tag，内容不会像分支那样变化）：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-install.ps1" -Tag v0.1.0
```

### Windows 无 Python

在管理员 PowerShell 里：

```powershell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/windows-bootstrap.ps1 -OutFile "$env:TEMP\soapbot-bootstrap.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-bootstrap.ps1" -Start
```

这条路径会自动安装 Python 3.12、创建虚拟环境、安装依赖并注册 `SoapbotBot` 计划任务。
两条 Windows 路径默认都安装到 `C:\soapbot`，并且都需要管理员权限。

改目录和端口时，先下载脚本再传参数：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-install.ps1" -Dir D:\soapbot -Port 7000
```

重复执行是安全的：已有 `data\` 不动、已有 `.venv` 复用，计划任务每次都被重写成同一份定义
（同一个名字、同一个账号）。任务**不再以 SYSTEM 运行**，而是 `NT AUTHORITY\LocalService`：
插件隔离层拒绝在 LocalSystem 下启动 worker，用 SYSTEM 装出来的机器会静默失去所有插件。升级
旧机器只要重跑一次安装脚本，脚本会把目录权限收敛成「管理员/SYSTEM 全控、服务账号只读 + 四个
可写位置」，并自动把任务迁到低权限账号；也可以单独执行
`powershell -ExecutionPolicy Bypass -File scripts\harden-windows.ps1`。

## Linux

已有 Python 3.12+ 时，在服务器上执行：

```bash
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.sh -o /tmp/soapbot-install.sh
bash /tmp/soapbot-install.sh
```

要可复现安装（固定 tag，内容不变；本地脚本支持 `--tag`，或直接改下载 URL 的
`refs/heads/master` 为 `refs/tags/v0.1.0`）：

```bash
bash /tmp/soapbot-install.sh --tag v0.1.0
```

默认 `/opt/soapbot`，以 root 运行时注册 `soapbot.service` 并 `systemctl enable --now`。
非 root 或加 `--no-service` 时只把服务放到后台并写 `panel.log`。

修改目录或端口：

```bash
bash /tmp/soapbot-install.sh --dir "$HOME/soapbot" --port 7000 --no-service
```

## Docker

先在服务器上获取仓库并进入根目录：

```bash
git clone https://github.com/Soa4P/soapbot.git
cd soapbot
```

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

## 远程云服务器怎么打开面板

如果 soapbot 装在 Linux 或 Windows 云服务器上，`127.0.0.1` 指的是**服务器自己**，不是你本地电脑。
在你自己的 Windows PowerShell 或 Linux/macOS 终端执行 SSH 隧道：

```bash
ssh -N -L 6185:127.0.0.1:6185 用户名@服务器IP
```

服务器 SSH 不是 22 端口时加 `-p`，使用私钥时加 `-i`：

```bash
ssh -p 443 -i ~/.ssh/id_ed25519 -N -L 6185:127.0.0.1:6185 用户名@服务器IP
```

保持这个终端不要关闭，然后在你自己的电脑打开 `http://127.0.0.1:6185`。
Windows 也可以运行仓库中的 `scripts/connect-linux.ps1 -Tunnel`。如果你已经通过 RDP 登录到 Windows 云服务器，直接在**云服务器桌面里的浏览器**打开 `http://127.0.0.1:6185`，不要在本地电脑打开。


### 第一次登录：令牌在哪、找不到怎么办

**先别急着翻文件。** 先问服务自己：令牌现在是什么状态、文件到底在哪。在**服务器本机**
打开 PowerShell：

```powershell
curl.exe -s http://127.0.0.1:6185/api/auth/status
```

看返回里的两个字段：

| 字段 | 值 | 含义 | 下一步 |
| --- | --- | --- | --- |
| `bootstrap_state` | `available` | 还没用过，文件在磁盘上 | 照 `bootstrap_path` 读值 |
| `bootstrap_state` | `redeemed` | 已经登录过，文件当时就删了 | 看下面「重新获取一枚」 |
| `bootstrap_state` | `uninitialised` | 认证模块没初始化 | 先看 `/api/health` 和 `panel.log` |
| `bootstrap_path` | 如 `C:\soapbot\data\init_token.txt` | 服务**实际**在用的完整路径 | 直接复制这个路径 |

`bootstrap_path` 是服务按自己的数据目录算出来的，不用猜装在哪：装的时候用了
`-Dir D:\soapbot`，或改过 `SOAPBOT_DATA_DIR`，下面写死的 `C:\soapbot` 就不再适用，
一律以它为准。

**读令牌**（RDP 或远程 PowerShell，在服务器上执行，**不是在你自己的电脑上**）：

```powershell
Get-Content C:\soapbot\data\init_token.txt
```

把输出的那一串字符复制进面板登录框。登录成功一次后，这个文件**立刻被删除**，同目录
留下 `init_token.redeemed` 作为「已经用过」的标记，磁盘上不再留凭据。

> 本机双击 `start-panel.bat` 时，启动窗口会直接把令牌显示出来；那是前台本机路径，
> 没有别的地方可读。服务化安装（`install.ps1` / `windows-bootstrap.ps1 -Start`）只给
> 路径、不把值打进终端，因为终端记录比令牌活得久。两条路径行为不同是有意的，不是
> 有一边坏了。

**重启会不会把令牌弄丢？不会。**

- 还没用过：文件留在磁盘上，重启后还是同一个值。
- 已经用过：文件本来就不在了，重启**不会**自动再发一枚，也不会重新开放登录。

所以「重启之后找不到 `init_token.txt`」不是故障，通常说明它早就被兑换掉了；反复重启
不会变出新令牌。

**重新获取一枚**（文件不存在 / 登录返回 401 / `bootstrap_state` 是 `redeemed`）：

在服务器本机进入安装目录，执行：

```powershell
cd C:\soapbot
.\.venv\Scripts\python.exe -m soapbot.cli token --reset
```

这条命令会**直接打印一枚新令牌**，立刻复制；它同时重建 `data\init_token.txt` 并清掉
`data\init_token.redeemed`。正在运行的服务还拿着旧的内存状态，**必须重启**才会接受
新令牌：

```powershell
schtasks /End /TN SoapbotBot
schtasks /Run /TN SoapbotBot
```

重启后回到上面「读令牌」那一步，`Get-Content` 应能读到刚才那枚新值。用 `-Dir` 装到
别处时，把两条命令里的 `C:\soapbot` 换成实际目录。

另外两种装法：

- Linux：`cat /opt/soapbot/data/init_token.txt`；重发一枚用
  `cd /opt/soapbot && .venv/bin/python -m soapbot.cli token --reset`，再
  `sudo systemctl restart soapbot`。
- Docker：`docker compose -f deploy/docker-compose.yml exec soapbot cat /data/init_token.txt`。

如果自己在 `.env` 里设了 `SOAPBOT_INIT_TOKEN`，服务不会写文件，用你设的那个值登录，
上面「读令牌」一步不适用。

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
(cd webui && npm ci && npm run build)  # 面板产物
python desktop/sidecar/build.py          # 从仓库根冻结后端并 staging 到 src-tauri/binaries/
(cd desktop && npm ci && npm run build)   # 出 NSIS 安装包
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
计划任务 `SoapbotBot`（SYSTEM、开机启动），触发器与设置也一致。服务化安装结束时只给出
令牌文件的完整路径和打开它的命令，不把值打进终端；本机前台的 `start-panel.bat` 会直接
显示令牌值，因为它没有别的地方可读。「怎么读、重启后找不到怎么办」见本文开头的
「第一次登录：令牌在哪、找不到怎么办」一节。卸载或重启前不必再猜任务名，命令见
本文末尾「卸载」。

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

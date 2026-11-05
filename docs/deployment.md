# 部署细节

systemd / 容器 / Windows 计划任务、反向代理、升级与回滚。

**写给：** 把面板放到公网或长期运行的人。

> 这部分从 `README.md` 搬出来，是为了让 README 只回答「是什么、怎么跑起来、坏了怎么办」。
> 内容没有删减。

---

## 运行与部署

### 本地

```bash
make install        # 建虚拟环境 + 装开发依赖
make run            # 先构建前端，再启动服务
make check          # lint + 配色 + 可访问性 + 测试断层 + test（与 CI 阻断项同一条命令）
make a11y           # 可访问性静态规则（按钮名称、点击目标可聚焦、img alt、对话框语义）
make gaps           # 测试断层扫描：无人引用的模块、文档里与看板不一致的数字
make typecheck      # mypy —— 当前基线非零，仅作参考，不阻断
make doctor         # 部署姿态检查
```

> **类型检查现状**：`mypy src` 目前报告 53 个错误，分布在 20 个文件，全部是既有问题。
> 因此 CI 把它放在独立的 `types` job 里（`continue-on-error`），只报告不阻断。
> 让它阻断会让首次推送就是红的，而让人们习惯红色徽章；按模块 `ignore_errors` 则会
> 把该文件里的下一个真实错误一并藏掉。降到 0 之后应当改为阻断。

不用 `make` 也可以，见[快速开始](#快速开始)。

### 双端安装（Windows / Linux / macOS，同一个安装器）

```bash
python scripts/bootstrap.py                       # 装到当前目录（或 --dir）
python scripts/bootstrap.py --autostart           # 开机/登录自动起来
python scripts/bootstrap.py --check               # 只体检已有安装
python scripts/bootstrap.py --dir D:\soapbot --port 6185
```

六个步骤两端一致：创建 venv → `pip install -e .` → 确认面板产物存在（缺 Node 时会明说）
→ 把数据目录/配置目录写成**绝对路径**写进 `.env` → 交给平台自己的进程管理者 →
轮询 `/api/health` 到通过 → 打印面板地址、取令牌的命令、下一步去第 07 页。幂等：再跑一次等于升级。

两端唯一真正不同的地方在最后一步：

| 平台 | 谁来托管进程 | `--autostart` 做什么 |
|---|---|---|
| Windows | 双击 `start-panel.bat`；或用 detached 进程后台起 | 注册计划任务 `soapbot-panel`（登录时启动） |
| Linux | systemd unit（有 root 时还会建 `soapbot` 系统账号并把服务跑成它，而不是 root）/ 用户级 unit（无 root，会提示 `loginctl enable-linger`） | 等价于 `systemctl enable --now` |
| 无 systemd | 明确告知：用 supervisor / openrc，或直接前台跑 | 不假装成功 |

已存在的同名 unit 若**不是**本安装器写的，一律不动（`--unit <名字>` 起第二份实例）——
覆盖别人的 unit 会把它指向新目录，而数据还留在原处。

> **Windows 上有两个长驻进程，都得交给计划任务托管，而且都要 `ExecutionTimeLimit=PT0S`。**
> 机器人用 [`scripts/install_windows_task.ps1`](../scripts/install_windows_task.ps1)，
> 协议端 NapCat 用 [`scripts/install_napcat_task.ps1`](../scripts/install_napcat_task.ps1)：
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\install_napcat_task.ps1 -QQNumber 你的QQ号 -Start
> ```
>
> 从 WinRM/RDP 会话里起的进程会在会话空闲 2 小时后被 job object 回收；而计划任务如果
> 保留默认的 `PT72H`，任务计划程序会在启动满 72 小时时**把任务连同 NapCat/QQ 整个进程树
> 杀掉**。后者在真机上发生过：`LastRunTime 10/31 22:10:10` + 72h = `11/03 22:10:10`，
> 首次拒连 `22:10:24`，`run.log` 停在 `22:10:20` 且没有退出记录，`LastTaskResult=267014`。
> 强杀还会丢失 QQ 会话，重启后必须到 `:6099` 的 WebUI **扫码一次**；登录后脚本设置的
> `autoLoginAccount` 与 `-q <QQ号>` 才会让之后的重启免扫码。

完全没有 Linux 主机时也可一张命令：

```bash
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/install.sh | sudo bash
```

它只负责弄到 Python ≥ 3.12（22.04 上自动换 deadsnakes 的 3.12）并 clone，然后调用上面
**同一个** `bootstrap.py`——两处分叉的安装器正是第一版脚本 systemd-only 的成因。

> **Ubuntu 上已经在真机跑过（不是只看代码）**：雨云 Ubuntu 24.04、root 登录、全新目录
> `/opt/soapbot-test`、端口 6186：venv → `pip install -e .` → 配置 → `systemctl enable --now`
> → `/api/health` 报 ok → 面板 `index.html` 与 JS 资源均 200；`doctor` 以服务账号运行时
> `privilege.uid` 为 ok（uid 996）。三个真机失败点都是这样被抓到并修掉的：
> `python3` 存在但没有 `ensurepip`（Debian 把 `python3-venv` 拆出去了）、另一进程占用
> `dpkg` 锁、unit 缺省 `User=` 导致服务跑成 root、以及**配置目录被解析到模板目录**
> （模板里的 `SOAPBOT_CONFIG_DIR=./config` 是相对路径，systemd 的工作目录就是 checkout，
> 于是面板改的是随仓库发布的模板，而安装器每次 `git pull` 会把它改回去；`data/config`
> 甚至根本没被创建）。现在配置目录跟随数据目录，模板那行已改为注释说明原因；真机上验证过：
> 面板保存落在 `data/config/providers.yaml`（可写卷），随仓库的 `config/providers.yaml` 一行未动，
> 面板读回来就是刚写的那条。
>
> **仍未实测**：Docker 路径（本机无 `docker`）、非 Debian 系发行版、以及在已存数据的旧安装上升级。

> **首次运行没有 Provider 是刻意的**：模板 `config/providers.yaml` 是空的。一个引用了未设置环境变量的
> 模板，会让每一次全新安装都以 `references unset environment variable` 拒绝启动——什么都没配就已经看起来坏了。
> 在第 07 页加一个即可（那边有「测试」按钮能当场证明它答得上话）。

> **Linux 一侧仍未在真机跑过**：本机没有 Linux 主机，`install.sh` 只通过语法检查；
> 首次在服务器上运行请把输出整段发回，第一个真实失败点会被直接指出。

### Docker

```bash
cp .env.example .env      # 至少填 OWNER_IDS 与主密钥来源
docker compose -f deploy/docker-compose.yml up -d --build
```

镜像要点（详见 `docs/deploy-layer.md`）：非 root 用户、`data/` 为卷、`config/` 只读、
主密钥从文件挂载。部署前跑一次 `doctor --strict`。

容器里 `.env` 被显式指到 `/data/.env`（`SOAPBOT_ENV_FILE`）。根文件系统是只读的，
默认位置在 `/app`，第 12 页保存设置会直接失败——把它放在数据卷上，保存才能落盘并在重启
后生效。`scripts/check_deploy.py` 会静态校验这一条。

> **容器未经实测。** 本机无 `docker` 命令，`check_deploy.py` 只能证明配置文件里写了
> `read_only: true`，不能证明容器起得来。9 条验收命令与预期输出见
> [`docs/deploy-layer.md` §8](deploy-layer.md)，需要在有 Docker 的机器上执行。

### 前端

```bash
cd webui
npm install
npm run dev       # 开发模式，代理到 127.0.0.1:6185
npm run build     # 产物写入 src/soapbot/webui/dist
```

产物缺失时后端不会崩溃，`GET /` 返回构建指引——这条是刻意的：容器里没有 npm，
一个「白屏 + 500」会让人以为是权限问题。

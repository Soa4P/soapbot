# 公开仓库 PR 提交与部署指南

这份文档写给第一次使用仓库的人：不会写 Python、不会配置服务器，也可以照着做。

## 1. 提交 PR 要写什么

PR 标题只写一件事，例如：

```text
修复：Windows 重启后保留登录令牌
新增：支持 Linux SSH 远程连接
```

PR 描述只需要回答三件事：

1. **PR 的意义**：一两句话讲清这个 PR 带来什么变化，涉及模块用小写英文写在句末。
2. **为什么改**：谁遇到了什么问题，原来为什么不行。
3. **怎么验证**：只写真正跑过的命令和结果；没跑过写“未验证”。

不涉及的内容直接删掉，不要用深奥的工程术语代替答案。模板在
`.github/pull_request_template.md`。不符合模板的 PR 会被标 `needs-manual-review`，
需要人工二次复检，不能只凭 AI 审查合并。

## 2. Windows 云服务器第一次部署

管理员 PowerShell 执行：

```powershell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 -OutFile "$env:TEMP\soapbot-install.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-install.ps1"
```

如果服务器没有 Python 3.12，改用自动安装 Python 的入口：

```powershell
irm https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/windows-bootstrap.ps1 -OutFile "$env:TEMP\soapbot-bootstrap.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\soapbot-bootstrap.ps1" -Start
```

安装结束后，令牌在服务器本机的：

```text
C:\soapbot\data\init_token.txt
```

读取它：

```powershell
Get-Content C:\soapbot\data\init_token.txt
```

把输出粘贴到 `http://127.0.0.1:6185` 的登录页面。登录一次后文件会被删除，这是正常的。

### Windows 重启后令牌会不会丢

不会：

- 还没登录：令牌保存在 `data\init_token.txt`，重启仍是同一枚。
- 已经登录：令牌已经被兑换并删除，重启不会自动生成新令牌。

如果需要重新登录，在服务器本机用**管理员 PowerShell**执行：

```powershell
cd C:\soapbot
.\.venv\Scripts\python.exe -m soapbot.cli token --reset
schtasks /End /TN SoapbotBot
schtasks /Run /TN SoapbotBot
Get-Content C:\soapbot\data\init_token.txt
```

如果安装时用了 `-Dir D:\my-soapbot`，把上面的 `C:\soapbot` 换成实际目录。令牌的唯一权威位置是服务实际使用的数据目录；也可以先访问本机：

```powershell
curl.exe -s http://127.0.0.1:6185/api/auth/status
```

返回的 `bootstrap_path` 就是实际路径。

## 2.5 让第二个人只看他自己该看的群

面板令牌是「拿到就全见」，第二个人不该拿它。用**第 13 页「聊天存档」**的账号体系：

1. 先建第一个所有者。`init_token` 只能干这一件事——它建不了存档会话，第 13 页会回 401：

  ```bash
  curl.exe -s -X POST http://127.0.0.1:6185/api/accounts/owner \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $(cat data/init_token.txt)" \
    -d '{"username": "owner", "password": "换成至少 8 位的密码"}'
  ```

  Windows 上把 `$(cat data/init_token.txt)` 换成 `(Get-Content data\init_token.txt)`，或者
  直接把令牌内容粘进去。密码用标准库 scrypt 存哈希，库里没有明文；用户名 3-32 位，
  只允许字母、数字、`_`、`.`、`-`。

  建完之后**立刻**用 `POST /api/auth/login` 把令牌消费掉（它会删掉 `init_token.txt` 并留一个
  `init_token.redeemed` 标记）。原因很直接：直接拿它当 Bearer 调 API 并不算消费，在被消费
  之前它一直是一把管理员钥匙。想省事就直接删 `data/init_token.txt`。

2. 打开 `http://127.0.0.1:6185/chat/login`，用刚建的账号登录。
3. 在第 13 页或 API 里生成邀请码，发给要加入的人；**邀请码只显示一次**，发错只能作废重发。
4. 对方访问同一个地址，用邀请码注册，登录后只看得到被授权的会话。

三个容易踩的点：

- 这一页只能看和写备注，**不会往 QQ 发任何东西**。备注落库为 `delivered=false`，对方在
  QQ 里看不到。
- 访问别人的会话会得到 **404**，不是「无权限」——403 等于告诉你这个群存在。
- 手机端和桌面壳默认关着（`SOAPBOT_CHAT_APP_ENABLED=false`、
  `SOAPBOT_CHAT_DESKTOP_ENABLED=false`）。要在手机上用，先在自己机器上把对应开关打开，
  再重启服务；三个开关全关时这些接口直接 404。

完整的账号、邀请、授权与停用说明见 [chat-archive.md](chat-archive.md)。

## 3. 从 Windows 连接 Linux

Windows 10/11 自带 OpenSSH Client。先测试：

```powershell
ssh -V
```

打开交互式 Linux 命令行：

```powershell
.\scripts\connect-linux.ps1 `
  -HostName 203.0.113.10 `
  -User ubuntu `
  -KeyPath "$env:USERPROFILE\.ssh\id_ed25519"
```

如果 PowerShell 阻止本地脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\connect-linux.ps1 `
  -HostName 203.0.113.10 -User ubuntu `
  -KeyPath "$env:USERPROFILE\.ssh\id_ed25519"
```

只想打开 Linux 上的 soapbot 面板，不要开放 6185 公网端口，使用 SSH 隧道：

```powershell
.\scripts\connect-linux.ps1 `
  -HostName 203.0.113.10 `
  -User ubuntu `
  -KeyPath "$env:USERPROFILE\.ssh\id_ed25519" `
  -Tunnel
```

然后在本机打开 `http://127.0.0.1:6185`。保持 PowerShell 窗口打开；关掉它隧道就断开。

这个脚本只做 SSH 命令行和回环隧道，不会自动安装 RDP、开放防火墙或把管理面板暴露到公网。需要完整 Linux 桌面时，请使用云厂商提供的控制台或在服务器上自行配置受防火墙保护的桌面服务；本项目默认不替用户打开高风险远程桌面端口。

## 4. 配置 DeepSeek

面板第 07 页选择 DeepSeek，默认地址是：

```text
https://api.deepseek.com/v1
```

默认模型是：

```text
deepseek-flash
```

这是 DeepSeek 官方当前模型文档列出的模型 ID。模型会变化，保存前点击“拉取模型列表”，以官方文档和实际返回列表为准：

<https://api-docs.deepseek.com/quick_start/pricing>

API Key 建议放在环境变量中，不要写进公开仓库：

```powershell
$env:DEEPSEEK_API_KEY = '在这里粘贴你的 Key'
```

配置文件里使用：

```yaml
api_key: env:DEEPSEEK_API_KEY
model: deepseek-flash
```

## 5. 写插件

插件必须先放进 `data/plugins/`，再在面板批准；复制进去不会自动执行。

最小插件：

```text
data/plugins/hello/plugin.yaml
data/plugins/hello/main.py
```

`plugin.yaml`：

```yaml
name: hello
version: 1.0.0
description: 回复 hello
entry: main:Plugin
trust: community
capabilities: [command]
```

`main.py`：

```python
class Plugin:
    def setup(self, ctx):
        @ctx.command("hello", description="打个招呼")
        async def hello(caller, args):
            return f"你好，{caller.display_name}"
```

能力要写进 `capabilities`，并在面板逐项批准。插件运行在独立进程，崩溃后不会自动重启；检查日志、修复插件后再手动 reload。完整 API 见 `docs/plugins.md` 和 `docs/wave3-plugin-api.md`。

## 6. 更新前先做什么

1. 备份 `data/`，尤其是 `secret.key`。
2. 记录当前版本：`git rev-parse HEAD`。
3. 更新后执行：

```powershell
python -m soapbot.cli doctor --strict
```

Linux 使用：

```bash
python3 -m soapbot.cli doctor --strict
```

如果是远程生产部署，使用完整 commit SHA，不要直接部署会变化的 `master` 分支。不要把 API Key、登录令牌、SSH 私钥、公网服务器地址提交到仓库。

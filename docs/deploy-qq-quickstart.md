# 从零把 QQ 机器人跑起来（15 分钟）

这份文档假设你**什么都没配过**，目标是：给机器人发一条消息，它回你一句。

三个角色先认清，后面所有步骤都是围绕它们：

| 角色 | 是什么 | 你要准备 |
|---|---|---|
| **soapbot** | 本体：收消息、调模型、回消息、带面板 | 本仓库 |
| **协议端** | NapCat / Lagrange，登录你的 QQ，把消息转成 WebSocket | 自己装一个 |
| **模型端点** | DeepSeek / 通义等，负责「说什么」 | 一个 API Key |

---

## 第 1 步：让面板跑起来（2 分钟）

### Windows

双击仓库根目录的 **`start-panel.bat`**。

它会：找不到 `.venv` 就建一个 → 装依赖 → 起服务 → **等到能访问才自动打开浏览器**。
窗口里会打印首次登录令牌（也存在 `data\init_token.txt`）。

### Linux / 服务器（一条命令）

```bash
curl -fsSL https://raw.githubusercontent.com/Soa4P/soapbot/master/deploy/install.sh | sudo bash
```

装依赖 → clone 到 `/opt/soapbot` → venv → 复制 `.env` → 写 systemd unit → 起服务 →
轮询到 `/api/health` 通过 → 打印面板地址和登录令牌的取法。重复执行等于升级（拉代码、重装、重启）。

想手动装就照旧：

```bash
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m soapbot.cli start
```

浏览器打开 `http://127.0.0.1:6185`。服务器没有图形界面时，在你自己的电脑上开隧道：

```bash
ssh -p 22 -i <你的密钥> -N -L 6185:127.0.0.1:6185 <用户>@<服务器IP>
```

然后本机浏览器访问 `http://127.0.0.1:6185`。

> **成功标志**：看到 12 个页面的侧边栏，标题「总览 · soapbot」。

**打不开怎么办**

| 现象 | 原因 | 处理 |
|---|---|---|
| 窗口一闪而过 | 缺 Python | 装 Python 3.12，勾选 "Add python.exe to PATH" |
| 提示缺 `DEEPSEEK_API_KEY` | 还没配模型 | 先做第 2 步（或把 `.env` 里对应变量填上） |
| 浏览器「无法访问」 | 服务没起来 | 看窗口里的 `data\panel.log` 尾部 |

---

## 第 2 步：配模型端点（3 分钟）

进入 **07 模型与人格** 页，找到 Provider 区块，新增一条：

| 字段 | 填什么 | 例子 |
|---|---|---|
| `id` | 随便起个名 | `deepseek` |
| `kind` | 接口类型 | `openai_compat` |
| `base_url` | 厂商给的地址 | `https://api.deepseek.com/v1` |
| `model` | **接口真实列出的模型名** | `deepseek-flash` |
| `api_key` | 密钥，或用 `env:变量名` 引用 | `env:DEEPSEEK_API_KEY` |

点「预览改动」→ 看 diff → 确认写入。

> **`model` 一定要用厂商 `/v1/models` 里真实存在的名字。** 写错不会报错，只会在回复时收到 400/404。
> 用 `env:` 时，变量必须真的存在于进程环境里（容器里放 `/data/.env`）。

**成功标志**：保存后重启服务，`` [ok] provider.upstream `` 不再报警告。

---

## 第 3 步：配 QQ 接入（5 分钟）

先在你的协议端（以 NapCat 为例）打开 WebSocket：

- 进 NapCat 的「网络配置」→ 新建 **WebSocket 服务器**（正向）或 **WebSocket 客户端**（反向）
- 记下端口和 access token

然后回到面板 **07 页 → 协议接入（adapters）**，点「新增接入」：

### 情况 A：让 soapbot 主动连 NapCat（forward，最简单）

| 字段 | 填什么 |
|---|---|
| 类型 | `onebot11` |
| 连接方式 | `forward` |
| 机器人 QQ | 你的机器人 QQ 号 |
| 反连地址 | NapCat 的 WebSocket 地址，如 `ws://127.0.0.1:3001` |
| 令牌 | NapCat 里设的 access token（没设就留空） |

### 情况 B：让 NapCat 主动连 soapbot（reverse，适合机器人跑在 NAT 后）

| 字段 | 填什么 |
|---|---|
| 类型 | `onebot11` |
| 连接方式 | `reverse` |
| 机器人 QQ | 你的机器人 QQ 号 |
| 监听地址 | `127.0.0.1`（或 `0.0.0.0`，届时务必配令牌） |
| 监听端口 | 例如 `6700` |
| 令牌 | **必填**——不填会拒绝启动，开放的反向端口等于谁都能往你的流水线里灌消息 |

填完 → 「预览改动」→ 「写入」→ **重启服务**（适配器只在启动时连接）。

> **成功标志**：面板 **02 运行状态** 页能看到这个适配器处于已连接；`/api/runtime` 的 `startup_errors` 为空。

---

## 第 4 步：真的发一条消息（1 分钟）

在 QQ 里私聊机器人（或在群里 @ 它），发：「你好」。

- **它回了** → 成了。
- **没反应** → 按下面顺序查，一步一个结论：

| 检查 | 怎么看 | 说明 |
|---|---|---|
| 1. 适配器连上了吗 | 02 页 / `/api/runtime` | 没连上：协议端没开、端口错、令牌不一致 |
| 2. 消息进来了吗 | 08 运行日志，找 inbound | 进来了但没回：看下一步 |
| 3. 模型答了吗 | 08 日志里有没有 provider 报错 | 401 = key 无效；403 = 额度用尽；404 = 模型名不对 |
| 4. 权限允许吗 | 群聊默认**不回复**，需在 `SOAPBOT_GROUP_ALLOWLIST` 里加群号；私聊默认**谁都不回**，需加 `SOAPBOT_PRIVATE_ALLOWLIST` | 这是刻意的默认值，不是 bug |

第 4 条是最常见的「明明配好了却不理我」。

---

## 一句话版

```
双击 start-panel.bat → 07 页配 Provider → 07 页配 adapters → 重启 → 发消息
```

## 配完怎么确认（不用重启试错）

**面板第 07 页，每行都有「测试」按钮**（Provider 表和 adapters 表各一个），结果就在按钮旁边：

- **Provider**：只探测 `base_url` 是否可达，**不发密钥**。所以 `401/403` 也算通过——端点活着，只是拒绝了匿名请求；`404` 多半是 `base_url` 少了 `/v1`。用的是表单里的草稿值，**没保存也能测**。
- **adapters / forward**：真的握手并请求一次 `get_login_info`，拿到 `user_id`/`nickname` 才算通；只握手成功但对面不是 OneBot，会明确报「不像 OneBot」。
- **adapters / reverse**：测的是**本机端口**——「端口已在监听」是正常状态（适配器正在跑），「端口空闲」说明还没监听。对方有没有连进来，这里看不到，要看 02 页。

总览页（01）顶部还有一张「首次运行检查」卡：Provider 配了没、接入配了没、适配器在不在线、启动有没有错误、配置目录可不可写——每项直接跳到要改的页面，五项全绿后自动消失。

## 服务器没有浏览器：`soapbot setup`

```bash
soapbot setup                       # 交互式逐项问；校验不过不写盘

soapbot setup --non-interactive \
  --provider-id deepseek --base-url https://api.deepseek.com/v1 \
  --model deepseek-flash --api-key-env DEEPSEEK_API_KEY \
  --kind onebot11 --mode forward --ws-url ws://127.0.0.1:3001
```

它和面板走同一套「读 → 合并 → 校验 → 原子写」：写之前先用启动解析器验一遍（`env:` 变量没设就直接报错，绝不落盘）；密钥可以用 `--api-key-env VAR` 只写变量名；结束会打印面板地址、`soapbot token` 和 `soapbot start`。配置在启动时读取，**改完仍需重启**。

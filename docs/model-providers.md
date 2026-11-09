# 接入 AI 模型（不用改代码）

这份文档写给**不想看代码的人**。全程在网页里点，不需要打开编辑器、不需要懂
`base_url` 是什么、不需要重启服务。

## 开始之前：只需要准备一样东西

一枚 **API Key**（一串字符，形如 `sk-...`）。在你选的模型厂商官网注册账号，进控制台
找到「API Keys / 密钥管理」，创建一枚，复制下来。

不知道选哪家：先选 **DeepSeek** 或 **Qwen**，注册和充值流程最 straightforward，且面板
里已经预填好了地址和模型名。之后随时可以加第二家、第三家，互不影响。

> 本文档只写仓库里真实存在的预填值，不猜测任何第三方厂商的申请网址或模型名。
> 厂商控制台地址和可用模型会变，以厂商自己的文档为准。

## 三步完成

1. 打开 `http://127.0.0.1:6185`，用 `data/init_token.txt` 里的令牌登录（见
   [部署文档](deploy-quickstart.md)「装完之后」）。
2. 进**第 07 页「模型与人格」**，在「模型」区域点一下你那家厂商的名字。点完会出现
   一行配置，**接口地址和模型名已经填好了**。
3. 把 API Key 粘贴进 `api_key` 那一格，点这一行的**「测试」**。出现绿灯再点**「保存」**。

「测试」会真的向厂商发一次请求，所以要点一下才发——不是自动的。没绿灯之前不要保存，
否则机器人会连着一个不通的端点，收消息但不回复。

保存后不用重启。配置写进 `data/config/providers.yaml`，这是**你的那份**；仓库里的
`config/` 只是模板，首次启动时播种一次，`git pull` 不会覆盖它。

## 面板里已经预填好的十家

下表全部来自 `webui/src/views/ConfigView.vue` 的预设，点一下就能用。`kind` 一栏是
内部协议类型，你不用改，列出来只是方便排查。

| 面板里的名字 | 接口地址（已预填） | 默认模型（已预填） | Key 去哪拿 |
| --- | --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-flash` | DeepSeek 开放平台 → API Keys |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | 阿里云百炼控制台 → API-KEY |
| OpenAI / ChatGPT | `https://api.openai.com/v1` | `gpt-4o-mini` | OpenAI 控制台 → API keys |
| GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4.5` | 智谱开放平台 → API Keys |
| Kimi / Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | Moonshot 开放平台 → API Key |
| Grok | `https://api.x.ai/v1` | `grok-2-latest` | xAI 控制台 → API Keys |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.0-flash` | Google AI Studio → Get API key |
| Claude | `https://api.anthropic.com/v1` | `claude-sonnet-4-5` | Anthropic 控制台 → API Keys |
| MiMo | `https://api.xiaomimimo.com/v1` | `MiMo-V2.6` | 小米 MiMo 开放平台 → API Keys |
| Ollama（本地） | `http://127.0.0.1:11434/v1` | `llama3.1` | 不用 Key，见下节 |

这十家**全部走 `openai_compat`**：只要服务端接受 `POST /chat/completions` + Bearer
Key，就能接。所以 Claude、Gemini 这里用的是它们各自的 OpenAI 兼容端点，不是原生协议。
`src/soapbot/providers/router.py` 里另有 `anthropic` 和 `gemini` 两种原生 `kind`，但那是
手改配置文件才用得到的，面板预设不依赖它们。

**模型名可能过期**：预设里的模型名只是起点。点「测试」旁边的**拉取模型列表**可以拿到
厂商当前真实可用的模型 ID，选一个再保存。举例，仓库模板 `config/providers.yaml` 里
DeepSeek 写的是 `deepseek-chat`，面板预设写的是 `deepseek-flash`——两者不是一个东西，
以拉取到的列表为准。

## 表里没有的厂商：MiniMax、混元、Nemotron、seed、Llama / Meta、Muse……

不用等我们加预设。绝大多数厂商都提供 **OpenAI 兼容端点**，自己加一行就行：

1. 第 07 页点**「添加一行」**（不是点预设）。
2. 按厂商文档填三格：
   - `kind`：保持 `openai_compat`
   - `base_url`：厂商文档里写的 OpenAI 兼容地址，通常以 `/v1` 结尾
   - `model`：厂商文档里的模型 ID
3. 粘贴 Key，点「测试」，绿灯后保存。

如果厂商只给**原生协议**（不提供 `/chat/completions`），`openai_compat` 接不上，需要
开发侧在 `src/soapbot/providers/` 新增一个 provider 类并在 `router.py` 注册——这属于
改代码，不是配置能解决的。本文档不把这种情况说成「填个地址就行」。

ChatGPT 就是上表的 OpenAI；Kimi 就是 Moonshot；这两组名字不必重复添加。

## 本地模型（不用 Key、不花钱、不出网）

最简单的是 **Ollama**：

1. 装好 Ollama 并拉一个模型，例如 `ollama pull llama3.1`。
2. 第 07 页点 `Ollama` 预设，`api_key` **留空**，点「测试」→ 保存。

面板预设用的是 `http://127.0.0.1:11434/v1`（Ollama 的 OpenAI 兼容端口）。仓库模板里
还有一种直接用原生协议的写法，适合要同时配嵌入模型的场景：

```yaml
providers:
  - id: local-embed
    kind: ollama
    label: 本地模型
    base_url: http://127.0.0.1:11434
    model: llama3.1
    embed_model: nomic-embed-text
    priority: 30
```

LM Studio、vLLM、llama.cpp 之类只要开了 OpenAI 兼容服务，就按上一节「表里没有的厂商」
处理：填它给你的地址和端口，Key 留空或随便填一个占位值（有些服务端要求非空）。

## 报错了怎么读

| 现象 | 原因 | 怎么办 |
| --- | --- | --- |
| 测试返回 401 | Key 错了、没复制全、或没生效 | 重新复制一枚；注意别把前后空格带进去 |
| 测试返回 404 | `base_url` 不对（常见是漏了 `/v1`，或填成了网页控制台地址） | 对照上表，或查厂商文档的「兼容 OpenAI」地址 |
| 测试返回「模型不存在」 | 预填的模型名已经下线，或账号没开通该模型 | 点「拉取模型列表」选一个真实 ID |
| 测试返回 429 | 额度用尽或触发限流 | 等一会儿重试；`src/soapbot/providers/base.py` 只对 429/5xx 重试，不会拿错误 Key 反复撞 |
| 一直转圈到超时 | 网络到不了该端点 | 先确认浏览器能打开厂商官网；出境访问问题不在本仓库能修的范围 |
| 服务起不来，提示 `references unset environment variable` | 配置文件里写了 `env:XXX_API_KEY` 但没设这个环境变量 | 删掉这行改成直接填 Key，或按 `docs/configuration.md` 设置环境变量。仓库模板故意留空 `providers: []`，就是为了避免全新安装一启动就报这个错 |
| 机器人收消息但不回复 | 配置没保存，或模型阶段被禁用 | 回第 07 页看绿灯；检查 `docs/configuration.md` 里「模型阶段禁用」相关项 |

## 想手写配置文件（可选，不用也可以）

只有当你需要批量配置、用环境变量管理密钥、或配 `vision_model` / `embed_model` /
`timeout` 这些面板没暴露的字段时才需要。编辑 **`data/config/providers.yaml`**（不是
`config/` 里的模板）：

```yaml
providers:
  - id: deepseek
    kind: openai_compat
    label: DeepSeek
    base_url: https://api.deepseek.com/v1
    api_key: env:DEEPSEEK_API_KEY
    model: deepseek-chat
    priority: 10

  - id: qwen-vision
    kind: openai_compat
    label: 通义千问（视觉）
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: env:DASHSCOPE_API_KEY
    model: qwen-vl-max
    vision_model: qwen-vl-max
    priority: 20
```

`api_key` 三种写法：

- `sk-字面量`：直接写明文，只建议本机实验
- `env:变量名`：从环境变量读；未设置会**启动即报错**，不会带着空 Key 跑出一串 401
- `enc:v1:...`：Fernet 密文，密钥在 `data/secret.key`

`priority` 数字越小越先尝试；某家连续失败 3 次会进冷却期，之后走下一家
（`src/soapbot/providers/router.py` 的 failover）。所以**加第二家不只是备份，是真的会用上**。

改完重启服务，或者回第 07 页点一次「测试」确认。相关环境变量见
[configuration.md](configuration.md)，面板操作见 [guide.md](guide.md)。

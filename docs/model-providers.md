# 接入 AI 模型（不用改代码）

这份文档写给**不想看代码的人**。全程在网页里点，不需要打开编辑器、不需要懂
`base_url` 是什么、不需要重启服务。

## 开始之前：只需要准备一样东西

一枚 **API Key**（一串字符，形如 `sk-...`）。在你选的模型厂商官网注册账号，进控制台
找到「API Keys / 密钥管理」，创建一枚，复制下来。

不知道选哪家：先选 **DeepSeek** 或 **Qwen**，注册和充值流程最 straightforward，且面板
里已经预填好了地址和模型名。之后随时可以加第二家、第三家，互不影响。

> 本文档里，**预填表只写仓库里真实存在的值**（来自 `webui/src/views/ConfigView.vue`）；
> 「更多厂商的接入细节」一节的端点逐条核实于 2026-11 并附官方来源，不凭记忆写。
> 厂商控制台地址和可用模型会变，以厂商自己的文档与「拉取模型列表」的结果为准。

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
厂商当前真实可用的模型 ID，选一个再保存。DeepSeek 官方当前文档列出的模型包括
`deepseek-flash` 和 `deepseek-v4-pro`；模型会随厂商调整，最终以拉取到的列表和
[DeepSeek 官方模型文档](https://api-docs.deepseek.com/quick_start/pricing)为准。
仓库模板和面板默认使用 `deepseek-flash`；如果你的旧配置仍写着其他模型名，请点击「拉取模型列表」后选择官方返回的可用 ID。

## 原生协议：openai_compat 之外的四种 kind

手改 `data/config/providers.yaml` 时可选的 `kind`，端点拼接与鉴权方式来自
`src/soapbot/providers/` 的实现（不是约定俗成，是这四个类真正发的请求）：

| kind | 实际请求 | 鉴权头（代码自动加） | base_url 缺省值 |
| --- | --- | --- | --- |
| `openai_compat` | `POST {base}/chat/completions` | `Authorization: Bearer <key>` | `https://api.openai.com/v1` |
| `anthropic` | `POST {base}/messages` | `x-api-key` + `anthropic-version` | `https://api.anthropic.com/v1` |
| `gemini` | `POST {base}/models/{model}:generateContent` | `x-goog-api-key` | `https://generativelanguage.googleapis.com/v1beta` |
| `ollama` | `POST {base}/api/chat`（本地原生协议） | 无 | `http://127.0.0.1:11434` |

什么时候值得用原生：需要厂商只在原生协议上提供的字段（例如 Gemini 的
`batchEmbedContents` 嵌入批处理，`gemini` kind 实现了、兼容端点没有）。纯聊天用
`openai_compat` 就够，少一个分支少一种错。

## 更多厂商的接入细节

以下端点**逐一核实于 2026-11**，来源附在每家之后；厂商随时可能改版，填完仍以第 07 页
「测试」的绿灯为准，模型 ID 用「拉取模型列表」取真实值。全部走 `openai_compat`（第 07
页「添加一行」），中国版与国际版地址不同的一并列出。

| 厂商 | base_url（OpenAI 兼容） | 说明与来源 |
| --- | --- | --- |
| MiniMax（国内） | `https://api.minimaxi.com/v1` | 国内平台域名多一个 `i`；官方 OpenAI 兼容文档 [platform.minimax.io](https://platform.minimax.io/docs/api-reference/text-chat-openai) |
| MiniMax（国际） | `https://api.minimax.io/v1` | 同上；与国内账号不通用 |
| 腾讯混元 | `https://api.hunyuan.cloud.tencent.com/v1` | 官方兼容调用文档 [cloud.tencent.com](https://cloud.tencent.com/document/product/1729/111007)；示例模型 `hunyuan-turbos-latest` |
| 字节豆包（火山方舟） | `https://ark.cn-beijing.volces.com/api/v3` | 注意路径是 `/api/v3` 不以 `/v1` 结尾；先在 [方舟控制台](https://console.volcengine.com/ark)开通模型；官方文档 [volcengine.com](https://www.volcengine.com/docs/82379/1099455) |
| 百度千帆（文心） | `https://qianfan.baidubce.com/v2` | v2 完全兼容 OpenAI 协议；官方文档 [cloud.baidu.com](https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26)；示例模型 `ernie-4.5-turbo-128k` |
| 硅基流动 SiliconFlow | `https://api.siliconflow.cn/v1` | 聚合托管平台，注册即送额度、部分模型免费；官方快速开始 [docs.siliconflow.cn](https://docs.siliconflow.cn/en/userguide/quickstart) |
| OpenRouter | `https://openrouter.ai/api/v1` | 聚合网关：一个 Key 访问多家厂商，模型 ID 带厂商前缀（如 `anthropic/claude-…`）；[API 参考](https://openrouter.ai/docs/api_reference/overview) |
| Groq | `https://api.groq.com/openai/v1` | 注意是 `/openai/v1` 不是 `/v1`；[官方兼容文档](https://console.groq.com/docs/openai) |
| Mistral | `https://api.mistral.ai/v1` | 代码补全模型 Codestral 走单独端点与单独 Key（`https://codestral.mistral.ai/v1`）；[docs.mistral.ai](https://docs.mistral.ai) |

三家预设之外的国内大厂补充说明：

- **Moonshot 国际版**：`https://api.moonshot.ai/v1`（国内预设表里是
  `api.moonshot.cn`，两个站点的账号与 Key 不通用）。
- **DashScope 国际版**：`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  （国内预设表里是 `dashscope.aliyuncs.com`）。
- **智谱 GLM**：预填的 `https://open.bigmodel.cn/api/paas/v4` 同时兼容
  `/chat/completions` 调用，无需换路径。

### 本地推理服务的默认端口

都按「表里没有的厂商」一节处理（`kind: openai_compat`），Key 留空或填占位值：

| 服务 | 默认 OpenAI 兼容地址 |
| --- | --- |
| Ollama | `http://127.0.0.1:11434/v1`（预设已内置） |
| LM Studio | `http://127.0.0.1:1234/v1` |
| vLLM | `http://127.0.0.1:8000/v1`（`--port` 可改） |
| llama.cpp server | `http://127.0.0.1:8080/v1` |

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

## 轻任务模型槽：让摘要走一个便宜的模型

机器人有两类模型调用：

- **主聊**：回复用户，走 `priority` 最靠前的可用厂商；
- **轻任务**：宿主自己发起的小活——目前是会话摘要 / 上下文压缩（`ai/engine.py`
  的 summariser）。量小、频次高、对模型智力要求低，用贵的主聊模型做是浪费。

给轻任务指派一个便宜模型：在 `providers.yaml` 的任一条目里加 `extra: {light: true}`：

```yaml
providers:
  - id: deepseek
    kind: openai_compat
    label: DeepSeek（主聊）
    base_url: https://api.deepseek.com/v1
    api_key: env:DEEPSEEK_API_KEY
    model: deepseek-chat
    priority: 10

  - id: cheap-summary
    kind: openai_compat
    label: 便宜小模型（摘要）
    base_url: https://api.deepseek.com/v1
    api_key: env:DEEPSEEK_API_KEY
    model: deepseek-chat-lite      # 换成你厂商的便宜/小杯模型 ID
    priority: 90
    extra: { light: true }
```

三条规则（`tests/test_provider_light_slot.py` 钉住）：

1. **指派是加选**：被标记的实例不会被从主聊链里摘出去，单厂商部署不会因此坏掉；
2. **轻任务优先走被指派的实例**：多个 `light: true` 时仍按 `priority` 排序；
3. **没指派就回落主聊链**：默认部署行为与从前完全一致，不配也能跑。

轻任务只由宿主挑选——模型与插件都无法把请求路由进这个槽。

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
    model: deepseek-flash
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

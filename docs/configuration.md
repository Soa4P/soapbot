# 配置项与依赖

每一个环境变量、每一个配置文件、以及运行时依赖。

**写给：** 部署后在调参的人。第一次跑起来不需要读这里。

> 这部分从 `README.md` 搬出来，是为了让 README 只回答「是什么、怎么跑起来、坏了怎么办」。
> 内容没有删减。

---

## 配置清单

### 配置文件

| 文件 | 作用 | 缺失时 |
|---|---|---|
| `config/providers.yaml` | 模型端点与故障转移顺序 | 模型阶段禁用，机器人收消息但不回复 |
| `config/adapters.yaml` | QQ 协议端连接参数 | 不连接任何平台，只提供管理 API |
| `config/personas/*.yaml` | 人格卡 | 使用空系统提示（能回复，但没人格） |

密钥有三种写法：字面量、`env:VAR`、`enc:v1:...`（Fernet 密文）。
`env:` 指向的变量未设置时**启动失败**。

### 环境变量（前缀 `SOAPBOT_`，也可写入 `.env`）

完整模板见 [`.env.example`](../.env.example)。

> `SOAPBOT_ENV_FILE` 改变进程读取哪个 `.env`（默认工作目录下的 `.env`）。它本身只能由
> 环境变量给出、不能写进 `.env`。**用 systemd 或容器部署时建议显式设置**：这类环境的工作
> 目录不是仓库根目录，相对路径的 `.env` 会指向一个没人读的位置，而第 12 页的保存按钮
> 会以为自己保存成功了。

要点：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `6185` | 绑定 `0.0.0.0` 会暴露管理 API，务必同时配置鉴权 |
| `DATA_DIR` | `./data` | 可写卷 |
| `CONFIG_DIR` | `<data>/config` | **运行期配置，可写**。面板从这里读写 |
| `CONFIG_TEMPLATE_DIR` | `./config` | 镜像自带的默认值，**只读**；文件缺失时复制到 `CONFIG_DIR`，已有文件永不覆盖 |
| `MASTER_KEY` / `MASTER_KEY_FILE` | 空（自动生成到 `data/master.key`） | 容器优先用文件：环境变量对 `docker inspect` 可见 |
| `OWNER_IDS` / `ADMIN_IDS` / `MEMBER_IDS` | 空 | **唯一**的权限来源，逗号分隔 |
| `REPLY_GROUPS` | 空 | 在哪些群回话。空 = 所有群都回 |
| `MEMORY_COLLECT_GROUPS` | 空 | 在哪些群归档消息、写记忆。空 = 所有群都采集 |
| `GROUP_PERSONAS` | 空 | 按群绑定人格卡，`群号:人格ID`，逗号分隔。不列出的群走默认卡 |
| `GROUP_ALLOWLIST` / `GROUP_BLACKLIST` | 空 | `GROUP_ALLOWLIST` 是 `REPLY_GROUPS` 的旧名，仍可用但会告警；`GROUP_BLACKLIST` 是硬拒绝，优先于两者 |
| `PRIVATE_ALLOWLIST` | 空 | 私聊范围。**空 = 谁都不行**，不是谁都行 |
| `ALLOW_UNKNOWN_PRIVATE` | `false` | 「任何人都能私聊」的显式开关 |
| `ALLOW_UNTRUSTED_PLUGINS` | `false` | 允许 `trust: untrusted` 插件持有敏感能力 |
| `PLUGIN_INTEGRITY_MODE` | `block` | 插件代码在批准后被改动时的处理：`block` 拒绝加载、`warn` 放行并审计、`off` 不检查（批准记录里没有内容摘要时视为 `unknown`，不阻断）|
| `MAX_PLUGIN_WORKERS` | `16` | 同时存在的插件 worker **进程数**上限，一个插件一个进程。范围 `1..64`；与 `MAX_INFLIGHT_HANDLERS` 不同，`0` 是**非法值**（启动时报错），因为这是安全边界而非吞吐旋钮。注册时卡注册数，启动时再按存活进程数兜底。容量规划：每个 worker 自带一个解释器、一对管道与独立地址空间上限，调大前先按内存估算；容器的 `pids_limit` 只是最后一道兜底。健康报告会同时输出 `max_workers` 与 `live_workers`，只读巡检见 `deploy/plugin-worker-guard.timer` |
| `ENABLE_RUNTIME` | `true` | 关掉则只提供 HTTP API |
| `ENABLE_BUDGET` / `ENABLE_BILIBILI` | `false` | 可选能力，默认关闭 |
| `STREAM_REPLY` | `true` | 边生成边发。仅在适配器声明 `PROGRESSIVE` 时生效（目前只有 OneBot v11）。关掉则等整段回复生成完才发，首字延迟 = 总延迟 |
| `HISTORY_TURNS` | `16` | 回放进提示词的历史条数。调大会让上下文更容易超出预算，从而在每次回复前多一次摘要调用 |
| `MAX_PROMPT_TOKENS` | `6000` | 提示词硬上限。超出时压缩器会折叠历史（**多一次模型调用**），这是「回复慢」最常见的成因 |
| `MAX_EMBEDDING_CHARS` | `2000` | 送去嵌入的最长字符数。超长文本各家行为不一致（截断/报错/换维度），在这里截断让行为可控且可复现 |
| `MAX_RECALL_ITEMS` | `20` | 单次召回条数上限。召回内容会进入**后续每一轮**提示词，这是成本的上界 |
| `USER_QUOTA_CALLS` | `30` | 单个用户每窗口的模型调用上限。限流此前只统计「被拒绝的动作」，不管正常高频对话 |
| `USER_QUOTA_WINDOW_SECONDS` | `300` | 上述配额的时间窗口（滑动窗口，不是固定窗口） |
| `USER_QUOTA_NOTICE` | 见下 | 超配额时回复用户的固定话术。静默会让人以为机器人坏了 |
| `BREAKER_THRESHOLD` | `3` | 连续多少次「全部提供方失败」后才暂停模型调用。设为 1 会挡住流式空内容后的正常回退 |
| `MAX_INFLIGHT_HANDLERS` | `32` | 单个适配器同时处理的消息数上限。**超限丢弃而不是排队**：排队会让之后每条回复都背上积压延迟，且每个等待的消息仍占一个任务。`0` 关闭上限。被丢弃的 @ 消息会回一句 `BUSY_NOTICE`，普通群聊消息静默丢弃 |
| `HANDLER_TIMEOUT_SECONDS` | `60` | 单条消息从开始处理到放弃的总时限。超时即取消该任务并写审计；已发出的部分回复不回收。略高于一次最坏模型调用加一次重试，因此触发即代表「卡住」而非「慢」。`0` 关闭 |
| `BUSY_NOTICE` | `忙不过来啦，稍后再试一次` | 因上限被丢弃的 @ 消息收到的回复。**沉默不是可接受的回答**：在成员看来，被无视的 @ 和机器人挂了没有区别。设为空字符串则连 @ 也静默丢弃 |
| `BREAKER_BASE_SECONDS` | `15` | 暂停的首次时长，之后按指数增长 |
| `BREAKER_MAX_SECONDS` | `300` | 暂停时长上限 |
| `OUTBOUND_CONNECT_TIMEOUT` | `5` | 建连超时（秒），**与读取超时分开**。合并成一个值时，一个挂掉的端点要耗掉整段生成预算才触发故障转移 |
| `OUTBOUND_READ_TIMEOUT` | `60` | 读取超时（秒）默认值。Provider 在 `providers.yaml` 里配了 `timeout` 时以它为准 |
| `OUTBOUND_WRITE_TIMEOUT` | `10` | 发送请求体超时（秒） |
| `OUTBOUND_POOL_TIMEOUT` | `5` | 连接池满时等待空闲连接的时长（秒）。短是刻意的：排在池后面一分钟和挂死无法区分 |
| `OUTBOUND_MAX_CONNECTIONS` | `32` | 出站并发连接上限（所有主机合计）。不设上限时，一个热闹的群会为每条并发回复各开一条连接 |
| `OUTBOUND_MAX_KEEPALIVE` | `16` | 保留的空闲连接数。让同一会话里两条消息之间能复用连接与 TLS 会话 |
| `OUTBOUND_KEEPALIVE_EXPIRY` | `30` | 空闲连接保留秒数 |
| `OUTBOUND_MAX_REDIRECTS` | `3` | 允许的重定向跳数。**默认不自动跟随重定向**，每一跳都要重新校验目标 |
| `OUTBOUND_USER_AGENT` | `soapbot/0.1 (+https://github.com/soapbot/soapbot)` | 出站 UA。默认值标识的是库而不是部署，会让本机器人的流量在提供方的滥用看板上和任何 httpx 客户端无法区分 |
| `MODEL_ERROR_NOTICE` | 见下 | 所有提供方不可用时回复用户的降级话术 |
| `VOICE_ENABLED` | `false` | 入站语音转写。需要 Provider 声明 `transcribe` 槽位 |
| `VOICE_TTS_ENABLED` / `VOICE_TTS_VOICE` | `false` / `zh-CN-XiaoxiaoNeural` | 回复转语音。需要 `pip install -e ".[voice]"` |
| `VOICE_ALLOW_HOSTS` | 空 | 允许下载音频的内网主机，逗号分隔。**同机部署 NapCat 必须配**，见下 |
| `VOICE_MAX_BYTES` / `VOICE_LANGUAGE` | `8388608` / `zh` | 单条音频上限与转写语言提示 |
| `NAPCAT_WS_PORT` | `3001` | 协议端 OneBot WebSocket 端口。面板自己起容器时绑这个端口，扫描/连上时也用它 |
| `NAPCAT_HOME` / `NAPCAT_WEBUI_TOKEN` | 空 | 手工安装的 NapCat 才需要：前者指向它的目录（从中找 `webui.json`），后者直接给 token；容器方案的路径自动发现 |
| `DEFAULT_LOCALE` | `zh-CN` | 机器人**对群里说话**的语言（拒绝文案、语音标签）。不影响面板，面板按浏览器语言走；人格卡可用 `locale` 逐群覆盖 |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | `LOG_JSON=false` 便于人读终端 |

> 列表型变量支持三种写法：`123,456`、`123;456`、`["123","456"]`。
> 早期版本只接受 JSON，用逗号会以一条不说明正确语法的 `SettingsError` 启动失败。

> **`VOICE_ALLOW_HOSTS` 为什么必须显式配。** 音频 URL 由群成员给出，服务器带着自己的
> 网络位置去取，所以默认只允许公网地址（防 `169.254.169.254` 这类元数据端点）。但
> NapCat 从**它自己的 HTTP 端口**提供语音文件，同机部署下 `record.url` 就是
> `http://127.0.0.1:3000/...`——严格规则会把每一条语音都拒掉，而且是静默降级成
> `[语音]`。因此内网媒体端点要由运维在 `.env` 里指名：
>
> ```bash
> SOAPBOT_VOICE_ALLOW_HOSTS=127.0.0.1
> ```
>
> 默认留空是刻意的：让「信任一个内网地址」成为一次显式、可审计的决定，而不是藏在
> 代码里的隐含假设。白名单只豁免地址判定，不豁免协议——`file://` 仍然被拒。

---

## 依赖清单

运行时（`requirements.txt` 与 `pyproject.toml` 由 `make check-deps` 校验一致）：

| 依赖 | 用途 |
|---|---|
| `fastapi` + `uvicorn[standard]` | HTTP API 与控制台托管 |
| `pydantic` + `pydantic-settings` | 校验模型与配置解析 |
| `sqlalchemy[asyncio]` + `aiosqlite` | 异步 ORM 与 SQLite（含 FTS5） |
| `httpx` | 调用模型端点与 B 站 API |
| `websockets` | OneBot v11 的 WebSocket 客户端 |
| `pyyaml` | 配置与插件清单（用 `safe_load`） |
| `pillow` + `numpy` | 图片预处理；向量 BLOB 与余弦计算 |
| `pyjwt` | 控制台会话令牌 |
| `cryptography` | Fernet 加密 Provider 密钥 |
| `croniter` + `apscheduler` | 插件 cron 表达式与周期调度 |

可选与开发：

```bash
pip install -e ".[qq-official]"   # qq-botpy：仅 QQ 官方适配器需要
pip install -e ".[precision]"     # tiktoken：更精确的 token 计数
pip install -e ".[voice]"         # edge-tts：回复转语音（入站转写不需要它）
pip install -e ".[dev]"           # pytest / ruff / mypy / respx
```

> `structlog`、`watchdog`、`python-multipart` 已从依赖中移除：代码里没有任何引用。
> 依赖清单是审计面的一部分，留着它们会让评审者以为项目具备实际不存在的功能
> （结构化日志、热监听、multipart 上传）。插件上传改收原始请求体，因此不需要
> `python-multipart`。
>
> `edge-tts` 曾因「语音合成不存在」被一并移除。语音现在存在了，所以它回到了
> **可选** extra 里，而不是默认依赖：它是一个大多数部署永远不会调用的厂商网络
> 客户端，放进默认集只会让「pip install 就能跑」为单个功能变重。

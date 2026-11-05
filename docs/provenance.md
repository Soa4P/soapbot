# 来源与版权边界

这个项目借鉴了哪些外部设计、它们在代码里落在哪、以及哪些部分完全原创。

**写给：** 审计者与关心许可证的人。

> 这部分从 `README.md` 搬出来，是为了让 README 只回答「是什么、怎么跑起来、坏了怎么办」。
> 内容没有删减。

---

## 参考来源与它们对成品的影响

这一节不是致谢名单，而是**溯源**：说清哪些设计来自外部，以及它们在代码里落在哪里。
便于审计者判断哪些是原创、哪些是遵循既有规范（若发现任何直接移植的代码，请以此节
为线索核对 `LICENSE` 中的声明）。

### 1. AstrBot — 分层取舍（架构参考，无代码复用）

- 来源：[AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot)，许可证 **AGPL-3.0**。
- 参考内容：把「平台适配 / 模型提供 / 消息处理 / 插件」切成互相不认识的四层，
  让新增一个平台或一个模型端点不触碰业务代码。
- 落到本项目的具体位置：
  - `core/adapter.py`（适配器契约）↔ `adapters/`（OneBot v11、QQ 官方、mock）
  - `providers/base.py`（四个能力槽 `chat`/`stream`/`vision`/`embed`）↔ `providers/`
  - `core/pipeline.py` + `core/stages.py`（本项目形态：有序 Stage 链，而非中间件栈）
  - `plugins/`（插件运行时，本项目额外做了进程隔离与逐能力授权）
- **版权边界**：本仓库未包含 AstrBot 代码，标识符、注释、实现均为原创。分层思想本身
  不受著作权保护，但这条界线必须写明——见 `LICENSE` 末尾的说明。
  如果将来引入其代码，MIT 声明不再成立，发行条款必须随之变更。

### 2. OneBot v11 协议 — 接入契约

- 来源：[OneBot 11 标准](https://github.com/botuniverse/onebot-11)。
- 影响：`adapters/onebot11.py` 的事件字段名（`post_type` / `message_type` /
  `notice_type` / `retcode` / `echo`）与动作名（`send_group_msg`、`delete_msg`、
  `set_group_ban`、`set_group_kick`、`get_group_list`）全部按该标准。
  这是「能接 NapCat / Lagrange / go-cqhttp」的原因。
- 本项目额外处理了标准未强制的两件事：`retcode` 的宽容取值（`0/1/None`，
  各家实现不一致），以及 `set_group_kick` 的 `reject_add_request` 键在部分实现中
  被忽略——代码注释里写明了为什么宁可显式发送而不是省略。

### 3. QQ 官方机器人开放平台 — 平台约束

- 来源：[QQ 机器人文档](https://bot.q.qq.com/wiki/)。
- 影响：`adapters/qq_official.py` 里写死的常量不是猜的，而是平台规则：
  主动推送 20 条/群/天、被动回复窗口 5 分钟、单群 5 条/秒。
  这些通过 `quota_hint` 暴露给限流层排队，而不是让发送直接失败。
- 影响还体现在范围裁剪上：**不支持 QQ 频道（guild）**，`MessageScene.CHANNEL`
  故意不存在，`Intents` 只申请群聊与私聊。

### 4. OpenAI Chat Completions 形状 — Provider 的公共子集

- 影响：`providers/openai_compat.py` 直接说 HTTP，不绑 SDK。`tools` /
  `tool_calls` / `image_url` parts 等字段按该形状收发，因此 DeepSeek、通义、
  Moonshot 以及绝大多数中转服务可共用一套实现。
- 已知取舍写进了 `ai/engine.py`：工具结果以**系统提示里的不可信数据块**回灌，而不是
  严格回显 assistant 的 `tool_calls` + `tool_call_id`，因为部分中转会丢弃或拒绝后者。

### 5. 经典检索与安全工程实践 — 无特定出处

- BM25 关键词检索 + 余弦向量检索双路融合（`memory/store.py`）：FTS5 提供关键词通道，
  numpy 暴力余弦提供语义通道，单路可用即降级而非失败。
- 提示注入防护（`security/injection.py`）：不可信内容打上 canary 边界标记，
  模型若在输出里复述 canary 则整条回复丢弃——这是「检测到即视为已失守」的思路，
  而非事后过滤关键词。

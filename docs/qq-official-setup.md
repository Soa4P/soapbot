# 接入 QQ 官方机器人（OpenAPI v2）

这是本仓库现在推荐的接入方式。它不登录个人 QQ、不做协议逆向，账号和权限都由腾讯开放平台发放。

> **本轮状态**：适配器与服务端装配已完成，单元测试用注入的假 SDK 覆盖，**没有**用真实
> AppID 做过线上联调。第一次上线时以官方文档与平台返回为准，不要假设本地测试等于线上可用。

## 为什么不再默认第三方桥接

| 协议端 | 状态 | 依据 |
|---|---|---|
| go-cqhttp | 2022 年停更 | 上游已归档 |
| SnowLuma | 2026-11-09 起不可见 | `gh api repos/SnowLuma/SnowLuma` 返回 404 |
| NapCat | 停止功能维护，只保留版本更新直到失效 | 2026-11-10 提交 `docs: ending`，README 新增 `## Ending` |

官方机器人不受这些项目生命周期影响，但它有自己的边界，见下面的「能力上限」。

## 准备

1. 在 [QQ 开放平台](https://q.qq.com/) 注册开发者、创建**机器人**应用。
2. 拿到 **AppID** 与 **AppSecret**（`开发设置` 页）。AppSecret 只显示一次。
3. 在 `沙箱配置` 里把测试群加进去；群聊能力需要单独申请开通，审核通过前只有私聊可用。
4. 记下机器人的 **AppID**：本仓库把它同时用作 `account_id`，因为官方机器人没有另一个
   对外的数字 QQ 号。

## 配置

`config/adapters.yaml`：

```yaml
adapters:
  - kind: qq_official
    account_id: "102000000"        # 通常就是 AppID
    app_id: "102000000"
    app_secret: env:QQ_BOT_SECRET  # 推荐引用环境变量，不写明文
    enabled: true
```

`.env`：

```bash
QQ_BOT_SECRET=你的AppSecret
```

或者用向导：

```bash
python -m soapbot.cli setup --kind qq_official --app-id 102000000 --app-secret-env QQ_BOT_SECRET
```

需要可选依赖：

```bash
.venv/Scripts/python.exe -m pip install ".[qq-official]"
```

包名是 `qq-botpy`，不是 `botpy`。缺依赖时适配器会在启动时直接报出这句安装命令。

重启后检查：

```bash
python -m soapbot.cli doctor --strict
```

日志里应出现 `qq_official starting app_id=... (group + c2c only, no guild)`，面板的
「02 运行时」应显示该适配器在线。

## Intents

只请求两个：

```python
botpy.Intents(public_messages=True, direct_message=True)
```

不请求 `guild` 相关 intent，也不实现任何子频道 API。`MessageScene.CHANNEL` 在本仓库不存在。

## 配额与时间窗

| 项目 | 数值 | 含义 |
|---|---|---|
| 被动回复窗口 | 5 分钟 | 收到消息后 5 分钟内回复，算被动消息 |
| 每条消息回复次数 | 5 次 | 同一条入站消息最多回 5 条；第 6 条会被判重复 |
| 主动消息 | 20 条/分钟/关系 | 按接收方关系维度限流 |
| 每群每日接收 | 1000 条 | 超过后该群当天收不到主动消息 |
| 群消息接口 | 100 QPS | 接口本身的频率限制 |

适配器会把最近一条入站消息的 `msg_id` 与自增 `msg_seq` 带在回复上，所以正常对话走被动
窗口，不消耗主动配额。超过 5 次后不再携带 `msg_id`，此时才算主动消息——这一点在
`quota_hint()` 的 `passive_replies_left` 里可见。

## 能力上限（官方开放范围决定，不是本仓库没做）

- **没有群成员加入/退群事件**，也没有成员列表：无法做入群欢迎、成员统计。
- **没有踢人、禁言、撤回**：`MUTE` / `KICK` / `RECALL` 不在 `capabilities` 里。
- **没有频道（guild）**，也没有子频道。
- **没有流式输出**：群消息接口不支持流式参数。
- **Markdown 不支持**：`MARKDOWN` 不在 `capabilities` 里，长文本按纯文本降级。
- 富媒体需要先上传拿 `file_info`，再以 `msg_type=7` 发送；图片软限 20 MB、硬限 200 MB。

加功能前先查开放平台的接口清单，不要按「第三方协议端能做」推断官方也能做。

## 富媒体与降级

- 图片、语音、文件走两步：`post_group_file` / `post_c2c_file` 上传，再 `msg_type=7` 发送。
- 上传或发送失败时，该段会被替换成 `[图片发送失败]` 之类的占位文本，**整条回复仍然送达**。
- 日志只记录文件类型与异常类型，不记录 URL：媒体链接通常自带签名，写进日志等于泄漏。

## 故障排查

| 现象 | 先看什么 |
|---|---|
| 启动即报缺少 `qq-botpy` | 装 `.[qq-official]`，注意包名 |
| 401 / 403 | AppID / AppSecret 是否配对；沙箱群是否加了机器人 |
| 消息发不出，日志说 `send failed` | 是否超过 5 次被动回复；是否触达主动配额 |
| 图片变成 `[图片发送失败]` | 上传接口是否返回 `file_info`；URL 是否可被平台访问 |
| 私聊正常、群里没反应 | 群聊能力是否已申请开通；消息是否 @ 了机器人 |

## 与 OneBot 的关系

官方适配器是**主路径**；`kind: onebot11` 仍然保留，用于已经自建协议端的部署。两者可以
同时存在于配置文件里，但运行时只启用一个（按 `enabled` 与 `kind` 选择）。

如果你需要让其他 OneBot 生态工具接入同一个官方机器人，阶段二会提供 OneBot 11 网关；
本轮尚未交付，因此这里不给出链接，避免文档指向一个还不存在的文件。

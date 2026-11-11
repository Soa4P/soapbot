# OneBot 11 网关

让**已经存在**的 OneBot 11 客户端可以驱动官方 QQ 机器人。它不登录 QQ、不实现 QQ 协议，
也不绕过开放平台审核。

## 它是什么，不是什么

| | |
|---|---|
| **是** | 一个 OneBot 11 WebSocket 服务端：对外广播标准事件，接收标准动作，内部转成 `OutgoingMessage` 交给 `qq_official` 适配器 |
| **不是** | QQ 协议端。不注入 QQ 客户端、不逆向协议、不提供个人号登录 |
| **不是** | 能力放大器。官方平台没有的接口，这里统一返回 `1404` |

## 前置条件

1. `config/adapters.yaml` 里已启用 `kind: qq_official`（见 [qq-official-setup.md](qq-official-setup.md)）；
2. 已安装 `pip install ".[qq-official]"`；
3. 准备一个长随机串作为网关 token（客户端也要用）。

如果当前启用的是 `onebot11` 适配器，网关会**拒绝启动**：那只是把客户端再桥接一次，不增加能力。

## 配置

`.env`：

```bash
SOAPBOT_ONEBOT_GATEWAY_ENABLED=true
SOAPBOT_ONEBOT_GATEWAY_HOST=127.0.0.1
SOAPBOT_ONEBOT_GATEWAY_PORT=6700
SOAPBOT_ONEBOT_GATEWAY_PATH=/onebot/v11/ws
SOAPBOT_ONEBOT_GATEWAY_TOKEN=换成长随机串
```

token 为空时**拒绝启动**，没有「无鉴权但网络隔离」的例外。默认只绑 `127.0.0.1`；
要暴露到其他机器，先确认前面有 TLS 与访问控制。

## 连接与鉴权

客户端连接 `ws://127.0.0.1:6700/onebot/v11/ws`，二选一携带 token：

```http
Authorization: Bearer <token>
```

```
ws://127.0.0.1:6700/onebot/v11/ws?access_token=<token>
```

token 用常量时间比较；失败会以 `1008 unauthorized` 关闭，并写一条审计（`kind=gateway`,
`action=connect`, `outcome=deny`），不记录 token 本身。

## 事件

只发 `post_type=message`：

```json
{
  "time": 1762800000,
  "self_id": "BOT",
  "post_type": "message",
  "message_type": "group",
  "sub_type": "normal",
  "message_id": "MSG-1",
  "group_id": "GROUP-OPENID",
  "message": [
    {"type": "at", "data": {"qq": "BOT"}},
    {"type": "text", "data": {"text": "你好"}}
  ],
  "raw_message": "你好",
  "font": 0,
  "sender": {"user_id": "USER-1", "nickname": "nick", "card": "", "role": "member"}
}
```

ID 保持字符串：官方 openid 是不透明令牌，不是数字，强转 `int` 会截断或报错。

## 动作

| 动作 | 说明 |
|---|---|
| `send_msg` | 按 `message_type` 路由；缺少时由 `group_id` / `user_id` 推断（两者都缺或都给则报 `1400`） |
| `send_group_msg` | 需要 `group_id` 与 `message` |
| `send_private_msg` | 需要 `user_id` 与 `message` |
| `get_login_info` | `user_id` / `nickname` |
| `get_status` | `online` / `good` |
| `get_version_info` | 应用版本、`protocol_version=v11`、`adapter=qq_official` |
| `can_send_image` | 由适配器 `capabilities` 决定 |
| `can_send_record` | 同上 |
| `get_group_list` / `get_friend_list` | 显式拒绝：官方平台没有这两个接口 |

响应包络固定：

```json
{"status": "ok", "retcode": 0, "data": {...}, "echo": "原样回传"}
```

失败时 `status=failed`，`retcode` 为 `1404`（不支持）、`1400`（参数错）、`1200`（发送失败
或限流）。**不会**用空 `data` 假装成功。

## 限制

- 每连接 600 次动作/分钟；超过返回 `1200`；
- 最多 16 个并发客户端，超出以 `1013` 关闭；
- 单帧上限 1 MiB；
- 广播对每个客户端独立 `send`，慢或断开的客户端被移除，不阻塞其他连接。

## 安全边界

- 网关只转发标准动作，不暴露插件、文件系统或配置写入；
- 发送能力等同于官方机器人本身，受 5 分钟被动窗口与主动消息配额约束；
- 审计只记动作名、结果与失败类型，不记消息内容、不记 token、不记媒体 URL。

## 故障排查

| 现象 | 原因 |
|---|---|
| 连接被 `1008` 关闭 | token 不匹配，或缺 `Authorization` / `access_token` |
| 启动日志说拒绝启动 | token 为空，或当前适配器是 `onebot11` |
| `retcode=1404` | 动作不在表里，或属于官方平台没有的能力 |
| `retcode=1200` 且 wording 是 rate limited | 单连接动作过快 |
| 事件收不到 | `qq_official` 适配器没在线；先看 02 运行时页 |

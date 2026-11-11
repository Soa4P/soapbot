# 云端聊天存档

网页端和手机端读的是同一份数据库，写的只有备注。本文说明这份数据的三条硬规则，
以及每条规则在代码里的位置——因为「只读」这种词很容易在后续重构里被悄悄放宽。

## 一条规则：QQ 是唯一信源

存档里的 `user` / `assistant` 行只由适配器写入（`core/stages.py`、`core/observer.py`）。
`api/chat.py` 里没有任何 `Adapter.send` 调用，也没有持有适配器的引用：

```text
GET  /api/chat/sessions                 读
GET  /api/chat/messages                 读
GET  /api/chat/stream                   读
POST /api/chat/notes                    写一行 role="note"
```

第四行的写入对象是 `MemoryStore.add_note`，它只接受内容、会话和作者，没有适配器参数可
以传错。返回值里的 `delivered: false` 不是装饰：它让客户端有字面依据显示「未发送」。

备注在 QQ 侧不可见，也不会被下一条群消息「带出去」。不要把它当草稿箱，它不是。

## 第二条规则：会话授权在服务端

`chat_memberships` 决定一个账号能看到哪些 `session_key`。三条实现细节：

- 缺行即拒绝，不是「默认可见」；
- 越权读取返回 **404 而不是 403**，因为 403 等于确认「这个会话存在」；
- 列表接口在 SQL 之后还要按成员表过滤（`api/chat.py::sessions`），前端隐藏行不算边界。

`role="owner"` 的账号跳过成员表。因此创建所有者是一次性操作：`create_owner` 在账号表
非空时直接拒绝，第二次调用不可能成功（`tests/test_accounts.py` 有对应用例）。

## 第三条规则：增量用 `after_id`

`MemoryStore.messages_since` 用 `id > after_id` 而不是 offset：

- SQLite 里 `id` 单调，偏移量则会在有新消息落库时错位——同一个客户端可能重复收到一条、
  或整条跳过；
- `limit` 上限 200，慢客户端不会一次把全量拖下来。

`/api/chat/stream` 是 `text/event-stream`，但实现是每 1.5 秒查询一次游标，不是消息总线。
文档这么写是为了避免误用：多实例部署时它不会收到别的进程写入的消息，别指望它做推送。

## 账号

- 登录：`POST /api/accounts/login`，用户名 + 密码，签发与面板相同的会话 Cookie。
- 注册：`POST /api/accounts/register`，必须带邀请码；邀请码只存 SHA-256，一次性消耗。
- 首个所有者：`POST /api/accounts/owner`，需要面板的一次性 bootstrap token，且仅当账号表
  为空时可用。
- 密码：`hashlib.scrypt(n=2**14, r=8, p=1)`，存 `salt` 与 `hash` 两个字段，比较用
  `hmac.compare_digest`。

不引入 argon2 是有意的：scrypt 已在标准库里提供内存困难特性，为它加一个依赖不值得。

## 端开关

| 环境变量 | 默认 | 含义 |
| --- | --- | --- |
| `SOAPBOT_CHAT_WEB_ENABLED` | `true` | 网页端；唯一常开的入口 |
| `SOAPBOT_CHAT_APP_ENABLED` | `false` | 手机端可以访问 `/api/chat/*` |
| `SOAPBOT_CHAT_DESKTOP_ENABLED` | `false` | 桌面壳可以访问 `/api/chat/*` |

三个全关时 `/api/chat/*` 返回 404，像这个部署里没有这些路由一样。目的很直接：装到别人
设备上的客户端不该默认能读存档。

## 已知边界

- 没有消息撤回与编辑：存档只追加。
- 没有全文检索：`timeline` 是 offset 分页，跨大群会慢，改用游标前不动它。
- 没有多实例共享：SSE 轮询只看得见本进程写入的行。

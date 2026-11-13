# 云端聊天存档与多端对话

网页端和手机端读的是同一份数据库。默认只写备注；开了对话开关之后，每个账号还能在自己
的会话里和机器人真正对话。本文说明这份数据的硬规则，以及每条规则在代码里的位置——因为
「只读」这种词很容易在后续重构里被悄悄放宽。

## 信源：按会话前缀分

- `qq:*` 会话（`onebot11:group:…`、`qq_official:…`）的信源是 QQ：这些行只由适配器
  侧的管线写入，`api/chat.py` 到今天也不持有任何 QQ 适配器的引用。**唯一例外**见下文
  「统一会话」：owner 绑定 + 显式开关同时成立时，被绑定用户的 QQ *私聊*落进其账号的
  `web:private:*` 会话——落库的行仍然如实记 `adapter=onebot11`，信源仍是 QQ 平台。
- `web:private:account-<id>` 会话的信源是网页/手机端自己：`POST /api/chat/messages`
  构造一条进程内消息交给 `runtime.dispatch`，**由管线**（Guard → 注入检测 → 白名单 →
  限频 → 人格 → 模型 → 回复 → 落库）写出 user 与 assistant 两行。端点本身仍然没有
  适配器引用——「回复由管线产生并由管线落库」由调用图保证，不由注释保证。

```text
GET  /api/chat/sessions                 读
GET  /api/chat/messages                 读（三种翻页模式，见下）
GET  /api/chat/stream                   读（SSE，1.5 秒游标轮询）
POST /api/chat/notes                    写一行 role="note"，永不投递
POST /api/chat/messages                 对话（SOAPBOT_CHAT_TALK_ENABLED=true 时才存在）
PUT  /api/accounts/<id>/binding         QQ 号绑定（owner，SOAPBOT_CHAT_UNIFIED_ENABLED 用）
```

备注在 QQ 侧不可见，也不会被下一条群消息「带出去」。不要把它当草稿箱，它不是。
对话则相反：机器人会真的回答，回复只出现在这个会话里。

## 第二条规则：会话授权在服务端

`chat_memberships` 决定一个账号能看到哪些 `session_key`。三条实现细节：

- 缺行即拒绝，不是「默认可见」；
- 越权读取返回 **404 而不是 403**，因为 403 等于确认「这个会话存在」；
- 列表接口把成员表当**查询条件**下推（`MemoryStore.list_sessions(session_keys=...)`，走
  `session_key IN (...)`），不是取 200 条再在 Python 里筛。这一点是被打回后改的：先取后筛
  会让只被授权一个冷清群号的成员看到空列表，把权限问题伪装成「还没有被授权的会话」。
  前端隐藏行从来不算边界。

`role="owner"` 的账号跳过成员表。因此创建所有者是一次性操作：`create_owner` 在账号表
非空时直接拒绝，第二次调用不可能成功（`tests/test_accounts.py` 有对应用例）。

## 第三条规则：增量用 `after_id`，首屏用 `latest`

`/api/chat/messages` 有三种互斥的翻页模式（同时给两种返回 400）：

- `after_id=N`（原语义）：`id > N` 的升序页，给轮询/SSE 的正向同步用。游标用 `id`
  而不是 offset：归档只在尾部增长，offset 会在并发写入时重复或漏行；`limit` 上限 200。
- `latest=true`：**最新**一页升序 + `has_older`。这是打开旧会话的首屏——早期只有
  `after_id` 时，客户端首屏拿到的是最早的 100 条，老会话的中间历史永远看不到，
  这是那个设计留下的洞，`latest` 是补法。
- `before_id=N`：N 之前的最后一页升序 + `has_older`，给「加载更早」按钮用。
  `has_older` 由服务端单独探测（不是 `len(rows)==limit`），首页恰好落在第一条消息时
  按钮会正确消失。

网页端与手机端会话列表 30 秒自动刷新一次（网页端定时器、手机端定时器 + 返回聊天页时），
新会话在第一条消息落库后最多半分钟内出现。

`/api/chat/stream` 是 `text/event-stream`，但实现是每 1.5 秒查询一次游标，不是消息总线。
文档这么写是为了避免误用：多实例部署时它不会收到别的进程写入的消息，别指望它做推送。

## 对话：一个账号一个会话

`SOAPBOT_CHAT_TALK_ENABLED=false`（默认）时 `POST /api/chat/messages` 返回 404；开启后
每条规则仍然成立：

1. **会话由服务端推导**：`web:private:account-<账号id>`，请求体里只有 `content`。
   客户端能指定会话等于给了伪造别人会话的钥匙。`account-` 前缀保证发送者 id 永远
   不会撞上 owner/admin/member 名单里的纯数字 QQ 号（`normalize_id` 对字母前缀的
   id 保形）。
2. **逐个授权**：账号必须有自己的 membership 行（owner 豁免）。没有授权的账号和读
   别人的会话一样拿到 404——同一个「会话不存在」答案，不泄露存在性。
3. **每条消息都过完整管线**：注入检测、Guard 的限频（web 用户有独立的 30 次/300 秒
   滑窗，key 含适配器名）、人格与记忆都按 QQ 消息同一条路径走。web 分支只改变了
   白名单的准入判断（准入已在 API 层由「密码 + membership」双重决定），QQ 私聊的
   默认拒绝一字未动，`tests/test_chat_talk.py` 有对应用例钉住这一点。
4. **开关改动要重启**：web 适配器在启动时随 `chat_talk_enabled` 注册，进程内没有
   热加载。

## 统一会话：四端一份连续对话

`SOAPBOT_CHAT_UNIFIED_ENABLED=false`（默认）时什么都不发生——QQ 私聊仍按原规则默认拒绝，
`qq:private:*` 与 `web:private:*` 互不相干。开启后，**第 15 页由 owner 把 QQ 号绑定到
账号**（`PUT /api/accounts/<id>/binding`，`DELETE` 解绑），该 QQ 号的私聊事件在
`runtime.dispatch` 里被会话映射器改写：

- 映射发生在**会话锁之前**——映射改变的就是锁键本身（`core/runtime.py` dispatch 开头）；
- 事件的 `adapter` 保持 `onebot11`：机器人的回复仍走 QQ 协议端发回去（回复只回来源端，
  不跨端推送），落库的行也如实记录 `adapter=onebot11`；
- 落点是 `web:private:account-<id>`：网页/App/桌面壳读到的与 QQ 里说的从此是同一条
  时间线，模型的上下文跨设备连续。

信任链三重，缺一即回到旧隔离：

1. **owner 绑定**（`accounts.qq_user_id`，唯一索引，QQ 号与账号一一对应）——QQ 用户
   无法自助认领，冒用别人的号发消息进不了别人的会话；
2. **显式开关** `SOAPBOT_CHAT_UNIFIED_ENABLED`（默认关）；
3. **既有 membership 授权**——统一会话沿用 web talk 的逐账号授权，被停用的账号映射
   不到会话（`account_by_qq_user` 拒绝 disabled 行）。

白名单对这条路径有显式分支（`core/stages.py`）：PRIVATE + onebot11 + 会话已被映射 +
flag 开 → 放行；**未绑定** QQ 私聊的默认拒绝一字未动。配额仍按 `adapter:user_id` 独立
计数——同一个账号在网页和 QQ 里是两个独立的限频窗口。

## 消息状态：发送失败与被拒可见

消息行带 `state`（schema v6 起；旧行为 NULL，一律按 `ok` 读）：

- `ok`：正常送达；
- `send_failed`：模型回了但平台投递失败——以前这种情况**一行都不写**，客户端看到的
  是沉默；现在回复照落库，四端渲染灰色失败徽标；
- `rejected`：管线拒绝了这条消息（Guard 限频、注入检测等），`reason` 是短 token
  （不是正文）。只对已认证的 talk 路径补写这种行——QQ 平台来的未验证文本被拒时仍然
  不留痕（平台信源原则）。

客户端的「发送中」是乐观 UI 状态，永远不进数据库：请求返回后由服务端行替代或转为失败。

## 账号

- 登录：`POST /api/accounts/login`，用户名 + 密码，签发与面板相同的会话 Cookie。
- 注册：`POST /api/accounts/register`，必须带邀请码；邀请码只存 SHA-256，一次性消耗，默认
  72 小时过期（`hours` 可调，上限 30 天）。明文只在创建响应里出现一次，发错只能作废重发。
- 首个所有者：`POST /api/accounts/owner`，需要面板的一次性 bootstrap token，且仅当账号表
  为空时可用。空表检查在写事务**内部**，否则两个并发 bootstrap 会都读到 0。
- 密码：`hashlib.scrypt(n=2**14, r=8, p=1)`，存 `salt` 与 `hash` 两个字段，比较用
  `hmac.compare_digest`。密码至少 8 位；用户名 3-32 位，只允许 `[A-Za-z0-9_.-]`。
- bootstrap token 不是存档钥匙：拿它请求 `/api/chat/*` 返回 **401**，不是「以所有者身份
  读全部」。它只用来建第一个账号，建完就该被 `POST /api/auth/login` 消费掉（删除
  `init_token.txt` 并留下 `init_token.redeemed` 标记）；只当 Bearer 用并不算消费。
- 停用账号后，已经签发出去的 token 立即失效：鉴权每次按 subject 回查账号状态。
- 停用 / 启用：`POST /api/accounts/{account_id}/status`，body `{"status": "active" | "disabled"}`，
  仅 owner。**没有删除接口**——删号会连同它的会话授权一起消失，而停用保留历史、随时能开回来。
  最后一个活动的 owner 不能被停用，否则谁也开不回来，只能改库。
  这些操作在**第 15 页「账号与邀请」**都有按钮：列表、停用/启用、签邀请码（明文只显示一次）、
  授权会话（「与机器人对话」一键预填 `web:private:account-<id>`）。

不引入 argon2 是有意的：scrypt 已在标准库里提供内存困难特性，为它加一个依赖不值得。

## 端开关

| 环境变量 | 默认 | 含义 |
| --- | --- | --- |
| `SOAPBOT_CHAT_WEB_ENABLED` | `true` | 网页端；唯一常开的入口 |
| `SOAPBOT_CHAT_APP_ENABLED` | `false` | 手机端可以访问 `/api/chat/*` |
| `SOAPBOT_CHAT_DESKTOP_ENABLED` | `false` | 桌面壳可以访问 `/api/chat/*` |
| `SOAPBOT_CHAT_TALK_ENABLED` | `false` | 对话端点 `POST /api/chat/messages` 是否存在 |
| `SOAPBOT_CHAT_UNIFIED_ENABLED` | `false` | 已绑定 QQ 号的私聊落进账号的 web 会话（见「统一会话」） |

三个全关时 `/api/chat/*` 返回 404，像这个部署里没有这些路由一样。目的很直接：装到别人
设备上的客户端不该默认能读存档。talk 开关单独管发送；关掉时同样的 404，开启时也仍要
先授权会话（见上）。

## 已知边界

- 没有消息撤回与编辑：存档只追加。
- 没有全文检索：`timeline` 是 offset 分页，跨大群会慢，改用游标前不动它。
- 没有多实例共享：SSE 轮询只看得见本进程写入的行。
- 对话不计费、不审批：web 对话的成本控制只有 Guard 的限频与 provider 自身的配额；
  budget 审批流不覆盖按条计费。把 talk 交给不熟的人之前想清楚这一点。

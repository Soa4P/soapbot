# 手机端骨架（Flutter）

只做一件事：读取云端存档。QQ 仍是消息来源，App 不发送任何消息，输入只写备注。

## 状态

源码骨架，**未在真机或模拟器上构建验证过**——本轮没有安装 Flutter SDK。以下命令是
按 `pubspec.yaml` 写的，第一次跑请以 `flutter doctor` 的输出为准。

## 四屏

| 文件 | 作用 |
| --- | --- |
| `lib/screens/login_screen.dart` | 用户名密码登录，或邀请码注册 |
| `lib/screens/sessions_screen.dart` | 被授权的会话列表 |
| `lib/screens/chat_screen.dart` | 消息流（轮询 `after_id` 游标） |
| `lib/screens/note_sheet.dart` | 备注输入，返回文本，不发消息 |

## 构建

```bash
cd mobile
flutter pub get
flutter analyze
flutter build apk --dart-define=SOAPBOT_BASE_URL=https://your.domain
```

`SOAPBOT_BASE_URL` 默认 `http://127.0.0.1:16700`，只适合模拟器；真机必须指向部署的
域名，且服务端需要设置 `SOAPBOT_CHAT_APP_ENABLED=true`，否则 `/api/chat/*` 返回 404。

## 与网页端的两点差异

- **同步方式**：网页端用 `EventSource` 订阅 `/api/chat/stream`；App 用两秒轮询同一个
  `after_id` 游标。服务端的 SSE 本身就是 1.5 秒轮询，所以两者语义一致，App 少一个长连接。
- **会话保持**：网页端依赖 HttpOnly Cookie；App 把返回的 Cookie 存进
  `flutter_secure_storage`，启动时先调 `/api/accounts/me` 验证，失效就回到登录页。

## 不做什么

- 不实现发送、撤回、转发；没有对应的 API 可以调。
- 不做应用商店签名与上架配置。
- 不缓存消息到本地数据库：存档在云端，本地只保留登录 Cookie。

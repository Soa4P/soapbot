# 手机端（Flutter）

读云端存档，写备注；被授权对话后，可以在自己的会话里和机器人对话。QQ 仍是 `qq:*`
会话的消息来源，App 不发送任何 QQ 消息。

## 状态

**2026-11-12 起过了完整本机验证**（Flutter 3.50.0 + JDK 17 + Android SDK 36）：

- `flutter analyze` 0 错误（仅 7 条 `material.dart` 弃用提示——新 SDK 把 Material 挪进了
  `package:material_ui`，但 pubspec 声明的下限是 3.22，换 import 之前旧 SDK 会装不上，
  保留；CI 的 mobile job 同样按默认把 info 保持非致命）
- `flutter test` 12 项全过（模型解析、翻页参数、对话发送、会话/聊天两屏的备注与对话模式）
- `flutter build apk --debug` 实测通过（Gradle assembleDebug 536s），产物
  `build/app/outputs/flutter-apk/app-debug.apk`——**可测试安装包**，直接
  `adb install` 或传到手机点开安装（系统会提示未知来源，允许一次即可）。
  applicationId 是 `dev.soapbot.archive`；release 签名与上架配置仍不做（见「不做什么」）。

## 四屏

| 文件 | 作用 |
| --- | --- |
| `lib/screens/login_screen.dart` | 用户名密码登录，或邀请码注册 |
| `lib/screens/sessions_screen.dart` | 被授权的会话列表（30 秒自动刷新 + 下拉刷新） |
| `lib/screens/chat_screen.dart` | 消息流（轮询 `after_id` 游标 + 「加载更早」向前翻页） |
| `lib/screens/note_sheet.dart` | 备注输入，返回文本，不发消息 |

## 对话模式

服务端设 `SOAPBOT_CHAT_TALK_ENABLED=true` 且所有者给你的账号授权了
`web:private:account-<id>` 会话后，打开那个会话，底部输入框从「写一条备注」变成
消息输入框：发一条，机器人在同一会话里回答。其余会话仍是备注按钮，右上角横幅
「这里只记录，不发送」只在备注会话显示。

## 构建

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --dart-define=SOAPBOT_BASE_URL=https://your.domain
```

`SOAPBOT_BASE_URL` 默认 `http://127.0.0.1:16700`，只适合模拟器；真机必须指向部署的
域名，且服务端需要设置 `SOAPBOT_CHAT_APP_ENABLED=true`，否则 `/api/chat/*` 返回 404。
首次构建前需要 `flutter create . --project-name soapbot_archive --platforms android`
生成过的 `android/` 目录已在仓库里，新克隆直接 `flutter pub get` 即可；Gradle 需要
JDK 17 与 `ANDROID_HOME` 指向的 Android SDK。

## 与网页端的两点差异

- **同步方式**：网页端用 `EventSource` 订阅 `/api/chat/stream`；App 用两秒轮询同一个
  `after_id` 游标。服务端的 SSE 本身就是 1.5 秒轮询，所以两者语义一致，App 少一个长连接。
- **会话保持**：网页端依赖 HttpOnly Cookie；App 把返回的 Cookie 存进
  `flutter_secure_storage`，启动时先调 `/api/accounts/me` 验证，失效就回到登录页。

## 不做什么

- 不实现发送到 QQ、撤回、转发；没有对应的 API 可以调——对话回复也只存在于
  云端会话里。
- 不做应用商店签名与上架配置。
- 不缓存消息到本地数据库：存档在云端，本地只保留登录 Cookie。

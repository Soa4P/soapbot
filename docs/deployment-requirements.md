# 最低系统配置与部署要求

本文是"跑起来"的硬底线与各端的构建要求。实际资源占用随消息量、插件数与模型并发
线性变化；下表给的是**可验证的起点**，不是拍脑袋的推荐值。

## 本体（soapbot 服务端）

| 项 | 最低 | 说明 |
|---|---|---|
| OS | Linux / Windows / macOS | 纯 Python + SQLite，无平台专用依赖 |
| Python | **3.12+**（硬要求） | `pyproject.toml` `requires-python = ">=3.12"` |
| CPU | 2 vCPU | 模型推理在**外部端点**，本机只做管线编排与 SQLite |
| 内存 | **2 GB**（保守 3 GB） | 实测参考：2 vCPU / 3.9 GB 主机上 uvicorn + 适配器约 150–250 MB（含 scrypt 登录峰值）——见 [deployment-web-chat.md](deployment-web-chat.md) 的实测记录 |
| 磁盘 | **1 GB** 数据 + 500 MB 环境 | `data/`（SQLite + 存档 + 插件 + 急停文件）默认在仓库根下；对话存档与日志随用量增长 |
| 网络 | 出站 HTTPS：模型端点、QQ 官方（websocket）、（可选）B 站/更新索引 | 入站：`127.0.0.1:6185`（面板/多端 API），QQ 网关 `127.0.0.1:6700` |

运行时依赖 15 项全部 pin 精确版本（fastapi/sqlalchemy/aiosqlite/httpx/pillow 等），
无 C 扩展编译需求（pillow/numpy 有 wheel）。可选 extra：`qq-official`、`voice`
（edge-tts）、`screen`（mss）、`precision`（tiktoken）、`sidecar`（pyinstaller，
仅打包桌面壳时需要）。

## 桌面壳（强执行端，Windows）

| 项 | 值 |
|---|---|
| 构建 | Node ≥ 22.16 + Rust ≥ 1.77 + NSIS；三段式：webui 构建 → sidecar 打包（onefile ≈ 46 MB）→ `tauri build`（NSIS ≈ 47 MB） |
| 运行 | Windows 10/11；桌面壳 = 后端 + 控制面的宿主，**键鼠注入只发生在这里** |
| 磁盘 | 安装 ≈ 200 MB（sidecar 内嵌） |

## 手机端（Flutter，弱端）

| 项 | 值 |
|---|---|
| 构建 | Flutter ≥ 3.22（本机验证 3.50.0）+ JDK 17 + Android SDK 36，本机 SDK 约 **10 GB** 磁盘；CI 每次构建出 APK，装测试包不需要本机 SDK |
| 运行 | Android 8+；内存占用与普通 WebView 应用同量级 |

## updatepilot（独立依赖更新 bot，GitHub Actions）

| 项 | 值 |
|---|---|
| 运行位置 | 调用方仓库的 Actions runner（ubuntu-latest 即可） |
| Python | 3.10–3.12（CI 矩阵覆盖） |
| 外部资源 | 模型 API key（可选，不配则只开 PR 不审查）；PyPI / npm / GitHub API 免 key（GitHub API 匿名限速，建议传 GITHUB_TOKEN） |

## 面板（webui）

构建产物约 **552 KiB**（34 个文件，vendor 单拆 + 逐 view 懒加载 chunk），由服务端
直接托管——面板不单独部署。浏览器要求：支持 ES2020 的现代 Chrome/Edge/Firefox。

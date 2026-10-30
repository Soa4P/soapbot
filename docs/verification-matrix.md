# 验证矩阵：哪些能力被证明过，哪些只是一行代码

这份表存在的理由很直接：仓库里有三种很容易混为一谈的说法——

- 「有实现」（文件存在，函数被调用过）
- 「有自动测试」（pytest 里跑得通）
- 「真的能用」（在浏览器/真机上跑通过一次）

前两种可以靠读代码确信，第三种只能靠证据。此前几轮把三者混写过，其中最典型的一次是
一个后端早已写入、前端一个字段都没渲染的字段（`trace.chunks`）：测试全绿，功能不存在。

**结论只允许三种取值**，定义如下：

| 取值 | 含义 |
|---|---|
| **自动 + 实测** | 有自动化断言，并且在真实进程/浏览器里跑通过一次，附观察到的现象 |
| **仅自动** | 只有自动化断言。这不等于「能用」，只等于「按当前理解是对的」 |
| **未验证** | 没有证据。写在这里不是为了认错，是为了不让下一个人以为它已经好了 |

本机没有 Docker、没有真实 STT 凭据、`providers: []` 未接任何云端端点——这三件事不会因为再多写几行代码而改变，所以它们固定落在「未验证」。

---

## 一、本轮改动的能力

| 能力 | 代码位置 | 自动化测试 | 人工实测 | 结论 |
|---|---|---|---|---|
| 分句渐进发送 | `ai/stages.py`、`core/progressive.py`、`core/stages.py` | `tests/test_streaming_wiring.py`（14 项） | 09 页：用真实 `ModelStage`+`ReplyStage` 生成 3 句回复，页面显示 3 条分句 | **自动 + 实测**（本地 fake provider，非真实云端） |
| 09 页流式面板 | `webui/src/views/PipelineView.vue`、`api/client.ts` | `tests/test_pipeline_trace.py`（34 项，含 API 层 `chunks`/`stream` 断言） | 浏览器三种形态：3 句、1 句、单条发送；中英双语各一次；12 页无横向溢出 | **自动 + 实测** |
| 面板内编辑 MCP（引擎） | `core/mcp_write.py` | `tests/test_mcp_write.py`（18 项：增删改、argv 强制、重复名、脱敏、陈旧哈希） | — | **仅自动**（引擎本身不直接面向用户） |
| 面板内编辑 MCP（API） | `api/config_write.py` | `tests/test_mcp_config_api.py`（14 项：权限、409/422、审计不留值、热重载） | 面板实际调用同一组端点完成写入 | **自动 + 实测** |
| 面板内编辑 MCP（界面） | `components/McpServers.vue`、`views/ConfigView.vue` | i18n 静态检查（键必须双目录存在、模板无残留中文） | 浏览器：新增 → `查看将要写入的改动` → 确认 → `mcp.yaml` 落盘。diff 显示 `GITHUB_TOKEN: redacted:be0b532d`，磁盘上写的是真值 | **自动 + 实测** |
| `McpManager.reload`（热生效） | `mcp/client.py` | `tests/test_mcp_write.py`（3 项：保留未变 client、改名才重启、空列表）、`test_mcp_wiring.py::test_the_first_server_added_shows_up_without_a_restart` | 带真服务的热生效：07 页写入后表格显示「已连接 · 14 个工具」，无需重启 | **自动 + 实测** |
| 真实 MCP 服务端（第三方 filesystem server） | `mcp/client.py`、`core/builder.py` | `tests/test_mcp_live.py`（opt-in：`SOAPBOT_LIVE_MCP=1`）、`test_mcp_wiring.py`（15 项） | 07 页写入 `npx -y @modelcontextprotocol/server-filesystem <dir>` → 热加载 → 14 个工具；`tools/call` 读回文件内容 | **自动 + 实测** |
| MCP 握手协商与失败区分 | `mcp/client.py` | `test_mcp_wiring.py`（服务端回旧版本时采纳其版本；握手期崩溃的错误带 stderr 与退出码） | 真实服务端返回 `2025-06-18`，客户端采纳而非假定自己的 | **自动 + 实测** |
| 三家 Provider 的报文映射 | `providers/anthropic.py`、`gemini.py`、`ollama.py` | `tests/test_providers_mapping.py`（7 项：system 提升、data URL 转换、token 字段名、`done` 终止、角色重命名、429→`ProviderError`） | — | **仅自动** |
| 可访问性静态规则 | `scripts/check_a11y.py` | 22 个组件 × 4 条规则（按钮名称、点击目标可聚焦、img 有 alt、对话框有语义） | 规则查出两处表格行只能鼠标点击，已补 `tabindex` 与 Enter/Space。**但这两行的键盘路径只由模板断言覆盖**：本机没有已配置的人格与会话，表格为空，浏览器里按不到那一行 | **仅自动**（键盘实测缺数据） |
| 测试断层扫描 | `scripts/check_test_gaps.py` | 孤儿模块基线（16 个）+ 文档数字与看板一致性 | 扫出 19 个无人引用的模块与 1 处过期数字；三家 provider 补测后降为 16 | **自动 + 实测** |
| 上游连通性静态检查 | `security/posture.py` | `tests/test_posture.py`（7 项：空配置、缺文件、坏 YAML、本机端点、明文 http、远端、进报告） | `python -m soapbot.cli doctor` 实跑，输出 `[warn] provider.upstream (medium)` | **自动 + 实测** |
| `doctor --probe` 网络探测 | `security/posture.py`、`cli.py` | `test_posture.py`：401 ⇒ 可达、503 ⇒ 不可达（mock transport，规则本身）；另有本地回环服务端的 Socket 测试 | 只对本地回环跑过。**本机回环被拦截返回 502，那条 Socket 测试在此环境会 skip**，规则由 mock 版覆盖 | **仅自动**（真实云端探测**未验证**） |
| 进度看板契约 | `docs/progress/` | `tests/test_progress_board.py`（8 项：时间戳带时区、状态枚举、blocked 必须写原因、done 不得留未完成文件） | 浏览器打开：显示「最后更新 32 秒前」，无陈旧横幅 | **自动 + 实测** |

## 二、没有变化的能力（沿用上几轮结论）

| 能力 | 结论 | 缺什么 |
|---|---|---|
| 容器部署 | **未验证** | 本机无 `docker`；9 条验收命令见 `deploy-layer.md` §8 |
| 真实 STT / TTS 厂商端点 | **未验证** | 无凭据；只验证过拒绝与降级路径 |
| 真实云端 Model Provider | **未验证** | `config/providers.yaml` 是 `providers: []`。真实 MCP 服务端已接（见上表），它证明的是协议与进程，不证明任何模型厂商 |
| 真机 QQ（OneBot / 官方） | **未验证** | mock 适配器验证；限频与被动回复窗口未测 |

---

## 三、为什么「本地 fake provider」不能升级成「已验证云端」

本轮把流式链路从头到尾打通了，用的是 `tests/test_streaming_wiring.py` 里的假 provider：它不联网、不鉴权、不重试、不限流、不会 429、不会在第一个 token 之后断流（除非测试让它断）。

真实云端会。所以这条链路的结论是「本项目内部的编排是对的」，不是「接上 DeepSeek 就能用」。差别具体在于：HTTPS 握手与证书、鉴权失败的重试语义、供应商的 SSE 心跳与空闲超时、区域网络的可达性。这四件事一件都没被覆盖。

拿到主机与凭据后，最短的验证路径是：

```bash
# 1. 填 config/providers.yaml（base_url + api_key: env:XXX）
# 2. 问它通不通，不发密钥
python -m soapbot.cli doctor --probe
# 3. 起服务，发一条真的群消息，看 09 页的三段耗时
python -m soapbot.cli start
```

`--probe` 故意不发送 API Key：它打 `/models`，把 401/403 当成「活着」——一个拒绝你的服务器，是一个回答了的服务器。这样一份被转发的调试日志里不会出现凭据。

---

## 四、复现这套结论

```bash
# 全量测试（本机基线：1024 passed / 10 skipped；另有 1 条 opt-in 的真实 MCP 测试）
PYTHONPATH=src SOAPBOT_ENABLE_RUNTIME=false python -m pytest -q

# 静态门禁
python -m ruff check src tests scripts
python -m mypy src            # 基线 53，不得增加
cd webui && npm run typecheck && npm run build
python scripts/check_contrast.py
python scripts/check_deploy.py

# 部署姿态（含本轮新增的上游检查）
python -m soapbot.cli doctor
```

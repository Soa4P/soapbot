# 安全边界与错误日志：18 项防线契约

这份表不是设计文档，是验收清单。用户提出的 18 项风险逐条落在下面：每一项都要有
一条能被机器验证的防线，可能是运行时防护、负向回归测试，或 `scripts/check_security_boundaries.py`
里的静态断言。已解决的项不再写第二套实现，用负向断言锁住「不许退回去」。

判定列的三种取值：

- **已解决 / 不适用**：现状已经挡住，防线是防回退。
- **部分属实**：挡住了一部分，缺口补运行时防护。
- **属实**：确实没有，本轮补实现。

风险等级沿用复核时的分级，只用来排阅读顺序，不用来决定是否可以失败——门禁对
18 项一视同仁，缺一条就红。

## 18 项防线契约

| # | 项 | 判定 | 等级 | 现状证据 | 防线 | 验收用例 |
|---|---|---|---|---|---|---|
| 01 | 文件操作路径拼接用户输入 | 部分属实 | high | `plugins/installer.py:149-166` 拒 `..` 与绝对路径、`:198-221` 解压二次校验；`plugins/loader.py:89,540-550`；`api/admin.py:86` 的 `_DOC_ID_RE` 在 `:701-709`、`:715-723` 两处漏用 | 抽出 `_require_doc_id()` 供全部 doc_id 端点复用；门禁禁止 API 层 f-string 路径直接打开 | `tests/test_security_boundaries.py` 构造越界 id；`test_wave4_plugin_security.py:76` 保持 |
| 02 | `shell=True` / 命令拼接 | 已解决 | critical | `mcp/client.py:115-137` 列表传参；`plugins/isolation.py:503-511`；`src/soapbot` 全量 `shell=True` 零匹配 | 门禁禁止 `shell=True`、`os.system(`、`create_subprocess_shell`；插件 IPC 门禁继续锁 IPC 协议 | `tests/test_mcp_tool_poisoning.py`；门禁负向自检 |
| 03 | pickle / `yaml.load` 无 SafeLoader | 已解决 | critical | `plugins/loader.py:303-307` `yaml.safe_load`；`plugins/isolation.py:409-411` 只收 JSON-able；`scripts/check_plugin_ipc.py:121-133` 已禁 pickle | 门禁禁止 `import pickle`、`pickle.loads`、`yaml.load(`；要求 manifest 仍用 `safe_load` | `tests/test_wave4_plugin_security.py:115-128` 的 `!!python/object/apply` 载荷 |
| 04 | `v-html` 渲染 LLM/用户内容 | 不适用 | high | `webui/src/components/ProtocolEnd.vue:331-336` 唯一一处，绑定本地生成的 `qrSvg`；无 `innerHTML` | 门禁扫描全部 `*.vue`，只允许 `v-html="qrSvg"`；补 CSP 响应头作浏览器侧兜底 | `tests/test_security_boundaries.py` 注入一个假 `v-html` 绑定使门禁失败 |
| 05 | 认证 token 存 `localStorage` | 属实 | critical | `webui/src/api/client.ts:6-10,21,34-60`；`webui/src/stores/auth.ts:41,62-73`；全仓无 `Set-Cookie` | 改 `HttpOnly + SameSite + Secure`（按请求条件）Cookie；前端 `credentials: 'include'` + CSRF 头；门禁禁止 `localStorage` 与 Bearer 注入 | `tests/test_auth_cookie.py` 验标志位、登录、登出、撤销；云服务器实测登录/登出 |
| 06 | `allow_origins=["*"]` 且带凭证 | 不适用 | critical | `app.py:452-465` 白名单 + `allow_credentials=True`；`api/auth.py:122-143` Origin 校验 | 门禁禁止通配来源；保留显式白名单断言 | `tests/test_security_boundaries.py` 负向自检 |
| 07 | 日志注入（换行/控制字符） | 部分属实 | high | `logging_setup.py:69` 手工拼 JSON、`:24-33` 原文入 ring；`security/audit.py:36-45` 只脱敏密钥 | Formatter 改 `json.dumps` 序列化，出口统一 `_clean_text()` 剥离 C0/换行/引号；ring buffer 只存净化后字符串 | `tests/test_logging_hardening.py` 用 `\n\r\x1b"` 注入，断言单行合法 JSON |
| 08 | 正则处理用户输入无超时 | 部分属实 | medium | `security/injection.py:37-108,177-179,255-256,423-437` 量词有界但执行前无输入上限 | 新增单一 `bounded_scan()` 入口：先按 `max_regex_input_chars` 截断再匹配；门禁要求入口与配置项存在 | `tests/test_security_boundaries.py` 超长输入有界；门禁禁止嵌套无界量词 |
| 09 | Jinja 渲染用户内容 | 不适用 | high | `*.py` 中 `jinja2|Template(|from_string|format_map` 零匹配；`app.py:658-670` 为硬编码 HTML | 门禁禁止 `from jinja2` 与 `from_string(` | 门禁负向自检 |
| 10 | 上传文件未校验类型/大小 | 已解决（缺类型白名单） | medium | `app.py:80-87,467-532` 请求体限长；`api/plugins.py:107-132` 413；`plugins/installer.py:44-49,97-106,139-166,198-236` | 保留既有体积/条目/zip slip/解压炸弹校验，补 magic bytes 比对与条目后缀白名单 | `tests/test_plugin_installer.py` 增加伪装后缀与坏魔数用例 |
| 11 | 错误堆栈直接返回用户 | 部分属实 | high | 无 `debug=True`、无 traceback 进响应；但 `detail=str(exc)` 在 20+ 处回显原文 | 新增 `api/errors.py` 的 `AppError` 分层与 `STATUS_BY_KIND` 映射，全局 `exception_handler` 只回稳定 code 与短句；完整上下文进服务端结构化日志 | `tests/test_error_mapping.py` 断言响应不含异常原文、状态码正确、服务端日志带定位字段 |
| 12 | 敏感端点缺认证 | 部分属实 | critical | `api/` 77 路由均带认证，但 `api/auth.py:182-197` loopback 直接 `owner`，全仓仅 `:394-410` 判角色 | `require_role()` 依赖工厂按 OWNER/ADMIN/MEMBER 分级；loopback 只豁免只读，写操作一律要凭据；Origin + CSRF 双校验 | `tests/test_auth_cookie.py` 验 77 路由的角色声明、loopback 读写分离、跨站拒绝 |
| 13 | 裸 `except` / `except Exception: pass` | 部分属实 | medium | 真裸 `except:` 零处；`contextlib.suppress(Exception)` 约 20+ 处部分无说明 | AST 门禁禁止「整个 except 体只有 pass」；要求宽泛捕获带注释或日志；逐处补说明 | `tests/test_async_hygiene.py:171` 保持；门禁负向自检 |
| 14 | 日志记原始消息 / Provider 响应（PII） | 部分属实 | high | `providers/openai_compat.py:69` 等 `resp.text[:400]` → `providers/router.py:218-219` `last_error` → `api/admin.py:270` → ring buffer；用户消息正文全仓零匹配 | Provider 错误改类型化摘要 + `redact()` + 长度上限；`last_error` 不再含响应正文；用户消息继续不写日志 | `tests/test_logging_hardening.py` 断言响应正文不落 ring、不出现在日志流 |
| 15 | 无 `trace_id` 贯穿 | 部分属实 | medium | `core/message.py:161` 只覆盖 chat；`ContextVar` 零匹配；`logging_setup.py:28-32,69` 无结构化字段 | `core/log_context.py` 用 `ContextVar` 绑定 `request_id/trace_id/message_id/plugin/provider`；中间件回写 `X-Request-ID`；chat 侧 trace 桥接进 ContextVar | `tests/test_logging_hardening.py` 并发请求不串号；`test_pipeline_trace.py:202` 保持 |
| 16 | 异常类型无分层 | 部分属实 | medium | 35 个异常类有局部层次（`providers/base.py:42`、`budget/models.py:38-73`），但无统一映射表、无全局处理器 | `AppError` 分层 + 映射表接入既有异常类，不重写它们 | `tests/test_error_mapping.py` 覆盖配置、鉴权、上游、插件、限流、内部六类 |
| 17 | 启动时非 fail-fast | 部分属实 | medium | `app.py:18-21,137-141` 已拒绝；但 `:300-304` 曾跳过失败 adapter、`:594-596` startup errors 仅 debug、`cli.py:204-209` `doctor` 默认退出 0 | `strict_startup` **默认开启**：已启用的适配器构造失败就在启动阶段中止。面板专用部署可显式设 `false`；测试夹具同样显式关闭，避免把每个业务断言变成启动脚本 | `tests/test_error_mapping.py` 的严格模式用例与 `test_wave6_runtime.py:93,128` |
| 18 | 日志级别滥用 / 无慢调用日志 / 缺定位字段 | 部分属实 | low | `logging_setup.py:69` 仅 4 字段；`providers/router.py:186-207` 有 latency 但无阈值；`security/audit.py:60-71` 无 `message_id`/`provider` | `slow_call_ms` 阈值告警；成功 Provider 调用由 info 降为 debug；`AuditEvent` 增补定位字段；级别规则写入配置文档 | `tests/test_logging_hardening.py` 断言超阈值才 warning、字段齐全 |

接线不变量（不计入 18 项编号，缺失同样失败）：CI 的 backend 双矩阵与 `make check`
都要调用 `scripts/check_security_boundaries.py`，本文件必须存在，否则门禁会退化成
「一个没人调用的脚本」。

## 防线类型说明

- **运行时防护**：真的在请求路径上拦住输入或改变行为。只用在「部分属实」和「属实」项。
- **负向静态断言**：禁止某个原语重新出现。用在「已解决 / 不适用」项，避免重复实现。
- **负向回归测试**：构造攻击载荷，断言被拒绝。三类防线都要有，但已解决项可以只靠
  静态断言 + 既有测试。

## 不承诺的事

`bounded_scan()` 是输入长度上限加有界模式，不是硬超时：标准库 `re` 没有超时参数，
引入第三方 `regex` 会破坏 `check_deps.py` 的依赖一致性。超长输入被截断后不参与匹配，
残余风险是「恰好在上限内」的病态模式，已在模式层面用有界量词约束。

Cookie 会话不能防住已经在同一浏览器里执行的 XSS；它防的是凭据被脚本读走后长期复用。
同源策略、CSP 和输出净化仍各自负责自己的那段，任何一层都不替代另一层。

日志净化剥离控制字符、脱敏密钥、截断长度，不等于语义脱敏：用户主动写进消息里的
手机号仍可能出现在「消息长度」之外的字段里。用户消息正文继续不写日志，这条不变。

细节与验证结果见 [验证矩阵](verification-matrix.md)；认证行为的运维说明见
[安全模型](security-model.md) 与 [配置](configuration.md)。

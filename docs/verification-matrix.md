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
| 09 页流式面板 | `webui/src/views/PipelineView.vue`、`api/client.ts` | `tests/test_pipeline_trace.py`（35 项，含 API 层 `chunks`/`stream` 断言与文档环节数断言） | 浏览器三种形态：3 句、1 句、单条发送；中英双语各一次；12 页无横向溢出 | **自动 + 实测** |
| 面板内编辑 MCP（引擎） | `core/mcp_write.py` | `tests/test_mcp_write.py`（18 项：增删改、argv 强制、重复名、脱敏、陈旧哈希） | — | **仅自动**（引擎本身不直接面向用户） |
| 面板内编辑 MCP（API） | `api/config_write.py` | `tests/test_mcp_config_api.py`（14 项：权限、409/422、审计不留值、热重载） | 面板实际调用同一组端点完成写入 | **自动 + 实测** |
| 面板内编辑 MCP（界面） | `components/McpServers.vue`、`views/ConfigView.vue` | i18n 静态检查（键必须双目录存在、模板无残留中文） | 浏览器：新增 → `查看将要写入的改动` → 确认 → `mcp.yaml` 落盘。diff 显示 `GITHUB_TOKEN: redacted:be0b532d`，磁盘上写的是真值 | **自动 + 实测** |
| `McpManager.reload`（热生效） | `mcp/client.py` | `tests/test_mcp_write.py`（3 项：保留未变 client、改名才重启、空列表）、`test_mcp_wiring.py::test_the_first_server_added_shows_up_without_a_restart` | 带真服务的热生效：07 页写入后表格显示「已连接 · 14 个工具」，无需重启 | **自动 + 实测** |
| 真实 MCP 服务端（第三方 filesystem server） | `mcp/client.py`、`core/builder.py` | `tests/test_mcp_live.py`（opt-in：`SOAPBOT_LIVE_MCP=1`）、`test_mcp_wiring.py`（16 项） | 07 页写入 `npx -y @modelcontextprotocol/server-filesystem <dir>` → 热加载 → 14 个工具；`tools/call` 读回文件内容 | **自动 + 实测** |
| MCP 握手协商与失败区分 | `mcp/client.py` | `test_mcp_wiring.py`（服务端回旧版本时采纳其版本；握手期崩溃的错误带 stderr 与退出码） | 真实服务端返回 `2025-06-18`，客户端采纳而非假定自己的 | **自动 + 实测** |
| 三家 Provider 的报文映射 | `providers/anthropic.py`、`gemini.py`、`ollama.py` | `tests/test_providers_mapping.py`（7 项：system 提升、data URL 转换、token 字段名、`done` 终止、角色重命名、429→`ProviderError`） | — | **仅自动** |
| 可访问性静态规则 | `scripts/check_a11y.py` | 32 个组件 × 4 条规则（按钮名称、点击目标可聚焦、img 有 alt、对话框有语义） | 规则查出两处表格行只能鼠标点击，已补 `tabindex` 与 Enter/Space。**但这两行的键盘路径只由模板断言覆盖**：本机没有已配置的人格与会话，表格为空，浏览器里按不到那一行 | **仅自动**（键盘实测缺数据） |
| 测试断层扫描 | `scripts/check_test_gaps.py` | 孤儿模块基线（10 个）+ 文档数字与看板一致性 | 扫出 19 个无人引用的模块与 1 处过期数字；补测后逐步降为 10 | **自动 + 实测** |
| 容器部署 | `deploy/docker-compose.yml`、`deploy/Dockerfile` | `scripts/check_deploy.py`（静态，17 项：16 通过 + 1 告警） | 雨云 Ubuntu 24.04 真机：镜像 430 MB、`Up (healthy)`、`uid=10001`、只读根、`tini`、`doctor: PASS`、`down/up` 后 `/data` 数据不变、设置写入后 `/data/.env` 落盘且重启可读回。§8 九条全过，见 `deploy-layer.md` §8.1 | **自动 + 实测** |
| 上游连通性静态检查 | `security/posture.py` | `tests/test_posture.py`（7 项：空配置、缺文件、坏 YAML、本机端点、明文 http、远端、进报告） | `python -m soapbot.cli doctor` 实跑，输出 `[warn] provider.upstream (medium)` | **自动 + 实测** |
| `doctor --probe` 网络探测 | `security/posture.py`、`cli.py` | `test_posture.py`：401 ⇒ 可达、503 ⇒ 不可达（mock transport，规则本身）；另有本地回环服务端的 Socket 测试 | 只对本地回环跑过。**本机回环被拦截返回 502，那条 Socket 测试在此环境会 skip**，规则由 mock 版覆盖 | **仅自动**（真实云端探测**未验证**） |
| 进度看板契约 | `docs/progress/` | `tests/test_progress_board.py`（8 项：时间戳带时区、状态枚举、blocked 必须写原因、done 不得留未完成文件） | 浏览器打开：显示「最后更新 32 秒前」，无陈旧横幅 | **自动 + 实测** |
| 插件 IPC 请求关联与帧预算 | `plugins/supervisor.py`、`plugins/isolation.py` | `tests/test_plugin_ipc_hardening.py`（伪造/迟到结果丢弃、未绑定回调拒绝、父子帧上限一致、出站超限含实际字节）、`tests/test_worker_limits.py`（两个 `-I` 子脚本的 AST 名检查） | 本机实跑 `scripts/check_plugin_ipc.py`，逐条打印证据行并全部成立 | **自动 + 实测**（本机；生产容器内的帧洪水与真实崩溃仍按下方「未验证」处理） |
| 进程数上限与统一回收 | `config.py`、`core/builder.py`、`plugins/loader.py`、`app.py` | `tests/test_plugin_ipc_hardening.py`（容量 fail-closed、非法值拒绝、退出看护 reap 与代际守卫）、`tests/test_deploy_isolation.py`（熔断不随时间自动恢复） | — | **仅自动** |
| 离线审计门禁与只读巡检 | `scripts/check_plugin_ipc.py`、`scripts/plugin_worker_guard.py`、`deploy/plugin-worker-guard.{service,timer}` | `tests/test_plugin_ipc_hardening.py`（门禁对故意移除不变量会失败、巡检自检的解析断言）、`make ipc-audit`、`make guard` | 本机跑过门禁与 `--self-test`；生产上实跑 `--json`，输出 `warnings: []`、`restart_performed: false`、退出码 0 | **自动 + 实测** |
| 20 项安全与错误日志契约 | `scripts/check_security_boundaries.py`、`docs/security-boundaries.md` | `tests/test_security_boundaries.py`（门禁对故意移除不变量会失败、20 个编号都有检查）、CI 双矩阵与 `make boundary-audit` | 本机逐条打印证据行 | **仅自动** |
| Cookie 会话与角色分级 | `api/auth.py`、`webui/src/api/client.ts`、`webui/src/stores/auth.ts` | `tests/test_auth_cookie.py`（Cookie 标志、CSRF/Origin、角色门槛、回环读写分离、登录登出） | 本机 TestClient 覆盖；云服务器上的登录/登出见本轮发布验收 | **仅自动**（云服务器实测见发布记录） |
| 日志净化与统一错误层 | `logging_setup.py`、`core/log_context.py`、`api/errors.py`、`security/audit.py` | `tests/test_logging_hardening.py`（控制字符、ContextVar 不串请求、有界正则）、`tests/test_error_mapping.py`（状态码映射、响应不含异常原文） | 本机跑过；日志环与 `X-Request-ID` 由 TestClient 断言 | **仅自动** |
| 生态对照与落地抉择 | `docs/reference-ecosystem.md` | `scripts/check_doc_links.py`、`scripts/check_test_gaps.py --strict` | 5 类抽样，每条对照对应本仓库一处改动或不改的理由 | **仅自动**（文档） |
| 数据库迁移入口 | `cli_migrate.py`、`cli.py` | `tests/test_cli_migrate.py`（15 项：五态探测、`--status` 只读不建表、`--dry-run` 不写盘、legacy 盖章后顺序跑 v2–v5、失败后重新探测再措辞、损坏文件不被报成空库） | 本机对真实 `data/soapbot.db` 跑 `--status`，输出 `versioned · version 5`；对 0 字节文件跑，输出 `empty` 并提示先启动一次服务 | **自动 + 实测** |
| 文档承诺的命令必须存在 | `tests/test_cli_documented_commands.py` | 扫描 `README.md`、`docs/*.md`、`UPDATING.md` 里的 `soapbot <子命令>`，断言 `build_parser()` 接受它（9 项） | 该测试抓出的第一个缺陷就是 `migrate` 本身：`UPDATING.md` 让人跑它，而它不存在 | **自动 + 实测** |
| 第三方子进程环境净化 | `core/proc_env.py`、`mcp/client.py`、`plugins/isolation.py` | `tests/test_untrusted_child_env.py`（27 项：真实子进程读自己的 `os.environ`、MCP 与插件共用同一白名单、`prefix=""` 不等于通配）、`check_security_boundaries.py` 的 AST 规则禁止四种 `os.environ` 透传写法 | 本机起真实 MCP 子进程，其环境里只有 `SAFE_ENV_KEYS` 与显式声明的 `env`，无 `SOAPBOT_MASTER_KEY` | **自动 + 实测** |
| `make check` 与 CI 门禁一致 | `Makefile`、`.github/workflows/ci.yml` | `tests/test_gate_parity.py`（7 项：正向差集、反向多余门禁、例外仍然有效、反向用例证明断言非空、磁盘上的 `check_*.py` 都被接线、两项例外在 README 里被解释、边界门禁的 Makefile needle 仍命中） | 补进 `check-deps`、`console-encoding`、`deploy-check` 后本机逐条跑通，退出码均为 0 | **自动 + 实测** |
| `.env` 并发写不丢键 | `core/config_write.py` | `tests/test_env_concurrent_write.py`（8 项：24 线程同写、4 进程同写、外部进程持锁时不因初始化字节而失败、锁超时抛命名异常且遵守预算、`EnvLockError` 仍是 `OSError`、sidecar 不混入 `.env`、注释与未知键保留、四个 API 写入点都走加锁入口） | 本机 20 轮 × 4 进程 × 20 次写（1600 次）0 失败；修掉 Windows CI 的 `PermissionError [Errno 13]` | **自动 + 实测** |
| 出站目标预允许列表 | `plugins/sandbox.py` | `tests/test_url_allowlist.py`（6 项：公网未列入被拒、精确与子域规则、空列表 fail-closed、`None` 保持旧行为、allowlist 不能授权私网、客户端逐次转发且支持轮换） | 改错复验：去掉列表检查报 DID NOT RAISE，去掉参数转发报 `assert None == frozenset`；既有 URL 校验测试未受影响 | **自动** |
| 记忆检索的受众准入 | `memory/handoff.py`、`memory/stages.py` | `tests/test_memory_handoff.py`（8 项：解析不作授权、反单调受众收窄、日志/遥测拒绝、置信度下限、篡改结构重校验、残余不安全检索率、跨会话记录不进 prompt、置信度在检索边界生效） | 改错复验三处：去掉准入后跨会话事实进入 prompt，去掉数据-only 与反单调规则后对应断言失败 | **自动** |
| 撤销达到闭合终态 | `api/auth.py`、`security/tokens.py`、`webui/src/api/client.ts` | `tests/test_revocation_closure.py`（6 项：撤销后不签发会话、调用者自己的 token 立即失效、轮换后的引导凭据是唯一回程且只能用一次、会话 cookie 被清除、终态检查失败返回 500、无文件实例仅内存轮换） | 改错复验四处均返回 1：去掉清 cookie 报 `[]`、不轮换凭据时报 500、去掉终态检查报 `assert 200 == 500`、响应里加回 `access_token` 报断言失败；既有认证测试 74 项未受影响 | **自动** |
| 工具参数级信息流溯源 | `security/provenance.py`、`ai/stages.py`、`plugins/dispatch.py` | `tests/test_parameter_provenance.py`（10 项：宿主调用不标记、伪造标记重校验、数据-only 来源拒绝、模型资源参数需宿主校验、校验失败即拒绝、非字符串/空值不放行、`mark_vetted` 记录已验、operator 来源免逐次校验、模型阶段接线、注册表准入先于两条分发路径） | 改错复验三处均返回 1：去掉标记、去掉注册表准入、去掉数据-only 规则；既有工具/插件测试 115 项未受影响 | **自动** |
| 运行时证明记录 | `plugins/attestation.py`、`plugins/loader.py` | `tests/test_runtime_attestation.py`（8 项：三元组绑定、JSON 往返可移植、工件变更、策略漂移、记录篡改、执行未完成、签名边界显式、两条加载路径接线与重验入口） | 改错复验四处均返回 1：去掉任一重验规则或去掉隔离路径的证明产生；既有插件加载测试 214 项未受影响 | **自动** |
| MCP 实现版本 pin 与握手清理 | `mcp/client.py`、`mcp/config.py` | `tests/test_mcp_version_pin.py`（10 项：配置读取与裁剪、空 pin、超长报错、纯逻辑校验、匹配时记录身份、不匹配被拒且无残留子进程、缺 serverInfo 被拒、未 pin 仍记录、status 暴露供应链视图、改 pin 触发重连） | 改错复验四处均返回 1：去掉握手清理报出「残留活进程」、去掉 pin 校验报 DID NOT RAISE、去掉签名中的 pin、去掉配置解析；既有 MCP 测试 63 项未受影响 | **自动** |
| Windows 服务名与令牌策略 | `scripts/install.ps1`、`deploy/windows-bootstrap.ps1`、`desktop/src-tauri/src/main.rs`、`desktop/ui/index.html` | `tests/test_windows_service_contract.py`（7 项：两个安装器注册同名任务、都设开机启动、桌面壳与离线页同名、文档同名且无旧名、服务化脚本不打印令牌、前台脚本是显式豁免、解析器反向用例） | 改错复验四处均返回 1：任务名改回 `SoapbotPanel`、触发器改 `AtLogOn`、把 `cli token` 加回、文档写回 `soapbot-panel` | **自动** |
| 桌面 sidecar 可构建且自钉目录 | `desktop/sidecar/entry.py`、`desktop/sidecar/build.py`、`desktop/src-tauri/src/main.rs` | `tests/test_sidecar_build.py`（12 项：入口先钉四个目录再 import、双击默认 start、两条 `--add-data`、动态导入覆盖、onefile、缺前端时拒绝构建、缺 bundler 时给出安装提示、产物被忽略、真实壳通过受控 spawn 规则、裸 spawn 被拒、调用点归因到函数、产物 staging 到 Tauri） | 本机 Windows 实际打包 46.3 MiB 并 staging 进 `src-tauri/binaries/`；启动后 `/api/health` 200、`/` 200、数据目录出现 `init_token.txt` 与 `config/`；`cargo check --locked` 与 5 项 `cargo test` 通过；实测踩到 onefile 子进程孤儿、SQLAlchemy dialect、`bundle.resources` 在 `cargo check` 阶段就校验路径三个坑 | **自动 + 实测** |
| 依赖升级兼容性 | `pyproject.toml`、`requirements.txt` | 隔离 venv 安装远程 pin（pydantic 2.14.3、SQLAlchemy 2.1.8、uvicorn 0.54.0、numpy 2.5.4、pytest 9.2.0 等 16 项）后跑全量 | 当轮 `1941 → 1947 passed / 12 skipped`（隔离 venv 建好时 1941，本轮基线 1947），与旧 pin 的本机结果逐项一致；`pip install --dry-run` 先行确认无版本冲突；主 `.venv` 未改动 | **实测** |
| 管理端查询与线程边界 | `memory/store.py`、`api/admin.py`、`webui/vite.config.ts` | `tests/test_admin_query_efficiency.py`（4 项：一次查询返回分层计数、空库返回空映射、`memory_stats` 不再逐层查询、技能读写走 `to_thread`） | 改错复验三处均返回 1：把 `count_by_layer` 换回 `count_memories`、去掉两处 `to_thread`；面板构建实测 `vendor` 104.28 kB / `index` 143.69 kB | **自动 + 实测** |
| 类型检查只降不升 | `scripts/check_mypy_baseline.py`、`scripts/mypy_baseline.txt` | `tests/test_gate_parity.py`（7 项，保证 `make check` 与 CI 的 `backend` 跑同一套门禁） | 本地冷启动实测 79 个错误 / 31 文件、CI 80 / 32，基线取较大的 80；`types` job 已改为同一个阻断脚本，`backend` 也跑它 | **自动** |
| 破坏性操作统一确认 | `webui/src/views/MemoryView.vue`、`PluginsView.vue`、`scripts/check_a11y.py` | `tests/test_a11y_gates.py`（3 项：真实调用被报、注释不误报、仓库当前干净）+ `npm run typecheck` / `lint` / `check:i18n` / `build` | 5 处 `window.confirm` 全部改为 `ConfirmDialog`（记忆 / 文档 / 技能 / 撤销审批 / 删除插件）；请求中禁用、失败不关闭；构建实测 `vendor` 104.28 kB、`index` 143.67 kB | **自动 + 实测** |
| 首次登录令牌指引可操作 | `docs/deploy-quickstart.md`、`README.md`、`docs/guide.md`、`docs/deployment.md`、`docs/operations.md`、`scripts/install.ps1`、`deploy/windows-bootstrap.ps1`、`start-panel.bat` | `tests/test_bootstrap_token_docs.py`（10 项：主指引含状态自查、真实路径、读取命令、重启语义、恢复命令与自定义目录说明；四处文档都有指针；两个服务化脚本说清是哪台机器、给出可粘贴命令且不把值带进终端；逐条删掉任一要素都变红；旧含糊提示被拒） | 改错复验 8 处均触发断言失败；`check_doc_links.py` 79 链接 / 33 文件、`check_test_gaps.py --strict`、`check_console_encoding.py` 全绿 | **自动** |
| 类型检查门禁的当前态描述 | `docs/deployment.md`、`CONTRIBUTING.md`、`docs/verification-matrix.md`、`docs/operations.md`、`Makefile`、`.github/workflows/ci.yml` | `tests/test_type_gate_docs.py`（8 项：基线值取自 `mypy_baseline.txt`、四份文档不得残留过时短语且必须写出脚本名与当前基线、`make check` 含 `mypy-baseline`、CI 两个 job 都跑棘轮脚本；7 条参数化反向用例逐条改坏一处） | 改错复验 7 处均触发断言失败；`check_mypy_baseline.py` 实跑 `79, under the 80 baseline (31 files)`；全量 1884 → 1892 passed / 12 skipped | **自动** |
| 向量检索批量化与两阶段取数 | `memory/vectors.py`、`memory/store.py`、`memory/db.py` | `tests/test_vector_ranking.py`（10 项：以改动前逐行循环为 oracle 比对分数与顺序、并列保持扫描顺序、坏行与不相关行分开计数、非有限 query、limit 边界、两处接线静态断言、两阶段查询回取完整字段） | 3000 行 / 128 维 / limit=24 / 5 轮同库基准：median 39.7ms → 19.6ms（2.03x），top-24 逐项一致，日志噪音归零；既有向量/记忆/数据库测试 71 项全绿 | **自动 + 实测** |
| 数字门禁的轮次记录豁免 | `scripts/check_test_gaps.py`、`docs/verification-matrix.md` | `tests/test_gate_round_reports.py`（6 项：历史增量行豁免、当前态总数与跳过数失真仍报、裸旧数字与基准箭头不豁免、真实文档至少匹配一条轮次记录） | 端到端改错复验：把 `architecture.md` 当前态数字改错一位，`--strict` 返回 1 并指出 `docs/architecture.md:234`，字节级还原后 diff 为空；平时打印 1 条豁免行及行号 | **自动 + 实测** |
| AI 审查不再空转（预算与重试分类） | `scripts/ai_review.py` | `tests/test_ai_review.py`（24 项，新增 5 项：`[]`/`null`/`42` 等「能解析但不是对象」一律降级、`normalise` 直接收非 dict 也报错、`concerns` 是字符串时不再拆成单字符、非对象响应下 `comment.md` 与 `GITHUB_OUTPUT` 仍然写出、`review()` 抛意外异常时评论仍写出且带上异常类型） | 故障证据：PR #24、#25 的评论逐字相同（`finish_reason=length, reasoning_tokens=3000, completion_tokens=3000`）。另有一处自查翻出的缺陷：`_extract_json` 原样返回 `json.loads` 的结果，`"[]"`、`"\"safe\""`、`"null"` 都能解析成功，于是 `normalise` 的 `payload.get` 抛 `AttributeError` 逃出 `review()`（该函数 docstring 承诺不抛），`Ask the model` 步骤失败 → `Comment`/`Label` 被跳过 → PR 上只剩一个没有解释的红叉，而 `review` 是必需检查。用 `git show HEAD:scripts/ai_review.py` 喂同样输入复验：6 种非对象载荷全部 `RAISED AttributeError`、`concerns` 为字符串时产出 17 条单字符。修复证据：同一输入现在全部 `verdict=needs_review` 且 `summary` 含「JSON 对象」；`main()` 在同条件下返回 0 并写出两份文件 | **自动 + 实测** |
| AI 审查模式开关与工作流 / 模板门禁 | `.github/workflows/ai-review.yml`、`.github/pull_request_template.md`、`CONTRIBUTING.md` | `tests/test_ai_review_workflow.py`（16 项：checkout 钉 `base.sha`、无 `pip`/`npm` 安装、`AI_REVIEW_MODE` 被读取且 observe 为默认、Enforce 在 Comment/Label 之后且为最后一步、含 block 分支、未知模式值 fail-closed；另有 9 条参数化用例在真实 bash 里执行 `run:` 块，断言 8 种 mode/verdict/degraded 组合的退出码，以及失败时必然先打印 `mode=/verdict=/degraded=` 与 `::error::`）、`tests/test_pr_template.py`（12 项：九节齐全、逐节删除都报错、`--fill` 被禁、block 模式写进协作文档）、`tests/test_required_checks_doc.py`（9 项：必需检查名单与 `REQUIRED_CHECKS` 快照逐项一致、缺 `review` 与写回「5 个」都报错、快照本身必须含 6 项、`CHANGELOG` 被有意排除且这条排除仍会失败、**从真实文档的名单里逐个删掉任一项都必须报错**、`全绿` 句点名错 job 必须报错、跨换行折断的句子必须整句读取） | 两档真实运行都验过：① `observe`（run 42760564100）打印 `mode=observe verdict=safe degraded=false` 后 exit 0，job 绿；② `block` + 故意把 `AI_REVIEW_MODEL` 设成不存在的名字（run 42761052441）打印 `mode=block verdict=needs_review degraded=true`、`::error::AI review blocks this PR` 后 exit 1，job 红，**而 PR #27 上仍出现了评论**（写明 HTTP 400 与被支持的模型名）——证明「先评论、后判定」的顺序在真实失败下成立。两次实验后变量已复位为 `deepseek-flash` / `observe`。③ 分支保护：`review` 已通过 `PATCH /branches/master/protection/required_status_checks` 写入并回读——6 个 context（原 5 个 + `review`）齐全、`strict=true`，写入前后各读一次，确认没有顶掉任何既有检查。④ 名单门禁的现实触发：`review` 加入后回读全仓，`CONTRIBUTING.md`（`--admin` 段写 5 个）、`.github/copilot-instructions.md`（写 5 个）、`CHANGELOG.md`（写「五道」）三处仍停留在旧数量，本轮据此改对并为前两处加上门禁。⑤ 门禁自身的盲区（自查翻出）：初版是**全文子串**匹配。在上一轮合并的那一版（`git show HEAD~1:` 的旧门禁 + 旧文档）上删掉 `frontend`/`desktop`/`review` 三项仍报 `NO PROBLEM`，只有 `package` 被抓到——纯粹因为那版全文只出现一次；把 225 行改对、让那句也提到 `package` 之后，同一个旧门禁对 `package` 也失去反应（四个删除项全过），说明它的命中依赖与意图无关的巧合。第 225 行「`backend` 两个平台 + `frontend` + `types` + `desktop` 全绿」在旧规则下返回空列表（不含数量词，规则 1/2 看不到）。改为段落锚定 + 句子级「全绿」规则后，同一批探针 6/6 全部命中，第 225 行原句也被点名「漏了 `package`、`review`，多了不需要的 `types`」，改写后返回干净 | **自动 + 实测** |

## 二、没有变化的能力（沿用上几轮结论）

| 能力 | 结论 | 缺什么 |
|---|---|---|
| 真实 STT / TTS 厂商端点 | **未验证** | 无凭据；只验证过拒绝与降级路径 |
| 真实云端 Model Provider | **已验证（2026-10-30）** | `providers.yaml` 接 DeepSeek（`model: deepseek-flash`）；容器内真实调用返回「我是深度求索开发的AI助手。」；`doctor --probe` 报 `HTTP 401` 属预期（该探测**不发密钥**，只证明到达） |
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

同一套探测现在也在面板里：07 页每行一个「测试」按钮（`POST /api/config/providers/test`、`POST /api/config/adapters/test`），用表单里的草稿值、不写盘、Provider 侧不发密钥；需要 `MANAGE_CONFIG` 权限并限流到 30 次/分钟，避免管理面被当成内网端口扫描器。服务器上没有浏览器时，`soapbot setup` 走同一套「读 → 合并 → 校验 → 原子写」，校验不过绝不落盘。

---

## 四、复现这套结论

```bash
# 全量测试（本机基线：1955 passed / 12 skipped；另有 1 条 opt-in 的真实 MCP 测试）
PYTHONPATH=src SOAPBOT_ENABLE_RUNTIME=false python -m pytest -q

# 静态门禁
python -m ruff check src tests scripts
python scripts/check_mypy_baseline.py   # 基线 80，只降不升（阻断）
cd webui && npm run typecheck && npm run build
python scripts/check_contrast.py
python scripts/check_deploy.py

# 部署侧复验（需要一台已部署的主机）
python scripts/deploy_remote.py --host <IP> --port 443 --key <私钥> --verify   # §8 十四项
python scripts/deploy_remote.py --host <IP> --port 443 --key <私钥> --backup   # 数据卷快照

# 部署姿态（含本轮新增的上游检查）
python -m soapbot.cli doctor
```

### AI 审查的端到端复验

这条只能在合并后验：工作流 checkout `base.sha`，所以改脚本的那个 PR 跑的还是旧脚本。
复验步骤是「开下一个 PR → 读它自己的 `ai-review` 评论」：

```bash
gh pr view <N> --json comments --jq '.comments[-1].body'   # 必须是真实结论，不是「返回空内容」
gh run view <run-id> --log | Select-String "mode=|verdict="  # Enforce review mode 的实际判定
```

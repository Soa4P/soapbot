# 变更记录

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

本项目的特殊情况：0.1.0 之前的开发没有逐版本留档，因此下面把「能运行但不构成
交付物」的中间状态合并记为 `0.1.0`，并把本轮修复逐条列出。每一条都写明**原来的
错误表现**，而不是只写「修复了 X」——因为这里的缺陷几乎全部是「组件都在、线没接」，
只写结论会让人以为是从零实现，下次仍会以同样的方式漏掉。

## [Unreleased]

### 新增

- **真实 MCP 服务端接上了**（`tests/test_mcp_live.py`，opt-in：`SOAPBOT_LIVE_MCP=1`）。
  之前所有 MCP 结论都来自一个照着客户端写的假服务端，它能证明的只有「客户端和自己谈得拢」。
  现在接的是第三方的 `@modelcontextprotocol/server-filesystem`：14 个工具、`tools/call`
  真的读回了文件内容。默认不进 CI——它要联网装 npm 包，一个会因为 npm 打嗝变红的门禁，
  最后会被人标成 flaky，而 flaky 的门禁比窄门禁更糟。
- **MCP 首次配置不再需要重启**。这条是实测查出来的：我按「面板新增 → 热加载」的路径走，
  表格一直显示「状态未知（运行时未启动）」——而运行时明明在跑。原因是
  `core/builder.py` 只在 `mcp.yaml` 已有服务器时才创建 `McpManager`，于是**最该热加载的
  那一次**（从零到一台）恰好没有任何东西可加载，面板只能回一句「重启后生效」。现在管理器
  总是创建，空列表只是它的初始状态。
- **MCP 握手改为版本协商**。客户端原来硬编码 `2024-11-05` 并把 `initialize` 的结果丢掉。
  现在发自己最新的版本、采纳服务端回的版本（实测对方回 `2025-06-18`），遇到没见过的版本
  按 INFO/WARN 记录而不是拒绝——三个调用在已发布的各版本里报文没变过，为一个不认识的
  字符串把一台能用的服务器停掉是更差的交易。
- **握手失败与启动失败不再长得一样**。以前子进程 `stderr=DEVNULL`，npx 下载 404 和协议谈崩
  都只表现为「connection closed」。现在保留 stderr 尾部 2 KB，握手期崩溃会写成
  `exited during the handshake (exit code 9); stderr: npm error 404 ...`。
- **三家 Provider 的报文映射补测**（`tests/test_providers_mapping.py`）。Anthropic、Gemini、
  Ollama 此前**没有任何测试提到过**——它们是三个把我们的结构翻译成别人 schema 的地方，
  而写错字段名不会抛异常，只会安静地少一半信息。
- **两个新的静态门禁**：`scripts/check_test_gaps.py`（孤儿模块 + 文档数字与看板一致性，
  带 `scripts/test_gaps_baseline.txt` 基线）与 `scripts/check_a11y.py`（按钮名称、点击目标
  可聚焦、img alt、对话框语义）。都挂进 `make check` 与 CI 既有作业，不新增作业。
- **09 页流式观察**。`trace.chunks` 与 `trace.stream` 从第一天就写进了环形缓冲，前端
  一个字段都没读——「有数据」和「看得见」之间隔着一次渲染。现在详情区有三段耗时阶梯
  （首 token / 首句送达 / 整条回复，共用同一刻度，所以「首句比整条短多少」是几何可见的）、
  实际发出的分句序列、中断与额度截断角标。
  **顺手修掉一个谎**：`MessageTrace` 在 TypeScript 里声明了 `extras`，而 `to_dict` 从不
  序列化它。第一版用 `extras.send_ok` 判断「回发环节是否跑过」，页面永远渲染不出区块——
  改成读 `stages`，并把这个字段从类型里删掉。
- **面板内编辑 MCP 服务器**（`/api/config/mcp` 的 read / diff / apply）。
  以前只能看状态和重连，增删要 SSH 上去改 `config/mcp.yaml`。三个决定值得记：
  ① **OWNER 权限**，高于 providers 的 ADMIN——新增一台服务器等于开放一条子进程执行通道，
  并把它的工具交给模型调用，与改一个 base_url 不是一个量级；
  ② **`env` 只写不读**，接口只回键名，提交时不带 `env` 就保留磁盘原值——`providers.yaml`
  里那个「把 `***` 存回真实密钥」的坑在这里由结构排除，而不是靠记得检查掩码；
  ③ **diff 用指纹而不是 `***`**：扁平占位符会让「换了 token」渲染成「没有改动」，操作者
  会对着一张空 diff 点确认。改用带进程内盐的 `redacted:xxxxxxxx`，变了看得见，值读不出来。
  写入后热重载（`McpManager.reload` 原地更新，不换对象——工具注册表持有的是这个实例），
  并逐个 server 报告「N 个工具」或「启动失败·原因」。
- **上游连通性自检**（`provider.upstream`）与 `doctor --probe`。
  `providers: []` 以前不产生任何 finding，`doctor` 对着一个答不出任何消息的机器人打印
  PASS。现在空配置是 `[warn]`（MEDIUM，不拉红门禁——只跑面板的机器是合法部署），
  坏 YAML 是 `[fail]`，指向本机或明文 http 会单独点名。
  `--probe` 是可选网络探测，**不发 API Key**：打 `/models`，把 401/403 当作「服务器回答了」。
- **验证矩阵** `docs/verification-matrix.md`：把「有实现 / 有测试 / 真能用」分开写，
  结论只有「自动+实测 / 仅自动 / 未验证」三种，并写明容器、真实 STT、真实云端 Provider
  各自的缺口。
- **看板契约测试** `tests/test_progress_board.py`。`docs/progress/README.md` 里写了四条
  规则（状态枚举、blocked 必须写原因、current 指向真实任务、updated_at 决定可信度），
  此前没有一条被执行——看板因此停在 10-28、`current` 还写着「首次提交待确认 git 身份」。
  规则文件只有人读就会腐烂，这 8 条断言是让它不腐烂的部分。

- 为了上面这条，两处既有代码被拆开而不是复制：
  `core/config_write.build_patch` 原来把 providers 的合并与脱敏规则写死，现在注入
  `apply_fn` / `validate_fn` / `diff_render` / `filename`，默认值保持 providers 行为，既有
  调用点零改动；`mcp/config.py` 把校验从 `load_config` 拆成 `parse_servers`，让面板校验
  候选文档与启动解析是**同一份代码**——两份解析器迟早会分叉，分叉的样子就是「面板保存
  成功、进程起不来」。
- **配置写入 API**（`POST /api/config/providers/{diff,apply}` + `GET /api/config/providers`）。
  三步而非一个 PUT：读取（密钥脱敏 + `base_hash`）→ diff（用**与启动同一套解析器**
  校验候选文档，**不写盘**）→ apply（校验 `base_hash` 未变、`approved_hash` 与确认内容
  一致，再原子写）。
  **这推翻了 `docs/architecture.md §6` 原来的「配置类写入一律不做 API」**：那条规则的
  前提是「文件在版本管理里、改动可被评审」，而单机部署里文件从未进过 git，评审从未
  发生。diff 才是第一次真正生效的评审面。原条目已标注修订并补 §6.1 说明理由。
  三条硬约束各有测试：字段级合并（不整文件覆盖）、候选必须通过启动解析器、不热重载。
- **09 流水线追踪页** + **10 运行指标页**（追加编号，不重排 01–08）。
  追踪数据此前不存在：`ctx.timings` 每条消息算完即丢。新增 `core/trace.py`
  有界环形缓冲（500 条，重启即失，不采样），通过已有的
  `Pipeline.observe` 与 `message.processed` 订阅接入，未改 `Pipeline` 内部。
  指标序列 5 秒一点、保留 720 点（约 1 小时）。
- **手写 SVG 图表组件** `components/charts/{LineChart,BarChart,Sparkline}.vue`。
  不引图表库：依赖清单是审计面（刚移除 4 个未用包），且 canvas 对读屏是不透明位图，
  做 WCAG AA 需再叠一层 DOM。每个图都带可展开的数据表。
- **`components/StageGraph.vue`**：纵向链路 + 逐环节耗时条 + 「在此中止」标记，
  以及**换序沙箱**——可拖拽试排，页面指出破坏了哪条具体约束，但不写回任何地方。
- **07 页 Provider 可视化编辑**：表格内增改、只发被编辑的行、改动行高亮、
  diff 预览 → 二次确认 → 写入，「需重启生效」常驻横幅。
- **`components/DiffEditor.vue`**：行级 diff，带新旧行号与 `+`/`−` 标记，
  不只靠颜色区分增删。

### 修复

- **MCP 子进程关闭时打印 `Exception ignored in BaseSubprocessTransport.__del__`**。
  `close()` 只 terminate + wait，没有收掉管道，于是传输对象被回收时 CPython 打一段
  traceback——部署日志里看起来像崩溃，其实是正常关机。
- **两张表格的行只能鼠标点**。人格表与会话表的 `<tr @click>` 没有 `tabindex`，键盘用户
  根本到不了，且按 Enter 什么也不会发生。补上焦点与 Enter/Space；`@click.self` 的遮罩层
  是例外，它不该成为 tab 停靠点（Esc 已经负责关闭）。
- **`Pipeline.observe` 的回调是 async 的**。首版传入同步函数，`await None` 抛错被
  pipeline 当作 observer 错误吞掉，导致所有耗时静默丢失、端点仍返回 200 空列表。
  现由 `_observe_stage` 适配，并有测试断言它是协程函数。
- **流水线崩溃的消息不留痕迹**。`_on_event` 的 except 分支直接 return，既不发布也不
  计数，`failed` 永远为 0。现在记录一条 `halt_reason=pipeline_error` 的 trace。
- **`file_hash` 与 `build_patch` 用了不同的哈希口径**：前者对原始文本、后者对规范化
  后渲染的内容，导致读取端点发出的 `base_hash` 永远无法通过写入校验。现统一走
  `render`。
- **只读文件无法被 `os.replace` 覆盖**（Windows WinError 5）。现在写入期间临时解除
  只读位、写后恢复，文件最终仍是只读。
- **`STAGE_ORDER` 与 `build_pipeline` 不一致**：插件环节实际名为
  `plugin_message_hooks`。漂移测试立刻抓到了它。


- **开发进度看板** `docs/progress/`：`index.html` + `board.css` + `board.js` +
  `progress.json` + `README.md`。零依赖、零构建、无 CDN、无 webfont，
  用 `make progress` 起静态服务查看（`file://` 下 fetch 会被 CORS 拦截）。
  百分比由文件清单复算（子任务权重 = 文件数，完成比 = 已完成/总数），
  **没有手工填写入口**——手填的百分比没有可信度。
  防「看板撒谎」三项：`updated_at` 超 10 分钟标黄、fetch 失败显式报错且保留上次
  渲染结果、只陈述四态（未启动/进行中/已完成/受阻）。
- **`scripts/check_contrast.py`**：解析 `base.css` 与 `board.css` 的 `:root` token，
  按 WCAG 相对亮度公式断言对比度，并检查 `:root` 之外无硬编码颜色。
  已接入 `make check`（`check: lint contrast test`）与
  `tests/test_a11y_tokens.py`（5 项）。
- **`webui/src/lib/useFocusTrap.ts`**：焦点陷阱 + Esc + 关闭后归还焦点。
  抽出而非各写一遍，因为登录框与确认框都需要且都不能做错。
- **`webui/src/components/ConfirmDialog.vue`**：`role="alertdialog"` + `aria-modal`，
  用 `tone` 与 `irreversible` 区分「可逆」与「不可逆」的措辞——
  统一的「确定吗？」会训练人闭眼点过。

### 变更

- **控制台整体改为浅色企业风**。8 个既有视图全部换肤。
  原因：这套面板实际是在客服通话中、笔记本上、和聊天窗口并排打开的，
  白底与其他窗口读作同一份文档，黑底读作另一个应用。
  保留的部分：衬线标题（运维工具里罕见，是主要识别度）、等宽数据列、
  01–08 编号导航（稳定标识符，重排会让过去沟通里的「05 页」失去指向）。
- **状态色全部重新取值**。深色主题的 `#5ec98a` 在白底上只有 1.9:1，
  不满足 AA。现值是 700 档（`--ok: #047857` 等），并新增 `--ok-soft` 等浅底配对。
- **控件边界从 `#cbd5e4` 改为 `#7c8aa3`**：前者在白底上 1.48:1，
  远低于 WCAG 对表单控件边界要求的 3:1；后者 3.49:1。
  这个值是校验脚本算出来的，不是目测调的。
- **散落的硬编码颜色收进 token**（`--ok-line` / `--warn-line` / `--danger-line` /
  `--brand-line` / `--on-brand`）。此前有 16 处绕过 token 直接写色值，
  其中 4 处引用了换肤后已不存在的变量（`var(--lamp)` / `var(--paper)` /
  `var(--ink-900)` / `var(--ink-600)`），会静默失效。
- **表格语义**：81 个 `<th>` 补 `scope="col"`；有 `<thead>` 的表加
  `.visually-hidden` 的 `<caption>`（面板标题已在屏幕上说明同一件事，
  重复显示只是噪音，但无名称的表会被读屏播报成「表格」）；
  键值表（配置文件、累计计数、策略）的首列改为 `<th scope="row">`，
  加 caption 解决不了这类表的实际问题——读屏无法判断哪个值属于哪个标签。

## [0.1.0] - 2026-10-28

首个可 clone、可构建、可部署的版本。

### 新增

- `LICENSE`（MIT）、`.env.example`、`CHANGELOG.md`、`Makefile`、
  `.github/workflows/ci.yml`、`scripts/check_deps.py`。
  此前仓库声明 MIT 但没有许可证文件，且没有任何自动化检查。
- 示例插件移入包内 `src/soapbot/examples/plugins/`（`admin` / `echo` / `help` /
  `remind`），通过 `soapbot.examples.bundled_plugins_dir()` 访问。
  此前它们在 `data/plugins/`，而 `data/` 被 `.gitignore` 排除：全新克隆没有任何
  插件，五个测试模块直接 `FileNotFoundError`。
- 插件批准状态持久化到 `data/plugin-approvals.json`
  （`soapbot.plugins.approvals.ApprovalStore`），并在启动时自动加载已批准的插件。
- 插件工具调用全链路：`AIRequest.tools` / `tool_note`、`ModelStage` 有界工具循环、
  隔离模式下的 `register_proxied_tool`。
- notice 链路：`OneBot11Adapter._to_notice`、`Adapter.emit` 放行 `NOTICE`、
  `BotRuntime._on_notice`。
- 群管命令 `/mute` `/unmute` `/kick` `/recall-msg`，以及
  `Permission.MODERATE_GROUP`。
- 适配器群管动作契约：`recall` / `set_group_ban` / `set_group_kick` /
  `get_group_list`，OneBot 端完整实现。
- 知识库写入 API：`POST /api/knowledge`、`DELETE /api/knowledge/{doc_id}`、
  `GET /api/knowledge/{doc_id}`，以及 `KnowledgeBase.ingest_document`（覆盖语义）。
- 管理面板新增「模型与人格」(07)、「运行日志」(08) 两页；记忆页补齐知识库上传与删除；
  插件页补齐「撤销批准」「删除」。
- `MemoryStore.find_message`：按会话 + 平台消息 ID 查询，供撤回命令做归属校验。

### 修复

- **QQ 官方适配器在群里完全不应答**。`_strip_at_prefix` 把 `<@bot>` 抹掉后不产生
  AT 段，而 `WakePolicy` 在群里先找 AT 段、再找唤醒词，两者都没有 → 所有正确
  @机器人 的消息被静默丢弃。现改为 `split_leading_at` 返回 `(mentioned, body)`，
  调用方据此补一个 AT 段。OneBot 端不受影响，因为它原生携带 AT 段——这正是缺陷
  长期不可见的原因：两个适配器对「谁来判断是否被呼叫」没有共识。
- **私聊在任何配置下都不可用**。`build_runtime` 接收 `allow_unknown_private` 却从未
  使用，`AccessPolicy()` 无参构造，因此 `SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true` 无效。
  新增 `build_access_policy()`，并把 `private_allowlist` / `group_allowlist` /
  `group_blacklist` / `user_blacklist` 一并接入配置。
- **插件批准在重启后全部丢失**。`_approved` 是纯内存字典，导致：重启后没有插件在跑、
  WebUI 显示「已启用」却加载失败、无头部署根本无法授权。
- **模型永远看不到插件工具**。`PluginToolRegistry.available_for` 零调用方，
  `AIRequest` 无 `tools` 字段，Provider 层虽已支持 `tools` 却收不到。
- **隔离模式下工具被注册成了命令**。worker 用同一帧上报命令与工具，宿主把两者都按
  命令注册，于是工具变成 `/tool-name` 斜杠命令，模型反而看不到。
- **`on_notice` 永远收不到通知**。三处同时断开：OneBot 丢弃 `post_type != "message"`、
  `Adapter.emit` 对非 MESSAGE 直接 return、`PluginManager.on_notice` 无调用方。
- **群管能力只有声明没有实现**。OneBot 声明了 `RECALL`/`MUTE`/`KICK`/`GROUP_LIST`，
  四个方法一个都没有。
- **知识库只读**。`add_document` 等写入路径实现完整且被检索侧消费，但服务内没有任何
  调用方，知识库页面只能是空的。
- **`list[str]` 配置项用逗号分隔会导致启动失败**。pydantic-settings 对复杂类型先做
  `json.loads`，`SOAPBOT_OWNER_IDS=123,456` 抛 `SettingsError` 且不说明正确写法——
  而文档写的正是逗号分隔。现支持 `a,b` / `a;b` / `["a","b"]` 三种。
- **声明了四个从未使用的依赖**：`structlog`、`watchdog`、`python-multipart`、
  `edge-tts`。依赖清单会扩大审计面，并让评审者以为项目具备实际不存在的功能。

### 变更

- 插件启动行为从「只发现、永不加载」改为「发现 + 加载已批准项」。区别在于选择来源：
  前者不会执行任何东西，后者执行的是**曾经由人做出的持久决定**。未获批准的目录仍然
  被 `load()` 拒绝，这条规则没有放宽。
- `/recall` 保持「检索记忆」语义，撤回消息命名为 `/recall-msg`。复用 `/recall` 会让
  既有部署的命令静默变成另一种行为。

### 已知限制

见 `docs/delivery-readiness-assessment.md` 与 `docs/wave6-10-runtime-auth-webui.md`。
简要列出：

- 插件之间不互相调用（设计如此：插件 A 不能借插件 B 提权），也没有插件市场。
- 无 MCP、无 STT/TTS、无流式输出、无 i18n。
- QQ 官方适配器的群管能力未实现（平台侧限制）。
- 额度审批、B 站浏览默认关闭，需显式开启。
- 清单摘要漂移只报告不阻断（在 `GET /api/plugins` 的 `approval.manifest_changed` 里）。

[Unreleased]: https://example.invalid/soapbot/compare/0.1.0...HEAD
[0.1.0]: https://example.invalid/soapbot/releases/tag/0.1.0

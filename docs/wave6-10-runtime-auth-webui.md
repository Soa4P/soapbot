# Wave 6–10：运行时接线、鉴权、B 站、只读 API、管理面板

本文是本轮的交付记录，也承担上一轮遗留的"未完成 wave 清单"。每一项都给出
**预期行为**、**验收标准**、**状态** 与 **可复核的证据**，避免"看起来实现了"。

验证基线：`691 passed, 3 skipped`（本轮开始时 590 passed / 3 skipped），
`ruff check src/ tests/` 全绿，`vue-tsc --noEmit` 通过，`vite build` 通过。

> 注：该数字是本 wave 结束时的快照。0.1.0 交付整理新增 27 项接线回归测试
> （`tests/test_delivery_wiring.py`），当前为 `718 passed, 3 skipped`。
> 本文件其余内容作为该轮的历史记录保留，不随之后的改动修订。

---

## 1. 总览

| # | 能力 | 状态 |
|---|---|---|
| 1 | 启动即运行（BotRuntime + 适配器装配） | ✅ 完成 |
| 2 | 定时任务（插件 cron + 额度过期清扫） | ✅ 完成（含一个真实缺陷修复） |
| 3 | 管理 API 鉴权（引导令牌 → JWT） | ✅ 完成 |
| 4 | B 站浏览 L1 + L2（wbi 签名） | ✅ 完成 |
| 5 | 只读管理视图 | ✅ 完成 |
| 6 | Vue3 管理面板 | ✅ 完成 |
| 7 | `render_pending_notice` 接入 | ✅ 完成 |
| 8 | 容器镜像的配置目录 | ✅ 完成（原缺失，会导致容器内无适配器） |

---

## 2. 逐项：预期行为与验收标准

### #1 启动即运行

**修复前的实际状态**：`app.py` 的 lifespan 只做了 `setup_logging` → `ensure_dirs` →
`build_plugin_manager` → `discover`。全仓库没有一处 `build_runtime` 出现在 `src/` 里，
`BotRuntime` 只被测试构造。`soapbot start` 起的是一个只有 HTTP 路由、**收不到任何 QQ 事件**
的进程，而 `/api/health` 一直返回 `ok`。

**预期行为**
- 启动时按 `config/providers.yaml` 构建 Provider 链；有 Provider 才启用模型阶段。
- 按 `config/adapters.yaml` 构造适配器并注册到 runtime；`runtime.start()` 逐个连接。
- 关闭时反序释放：调度器 → B 站 HTTP 池 → 适配器 → 插件 → 数据库。

**验收标准**
- 配置里写一个适配器，启动后 `runtime.adapters` 包含它且 `started is True`；关闭后
  `stopped is True`。
- 单个适配器构造失败时：服务仍启动，`GET /api/runtime` 的 `startup_errors` 有该错误，
  `adapter_count` 不含它。
- 未配置任何适配器时：`/api/health` 仍 `ok`，`/api/runtime` 明确显示 0 个适配器。
- 无 Provider 时模型阶段禁用，并在启动日志中说明。

**证据**：`src/soapbot/app.py`（`_start_runtime` / `_attach_adapters` / `_shutdown`）、
`tests/test_wave6_runtime.py`（`test_lifespan_builds_runtime_and_starts_configured_adapter`、
`test_broken_adapter_is_reported_but_service_stays_up`、`test_health_stays_green_with_no_adapters`）。

**设计取舍**
- **默认不连接任何适配器**。`adapters.yaml` 出厂为空。启用一个指向不存在的 NapCat 的默认
  适配器，会让首次启动变成一串重连日志，把真正要看的信息淹掉。代价是必须显式配置——
  这一点写进了 README 的快速开始。
- **配置文件本身不可解析 → 启动失败**；**单个适配器构造失败 → 跳过并上报**。
  前者无法"部分理解"，后者是可解释的有界损失，且管理面板正是用来修它的。

---

### #2 定时任务

**修复前的实际状态**：`apscheduler` 在依赖里但 `src/` 内零引用。
`PluginCronRunner.run_due()` 的注释写着"由 app 里的 APScheduler 调度"，
`BudgetStore.sweep_expired()` 的注释写着"后台 tick 会调用"——两个都不存在。

**顺带发现并修复的真实缺陷**：原 `run_due()` 遍历所有 job 后**无条件执行**，完全忽略
`expr` 与 `now`。若按 30 秒 tick 接上调度，一个 `0 9 * * *` 的任务会执行 2880 次/天。
这不是"没接调度"的副作用，而是接上之后立刻会炸的正确性问题。

**预期行为**
- 单个 tick 同时驱动：插件 cron、额度过期清扫。
- cron 用配置时区（`SOAPBOT_DEFAULT_TIMEZONE`）解释，不随容器 `TZ` 漂移。
- 任务首次被看到时**只排期、不执行**；错过的时间窗跳过而不是补跑。
- 一个单元失败不影响另一个（cron 抛异常不能让额度永远锁死）。

**验收标准**
- `*/5 * * * *` 的任务在首次 `run_due` 返回 0、在 +5 分钟后返回 1、同一窗口内再次调用返回 0。
- `0 9 * * *` 的任务在连续 20 次 tick（10 分钟）内执行 0 次。
- cron 抛异常时 budget sweep 仍然执行，且 `scheduler.last_error` 记录原因。
- 插件卸载后其排期被清除。

**证据**：`src/soapbot/core/scheduler.py`、`plugins/dispatch.py::PluginCronRunner`、
`tests/test_wave6_runtime.py`（`test_cron_runner_survives_a_tick_interval_longer_than_the_expression`、
`test_scheduler_tick_isolates_failures`）、`tests/test_wave4_plugin_review.py`（更新后的两个 cron 用例）。

**为什么用"一个 tick"而不是"每个插件任务一个 scheduler job"**：插件在运行时可加载/卸载，
逐任务注册会在生命周期事件里不断增删 job，并存在"半个 job 已注册"的窗口。单一 tick 以
"当前已加载插件"为唯一真相来源，不会与调度器状态漂移。

---

### #3 管理 API 鉴权

**修复前的实际状态**：`jwt_secret` / `jwt_ttl_hours` / `init_token` 三个配置项零引用，
`pyjwt` 装了但没人用。唯一防线是 `_require_loopback`（客户端 IP 属于 loopback 集合）——
这不是边界：反向代理会让远端请求真的来自 loopback，且 `SOAPBOT_HOST=0.0.0.0` 只是一次配置编辑。

**预期行为**
- 首次启动生成一次性引导令牌，写入 `data/init_token.txt`（0600），并记一条日志指向它。
- `POST /api/auth/login` 用引导令牌换 JWT；引导令牌**只能用一次**，用完即失效。
- 非本机来源、无令牌 → 401（带 `WWW-Authenticate: Bearer`）。
- 本机来源可免令牌；但状态变更请求若带跨站 `Origin` → 403。
- 令牌校验覆盖签名、`exp`、`aud`、`iss` 与必需声明。

**验收标准**
- 登录返回 `access_token`，用它访问 `/api/runtime` 等接口返回 200。
- 同一引导令牌第二次登录返回 401。
- 伪造 / 过期 / 无 `exp` / 别的 audience 的令牌全部 401。
- `SOAPBOT_JWT_SECRET` 少于 32 字节时启动失败（短 HMAC 密钥可被离线爆破）。
- 连错 5 次后第 6 次登录返回 429。
- `/api/auth/status` 只报告"是否还能登录"，绝不回显令牌本身。

**证据**：`security/tokens.py`、`api/auth.py`、`tests/test_wave7_auth.py`（27 个用例）。
真实服务端到端复核：引导令牌登录 → 10 个只读接口全部 200 → 伪造令牌 401 → 重放引导令牌 401。

**已知限制（明确记录，不假装解决）**
- JWT 是无状态的，**没有吊销列表**。撤销 = 删除 `data/jwt.key` 并重启（所有令牌失效）。
  单操作者场景下这够了；多操作者需要引入服务端会话表。
- 引导令牌"一次性"的语义是**进程内**的：重启会重新生成。这是刻意的——把文件留成永久
  凭证更糟。

---

### #4 B 站浏览（L1 + L2）

**修复前的实际状态**：`src/soapbot/bilibili/` 只有一行 docstring，README 却写着
"B 站自主浏览与观后感"。

**预期行为**
- `l1`：仅免签名公开接口（视频详情、热门评论）。
- `l2`：额外做 wbi 签名，可访问需要签名的公开列表/搜索接口。仍然**不带 Cookie、不登录**。
- `l3`：**拒绝**，不静默降级为 l2。
- 用户输入只能是 BV/av/视频链接/`b23.tv` 短链；短链通过读取 `Location` 头解析并校验目标
  主机，不跟随跳转。
- 观后感明确标注"基于公开信息推断，并非真正观看"；无模型时降级为信息整理并说明。

**验收标准**
- wbi `mixin_key` 对固定向量匹配；`sign` 的 `w_rid` 可用独立实现复算一致。
- l1 下调 `user_videos()` 在网络请求**之前**抛 `BilibiliTierError`。
- `-404` → 不存在；`-412`/`403` → 风控；`-403` 类 → 限频。错误信息可直接发给用户。
- 短链指向非 B 站域名 → 拒绝；无 `Location` → 拒绝；非 `b23.tv` 主机 → 拒绝。
- 每分钟上限触发时抛错而不是静默排队。
- 评论接口失败不影响视频信息返回。
- 提示词中平台文本被"不可信数据"边界包裹（复用 `security.injection`）。

**证据**：`bilibili/{wbi,client,watcher,commands,models}.py`、`tests/test_wave8_bilibili.py`（38 个用例）、
`api/bilibili.py`。

**为什么不做 UA 轮换**：指纹随机化的用途是规避平台的检测。README 的免责声明写的是
"默认 L1 静默模式"，如果同时轮换指纹，这句话就是假的。因此使用固定、可识别的 UA，
并在客户端模块顶部写明了理由。

---

### #5 只读管理视图

**预期行为**：`/api/runtime`、`/api/adapters`、`/api/providers`、`/api/personas`、
`/api/memory/{sessions,timeline,stats}`、`/api/knowledge`、`/api/budget`、`/api/logs`、
`/api/access` 全部只读、全部鉴权、**任何响应都不含凭据**。

**验收标准**
- `providers.yaml` 里写一个字面量 `api_key`，`/api/providers` 的响应体中不出现它。
- 额度未启用时返回 `enabled: false`，而不是空列表——"没有申请"和"没有账本"必须可区分。
- runtime 未启用时 `/api/runtime` 返回 503 而不是 500 堆栈。
- 未知 `/api/*` 返回 JSON 404，不被前端 catch-all 吞成 HTML 200。

**证据**：`api/admin.py`、`tests/test_wave9_admin.py`（19 个用例）。

**为什么这一轮不做写接口**：改 persona 等于改系统提示里那段安全声明，改 provider 等于
把流量指向别人的端点——每一个都是独立的授权决策，值得单独设计与评审。本轮的目标是
"让系统可被观察"，这是安全变更的前提。

---

### #6 Vue3 管理面板

**预期行为**：登录、总览、运行状态、插件、安全审计、记忆与知识库、额度共 6 个界面；
产物随 wheel 打包由 FastAPI 托管；产物缺失时后端不崩溃，只提示未构建。

**验收标准**
- `npm run build` 产出 `src/soapbot/webui/dist`，`GET /` 返回该 `index.html`。
- 深链接（如 `/budget`）返回 SPA 外壳而不是 404。
- `/api/*` 的未知路径仍是 JSON 404。
- 打包不含 sourcemap。
- 产物缺失时 `GET /` 返回 200 + 构建指引。

**证据**：`webui/`（Vite + Vue 3 + TS + Pinia + Vue Router）、`app.py::_mount_webui`、
`tests/test_wave9_admin.py`（`test_built_webui_is_served_when_present` 等）。
浏览器实测（Edge，1440×900）已渲染并逐一检查：总览 / 运行状态 / 插件 / 安全审计 / 额度。

**偏离原计划的地方**：原计划选 TDesign 组件库，实际改用**手写 CSS 变量 + 少量自建组件**。
理由：6 个页面里需要的是表格、状态点、读数块，组件库的深色主题需要整套 less 变量覆盖，
引入约 400KB 依赖换来的是一层要对抗的默认样式。手写方案总产物 gzip 44KB，且"机房夜班
控制台"的视觉方向（等宽读数 + 单一琥珀色强调 + 面板角上的套准刻线）需要精确控制，
组件库反而挡路。如果你希望统一到 TDesign，这一步可以替换，代价是体积与主题适配。

---

### #7 `render_pending_notice`

**预期行为**：审批或驳回后，若队列里仍有待批申请，回复里追加一行汇总。

**验收标准**：两笔待批 → 批准第一笔后回复含"待审批申请"；批准第二笔后不含该行
（而不是"有 0 笔"）。

**证据**：`budget/commands.py::_remaining_notice`、`tests/test_wave5_commands.py::test_decision_reports_what_is_still_queued`。

---

### #8 容器镜像的配置目录

**发现**：`deploy/Dockerfile` 只 `COPY src`，没有 `COPY config`。而本轮把 personas 与
provider/adapter 配置统一到 `SOAPBOT_CONFIG_DIR`（默认仓库根的 `config/`）之后，容器内的
`/app/config` 根本不存在——镜像会启动成一个没有适配器、没有人格卡的进程。

**修复**：镜像内 `COPY config /app/config` 并设 `SOAPBOT_CONFIG_DIR=/app/config`；
compose 把宿主 `./config` **只读**挂上去。只读是刻意的：能改写 `adapters.yaml` 的插件
可以在下次重启时把机器人的连接指向别处。

**未验证**：本机没有 Docker，镜像未实际构建。`docs/deploy-layer.md` 里原有的同类警告仍然有效。

---

## 3. 验证记录

```
ruff check src/ tests/         All checks passed
pytest -q                      691 passed, 3 skipped
cd webui && npm run build      ✓ built（gzip ≈ 44KB）
cd webui && npm run typecheck  clean
```

真实服务端到端（`uvicorn soapbot.app:app`，非 TestClient）：

| 步骤 | 结果 |
|---|---|
| `GET /api/health` | 200 `{"status":"ok"}` |
| `GET /` | 200，返回 SPA 外壳 |
| `GET /api/auth/status` | `mode=loopback, login_available=true` |
| `POST /api/auth/login`（引导令牌） | 200，`expires_in=259200`，`role=owner` |
| 10 个只读接口（Bearer） | 全部 200 |
| `GET /api/runtime`（伪造令牌） | 401 |
| 引导令牌重放 | 401 |

浏览器（Edge headless，1440×900）已渲染：总览 / 运行状态 / 插件 / 安全审计 / 额度。

---

## 4. 遗留问题（按优先级）

1. **JWT 无吊销**。换密钥才能撤销。多操作者部署前需要服务端会话表。
2. **反向代理场景下的信任边界**。loopback 免令牌分支假设"能访问 loopback 的就是操作者"。
   若把服务放在代理后面，必须让代理丢弃外部传入的 `Authorization`，否则上游令牌语义不清。
3. **写接口缺失**：personas / providers / knowledge 上传 / memory 删除都没有 HTTP 写路径。
   目前只能改文件重启。这是刻意的，但意味着 WebUI 是"只读控制台"。
4. **B 站 L2 依赖 wbi 密钥轮换**。密钥每天轮换，客户端缓存 6 小时；若平台改动算法，
   L2 会整体失败（L1 不受影响）。没有自动化检测。
5. **适配器重连**：`onebot11` 自带重连，`qq_official` 依赖 botpy；runtime 不做统一的重连
   监督，适配器若静默失联，`health.online` 可能滞后。
6. **容器镜像未实测**（无 Docker 环境），包括新增的 config 挂载。
7. **额度上限未按角色区分**——仍建议不做，理由见 `wave5-budget.md` §11。

---

## 5. 需要你确认的事项

1. **生产暴露方式**：是否要在 loopback 之外的地址监听？如果需要，建议先在代理层做 TLS +
   令牌，再改 `SOAPBOT_HOST`。当前默认仍是 `127.0.0.1`。
2. **B 站档位**：默认 `l1`。你已选择实现 L2（签名），但是否在部署里启用 `l2`
   属于你的合规判断——代码只保证"启用 l2 时不会偷偷用登录态"。
3. **前端是否需要换成 TDesign**（见 #6 的偏离说明）。
4. **是否需要 WebUI 写能力**（provider/persona 编辑）。这需要单独设计授权与审计，
   不建议顺手加。
5. **令牌吊销策略**：接受"换密钥即全员下线"，还是要引入会话表？

# 参考生态：看了什么，改了什么，没抄什么

给了一批仓库，按生态分五类抽样看。这里只记工程做法，不记功能。每个仓库都是
Node/TypeScript 或 Python 的 QQ 机器人生态，和 soapbot 的 FastAPI + Vue + Docker
不是一套东西；能搬的是把边界写在哪、把校验放在哪、把恢复写成什么动作。业务功能
一个没搬。

看的是公开 README 与目录结构，没有引入任何一方的源码、依赖或运行时。

## 分组

| 类 | 仓库 | 抽样深读 |
|---|---|---|
| 协议运行时 | [SnowLuma](https://github.com/SnowLuma/SnowLuma)、[NapCatQQ](https://github.com/NapNeko/NapCatQQ)、[snowluma-websocket](https://github.com/SnowLuma/snowluma-websocket)、[SnowLumaNative](https://github.com/SnowLuma/SnowLumaNative)、[SnowDrift](https://github.com/SnowLuma/SnowDrift)、[tsilk](https://github.com/SnowLuma/tsilk)、[protobuf-dsl](https://github.com/SnowLuma/protobuf-dsl)、[NapCat-Docker](https://github.com/NapNeko/NapCat-Docker)、[SnowLuma 组织](https://github.com/SnowLuma) | SnowLuma、NapCatQQ |
| 文档站 | [SnowLumaDocs](https://github.com/SnowLuma/SnowLumaDocs)、[snowluma.github.io](https://github.com/SnowLuma/snowluma.github.io)、[.github](https://github.com/SnowLuma/.github) | SnowLumaDocs |
| 桌面与 Docker | [SnowLuma.Docker.Framework](https://github.com/SnowLuma/SnowLuma.Docker.Framework)、[SnowLumaDesktop](https://github.com/SnowLuma/SnowLumaDesktop)、[NapCatQQ-Desktop](https://github.com/NapNeko/NapCatQQ-Desktop)、[mcp-frida](https://github.com/SnowLuma/mcp-frida)、[ffmpeg-cmake](https://github.com/SnowLuma/ffmpeg-cmake) | SnowLuma.Docker.Framework |
| 插件市场 | [plugin-repo](https://github.com/Mai-with-u/plugin-repo)、[MaiBotOneKey](https://github.com/Mai-with-u/MaiBotOneKey)、[Amaidesu](https://github.com/Mai-with-u/Amaidesu)、[MaiCraftMod](https://github.com/Mai-with-u/MaiCraftMod) | plugin-repo |
| 机器人框架 | [MaiBot](https://github.com/Mai-with-u/MaiBot)、[Pallas-Bot](https://github.com/PallasBot/Pallas-Bot)、[MoFox-Core](https://github.com/MoFox-Studio/MoFox-Core) | MaiBot |

## 值得学的，明确不照搬的

| 来源 | 值得学 | 不照搬 |
|---|---|---|
| SnowLuma 主仓 | 会话接入 / 协议解析 / 身份映射 / OneBot 转换 / 网络适配各自独立；账号识别由登录数据库变化与进程事件触发，不做周期探测；JSON 消息段严格校验「data 必填且最终是对象」；`pnpm --frozen-lockfile` + typecheck + test 是同一条门禁 | 不搬 monorepo 与 OneBot 协议栈。soapbot 的适配器已经把协议翻译收在 `protocol/`，再加一层映射只是多一份要同步的状态 |
| NapCatQQ | `SECURITY.md` 单独维护；README 写明「不提供哪些支持」和许可边界；`packages/` 按能力分目录 | 不搬 NTQQ 注入与 native addon。那需要 `SYS_PTRACE` 和 `seccomp=unconfined`，与 soapbot 容器 `cap_drop: ALL` 的取舍相反 |
| SnowLumaDocs | README 只有四块：一句技术栈、DEVELOP 命令、BUILD 命令、一句明确禁令「不要复活旧脚本」。没有一个形容词 | 不搬 Fumadocs/Next.js 文档站。本仓库文档是仓库内的 Markdown，`check_doc_links.py` 能查，不需要生成器 |
| SnowLuma.Docker.Framework | 初始密码只在首次启动日志打印一次，之后存数据卷、重启不换；README 把已知坑直接写出来（软件渲染内存泄漏、nofile 上限、不要暴露 noVNC 端口）；构建产物按架构校验 | 不搬 supervisord 多进程与 VNC 桌面。soapbot 容器是单进程 + tini，`pids_limit` 与只读根是另一套边界 |
| plugin-repo | 索引拆成多个独立文件：列表、详情、版本、归档、封禁版本、可信开发者；版本发布与审核写成独立文档；README 只放链接 | 不搬中心化插件市场、可信开发者名单与远程版本索引。soapbot 是单实例人工审批，引入远端信任链会多一个可被投毒的源 |
| MaiBot | `EULA` / `PRIVACY` / `AGENTS` / `CLAUDE` / `pre-commit` / `changelogs` 各自独立；README 用作者原话写设计原则而不是功能清单 | 不搬其人格设定与插件事件系统。soapbot 的人格卡是人工审批的持久实体，不是提示词分层 |

## 落到本仓库的抉择

每条对照必须落到一个具体改动。没有对应改动的能力，就只写「不改」。

| # | 抉择 | 改了什么 | 为什么 | 不改什么 |
|---|---|---|---|---|
| 1 | 把边界写成可验证的契约 | `docs/security-boundaries.md` + `scripts/check_security_boundaries.py`，18 项各有一条防线；CI 双矩阵与 `make check` 都跑它 | 「已加固」是散文，改一次就可能退回去。负向不变量只能靠门禁守住 | 不引入 SAST 框架，不把检查做成需要联网的服务 |
| 2 | 认证凭据移出脚本可读区 | `webui/src/api/client.ts` 去掉 localStorage 与 Bearer 注入，改 `credentials: 'include'`；`api/auth.py` 下发 HttpOnly + SameSite Cookie 并做 CSRF 双提交 | SnowLuma 的一次性初始密码思路启发的是「凭据不要长期留在可读处」，不是照搬它的密码表单 | 保留 Bearer 给 CLI 与脚本；不引入 OAuth / 会话服务器 |
| 3 | 把「不做什么」写进 README | `README.md` 重写为四块，边界声明写清回环只读、CSP 不替代转义、正则上限不是硬超时 | SnowLumaDocs 和 NapCatQQ 都是这个写法：事实、命令、边界 | 不写功能清单，不写宣传语，不把 README 变成站点首页 |
| 4 | 错误响应与日志分工 | `api/errors.py` 统一异常分层与状态码映射；`logging_setup.py` 用 `json.dumps` 并剥离控制字符；`core/log_context.py` 用 ContextVar 贯穿定位字段 | 一次跨站的调试经历：异常原文回到浏览器，完整诊断却没进日志。两边都错 | 不引入 structlog，不改现有 `ProviderError` / `IsolationError` 继承 |
| 5 | 输入与上传在边界处收口 | `security/injection.py` 的 `bounded_scan()`；`plugins/installer.py` 的 zip 魔数与后缀白名单；`api/admin.py` 的 `_require_doc_id()` | 校验位置决定下一个存储后端是否继承它。放到 store 里等于赌存储实现 | 不加第三方 `regex`（会破坏 `check_deps.py`），不加文件类型识别库 |
| 6 | 命令构造不留字符串拼接 | `deploy/backup.sh` 把命令字符串改成 `compose()` 函数与引号路径 | 未加引号的 `$COMPOSE` 依赖分词，路径带空格就断，读起来也像在拼接输入 | 不改 `deploy_remote.py` 的 `--backup` / `--verify` / `--commit` 语义 |
| 7 | 恢复动作保持显式 | 保留 `PluginSupervisor` 的熔断需人工重置；巡检脚本只读报告 | SnowLuma 的账号识别靠事件不靠轮询，MaiBot 的审核靠人，都是同一条：自动重试会掩盖故障 | 不给巡检加自动重启，不给熔断加定时器 |
| 8 | 依赖与产物自己校验自己 | 保留 `check_deps.py`、CI 的 package job 与 `check_plugin_ipc.py`；新增门禁沿用「逐条打印证据行」的写法 | Docker.Framework 按架构校验产物，与 package job 检查 wheel 含面板是同一个道理 | 不引入镜像仓库、多平台 manifest 或 release 派发工作流 |

## 没搬的功能

SnowLuma 的多账号会话、MaiBot 的人格与插件事件、plugin-repo 的远端市场、
NapCatQQ 的 native 注入、MoFox-Core 的 fork 分支——这些是各自产品的形态，不是
边界治理。soapbot 这轮只动边界层、可观测层和文档结构，业务行为不变。

18 项逐条证据见 [安全边界与错误日志](security-boundaries.md)；认证行为见
[安全模型](security-model.md)；新增配置见 [配置](configuration.md)。

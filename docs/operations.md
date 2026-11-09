# 运维

部署、备份、巡检、排障、升级。本地开发命令在 README 的「门禁」一节。

## 坏了先看这里

**收到消息但不回复。** 按顺序查三件事：模型端点通不通（`GET /api/providers`）；
有没有 @ 它或说唤醒词（唤醒词在人格卡里）；`GET /api/runtime` 的 `metrics.halted`
涨没涨。中止原因会写进日志，`reason=not_woken` 和 `reason=private_not_allowed`
的处置完全不同。

**私聊没反应。** 默认谁都不能私聊。把 QQ 号加进 `SOAPBOT_PRIVATE_ALLOWLIST`，
或显式设 `SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true`。

**插件显示「已启用」但不干活。** 看「已授权」是不是「部分」——清单新增了能力而
批准没覆盖就会这样。`GET /api/plugins` 里 `approval.manifest_changed` 为 `true`
说明清单在批准后被改过，需要重新批准。

**QQ 掉线了，扫码也扫不进去。** 先看 `GET /api/protocol/napcat/status`。
`logged_in: false` 且二维码很久没变，说明 NapCat 的登录过期了，它自己不会换新码；
重启 NapCat 会出一张新的。卡片上写明码的年龄和上次失败原因。

**控制台白屏。** `GET /` 返回指引文字而不是 HTML，说明
`src/soapbot/webui/dist/` 缺失。clone 自带产物，只有手动清理过才需要 `make ui`。

**`SettingsError: error parsing value for field ...`** 列表型变量写坏了。用 `a,b`、
`a;b` 或 `["a","b"]` 都行。

**NapCat 每 72 小时准时掉一次。** Windows 计划任务默认
`ExecutionTimeLimit=PT72H`，到期会把 NapCat 连同 QQ 一起杀掉。用
`scripts/install_napcat_task.ps1` 注册，它设成 `PT0S` 并加开机自启。

**登录后写操作返回 403。** Cookie 会话的写操作要带 `X-CSRF-Token`，值取
`soapbot_csrf`；同时 `Origin` 必须同源。脚本用 Bearer token 不受这条约束，因为
跨站页面附加不了 Bearer 头。

## 部署前检查

```bash
python -m soapbot.cli doctor --strict
make check
cd webui && npm run verify
```

`doctor --strict` 检查绑定地址、密钥来源、文件权限、插件隔离模式和上游端点，
有 critical/high 未解决就退出非零。它不替代容器实测：静态配置对了不等于
`docker compose -f deploy/docker-compose.yml up -d` 能起来。

`strict_startup` 默认关闭，一个可选适配器构造失败会被记录并跳过，控制台还能用来
排障。要硬边界就设 `SOAPBOT_STRICT_STARTUP=true`，启动阶段直接中止。

容器、systemd、Windows 计划任务、反向代理的具体写法在
[deployment.md](deployment.md)；容器加固的分层说明在
[deploy-layer.md](deploy-layer.md)。

## 备份

```bash
python scripts/deploy_remote.py --host <IP> --user root --port 443 \
  --key <私钥路径> --backup --keep 10
python scripts/deploy_remote.py --host <IP> --user root --port 443 \
  --key <私钥路径> --verify
```

`--backup` 把 `/data` 命名卷只读挂进 Alpine 打包，最后用 `tar -tzf` 证明归档能打开。
`--verify` 是 14 项只读验收，两者必须分开运行。systemd timer
`deploy/soapbot-backup.timer` 每日 03:30 调 `deploy/backup.sh`。

`scripts/backup.py` 产出的 zip 与远程 tar.gz **不互通**：zip 含 SQLite 一致性快照
与 config，不含 `/data/.env`、`secret.key`；`scripts/restore.py` 只吃 zip。恢复前
先停服务，恢复脚本会拒绝更高 schema、阻止路径穿越，并把旧库改名保留。

## 巡检

`scripts/plugin_worker_guard.py` 只读报告容器状态、worker 进程数、僵尸态和回环
健康接口，支持 `--json`。`deploy/plugin-worker-guard.timer` 每 5 分钟触发一次。
它**不会**重启任何进程：自动重启会掩盖敌意插件，也会和熔断策略打架。

```bash
make guard                                   # 离线自检
python scripts/plugin_worker_guard.py --json  # 需要 docker / ps
```

插件崩溃后 worker 保持下线，由运维 reload 恢复；熔断只能显式重置。理由见
[deploy-layer.md](deploy-layer.md) 的故障恢复一节。

## 升级

固定版本部署，不用漂移的分支：

```bash
python scripts/deploy_remote.py --host <IP> --user root --port 443 \
  --key <私钥路径> --commit <完整 SHA> --dry-run   # 先看步骤
python scripts/deploy_remote.py --host <IP> --user root --port 443 \
  --key <私钥路径> --commit <完整 SHA>
```

驱动每步独立 SSH、失败即停，会构建镜像、重建容器、等待 healthy，再跑 uid、只读根、
健康端点、tini 和 doctor。升级前先备份。回滚步骤见
[UPDATING.md](../UPDATING.md)。

## 数据库迁移

启动时会自动迁移，`soapbot migrate` 是把这一步单独拿出来执行——换二进制前、恢复备份后、
或排查启动失败时用：

```bash
soapbot migrate --status    # 只读：当前 schema 版本 -> 本程序支持的版本
soapbot migrate --dry-run   # 只读：列出将要执行的步骤，不动库
soapbot migrate             # 顺序升到本程序支持的版本
```

三条约束值得记住：**只前进**（`--target` 小于当前版本会被拒绝，不提供降级）；**不建库**
（文件不存在或为空时拒绝执行，因为那样只会留下一个只有版本号、没有业务表的文件）；
**老库不会被盖章跳过**（早于版本控制、有业务表但无版本记录的库，会先记为 v1 再顺序补齐，
而不是直接标成最新）。退出码 `2` 表示库比程序新，与 `doctor --strict` 一致。

## 门禁清单

| 脚本 | 查什么 |
|---|---|
| `check_secrets.py` | 暂存区 / 待推送对象 / 已提交树里的凭据与生产产物 |
| `check_plugin_ipc.py` | 插件进程边界的 65 条否定式不变量 |
| `check_security_boundaries.py` | 20 项安全与错误日志契约 |
| `check_deps.py` | `requirements.txt` 与 `pyproject.toml` 运行时依赖一致 |
| `check_console_encoding.py` | 打印中文的脚本必须先 reconfigure(utf-8)，否则只在 Windows runner 上红 |
| `check_deploy.py` | 容器配置静态校验 |
| `check_doc_links.py` | README / SECURITY / docs 的相对链接 |
| `check_test_gaps.py` | 孤儿模块与文档数字 |
| `check_contrast.py` / `check_a11y.py` | 对比度与可静态检查的无障碍规则 |

`pre-push` 只跑 `check_secrets.py --pre-push`（用项目虚拟环境的解释器，Windows 上不依赖
系统 `python`），所以**只有它会挡住 push**；其余八项由 `make check` 与 CI 的 `backend`
任务拦截，本地不跑就直接推的话，红在 CI 而不是红在 push。
`tests/test_gate_parity.py` 断言 `make check` 与 CI 的差集恰好是两项（`check_secrets
--committed` 要 git 历史、`pip-audit` 要联网），两边再漂移就会红。

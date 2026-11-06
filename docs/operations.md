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
`docker compose up` 能起来。

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

## 门禁清单

| 脚本 | 查什么 |
|---|---|
| `check_secrets.py` | 暂存区 / 待推送对象 / 已提交树里的凭据与生产产物 |
| `check_plugin_ipc.py` | 插件进程边界的 62 条否定式不变量 |
| `check_security_boundaries.py` | 18 项安全与错误日志契约 |
| `check_deps.py` | `requirements.txt` 与 `pyproject.toml` 运行时依赖一致 |
| `check_deploy.py` | 容器配置静态校验 |
| `check_doc_links.py` | README / SECURITY / docs 的相对链接 |
| `check_test_gaps.py` | 孤儿模块与文档数字 |
| `check_contrast.py` / `check_a11y.py` | 对比度与可静态检查的无障碍规则 |

前三个失败会让 push 或 CI 直接红。`pre-push` 用项目虚拟环境的解释器，
Windows 上不依赖系统 `python`。

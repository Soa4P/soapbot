# 升级指南

## 原则

升级前**先备份**。本项目不对「跳过多个版本」做兼容承诺，但会对每一次 schema 变更
提供顺序迁移，所以按版本顺序升是安全的。

## 升级步骤

```bash
# 1. 停服务
docker compose -f deploy/docker-compose.yml down      # 或 systemctl stop soapbot

# 2. 备份（必须）
python scripts/backup.py --out backups/pre-upgrade.zip

# 3. 更新代码
git fetch --tags && git checkout v0.2.0

# 4. 装依赖
pip install -e .            # 或 docker compose build

# 5. 数据库迁移
soapbot migrate

# 6. 自检
soapbot doctor --strict

# 7. 起服务
docker compose -f deploy/docker-compose.yml up -d

# 8. 验证
curl -sS http://127.0.0.1:6185/api/health
```

## 数据库版本

`memory/db.py` 的 `SCHEMA_VERSION` 是库结构的版本号，与包版本独立。

```bash
soapbot migrate --status     # 当前版本与目标版本
soapbot migrate              # 顺序升到当前包所需的版本
```

迁移**只前进**。回滚需要从备份恢复，不提供降级脚本——降级脚本要写两套逻辑，
而实际发生的回滚远少于升级，维护成本与出错概率都不划算。

若 `SCHEMA_VERSION` 高于代码（即你回退了代码但没恢复数据库），启动会拒绝运行并
给出明确提示，而不是带着未知结构继续跑。

## 从无版本控制的历史版本升级

若你的部署早于首次发布（没有 `git` 历史），升级方式是：

1. 备份 `data/` 与 `config/`
2. 用新版本代码覆盖，保留 `data/` 与 `config/`
3. 对比 `config/` 与仓库中的模板，手动补齐新增必填项
4. `soapbot migrate`

`soapbot doctor` 会指出缺失的配置项。

## 回滚

```bash
git checkout <旧版本>
python scripts/restore.py --in backups/pre-upgrade.zip
```

恢复脚本会校验备份中的 schema 版本与当前代码是否兼容，不兼容会拒绝并说明原因。

## 各版本变更要点

### 0.1.0 → 后续

见 [CHANGELOG.md](CHANGELOG.md)。每一项破坏性变更都会标注 `BREAKING`，
并在此处补充对应的迁移说明。

## 常见问题

**升级后面板打不开，显示 "not built"**
说明 `src/soapbot/webui/dist/` 缺失。该目录随仓库提交，若你用了只复制 `src/` 的
部署方式，需要一并复制它，或本地 `make ui` 重新构建。

**升级后插件全部失效**
插件的 `manifest_digest` 变了（manifest 被改动），需要重新审批。这是设计如此：
改 manifest 等同于改权限声明。在插件页逐项重新批准。

**`soapbot migrate` 报 "database is locked"**
先停止服务。SQLite 在 WAL 模式下仍不允许两个进程同时写 schema。

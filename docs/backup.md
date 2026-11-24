# 备份与恢复

两条互补的备份路径：**应用层**（`soapbot backup`，本文档）与**部署层卷快照**
（`scripts/deploy_remote.py --backup`，整卷 tar，见 deploy-layer.md §8）。日常用
应用层；迁移整台机器用卷快照。

## 应用层备份（`soapbot backup`）

```bash
# 创建（默认输出 <data>/backups/，保留最近 7 份）
soapbot backup create
soapbot backup create --out /mnt/backup --keep 14

# 列出（名字、大小、摘要前 16 位）
soapbot backup list

# 校验 + 演练（不落盘）
soapbot backup restore <data>/backups/soapbot-backup-20261121-120000-123.zip --dry-run

# 恢复（先停服务；恢复前自动快照当前状态）
docker compose stop    # 或 systemd stop
soapbot backup restore <归档路径>
```

每份归档 = **zip + `manifest.json`**（逐文件 sha256、`schema_version`）加一
`.sha256` 边车。两层校验各挡一种攻击：边车管整包字节（含 manifest），manifest 管
恢复时真正写下去的内容——把替换过的文件连同摘要一起重写，能过逐文件校验，过不了
边车。**数据库走 SQLite 在线备份 API**——服务运行中创建的备份也是一致快照。

> 格式历史（S-DEP-12）：曾经有两套实现（CLI 的 `tar.gz`+边车、部署定时器的
> `zip`+manifest）。现统一为 **zip+manifest**——那是生产归档既有的格式，换写入端
> 等于同时改定时器的轮换、`chmod 600` 与恢复手册。`scripts/backup.py` /
> `scripts/restore.py` 现在是同一实现的薄入口，`deploy/backup.sh` 的命令行不变。
> 收敛前的 `tar.gz` 归档需用旧版程序恢复（当前读取端会明确拒绝并说明原因）。

**恢复的安全语义**：

* 恢复前自动给当前状态打一份快照（标 pre-restore，进同一轮换）——恢复失败本身可逆；
* 归档成员逐一检查：绝对路径、`..`、非 `data/`/`config/` 前缀一律拒绝（与插件安装器
  同一套穿越纪律）；解包到暂存目录并跑 `PRAGMA integrity_check`，通过了才动现库；
* 旧库不覆盖而是改名成 `soapbot.db.pre-restore-<时间戳>`，恢复错了改回来即可；
* 恢复运行中的活库是危险的（WAL 会打架）——先停服务；忘了停，恢复完重启服务加载。

**备份里有什么**：`data/` 全部——数据库、`config/`（providers/adapters/personas）、
插件、上传与存档，以及 `secret.key`/`jwt.key`。**钥匙在备份里**意味着备份文件
本身就是敏感物（能解密插件加密存储）——存放位置要与主机同级防护。与 dsh-backup
「凭据默认脱敏」相反，这里默认全量：不能解密存储的备份对 soapbot 没有恢复价值；
需要脱敏场景手动删掉两个 key 文件再打包。

**不内置任何网络上传**：备份只写本地盘（`<data>/backups/` 或 `--out` 指定的本地
目录）。异地保存需要用户自己手动传输并自行加密——这是有意不做的能力：自动上传
意味着密钥材料离开主机。

**轮换**：`--keep N` 保留最近 N 份（默认 7），旧归档与边车一并删除。

Docker 部署下命令在容器内执行：
`docker exec deploy-soapbot-1 python -m soapbot.cli backup create`。

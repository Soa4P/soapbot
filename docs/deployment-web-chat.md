# 网页聊天端部署方案（服务器 A）

本轮已批准按 **A1** 执行：SSH 从 443 迁到 2222，443 交给 Caddy 做 HTTPS。本文是执行
前的完整方案与回滚步骤，包括内存与端口两个已知约束。**端口价格与服务器价格不在此列**
——那是你的账单，不是本仓库能断言的事实。

## 拓扑

```text
用户浏览器 / 手机 App
        │ HTTPS 443
        ▼
      Caddy  ──/api/*──►  uvicorn 127.0.0.1:16700  ──►  SQLite + 适配器
        │                    （soapbot-web.service）
        └──/──►  面板静态文件（src/soapbot/webui/dist）
```

- 网关（OneBot 反向 WS，`SOAPBOT_ONEBOT_GATEWAY_*`）仍只绑 `127.0.0.1:6700`，
  由协议端从本机连入；**不**经 Caddy 暴露。
- 只有 Caddy 监听公网端口。uvicorn 不监听 `0.0.0.0`。

## 约束一：443 被 sshd 占用

服务器 A 现状：`sshd` 监听 443，80 空闲，没有 nginx/Caddy。要让 Let's Encrypt 走
HTTP-01 并让用户走 HTTPS，必须把 443 让出来。

步骤（**保留当前 SSH 会话不要关**，直到第 4 步验证通过）：

1. 改 `/etc/ssh/sshd_config`：新增 `Port 2222`，**先不删** `Port 443`。
2. `systemctl restart sshd`，确认 443 和 2222 都能登录。
3. 改 `Port 2222`、删 `Port 443`，`systemctl restart sshd`，用
   `ssh -p 2222 -i <key> root@<host>` 新开一个会话验证。
4. 旧会话仍然开着，此时才动 443。
5. 云厂商控制台的安全组放行 2222，并**保留** 80/443。

回滚：把第 3 步反过来即可。因为第 2 步同时开了两个端口，任何一步失败都还有一条活路。

## 约束二：内存偏紧

探测结果：2 vCPU / 3.9 GB，可用约 **341 MB**。已存在三个旧实例（`soapbot-c.service`、
docker `deploy-soapbot-1`、一个 cwd 已删除的进程），它们加起来是这个数字的来源。

因此上线顺序是先腾内存、再起新实例：

1. `systemctl stop soapbot-c.service`（**只停不删**）。
2. `docker stop deploy-soapbot-1`（同样只停不删，镜像与卷保留）。
3. `kill <PID>` 那个 cwd 已删的残留进程（先 `ps -o cwd=` 确认）。
4. `free -m` 记录腾出来的量，再启动新实例。

粗略占用：Caddy 约 30–50 MB，uvicorn + 适配器约 150–250 MB（含 scrypt 登录峰值）。
341 MB 属于「能跑但没余量」——真出现 OOM，选一个：

- 给 A 加内存（**需要你确认价格**，本文不给数字）；
- 把适配器搬到 B，A 只留面板（B 是 Windows Server 2019，2 vCPU / 2 GB，需要先验通）。

## 安装

```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
apt-get update && apt-get install -y caddy

# 代码与虚拟环境
git clone <repo> /opt/soapbot-web && cd /opt/soapbot-web
python3 -m venv .venv && ./.venv/bin/pip install .

# 配置
cp .env.example .env    # 填 init token、域名、chat 开关
```

`/etc/caddy/Caddyfile`：

```caddyfile
chat.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:16700
}
```

`systemd` 单元 `/etc/systemd/system/soapbot-web.service`：

```ini
[Unit]
Description=Chat archive for SoapBot
After=network-online.target

[Service]
WorkingDirectory=/opt/soapbot-web
EnvironmentFile=/opt/soapbot-web/.env
ExecStart=/opt/soapbot-web/.venv/bin/soapbot start --host 127.0.0.1 --port 16700
Restart=on-failure
MemoryMax=700M
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

`MemoryMax` 是有意的：宁可被 systemd 杀掉并重启，也不要触发整机 OOM 把 SSH 一起带走。

## 上线后验证

```bash
curl -fsS https://chat.example.com/api/chat/surfaces
# 期望：{"web":true,"app":false,"desktop":false}

curl -fsS -X POST https://chat.example.com/api/accounts/login \
  -H 'content-type: application/json' \
  -d '{"username":"<owner>","password":"<password>"}' | head -c 200

curl -fsS https://chat.example.com/api/chat/sessions -H "cookie: <拿到的 cookie>"
```

- 未登录访问 `/api/chat/sessions` 必须 401；
- 用非成员账号访问别人会话必须 404；
- 备注写入后 `curl` 拉 `/api/chat/messages` 应看到 `role="note"`；
- **不去 QQ 侧验证**：备注本就不该出现在那里，出现才是 bug。

## 成本增量

| 项目 | 是否需要新增支出 |
| --- | --- |
| 服务器 A / B | 已有，无新增 |
| 域名 | 已有，无新增 |
| Let's Encrypt 证书 | 免费 |
| 带宽 | 存档是文本，按现有流量估可忽略 |
| 内存升级（若选） | **需要你按供应商报价确认** |
| 手机端构建 | 需要 Flutter SDK 与 Android SDK，本机安装约 10 GB 磁盘 |

本文有意不写具体金额：写一个凭印象的价格比不写更糟。

## 回滚

1. `systemctl stop soapbot-web && systemctl disable soapbot-web`
2. `systemctl stop caddy`（或只删 Caddyfile 里的站点块并 `systemctl reload caddy`）
3. `sshd_config` 恢复 `Port 443`
4. `systemctl start soapbot-c`（旧实例只被停过，目录与数据都在）

数据库是 `data/*.db`，新增三张表不影响旧版本读取：旧代码不认识它们，但也从不查询。

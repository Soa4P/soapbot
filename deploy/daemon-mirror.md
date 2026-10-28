# 镜像加速配置（服务器部署前置步骤）

## 为什么必须先做这一步

在本机实测过（2026-10-28）：

```
$ curl -m 8 https://registry-1.docker.io/v2/
超时
$ curl -m 8 https://registry-1.docker.io/v2/library/python/manifests/3.12-slim
超时
```

而三个国内源可达，且走完整 token 流程后能真实取到 manifest：

```
docker.m.daocloud.io         → token 200（718 字节）→ manifest 200（10373 字节）
registry.cn-hangzhou.aliyuncs.com → 401（v2 协议正常，需鉴权）
docker.nju.edu.cn            → 403（可达）
```

**结论**：不做加速配置，`docker build` 会在第一行 `FROM python:3.12-slim` 就失败。
这不是「慢」，是直接不通。先配镜像源，再谈构建。

## 配置方式

### Linux 服务器（推荐）

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.nju.edu.cn"
  ],
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON

sudo systemctl daemon-reload
sudo systemctl restart docker
```

验证（必须看到实际返回，不能只看命令成功）：

```bash
docker pull python:3.12-slim
docker image ls python
```

`docker pull` 成功且 `docker image ls` 列出 `python 3.12-slim` 才算配好了。

### 如果不允许改 daemon.json

在 `Dockerfile` 顶部把基础镜像换成显式带仓库前缀的形式，一处改完：

```dockerfile
FROM docker.m.daocloud.io/library/python:3.12-slim AS build
FROM docker.m.daocloud.io/library/python:3.12-slim AS runtime
```

`scripts/check_deploy.py --mirror <host>` 会把这个条件记录进检查结论，所以两种做法都能被
检查脚本识别。

## 构建与启动

```bash
# 1. 静态预检（不需要 docker daemon，本机也能跑）
python scripts/check_deploy.py --mirror docker.m.daocloud.io

# 2. 构建
docker compose -f deploy/docker-compose.yml build

# 3. 首次启动
docker compose -f deploy/docker-compose.yml up -d

# 4. 观察
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f --tail=100
```

## 启动后必须核对的四件事

这四项是「容器里真的能跑」的判据，缺一项都不能写「已验证」：

| 检查 | 命令 | 期望 |
|---|---|---|
| 进程非 root | `docker compose exec soapbot id -u` | `10001` |
| 根文件系统只读 | `docker compose exec soapbot touch /x` | 失败（Read-only file system） |
| 数据卷可写 | `docker compose exec soapbot touch /data/x && rm /data/x` | 成功 |
| 面板可达 | `curl -sS http://127.0.0.1:6185/api/health` | `{"status":"ok",...}` |

健康检查本身也是判据：

```bash
docker inspect --format '{{.State.Health.Status}}' $(docker compose ps -q soapbot)
# 期望 healthy（start_period 20s + interval 30s，等 60s 再查）
```

## 已知需要在服务器上确认的两点

1. **容器内绑定地址已改为 `0.0.0.0`**。原配置绑定 `127.0.0.1`，端口映射永远连不上
   容器；隔离改由宿主机侧 `127.0.0.1:6185:6185` 保证。这一条改动是静态审阅结果，
   **未在真实容器里验证过**。
2. **主密钥默认写入 `/data/secret.key`**（在数据卷内，可持久）。挂载独立密钥文件的做法
   写在 compose 注释里，但当前默认关闭——因为 bind mount 源不存在时 Docker 会创建一个
   空目录，应用读目录当密钥文件会失败，然后静默退化为明文存储。宁可先用「数据卷内的
   密钥」，也不要一个看起来更安全、实际退化成明文的状态。

# 全库安全审查报告（2026-11-12）

> 方法：按云鼎实验室 Skill 审查 skill 的三层流程（关键词扫描 → 深度分析 → 供应链
> 溯源）对**整个仓库与插件仓库**做一轮只读审查；同时用 code-vuln-crossreview 的
> 双视角（攻击者/建设者）复核了 #49–#53 五轮 PR 的安全敏感面。本文只记结论与证据，
> 不复制扫描过程。

## 结论

**0 Malicious / 0 Suspicious（必须处理）/ 2 项 P2 建议。** 静态门禁之外未发现新的
恶意或可疑模式。

## 覆盖面与判定

| 审查面 | 覆盖方式 | 判定 |
| --- | --- | --- |
| 远程执行模式（`curl\|bash`、`irm\|iex`） | scripts/、deploy/、.github/ 全扫 | **Suspicious → 已降级**：全部指向本仓库自身 master（install.ps1 / install.sh / windows-bootstrap），README 已提供 `-OutFile` 下载后执行变体；固有风险（master 可变）由部署文档声明。P2-1 建议加 pinned tag 变体 |
| 未固定版本安装 | scripts/、deploy/、CI、docs | 干净：pip 安装全部 `==` 固定或在 venv 内；无 `npm i -g` 未固定版本 |
| Base64 隐蔽载荷 | scripts/、deploy/、CI | 0 命中（ci.yml 唯一命中是零 SHA 比较） |
| 敏感路径（.ssh//etc/凭据） | scripts/、deploy/、src/ | 命中均为防御代码注释或操作者自己的 SSH 用法说明 |
| PATH/shell 配置篡改 | scripts/、deploy/ | 0 命中 |
| 出站域名清单 | scripts/、deploy/、CI、examples | github.com / python.org / docker 官方源 / napcat.napneko.icu（NapCat 安装文档）/ daocloud+nju 镜像（daemon-mirror.md 有实测记录）——全部与功能直接相关 |
| 子进程 worker 模板 | supervisor.py | 无直接出站；execve 不经 shell；http 面经宿主白名单 |
| 示例插件（bili/qzone-watch/echo/warmth-observer） | 源码逐读 | 出口钉死（bilibili 域 / qzone 网关），声明最小能力集 |
| qzone 网关（#51） | qzone.py + surfaces.py | 动作白名单（3 读 1 写）、fail-closed 默认关、token 只进请求头不回插件、写需 confirm=true、审计只记长度、错误只报状态码——干净 |
| 温度模型写入权（#52） | 全仓写点追踪 | 唯一写点在回复成功归档后；插件只读 |
| WBI 字幕（#52） | bilibili/client.py | 无登录态注入、字段白名单、BV 校验不触网 |
| 审批 feed（#49/#50） | admin.py | require_api_auth + MANAGE_CONFIG + 白名单 payload |
| 插件仓库六包 | packages/ 逐读 | 危险模式 0；出站只有 open-meteo / nmc.cn；凭据零命中 |
| mcp.yaml 模板 | config/ | 默认空 servers；命令必须是参数列表（execve 不经 shell）；min_role fail-closed |

## P2 建议（不阻断，下一批顺手）

1. **P2-1 · pinned 安装变体**：README 的 `irm | iex` / `curl | bash` 指向 master。
   建议在部署文档加一条 pinned tag 变体（`codeload.github.com/Soa4P/soapbot/zip/refs/tags/v<版本>`），
   给想要可复现安装的操作者一个显式选择。既有 `-OutFile` 变体已覆盖一部分。
2. **P2-2 · 失效镜像标注**：daemon-mirror.md 已记录 `docker.nju.edu.cn → 403`，
   建议在 compose 注释里同步标注，避免后来者选用失效源。

## 审查方法声明

- 全程只读：未执行任何被审代码，未运行被审安装脚本。
- 负责范围：本仓库、插件仓库（packages/ 六包）、CI 工作流、部署脚本与文档中的
  命令面。第三方依赖的供应链以 pip-audit（CI）为准，不在本轮。
- 工具：云鼎三层审查流程 + code-vuln-crossreview 双视角；静态门禁
  （security-boundaries 89 项、plugin-ipc 67 项）作为既有契约基线不再重复。

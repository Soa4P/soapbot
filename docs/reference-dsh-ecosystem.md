# DSH 生态参考评估：哪些能迁移到 soapbot

本文回答一个问题：三个参考仓库都是 DeepSeek Harness（DSH）/ Node.js / Windows 桌面生态的
项目，与 soapbot（Python / FastAPI / Vue / Docker on Linux）技术栈不同，其中哪些设计
**适合**搬过来，哪些不适合。结论先行：

- **治理机制适合迁移，且已落地实现**（见下表）。
- **运维形态适合迁移，但必须改造成「只读」**（见「看门狗」一节）。
- **业务设计不适合移植**，只给出评估结论，不实现（见最后一节）。

参考仓库：

- [surfcore](https://github.com/Mieksido/surfcore)
- [qq-dsh-bridge](https://github.com/NoMindSama/qq-dsh-bridge)
- [dsh-bili-humanism](https://github.com/InariNGT-Ofiicial/dsh-bili-humanism)

> 边界说明：以下均来自这些仓库的公开 README 与设计说明，只读评估，没有引入它们的源码、
> 依赖或运行时，也没有在本项目里复刻 DSH 的会话模型。

---

## 1. 三者各自的架构位置

| 仓库 | 形态 | 进程间通信 | 与本次问题的关系 |
|---|---|---|---|
| surfcore | DSH 插件 bundle + 独立 `src/bridge.js` 单实例桥接 | HTTP（本机 Cookie）、OneBot WS、stdio MCP | 双进程划分、fail-closed 工具面、发布前审计门禁 |
| qq-dsh-bridge | QQ ↔ OneBot ↔ 桥接主进程 ↔ DSH Web API ↔ MCP | WS + slash RPC + mux 事件流、stdio MCP | 出站二次校验、重连、看门狗、发送限流与体积上限 |
| dsh-bili-humanism | 原生 JS DSH bundle（进程内工具） | DSH SDK stdio JSON-RPC | 请求/事件回执关联、明确字节预算、任务互斥与持久暂停 |

三者都没有「把 Python 插件放进子进程并用 pickle 传对象」这种形态；它们提供的是
**协议与治理经验**，不是可直接复用的代码。

---

## 2. 已迁移的治理机制

| 机制 | 来源 | soapbot 落地位置 | 说明 |
|---|---|---|---|
| 请求与响应一一关联，迟到/伪造帧不算数 | dsh-bili-humanism 的 stdio JSON-RPC 请求 id；surfcore 处理「字幕串台」时坚持身份核验 | `src/soapbot/plugins/supervisor.py` | `invoke` 生成随机 `rid`；`result.id` 与 `call.rid` 都强校验；串行调用加 `asyncio.Lock` |
| 明确字节预算 + 可诊断的超限错误 | dsh-bili-humanism：JSON 4 MiB、媒体 32 MiB、单卷 24 KiB，`RESPONSE_TOO_LARGE` 给出上限与已读字节 | `src/soapbot/plugins/isolation.py` 的 `MAX_FRAME_BYTES`；`supervisor.py` 的 `_read_frame` / `_write_frame` | 唯一常量源，注入两个 `-I` 子脚本；父子双向都限；错误带「实际字节 + 上限」 |
| 出站二次校验、fail-closed 工具面 | qq-dsh-bridge：工具调用再过白名单 + 档位 + 开关 + 限流 + 敏感词；surfcore：工具面白名单、无管理员后门 | `supervisor.py::_handle_callback` | 保留父进程单一授权点；新增 rid 绑定，未绑定的回调根本不进 capability dispatcher |
| 不可信数据不能成为授权依据 | dsh-bili-humanism：字幕/标题不得作为权限或删除记忆的授权 | `supervisor.py` 的 `_FORBIDDEN_ARG_KEYS`、子端 `_boot_path` | IPC 帧与 boot 参数一律视为不可信；子端再校验路径与 attr |
| 进程数上限、任务互斥、退出恢复 | dsh-bili-humanism：SQLite 任务互斥、取消、进程退出恢复、持久暂停 | `config.py::max_plugin_workers`、`supervisor.py::PluginSupervisor`、`loader.py::unload_all` | 默认 16、硬顶 64、0 非法；退出看护 reap；关闭路径统一 `stop_all()` |
| 结果不明不自动重试、恢复需人工显式动作 | dsh-bili-humanism：账号风险持久暂停，需可信 CLI `resume --acknowledge-account-risk`；surfcore 的重启矩阵 | 既有熔断 + `reset_circuit()` | 熔断不随时间自动恢复；新增巡检**不得**自动重启 |
| 发布前离线回归门禁 | surfcore `test:audit` / `privacy-scan:strict`；dsh-bili-humanism 的离线回归 + 三平台 CI | `scripts/check_plugin_ipc.py`、`.github/workflows/ci.yml`、`Makefile` | 静态固化「无 pickle、两端帧预算一致、请求关联、stdout drain、进程上限」等否定式不变量 |
| 发布包完整性与来源固定 | surfcore 的 SHA-256 + `merge --ff-only`；dsh-bili-humanism 的 Release 校验与固定 commit SHA | `scripts/deploy_remote.py --commit <完整 SHA>`、`scripts/check_secrets.py` / `pre-push` | 部署固定版本，不依赖分支漂移；推送前扫描实际将离开仓库的 Git 对象 |

**刻意没有照搬**的一条：surfcore 与 qq-dsh-bridge 的「白名单为空 = 谁都不响应」。
soapbot 的会话/群组白名单语义是「空列表 = 监听全部」，这是运营者已确认的行为，改成
全拒会造成静默失联。

---

## 3. 运维脚本：迁移但改成只读

qq-dsh-bridge 提供 `bridge-guard.ps1` 看门狗、`qq-bot.ps1 status|start|stop|restart`、
每日记忆备份；surfcore 有 12 篇运维文档与「改什么要重启什么」矩阵。soapbot 落地为：

- `scripts/plugin_worker_guard.py`：`docker compose ps`、`ps`、回环健康接口的**只读**巡检，
  统计 worker 子进程数、僵尸态、容量水位，支持 `--json` 与 `--self-test`。
- `deploy/plugin-worker-guard.service` + `.timer`：每 5 分钟触发，与每日 03:30 的
  `soapbot-backup.timer` 互不依赖。
- `make guard` 在本地跑离线自检；`make ipc-audit` 跑静态门禁。

**关键差异：soapbot 的巡检绝不 kill / restart。** 插件崩溃的恢复权归
`PluginSupervisor` 的退避与熔断，且熔断只能由运维显式重置。一个自动重启的看门狗会
掩盖敌意插件、制造绿色假象，并与熔断状态打架。这与 dsh-bili-humanism「结果不明不
自动重试」是同一条原则。

---

## 4. 业务设计评估：结论是不移植

以下是三者最具特色的业务设计。逐项给出结论与理由；**本次不实现**。

### 4.1 人格三层/四层结构（surfcore、qq-dsh-bridge）

DSH 把人格拆成 preset persona、agent-context 注入、临时角色卡、本轮唤醒包，并让它在
相处中「成长」。soapbot 已有**人工审批的人格卡**（Persona ID 作为稳定标识，按
用户 → 群组 → 全局默认 → 第一张可用卡的顺序绑定），属于显式配置而不是提示词分层。

**结论：不移植。** 理由：① DSH 的分层是为「同一 agent loop 内复用 system prompt 前缀」
服务的，soapbot 的人格卡是一次配置、多次读取的持久化实体，没有对应的缓存语义；
② 「人格会自己成长」与本项目「人格变更需人工审批、可审计」的安全模型冲突，模型
自行改写人设会成为提示注入的落点；③ 迁移需要引入 preset / context 注入管线，属于
运行时重构，远超插件进程治理的范围。

### 4.2 四层记忆 + selfNote（qq-dsh-bridge）

L0 原文库、L1 会话摘要、L2 长期事实、L3 产物索引，加一层 L4「AI 对自己的叙述」，
由模型自己写、只在会话首次唤醒时读一次，上限 40 条。

**结论：不移植。** 理由：① soapbot 已有按采集 scope 隔离的记忆与知识库文档，二者
职责不同且已有回归测试锁定；② 新增一层「模型对自身的叙述」等于给不可信的模型输出
一个跨会话持久化的写入口，而本项目的记忆写入要经过能力与 scope 双重判定；③ 该设计
的价值依赖 DSH 会话生命周期，soapbot 没有对应的会话对象可挂载。

### 4.3 只在闲置边界压缩上下文（qq-dsh-bridge）

压阈值从 0.15 提到 0.95，等安静 30 分钟、上下文超过 30 万 token 时先让模型写记忆、
再调 `/compact` 原地压缩，以保住 provider 的 KV cache 前缀命中率。

**结论：不移植。** 理由：① 这是一个针对 DSH `compaction-basic` 在 agent loop 内每步
检查阈值的具体缺陷，soapbot 没有这个压缩器，也没有「每步检查」的行为；② 收益完全
来自 provider 的 KV cache 前缀命中，属于特定模型通道的计费/延迟优化，与进程隔离、
IPC 安全无关；③ 「压缩前先写记忆」会把模型输出变成持久化事实，同样引入不可信写入。

### 4.4 其它（写入执行器、每日取稿、桌宠、B 站作息）

dsh-bili-humanism 的历史/收藏/点赞/投币执行器、每日取稿预算，surfcore 的 B 站作息与
桌宠，都是面向具体平台账号的能力，不是插件进程边界的一部分。

**结论：不移植。** 与本次目标无关，且会显著扩大对外写入面。

---

## 5. 一句话总结

可以搬的是「把边界写成协议、把预算写成常量、把恢复写成显式动作、把不变量写成
CI 门禁」；不能搬的是「让模型自己决定长期状态」。前者与 soapbot 现有的父进程授权、
显式熔断、人工审批一致，后者与之相悖。

# 代码层全面审计（2026-11-13）

> 方法：云鼎三层扫描（危险模式 → 深度分析 → 供应链）+ AST 结构分析（超长函数、
> 循环内查询、跨文件重复）+ code-vuln-crossreview 双视角，覆盖 src/soapbot 全部
> 160 文件 47,801 行。既有静态门禁（ruff / mypy 棘轮 / 安全边界 89 项 / 插件 IPC
> 67 项 / 测试断层）作为基线不再重复。

## 结论

**0 P0（安全）/ 0 P1（正确性）**。结构健康：无危险模式、无 N+1、无死代码集群、
索引覆盖完整。可优化的都是 P2/P3 维护级项，逐条列在文末。

## 逐类判定

| 扫描类 | 命中 | 判定 |
| --- | --- | --- |
| 远程执行 / shell=True / pickle.loads / yaml.load | 0 | — |
| md5/sha1（3 处） | wbi.py（协议要求的请求校验和）、skills.py ×2（文件名去重摘要） | 合理：均非安全原语，前者有注释声明 |
| verify=False（1 处） | net/client.py 的 docstring「从未禁用 TLS，测试钉死」 | 合理：防御声明非实际使用 |
| 循环内 await execute（7 处） | 启动期 PRAGMA/迁移、scene.py 2 次迭代、错误清理 | 均非热路径，无 N+1 |
| 跨文件 15 行重复 | providers openai_compat/ollama 的 import 块 | 误报：import 天然相同 |
| 索引覆盖 | messages(session_key+created_at 组合)、分层过滤列 | 完整 |

## 维护级优化清单（按优先级）

| 优先级 | 项 | 说明 | 建议 |
| --- | --- | --- | --- |
| P2 | 装配函数超长 | `create_app`（340 行）/ `build_runtime`（259）/ `build_pipeline`（213）是编排函数，文档密度高、行为正确 | 拆分风险大于收益（测试已锁定行为）；等下次功能性改动时顺手按段抽取 |
| P2 | ModelStage.run（182 行） | 热路径（每次回复），混合了 prompt 组装与流式处理 | 流式分支拆 `_stream_reply` 已存在；组装部分可在下次管线改动时拆 |
| P3 | loader.load（195 行） | 插件生命周期：discover→approve→load 三阶段集中在单函数 | 各阶段已有独立方法；只差把顺序编排抽出 |
| P3 | 长会话交接语义 | auto-chat 攒状态的 worker 重启行为（reference-ops-handoff.md 吸收 1） | auto-chat 0.3.0 行为说明 |
| P3 | 假完成识别 | 审批记录加 done_at（reference-ops-handoff.md 吸收 2） | 面板侧下批 |

## 明确不做

- 拆 `create_app`/`build_runtime` 为多个小函数：行为被 2,273 项测试锁定，纯结构
  搬移的回归风险大于可读性收益；在下次功能改动触碰这些函数时按段抽取。
- 修 mypy 至 0：棘轮语义是「不许增长」，为归零而大量加注解会让真正的问题被淹没。

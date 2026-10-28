# 参与开发

## 环境

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
source .venv/bin/activate     # Linux / macOS
pip install -e ".[dev]"
```

前端（仅在你改面板时需要）：

```bash
cd webui && npm ci
```

面板构建产物随仓库提交（`src/soapbot/webui/dist/`），所以**不改前端就不需要 Node**。

## 提交前的门槛

```bash
make check
```

`make check` = `lint` + `contrast` + `test`，与 CI 一致。三项任一失败都不应提交。

单独跑：

| 命令 | 内容 |
|---|---|
| `make test` | pytest 全量 |
| `make lint` | ruff |
| `make fmt` | ruff 自动修复 |
| `make contrast` | WCAG 对比度校验（14 组色对） |
| `make typecheck` | mypy（当前基线非零，尚未作为阻断项） |
| `make deploy-check` | 容器配置静态检查（不需要 docker） |
| `make progress` | 启动进度看板 `http://127.0.0.1:8099/` |

改前端后还要跑：

```bash
cd webui && npm run typecheck && npm run build
```

## 代码约定

### 注释写「为什么」，不写「是什么」

这个仓库里没有「给输入框加个边框」这类注释。注释解释的是**为什么这样做而不是那样**，
尤其是被否决的替代方案。

反例：

```python
# increment the counter
self.metrics["handled"] += 1
```

正例：

```python
# Counters are bumped before publishing so an observer that reads metrics after
# seeing the sent message finds them consistent.
self.metrics["handled"] += 1
```

### 新能力必须有接线测试

「未接线」的能力等于不存在。测试必须驱动**真实入口**（例如 `runtime._on_event`），
而不是只测注册表本身。参照 `tests/test_delivery_wiring.py`。

反例：断言 `TraceStore` 能存数据，但没有任何测试证明 runtime 真的往里写。

### 文档与代码冲突时，改文档并写明理由

不要默默放宽规则。参照 `docs/architecture.md §6.1`：原文规定「配置类写入不做 API」，
后来推翻了这条，做法是把原条目划掉、补一节说明为什么原前提不成立。

### 不假装修了

未验证的写「未验证」并附验证方法。这比声称通过更可信，也更容易在下一轮补上。

## 安全相关改动

触及以下任一处，PR 必须写明攻击面分析：

- `src/soapbot/security/`（令牌、加密、审计）
- `src/soapbot/plugins/`（加载、审批、隔离、安装）
- `src/soapbot/core/stages.py` 的安全阶段（`guard` / `sanitize` / `injection_screen` / `safety`）
- `deploy/`（容器与网络暴露面）

阶段顺序是安全语义，不是可调参数：`STAGE_ORDER` 有漂移测试守着，改动会失败。

## 提交信息

格式：`类型: 一句话`

类型取 `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf`。

正文解释**为什么**，不要复述 diff。修 bug 时写清根因，例如：

```
fix: 追踪页恒为空，因为 observe 回调必须是 async

Pipeline.observe 的回调签名是 Awaitable[None]，首版传入同步函数。
await None 抛错被 pipeline 当作 observer 错误吞掉，于是所有耗时静默丢失，
而端点仍返回 200 与空列表。
```

## 报告问题

安全问题**不要**开公开 issue，见 [SECURITY.md](SECURITY.md)。

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

`make check` 跑 CI `backend` 任务里能在本机跑的全部门禁，任一项失败都不应提交。
只有两项不在其中：`check_secrets.py --committed` 要读 git 历史，`pip-audit` 要联网。
这个差集由 `tests/test_gate_parity.py` 断言——往 CI 加门禁却忘了加进 `make check`，
测试会红。

单独跑：

| 命令 | 内容 |
|---|---|
| `make test` | pytest 全量 |
| `make lint` | ruff |
| `make fmt` | ruff 自动修复 |
| `make contrast` | WCAG 对比度校验（14 组色对） |
| `make check-deps` | `requirements.txt` 与 `pyproject.toml` 是否一致 |
| `make console-encoding` | 打印中文的脚本必须先把流设成 UTF-8（Windows CI 专属故障） |
| `make deploy-check` | 容器配置静态检查（不需要 docker） |
| `make typecheck` | mypy 原始输出（存量错误非零，仅用于查看，不进 `make check`） |
| `make mypy-baseline` | `scripts/check_mypy_baseline.py`：类型错误总数只降不升，基线 80，超过即失败（进 `make check` 与 CI，阻断） |
| `make progress` | 启动进度看板 `http://127.0.0.1:8099/` |

改前端后还要跑：

```bash
cd webui && npm run typecheck && npm run build
```

## 分支与合并：走 PR，不直推 master

`master` 有分支保护：必须通过 pull request，且 5 个必需状态检查全绿才能合并。
2026-11-09 有一次直推绕过它（GitHub 允许管理员 bypass），事后看，那条保护只是被跳过
而不是被遵守——「已保护」于是变成一句注释。所以流程写在这里，作为默认而不是建议：

```bash
git switch -c feat/short-description          # 1. 开分支，不碰 master
# …改动、make check…
git push -u origin feat/short-description      # 2. 推分支
gh pr create --fill --base master              # 3. 开 PR
gh pr checks --watch                           # 4. 等 5 个检查全绿
gh pr merge --squash --delete-branch           # 5. 合并并删分支
```

五道必需检查（读自 `branches/master/protection`，不是凭印象）是
`backend (ubuntu-latest, 3.12)`、`backend (windows-latest, 3.12)`、`frontend`、
`desktop`、`package`。`types` 是咨询性类型检查、`desktop-bundle` 按需触发，两者都不在
必需列表里。

### 单人维护时的 review 要求

保护规则还要求 1 个批准。仓库只有一个人时 GitHub 不允许自己批自己，PR 会停在
`REVIEW_REQUIRED`，`gh pr merge` 被拒：

```
X Pull request #N is not mergeable: the base branch policy prohibits the merge.
```

这时用管理员的 `--admin`：

```bash
gh pr merge <N> --admin --squash --delete-branch
```

`--admin` 只跳过 review 这一项：PR 存在、5 个检查全绿、diff 与检查结果都留在 PR 里。
它和直推 `master` 不是一回事——直推把 PR 和检查一起跳过了。等有第二个维护者时，
`required_approving_review_count` 保持为 1，`--admin` 就不该再用。

为什么不允许直推：

- bypass 一次之后，规则的存在与不存在没有区别，下一个人也只能靠自觉；
- PR 把 diff、检查结果和讨论放在同一处，回滚时能找到「为什么」；
- Windows 的差异只有 CI 的 `windows-latest` 能跑出来，本地绿不等于能合并。

发布走 tag，不手工上传：

```bash
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/ci.yml` 的 `release` job 会把 wheel 与未签名安装包挂到 GitHub
Release 上。

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

## 依赖更新

四个 ecosystem（pip、`webui/` 的 npm、`desktop/src-tauri` 的 cargo、github-actions）每周
检查一次，配置在 `.github/dependabot.yml`，每条规则的理由写在文件注释里。

读一个 Dependabot PR 的顺序：

1. **看 group**。`python-minor-and-patch` 与 `panel-minor-and-patch` 把 minor/patch 打成
   一个 PR，一次 CI 覆盖全部；`cargo` 与 `github-actions` 各自独立。
2. **major 不会自动来**。`ignore: version-update:semver-major`：major 需要人先读
   changelog，所以它应该是 issue，不是 bot PR。`github-actions` 例外，它的 major 通常
   只是运行时升级、输入不变。
3. **合并看 CI**。`backend` 两个平台 + `frontend` + `types` + `desktop` 全绿。
   2026-11-08 的 `#18`（16 个包）在 Windows 上红过一次，根因是 `.env` 旁路锁的字节
   竞态，与依赖无关；修完之后同一组包在两个平台都通过。
4. **合并后本地跑一次全量**。CI 跑的是同一套，但本地能立刻看到新增的 warning。

想确认「升级后是否兼容」而不动主环境：

```bash
python -m venv /tmp/pin-check
/tmp/pin-check/bin/pip install -r requirements.txt
# 再装测试依赖，版本取自 pyproject.toml 的 dev extra
/tmp/pin-check/bin/pip install "pytest==9.2.0" "pytest-asyncio==1.4.1.post1" \
    "pytest-timeout==2.4.0" "respx==0.23.1"
PYTHONPATH=src /tmp/pin-check/bin/python -m pytest -q
```

`requirements.txt` 与 `pyproject.toml` 的一致性由 `make check-deps` 保证，两者不一致
CI 会红。

## 报告问题

安全问题**不要**开公开 issue，见 [SECURITY.md](SECURITY.md)。

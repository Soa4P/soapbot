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

## 分支与合并：所有权、审批与绕过

### 谁能做什么

| 角色 | 直推 `master` | 开 PR | 人工批准 | 合并方式 |
|---|---|---|---|---|
| 仓库所有者（`admin`） | 允许 | 需要留痕或 AI 审查时 | 不需要 | 直推，或 `gh pr merge --admin --squash` |
| 其他人（`write` / `maintain`，含被授予审批权的人） | 禁止 | 必须 | 必须由他人批准 | 普通 `gh pr merge --squash` |

规则由仓库 Ruleset 执行，不是靠自觉：

- **提交者不能自批自合**：启用 `require_last_push_approval`（最后一次推送必须由他人批准），
  自己提交的 PR 既不能自己批准，也不能自己强制合并。
- **绕过权限绑定 `admin` 角色，不绑定某个人**。GitHub Ruleset 的 `bypass_actors` 只接受
  角色 / team / App，而本仓库挂在个人账号下、没有 team 可建，无法按 user id 锁定。
  当前全仓只有所有者是 `admin`、`Cossiant` 是 `write`，所以效果就是「仅所有者可绕过」。
- **新增协作者最高给 `maintain`**。给 `admin` 等于把直推权一起给出去了；`maintain`
  可以审别人的 PR，但自己的 PR 仍然要别人批准。
- 所有者的直推路径**不产生 PR，因此也没有 PR 上的 AI 审查记录**。需要 AI 审查或留痕时，
  走 PR + `--admin` 合并，结论留在 PR 里可查。
- `--admin` 只跳过人工批准这一项，**不得用来跳过红色检查**。

### 贡献者与其他维护者的流程

```bash
git switch -c feat/short-description          # 1. 开分支，不碰 master
# …改动、make check…
git push -u origin feat/short-description      # 2. 推分支
gh pr create --base master --body-file pr-body.md   # 3. 开 PR，正文按模板四节写
gh pr checks --watch                           # 4. 等必需检查全绿
gh pr merge --squash --delete-branch           # 5. 由他人批准后合并
```

**不要用 `--fill`**：它用 commit message 填 body，模板四节一个都不会出现。
正文用 `--body-file` 传入，十几行就够，结构见 `.github/pull_request_template.md`；
不传 `--body` 时 `gh` 会打开编辑器并带上模板。

### PR 标题与正文

标题一行中文「动作: 对象」：

```
新增安全加固: 语义授权取舍与完整性信号
修复: Windows 重启后保留登录令牌
```

正文四节：作用的模块（仅英文小写）、为什么、提交前确认、Agent 参与声明。
检查项是普通列表，不是复选框；不要放表格。

### 六道必需检查

六道必需检查（读自 `branches/master/protection`，不是凭印象）是
`backend (ubuntu-latest, 3.12)`、`backend (windows-latest, 3.12)`、`frontend`、
`desktop`、`package`、`review`。`types` 是咨询性类型检查、`desktop-bundle` 按需触发，
两者都不在必需列表里。

AI 审查的 `review` job 在 `AI_REVIEW_MODE=observe`（默认）下只评论、只打标签，job 恒绿；
切成 `block` 后 verdict 不是 `safe`、或评论是降级结论时它会让 job 失败，而 `review` 已是
必需检查，所以失败就是真的合不了。那个开关是**仓库变量**，不是代码——改它不需要 PR，
也不需要重新跑测试。

它的结论写在 PR 评论里（固定带 verdict 与 risk）：`safe` 之外都要人读一遍。评论说
「模型返回空内容」时，说明这一轮审查**没有发生**，别把评论的存在当成审查通过。

`review` **已经是必需检查**（2026-11-10 加入）。六个 context 一个都不能少，否则等于悄悄
取消那项检查——所以先读、再写、写完回读：

```bash
gh api repos/:owner/:repo/branches/master/protection/required_status_checks \
  --jq '{strict:.strict, contexts:.contexts}'          # 1. 先读

gh api -X PATCH repos/:owner/:repo/branches/master/protection/required_status_checks \
  -F 'strict=true' \
  -f 'contexts[]=backend (ubuntu-latest, 3.12)' \
  -f 'contexts[]=backend (windows-latest, 3.12)' \
  -f 'contexts[]=frontend' -f 'contexts[]=desktop' -f 'contexts[]=package' \
  -f 'contexts[]=review'                               # 2. 再写（整体替换）

gh api repos/:owner/:repo/branches/master/protection/required_status_checks \
  --jq '.contexts'                                     # 3. 回读，必须 6 个
```

必须是 `PATCH` 不是 `PUT`：2026-11-10 实测 `gh api -X PUT` 在这个端点上返回 404，
`PATCH` 成功，**原因未查明**（不写成「因为它会先读一次」——那是推测，不是证据）。
不管原因是什么，下面的做法都成立：先单独读、再整体写、写完回读。回滚是同一份列表
去掉 `review`，用 `PATCH`。

一条代价要先知道：`pull_request_target` 工作流一旦 `startup_failure`（0 秒失败、无日志），
`review` 这个必需检查就永远不会上报，该 PR 会被卡死，只能改工作流或临时调整保护规则来解。
这不是假想——2026-11-09 发生过一次（run `42654474652`）。`tests/test_ai_review_workflow.py`
就是为了让这类语法错误在本地就暴露，但它替代不了 `actionlint`。

### 所有者强制合并

保护规则要求 1 个批准。PR 由你自己的账号开出时，GitHub 认为提交者就是你，无法自批，
PR 会停在 `REVIEW_REQUIRED`：

```
X Pull request #N is not mergeable: the base branch policy prohibits the merge.
```

所有者用 `--admin`：

```bash
gh pr merge <N> --admin --squash --delete-branch
```

`--admin` 只跳过人工批准：PR 存在、6 项检查全绿、diff 与结果都留在 PR 里。
它和直推 `master` 不是一回事——直推不留 PR 记录，也不会跑 PR 上的 AI 审查。
检查红的时候先修问题，`--admin` 不是跳过检查的工具。

### 为什么其他人不允许直推

- bypass 一次之后，规则的存在与不存在没有区别，下一个人也只能靠自觉；
- PR 把 diff、检查结果和讨论放在同一处，回滚时能找到「为什么」；
- Windows 的差异只有 CI 的 `windows-latest` 能跑出来，本地绿不等于能合并；
- 自己批自己等于没有批准，所以 `require_last_push_approval` 必须开着。

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
3. **合并看 CI**。必需的六个检查全绿：`backend` 两个平台、`frontend`、`desktop`、
   `package`、`review`。`types` 红了也要修，但它是咨询性的，不拦合并。
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

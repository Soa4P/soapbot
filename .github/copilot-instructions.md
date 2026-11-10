# 仓库说明（给 AI 助手）

这份文件是给 GitHub Copilot、以及其他读仓库上下文的编码助手看的。它不复述架构
（那是 `docs/architecture.md`），只写「在这个仓库里做改动时，什么算对」。

## 项目是什么

一个单进程的 QQ 机器人：FastAPI 后端 + Vue 面板 + 可选插件 + 可选 MCP 服务器。
Python 3.12，依赖全部 pin 到 patch 版本。面板构建产物随仓库提交
（`src/soapbot/webui/dist/`），所以不改前端就不需要 Node。

## 硬性规则

**不假装修了。** 没验证的写「未验证」并附验证方法。这不是措辞要求：仓库里有多处
注释、文档和测试专门记录「这个能力没有实测过」，例如 `docs/deploy-quickstart.md` 里
桌面端签名的状态。写「已支持」而没有证据，是这个仓库最严重的错误。

**注释写「为什么」，不写「是什么」。** 尤其是被否决的替代方案。参照
`src/soapbot/core/config_write.py` 里 `_acquire_windows_lock` 的注释。

**新能力必须有接线测试。** 断言注册表能存数据不算；必须驱动真实入口。参照
`tests/test_delivery_wiring.py`。

**升级依赖或改门禁时，同步文档里的数字。** 全量用例数写在
`docs/verification-matrix.md`、`docs/delivery-readiness-v2.md`、`docs/architecture.md`
和 `docs/progress/progress.json`。`tests/test_doc_test_counts.py` 与
`scripts/check_test_gaps.py --strict` 会抓不一致，但先改对更快。

## 不要做的事

- **不要直推 `master`。** 分支 + PR，等 6 个必需检查（`backend` 两个平台、`frontend`、
  `desktop`、`package`、`review`）。其中 `review` 是 AI 审查，不是可选建议——它变红同样
  合不了。名单以 `CONTRIBUTING.md` 为准。
- **不要放宽断言来让测试变绿。** 如果测试固化了一个错误行为，改测试并写清为什么
  （例如 `tests/test_install_scripts.py` 曾断言过 `docker compose up -d` 这个坏命令）。
- **不要在 `detail` 或日志里放凭据。** 审计层会脱敏，但不要依赖它。
- **不要把 `data/`、`.env`、`desktop/src-tauri/binaries/` 提交进仓库。** 它们是运行时
  数据或构建产物。
- **不要引入新的运行时依赖**，除非明确要求：`check_deps.py` 要求
  `pyproject.toml` 与 `requirements.txt` 的 15 个 pin 一致。

## 常用命令

```bash
make check                 # 本机能跑的 CI 静态门禁
python -m pytest -q        # 全量（Windows 上约 6–10 分钟）
python scripts/check_desktop.py
python scripts/check_test_gaps.py --strict
```

## 平台差异

Windows 有独立的代码路径（进程锁、控制台编码、任务计划）。CI 的 `backend` job 在两个
平台都跑，本地只在 Windows 绿是**不够**的。反过来，`desktop-bundle` 只在
`windows-latest` 上跑，Linux 上无法验证。

## 安全相关

`src/soapbot/security/`、`src/soapbot/plugins/`、`core/stages.py` 的安全阶段、
`deploy/` 的改动需要攻击面分析，见 `CONTRIBUTING.md` 与 `docs/security-model.md`。

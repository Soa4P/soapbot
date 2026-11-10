> 不适用的小节直接删掉，不要留空——空小节会让下一个人以为检查过，而其实什么都没写。

## 改了什么

<!-- 一句话说清这个 PR 解决什么问题。不要复述 diff。 -->

## 为什么

<!-- 根因或需求来源。修 bug 时写清是哪个假设错了、怎么发现的——
     下一个人回滚之前会先读这一段。 -->

## 影响面

<!-- 逐项回答，不涉及就写「不涉及」。空着等于没答。 -->

| 维度 | 说明 |
| --- | --- |
| 兼容性 | 公开 API / CLI 参数 / 配置文件格式是否变化 |
| 数据迁移 | 是否需要迁移已有数据（数据库、归档、缓存） |
| 配置变更 | 新增或改名的环境变量、仓库变量、工作流开关 |
| 依赖变更 | `pyproject.toml` / `requirements.txt` / `webui/package.json` / cargo |
| 是否需要重启 | 部署后是否必须重启进程或容器才生效 |

## 验证

<!-- 贴实际跑过的命令与结果。没验证的写「未验证」并说明怎么验证 —— 见 CONTRIBUTING
     的「不假装修了」。 -->

| 项 | 结果 |
| --- | --- |
| `make check` | |
| 全量 `pytest -q` | |
| 静态门禁（`ruff` / `check_test_gaps --strict` / `check_doc_links`） | |

`make check` 未整体跑过时必须在这里写原因：`check_secrets --committed` 要读 git 历史、
`pip-audit` 要联网，这两项不在本机 `make check` 范围内。

## 数字基线

<!-- 新增或删除测试会改变全量通过数。以下位置必须同步，漏一处就会自相矛盾。
     本 PR 没有改变测试数量时写「无变化」。 -->

- [ ] `docs/verification-matrix.md`（两处）
- [ ] `docs/delivery-readiness-v2.md`（两处）
- [ ] `docs/architecture.md`
- [ ] `docs/progress/progress.json`（含 `updated_at`）

## AI 审查

<!-- ai-review 工作流的结论。贴 verdict 与 risk 原文，不要改写。 -->

| 项 | 值 |
| --- | --- |
| verdict | |
| risk | |

评论是 `degraded` 或 `needs_review` 时，写清人工复核了什么、结论是什么。
`AI_REVIEW_MODE=block` 下 verdict 非 `safe` 会阻断合并，不是建议。

## 安全影响

<!-- 触及 src/soapbot/security/、src/soapbot/plugins/、core/stages.py 的
     guard/sanitize/injection_screen/safety、或 deploy/ 时必须填：攻击面是什么，
     这个改动扩大还是缩小它。不涉及时写「不涉及」。 -->

## 回滚

<!-- 一行命令，或「无状态变更」。写不出回滚方式的改动不该合。 -->

## 检查

<!-- 每条都要勾。不适用的小节请整节删掉，不要留空——空小节会让下一个人
     以为检查过，而其实什么都没写。 -->

- [ ] 走的是分支 + PR，没有直推 `master`
- [ ] 新增能力有接线测试（驱动真实入口，不只测注册表本身）
- [ ] 文档与代码冲突时改的是文档，并写明了理由
- [ ] 未验证的部分标了「未验证」，没有写成「已支持」
- [ ] 数字基线四处已同步（或写明「无变化」）
- [ ] AI 审查结论已读过，降级情况已写明人工复核范围
- [ ] 回滚方式已写明

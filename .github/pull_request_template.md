> 不适用的小节直接删除，不要留空——空小节会让下一个人以为检查过，而其实什么都没写。
> PR 标题请写清「新增/修复 + 内容」，例如：`修复：Windows 重启后保留登录令牌`。

## 该 PR 作用的地图（仅英文小写）

<!-- 例如：auth_token / provider / plugin / deploy_windows；没有就写 none。 -->

## 改了什么

<!-- 一句话说清这个 PR 解决什么问题。不要复述 diff。 -->

## 为什么要增加/修改这个东西

<!-- 根因或需求来源，用普通人能看懂的话写：谁遇到什么问题，改完后会怎样。
     修 bug 时写清是哪个假设错了、怎么发现的——下一个人回滚之前会先读这一段。 -->

## 用户怎么使用

<!-- 如果是用户可见改动，给出复制即可执行的命令或面板操作；没有就删除本节。 -->

## 影响面

<!-- 逐项回答，不涉及就写「不涉及」。空着等于没答。 -->

| 维度 | 说明 |
| --- | --- |
| 兼容性 | 公开 API / CLI 参数 / 配置文件格式是否变化 |
| 数据迁移 | 是否需要迁移已有数据（数据库、归档、缓存） |
| 配置变更 | 新增或改名的环境变量、仓库变量、工作流开关 |
| 依赖变更 | `pyproject.toml` / `requirements.txt` / `webui/package.json` / cargo |
| 是否需要重启 | 部署后是否必须重启进程或容器才生效 |

## 破坏性变更

<!-- 配置、数据库、API、插件接口、启动方式是否变化；没有就写 none。 -->

## 安全影响

<!-- 触及 src/soapbot/security/、src/soapbot/plugins/、core/stages.py 的
     guard/sanitize/injection_screen/safety、或 deploy/ 时必须填：攻击面是什么，
     这个改动扩大还是缩小它。不涉及时写「不涉及」。 -->

## 在提交 PR 前确认已经完成以下工作

- [ ] 我已经阅读了 `CONTRIBUTING.md` 和相关文档。
- [ ] 我已经在干净环境或目标平台验证了改动。
- [ ] 我已经补了回归测试，或说明为什么不需要测试。
- [ ] 我已经检查没有提交 API Key、令牌、私钥或服务器地址。
- [ ] 我已经确认文档中的命令、配置项和模型 ID 与当前代码一致。
- [ ] 我已经确认本 PR 只包含与标题相关的改动。

## 验证结果

<!-- 写实际执行过的命令和结果；没有执行的明确写「未验证」，并说明怎么验证。 -->

```text
命令：
结果：
```

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

## 回滚

<!-- 一行命令，或「无状态变更」。写不出回滚方式的改动不该合。 -->

## Agent 参与声明

<!-- 没有 AI/Agent 参与就写 none；有则写名称和实际使用的模型，例如：Claude Code（Claude Opus 4.5）。 -->

none

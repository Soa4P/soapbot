# 记忆分层

原来的记忆只有一层：`messages` 全文加 `memories` 里抽取出来的条目。够用，但回答不了
「刚刚发生了什么」和「我上次是怎么处理的」这类问题——它们不是同一种东西。

现在分成四层，加一条时间线。

## 四层各自是什么

| 层 | 表 | 写的人 | 能不能丢 |
|---|---|---|---|
| L0 原文 | `messages` | 流水线 | 不能。append-only，压缩不碰它 |
| L1 会话摘要 | `summaries` | 压缩 | 能。删掉可以从 L0 重算 |
| L2 长期事实 | `memories`（`layer=semantic`） | 抽取器 | 能。只标记 `archived`，不删行 |
| L3 产物索引 | `memory_artifacts` + `data/artifacts/` | 生成产物的一方 | 索引能重建，正文丢了就没了 |
| L4 selfNote | `memory_self_notes` | 压缩或人格成长 | 能。上限 40 条，按时间淘汰 |

L2 没有单独建表。`memories` 已经有 `importance`、`accessed_at`、`access_count`，
再建一张 `memory_facts` 只会让「哪张表才是长期事实」变成一个需要记住的约定。这次只加了
一个 `archived` 列：退役不删除，因为删掉之后「上月它为什么相信这个」就查不出来了。

L3 的正文不放数据库。放进 SQLite 会让库无限增长，而且截断的文件和丢失的文件在库里
长得一样。现在按 `sha256` 命名、读的时候重新算一遍摘要——对不上就是被改过。

## 时间线

`memory_timeline` 记 `kind`（chat / tool / plugin / artifact）、`ref`、一句摘要、
会话键、时间。目的只有一个：让「最近发生了什么」有唯一答案，而不是去翻三份日志。

**它不复制消息正文。** 记的是「收到 1 条消息（某人）」这种事件摘要。复制正文会造出
第二个需要脱敏的地方，而那个地方通常没人记得。

## 压缩的触发条件

必须同时满足：

- 安静 ≥ `COMPACTION_IDLE_MINUTES`（默认 30 分钟）
- 估算上下文 ≥ `COMPACTION_TOKEN_THRESHOLD`（默认 6000）

只满足前者，一个只有三句话的群也会被压缩；只满足后者，会在对话正热的时候插入一次
额外的模型调用。

顺序是**先出摘要，再落库**。摘要调用失败时什么都不写，所以不会出现「压缩没成功，
但上下文已经被清掉」。写入失败只丢 L1，L0 不动。

## 注入

`RecallStage` 在检索结果前面加三块，各有标签：

```
【会话摘要】…
【自我提醒】…      ← 只在新会话首轮
【近期事件】…
```

分标签而不是揉成一段，是因为模型会把它们当成不同性质的证据，运维在流水线追踪里也能
看出某句话来自哪一层。selfNote 只在新会话首轮注入——每轮都注入等于永久多付一份 token。

## 迁移

schema 版本 3 → 4 → 5，走 `memory/migrations.py` 的 forward-only 链路：

- v4：`summaries` 加 `window_start/window_end/model`；`memories` 加 `archived`；
  建 `memory_self_notes`、`memory_timeline`
- v5：建 `memory_artifacts`

`ALTER TABLE` 前会检查表是否存在：迁移测试会在没跑过 `create_all` 的库上驱动这些步骤，
而 SQLite 对不存在的表执行 `ALTER` 是硬错误，不是空操作。

回滚只到「恢复备份」这一层：schema 不支持降级，降级是带额外步骤的数据丢失。

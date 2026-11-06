# 人格成长

这份文档说清一件不太舒服的事：**人格卡不再完全由人写。**

原来的设计里，`ai/persona.py` 的第一段注释写着「persona text is trusted operator
input」。人格卡进 system prompt，用户消息永远不进——这条隔离是防提示注入改写人设的
主要手段。开启自动成长后，这条隔离没有了：模型可以写人格，而且立即生效。

这是有意的选择，不是疏忽。下面写的是剩下还有什么。

## 能改什么，不能改什么

| 字段 | 模型可写 | 原因 |
|---|---|---|
| `system_prompt` | 是 | 人格正文 |
| `style` | 是 | 说话风格 |
| `banned_words` | 是 | 禁词表 |
| `max_reply_chars` | 是 | 回复长度 |
| `id` / `name` | 否 | 改 id 会让群绑定指向空 |
| `enabled` | 否 | 模型不该能把自己关掉或打开 |
| `wake_words` | 否 | 改唤醒词等于改「什么时候插话」 |
| `locale` | 否 | 回复语言是运营决定 |
| `examples` | 否 | few-shot 对话会被当成指令读 |

白名单在 `ai/persona_growth.GROWABLE_FIELDS`，不在路由层。绕过 API 直接调服务也一样。

## 每次写入都是一个版本

写入顺序是：算好新卡 → 落版本 → 再改内存与磁盘。

- 版本表在 `data/persona_history.db`，append-only，`UNIQUE(persona_id, version)`；
- 回滚不是「删除新版本」，而是把旧版本内容当成一次新写入，所以可以回滚回滚；
- 启动时如果卡片文件坏了（手改坏、写一半），会从最近一个能解析的版本重建，并记
  error；不会因为一张卡坏了就起不来；
- 首次启动会给每张已有卡写一条 `actor=system` 的基线，否则「模型动手之前」那个状态
  根本没有版本号可以回。

## 限额

| 项 | 默认 | 说明 |
|---|---|---|
| `PERSONA_GROWTH_ENABLED` | `true` | 关掉后成长接口直接拒绝，历史仍可读 |
| `PERSONA_GROWTH_MAX_CHARS` | `2000` | 渲染后字符数上限 |
| `PERSONA_GROWTH_PER_HOUR` | `6` | 每卡每小时模型写入次数 |

额度只统计 `actor=model` 的写入。基线（`system`）与人工回滚（`operator`）不占额度，
否则第一次成长就把额度用完了。

## 注入不拦，但留痕

写入前会跑一遍 `security/injection.scan_injection()`。命中时不拒绝——拒绝等于把
「全自动」改回「人工批准」——而是把 `flagged=1` 和命中的模式名写进版本行与审计。

面板上这条版本会带标记，点开能看到命中的是哪一类模式。这是「事后能发现」，不是
「事前能拦住」。两者的区别很重要，下面还会说一次。

## 怎么回滚

```bash
# 版本列表
curl -s http://127.0.0.1:6185/api/personas/<id>/versions -H "Authorization: Bearer <token>"

# 某一版的正文与上一版正文（供 diff）
curl -s http://127.0.0.1:6185/api/personas/<id>/versions/3 -H "Authorization: Bearer <token>"

# 回滚到第 1 版
curl -s -X POST http://127.0.0.1:6185/api/personas/<id>/rollback/1 -H "Authorization: Bearer <token>"
```

三个端点都要求 `ADMIN`，因为人格正文就是 system prompt 的第一段。浏览器用 Cookie
会话时，写操作还要带 `X-CSRF-Token`。

## 残余风险

- **提示注入一旦成功，人设会被持久改写。** 版本与 diff 让这件事可发现、可撤销，
  但不能阻止它发生。要阻止，就得关掉 `PERSONA_GROWTH_ENABLED` 或改回人工批准。
- **注入筛查只看模式，不懂语义。** 一句没有触发任何模式的改写，同样可能把「不要
  讨论 X」从人设里删掉。diff 是唯一能看见这种事的地方。
- **每小时 6 次不是安全边界。** 它只防跑飞的循环，不防一次精心构造的写入。

人格卡本身的写法、绑定顺序与编辑方式没变，见 [personas.md](personas.md)。

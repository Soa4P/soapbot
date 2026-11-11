# 变更记录

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

本项目的特殊情况：0.1.0 之前的开发没有逐版本留档，因此下面把「能运行但不构成
交付物」的中间状态合并记为 `0.1.0`，并把本轮修复逐条列出。每一条都写明**原来的
错误表现**，而不是只写「修复了 X」——因为这里的缺陷几乎全部是「组件都在、线没接」，
只写结论会让人以为是从零实现，下次仍会以同样的方式漏掉。

## [Unreleased]

### 多端对话：网页/手机端可以和机器人真正说话了

原来错在哪：存档端点做完后，「多端」只有读的能力——网页和手机上的输入框写的是备注，
永远发不出一条能让机器人回答的消息。原本在 QQ 里完成的「和机器人对话」这件事，在
主力使用的网页端/手机端上不存在；而会话列表还有两个伴随缺陷：首屏加载的是**最早的**
100 条（老会话的中间历史永远看不到），列表拉一次就不再更新（新会话不出现、计数不涨）。

现在：

- **`POST /api/chat/messages`**：构造进程内消息交给 `runtime.dispatch`，与 QQ 消息过
  同一条管线（Guard → 注入检测 → 白名单 → 限频 → 人格 → 模型 → 回复落库）。端点不持有
  适配器引用，回复由 `PersistReplyStage` 在 `send_ok` 后落库，SSE 自动送达客户端。
  session_key 由服务端推导为 `web:private:account-<id>`，请求体里没有身份字段；
  `account-` 前缀保证永不与 owner/admin 名单里的纯数字 QQ 号撞车
  （`normalize_id` 对字母前缀保形）。
- **逐个授权**：账号必须有自己的 membership 行（owner 豁免），无授权与读路径一样 404。
  `WhitelistStage` 的 web 分支锚定在进程内适配器名上，QQ 私聊默认拒绝原样保留，
  `tests/test_chat_talk.py` 有 QQ 侧仍然拒绝的对抗用例。
- **开关 `SOAPBOT_CHAT_TALK_ENABLED`**（默认 false，改后需重启——web 适配器启动时注册），
  关闭时发送端点 404；`/api/chat/surfaces` 新增 `talk` 键。
- **新适配器 `adapters/web.py`**：capabilities 只有 TEXT/REPLY（语音自动降级为文本），
  `send()` 不写库（`PersistReplyStage` 会写，写两次等于每条回复存两行）。
- **历史翻页**：`GET /api/chat/messages` 新增 `latest`（最新一页）与 `before_id`（向前
  翻）两种模式，响应带服务端探测的 `has_older`；三种模式互斥，同时给返回 400，
  `after_id` 原语义不动。网页端与手机端首屏改为最新一页，消息区顶部有「加载更早」，
  空白消息在端点被 400 拒绝（POST 直进 dispatch，绕过了 `_on_event` 的 blank 检查，
  这条是补上的）。
- **会话列表自动刷新**：网页端 30 秒轮询（保留选中态），手机端 30 秒定时器 + 从聊天页
  返回时刷新。
- **第 15 页「账号与邀请」**：账号列表、停用/启用、签邀请码（明文一次性显示 + 复制）、
  授权会话——「与机器人对话」按钮一键预填 `web:private:account-<id>`。此前这些操作
  只有 API，文档自己承认「面板上还没有这一层按钮」。页面编号按「只追加、永不重排」
  规则落到 15（14 已被存档登录页占用），面板页数口径 13 → 15。
- **手机端**：`sendMessage`/`talkEnabled`/翻页参数进 `client.dart`，聊天屏对自己的
  web 会话显示发送框（其余会话仍是备注按钮），列表屏 30 秒刷新。**仍未在真机构建验证**
  ——本机没有 Flutter SDK，这是本轮已知未验证项。
- **测试**：`tests/test_chat_talk.py` 10 项（flag 404、无适配器 503、无授权 404、
  owner/成员对话、halted 429、内容边界、白名单对抗）、`tests/test_chat_api.py` 6 项
  翻页用例、webui `ChatView.spec.ts` 5 项 + `AccountsView.spec.ts` 4 项。

### 接入层只有一个身份：拿到令牌的人能看到一切

原来错在哪：前 41 轮把机器人本体做完了，接入层却始终是「一条 `init_token` 就是 operator」。
`TokenService.issue("operator")` 固定签发同一个角色，`messages` 表有会话列和两个索引，却
**没有任何按会话授权的查询，也没有 `/api/chat/*` 端点**。于是「网页优先、手机只读」这件事
没有落脚点：想给第二个人只看某个群，唯一的办法是把面板令牌给他，而他随即能看到全部。

现在：

- **三张表**：`accounts` / `account_invites` / `chat_memberships`。密码用标准库
  `hashlib.scrypt(n=2**14, r=8, p=1)`，salt 与 hash 分列，比较走 `hmac.compare_digest`；
  邀请码只存 SHA-256，明文仅在创建响应里出现一次，一次性、默认 72 小时过期（`hours` 可调，上限 30 天）。三张表声明为
  ORM 模型随 `create_all` 落库，所以是纯增量加表，`SCHEMA_VERSION` 仍是 5。
- **首个所有者必须带 bootstrap token**：`POST /api/accounts/owner`，账号表非空后固定 409。
  「账号表为空」的检查放在写事务**内部**——原先放在外面，两个并发 bootstrap 会都读到 0。
- **会话隔离在 SQL 里**，不是取完 200 条再在 Python 里筛：后者会让只被授权一个冷清群号的
  成员看到空列表，而页面上写的是「还没有被授权的会话」——一个权限问题被伪装成了没数据。
  越权访问未授权会话返回 404 而不是 403，因为 403 会确认「这个会话存在」。
- **消息按 `after_id` 游标增量拉**，不用 offset：归档只在尾部增长，offset 在并发写入时会
  重复或漏行。SSE 是 1.5 秒轮询同一游标的 async generator。
- **输入只写备注**：落库 `role=note`、`adapter=web`、`delivered=false`，整条路径不 import
  适配器——「不发送」由调用图保证，不由注释和提示语保证。
- **端开关**：`SOAPBOT_CHAT_{WEB,APP,DESKTOP}_ENABLED`，默认只有 web 开；全关时
  `/api/chat/*` 返回 404 而不是 403。
- 网页端第 13 页（登录、会话、消息流、备注，移动优先 / 桌面三栏），`mobile/` 只有 Flutter
  源码骨架与构建说明，**未在真机构建**。

同一轮里被打回的三处，都是「测试先绿、真机上无效」的形状：

1. 三个端开关最初用 `os.getenv` 读，而 `.env` 是 pydantic-settings 消费的、**从不写进
   `os.environ`**——运维改 `.env` 会静默无效，测试因为 `monkeypatch.setenv` 反而通过。改为
   读 `Settings`，默认值用例改成构造真实 `Settings(_env_file=None)`。
2. `check_security_boundaries.py` 的 s11 抓住 `detail=str(exc)`：即使当下消息是手写的，这条
   写法会让下一次「把 `repr(exc)` 塞进去」变成零成本。`AccountError` 增加 `.message`，备注的
   `ValueError` 改成固定文案 + 服务端日志。
3. 部署文档写了不存在的 `soapbot serve`（CLI 只有 start/token/doctor/setup/migrate/version），
   `tests/test_cli_documented_commands.py` 直接把这条漂移报了出来。

### 两条「已经写好」的契约，其实都没生效

原来错在哪：两处都是上一轮自己写的，两处都没测到自己写的那句话。

**一、`review()` 承诺不抛异常，实际会抛。** `_extract_json()` 把 `json.loads` 的结果原样返回，
于是 `"[]"`、`"[1, 2]"`、`"\"safe\""`、`"null"`、`"42"` 这些**能解析但不是对象**的响应一路走到
`normalise()`，在 `payload.get(...)` 上抛 `AttributeError`。用改动前的脚本喂这六种载荷，六次全部
`RAISED AttributeError`；照常调 `main()` 则是 `comment.md` 与 `GITHUB_OUTPUT` 一个都没写出来。
后果不只是「少一条评论」：`ai-review.yml` 的步骤顺序是 `Ask the model` → `Comment` → `Label` →
`Enforce`，第一步崩掉后面全跳过，PR 上只剩一个没有解释的红叉；而 `review` 是必需检查，这个红叉
直接卡住合并。`Enforce` 被刻意放到最后就是为了避免这种情形，结果被一个模型很容易产出的返回形状
绕过去了。`README.md` 当时写着「返回非法 JSON 一律降级」——`[]` 是合法 JSON，这句话不成立。

**二、文档门禁查的是「这个词在全文出现过」。** 从 `CONTRIBUTING.md` 的真实名单里逐个删掉名字：
在上一轮合并的那一版（旧门禁 + 旧文档）上，`frontend`、`desktop`、`review` 三项删掉之后仍然报
`NO PROBLEM`，只有两个 `backend` 和 `package` 被抓到——`package` 被抓到纯粹因为它当时全文只出现
一次。而本轮把 225 行改对、让那句也提到 `package` 之后，同一个旧门禁对 `package` 也失去了反应：
四个删除项全部通过。也就是说上一轮「门禁能挡住漂移」只对「整行删掉」成立，对「清单里少一项」不
成立——而后者才是真实事故的形状；更糟的是它的命中依赖「这个词碰巧只出现一次」这种与意图无关的
巧合，改好一句别处的文案就能把最后一个偶然的拦截点也拆掉。同一文件 225 行还躺着第三份更旧的
名单：「`backend` 两个平台 + `frontend` + `types` + `desktop` 全绿」，既把咨询性的 `types` 当成
合并条件，又漏掉 `package` 与 `review`；它不含数量词，旧规则根本看不到它（返回空列表）。

现在：

- `_extract_json()` 解析成功后校验必须是对象，失败抛 `ReviewError`，消息区分「不是 JSON」与
  「是 JSON 但不是对象」——两者修法不同，前者是加 token 预算，后者是让 prompt 说清返回对象。
  `normalise()` 同样加了守卫，供直接调用方使用。任意形状的响应现在都是 `needs_review`，
  `comment.md` 与 `GITHUB_OUTPUT` 照常写出。
- `concerns` 不再是「可迭代就当列表」：`for item in "no concerns found"` 会迭代字符，产出 17 条
  单字符关注点，渲染成一串噪音。抽出的 `_normalise_concerns()` 把字符串当成一条保留（那是人写的
  抱怨，只是不合 schema），dict 当一条，上限仍是 20。
- `main()` 在 `review()` 外面留了最后一道网：意外异常也降级成 `needs_review`，并把异常类型写进
  评论。理由和上面一样——这个步骤红掉等于 PR 上只有一个不说话的红叉；写下 `KeyError` 至少让日志
  指得回真正的 bug。
- 门禁改成三条段落级规则：①必须有某一段同时写下数量和完整名单，失败时点名缺哪一项；②每处写下的
  数量都必须是 6；③含「全绿」的句子若点名了 job，就必须正好是那五个 job 名，多一个 `types` 也报。
  `CONTRIBUTING.md` 225 行据此改写：点名六个必需检查，`types` 单独一句「红了也要修，但咨询性、
  不拦合并」。
- 用例：`tests/test_ai_review.py` 19 → 24 项，`tests/test_required_checks_doc.py` 6 → 9 项。
  两处都补的是「改坏必须红」的用例——`git show HEAD:` 喂同样输入可复现旧行为（6 种载荷全抛、
  6 个删除项漏 4 项、225 行原句返回 `[]`），这是新用例有效的证据，而不再是「跑过了」。

实现被两件事打回，值得记下来：门禁的句子切分原本把换行也当边界，而 225 行恰好在 `desktop` 后
换行，含「全绿」的半句只剩三个名字，误报「漏了 `package`、`review`」；改成先把续行拼回逻辑行
再按句号切。token 原本直接与 job 短名比较，写完整 context 的文档（`` `backend (ubuntu-latest, 3.12)` ``）
匹配不上；改成取 `(` 之前的部分归一。两处都是「规则写对了但切分错了」，靠真实文档才暴露。

### 必需检查的数量只剩一种说法

原来错在哪：`review` 在 2026-11-10 成为第六个必需检查，同一个事实随即在仓库里分裂成三种
写法——`CONTRIBUTING.md` 开头写「6 个必需状态检查」，同一文件里 `--admin` 那段又写「5 个
检查全绿」；`.github/copilot-instructions.md` 告诉 AI 助手「等 5 个必需检查」；`CHANGELOG`
把它描述成「五道必需检查」。第三处是历史条目，写的是当时的事实；前两处描述的是今天，却是
错的，而它们恰好是人和 AI 助手判断「能不能合」的依据。

现有门禁一条都看不见：`scripts/check_test_gaps.py` 只扫 `README.md` 与 `docs/**` 里的
`N passed`，`tests/test_doc_test_counts.py` 扫同一批文件里的按文件计数；`CHANGELOG.md` 与
`.github/*.md` 从来不在扫描范围内——这是既有盲区，不是这一轮新引入的。

现在：三处改成六个并把 `review` 点名（AI 助手的规则里多一句「它变红同样合不了」），
`CHANGELOG` 的历史段改为不写具体数字、只写「名单读自 `branches/master/protection`，`review`
在后续一轮加入」。新增 `tests/test_required_checks_doc.py`（6 项，下一轮补到 9 项——那一轮发现
这 6 项只查「词是否出现在全文」，见本节上方）：`REQUIRED_CHECKS` 六项
是 `gh api` 只读回读的快照，`required_check_doc_problems()` 检查两份当前态文档是否逐项点到、
数量是否写成 6；反向用例用构造文本证明删掉 `review`、写回「5 个」、或干脆一行都不写数量都会
失败。`CHANGELOG.md` 有意排除在外——把「当时只有五道」改写成不含数字的措辞以迎合门禁，方向
是反的，和上一轮给轮次记录加豁免是同一个理由；那条用例同时断言规则确实会拒绝这种历史写法，
否则「被排除」与「本来就通不过」无法区分。

顺带把 `CONTRIBUTING.md` 里「`PUT` 会先读一次，读不到就 404」降级为「实测返回 404，原因
未查明」：前半句是推测，不是证据。可复验的部分（`PATCH` 可用、整体替换、写完回读）保留。

### AI 审查不再「每次都在、每次都说不出话」

原来错在哪：`review` job 一直是绿的，评论却固定是同一段降级文案。PR #24 与 #25 的评论
逐字相同：`finish_reason=length, reasoning_tokens=3000, completion_tokens=3000`。
`deepseek-flash` 是 reasoning 模型，`completion_tokens` 包含隐藏推理，脚本里硬编码的
`max_tokens: 3000` 全被推理吃光，`content` 为空；`review()` 按 fail-closed 降级成
`needs_review`。于是「job 通过」和「审查发生」变成了两件事，而 PR 页面只看得出前者。

现在：单次预算提到 8000；只在「`finish_reason=length` 且内容为空」时用 16000 重试一次。
这是唯一值得重试的失败——HTTP 401/403/429、超时、响应体不是 JSON、JSON 字段非法，重试
只会重复同一个错误并多花一分钟。两次都空时评论写明「已用 8000 与 16000 两次预算，均被
推理耗尽」，附 `reasoning_tokens`，下次是改模型还是继续加预算有数据可依。判断不了一律
仍是 `needs_review`，重试不会让结论变成 `safe`。

### `AI_REVIEW_MODE` 从死变量变成真开关

原来错在哪：仓库变量 `AI_REVIEW_MODE=observe` 存在，但 `ai-review.yml` 从未引用它。
一个没人读的开关比没有开关更糟——它让人以为改了就生效。

现在：`observe`（默认）只评论、只打标签，job 恒通过；`block` 在 verdict 非 `safe` 或
评论是降级结论时让 job 失败。判定步骤 `Enforce review mode` 是**最后一个** step：放在
评论之前的话，block 模式下 job 一失败就没有评论，PR 上只剩一个没有原因的红叉。

### 工作流与 PR 模板变成可校验项

原来错在哪：2026-11-09 有一次 `startup_failure`（0 秒、无日志），`make check` 完全看不
见；模板改了也可能不生效，因为 `CONTRIBUTING.md` 教的是 `gh pr create --fill`，而
`--fill` 用 commit message 填 body、直接覆盖模板。

现在：`tests/test_ai_review_workflow.py`（16 项）。前 7 项解析 YAML，钉住 checkout 必须是
`pull_request.base.sha`、持有密钥的 job 里不得出现 `pip install`/`npm install`/`npm ci`、
`AI_REVIEW_MODE` 被读取且 observe 是默认、`Enforce` 排在 Comment/Label 之后且为最后一步、
未知模式值（`MODE=Block` 这类拼写）也 fail-closed 而不是静默落进 observe。后 9 项不是
「再读一遍 YAML」——读 YAML 只能证明文本里有 `block` 这个词，证明不了退出码对。它们用
真实 bash 执行 `Enforce` 的 `run:` 块本身，参数化断言 8 种 mode/verdict/degraded 组合的
退出码（observe 恒 0；block 下 needs_review/malicious/degraded 为 1；`Block` 与空串这类
拼写错误也为 1），外加一条断言失败时必然先打印 `mode=/verdict=/degraded=` 与 `::error::`。
`tests/test_pr_template.py`（12 项）钉住模板九个小节（改了什么/为什么/影响面/验证/数字
基线/AI 审查/安全影响/回滚/检查），逐节删除都会失败，并禁止 `--fill` 回归。

一个曾经成立、现在已被现实推翻的限制：这一轮的 PR 自己的 `ai-review` 跑的是 master 上的
旧脚本（工作流按设计 checkout `base.sha`，这正是安全模型要的），所以当时把端到端证据记为
**未验证**。合并后的第一个 PR（#27）推翻了这个结论：它的评论第一次给出真实结论
（`未发现问题`、risk `low`），8000 那一档就够，没有用到 16000 重试。`checkout base.sha`
这条约束本身仍然成立——改脚本的 PR 仍然跑旧脚本，只有合并后的下一个 PR 才是验收对象。

### 数字门禁不再把轮次记录钉到今天

原来错在哪：`check_test_gaps.py` 的 `stale_totals()` 逐行扫 `N passed`，而
`verification-matrix.md`（被列为 `LIVE_DOCUMENTS`，因为它的头部数字确实是当前态）里同时
记着每轮的增量，例如「全量 1884 → 1892 passed / 12 skipped」。看板一前进到 1902，这条
上一轮的记录就变红；上一轮只能把句子改写成不含 `passed` 的措辞来绕过门禁——为了让
检查通过而去改历史记录，方向是反的。

现在：`ROUND_CHANGE` 只豁免「整数 → 整数 + `passed` / `项通过`」这一种明确的轮次变化
写法。裸的当前态声明（`1902 passed, 12 skipped`）没有箭头、基准数据
（`39.7ms → 19.6ms`）两边带单位，都继续被检查；`round_report_lines()` 把每条被豁免的
行以 `文件:行号` 打印出来，避免规则静默失配。`stale_totals(root)` 支持注入目录，错误
路径也不再用 `Path.relative_to`（在 `tmp_path` 下会抛异常而不是报问题）。上一轮被迫改掉
的 ph35 轮次行已恢复成自然写法，成为真实覆盖点。

新增 `tests/test_gate_round_reports.py`（6 项）：历史行豁免生效、当前态总数与跳过数失真
仍报、裸旧数字与基准箭头不被豁免、真实文档里至少匹配到一条轮次记录。另在真实文件上做
了端到端改错复验：把 `architecture.md` 的 `1902 项通过` 临时改成 `1901`，`--strict`
返回 1 并精确指出 `docs/architecture.md:234`，随后字节级还原、diff 为空。

### 记忆与 RAG 向量检索批量化

原来错在哪：两个召回通道（`MemoryStore._vector_search` 与 `KnowledgeBase.search`）都把
所有带向量的行用 `select(MemoryRow)` / `select(KnowledgeRow)` 取成完整 ORM 对象——包括
永远不会被读到的 `content` / `keywords` 文本——再在 Python 循环里逐行做
`np.frombuffer` + `np.linalg.norm` + `np.dot`。3000 行就是 3000 次 Python→C 往返，每次
recall 都要付一遍。更麻烦的是两处防护不一致：`MemoryStore` 查 NaN/inf，
`KnowledgeBase` 完全没查，一个坏向量就能让 RRF 排名变成任意顺序；而 `MemoryStore` 把
「余弦 ≤ 0 的正常不相关行」也算进 `dropped` 打 warning，随机语料一次 recall 能刷上千
行日志，真正的坏向量反而被淹没。

现在：`memory/vectors.py` 把打分收敛成一次矩阵乘，两个调用点改成两阶段查询——先只取
`(id, blob, dim)`，算出 top-N 后再按 id 回查展示列；NaN/inf/零范数/维度/blob 长度校验
与稳定排序集中在一处，`KnowledgeBase` 因此自动获得此前缺失的防护。`dropped` 只计坏行，
不相关的正常行单独计 `non_positive`，不再触发告警。`db.py` 里「brute-force 余弦胜过
向量库」的设计决策没有变：仍是全量扫描、同样的余弦、同样的 RRF 排名。

实测（临时基准，3000 行 / 128 维 / limit=24 / 5 轮，同库同数据与旧写法对比）：
median 39.7ms → 19.6ms（约 2x），top-24 结果逐项一致，日志噪音归零。新增
`tests/test_vector_ranking.py`（10 项）：以旧循环为 oracle 逐项比对分数与顺序、并列保持
扫描顺序、坏行与不相关行分开计数、非有限 query、limit 边界、两处接线静态断言，以及
两阶段查询确实回取了完整字段。

一个未归因、但不隐藏的观察：本机本轮三次全量耗时稳定在 680–702s，明显高于上一轮的
236s。加 `--durations=15` 复核后，最慢 15 项合计约 110s 且均不在检索路径，新增 10 项
单独 0.51s，去掉顶层 numpy 导入后总耗时也没有变化；判断是宿主层面的整体变慢，未声称
由本次改动造成，也没有据此放宽任何断言或超时。

### 类型检查门禁的当前态描述对齐

原来错在哪：`check_mypy_baseline.py` 早已接进 `make check` 和 CI 的 `backend` /
`types` 两个 job，是**阻断**门禁，基线也因本地与 CI 差一个错误而从 79 抬到 80；但
`deployment.md` 仍写着「`types` job 里只报告不阻断、降到 0 再改阻断」，`CONTRIBUTING.md`
写「基线 79、尚未作为阻断项」，`operations.md` 的门禁清单整条漏掉它，
`verification-matrix.md` 的复现命令还是原始 mypy 加旧基线。最矛盾的是 `ci.yml`：同一个
`backend` job 上面是阻断的 `Type check (ratchet)`，下面的注释却写着
「mypy is deliberately *not* a gate here ... 79 errors across 31 files」。

现在：这些当前态描述统一改为「棘轮只比较总数、基线取本地与 CI 中较大的 80、两个 job
都阻断」；Makefile 的 help 区分「查看用的 typecheck」与「进 check 的 mypy-baseline」，
注释不再写死错误数；CI 里那段自相矛盾的注释删掉。带轮次语境的历史记录（本文件旧条目、
`progress.json` 的 ph32 note、门禁脚本的 Why-this-exists 段）按既有边界保持原样。

新增 `tests/test_type_gate_docs.py`：把基线值、`make check` 与 CI 两个 job 的接线、以及
四份当前态文档里的过时短语一起变成可失败门禁，逐条反向复验。

### 首次登录令牌指引：从「给个路径」改成「能照着做」

原来错在哪：文档只写 `data/init_token.txt` 或写死 `C:\soapbot\data\init_token.txt`，
`deployment.md` 甚至写着「打印取令牌的命令」却根本没给命令；两个服务化脚本收尾只留
一句英文 `open it on this machine; it is not printed here`，云服务器用户分不清指的是
哪台机器；`start-panel.bat` 反而把令牌值 `type` 出来，这条差异只用「有意保留」一笔
带过。最要紧的是全库没有写「兑换后文件即删除、重启不会重新发放」，于是重启后找不到
文件被当成故障，反复重启也不会变出新令牌。

现在：`docs/deploy-quickstart.md` 的「第一次登录」以 `GET /api/auth/status` 开头，用
服务自己算出的 `bootstrap_path` 与 `bootstrap_state` 区分 available / redeemed，再给
`Get-Content`、一次性兑换、以及 `token --reset` 加 `schtasks` 重启的完整可复制命令；
README / guide / deployment / operations 都指向它，operations 另加「重启后找不到
`init_token.txt`」排障条目。两个服务化脚本改成明确写出 `ON THIS SERVER` 并给出可直接
粘贴的 `notepad "<完整路径>"`，同时说明已兑换后重启不会重发；脚本保持纯 ASCII，避免
Windows PowerShell 5.1 按 ANSI 解析造成中文乱码。`start-panel.bat` 保留打印值，但在
同一屏解释两条路径为何不同、文件不在时意味着什么。

新增 `tests/test_bootstrap_token_docs.py`：把「指引可操作」变成可失败门禁，逐条删掉
状态自查、读取命令、恢复命令、脚本提示或文档指针都会红。

### 安全边界与错误日志治理

运营者提出 18 项风险。逐条核实后：6 项已经解决或不适用（`shell=True`、pickle /
`yaml.load`、`v-html` 渲染用户内容、CORS 通配带凭证、Jinja 渲染用户内容、上传体积
校验），1 项属实（token 存 `localStorage`），其余部分属实。口径是**全量加固**：
18 项每项都要有一条能验证的防线，已解决项用负向静态断言锁住不许退回去，不重复
写第二套实现。

原来错在哪：

- 认证：浏览器把签名 token 存在 `localStorage`，页面里任何脚本都能读走并长期复用；
  `api/auth.py` 对回环请求无条件给 `owner`，77 个管理路由只有「要不要认证」没有
  「谁可以改」。现在会话是 `HttpOnly` + `SameSite` Cookie，写操作另需 CSRF 双提交与
  同源 `Origin`；回环只读降为 `MEMBER`，写操作要凭据；配置写入要求 `ADMIN`，
  撤销全部仍要求 `OWNER`。Bearer 保留给脚本和 CLI。
- 错误：二十多处 `HTTPException(..., detail=str(exc))` 把配置解析错误、插件异常文本
  甚至路径回显到浏览器。现在统一异常分层与状态码映射，响应只给稳定短句加白名单
  类别标签（如 `traversal`、`YAML`、未设置的环境变量名），完整异常进服务端日志。
- 日志：`logging_setup.py` 手工拼 JSON 字符串，用户内容里的换行能伪造出第二行日志；
  日志环存原文；Provider 响应正文经 `last_error` 被管理 API 返回并写进日志环。
  现在用 `json.dumps` 序列化、出口剥离控制字符、`ContextVar` 贯穿 `trace_id` 等定位
  字段、慢调用按阈值告警；Provider 异常只带 `kind + HTTP status`。
- 输入：正则跑在用户可控文本上，执行前没有统一长度上限；上传只查 zip 结构不查
  文件类型；`doc_id` 有四处入口，两处漏了校验。现在分别补上 `bounded_scan()`、
  zip 魔数与后缀白名单、`_require_doc_id()`。标准库 `re` 没有超时参数，长度上限是
  不加依赖时唯一可验证的替代，文档里如实写明它不是硬超时。
- 异常吞没：三处 `except ...: pass` 有注释说明但没有任何动作，改成显式降级日志。

新增 `scripts/check_security_boundaries.py`（84 条不变量，接进 CI 双矩阵与
`make check`）、`docs/security-boundaries.md`（18 项逐条证据）、
`tests/test_security_boundaries.py`、`tests/test_auth_cookie.py`、
`tests/test_logging_hardening.py`、`tests/test_error_mapping.py`。
`deploy/backup.sh` 把命令字符串拼接改成显式函数与引号路径。

参考了 SnowLuma / NapCatQQ / MaiBot 等 23 个仓库，按 5 类生态抽样。学的是把边界
写在哪、把校验放在哪、把恢复写成显式动作，没有搬任何功能、源码或依赖。逐条
「改什么、为什么、不改什么」在 `docs/reference-ecosystem.md`。

README 按四块重写（定位 / 启动 / 边界 / 门禁），安装细节迁到 `docs/guide.md`，
排障与部署迁到 `docs/operations.md`。删掉宣传语，只写事实、命令和取舍。
`tests/test_readme_claims.py` 的环境变量表仍在 `docs/configuration.md`，断言保持。

### 插件进程与 IPC 边界加固

对运营者提出的十项风险做了**逐项核实**，其中六项在当前代码中已经解决，本轮只修真实缺口，
并把「不得回退」固化成 CI 门禁。核实结论：

| 提出的风险 | 核实结果 |
|---|---|
| IPC 用 pickle | 不符：长度前缀 JSON，全仓无 pickle 原语 |
| 能力授权在插件进程内自查 | 不符：父进程 `_handle_callback` + `surfaces.py` + `sandbox.py` 单一授权点 |
| 崩溃无重启/熔断 | 不符：指数退避、窗口内重启预算、熔断且需显式重置 |
| 子进程继承全部环境变量 | 不符：`sanitize_env()` 白名单，仅转发 `SOAPBOT_PLUGIN_*` 前缀 |
| 插件加载路径未校验 | 基本不符：symlink、`resolve().parents`、zip slip、名称正则、manifest digest 均已有 |
| correlation id + 超时 / stdout drain / 进程数 / 僵尸回收 / 消息大小上限 | **部分属实**，见下 |

真实缺口与修复：

- **请求串台**：父端 `invoke()` 收到 `result` 时完全不校验 `id`（子端其实一直回带了 id），
  `call` 帧也不绑定当前请求。现在每次调用生成随机 `rid`，`result.id` 与 `call.rid`
  都要强校验，不匹配即丢弃并计数；未绑定的回调在查 capability 之前就被拒绝。
  `invoke()` 全程持锁，杜绝两个调用交错读同一条管道。
- **帧预算漂移**：父端入站 4 MiB、子端入站硬编码 8 MiB、出站不限。现在
  `isolation.MAX_FRAME_BYTES` 是唯一常量源，以字面量注入两个 `-I` 子脚本；
  父/子入站与出站、一次性 runner 的请求与回包统一受限，错误带「上限 + 实际字节」。
- **stdout 只在调用期间读**：空闲期插件写满管道会把自己阻塞。现在一个常驻 reader
  独占 stdout，帧进入 `asyncio.Queue(maxsize=4)`；队列 0.5 秒无人消费即判定帧洪水并
  杀进程树。
- **进程数无上限**：新增 `SOAPBOT_MAX_PLUGIN_WORKERS`（默认 16，`1..64`，`0` 非法），
  注册与启动双重 fail-closed；容器的 `pids_limit` 退居最后一道兜底。
- **回收不统一**：新增 `proc.wait()` 退出看护（带进程代际守卫），`stop()` 取消并 await
  三个任务，`loader.unload_all()` 与 `app._shutdown()` 都调用幂等 `stop_all()`。
- **子端纵深校验**：两个子脚本都对 boot/请求里的 `plugin_dir` 做 `realpath`、目录存在、
  `main.py` 普通文件且未逃逸根目录、`attr` 合法标识符的复核。
- **一次性 runner 的静默失效**：`_CHILD_BOOTSTRAP._apply_limits()` 引用只存在于宿主模块的
  `DEFAULT_PLUGIN_MEMORY_BYTES`，`NameError` 被裸 `except: pass` 吞掉，资源限制从未生效。
  现在默认值是字面量，其它异常打印到 stderr。

并发交叉审查后追加修复：帧洪水/协议错误时 reader **同步**杀进程并关闭队列（此前
`await self._abort()` → `proc.wait()` 会与 stdout EOF 形成循环依赖，持锁的 `invoke()` 永久挂死）；
所有 `proc.wait()` 加上界；`stop()` 在 `finally` 中无条件回收三个任务；
`PluginSupervisor` 增加生命周期锁使容量检查与建进程原子化，并新增 `unregister()` 在卸载时
释放容量；同一 worker 重入 `start()` 时杀掉旧进程并重置全部代际状态；
一次性 runner 不再用无上限的 `communicate()`，改为按帧有界读取；
启动期回调立即拒绝而不是让 shutdown 等满超时。这些不变量也写进了 `check_plugin_ipc.py`。

新增运维与门禁：`scripts/check_plugin_ipc.py`（离线静态审计，挂进 CI 与 `make check`）、
`scripts/plugin_worker_guard.py`（**只读**巡检，绝不重启）、
`deploy/plugin-worker-guard.{service,timer}`（每 5 分钟）、
`tests/test_plugin_ipc_hardening.py`。

参考 [surfcore](https://github.com/Mieksido/surfcore)、
[qq-dsh-bridge](https://github.com/NoMindSama/qq-dsh-bridge)、
[dsh-bili-humanism](https://github.com/InariNGT-Ofiicial/dsh-bili-humanism) 的治理机制
已落地；人格分层、四层记忆与 selfNote、闲置边界压缩等业务设计**评估后不移植**，
理由见 [DSH 生态参考评估](docs/reference-dsh-ecosystem.md)。

### 新增

- **Windows 双击启动器**：`start-panel.bat`（本地起面板并自动开浏览器）、`stop-panel.bat`、
  `open-remote-panel.bat`（SSH 隧道看服务器上那个实例）。此前"看界面"只能靠手敲
  `python -m soapbot.cli start` 再自己输网址，README 里也只有一行字——面板一直存在，但没有
  任何可点的入口。
- **真实 MCP 服务端接上了**（`tests/test_mcp_live.py`，opt-in：`SOAPBOT_LIVE_MCP=1`）。
  之前所有 MCP 结论都来自一个照着客户端写的假服务端，它能证明的只有「客户端和自己谈得拢」。
  现在接的是第三方的 `@modelcontextprotocol/server-filesystem`：14 个工具、`tools/call`
  真的读回了文件内容。默认不进 CI——它要联网装 npm 包，一个会因为 npm 打嗝变红的门禁，
  最后会被人标成 flaky，而 flaky 的门禁比窄门禁更糟。
- **MCP 首次配置不再需要重启**。这条是实测查出来的：我按「面板新增 → 热加载」的路径走，
  表格一直显示「状态未知（运行时未启动）」——而运行时明明在跑。原因是
  `core/builder.py` 只在 `mcp.yaml` 已有服务器时才创建 `McpManager`，于是**最该热加载的
  那一次**（从零到一台）恰好没有任何东西可加载，面板只能回一句「重启后生效」。现在管理器
  总是创建，空列表只是它的初始状态。
- **MCP 握手改为版本协商**。客户端原来硬编码 `2024-11-05` 并把 `initialize` 的结果丢掉。
  现在发自己最新的版本、采纳服务端回的版本（实测对方回 `2025-06-18`），遇到没见过的版本
  按 INFO/WARN 记录而不是拒绝——三个调用在已发布的各版本里报文没变过，为一个不认识的
  字符串把一台能用的服务器停掉是更差的交易。
- **握手失败与启动失败不再长得一样**。以前子进程 `stderr=DEVNULL`，npx 下载 404 和协议谈崩
  都只表现为「connection closed」。现在保留 stderr 尾部 2 KB，握手期崩溃会写成
  `exited during the handshake (exit code 9); stderr: npm error 404 ...`。
- **三家 Provider 的报文映射补测**（`tests/test_providers_mapping.py`）。Anthropic、Gemini、
  Ollama 此前**没有任何测试提到过**——它们是三个把我们的结构翻译成别人 schema 的地方，
  而写错字段名不会抛异常，只会安静地少一半信息。
- **两个新的静态门禁**：`scripts/check_test_gaps.py`（孤儿模块 + 文档数字与看板一致性，
  带 `scripts/test_gaps_baseline.txt` 基线）与 `scripts/check_a11y.py`（按钮名称、点击目标
  可聚焦、img alt、对话框语义）。都挂进 `make check` 与 CI 既有作业，不新增作业。
- **09 页流式观察**。`trace.chunks` 与 `trace.stream` 从第一天就写进了环形缓冲，前端
  一个字段都没读——「有数据」和「看得见」之间隔着一次渲染。现在详情区有三段耗时阶梯
  （首 token / 首句送达 / 整条回复，共用同一刻度，所以「首句比整条短多少」是几何可见的）、
  实际发出的分句序列、中断与额度截断角标。
  **顺手修掉一个谎**：`MessageTrace` 在 TypeScript 里声明了 `extras`，而 `to_dict` 从不
  序列化它。第一版用 `extras.send_ok` 判断「回发环节是否跑过」，页面永远渲染不出区块——
  改成读 `stages`，并把这个字段从类型里删掉。
- **面板内编辑 MCP 服务器**（`/api/config/mcp` 的 read / diff / apply）。
  以前只能看状态和重连，增删要 SSH 上去改 `config/mcp.yaml`。三个决定值得记：
  ① **OWNER 权限**，高于 providers 的 ADMIN——新增一台服务器等于开放一条子进程执行通道，
  并把它的工具交给模型调用，与改一个 base_url 不是一个量级；
  ② **`env` 只写不读**，接口只回键名，提交时不带 `env` 就保留磁盘原值——`providers.yaml`
  里那个「把 `***` 存回真实密钥」的坑在这里由结构排除，而不是靠记得检查掩码；
  ③ **diff 用指纹而不是 `***`**：扁平占位符会让「换了 token」渲染成「没有改动」，操作者
  会对着一张空 diff 点确认。改用带进程内盐的 `redacted:xxxxxxxx`，变了看得见，值读不出来。
  写入后热重载（`McpManager.reload` 原地更新，不换对象——工具注册表持有的是这个实例），
  并逐个 server 报告「N 个工具」或「启动失败·原因」。
- **上游连通性自检**（`provider.upstream`）与 `doctor --probe`。
  `providers: []` 以前不产生任何 finding，`doctor` 对着一个答不出任何消息的机器人打印
  PASS。现在空配置是 `[warn]`（MEDIUM，不拉红门禁——只跑面板的机器是合法部署），
  坏 YAML 是 `[fail]`，指向本机或明文 http 会单独点名。
  `--probe` 是可选网络探测，**不发 API Key**：打 `/models`，把 401/403 当作「服务器回答了」。
- **验证矩阵** `docs/verification-matrix.md`：把「有实现 / 有测试 / 真能用」分开写，
  结论只有「自动+实测 / 仅自动 / 未验证」三种，并写明容器、真实 STT、真实云端 Provider
  各自的缺口。
- **看板契约测试** `tests/test_progress_board.py`。`docs/progress/README.md` 里写了四条
  规则（状态枚举、blocked 必须写原因、current 指向真实任务、updated_at 决定可信度），
  此前没有一条被执行——看板因此停在 10-28、`current` 还写着「首次提交待确认 git 身份」。
  规则文件只有人读就会腐烂，这 8 条断言是让它不腐烂的部分。

- 为了上面这条，两处既有代码被拆开而不是复制：
  `core/config_write.build_patch` 原来把 providers 的合并与脱敏规则写死，现在注入
  `apply_fn` / `validate_fn` / `diff_render` / `filename`，默认值保持 providers 行为，既有
  调用点零改动；`mcp/config.py` 把校验从 `load_config` 拆成 `parse_servers`，让面板校验
  候选文档与启动解析是**同一份代码**——两份解析器迟早会分叉，分叉的样子就是「面板保存
  成功、进程起不来」。
- **配置写入 API**（`POST /api/config/providers/{diff,apply}` + `GET /api/config/providers`）。
  三步而非一个 PUT：读取（密钥脱敏 + `base_hash`）→ diff（用**与启动同一套解析器**
  校验候选文档，**不写盘**）→ apply（校验 `base_hash` 未变、`approved_hash` 与确认内容
  一致，再原子写）。
  **这推翻了 `docs/architecture.md §6` 原来的「配置类写入一律不做 API」**：那条规则的
  前提是「文件在版本管理里、改动可被评审」，而单机部署里文件从未进过 git，评审从未
  发生。diff 才是第一次真正生效的评审面。原条目已标注修订并补 §6.1 说明理由。
  三条硬约束各有测试：字段级合并（不整文件覆盖）、候选必须通过启动解析器、不热重载。
- **09 流水线追踪页** + **10 运行指标页**（追加编号，不重排 01–08）。
  追踪数据此前不存在：`ctx.timings` 每条消息算完即丢。新增 `core/trace.py`
  有界环形缓冲（500 条，重启即失，不采样），通过已有的
  `Pipeline.observe` 与 `message.processed` 订阅接入，未改 `Pipeline` 内部。
  指标序列 5 秒一点、保留 720 点（约 1 小时）。
- **手写 SVG 图表组件** `components/charts/{LineChart,BarChart,Sparkline}.vue`。
  不引图表库：依赖清单是审计面（刚移除 4 个未用包），且 canvas 对读屏是不透明位图，
  做 WCAG AA 需再叠一层 DOM。每个图都带可展开的数据表。
- **`components/StageGraph.vue`**：纵向链路 + 逐环节耗时条 + 「在此中止」标记，
  以及**换序沙箱**——可拖拽试排，页面指出破坏了哪条具体约束，但不写回任何地方。
- **07 页 Provider 可视化编辑**：表格内增改、只发被编辑的行、改动行高亮、
  diff 预览 → 二次确认 → 写入，「需重启生效」常驻横幅。
- **`components/DiffEditor.vue`**：行级 diff，带新旧行号与 `+`/`−` 标记，
  不只靠颜色区分增删。
- **`soapbot migrate` 子命令**（`cli_migrate.py`，`--status` / `--dry-run` / `--target`）。
  `UPDATING.md` 从 v0.x 起就让人「升级后跑一次数据库迁移」，而仓库里**没有这个命令**——
  文档承诺了一个不存在的入口，读者只能去翻 `memory/migrations.py` 猜怎么调。
  现在 `--status` 是**只读**的：用 `mode=ro` URI 连库，不触发 `current_version()` 里那句
  `CREATE TABLE`，所以对着一个生产库执行它不会留下任何痕迹。
  探测分五态而不是三态，因为把不同故障压成同一个词会给出错误建议：
  `missing`（文件不存在）、`empty`（0 字节，典型是挂载了空卷）、`unreadable`（损坏或权限不足）、
  `legacy`（有表无版本记录）、`versioned`。前两态提示「先启动一次服务让它建表」，
  `unreadable` 提示「从备份恢复」——把损坏文件说成空库，会让人去启动服务，然后覆盖掉唯一
  的备份线索。
  `legacy` 库先盖章 v1 再顺序跑 v2–v5，与首步同事务：失败回滚后版本表不存在，所以失败
  提示会**重新探测**再措辞，而不是照着进函数时的快照宣称「仍停在 version 1」。
- **`core/proc_env.py`**：插件与 MCP 服务共用的子进程环境白名单。此前 MCP 侧传的是
  `{**os.environ, **server.env}`，于是 `npx -y <某个包>` 起的服务能直接读到
  `SOAPBOT_MASTER_KEY` 与全部 provider 密钥——而 `SECURITY.md` 把 MCP 定级为「不可信」。
  一个被实现否定的定级比没有定级更糟，因为它请读者去依赖它。两侧共用一个模块而不是各写
  一份：两份白名单迟早分叉，而往这个方向分叉是 fail-open。
- **`tests/test_cli_documented_commands.py`**：扫描文档里出现的 `soapbot <子命令>`，断言
  解析器真的接受它。`migrate` 缺失这件事能活到被发现，是因为没有任何东西把「文档说了」
  和「代码有」连起来。同类的下一个缺陷现在会在 CI 里红。

### 修复

- **`SOAPBOT_ENV_FILE` 指定的 `.env` 从来没被读进 `os.environ`**。`load_dotenv_if_present`
  按 `__file__` 推到源码树根的 `.env`（容器里是只读的 `/app/.env`），而且**这个函数一次都没被
  调用过**。自定义键（如 `DEEPSEEK_API_KEY`）只存在于数据卷的 `/data/.env`，而 `api_key: env:NAME`
  是从 `os.environ` 解析的——密钥放在文档说的那个位置，启动会直接报 `references unset
  environment variable`，看起来像密钥文件坏了。现在按 `SOAPBOT_ENV_FILE` 解析，并在解析
  provider 之前调用。
- **`doctor --probe` 的 5 秒超时把能用的 Provider 判成不可达**。容器内实测：DNS 0.03 s、
  到 `api.deepseek.com` 的 TCP **4.0 s**、TLS 与 401 再 1.3 s。5 秒预算一擦边就是
  `ConnectTimeout`，会把人送去查防火墙，而真正的原因是路由距离。默认改为 15 秒。
- **MCP 子进程关闭时打印 `Exception ignored in BaseSubprocessTransport.__del__`**。
  `close()` 只 terminate + wait，没有收掉管道，于是传输对象被回收时 CPython 打一段
  traceback——部署日志里看起来像崩溃，其实是正常关机。
- **两张表格的行只能鼠标点**。人格表与会话表的 `<tr @click>` 没有 `tabindex`，键盘用户
  根本到不了，且按 Enter 什么也不会发生。补上焦点与 Enter/Space；`@click.self` 的遮罩层
  是例外，它不该成为 tab 停靠点（Esc 已经负责关闭）。
- **`Pipeline.observe` 的回调是 async 的**。首版传入同步函数，`await None` 抛错被
  pipeline 当作 observer 错误吞掉，导致所有耗时静默丢失、端点仍返回 200 空列表。
  现由 `_observe_stage` 适配，并有测试断言它是协程函数。
- **流水线崩溃的消息不留痕迹**。`_on_event` 的 except 分支直接 return，既不发布也不
  计数，`failed` 永远为 0。现在记录一条 `halt_reason=pipeline_error` 的 trace。
- **`file_hash` 与 `build_patch` 用了不同的哈希口径**：前者对原始文本、后者对规范化
  后渲染的内容，导致读取端点发出的 `base_hash` 永远无法通过写入校验。现统一走
  `render`。
- **只读文件无法被 `os.replace` 覆盖**（Windows WinError 5）。现在写入期间临时解除
  只读位、写后恢复，文件最终仍是只读。
- **`STAGE_ORDER` 与 `build_pipeline` 不一致**：插件环节实际名为
  `plugin_message_hooks`。漂移测试立刻抓到了它。
- **`make check` 与 CI `backend` 不是同一组命令**，而 `Makefile` 文件头就写着它们是。
  实测差集：`check_deps.py`、`check_console_encoding.py`、`check_deploy.py` 只在 CI 跑。
  三个都是离线、确定性、一秒内跑完的静态扫描——正是最该在本机跑的那类门禁，它们的缺席
  意味着同一份提交可以本地全绿、CI 全红。现在补进 `check`，并新增
  `tests/test_gate_parity.py` 解析两边文件、断言差集恰好是两项（`check_secrets
  --committed` 要 git 历史，`pip-audit` 要联网）。注释里的承诺不是门禁，这个测试是。
- **Windows 上 `.env` 的跨进程锁有 10 秒硬上限**。`msvcrt.LK_LOCK` 是「重试 10 次 × 1 秒
  后抛 `OSError`」，预算由系统决定且无法观测。4 个进程各写 20 次同一个文件时，全量跑
  大约每轮失败一次——看起来像锁的竞态 bug，实际是重试策略的超时。改用 `LK_NBLCK`
  非阻塞加指数退避（5 ms 起、上限 250 ms），预算 30 秒由我们定；超时抛
  `EnvLockError`（`TimeoutError` 子类，仍是 `OSError`，四个 API 写入点的
  `except OSError` 映射不变），日志能说清「另一个写入者正持有它」而不是「磁盘坏了」。
  睡眠不超过剩余预算，所以超时是真正的上界而不是「上界加一个退避间隔」。


- **开发进度看板** `docs/progress/`：`index.html` + `board.css` + `board.js` +
  `progress.json` + `README.md`。零依赖、零构建、无 CDN、无 webfont，
  用 `make progress` 起静态服务查看（`file://` 下 fetch 会被 CORS 拦截）。
  百分比由文件清单复算（子任务权重 = 文件数，完成比 = 已完成/总数），
  **没有手工填写入口**——手填的百分比没有可信度。
  防「看板撒谎」三项：`updated_at` 超 10 分钟标黄、fetch 失败显式报错且保留上次
  渲染结果、只陈述四态（未启动/进行中/已完成/受阻）。
- **`scripts/check_contrast.py`**：解析 `base.css` 与 `board.css` 的 `:root` token，
  按 WCAG 相对亮度公式断言对比度，并检查 `:root` 之外无硬编码颜色。
  已接入 `make check`（`check: lint contrast test`）与
  `tests/test_a11y_tokens.py`（5 项）。
- **`webui/src/lib/useFocusTrap.ts`**：焦点陷阱 + Esc + 关闭后归还焦点。
  抽出而非各写一遍，因为登录框与确认框都需要且都不能做错。
- **`webui/src/components/ConfirmDialog.vue`**：`role="alertdialog"` + `aria-modal`，
  用 `tone` 与 `irreversible` 区分「可逆」与「不可逆」的措辞——
  统一的「确定吗？」会训练人闭眼点过。

### 变更

- **控制台整体改为浅色企业风**。8 个既有视图全部换肤。
  原因：这套面板实际是在客服通话中、笔记本上、和聊天窗口并排打开的，
  白底与其他窗口读作同一份文档，黑底读作另一个应用。
  保留的部分：衬线标题（运维工具里罕见，是主要识别度）、等宽数据列、
  01–08 编号导航（稳定标识符，重排会让过去沟通里的「05 页」失去指向）。
- **状态色全部重新取值**。深色主题的 `#5ec98a` 在白底上只有 1.9:1，
  不满足 AA。现值是 700 档（`--ok: #047857` 等），并新增 `--ok-soft` 等浅底配对。
- **控件边界从 `#cbd5e4` 改为 `#7c8aa3`**：前者在白底上 1.48:1，
  远低于 WCAG 对表单控件边界要求的 3:1；后者 3.49:1。
  这个值是校验脚本算出来的，不是目测调的。
- **散落的硬编码颜色收进 token**（`--ok-line` / `--warn-line` / `--danger-line` /
  `--brand-line` / `--on-brand`）。此前有 16 处绕过 token 直接写色值，
  其中 4 处引用了换肤后已不存在的变量（`var(--lamp)` / `var(--paper)` /
  `var(--ink-900)` / `var(--ink-600)`），会静默失效。
- **表格语义**：81 个 `<th>` 补 `scope="col"`；有 `<thead>` 的表加
  `.visually-hidden` 的 `<caption>`（面板标题已在屏幕上说明同一件事，
  重复显示只是噪音，但无名称的表会被读屏播报成「表格」）；
  键值表（配置文件、累计计数、策略）的首列改为 `<th scope="row">`，
  加 caption 解决不了这类表的实际问题——读屏无法判断哪个值属于哪个标签。

### 上下文连续性：滚动摘要不再每轮丢失

原来错在哪：`ContextCompressor.compress()` 早就接受 `prior_summary` 并返回更新后的
`summary`，`MemoryStore` 也有 `latest_summary` / `save_summary`，`MemoryStage` 会注入
「【会话摘要】」——但 `AIEngine._prepare` 既不传也不存，装配处也没接线。结果是 L1 摘要
表恒空、每轮从零重压缩、折叠掉的历史只活一个请求。

现在 `AIEngine` 注入 `summary_loader` / `summary_saver` 两个 callable：压缩前读，
在**模型调用之前**写（折叠已经把这些轮次从请求里移走，摘要是唯一副本）。读写失败只记
日志、绝不抛——摘要是上下文的改进，不是回答的前置条件。

### 特权操作的安全边界

原来错在哪：出站 URL 只做 deny-list（拦私网），任何公网主机都放行；记忆检索只按
`scope` 过滤，把过滤器当成了授权边界；`revoke-all` 撤销全部后立刻重签一枚 72h 完整
会话，使撤销只停留在审计日志里；工具参数从模型 JSON 直接进注册表，没有来源标记；
插件加载只有字节摘要，没有能带走的执行凭据；MCP 只协商线协议，不记录第三方实现的
版本。

现在六道确定性边界，每道都配了改错复验（去掉规则则测试必须失败）：

| 能力 | 落点 | 拒绝时的行为 |
|---|---|---|
| 出站目标预允许列表 | `plugins/sandbox.py` | 未列入的主机在 deny-list 之前被拒；空列表 fail-closed |
| 记忆 handoff 反单调准入 | `memory/handoff.py` | 受众被放宽、数据-only 来源、低置信度记录不进 prompt；残余不安全率是实测值 |
| 撤销达到闭合终态 | `api/auth.py`、`security/tokens.py` | 不签发会话；轮换一次性引导凭据并验证终态，任一不成立返回 500 |
| 参数级信息流溯源 | `security/provenance.py` | 来源标记放在 dict 属性上，模型 JSON 无法伪造；资源参数须过宿主注入的校验 |
| 可移植运行时证明 | `plugins/attestation.py` | 工件哈希 + 策略指纹 + 执行证据；签名边界如实标为空，未声称已签名 |
| MCP 实现版本 pin | `mcp/client.py`、`mcp/config.py` | 版本不匹配拒绝并清理子进程；不 pin 也记录身份与协议版本 |

### Windows 双端与桌面端

原来错在哪：三条 Windows 入口注册三个不同的计划任务名（`SoapbotBot` /
`SoapbotPanel` / `soapbot-panel`），触发器和令牌策略还相反；桌面端只是一个连接 6185 的
Tauri 托盘壳，不携带后端、不产安装包，CI 在 Ubuntu 上只做 `cargo check`。

现在：

- 两条安装路径注册**同一个** `SoapbotBot`（SYSTEM、开机启动），令牌只给
  `data\init_token.txt` 的路径；`start-panel.bat` 作为前台本地路径显式豁免并写进测试。
- 后端可冻结成 46.3 MiB onefile（`desktop/sidecar/build.py`），壳先探测 6185、端口空才
  spawn、退出用 `taskkill /T` 杀整棵进程树（`desktop/src-tauri/src/main.rs`）。
- NSIS 安装包本地实测 47.48 MiB，`installer.nsi` 把后端写进 `$INSTDIR\binaries\`。
- CI 新增按需的 `desktop-bundle`（Windows runner），首次真实运行 9m2s、产物 46.9 MiB。
- **签名未做**：`docs/desktop-signing.md` 写明未签名的具体代价（SmartScreen 两次点击、
  杀软误报、企业 AppLocker 可能直拦）与两条开源通道，没有写成「已支持」。

### 发布与协作流程

原来错在哪：`master` 有分支保护，但仓库里没有任何地方写这件事，一次直推绕过了它
（GitHub 回 «Bypassed rule violations»）；Releases 页是空的，唯一产物是 7 天过期的
artifact；AI 助手拿不到仓库的硬性规则。

现在 `CONTRIBUTING.md` 写出五步流程与必需检查名单——名单读自
`branches/master/protection`（`backend` 两个平台、`frontend`、`desktop`、`package`；
`review` 在后续一轮加入，当前为六道），并说明单人维护时 `gh pr merge --admin` 只跳过
人工 approve，与直推不是一回事。
`.github/pull_request_template.md` 把接线测试、文档优先、未验证要标注变成 PR 必答项；
`.github/copilot-instructions.md` 给 AI 助手同一套规则；`ci.yml` 新增 tag 触发的
`release` job，把 wheel 与安装包挂到 GitHub Release。

### 类型检查棘轮、查询效率与分包

`mypy` 一直以 `continue-on-error` 运行：79 个错误躺在没人打开的日志里，第 80 个也不会
被拦——和当初 `pip-audit` 的毛病一样，能失败才算门禁。新增
`scripts/check_mypy_baseline.py`：基线写在同一目录的 `mypy_baseline.txt`，只允许降不允许
升，不要求修那 79 个，只拒绝新增。一次约 1.7 秒，已进 `make check` 与 CI 的 `backend`
job（`tests/test_gate_parity.py` 保证两边一致）。

三处结构问题：

- `memory_stats` 对每个 layer 单独 `COUNT`，一屏 4–5 次往返，且每次可能读到不同快照，
  于是「总数」和「各部分之和」在负载下能对不上。改为一次 `GROUP BY`
  （`MemoryStore.count_by_layer`）；`-1` 仍表示「这一屏读不到」，与「零行」区分开。
- 技能列表的目录遍历和保存时的 `mkdir + write_text` 原来直接在事件循环上跑。改用
  `asyncio.to_thread`——同文件里 `api/napcat.py` 早就是这个写法，只是没推广。
- 面板没有 vendor 分包：`vue`/`vue-router`/`pinia` 与视图代码打进同一个入口 chunk。
  加 `manualChunks` 后实测 `vendor` 104.28 kB、`index` 143.69 kB（gzip 40.60 / 52.69），
  面板更新时只有视图 chunk 失效。

删掉 3 项未接线代码：`SceneMemory.drop_portrait`、`content_fingerprint`、
`charts/Sparkline.vue`（134 行，从未被 import）。`check_secret_resolvable` **没有删**：
它的注释明确写着「Unused, and deliberately kept」，理由是替代做法会在 API 层长出第二套
密钥解析——注释里写明的取舍不该被当成死代码清理。

### 破坏性操作的确认统一走组件

面板里 5 处删除/撤销用的是原生 `window.confirm`：它阻塞事件循环、渲染在焦点陷阱之外
（键盘还留在背后那一页上）、且只能显示一个字符串——所以记忆页三种不同的删除，在「确定
不可逆」那一刻看起来完全一样。

现在统一用 `ConfirmDialog`，目标自带类型（记忆 / 知识文档 / 技能 / 撤销审批 / 删除插件），
对话框据此显示正确的标题与后果；请求进行中按钮禁用，**失败时对话框不关闭**——先关再失败
会让人以为已经删掉了。

`scripts/check_a11y.py` 增加第五条规则禁止 `window.confirm`，配套
`tests/test_a11y_gates.py` 三条用例：真实调用必须被抓到、注释里的提及不能误报、仓库当前
干净。规则按行判断并跳过注释行，这是近似做法，写在函数的 docstring 里。

## [0.1.0] - 2026-10-28

首个可 clone、可构建、可部署的版本。

### 新增

- `LICENSE`（MIT）、`.env.example`、`CHANGELOG.md`、`Makefile`、
  `.github/workflows/ci.yml`、`scripts/check_deps.py`。
  此前仓库声明 MIT 但没有许可证文件，且没有任何自动化检查。
- 示例插件移入包内 `src/soapbot/examples/plugins/`（`admin` / `echo` / `help` /
  `remind`），通过 `soapbot.examples.bundled_plugins_dir()` 访问。
  此前它们在 `data/plugins/`，而 `data/` 被 `.gitignore` 排除：全新克隆没有任何
  插件，五个测试模块直接 `FileNotFoundError`。
- 插件批准状态持久化到 `data/plugin-approvals.json`
  （`soapbot.plugins.approvals.ApprovalStore`），并在启动时自动加载已批准的插件。
- 插件工具调用全链路：`AIRequest.tools` / `tool_note`、`ModelStage` 有界工具循环、
  隔离模式下的 `register_proxied_tool`。
- notice 链路：`OneBot11Adapter._to_notice`、`Adapter.emit` 放行 `NOTICE`、
  `BotRuntime._on_notice`。
- 群管命令 `/mute` `/unmute` `/kick` `/recall-msg`，以及
  `Permission.MODERATE_GROUP`。
- 适配器群管动作契约：`recall` / `set_group_ban` / `set_group_kick` /
  `get_group_list`，OneBot 端完整实现。
- 知识库写入 API：`POST /api/knowledge`、`DELETE /api/knowledge/{doc_id}`、
  `GET /api/knowledge/{doc_id}`，以及 `KnowledgeBase.ingest_document`（覆盖语义）。
- 管理面板新增「模型与人格」(07)、「运行日志」(08) 两页；记忆页补齐知识库上传与删除；
  插件页补齐「撤销批准」「删除」。
- `MemoryStore.find_message`：按会话 + 平台消息 ID 查询，供撤回命令做归属校验。

### 修复

- **QQ 官方适配器在群里完全不应答**。`_strip_at_prefix` 把 `<@bot>` 抹掉后不产生
  AT 段，而 `WakePolicy` 在群里先找 AT 段、再找唤醒词，两者都没有 → 所有正确
  @机器人 的消息被静默丢弃。现改为 `split_leading_at` 返回 `(mentioned, body)`，
  调用方据此补一个 AT 段。OneBot 端不受影响，因为它原生携带 AT 段——这正是缺陷
  长期不可见的原因：两个适配器对「谁来判断是否被呼叫」没有共识。
- **私聊在任何配置下都不可用**。`build_runtime` 接收 `allow_unknown_private` 却从未
  使用，`AccessPolicy()` 无参构造，因此 `SOAPBOT_ALLOW_UNKNOWN_PRIVATE=true` 无效。
  新增 `build_access_policy()`，并把 `private_allowlist` / `group_allowlist` /
  `group_blacklist` / `user_blacklist` 一并接入配置。
- **插件批准在重启后全部丢失**。`_approved` 是纯内存字典，导致：重启后没有插件在跑、
  WebUI 显示「已启用」却加载失败、无头部署根本无法授权。
- **模型永远看不到插件工具**。`PluginToolRegistry.available_for` 零调用方，
  `AIRequest` 无 `tools` 字段，Provider 层虽已支持 `tools` 却收不到。
- **隔离模式下工具被注册成了命令**。worker 用同一帧上报命令与工具，宿主把两者都按
  命令注册，于是工具变成 `/tool-name` 斜杠命令，模型反而看不到。
- **`on_notice` 永远收不到通知**。三处同时断开：OneBot 丢弃 `post_type != "message"`、
  `Adapter.emit` 对非 MESSAGE 直接 return、`PluginManager.on_notice` 无调用方。
- **群管能力只有声明没有实现**。OneBot 声明了 `RECALL`/`MUTE`/`KICK`/`GROUP_LIST`，
  四个方法一个都没有。
- **知识库只读**。`add_document` 等写入路径实现完整且被检索侧消费，但服务内没有任何
  调用方，知识库页面只能是空的。
- **`list[str]` 配置项用逗号分隔会导致启动失败**。pydantic-settings 对复杂类型先做
  `json.loads`，`SOAPBOT_OWNER_IDS=123,456` 抛 `SettingsError` 且不说明正确写法——
  而文档写的正是逗号分隔。现支持 `a,b` / `a;b` / `["a","b"]` 三种。
- **声明了四个从未使用的依赖**：`structlog`、`watchdog`、`python-multipart`、
  `edge-tts`。依赖清单会扩大审计面，并让评审者以为项目具备实际不存在的功能。

### 变更

- 插件启动行为从「只发现、永不加载」改为「发现 + 加载已批准项」。区别在于选择来源：
  前者不会执行任何东西，后者执行的是**曾经由人做出的持久决定**。未获批准的目录仍然
  被 `load()` 拒绝，这条规则没有放宽。
- `/recall` 保持「检索记忆」语义，撤回消息命名为 `/recall-msg`。复用 `/recall` 会让
  既有部署的命令静默变成另一种行为。

### 已知限制

见 `docs/delivery-readiness-assessment.md` 与 `docs/wave6-10-runtime-auth-webui.md`。
简要列出：

- 插件之间不互相调用（设计如此：插件 A 不能借插件 B 提权），也没有插件市场。
- 无 MCP、无 STT/TTS、无流式输出、无 i18n。
- QQ 官方适配器的群管能力未实现（平台侧限制）。
- 额度审批、B 站浏览默认关闭，需显式开启。
- 清单摘要漂移只报告不阻断（在 `GET /api/plugins` 的 `approval.manifest_changed` 里）。

[Unreleased]: https://example.invalid/soapbot/compare/0.1.0...HEAD
[0.1.0]: https://example.invalid/soapbot/releases/tag/0.1.0

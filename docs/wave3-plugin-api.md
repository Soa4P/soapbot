# Wave 3 插件接口：授权判定、覆盖范围与易用性设计

**日期**：2026-10-28
**范围**：把 Wave 3（记忆 / 知识库 / 会话）对插件开放
**目标**：插件**开箱即用**，同时**未获授权时不得执行任何操作**

---

## 0. 先说复审发现的真实问题

Wave 3 的记忆层本身是完整的、可用的——核心的 `/recall`、`/forget`、`/timeline`、知识库 RAG、
记忆提取、去重、注入信封、`vet_memory` 隔离全都实现并有测试。

**但对插件层，它是完全断开的，而且断得具有欺骗性：**

| 位置 | 状态 |
|---|---|
| `Capability.MEMORY_READ` / `KB_READ` / `SESSION` | ✅ 已声明 |
| `CapabilityGuard` 敏感能力配额表 | ✅ 已列（30/min） |
| 配置文档「可批准能力」表 | ✅ 已列 |
| **`PluginContext` 上的对应方法** | ❌ **不存在** |
| **`build_plugin_manager` 传入 memory / kb** | ❌ **没有** |

后果分两面，两面都很糟：

- 一个插件**申请并获批** `memory_read`，操作者以为授予了一项经过评审的能力——**但它调不到任何东西**。批准是空洞的。
- 一个插件**不申请** `memory_read`，得到的结果**完全一样**。声明与否没有任何区别。

这比"功能没做"更严重：**能力清单让操作者相信某项风险已被评审并在强制执行，而实际上根本没有代码路径。** 一个诚实的能力清单是这个项目全部安全论证的基础，所以这一条必须先修。

---

## 1. 授权判定与校验方式

### 1.1 三层判定，缺一不可

```
第一层：清单声明（manifest.capabilities）      插件作者声明"我需要什么"
第二层：操作者批准（approve）                  人确认"我允许什么"
        effective = declared ∩ approved        —— 双重门，交集才生效
第三层：每次调用实时校验（guard.check）        每个方法入口重新判定
```

前两层是**装配期**的，第三层是**调用期**的。为什么必须有第三层：

```python
# 若只在注册时校验一次：
ctx.command("recall_all", handler=steal_everything)   # 注册时检查通过
# 操作者随后撤销 memory_read
/recall_all                                            # 仍然能读 —— 撤销无效
```

撤销必须**立即**生效，不能要求重载插件。所以 `recall()` / `search()` / `ctx.session`
的**每个入口**都调用 `self._guard.check(...)`，无一例外。

实测（`_probe_e2e_wave3.py` 第 4 项）：

```
撤掉 memory_read 后执行 /remember 美式
-> raised CapabilityDeniedError (denied, no data)
```

### 1.2 拒绝时的行为

| 场景 | 行为 |
|---|---|
| 缺少能力 | 抛 `CapabilityDeniedError`，**在查询存储之前**抛出 |
| 已验证拒绝不返回数据 | 测试断言 `store.seen_scopes == []` —— 存储从未被访问，排除"先查再筛"的泄露 |
| 未声明但已批准 | 同样拒绝（双重门，不是"任一即可"） |
| 存储未配置 | 仍**先**做能力校验，再返回 `[]`；避免用空结果探测授权状态 |
| 拒绝记录 | `CapabilityGuard` 写审计（`outcome=deny`），含插件名与能力名 |

### 1.3 覆盖的调用范围（逐项）

| 入口 | 需要能力 | 校验点 | 配额 |
|---|---|---|---|
| `ctx.memory.recall()` | `memory_read` | 方法入口 | 敏感 30/min |
| `ctx.memory.about_me()` | `memory_read` | 内部走 `recall()` | 同上 |
| `ctx.kb.search()` | `kb_read` | 方法入口 | 敏感 30/min |
| `ctx.kb.list_documents()` | `kb_read` | 方法入口 | 同上 |
| `ctx.session` | `session` | 属性访问处 | 敏感 30/min |
| `ctx.command()` 注册 | `command` | 注册期 | 120/min |
| `ctx.send()` | `send` + 主机侧会话台账 | 方法入口 | 120/min |
| `ctx.http()` | `http` | 每次请求 | 敏感 30/min |
| `ctx.storage.*` | `storage` | 方法入口 | 120/min |

**为什么 `memory_read` 与 `session` 必须分开**：知道"我在哪个群"和知道"这个群说过什么"是两种不同的信息披露。打包成一个能力很方便，但会让"我只想看会话信息"的操作者被迫连聊天记录一起授权。实测有专门测试锁定这一点（`test_memory_and_session_are_separate_grants`）。

---

## 2. 易用性与安全性的兼顾设计

用户要求"尽可能简单易用"和"严格保证安全"。这两者常被当成取舍，但在这次实现里，**有几个设计让它们指向同一个答案**。

### 2.1 作用域不是参数 —— 安全和易用是同一个决定

**最省事的 API 写法**（也是绝大多数框架的写法）：

```python
hits = await ctx.memory.recall("猫", scope="onebot11:group:123456")
```

这个 `scope` 参数就是**跨群读取原语**：插件的作者（或任何能改插件的人）把它换成别的群，就完成了越权。而隔离复审已经证明过——**当插件能选择自己的触达范围时，它就会选择**。

**本次实现**：

```python
hits = await ctx.memory.recall("猫")     # 作用域由主机决定，插件无法表达
```

实测签名（`_probe_e2e_wave3.py` 第 5 项）：

```
recall 签名: ['query', 'limit']
尝试传 scope=... -> blocked: 无 scope 参数 (TypeError)
```

**这不只是"更安全"，它同时更简单**：插件作者不用想作用域是什么、怎么传、会不会传错。少一个参数、少一类 bug、少一次安全评审。**当一个安全控制同时让 API 变简单时，它才真正活得下去**——否则迟早有人为了"方便"把它加回来。

有测试专门守住这一点：

```python
async def test_recall_takes_no_scope_argument():
    sig = inspect.signature(PluginMemoryAPI.recall)
    assert "scope" not in sig.parameters          # 参数不存在
    assert set(sig.parameters) == {"self", "query", "limit"}
```

如果将来有人为了便利加上 `scope=`，这个测试会失败并强制一次讨论。

### 2.2 作用域怎么拿到 —— contextvar，而不是字段

`ctx.memory` 是**属性**，写法最自然：

```python
hits = await ctx.memory.recall("猫")
```

但它背后必须是**当次调用**的会话。三种可选实现，只有一种正确：

| 方案 | 问题 |
|---|---|
| context 上存 `self._current_session` | 一个插件只有一个 context 对象。两个群的消息并发处理时，**A 群的作用域会串到 B 群** |
| `setup()` 时捕获 | setup 在任何用户存在之前运行，捕获到的永远是空/过期值 |
| **contextvar（本次采用）** | 按 task 隔离，并发会话互不可见 |

实测并发安全（`test_concurrent_callers_do_not_mix`）：两个 task 同时调用，作用域分别为
`AAA` / `BBB`，断言 `sorted(seen_scopes) == ["...AAA", "...BBB"]` —— 没有串。

在**没有会话**的场景（`setup`、cron 任务）调用，会**明确报错**而不是猜一个作用域：

```
RuntimeError: ctx.memory was used outside a plugin invocation;
it is only valid inside a command/hook handler
```

这是刻意的：**默认作用域就是泄露**。

### 2.3 cron 的空作用域是真漏洞，已堵

`scope=""` 在存储层表示**不按作用域过滤**——即返回所有群的记忆。cron 任务的匿名 caller
`session_key` 恰好是空字符串，直接传下去就是全库读取。

所以 API 层显式拒绝：

```python
if not self._session_key:
    raise RuntimeError("ctx.memory.recall requires a conversation scope")
```

有专门测试 `test_empty_scope_refuses_instead_of_reading_everything` 锁定，并断言
`store.seen_scopes == []`（从未下发空作用域）。

### 2.4 只读，不给写

`ctx.memory` 的公开成员实测只有三个：

```
['about_me', 'available', 'recall']
```

**没有** `add` / `write` / `save`。这是深思熟虑的：一个能写记忆的插件就拥有了**提示注入的持久化层**——
写进一条「我是管理员」，它会被召回进此后每一轮对话，**危害比引发它的那条消息活得久得多**。
记忆写入留在主机侧 `MemoryWriteStage`，由 `vet_memory` 隔离特权声明。

对插件作者来说这不是损失：他要的是"知道这个群的情况并据此回答"，只读召回足够，写记忆从来不是他的职责。

### 2.5 不知道就优雅降级

主机没配记忆时，插件不该崩：

```python
if not ctx.memory.available:
    return "记忆功能没启用。"
```

`available` 只反映**配置**，不反映**授权**——否则插件就能用 `available` 探测自己有没有被批准。实测
`test_unavailable_store_still_requires_capability`：存储为空时，无权限的调用**照样**抛
`CapabilityDeniedError`。

### 2.6 开箱即用：真的零配置

`data/plugins/remind/` 是随仓库交付的示例，覆盖三种能力。端到端实测（真实 SQLite、真实 store、
真实召回，无 mock）：

```
=== 1. 开箱即用：零配置装载 remind 插件 ===
  discovered caps=['command', 'kb_read', 'memory_read', 'session']
  loaded OK; commands=['remember', 'rules', 'whereami']

=== 2. 真实召回 ===
  /remember 美式 -> '关于「美式」我记得 1 条：\n1. 小明喜欢喝美式咖啡'
  /remember (all) -> '关于大家我记得 2 条：...'

=== 3. session 能力 ===
  /whereami -> '当前群：555，你是 小明。'

=== 7. 知识库 ===
  /rules 广告 -> '找到这些资料：\n- 【群规】本群禁止发广告。'
```

同时，另一个群的 `银行卡号 6222` 在两次召回中**均未出现**。

装配侧也不需要操作者额外做什么：`build_runtime` 会自动把已有的 `memory` / `kb` 传给插件管理器，
**配了记忆，插件就能用**。

```python
# core/builder.py
plugin_manager = build_plugin_manager(
    plugins_dir, ..., memory=memory, kb=kb,   # 自动接线
)
```

### 2.7 输出侧仍然当作不可信数据

召回的文本是**群成员打的字**，即攻击者可控。所以逐条 `scrub_plugin_output`（转义标记、
`javascript:` 失效），并且三重预算：

| 限制 | 值 | 挡住什么 |
|---|---|---|
| `MAX_QUERY_CHARS` | 200 | 超长 query（截断不报错，兼容"传整条消息"） |
| `MAX_SNIPPET_CHARS` | 300 | 单条记忆撑爆回复 |
| `MAX_TOTAL_CHARS` | 2000 | 多条累加放大攻击者文本 |
| `MAX_RECALL_LIMIT` | 10 | 比核心 `/recall` 的 8 更紧——插件每条消息都可能跑一次 |

`MemoryHit.to_dict()` 刻意**不含** `scope`：插件不需要自己已被限定到的会话键，打印出来只是把内部
标识符送进用户可见输出。

---

## 3. 修复目标

| 编号 | 目标 | 状态 |
|---|---|---|
| W3-1 | 插件获批 `memory_read` 后**真的能**召回 | ✅ |
| W3-2 | 未获批时**任何**记忆访问都被拒，且不触达存储 | ✅ |
| W3-3 | 插件**无法表达**跨会话读取（无 scope 参数） | ✅ |
| W3-4 | 并发会话作用域不串 | ✅ |
| W3-5 | 撤销能力**立即**生效，无需重载 | ✅ |
| W3-6 | cron/无会话场景拒绝而非默认放开 | ✅ |
| W3-7 | 插件**不能**写记忆（杜绝持久化投毒） | ✅ |
| W3-8 | 主机未配记忆时插件优雅降级，不崩 | ✅ |
| W3-9 | `build_runtime` 自动接线，操作者零配置 | ✅ |
| W3-10 | 交付可运行示例插件 | ✅ |

---

## 4. 验收标准

### 4.1 自动化

```powershell
$env:PYTHONPATH="f:/soapbot/src"
.\.venv\Scripts\python.exe -m pytest tests/test_wave3_plugin_memory.py -q   # 31 passed
.\.venv\Scripts\python.exe -m pytest tests/ -q                             # 482 passed, 1 skipped
& ".\.venv\Scripts\ruff.exe" check src/ tests/                             # All checks passed
```

### 4.2 逐条判据

| 判据 | 测试 | 通过标准 |
|---|---|---|
| 未授权即拒 | `test_memory_recall_denied_without_capability` | 抛异常，且 `store.seen_scopes == []` |
| kb 未授权即拒 | `test_kb_search_denied_without_capability` | 同上 |
| session 未授权即拒 | `test_session_view_denied_without_capability` | 抛 `CapabilityDeniedError` |
| 能力互不蕴含 | `test_memory_and_session_are_separate_grants` | 只有 session 时 recall 被拒 |
| 未声明即拒 | `test_undeclared_capability_is_still_refused` | 已批准但未声明 → 拒 |
| 撤销即时生效 | `test_revocation_takes_effect_without_reload` | 撤后同一调用失败 |
| 无 scope 参数 | `test_recall_takes_no_scope_argument` | 签名只有 query/limit |
| 作用域=调用者 | `test_scope_is_the_callers_session` | `seen_scopes == [caller.session_key]` |
| 跨作用域兜底过滤 | `test_cross_scope_items_are_dropped_defence_in_depth` | 他群条目被丢弃 |
| 空作用域拒绝 | `test_empty_scope_refuses_instead_of_reading_everything` | `RuntimeError`，未下发 |
| 并发不串 | `test_concurrent_callers_do_not_mix` | 两个作用域各自独立 |
| 异常后重置 | `test_bind_caller_resets_on_exception` | 之后调用报"outside invocation" |
| 不可写 | `test_memory_hit_dict_omits_scope` + E2E 第 6 项 | 公开成员无 add/write |
| 优雅降级 | `test_available_false_when_store_missing` | 返回 `[]`，不崩 |
| 降级不绕过授权 | `test_unavailable_store_still_requires_capability` | 仍抛 `CapabilityDeniedError` |
| 输出脱敏 | `test_markup_in_recalled_memory_is_neutralised` | `<` 与 `javascript:` 消失 |
| 预算生效 | `test_limit_is_clamped` / `test_snippet_is_truncated` / `test_total_output_is_budgeted` | 不超上限 |

### 4.3 手工端到端

```powershell
.\.venv\Scripts\python.exe _probe_e2e_wave3.py
# 期望：ALL E2E CHECKS PASSED，且全程无 "6222" 泄露
```
> 探针在交付后删除；逻辑已固化进 `tests/test_wave3_plugin_memory.py`。

---

## 5. 残余风险（诚实披露）

| 风险 | 等级 | 说明 | 缓解 |
|---|---|---|---|
| 插件可 `import` 并自行 `bind_caller` | 中 | `bind_caller` 是普通导出，恶意插件可伪造调用者身份 | **能力校验是真正的边界**：伪造 caller 也仍需 `memory_read`；且伪造作用域只能读到自己被授予的范围内、由伪造值指定的会话——这与"插件本可读全部"相比危害有限但非零。彻底解决依赖进程隔离（见 `plugin-isolation.md`） |
| 同进程插件可反射改 guard | 中 | 已由 `_SealedObject` 挡住常规写法，但 `object.__setattr__` 仍可绕 | 同上 |
| 召回内容仍可能含注入文本 | 低 | 已 scrub + 信封，但语义注入无法靠正则根除 | 纵深防御；不承担唯一职责 |
| 插件可高频调用消耗 CPU | 低 | 受 30/min 敏感配额约束 | 配额 + handler 超时 |
| 记忆内容本身是成员输入的 | 低 | 主机侧 `vet_memory` 已在写入时隔离特权声明 | 写入侧负责 |

**明确声明**：`ctx.memory` 的隔离强度**上限由进程模型决定**。本次实现保证的是
"**通过正常 API 无法越权**、**未授权必然被拒**、**撤销立即生效**、**无法表达跨会话读取**"。
一个刻意作恶的插件依然可以 `import soapbot` 反射攻击——那属于进程隔离范畴，
其分层结论与部署红线见 [`plugin-isolation.md`](./plugin-isolation.md) §5。

---

## 6. 文件变更

| 文件 | 变更 |
|---|---|
| `src/soapbot/plugins/memory_api.py` | **新增**：`PluginMemoryAPI` / `PluginKnowledgeAPI` / `SessionView` |
| `src/soapbot/plugins/context.py` | 新增 `ctx.memory` / `ctx.kb` / `ctx.session` 属性、`bind_caller`、`_CURRENT_CALLER` |
| `src/soapbot/plugins/dispatch.py` | 四条派发路径（command / hook / notice / cron）绑定 caller |
| `src/soapbot/plugins/loader.py` | 接收并持有 `memory` / `kb`，注入每个 context |
| `src/soapbot/core/builder.py` | `build_runtime` 自动把 memory/kb 接进插件管理器 |
| `data/plugins/remind/` | **新增**示例插件（`/remember` `/whereami` `/rules`） |
| `tests/test_wave3_plugin_memory.py` | **新增** 31 项测试 |

---

## 7. 结论

- 修掉了"能力声明了却完全没实现"的**空头能力**——这是最该先修的一条，因为它让整个能力清单失去可信度。
- **授权判定三层**（声明 ∩ 批准 ∩ 每次调用校验），拒绝发生在触达存储**之前**。
- **易用性与安全性在关键处同向**：去掉 `scope` 参数同时做到了更安全和更简单；用 contextvar 同时做到了并发正确和写法自然；只读接口同时挡住了持久化投毒和 API 表面膨胀。
- 实测 31 项自动化 + 端到端真实数据验证（含跨群泄露检测）。
- 全量 **482 passed / 1 skipped**，`ruff` 零告警。
- 未做美化：同进程模型下仍有反射攻击面，已如实列入 §5，并指向进程隔离的分层结论。

---

## 8. 后续补充：三项「API 有了、调用方没有」的能力（0.1.0）

本文件成稿时，`ctx.tool` / `ctx.on_notice` / 群管动作三者的**宿主侧实现都已存在**且测试
通过，但都没有接到任何生产路径上。这种形态比"未实现"更危险：文档和面板都在宣称能力，
而调用方为零。0.1.0 修复如下。

### 8.1 工具调用（`ctx.tool`）

原来的断点有三处，缺一不可：

1. `PluginToolRegistry.available_for()` 零调用方；
2. `AIRequest` 没有 `tools` 字段，`AIEngine` 也无从传给 `ChatRequest`
   （Provider 层其实早已序列化 `tools`）；
3. 隔离模式下 worker 用同一帧上报命令与工具，宿主 `_load_isolated` 一律按**命令**注册，
   于是工具变成斜杠命令、`ctx._tools` 始终为空。

现在的路径与约束：

- 宿主按 `api[name]["kind"] == "tool"` 分流到 `register_proxied_tool`；
- `ModelStage` 在每轮把 `available_for(principal)` 的结果放进 `AIRequest.tools`；
- 模型返回 `tool_calls` 后，**逐次重新授权**再执行（模型决定调用谁，宿主决定能不能），
  结果以 `wrap_untrusted(kind="tool")` 的数据块回灌，最多 `MAX_TOOL_ROUNDS=2` 轮；
- 工具结果不走严格的 `role="tool"` + `tool_call_id` 回显，因为部分 OpenAI 兼容中转会
  丢弃或拒绝该形状。代价是模型无法完美接着原始工具结果链式推理，取舍写在
  `ai/engine.py` 的 `AIRequest.tool_note` 注释里。

### 8.2 通知（`ctx.on_notice`）

断点同样三处：OneBot 适配器 `if post_type != "message": return` 丢弃全部通知、
`Adapter.emit` 对非 MESSAGE 事件提前 return、`PluginManager.on_notice` 无调用方。

现在：`OneBot11Adapter._to_notice` 把群通知归一化成扁平 dict（`type` / `sub_type` /
`group_id` / `user_id` / `operator_id` / `target_id`），`emit` 放行 `NOTICE`，
`BotRuntime._on_notice` 构造 `CallerContext` 后分发。通知**不经过流水线**：它不需要
"是否被呼叫""是否有权限"这类判断，走准入会让"某人被禁言"因为"没 @ 机器人"而被拒。

私聊通知（`friend_recall` 等）显式拒绝——`CallerContext` 围绕"会话"建模，群通知能
无歧义描述会话，私聊通知不能。

### 8.3 群管动作

`Capability.MUTE/KICK/RECALL/GROUP_LIST` 之前只有声明。现在 `Adapter` 基类提供四个
带默认实现的方法（未声明能力时返回明确失败而非 `AttributeError`），OneBot 端用
`set_group_ban` / `set_group_kick` / `delete_msg` / `get_group_list` 实现。

命令层的额外约束（`memory/stages.py`）：

- 新权限 `MODERATE_GROUP`（默认 ADMIN），与 `MANAGE_CONFIG` 分开——允许一个群管清理
  刷屏，不等于允许他改 Provider 密钥；
- 目标权限必须**严格低于**调用者：否则管理员可以通过机器人禁言 owner，而 owner 无法
  从聊天里撤销（撤销同样是群管命令）；
- 拒绝目标为机器人自己、调用者自己、非法 QQ 号、非群聊；
- `/recall-msg` 要求该消息**在本会话归档中存在**（`MemoryStore.find_message`）：
  协议端删除接口只收裸消息 ID、不带群号，归属只能由宿主记录来证明，否则这就是一个
  跨群的删除原语。

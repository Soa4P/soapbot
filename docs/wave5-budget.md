# Wave 5：额度审批工作流

**日期**：2026-10-28
**代码**：`src/soapbot/budget/`（`models.py` / `policy.py` / `store.py` / `commands.py`）
**接入点**：`memory/stages.py`（`CommandStage`）、`core/builder.py`、`config.py`、`memory/db.py`

---

## 0. 这一轮要解决什么

`budget/` 一直是空包，而 `Permission.APPROVE_PAYMENT` 从第一轮就定义了、被 `PERMISSION_MIN_ROLE` 映射到 `OWNER`，却**从未被任何代码检查过**。README 写着「额度审批工作流」，免责声明写着「所有消费均需人工二次授权」。

也就是说：一个只存在于类型定义里的权限，和一段只存在于文档里的承诺。Wave 5 把它们变成可执行的东西。

---

## 1. 功能边界（先说清楚不做什么）

### 1.1 这是一个**授权账本**，不是支付系统

| 做 | 不做 |
|---|---|
| 记录"某人申请花 X" | 不持有任何支付凭据 |
| 记录"另一个人批准了" | 不调用任何支付 API |
| 按周期统计配额 | 不自动扣款 |
| 超额时拒绝 | 不存储收款账号 |

终态是 `APPROVED`，含义是**一个有权限的人说了"可以"**，而不是"钱已经付了"。

这条边界听起来像免责话术，但它有一个具体的代码后果：`spend_requests` 表里**没有** `paid_at`、没有 `payment_token`、没有 `executed` 标记。理由写在 schema 的 docstring 里——一个"为将来预留"的 `paid_at` 列，就是账本慢慢变成支付系统的开始，而没有人会为此做一次决定。

### 1.2 不做 Web API 路由（本轮）

`app.py` 的注释已经写明：现有 router 全部无鉴权，必须等 Wave 7 的 JWT 就位才能对外。此时新增 `/api/budget/*` 会造出一个**没有身份验证的审批接口**——比不提供更糟。因此本轮只做命令层（`/budget`），路由留到鉴权就位之后。

### 1.3 默认关闭

`enable_budget: bool = False`。理由：一个没人配置的额度账本会注册 `/budget` 命令，读起来像一个可用的管控措施，实际不约束任何东西。**只有被显式开启的管控才是管控。**

---

## 2. 模块结构

```
budget/
  models.py    领域模型：金额、状态机、异常类型
  policy.py    配额策略：周期、上限、TTL、币种
  store.py     持久化与不变量：原子预留、审批、过期
  commands.py  /budget 命令族
```

分层理由：`store.py` 不认识 `PipelineContext`，`commands.py` 不认识 SQL。这样账本的不变量可以脱离聊天框架单独测试（见 `tests/test_wave5_budget.py`，46 项）。

---

## 3. 三条必须成立的不变量

### 3.1 金额是整数最小单位，永远不用浮点

```python
parse_amount("0.29")  # -> 29，不是 28.999999999999996
sum(parse_amount("0.29") for _ in range(100))  # -> 2900，精确
```

浮点账本会漂移：批准额之和最终不等于记录的总额，并且在边界上会**多批一笔**。所以：

- 存储一律 `amount_minor: int`（分）
- 用户输入只在 `parse_amount` 一处转换，舍入规则只有一份
- 两位以上小数**报错**而非静默舍入（`10.005` 是半厘，猜错方向就是一笔无法解释的差额）

`nan` / `inf` / `1e9` / 负数全部拒绝——它们要么与任何上限比较都为真，要么静默变成 0。

### 3.2 并发请求不能超支（核心）

看起来最自然的写法是错的：

```python
# 错：check-then-act
committed = await sum_usage(...)
if committed + amount > cap:
    raise BudgetExceeded
await insert(...)
```

两个请求在同一毫秒到达，都读到同一个"可用余额"，都通过，账本就超支一笔。**单线程测试永远复现不了，生产负载下必然复现。**

正确做法是把比较放进 INSERT 本身：

```sql
INSERT INTO spend_requests (...)
SELECT ... 
WHERE (
    SELECT COALESCE(SUM(amount_minor), 0) FROM spend_requests
    WHERE session_key = :session_key AND period = :period
      AND status IN ('approved', 'pending')
) + :amount_minor <= :cap
```

SQLite 在一个写事务内完成读和写，并发写者会看到刚插入的行。`rowcount == 0` 即"会被拒绝"。

测试 `test_concurrent_creates_cannot_overrun_the_cap`：10 个并发 ¥50 请求对 ¥100 上限，**恰好 2 个成功**。

### 3.3 待批金额计入已用

上限比较的是 `committed + reserved`，不是 `committed`。

否则十笔待批请求每笔都被告知"剩余全部可用"，第十一次批准才超支——而它超支在**一个人已经批准之后**。预留（reservation）正是让并发检查有意义的东西。

---

## 4. 审批状态机

```
                 ┌──────── approve ────────► APPROVED  (计入已用)
                 │
PENDING ─────────┼──────── deny ───────────► DENIED    (释放配额)
  （占配额）      │
                 ├──────── cancel ─────────► CANCELLED (释放配额，仅申请人)
                 │
                 └──────── 超时 ───────────► EXPIRED   (释放配额)
```

### 4.1 释放路径和预留路径同样重要

一笔超时未处理的申请若**不释放**预留，可用配额会永久变小。症状是"额度莫名其妙越来越少"，而运维从界面上无法诊断——必须读这段代码才知道。

因此：

- `snapshot()` 读之前先扫过期（同一事务内）
- `sweep_expired()` 供后台 tick 跨作用域清理，不依赖任何人打开界面
- `approve()` 额外自己查时钟，不完全信任扫描——TTL 可能刚过而扫描还没跑

### 4.2 审批时的五道检查（顺序即语义）

| # | 检查 | 为什么单独一类 |
|---|---|---|
| 1 | 不在本作用域 | 与"不存在"返回**同一句话**，否则命令变成 id 探测器 |
| 2 | 非待批 | 重放防护：重复的批准（转发、重试、双击）不得重跑状态转移 |
| 3 | 自批 | 与"无权限"**不同的错误**，否则 owner 会去查自己的角色配置，而不是去找第二个人 |
| 4 | 已过期 | 查时钟，不信任扫描 |
| 5 | 预算重算 | 请求时查过不代表批准时仍成立：周期可能翻转、期间可能批了别的 |

---

## 5. 权限模型：`APPROVE_PAYMENT` 终于是真的

```python
Permission.APPROVE_PAYMENT: Role.OWNER   # 既有设计，未改动
```

`/budget` 本身只要 `USE_COMMAND`（查看额度不敏感、发起申请对成员开放——控制点是"必须另有他人批准"）。`approve` / `deny` 在 handler 内**二次校验** `APPROVE_PAYMENT`。

之所以不在 `COMMAND_PERMISSIONS` 表里统一声明：一张表无法表达"查看要 A 权限、决策要 B 权限、撤回要 C 规则"。所以入口按最宽要求授权，决策子命令各自收紧。

### 5.1 一个诚实的限制

`APPROVE_PAYMENT` 是 OWNER 级，而 OWNER 是最高级。加上"不能自批"，**单 owner 部署无法完成审批**。

这不是缺陷，是设计的直接推论：

- 不能为了"能用"把审批降到 ADMIN —— 那等于任何 bot 管理员都能动钱
- 不能为了"能用"允许自批 —— 那"二次授权"就是一句空话

正确做法是配两个 owner，或者关掉 `require_distinct_approver`（名字写得很直白，让运维知道自己把工作流降级成了确认框）。

---

## 6. 作用域：永远来自事件，永不来自参数

```python
session_key = ctx.event.session_key   # 不是 args
```

若作用域来自参数，`/budget 500 买书 --scope other:group:9` 就能花掉别的群的配额，而账本会忠实地记在别人的账上。这与 `/recall` 的规则完全一致。

跨群请求 id 一律"不存在"而非"禁止"——后者是存在性预言机。

---

## 7. 顺带修复的两个真实缺陷

### 7.1 唤醒词配 `/` 会静默废掉所有斜杠命令

`StripWakeWordStage` 会剥掉以唤醒词开头的文本。而 `/` 是合法唤醒词——一旦运维把它写进配置：

```
/budget  →  budget   →  CommandStage 不识别  →  空回复
```

`/recall`、`/kb`、`/forget` 全部一起失效，**没有任何报错**。空回复看起来像模型故障，实际是配置问题。

修复：命令前缀永不剥离。

```python
_COMMAND_PREFIXES = frozenset({"/", "!", "／", "！"})
```

测试：`test_strip_wake_never_removes_a_command_prefix`（4 个前缀）+ 一条守护"正常唤醒词仍然会被剥离"。

### 7.2 `_overrun_message` 在写事务内另开连接会争锁

初版在 `BudgetExceededError` 里重新读总额来生成错误消息，而那时当前事务还持有写锁——第二个连接读不到，回复会挂到 `busy_timeout`（5 秒）然后报 `database is locked`，用户看到的是一个与"额度不足"毫无关系的错误。

修复：先 `rollback()` 释放锁，再读、再抛。

---

## 8. 验证

### 8.1 测试

| 文件 | 数量 | 守护 |
|---|---|---|
| `tests/test_wave5_budget.py` | 46 | 金额精度、原子预留、并发超支、幂等、自批、重放、过期释放、作用域、审计 |
| `tests/test_wave5_commands.py` | 17 | 命令层权限、作用域钉死、用途必填、双击去重 |
| `tests/test_wave1_pipeline.py` | +5 | 唤醒词不得吞掉命令前缀 |
| 全量 | **585 passed, 3 skipped** | 无回归 |

### 8.2 端到端（走真实 `build_pipeline`）

`_probe_e2e_wave5.py` — 13/13：

```
[PASS] wiring: /budget answers through the real pipeline
[PASS] flow: member can request — 已提交申请 #1：¥25.50（买资料）
[PASS] flow: a different owner approves
[PASS] flow: approval moves reserved -> committed — 已用 ¥25.50 / 可用 ¥74.50
[PASS] authz: a member cannot approve — 抱歉，你没有执行该操作的权限。
[PASS] authz: an admin cannot approve (money is owner-only)
[PASS] authz: an owner cannot approve their own request
[PASS] scope: another group's spend is invisible here
[PASS] scope: a cross-group request id looks nonexistent
[PASS] replay: a double-tap reserves once
[PASS] pay: no reply ever claims the bot moved money
```

走真实管道（`GuardStage` 解析身份 → `AuthorizationStage` → `CommandStage` 派发），而不是直接调用 `BudgetCommands`。理由和隔离那一轮相同：**只做单元测试的组件，可以在从未接线的情况下全部通过。**

### 8.3 手工验收

```bash
# 开启
SOAPBOT_ENABLE_BUDGET=true

# 群里
/budget                    # 查看本期额度
/budget 25.5 买资料         # 发起申请
/budget list               # 待审批列表
/budget approve 1          # 需另一位 owner
/budget deny 1 不需要
/budget cancel 1           # 仅申请人
```

---

## 9. 需要人工确认的要点

1. **配两个 owner**，否则"他人审批"这条规则无法满足（见 §5.1）。或显式设 `require_distinct_approver=false` 并接受工作流降级。
2. **币种固定**，`budget_currency` 一部署一个。跨币种会让 1 USD 和 1 CNY 都"计 100"，是静默错账。
3. **周期时区**：`period_key` 用固定 +8 偏移，不随容器 `TZ` 变。异地部署应把偏移对齐到自己的零点，否则周期会在部署边界处出现"双倍上限"的窗口。
4. **上限是整数分**：`budget_period_cap_minor=50000` 表示 ¥500.00，不是 ¥50000。

---

## 10. 后续（不属于本轮）

- Wave 7 JWT 就位后再开放 `/api/budget/*` 只读视图
- ~~审批提醒（`render_pending_notice` 已备，尚未接 notice 通道）~~ —— 已接入：`budget/commands.py` 在回复里调用它，见 §11
- 额度策略按角色区分（当前全作用域统一上限）

---

## 11. 状态更新（Wave 6–10 完成后回填）

上节两项已落实，见 `docs/wave6-10-runtime-auth-webui.md`：

- ✅ 鉴权就位，只读视图 `GET /api/budget` 已开放（跨作用域查询仅限操作者令牌）
- ✅ `render_pending_notice` 已接入：审批/驳回后回复里追加剩余待批数量
- ⏳ 按角色区分额度上限：仍未实现，且**不建议**在没有明确需求前实现——
  它会把"本期上限"从一个可解释的数字变成一张表格

另外本轮补上了一个原设计没写的调度职责：**过期的预留必须有后台清扫**。
`BudgetStore.sweep_expired()` 现在由 `RuntimeScheduler` 每 30 秒调用一次，
不再依赖"有人刚好查看余额"来释放配额。

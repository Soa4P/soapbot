# 跨端信任级审计（2026-11-19）

**命题**：网页 / App / QQ 是弱执行端；桌面端是强执行端（键鼠注入、文件、命令）。强执
行端的权限与后果，不能因为弱端被攻破或被人诱导而被间接调用。本审计沿"弱端输入 →
桌面执行"的全部路径逐跳验证闸门，并给出修复。

**方法**：双代理分域收集（路径证据 / UI 与安装流）+ 攻击者×建设者双视角交叉判定。
**范围**：soapbot 主干（commit 9ea5d16）+ updatepilot v1.1.0。

---

## 路径矩阵与判定

| 路径 | 闸门链 | 判定 |
|---|---|---|
| A. 聊天命令 → 控制面注入（/act） | 入口 MANAGE_CONFIG(ADMIN+) → **签发 CONTROL_GRANT(OWNER)**（本次收紧）→ hold 内存态 → 急停现读 → flag+主机名 → 白名单 | ⚠→✅（收紧后） |
| B. 面板 API → 桌面（hold/kill） | OWNER + **token 凭据**（cookie 401，测试钉住）；服务端双钳制 | ✅ |
| C. 插件 → 桌面（control.act） | manifest 声明 → 人工批准勾选能力（面板逐项）→ guard 10/min 独立桶 → hold → 急停 | ✅ |
| D. 桌面壳自身 | Tauri：CSP 无通配、无远程资产、单实例；IPC 面受 boundary-audit 89 项覆盖 | ✅ |
| E. updatepilot（独立仓） | PR 内容纯文本不执行；bot 永不自合并（无 merge 逻辑）；GitHub_TOKEN 最小集 + README 明示 | ✅ |

## 已验证的既有闸门（逐条证据）

1. **命令入口防回环**：`CommandStage.run` 只解析 `clean_segments/event.segments`
   （真实入站消息），模型回复经适配器发出、不回灌管线——模型被诱导生成 "/act …"
   只会成为一条发出的消息，不会被执行。
2. **模型工具面不含控制**：模型工具 = PluginToolRegistry（TOOL 能力插件，逐个批准）
   + MCP（MANAGE_MCP=OWNER 配置、按角色分级暴露）——`act`/`control` 不在其中。
3. **弱端角色分级**：member 被攻破 → 无 USE_COMMAND 之外的权限，/act 入口即拒；
   guest 只能 VIEW_TIMELINE。
4. **hold/kill API**：OWNER + token（test_screen_kill_switch 钉住 403/401/422）。
5. **CONTROL 插件面**：能力批准是人工勾选（面板），10/min 独立桶（写面收紧），
   grant 不可写（隔离审查历史）。

## 发现与修复

### 🟠 P1（设计收紧，本次已修）：授权窗签发权 ADMIN → OWNER

* **触发路径**：QQ/网页弱端的 **admin** 账号被攻破或被诱导 → `/act grant` 自签授权窗
  → 强执行端（桌面）被间接调用——正是命题禁止的跨端升级路径。
* **对照**：同表 `APPROVE_PAYMENT`（花钱）与 `MANAGE_MCP`（开子进程通道）都是 OWNER
  ——键鼠注入的物理后果 ≥ 两者，档位却只有 ADMIN，属后果-档位错配。
* **修法（已落地）**：新增 `Permission.CONTROL_GRANT: OWNER`（principal.py，docstring
  写明跨端阻断线）；`/act grant` 在 handler 内 `principal.can(CONTROL_GRANT)` 二次查
  （budget approve/deny 的子命令内查先例）。**拉闸（revoke /panic）保持 ADMIN**：
  拉闸永远比给油便宜——不对称是有意的。
* **回归**：admin grant 拒绝 + owner 签发成功 + admin revoke 放行 + 权限表钉住。

### 🟡 P2（登记）

1. 面板 hold/kill 按钮对非 owner 仍渲染、由后端 403 兜底——前端隐藏角色 UI 是体验
   优化，非安全缺口（后端是闸）。
2. 参见 docs/reference-batch9-evaluation.md：窗口绑定/前台确认（dsh-world 输入）为
   控制面第三增量。

## 结论

收紧后，"弱端 → 桌面执行"的每条路径都需要 **OWNER 级决策 × 强端物理在位**：
弱端没有任何账号状态可以直接或间接驱动强执行端；急停现读闸在所有路径上高于一切。

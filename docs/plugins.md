# 插件系统

插件目录结构、能力授权、进程隔离与批准流程。

**写给：** 要写插件的人。

> 这部分从 `README.md` 搬出来，是为了让 README 只回答「是什么、怎么跑起来、坏了怎么办」。
> 内容没有删减。

---

## 插件系统

### 三步分离

```text
发现（只读清单） → 批准（运维按能力逐项授予） → 加载（执行代码）
```

前两步不会执行任何东西。批准记录持久化在 `data/plugin-approvals.json`，**与清单分开
存放**：清单由插件作者写，批准由运维写，插件更新不能把自己的新能力带成已授权。
启动时会自动加载**已批准**的插件——「批准过」是一个持续有效的决定，不是一次点击。

### 示例插件

四个示例随包发布在 `src/soapbot/examples/plugins/`，用
`soapbot.examples.bundled_plugins_dir()` 取路径：

| 插件 | 演示什么 |
|---|---|
| `echo` | 命令 + 工具注册；`/echo` 与模型可调用的 `echo_text` |
| `help` | 读取其他插件注册的命令，生成帮助列表 |
| `admin` | 敏感能力（`storage`）与角色门槛 |
| `remind` | `cron` 定时任务 + 发消息 |

它们**不会被自动启用**。把它们复制到 `data/plugins/` 后在面板里逐项检查能力并批准：

```bash
cp -r src/soapbot/examples/plugins/* data/plugins/
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force data\plugins | Out-Null
Copy-Item -Recurse -Force src\soapbot\examples\plugins\* data\plugins\
```

### 最小插件

```yaml
# data/my-plugin/plugin.yaml
name: my-plugin
version: 1.0.0
description: 最小示例
entry: main:Plugin
trust: community
capabilities: [command]
```

```python
# data/my-plugin/main.py
class Plugin:
    def setup(self, ctx):
        @ctx.command("hello", description="打个招呼")
        async def hello(caller, args):
            return f"你好，{caller.display_name}"
```

清单 `capabilities` 必须声明才能注册对应 API：`command` / `tool` / `cron` /
`message` / `notice` / `http` / `memory` / `kb` / `send` / `storage`。
详见 `docs/wave3-plugin-api.md` 与 `docs/plugin-security.md`。

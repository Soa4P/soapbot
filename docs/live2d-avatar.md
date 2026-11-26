# 人格形象（Live2D）：装模型、看预览、渲染器留给下一步

07 页展开一张人格卡时能看到「人格形象」区块。它读的是 `data/avatars/<persona_id>/`
里的 Live2D 模型；**没有模型是正常状态**，页面会告诉你该把什么放到哪里。

> **当前是占位渲染**：面板显示模型的首张贴图作为静态预览，并列出模型声明的动作与表情。
> 动画渲染需要 Cubism 运行时 + JS 封装（`pixi-live2d-display` 一类，MIT），本仓库还没
> 接。之所以先做这一层：发现、校验与文件服务是**不管有没有渲染器都必须正确**的部分，
> 而渲染器接入时它们不用改。

## 目录结构

```
data/avatars/<persona_id>/
    model.model3.json      # Cubism 设置文件（必须有）
    <name>.moc3            # 模型数据（必须有，且要在设置文件的 FileReferences.Moc 里）
    textures/*.png
    motions/*.motion3.json
    expressions/*.exp3.json
```

`<persona_id>` 是人格卡的 `id`（不是文件名、不是显示名）。

最小可用集合：一个 `*.model3.json` + 它引用的 `.moc3` + 至少一张贴图。Cubism 导出的
模型本身就是这个布局，直接整个目录拷进来即可，不需要改名。

## 限制（为什么有）

模型目录会通过 HTTP 提供给面板，所以它同时是一个**文件读取面**：

| 限制 | 值 | 理由 |
|---|---|---|
| 单文件 | 8 MiB | 超出的贴图会被请求处理器整块读进内存 |
| 目录总量 | 64 MiB / 400 个文件 | 同上，且防止误拖整个素材库 |
| 设置文件 | 512 KiB | `model3.json` 是几 KB 的文本，超出说明放错了文件 |
| 扩展名 | `.json` `.moc3` `.png` `.jpg` `.jpeg` `.wav` `.mp3` | 白名单。否则运营者的一个笔误（把 `.env` 放进来）就变成任意文件读取 |
| 路径 | 必须在 `data/avatars/<id>/` 内，符号链接一律拒绝 | `..`、绝对路径、链接都是逃逸手法；链接对「当素材读」的目录没有正当用途 |

超出上限时页面显示 `reason`（`too_large` / `settings_unreadable` / `no_moc` 等）并给出
提示，不会静默不显示。

## 换成真模型

把 Cubism 导出的模型目录整个拷到 `data/avatars/<persona_id>/`，刷新 07 页即可——没有
配置项、没有重启。换模型同理：覆盖目录内容。

模型资产版权（Cubism 模型授权）需自行确认；仓库不附带任何模型文件。

## 接渲染器时要动的地方

- 前端 `webui/src/components/PersonaAvatar.vue`：把静态 `<img>` 换成 canvas 渲染，
  读取同一份 `motions` / `expressions` / `textures`；
- 后端 `GET /api/personas/<id>/avatar` 的 `renderer` 字段由 `none` 变为实际渲染器标识，
  面板据此决定是否显示「占位」提示；
- 文件服务 `GET /api/personas/<id>/avatar/asset?path=…` 不需要改：`moc3`、贴图、
  动作 json 都已经在允许列表里。

「情绪 → 动作」的映射刻意没有写死在前端：模型之间动作组命名完全不同（`TapBody` /
`Idle` / 自定义），等渲染器接入时从模型声明里读，而不是猜。

## 相关

- 人格卡本身怎么写、怎么绑到群：[personas.md](personas.md)
- 自动成长与回滚：[persona-growth.md](persona-growth.md)

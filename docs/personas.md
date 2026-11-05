# 人格卡：怎么写、怎么绑到群

人格卡决定"它在谁面前是什么样子"。一个机器人可以有多张卡，按群、按人切换。

## 三步做出第一张

1. 复制模板：把 [`config/personas/_template.yaml`](../config/personas/_template.yaml) 复制到 `data/config/personas/`，重命名成你认得出的名字（文件名不影响绑定）。
2. 至少改这两行：

   ```yaml
   id: work-helper      # 绑定用它，不是文件名
   name: 工作助手
   ```

3. 重启服务，然后在面板第 07 页确认卡片出现在列表里。

> `config/personas/` 里的是**出厂模板**，首次启动会播种到 `data/config/personas/`。之后你改的都是 `data/` 那一份，所以 `git pull` 不会把你的卡改回去。

## 字段

| 字段 | 作用 | 不写会怎样 |
|---|---|---|
| `id` | 绑定用的唯一标识 | 必填 |
| `name` | 面板里显示的名字 | 必填 |
| `enabled` | 关掉这张卡 | 默认 `true` |
| `system_prompt` | 每次回答都带上的系统提示 | 空：能说话，但没有设定 |
| `style` | 一句话风格补充，追加在系统提示后 | 不加 |
| `max_reply_chars` | 回复字数上限 | 默认 500 |
| `temperature` | 采样温度，0 稳、1 放飞 | 用模型默认 |
| `locale` | 这张卡说什么语言 | 跟随进程默认 |
| `wake_words` | 额外唤醒词，叠加全局的 | 只用全局唤醒词 |
| `banned_words` | 禁止出现的说法 | 不限制 |
| `examples` | `user`/`assistant` 少样本 | 不提供 |

`max_reply_chars`、`banned_words`、`style` 会被拼进系统提示，所以它们对模型是**硬性要求**，不是后处理截断。

## 绑定：哪张卡在哪儿生效

绑定写在 `.env` 里，格式是 `群号:人格ID`，多个用逗号隔开：

```bash
SOAPBOT_GROUP_PERSONAS=123456789:work-helper,987654321:casual-talk
```

也可以直接在**面板第 07 页**的「人格绑定」里填，走的是同一个键，保存后提示重启。

生效顺序（前面的优先）：

```text
按人绑定  →  按群绑定  →  global_default  →  第一张 enabled 的卡
```

按人绑定目前没有 `.env` 入口（只有 `PersonaStore.bind_user` 这个 API），需要的话用插件或在代码里调用。

**填错会怎样**：`SOAPBOT_GROUP_PERSONAS` 里写了一个不存在的人格 ID，启动时会打一条 WARNING 并跳过那一对，其余照常生效。不会因为一个拼写错误让整张表失效。

## 常见问题

**改了卡，群里没变化。**
卡是启动时加载的。改文件后重启服务；面板里点「重载」只对面板自己的缓存有效，不改变已经在跑的进程。

**同一个群想换语气。**
新建一张卡、改 `.env` 里那个群对应的 ID、重启。不要直接改旧卡——你会同时改掉所有绑它的群。

**想让它只在某个群用某张卡，其他群用默认。**
只写那一个群：`SOAPBOT_GROUP_PERSONAS=123456789:work-helper`，没列出的群自动走 `global_default`。

**`id` 能中文吗？**
技术上能，但 `.env` 里用 `群号:人格ID` 的格式解析，中文和冒号容易踩坑。建议 `id` 只用小写英文、数字和短横线。

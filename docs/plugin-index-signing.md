# 插件索引签名（S-SUP-01）

索引是「有什么」的来源，签名是「这些文件确实是维护者发布的」的凭据。两者解决的是不同
问题，缺一不可：

| 检查 | 挡住什么 | 挡不住什么 |
|---|---|---|
| digest（`plugin_versions.json` 声明的 SHA-256） | 下载包被替换 | 索引本身被改：改索引的人可以声明自己的 digest，下游检查全部同意 |
| 签名（本文件） | 索引被改 | 已发布版本的源码本身有后门（那要靠审查与审批） |

一键安装要求两者都通过。**发现**不需要签名：手工上传 zip 依然可用（那条路本来就表示
「我手上就是这份字节」），只是仍然要人工审批能力清单。

## 信任锚

- 公钥**内嵌在代码里**：`src/soapbot/plugins/index_signature.py` 的
  `MARKET_PUBLIC_KEY_B64` / `MARKET_KEY_ID`。
- 私钥**离线、不在任何仓库里**，也不在任何 CI runner 上。
- 故意不做「从索引同源下载公钥」：那等于用被篡改的服务器验证自己被篡改的索引。

## 签名覆盖什么

`index.sig.json` 是一个分离签名，内容规范化后由 Ed25519 私钥签名：

```json
{
  "version": 1,
  "algorithm": "ed25519",
  "key_id": "c74ba4090e4ea9ca",
  "covers": {
    "plugin_versions.json": "sha256:…",
    "plugins.json": "sha256:…"
  },
  "signature": "base64…"
}
```

- 签名的是 `canonical_payload(covers)`：`{"algorithm","covers","version"}`，键排序、
  无空白、UTF-8 —— 签名是对字节的，两侧必须产出同一串字节。
- 文件摘要**按 LF 规范化后**计算：同一份 JSON 在 Windows（CRLF）与 CI（LF）下的
  checkout 字节不同，直接哈希会让维护者本机验签通过、CI 报"被篡改"（实测过）。规范化
  之后唯一检测不到的是纯换行翻转——那对 JSON 解析器毫无区别。
- 必须覆盖 `plugins.json`（目录本身）。只签元数据等于把「有什么」留给攻击者。
- `plugin_versions.json` 若被签名覆盖但没收到，一键安装拒绝：签名声明的内容必须对齐。
- 未知的覆盖文件名一律拒绝（签名范围是封闭集合，不是「随便多点也行」）。
- **不在签名范围内**：`blocked_versions.json` / `plugin_details.json` /
  `trusted_developers.json`。封禁的权威来源是随 soapbot 版本发布的本地表（远端只能
  加、不能减），详情与作者提示都不改变任何安装门槛 —— 签它们不增加保证，只会让每次
  文案改动都要重新签名。

## 维护者操作

```bash
# 只做一次：生成密钥（文件权限 0600，目录 ~/.soapbot）
python scripts/sign_plugin_index.py --generate-key ~/.soapbot/market-index-signing.key
# → 打印 MARKET_PUBLIC_KEY_B64 / MARKET_KEY_ID，粘贴进 index_signature.py 并发版

# 每次改动 plugins.json / plugin_versions.json 之后：
python scripts/sign_plugin_index.py --key ~/.soapbot/market-index-signing.key \
    --index-dir /path/to/soapbot-plugins

# CI 里不需要私钥，只验证（插件仓的 validate 工作流跑这条）：
python scripts/sign_plugin_index.py --verify --index-dir .
```

**私钥丢了怎么办**：换新密钥 → 更新内嵌公钥 → 发一个新版本 → 重新签名索引。代价是
「旧版本 soapbot 会拒绝新索引的一键安装」（它们只认旧公钥），所以密钥要有离线备份，
但不要放进仓库、云盘共享链接或任何会公开的地方。

## 配置

| 配置项 | 默认 | 说明 |
|---|---|---|
| `PLUGIN_INDEX_REQUIRE_SIGNATURE` | `true` | 索引无有效签名时拒绝一键安装（409）；发现与手工上传不受影响 |

关掉它只适合你自己签名的本地 fork 在调试时用；关掉会在日志留下 warning，审计里也能
看到拒绝记录（`plugin install refused: index unsigned`）。

## 抓取时的出站纪律（S-SUP-12）

索引、`index.sig.json` 和发布包的下载都忽略 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`
（`IndexClient._client()` 里 `trust_env=False`）。理由与项目其它出站路径一致：代理会把请求
送到进程内白名单从未看过的地方，而这里下的判断是「哪一份是维护者发布的索引」——能把请求
改道的人就能改道这个答案，签名与 digest 也就无从谈起。需要出网代理的环境请在部署侧做透明
代理或设置 `PLUGIN_INDEX_URL` 指向镜像，而不是放宽这条规则。

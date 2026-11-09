# 桌面端签名：Windows 代码签名证书怎么解决

先说结论：**没有证书不等于不能发安装包，只等于 Windows 会弹一次警告。** 这一页说明警告是怎么来的、有哪几条路、每条的真实门槛，以及仓库现在做到哪一步。

## 一、为什么会有警告

Windows 用 Authenticode 给可执行文件签名。没签名或签名不受信时，SmartScreen 会显示「Windows 已保护你的电脑」→「未知发布者」，用户必须点「更多信息」→「仍要运行」。

这与代码质量无关，只看两件事：**文件有没有签名**、**这个签名在微软的声誉库里够不够**。新证书即使有效，前几周也可能继续警告——声誉是按签名累计的。

## 二、五条路，按门槛从低到高

| 方案 | 费用 | 能消除警告吗 | 适用场景 |
|---|---|---|---|
| 不签名 | 0 | 不能，用户点两次 | 内测、自己用、源码分发 |
| 自签名证书 | 0 | 不能。除非用户手动把你的根证书装进「受信任的根证书颁发机构」，外部分发不现实 | 企业内部可控终端 |
| OV 代码签名 | 约 ¥1500–3000/年 | 需要声誉积累，新证书初期仍警告 | 有公司主体、能等几周 |
| EV 代码签名 | 约 ¥3000–6000/年 | 即时信任 | 面向公众下载的产品 |
| Azure Trusted Signing | 约 $10/月 | 即时信任（微软云签名） | 有 3 年以上营业执照的组织 |

价格随渠道和年限浮动，以证书商官网为准；这里给区间是为了说明量级，不是报价。

### 开源项目有两条免费/低价通道

这个仓库是公开的，可以走专门给开源项目的计划：

- **SignPath Foundation** —— 给通过审核的开源项目免费提供代码签名（含 EV），与 GitHub Actions 集成，签名在云端完成。需要项目公开、许可证合规、提交申请并等待审核。
- **Certum Open Source Code Signing** —— 约 €29 一次性（硬件介质）+ 免费证书，需要提供开源证明。

这两条的共同点是**都不需要在 CI 里放 USB 令牌**，这是关键，见下一节。

## 三、CI 上真正的卡点：硬件令牌

OV/EV 证书通常以 **USB 硬件令牌**形式发放，私钥不可导出。GitHub Actions 的 runner 是虚拟机，**无法插入 USB 令牌**。所以在 CI 里签名只有三种可能：

1. **云 HSM**：证书商提供的云签名服务（如 DigiCert KeyLocker、Azure Key Vault 托管），CI 用 API 调用签名；
2. **云端签名服务**：SignPath 这类，把文件传上去签完取回；
3. **不在 CI 签**：CI 产出未签名安装包作为构建产物，发布时在本地机器用 USB 令牌手工签名再上传。

第 3 条最省事，代价是发布流程多一步人工。

## 四、Tauri 2 里怎么接

Tauri 有两套完全不同的签名，**不要混**：

| 用途 | 配置位置 | 作用 |
|---|---|---|
| Windows 代码签名（Authenticode） | `bundle.windows.certificateThumbprint` 或 `bundle.windows.signCommand` | 消除 SmartScreen 警告 |
| 应用更新签名（updater） | 环境变量 `TAURI_SIGNING_PRIVATE_KEY` | 让已安装的客户端信任自动更新包，与 Windows 警告无关 |

**`TAURI_SIGNING_PRIVATE_KEY` 不能消除 SmartScreen 警告**，这一点经常被搞混。

代码签名有两种接法：

```jsonc
// 方式 A：证书装在 runner 的证书存储里（云 HSM 或已导入的 pfx）
"bundle": {
  "windows": {
    "certificateThumbprint": "<证书指纹>",
    "digestAlgorithm": "sha256",
    "timestampUrl": "http://timestamp.digicert.com"
  }
}
```

```jsonc
// 方式 B：外部签名命令（SignPath、Azure Trusted Signing、自定义脚本都走这条）
"bundle": {
  "windows": {
    "signCommand": { "cmd": "signpath-sign", "args": ["%1"] }
  }
}
```

`%1` 由 Tauri 替换成待签文件路径。

## 五、这个仓库现在的状态

**未签名，但安装包已经能出。**

- `desktop/src-tauri/tauri.conf.json` 里没有 `certificateThumbprint` / `signCommand`；
- 本机 Windows 实测 `cd desktop && npm run build` 产出
  `soapbot_0.1.0_x64-setup.exe`（47.48 MiB），`installer.nsi` 把冻结后的后端写进
  `$INSTDIR\binaries\soapbot-backend.exe`；
- CI 有 `desktop-bundle` job（Windows runner，`workflow_dispatch` 或 `v*` tag 触发），
  产出未签名安装包并上传 artifact。

**证书到位后要改的地方只有两处**，不需要动业务代码：

1. `tauri.conf.json` 的 `bundle.windows` 增加 `certificateThumbprint` 或 `signCommand`；
2. `desktop-bundle` job 增加「导入证书 / 调用签名服务」一步，密码放进 repository secret。

## 六、先不签名会怎样

可以接受。代价是具体的，不是抽象的：

| 影响 | 具体表现 |
| --- | --- |
| 用户第一次运行 | SmartScreen 全屏提示「Windows 已保护你的电脑」，要点「更多信息」→「仍要运行」 |
| 浏览器下载 | Edge/Chrome 可能提示「不常下载，可能有危险」，需要手动保留文件 |
| 某些杀软 | 未签名 + PyInstaller 打包的 exe 被误报的概率更高，可能需要加白 |
| 企业环境 | AppLocker / WDAC 组策略可能直接拦未签名 exe，这种情况必须先签名才能部署 |

不受影响：程序功能、面板访问、自动更新（Tauri updater 用独立密钥，与 Authenticode
无关）、CI 是否变绿、源码部署与 Docker 部署。

所以「先不申请证书」是合理的选择：先把安装包和双端链路跑通，等分发量上来再补签名。
届时代价不变——只改两处配置，不用重构。

## 七、如果只能选一条

按这个项目的形态（开源、无公司主体、要双端一键）：

1. **先申请 SignPath Foundation**（免费、云端、无需硬件令牌），审核通过后接 `signCommand`；
2. 审核不通过再考虑 **Certum 开源证书 + 本地人工签名**；
3. 两者都没有之前，保持「未签名 + 文档明示」，不要用自签名证书假装解决了问题——那只是把两次点击转移到「安装根证书」上，而且教用户信任任意根证书是更坏的安全习惯。

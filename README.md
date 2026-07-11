# ImmortalWrt 手动定制单设备云编译

用 GitHub Actions **纯手动**编译 ImmortalWrt / OpenWrt 固件。所有选项在网页上用下拉框选择，
**只编译你选中的那一个设备**，所有源码都在 workflow 运行时才拉取。

> 参考：[芋头小皮蛋的博客](https://www.cnblogs.com/virgil-zu/articles/19241688)、
> [rocks311/IMMWRT](https://github.com/rocks311/IMMWRT) 的定制思路。

---

## 目录结构

```
.github/workflows/
  Build.yml        # 主工作流：手动选参数 → 只编译单设备
  Auto-Clean.yml   # 手动清理旧运行记录 / Release
README.md
```

没有任何定时任务，不会自动跑。

---

## 使用

1. 把本仓库推送到你自己的 GitHub。
2. **Settings → Actions → General → Workflow permissions** 选 **Read and write**（发布 Release 需要）。
3. **Actions → Build → Run workflow**，按需选择下面的选项后点绿色按钮。
4. 编译完成后：
   - 在该次运行页面底部 **Artifacts** 下载；
   - 同时会在 **Releases** 里发布一份（按 `平台-设备-日期` 命名）。

---

## 可选项说明（Run workflow 界面）

| 选项 | 类型 | 说明 |
| --- | --- | --- |
| **source 源码仓库** | 下拉 | `immortalwrt/immortalwrt`(官方) / `VIKINGYFY/immortalwrt`(高通满血NSS) / `openwrt/openwrt`(原版) / `custom` |
| **custom_repo** | 输入 | 选 `custom` 时填 `owner/repo` |
| **branch 系统版本/分支** | 输入 | 决定"系统版本"。如 `openwrt-24.10`、`openwrt-23.05`、`master`、或某个 tag `v24.10.4` |
| **kernel 内核版本** | 下拉 | `默认内核`（跟随分支）/ `测试版内核`（启用 `CONFIG_TESTING_KERNEL`，部分平台有更高版本内核） |
| **device 设备型号** | 下拉 | **精选热门机型（约 300 项）**；其余机型选「⚙ 自定义」后在 `custom_device` 填写 |
| **custom_device** | 输入 | 选「自定义」时填，格式 `target/subtarget\|profile`，如 `mediatek/filogic\|xiaomi_redmi-router-ax6000` |
| **theme 主题** | 下拉 | `argon` / `bootstrap` / `material` / `design` |
| **plugins 预装插件** | 多行输入 | 每行一个包名，见下方 |
| **lan_ip 管理IP** | 输入 | 默认 `192.168.1.1` |
| **ssid WiFi名** | 输入 | 默认 `ImmortalWrt` |

### 关于"内核版本 / 系统版本 / 分支"
OpenWrt 的内核版本是**由分支决定**的（例如 `openwrt-24.10` 对应内核 6.6，`master` 对应 6.12）。
所以：
- 想换**系统大版本** → 改 `branch`（如 `openwrt-23.05` ⇄ `openwrt-24.10`）；
- 想在同一分支上用**更高的测试内核** → `kernel` 选「测试版内核」。

### 关于"设备型号"下拉
`device` 下拉**内置全部 877 个机型**（仓库支持的所有平台），直接选即可，无需手敲。下拉值是
`target/subtarget|profile` 形式（例如 `mediatek/filogic|cmcc_rax3000m`），工作流会自动拆出平台、子平台与设备。

下拉最底部有 **「custom」**：选它后在 `custom_device` 里填 `target/subtarget|profile`
（例如 `mediatek/filogic|xiaomi_redmi-router-ax6000`），即可编译列表内/外的任意设备。

> ⚠️ **实现要点**：`workflow_dispatch` 的 `options` **只支持纯字符串列表**，不支持 `name`/`value`
> 对象格式（用对象会导致整个输入被 GitHub 判为无效、所有值被拒、没有 Run 按钮）。因此下拉直接显示
> `target/subtarget|profile` 原始串。完整机型清单见仓库根目录 `devices.txt`（按平台分组，复制任一行即可）。

> 机型列表取自 ImmortalWrt / OpenWrt 源码里真实的 `define Device/<profile>`：MT798x / Rockchip / 高通 NSS 系列取自
> VIKINGYFY `main` 与 23.05 发布版，其余平台（MT7621 / MT76x8 / MT7622 / ATH79 / IPQ40xx / 树莓派）取自 23.05.5 发布版的 `profiles.json`。
> 不同分支的个别 profile 名可能有差异（如 `-stock` / `-ubootmod` 后缀），列表里没找到或编不出 → 选「custom」填对应分支的确切名即可。

常见 profile 示例（下拉里直接搜，或在 `devices.txt` 里找）：
- x86_64：`generic`
- 红米 AX6000（uboot）：`xiaomi_redmi-router-ax6000-ubootmod`
- 小米 AX3000T：`xiaomi_mi-router-ax3000t`
- 中国移动 RAX3000M：`cmcc_rax3000m`
- 京东云雅典娜（ipq60xx）：`jdcloud_re-ss-01`

### 关于"预装插件"
`plugins` 每行填一个包名，会被追加为 `CONFIG_PACKAGE_<名>=y`：
```
luci-app-ttyd
luci-app-upnp
luci-app-openclash
```
- feeds 里已有的包直接生效；
- 以下常用第三方插件写上名字会**自动从对应源拉取**：
  `luci-app-openclash`、`luci-app-passwall`、`luci-app-passwall2`、
  `luci-app-homeproxy`、`luci-app-nikki`；
- 写错 / 不存在的包会被 `make defconfig` 自动忽略，不会导致失败。

---

## 高通 NSS 提示
需要**满血 NSS 硬件加速**（`qualcommax` 平台）时，`source` 要选 `VIKINGYFY/immortalwrt`、
`branch` 用它的 `main`。官方 `immortalwrt/immortalwrt` 不含满血 NSS 驱动。

## 资源提示
- 单设备编译在 GitHub 免费 runner 上一般 1~2 小时；单任务上限 6 小时。
- 首次编译要从零构建工具链，最慢；产物一般几十 MB ~ 几百 MB（x86 稍大）。

# ImmortalWrt 手动定制单设备云编译

用 GitHub Actions **纯手动**编译 ImmortalWrt / OpenWrt 固件。所有选项在网页上用下拉框选择，
**只编译你选中的那一个设备**，所有源码都在 workflow 运行时才拉取。

> 参考：[芋头小皮蛋的博客](https://www.cnblogs.com/virgil-zu/articles/19241688)、
> [rocks311/IMMWRT](https://github.com/rocks311/IMMWRT) 的定制思路，
> 以及 [hzyitc/openwrt-redmi-ax3000](https://github.com/hzyitc/openwrt-redmi-ax3000) 的分段编译（tools/install → toolchain/install → make）方式。

---

## 目录结构

```
.github/workflows/
  Build.yml        # 主工作流：手动选参数 → 只编译单设备
device-map.txt   # 中文设备名 ↔ target/subtarget|profile 映射（工作流运行时反查用）
devices.txt      # 全部 877 个机型原始 profile 清单（自定义时复制用）
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
| **branch 系统版本/分支** | 下拉 | 真实分支：`openwrt-24.10` / `openwrt-23.05` / `openwrt-22.03` / `master`；clone 前用 `git ls-remote` 校验该分支/tag 是否真实存在于所选源码仓库，不存在则列出可用分支并中断 |
| **kernel 内核版本** | 下拉 | `自动（源码默认）` / `5.15` / `6.1` / `6.6` / `6.12`：**运行时读取所选目标源码实际支持的内核列表**，选具体版本则校验该目标是否支持，不支持回退默认并 `::warning`；选「自动」用分支自带内核 |
| **device 设备型号** | 下拉 | **全部 877 个机型，以「中文名」显示**（如 `小米 AX6000`、`网件 RAX120`、`X86 软路由`）；列表外的机型选「⚙ 自定义」后在 `custom_device` 填写 |
| **custom_device** | 输入 | 选「自定义」时填，格式 `target/subtarget\|profile`，如 `mediatek/filogic\|xiaomi_redmi-router-ax6000` |
| **theme 主题** | 下拉 | `argon` / `bootstrap` / `material` / `design` |
| **plugins 预装插件** | 多行输入 | 每行一个包名，见下方 |
| **lan_ip 管理IP** | 输入 | 默认 `192.168.1.1` |
| **ssid WiFi名** | 输入 | 默认 `ImmortalWrt` |

### 关于"内核版本 / 系统版本 / 分支 / 插件"（全部按源码实际支持情况处理）
工作流的**内核、分支、插件、设备都以所选源码实际支持情况为准**，不是写死的例子：

- **系统版本（branch）**：下拉是真实分支名；clone 前用 `git ls-remote` 校验该分支/tag 是否真的存在于所选 `source` 仓库，
  不存在就列出可用分支并中断，避免编到一个不存在的分支。
- **内核（kernel）**：下拉给出的是真实内核版本（5.15 / 6.1 / 6.6 / 6.12，现代 ImmortalWrt/OpenWrt 已无 4.x）。
  编译时工作流读取该目标 `target/linux/<plat>/Makefile` 的 `KERNEL_PATCHVER` / `KERNEL_TESTING_PATCHVER`
  以及 `linux-*` 目录，**得出该目标源码实际支持的内核列表**：
  - 选「自动（源码默认）」→ 直接用分支自带内核；
  - 选具体版本（如 `6.6`）→ 若在该目标支持列表里，就改写 Makefile 切过去（测试版内核额外加 `CONFIG_TESTING_KERNEL=y`）；
    若不支持，则回退默认并在日志 `::warning` 提示。
- **设备（device）**：中文名下拉里的每一项都对应源码里真实的 `define Device/<profile>`；
  编译前会校验该设备是否真的存在于所选源码目标，不存在则 `::error` 中断。
- **插件（plugins）**：编译时会校验每个插件是否真实存在于源码/feeds（`tmp/.config-package.in`），
  不存在的会 `::warning` 并跳过，不会导致失败。

### 关于"设备型号"下拉
`device` 下拉**内置全部 877 个机型**，但显示为**中文名**（品牌 + 型号，如 `小米 AX6000`、`网件 RAX120`、
`X86 软路由`、`瑞莎 Rock 5B`、`香橙派 Orangepi 5`），比原来的 `target/subtarget|profile` 原始串更直观、更短。

下拉最底部有 **「⚙ 自定义」**：选它后在 `custom_device` 里填 `target/subtarget|profile`
（例如 `mediatek/filogic|xiaomi_redmi-router-ax6000`），即可编译列表内/外的任意设备。

> ⚠️ **实现要点**：`workflow_dispatch` 的 `options` **只支持纯字符串列表**，不支持 `name`/`value`
> 对象格式（用对象会导致整个输入被 GitHub 判为无效、所有值被拒、没有 Run 按钮）。
> 中文名与真实 `target/subtarget|profile` 的对应关系，保存在仓库根目录 **`device-map.txt`**
> （每行 `中文名|target/subtarget|profile`），工作流运行时用 `awk` 精确反查，你无需记忆任何代码。
> 完整清单也可直接看 `device-map.txt`。

> 机型列表取自 ImmortalWrt / OpenWrt 源码里真实的 `define Device/<profile>`：MT798x / Rockchip / 高通 NSS 系列取自
> VIKINGYFY `main` 与 23.05 发布版，其余平台（MT7621 / MT76x8 / MT7622 / ATH79 / IPQ40xx / 树莓派）取自 23.05.5 发布版的 `profiles.json`。
> 不同分支的个别 profile 名可能有差异（如 `-stock` / `-ubootmod` 后缀），列表里没找到或编不出 → 选「⚙ 自定义」填对应分支的确切名即可。

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
- 写错 / 不存在的包：编译时工作流会校验每个插件是否真实存在于源码/feeds（`tmp/.config-package.in`），不存在的会 `::warning` 并跳过，不会导致失败。

---

## 高通 NSS 提示
需要**满血 NSS 硬件加速**（`qualcommax` 平台）时，`source` 要选 `VIKINGYFY/immortalwrt`、
`branch` 用它的 `main`。官方 `immortalwrt/immortalwrt` 不含满血 NSS 驱动。

## 资源提示
- 单设备编译在 GitHub 免费 runner 上一般 1~2 小时；单任务上限 6 小时。
- 首次编译要从零构建工具链，最慢；产物一般几十 MB ~ 几百 MB（x86 稍大）。

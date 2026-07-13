#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_build.py —— 把 Build.yml 的三个下拉（系统版本/内核/设备）同步为
「所选源码仓库 + 官方最新发布渠道」真实支持的内容。

用法（在仓库根目录执行）：
  python3 scripts/update_build.py \
      --src-dir src \
      --repo immortalwrt/immortalwrt \
      --ref openwrt-24.10 \
      --build .github/workflows/Build.yml \
      --map device-map.txt

设计要点：
  - 设备：扫描 target/linux/**/image/{Makefile,*.mk} 里的 define Device/<profile>，
    得到 (target, subtarget, profile, title)；中文名优先复用旧 device-map.txt 里
    同 profile 的名字（保持连续、减少抖动），新设备按品牌词翻译自动起名。
  - 内核：扫描 target/linux/*/Makefile 的 KERNEL_PATCHVER / KERNEL_TESTING_PATCHVER，
    取并集作为真实可选内核（首项固定为「自动（源码默认）」）。
  - 系统版本/分支：git ls-remote --heads，列出所有 openwrt-* 分支（按版本倒序）+ master。
  - 回写：只替换 Build.yml 中 branch/kernel/device 三个 options 块与各自 default，
    其余（source、custom_device、theme、plugins、编译步骤等）原样保留。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# 品牌词 → 中文（用于给新设备自动起短名）
# ----------------------------------------------------------------------------
BRAND_MAP = {
    "xiaomi": "小米", "mi": "小米", "redmi": "红米",
    "netgear": "网件", "linksys": "领势", "glinet": "GL.iNet", "gl": "GL.iNet",
    "tplink": "TP-Link", "tp-link": "TP-Link", "tplinkjp": "TP-Link",
    "huawei": "华为", "zte": "中兴", "cmcc": "中国移动", "chinamobile": "中国移动",
    "china": "中国移动", "friendlyarm": "友善", "friendlyelec": "友善", "nanopi": "友善",
    "raspberrypi": "树莓派", "raspberry": "树莓派", "orangepi": "香橙派",
    "banana": "香蕉派", "bananapi": "香蕉派", "bpi": "香蕉派",
    "asus": "华硕", "dlink": "友讯", "d-link": "友讯", "tenda": "腾达",
    "mercusys": "水星", "qnap": "威联通", "ubiquiti": "Ubiquiti",
    "edgecore": "EdgeCore", "mikrotik": "MikroTik", "ruijie": "锐捷",
    "reyee": "锐捷", "h3c": "新华三", "newwifi": "新路由", "youku": "优酷",
    "jdc": "京东云", "jdcloud": "京东云", "rockchip": "瑞芯微", "mediatek": "联发科",
    "synology": "群晖", "zyxel": "合勤", "belkin": "贝尔金", "buffalo": "巴法罗",
    "cudy": "Cudy", "glinet": "GL.iNet", "linksys": "领势", "yuncore": "云核",
    "wavlink": "Wavlink", "totolink": "TOTOLINK", "phicomm": "斐讯",
    "edge": "Edge", "armsoM": "ArmSoM", "pine64": "Pine64", "radxa": "瑞莎",
    "rock": "瑞莎", "libre": "Libre", "9tripod": "9Tripod", "fastrhino": "FastRhino",
    "lunzn": "Lunzn", "mmbox": "MMBOX", "widora": "Widora", "aria": "AriaBoard",
    "photonicat": "Photonicat", "ezpro": "EZPro", "cyber": "Cyber", "huake": "华科",
    "linkease": "LinkEase", "lyt": "LYT", "nlnet": "NLnet", "xiguapi": "西瓜皮",
    "firefly": "Firefly", "fastrhino": "FastRhino", "roclink": "RocLink",
    "sipeed": "Sipeed", "seeed": "Seeed", "odroid": "Odroid", "kooiot": "KooIoT",
}

# 设备命名时尽量保留的“型号词”前缀（不翻译）
KEEP_AS_IS = set()


def translate_token(tok: str) -> str:
    t = tok.lower().strip(" -_./")
    if t in BRAND_MAP:
        return BRAND_MAP[t]
    return tok


# 镜像模板 / 基类关键词（这些 define Device/<X> 不是可刷写机型）
_TEMPLATE_KW = (
    "image with", "fitimage", "initramfs", "legacyimage", "ubifit", "dniimage",
    "fitzimage", "onhubimage", "tpsafeimage", "zyxelimage", "lantiq", "emmcimage",
    "sercomm", "kernel size", "dsa migration", "sysupgrade", "sdboot", "sdcard",
    "methode", "jboot", "bcm63xx", "lzma loader", "routerstation common",
    "meraki common", "template", "common$", "base$", "^nand$", "nand/", "default arm64",
)


def _is_real_profile(p: str) -> bool:
    """真实 OpenWrt 设备 profile 是空格-free 的 make 标识符，且不是镜像模板。"""
    if not p or re.search(r"\s", p):
        return False
    low = p.lower()
    return not any(re.search(k, low) for k in _TEMPLATE_KW)


def auto_name(title: str, profile: str) -> str:
    """根据 DEVICE_TITLE 或 profile 生成一个简短中文名。"""
    base = (title or "").strip()
    if not base:
        base = profile.replace("_", " ").replace("-", " ")
    # 按空格 / 下划线 / 连字符切词翻译品牌
    parts = re.split(r"[\s_\-]+", base)
    out = []
    for p in parts:
        if not p:
            continue
        out.append(translate_token(p))
    name = " ".join(out).strip()
    # 去重连的空格
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = profile
    return name


# ----------------------------------------------------------------------------
# 源码解析
# ----------------------------------------------------------------------------
def parse_version_key(s: str):
    """openwrt-24.10 -> (24,10)；非标准返回 (0,0)。"""
    m = re.search(r"(\d+)\.(\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def list_branches(repo: str):
    """返回 (branch_options, latest_release)。"""
    url = f"https://github.com/{repo}.git"
    try:
        out = subprocess.run(
            ["git", "ls-remote", "--heads", url],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception as e:
        print(f"::warning::ls-remote 失败: {e}")
        return [], None
    branches = []
    for line in out.splitlines():
        if "refs/heads/" in line:
            b = line.split("refs/heads/")[1].strip()
            branches.append(b)
    releases = sorted(
        [b for b in branches if b.startswith("openwrt-")],
        key=parse_version_key, reverse=True,
    )
    others = [b for b in branches if b in ("master", "main")]
    opts = releases + others
    latest = releases[0] if releases else (others[0] if others else None)
    return opts, latest


def scan_kernels(src_dir: str):
    """扫描 target/linux 下所有 Makefile 的 KERNEL_PATCHVER/TESTING。"""
    root = Path(src_dir) / "target" / "linux"
    vers = set()
    pat = re.compile(r"KERNEL_(TESTING_)?PATCHVER[:?]?=[\s]*([0-9]+\.[0-9]+)")
    files = list(root.glob("*/Makefile")) + list(root.glob("*/*/Makefile"))
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in pat.finditer(txt):
            vers.add(m.group(2))
    return sorted(vers, key=lambda v: tuple(map(int, v.split("."))))


def scan_devices(src_dir: str):
    """返回 list[(target, subtarget, profile, title)]，仅含真正被实例化的可刷写设备。

    关键点：源码里很多 `define Device/<X>` 是「镜像模板」（如 FitImage /
    Initramfs Image / bcm63xx cfe），并非真实机型。只有被
    `$(eval $(call Device,<X>))` 或 `TARGET_DEVICES += <X>` 实例化的，才是
    会出固件的真实设备。两遍扫描取交集。
    """
    root = Path(src_dir) / "target" / "linux"
    files = []
    for f in root.rglob("*"):
        if f.is_file() and (f.name == "Makefile" or f.suffix == ".mk"):
            if "image" in f.parts:
                files.append(f)

    def_pat = re.compile(r"define\s+Device/(\S+)\s*(?:#.*)?$")
    # 实例化：TARGET_DEVICES += foo  或  $(eval $(call Device,foo)) / BuildDevice
    inst_pat = re.compile(
        r"(?:TARGET_DEVICES\s*\+=\s*(\S+)|eval\s*\$\(call\s*(?:Device|BuildDevice)\s*,\s*(\S+?)\))"
    )

    defines = {}        # profile -> (target, subtarget, title)
    instantiated = set()
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = f.relative_to(root).parts
        idx = rel.index("image")
        pre = rel[:idx]
        target = pre[0]
        subtarget = pre[1] if len(pre) > 1 else pre[0]

        # 第一遍：收集 define Device/<profile> 及其标题
        in_def = False
        profile = ""
        title = ""
        buf = []
        for ln in txt.splitlines():
            if not in_def:
                m = def_pat.match(ln.strip())
                if m:
                    in_def = True
                    profile = m.group(1)
                    # define Device/Default 是基类模板，不是可刷写机型
                    if profile.strip().lower() == "default":
                        in_def = False
                        continue
                    title = ""
                    buf = []
                continue
            if ln.strip().startswith("endef"):
                for bl in buf:
                    bm = re.match(
                        r"\s*(DEVICE_TITLE|DEVICE_MODEL|DEVICE_NAME)\s*:?=\s*(.+)", bl
                    )
                    if bm:
                        title = bm.group(2).strip().strip('"').strip("'")
                        title = re.sub(r"\$\(.*?\)", "", title).strip()
                        break
                if profile and _is_real_profile(profile):
                    defines[profile] = (target, subtarget, title)
                in_def = False
                continue
            buf.append(ln)

        # 第二遍：收集被实例化的 profile
        for m in inst_pat.finditer(txt):
            p = (m.group(1) or m.group(2) or "").strip()
            if p:
                instantiated.add(p)

    # 取交集：只有既被定义、又被实例化的才是真实设备
    devs = []
    seen = set()
    for p, (t, s, title) in defines.items():
        if p in instantiated and p not in seen:
            seen.add(p)
            devs.append((t, s, p, title))
    return devs


# ----------------------------------------------------------------------------
# Build.yml 回写
# ----------------------------------------------------------------------------
ITEM_IND = "          "  # 10 空格（opt_line 再补 "- "）
OPT_IND = "        options:"  # 8 空格


def find_input(lines, key):
    for i, l in enumerate(lines):
        if re.match(r"^      " + re.escape(key) + r":\s*$", l):
            return i
    return -1


def replace_options(lines, key, new_items, new_default=None):
    """替换某个 input 的 options 块，可选更新 default。返回是否改动。"""
    i = find_input(lines, key)
    if i < 0:
        print(f"::warning::未找到 input 键 {key}")
        return False
    # 找 options: 行
    j = -1
    for k in range(i, min(i + 12, len(lines))):
        if lines[k].rstrip() == OPT_IND:
            j = k
            break
    if j < 0:
        print(f"::warning::{key} 下没有 options:")
        return False
    # 找 items 范围
    k = j + 1
    while k < len(lines) and re.match(r"^          - ", lines[k]):
        k += 1
    # 写回
    lines[j + 1:k] = new_items
    changed = True
    # 更新 default
    if new_default is not None:
        for d in range(i, j):
            if re.match(r"^      default:", lines[d]):
                lines[d] = f"      default: {new_default}"
                break
    return changed


def opt_line(v):
    v = v.replace('"', "'")
    return f'{ITEM_IND}- "{v}"\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-dir", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--map", required=True)
    args = ap.parse_args()

    build_path = Path(args.build)
    map_path = Path(args.map)
    lines = build_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # ---- 系统版本 / 分支 ----
    branch_opts, latest = list_branches(args.repo)
    if not branch_opts:
        branch_opts = [args.ref]
    if latest is None:
        latest = args.ref
    print(f"分支选项({len(branch_opts)}): {branch_opts}")
    print(f"官方最新发布渠道(latest-release) = {latest}")
    # 让 latest 排在最前（用户要“官方最新发布渠道”当默认/首位）
    ordered = [latest] + [b for b in branch_opts if b != latest]
    branch_items = [opt_line(b) for b in ordered]

    # ---- 内核 ----
    kernels = scan_kernels(args.src_dir)
    print(f"内核选项({len(kernels)}): {kernels}")
    kernel_items = [opt_line("自动（源码默认）")] + [opt_line(k) for k in kernels]

    # ---- 设备 ----
    devs = scan_devices(args.src_dir)
    print(f"扫描到设备 profile 数: {len(devs)}")

    # 旧映射：profile -> 中文名（连续保留），并记录旧下拉顺序
    # 过滤掉旧 device-map 里可能残留的镜像模板（profile 含空格/匹配模板关键词）
    old_map = {}
    old_order = []
    if map_path.exists():
        for ln in map_path.read_text(encoding="utf-8").splitlines():
            ps = ln.split("|")
            if len(ps) != 3:
                continue
            p = ps[2].strip()
            if not p or not _is_real_profile(p):
                continue
            if p not in old_map:
                old_map[p] = ps[0]
                old_order.append(p)

    # profile -> (target, subtarget, title)
    info = {}
    for (t, s, profile, title) in devs:
        info[profile] = (t, s, title)

    # 生成中文名（优先复用旧名），并全局去重
    name_by_profile = {}
    seen_names = set()
    for profile in info:
        t, s, title = info[profile]
        nm = old_map.get(profile) or auto_name(title, profile)
        if nm in seen_names:
            cand = f"{nm} ({s})"
            if cand not in seen_names:
                nm = cand
            else:
                c = 2
                while f"{nm} ({c})" in seen_names:
                    c += 1
                nm = f"{nm} ({c})"
        seen_names.add(nm)
        name_by_profile[profile] = nm

    # 排序：旧列表优先（保持旧顺序），新设备按 (target, subtarget, profile) 追加
    old_set = set(old_order)
    old_in_new = [p for p in old_order if p in name_by_profile]
    new_only = sorted(
        [p for p in name_by_profile if p not in old_set],
        key=lambda p: (info[p][0], info[p][1], p),
    )
    ordered = old_in_new + new_only

    # 下拉字符上限（GitHub 单输入 ~65535，留安全余量）
    MAX = 48000
    dropdown = []
    cum = 0
    for p in ordered:
        line = opt_line(name_by_profile[p])
        if dropdown and cum + len(line.encode("utf-8")) + 1 > MAX:
            break
        dropdown.append(line)
        cum += len(line.encode("utf-8")) + 1
    device_items = dropdown + [opt_line("⚙ 自定义")]

    # device-map.txt 存全量（无上限），保证自定义路径 + awk 反查覆盖所有机型
    full_sorted = sorted(
        name_by_profile.keys(),
        key=lambda p: (info[p][0], info[p][1], p),
    )
    new_map_lines = [
        f"{name_by_profile[p]}|{info[p][0]}/{info[p][1]}|{p}" for p in full_sorted
    ]

    # 设备 default：保留旧默认（若仍在下拉），否则取 X86 软路由 / 首个
    old_default = None
    for d in range(find_input(lines, "device"), len(lines)):
        if re.match(r"^      default:", lines[d]):
            old_default = lines[d].split(":", 1)[1].strip().strip('"')
            break
    drop_names = [name_by_profile[p] for p in ordered[: len(dropdown)]]
    if old_default in drop_names:
        new_device_default = old_default
    elif "X86 软路由" in drop_names:
        new_device_default = "X86 软路由"
    elif drop_names:
        new_device_default = drop_names[0]
    else:
        new_device_default = "⚙ 自定义"

    # ---- 回写 Build.yml ----
    replace_options(lines, "branch", branch_items, new_default=latest)
    replace_options(lines, "kernel", kernel_items, new_default="自动（源码默认）")
    replace_options(lines, "device", device_items, new_default=new_device_default)

    build_path.write_text("".join(lines), encoding="utf-8")
    map_path.write_text("\n".join(new_map_lines) + "\n", encoding="utf-8")

    print(f"device-map.txt 全量设备: {len(new_map_lines)} 个")
    print(f"device 下拉项数: {len(device_items)}（含自定义，受字符上限约束）")
    print(f"branch 默认 = {latest}；device 默认 = {new_device_default}")

    # ---- 健全性检查 ----
    # 1) 下拉里每个设备名都要能在 device-map 里反查到
    drop_names_set = set(drop_names)
    map_names = set(name_by_profile.values())
    missing = drop_names_set - map_names
    assert not missing, f"下拉存在未在 device-map 的设备: {missing}"
    # 2) 下拉字符占用不得超过 GitHub 单输入上限
    total_chars = sum(len(l.encode("utf-8")) + 1 for l in device_items)
    assert total_chars <= 65535, f"下拉字符数 {total_chars} 超出 GitHub 上限"
    print(f"下拉字符占用: {total_chars} / 65535")
    print("健全性检查通过 ✅")


    # ---- YAML safety: fix merged option lines with next key ----
    raw = build_path.read_text(encoding="utf-8")
    fixed = re.sub(
        r'(          - [^\n]*?)(      [a-z_]+:)',
        r'\1\n\2',
        raw,
    )
    if fixed != raw:
        # Second pass for safety
        fixed2 = re.sub(
            r'(          - [^\n]*?)(      [a-z_]+:)',
            r'\1\n\2',
            fixed,
        )
        if fixed2 != fixed:
            fixed = fixed2
        print("::notice::YAML safety: fixed merged option line(s) with next key")
        build_path.write_text(fixed, encoding="utf-8")
if __name__ == "__main__":
    main()

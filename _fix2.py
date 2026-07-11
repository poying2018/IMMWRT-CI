import yaml, re

SRC = ".github/workflows/Build.yml"
OUT = ".github/workflows/Build.yml"
CAP = 50  # 先测 50 项，验证"选项个数上限"假设

d = yaml.safe_load(open(SRC, encoding="utf-8"))
opts = d[True]["workflow_dispatch"]["inputs"]["device"]["options"]
curated = [o for o in opts if o["value"] != "custom"]
custom = [o for o in opts if o["value"] == "custom"]
curated = curated[:CAP]
new_opts = curated + custom
print("将 device 选项设为:", len(new_opts), "(含 custom)")

lines = open(SRC, encoding="utf-8").read().split("\n")
dev_start = next(i for i, ln in enumerate(lines) if ln == "      device:")
opt_idx = None; cust_idx = None
for i in range(dev_start + 1, len(lines)):
    if opt_idx is None and lines[i].strip() == "options:":
        opt_idx = i; continue
    if opt_idx is not None and re.match(r"^      [a-z_]+:", lines[i]):
        cust_idx = i; break
assert opt_idx and cust_idx
new_block = ['        options:']
for o in new_opts:
    new_block.append('          - name: "%s"' % o["name"])
    new_block.append('            value: "%s"' % o["value"])
open(OUT, "w", encoding="utf-8").write("\n".join(lines[:opt_idx] + new_block + lines[cust_idx:]))
print("已写回，替换行", opt_idx+1, "->", cust_idx)

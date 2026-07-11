#!/usr/bin/env bash
# IMMWRT-CI 一键推送脚本（Git Bash / WSL 使用）
# 前置：先在本机执行 `gh auth login` 完成 GitHub 登录（或 `gh auth login --with-token < PAT`）
set -euo pipefail

REPO_NAME="${1:-IMMWRT-CI}"
VISIBILITY="${2:-public}"   # public | private

if ! command -v gh >/dev/null 2>&1; then
  echo "未检测到 gh CLI，请先安装：https://cli.github.com/"
  exit 1
fi

gh auth status || { echo "请先运行: gh auth login"; exit 1; }

git add -A
git commit -m "Initial commit: IMMWRT manual single-device build action" || echo "(无新改动，跳过提交)"

# 若远程已存在则直接用，否则用 gh 创建
if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --push
else
  git push -u origin main
fi

echo "完成。仓库地址："
gh repo view --json url -q .url 2>/dev/null || true

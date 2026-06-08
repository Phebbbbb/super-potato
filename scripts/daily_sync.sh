#!/bin/bash
# 每日自动同步源码到 GitHub
set -e

REPO_DIR="/c/Users/23182/smart-tax"
cd "$REPO_DIR"

# 检查是否有变更
if [[ -z $(git status --porcelain) ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M')] 无变更，跳过提交"
    exit 0
fi

git add -A
git commit -m "chore: daily auto-sync $(date '+%Y-%m-%d')" --no-verify
git push origin master

echo "[$(date '+%Y-%m-%d %H:%M')] 源码已同步到 GitHub"

#!/usr/bin/env bash
# 把出片提交回 GitHub 的 results 分支（防止 Kaggle 会话超时丢成果）
# 用法：
#   export GITHUB_TOKEN=ghp_xxxx
#   bash kaggle/push_results.sh
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
W=/kaggle/working
: "${GITHUB_TOKEN:?请先 export GITHUB_TOKEN=你的GitHub令牌}"

mkdir -p "$REPO/results"
cp "$W"/ComfyUI/output/*.mp4 "$REPO/results/" 2>/dev/null || true
cp "$W"/ComfyUI/output/*.webm "$REPO/results/" 2>/dev/null || true
ls -lh "$REPO/results/"

cd "$REPO"
git -c user.name=kaggle -c user.email=kaggle@local checkout -B results
git add -f results
if git -c user.name=kaggle -c user.email=kaggle@local commit -m "results $(date +%F_%H%M)"; then
  git -c credential.helper= push -f \
    "https://x-access-token:${GITHUB_TOKEN}@github.com/zhangpengjuGitHub/music-mv.git" results
  echo "PUSH_OK"
else
  echo "没有新文件，跳过推送"
fi

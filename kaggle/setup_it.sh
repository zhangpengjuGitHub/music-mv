#!/usr/bin/env bash
# InfiniteTalk 部署（Kaggle T4 16G / working 19.5GiB）
# 幂等：已存在的目录/模型会跳过，中断后重跑安全
set -e
W=/kaggle/working
C=$W/ComfyUI
R=$W/music-mv
LOG=$W/setup_it.log
exec > >(tee -a "$LOG") 2>&1

echo "=== [1/5] 磁盘 ==="
df -h $W | tail -1

echo "=== [2/5] ComfyUI 核心 ==="
if [ ! -d $C ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI $C
fi
pip install -q -r $C/requirements.txt || echo "WARN: core deps 部分失败"
# transformers 必须 <5：v5 的 Wav2Vec2Encoder 不再返回 hidden_states，
# MultiTalkWav2VecEmbeds 会在 nodes.py:248 报 'NoneType' object is not subscriptable
# （Kijai issue #2052）。v5 装上后必须降级，否则 InfiniteTalk 口型音频编码必崩。
pip install -q "transformers==4.57.1" || echo "WARN: transformers 降级失败"

echo "=== [3/5] 自定义节点（WanVideoWrapper / KJNodes / VideoHelperSuite）==="
mkdir -p $C/custom_nodes
cd $C/custom_nodes
for repo in https://github.com/kijai/ComfyUI-WanVideoWrapper \
            https://github.com/kijai/ComfyUI-KJNodes \
            https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite; do
  d=$(basename $repo)
  [ -d "$d" ] || git clone --depth 1 $repo
  [ -f "$d/requirements.txt" ] && pip install -q -r "$d/requirements.txt" || true
done
echo "--- 工作流模板是否就位 ---"
ls $C/custom_nodes/ComfyUI-WanVideoWrapper/example_workflows/ | grep -i infinitetalk

echo "=== [4/5] 模型下载（预算内自动选档）==="
mkdir -p $C/models/diffusion_models $C/models/text_encoders $C/models/vae \
         $C/models/loras $C/models/clip_vision $C/models/wav2vec2
python $R/kaggle/dl_models.py --apply

echo "=== [5/5] 收尾 ==="
df -h $W | tail -1
du -sh $C/models/* 2>/dev/null
echo "SETUP_IT_DONE"

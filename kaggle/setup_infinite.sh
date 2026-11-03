#!/usr/bin/env bash
# InfiniteTalk 部署（Kaggle T4 16G / working 盘 19.5GiB）
# 目标：把 Wan2.2-S2V 环境原地改造成 InfiniteTalk
# 幂等：已存在的文件会跳过，中断后重跑安全
set -e
W=/kaggle/working
C=$W/ComfyUI
LOG=$W/setup_infinite.log
exec > >(tee -a "$LOG") 2>&1

echo "=== [1/5] 磁盘现状 ==="
df -h $W | tail -1

echo "=== [2/5] 删除 S2V unet 腾空间（约 11G）==="
rm -f $C/models/unet/*.gguf
rm -f $W/models/unet/*.gguf 2>/dev/null || true
df -h $W | tail -1

echo "=== [3/5] 安装 ComfyUI-WanVideoWrapper（InfiniteTalk 节点由它提供）==="
mkdir -p $C/custom_nodes
cd $C/custom_nodes
if [ ! -d ComfyUI-WanVideoWrapper ]; then
  git clone --depth 1 https://github.com/kijai/ComfyUI-WanVideoWrapper
fi
if [ -f ComfyUI-WanVideoWrapper/requirements.txt ]; then
  pip install -q -r ComfyUI-WanVideoWrapper/requirements.txt || echo "WARN: pip deps 部分失败，继续"
fi
ls $C/custom_nodes/ComfyUI-WanVideoWrapper/example_workflows/ 2>/dev/null | grep -i infinitetalk || true

echo "=== [4/5] 下载模型 ==="
mkdir -p $C/models/diffusion_models $C/models/clip_vision $C/models/text_encoders $C/models/vae

# 4a 基座：Wan2.1 I2V 14B 480P，GGUF Q4_K_M（通配匹配，避免文件名猜错）
#    注：不要用 FusionX 版本，它是 finetune，与 InfiniteTalk patch 兼容性存疑
cd $C/models/diffusion_models
if ! ls | grep -qi "i2v.*14b.*480p.*q4"; then
  python -m huggingface_hub download city96/Wan2.1-I2V-14B-480P-gguf \
    --include "*Q4_K_M*" --local-dir . --local-dir-use-symlinks False \
    || HF_HUB_ENABLE_HF_TRANSFER=0 huggingface-cli download city96/Wan2.1-I2V-14B-480P-gguf \
    --include "*Q4_K_M*" --local-dir . --local-dir-use-symlinks False
fi
ls -lh | tail -5

# 4b InfiniteTalk patch（单人版，fp8 scaled，约 1.9G，比 fp16 的 3.7G 省一半）
if ! ls | grep -qi "infinitetalk"; then
  wget -q -nc "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/InfiniteTalk/infinitetalk-single_fp8_e4m3fn_scaled_KJ.safetensors" \
    || wget -q -nc "https://huggingface.co/MeiGen-AI/InfiniteTalk/resolve/main/single/infinitetalk_single.safetensors"
fi

# 4c CLIP Vision H（I2V 必需，约 2.5G）
cd $C/models/clip_vision
if [ ! -f clip_vision_h.safetensors ]; then
  wget -q -nc "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/clip_vision_h.safetensors" \
    || wget -q -nc "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"
fi

# 4d 中文音频编码器（唱歌用中文更准；英文 wav2vec2 已存在也会保留）
mkdir -p $C/models/wav2vec2
cd $C/models/wav2vec2
if [ ! -f chinese-wav2vec2-base.bin ]; then
  wget -q -nc "https://huggingface.co/TencentGameMate/chinese-wav2vec2-base/resolve/main/pytorch_model.bin" -O chinese-wav2vec2-base.bin || echo "WARN: 中文 wav2vec2 下载失败，可退回英文版"
fi

echo "=== [5/5] 复用检查 + 磁盘 ==="
echo "--- text_encoders ---"; ls -lh $C/models/text_encoders/ 2>/dev/null | tail -3
echo "--- clip (umt5) ---";   ls -lh $C/models/clip/ 2>/dev/null | tail -3
echo "--- vae ---";           ls -lh $C/models/vae/ 2>/dev/null | tail -3
df -h $W | tail -1
echo "SETUP_INFINITE_DONE"

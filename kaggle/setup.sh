#!/usr/bin/env bash
# ---------------------------------------------------------------
# Kaggle 一键搭环境：ComfyUI + GGUF 插件 + Wan2.2-S2V 模型
#                 + 双卡服务 + cloudflared 公网隧道
# 用法（Kaggle 单元格）：
#   !git clone -q https://github.com/zhangpengjuGitHub/music-mv;bash music-mv/kaggle/setup.sh
# 幂等：重复执行会跳过已完成的步骤（会话崩了直接重跑这一条即可）
# ---------------------------------------------------------------
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
W=/kaggle/working
cd "$W"

echo "== 1/6 ComfyUI =="
if [ ! -d ComfyUI ]; then
  git clone --depth 1 -q https://github.com/comfyanonymous/ComfyUI
  git clone --depth 1 -q https://github.com/city96/ComfyUI-GGUF ComfyUI/custom_nodes/ComfyUI-GGUF
  pip install -q -r ComfyUI/requirements.txt gguf sentencepiece av 2>&1 | tail -2
else
  echo "ComfyUI 已存在，跳过"
fi

echo "== 2/6 模型（约 15GB，HuggingFace 直连）=="
M=$W/ComfyUI/models
mkdir -p "$M/unet" "$M/clip" "$M/vae" "$M/audio_encoders"
wget -c -q -P "$M/unet"           https://hf.co/QuantStack/Wan2.2-S2V-14B-GGUF/resolve/main/Wan2.2-S2V-14B-Q3_K_M.gguf
wget -c -q -P "$M/clip"           https://hf.co/city96/umt5-xxl-encoder-gguf/resolve/main/umt5-xxl-encoder-Q4_K_M.gguf
wget -c -q -P "$M/vae"            https://hf.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors
wget -c -q -P "$M/audio_encoders" https://hf.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/audio_encoders/wav2vec2_large_english_fp16.safetensors
du -sh "$M"/*

echo "== 3/6 素材 =="
mkdir -p "$W/ComfyUI/input"
cp "$REPO"/assets/*.wav "$REPO"/assets/*.jpg "$W/ComfyUI/input/" 2>/dev/null || true
ls -lh "$W/ComfyUI/input/"

echo "== 4/6 切块（4.7 秒/块，对应 length=77 帧 @16fps）=="
python "$REPO"/segments/cut_wav.py --in "$REPO"/assets/dseg_dry.wav --start 0   --dur 4.7 --out "$W/ComfyUI/input/dseg48a.wav"
python "$REPO"/segments/cut_wav.py --in "$REPO"/assets/dseg_dry.wav --start 4.7 --dur 4.7 --out "$W/ComfyUI/input/dseg48b.wav"

echo "== 5/6 工作流 JSON =="
if [ ! -f "$W/s2v_workflow.json" ]; then
  wget -q -O "$W/s2v_workflow.json" "https://hf.co/QuantStack/Wan2.2-S2V-14B-GGUF/resolve/main/workflow/QuantStack%20-%20Wan2.2%20S2V%20(GGUF).json"
fi
head -c 80 "$W/s2v_workflow.json"; echo

echo "== 6/6 起服务 + 隧道 =="
NGPU=$(nvidia-smi -L 2>/dev/null | grep -c GPU || true)
echo "检测到 GPU 数量: $NGPU"
cd "$W/ComfyUI"
CUDA_VISIBLE_DEVICES=0 nohup python main.py --listen 127.0.0.1 --port 8188 > "$W/comfy0.log" 2>&1 &
if [ "$NGPU" -ge 2 ]; then
  CUDA_VISIBLE_DEVICES=1 nohup python main.py --listen 127.0.0.1 --port 8189 > "$W/comfy1.log" 2>&1 &
fi
sleep 40
tail -2 "$W/comfy0.log"

if [ ! -f "$W/cf" ]; then
  wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O "$W/cf"
  chmod +x "$W/cf"
fi
nohup "$W/cf" tunnel --url http://127.0.0.1:8188 --no-autoupdate > "$W/cf0.log" 2>&1 &
if [ "$NGPU" -ge 2 ]; then
  nohup "$W/cf" tunnel --url http://127.0.0.1:8189 --no-autoupdate > "$W/cf1.log" 2>&1 &
fi
sleep 18
echo "GPU0 界面: $(grep -oE 'https://[a-z0-9-]+\.trycloudflare.com' "$W/cf0.log" | head -1)"
if [ "$NGPU" -ge 2 ]; then
  echo "GPU1 界面: $(grep -oE 'https://[a-z0-9-]+\.trycloudflare.com' "$W/cf1.log" | head -1)"
fi
echo "SETUP_DONE"

#!/usr/bin/env bash
# 看进度：日志 + 队列 + 已出片 + 显存
W=/kaggle/working
echo "=== GPU0 日志 ==="; tail -3 "$W/comfy0.log" 2>/dev/null
if [ -f "$W/comfy1.log" ]; then echo "=== GPU1 日志 ==="; tail -3 "$W/comfy1.log"; fi
echo "=== 队列 GPU0 ==="; curl -s --max-time 5 http://127.0.0.1:8188/queue | head -c 150; echo
if [ -f "$W/comfy1.log" ]; then
  echo "=== 队列 GPU1 ==="; curl -s --max-time 5 http://127.0.0.1:8189/queue | head -c 150; echo
fi
echo "=== 已出片 ==="; ls -lh "$W/ComfyUI/output/" 2>/dev/null | tail -12
echo "=== 显存 ==="; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv
echo "=== 磁盘 ==="; du -sh "$W" 2>/dev/null

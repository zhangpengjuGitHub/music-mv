# -*- coding: utf-8 -*-
"""打印 WanVideo 相关节点的 required 入参，用于把普通节点换成 MultiGPU 版本"""
import json
import urllib.request

WANT = [
    "WanVideoTextEncodeCached", "WanVideoTextEncodeCachedMultiGPU",
    "WanVideoVAELoader", "WanVideoVAELoaderMultiGPU",
    "WanVideoModelLoader", "WanVideoModelLoaderMultiGPU", "WanVideoModelLoaderMultiGPU_2",
    "WanVideoBlockSwap", "WanVideoBlockSwapMultiGPU",
    "WanVideoSampler", "WanVideoSamplerMultiGPU",
]

oi = json.load(urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=180))
print("== MultiGPU 变体 ==")
print([k for k in oi if "WanVideo" in k and "MultiGPU" in k])
for c in WANT:
    x = oi.get(c)
    if not x:
        print("MISSING", c)
        continue
    req = x.get("input", {}).get("required", {})
    print("--", c)
    print("   " + ",".join(req.keys()))
    for k in ("device", "base_device", "compute_device", "distorch_allocation",
              "virtual_vram_gb", "blocks_to_swap"):
        if k in req:
            print("   *%s=%s" % (k, json.dumps(req[k])[:120]))

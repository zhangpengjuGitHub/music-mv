# -*- coding: utf-8 -*-
"""Kijai InfiniteTalk 示例工作流(UI JSON) -> ComfyUI API 格式 -> 排队

解决四类问题：
1) SetNode/GetNode 是前端虚拟节点，API 里不存在 -> 转换时按名字回溯到真实来源
2) MelBand 人声分离节点用不上（我们喂的已是干声）-> 旁路，音频直连
3) wav2vec2 用 DownloadAndLoadWav2VecModel 会写 HF 缓存到别处 -> 换成本地 safetensors 加载器
4) 模型文件名不硬编码 -> 从 /object_info 的下拉项里按关键词挑，避免猜错

用法:
  python it_build.py --audio dseg48a.wav --image anchor_upload.jpg --seconds 15 --dry
  python it_build.py --audio dseg48a.wav --image anchor_upload.jpg --seconds 15
"""
import argparse
import json
import os
import sys
import urllib.request

HOST = "http://127.0.0.1:8188"
W = "/kaggle/working"
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
SKIP_TYPES = {"Note", "MarkdownNote", "PreviewAny", "SetNode", "GetNode",
              "Reroute", "RerouteNode", "WanVideoTorchCompileSettings",
              "MelBandRoFormerSampler", "MelBandRoFormerModelLoader"}
# 旁路：节点类型 -> 用它的哪个输入替代它的输出
BYPASS = {"MelBandRoFormerSampler": "audio", "MelBandRoFormerModelLoader": None}
# 显式改接：(目标节点, 输入名) -> (源节点, 输出槽)
REWIRE = {(194, "wav2vec_model"): (300, 0)}


def get(path):
    with urllib.request.urlopen(HOST + path, timeout=180) as r:
        return json.load(r)


def post(path, payload):
    req = urllib.request.Request(HOST + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


class Wf:
    def __init__(self, wf):
        self.nodes = {n["id"]: n for n in wf["nodes"]}
        self.links = {l[0]: l for l in wf["links"]}
        self.setmap = {}
        for n in wf["nodes"]:
            if n["type"] == "SetNode":
                name = (n.get("widgets_values") or [""])[0]
                ins = n.get("inputs") or []
                self.setmap[name] = ins[0].get("link") if ins else None

    def resolve(self, lid, depth=0):
        if lid is None or depth > 15:
            return None
        l = self.links.get(lid)
        if not l:
            return None
        src, slot = l[1], l[2]
        node = self.nodes.get(src)
        if node is None:
            return None
        t = node["type"]
        if t in ("SetNode", "Reroute", "RerouteNode"):
            ins = node.get("inputs") or []
            return self.resolve(ins[0].get("link") if ins else None, depth + 1)
        if t == "GetNode":
            name = (node.get("widgets_values") or [""])[0]
            return self.resolve(self.setmap.get(name), depth + 1)
        if t in BYPASS:
            key = BYPASS[t]
            if key is None:
                return None
            for i in node.get("inputs") or []:
                if i["name"] == key:
                    return self.resolve(i.get("link"), depth + 1)
            return None
        return (src, slot)


def names_of(oi, t):
    """该节点在 API 里的 widget 参数名（按定义顺序）"""
    spec = (oi.get(t) or {}).get("input") or {}
    order = (oi.get(t) or {}).get("input_order") or {}
    out = []
    for sec in ("required", "optional"):
        for k in order.get(sec) or list((spec.get(sec) or {}).keys()):
            v = (spec.get(sec) or {}).get(k)
            if not isinstance(v, list) or not v:
                continue
            first = v[0]
            if isinstance(first, list) or first in WIDGET_TYPES:
                out.append(k)
    return out


def combos(oi, t, key):
    spec = (oi.get(t) or {}).get("input") or {}
    for sec in ("required", "optional"):
        v = (spec.get(sec) or {}).get(key)
        if isinstance(v, list) and v and isinstance(v[0], list):
            return v[0]
    return []


def choose(oi, t, key, prefer, must_all=(), must_any=()):
    opts = [o for o in combos(oi, t, key)
            if ".cache" not in o and not o.lower().startswith("put_")]
    for p in prefer:
        for o in opts:
            n = o.lower()
            if p.lower() in n and all(k.lower() in n for k in must_all) and \
                    (not must_any or any(k.lower() in n for k in must_any)):
                return o
    for o in opts:
        n = o.lower()
        if all(k.lower() in n for k in must_all) and (not must_any or any(k.lower() in n for k in must_any)):
            return o
    return None


def build(oi, ui, audio, image, seconds, steps, seed, prefix, w, h, max_gb_left=None):
    f = Wf(ui)
    api = {}
    for nid, n in f.nodes.items():
        t = n["type"]
        if t in SKIP_TYPES:
            continue
        ins = {}
        wv = n.get("widgets_values")
        converted = {i["widget"]["name"] for i in (n.get("inputs") or []) if "widget" in i}
        if isinstance(wv, dict):
            for k, v in wv.items():
                if k in (names_of(oi, t) or []):
                    ins[k] = v
        else:
            wv = wv or []
            wv = [x for x in wv if not (isinstance(x, str) and x in
                                        ("randomize", "fixed", "increment", "decrement"))]
            nm = [x for x in names_of(oi, t) if x not in converted]
            for k, v in zip(nm, wv):
                if v is not None:
                    ins[k] = v
        for i in n.get("inputs") or []:
            if "widget" in i:
                continue
            key = (nid, i["name"])
            if key in REWIRE:
                ins[i["name"]] = [str(REWIRE[key][0]), REWIRE[key][1]]
                continue
            src = f.resolve(i.get("link"))
            if src is None:
                continue
            ins[i["name"]] = [str(src[0]), src[1]]
        api[str(nid)] = {"class_type": t, "inputs": ins}

    # ---- 覆写 ----
    frames = int(round(seconds * 25))
    A = api

    def setv(nid, **kv):
        if str(nid) in A:
            A[str(nid)]["inputs"].update(kv)

    setv(284, image=image)
    setv(281, width=w, height=h)
    setv(125, audio=audio)
    setv(245, value=w)
    setv(246, value=h)
    setv(270, value=frames)
    setv(128, steps=steps, seed=seed)
    setv(192, width=w, height=h)
    setv(131, filename_prefix=prefix, frame_rate=25)

    # 模型自动挑
    m = choose(oi, "WanVideoModelLoader", "model", ["Q4_K_M", "Q3_K_M"], ("14b", "i2v"))
    if m:
        setv(122, model=m, attention_mode="sdpa")
    else:
        print("WARN: WanVideoModelLoader 找不到 I2V 14B 基座")
    it = choose(oi, "MultiTalkModelLoader", "model", ["Q4_K_M", "Q5", "Q8", "Q6", "Q3"], ("infinitetalk",))
    if it:
        setv(120, model=it)
    else:
        print("WARN: MultiTalkModelLoader 找不到 InfiniteTalk 模型")
    te = choose(oi, "WanVideoTextEncodeCached", "model_name", ["fp8_e4m3fn"], ("umt5",))
    if te:
        setv(241, model_name=te, precision="fp8_e4m3fn")
    else:
        print("WARN: 找不到 umt5 文本编码器")
    vae = choose(oi, "WanVideoVAELoader", "model_name", ["bf16"], ("vae",))
    if vae:
        setv(129, model_name=vae)
    cv = choose(oi, "CLIPVisionLoader", "clip_name", ["clip_vision_h"])
    if cv:
        setv(238, clip_name=cv)
    else:
        api.pop("238", None)
        api.pop("237", None)
        if "192" in A:
            A["192"]["inputs"].pop("clip_embeds", None)
    w2v = choose(oi, "Wav2VecModelLoader", "model", ["chinese"], ())
    if w2v:
        setv(300, model=w2v, base_precision="fp16")
    api.pop("137", None)
    return api


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default="dseg48a.wav")
    ap.add_argument("--image", default="anchor_upload.jpg")
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20261103)
    ap.add_argument("--prefix", default="it_test")
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--workflow", default=None)
    a = ap.parse_args()

    wf_path = a.workflow or os.path.join(
        W, "ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper/example_workflows",
        "wanvideo_2_1_14B_I2V_InfiniteTalk_example_03.json")
    ui = json.load(open(wf_path, encoding="utf-8"))
    oi = get("/object_info")
    api = build(oi, ui, a.audio, a.image, a.seconds, a.steps, a.seed, a.prefix,
                a.width, a.height)
    out = os.path.join(W, "it_api.json")
    json.dump(api, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("nodes=%d -> %s" % (len(api), out))
    if a.dry:
        for k in sorted(api, key=lambda x: int(x)):
            print(" ", k, api[k]["class_type"])
        return
    r = post("/prompt", {"prompt": api})
    print(json.dumps(r)[:400])


if __name__ == "__main__":
    main()

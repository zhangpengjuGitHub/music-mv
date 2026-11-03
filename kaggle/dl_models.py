# -*- coding: utf-8 -*-
"""InfiniteTalk 模型选型 + 下载（Kaggle working 盘 19.5GiB 预算内）

用法：
  python dl_models.py --plan   只看方案（选哪些文件、多大、放哪），不下载
  python dl_models.py --apply  按方案下载（幂等，已存在跳过）

设计要点：
- 文件名不硬编码：用 HF API 查仓库真实文件树，按关键词 + 体积优选，避免猜错名白下十几 G
- 按磁盘预算动态降档：够则 Q4_K_M，不够退 Q3_K_M；clip_vision 是可选件，最后有余量才下
"""
import argparse
import json
import os
import sys
import urllib.request

HF = "https://huggingface.co/api/models/{}/tree/main?recursive=true"
W = "/kaggle/working"
C = os.path.join(W, "ComfyUI")
BUDGET_GB = 18.0          # 留 1.5G 给 ComfyUI/日志/成片
GB = 1024.0 ** 3


def tree(repo):
    with urllib.request.urlopen(HF.format(repo), timeout=120) as r:
        return [x for x in json.load(r) if x.get("type") == "file"]


def pick(repo, must=(), any_=(), ext=(), prefer=(), max_gb=None):
    """返回 (选中项, 全部候选)；选中项形如 (path, size_bytes)"""
    cands = []
    for x in tree(repo):
        n = x["path"].lower()
        if not all(k.lower() in n for k in must):
            continue
        if any_ and not any(k.lower() in n for k in any_):
            continue
        if ext and not n.endswith(tuple(ext)):
            continue
        cands.append((x["path"], x.get("size", 0)))
    if not cands:
        return None, []
    cands.sort(key=lambda t: t[1])
    for p in prefer:
        for c in cands:
            if p.lower() in c[0].lower() and (max_gb is None or c[1] <= max_gb * GB):
                return c, cands
    for c in cands:
        if max_gb is None or c[1] <= max_gb * GB:
            return c, cands
    return None, cands


def gb(n):
    return round(n / GB, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    plan = []   # (label, repo, path, size_bytes, dest_subdir)
    notes = []

    # ---------- 必装小件 ----------
    te, _ = pick("Kijai/WanVideo_comfy", must=("umt5-xxl-enc",), any_=("fp8_e4m3fn",),
                 ext=(".safetensors",), prefer=["fp8_e4m3fn"])
    if te:
        plan.append(("text_encoder", "Kijai/WanVideo_comfy", te[0], te[1], "text_encoders"))

    vae, _ = pick("Kijai/WanVideo_comfy", must=("wan2_1_vae",), any_=("bf16",),
                  ext=(".safetensors",), prefer=["bf16"])
    if vae:
        plan.append(("vae", "Kijai/WanVideo_comfy", vae[0], vae[1], "vae"))

    lora, _ = pick("Kijai/WanVideo_comfy", must=("lightx2v", "i2v", "14b", "480p", "rank64"),
                   ext=(".safetensors",))
    if lora:
        plan.append(("distill_lora", "Kijai/WanVideo_comfy", lora[0], lora[1], "loras"))

    w2v, _ = pick("Kijai/wav2vec2_safetensors", must=("chinese",), ext=(".safetensors",))
    if w2v:
        plan.append(("wav2vec2", "Kijai/wav2vec2_safetensors", w2v[0], w2v[1], "wav2vec2"))

    fixed = sum(p[3] for p in plan)

    # ---------- InfiniteTalk 单人口型模型 ----------
    it, it_all = pick("Kijai/WanVideo_comfy", must=("infinitetalk", "single"),
                      ext=(".gguf",), prefer=["Q8", "Q6", "Q5", "Q4", "Q3"])
    if it is None:
        it, it_all = pick("Kijai/WanVideo_comfy", must=("infinitetalk",), ext=(".gguf",),
                          prefer=["single", "Q5", "Q4"])
    if it is None:
        print("FATAL: Kijai/WanVideo_comfy 里找不到 InfiniteTalk GGUF。候选如下：")
        for p, s in pick("Kijai/WanVideo_comfy", must=("infinitetalk",))[1]:
            print("  %.2fG %s" % (gb(s), p))
        sys.exit(2)

    # 预算内挑 IT：给基座至少留 7.0G
    room = BUDGET_GB - fixed - 7.0
    it_pick = None
    for p in ["Q8", "Q6", "Q5", "Q4", "Q3"]:
        for c in sorted(it_all, key=lambda t: -t[1]):
            if p in c[0] and gb(c[1]) <= room:
                it_pick = c
                break
        if it_pick:
            break
    if it_pick is None:
        it_pick = min(it_all, key=lambda t: t[1])
        notes.append("IT 全部超预算，退最小档")
    plan.append(("infinitetalk", "Kijai/WanVideo_comfy", it_pick[0], it_pick[1], "diffusion_models"))

    # ---------- 基座 I2V 14B ----------
    left = BUDGET_GB - fixed - gb(it_pick[1]) - 0.8
    q = "Q4_K_M" if left >= 8.9 else "Q3_K_M"
    base, base_all = pick("city96/Wan2.1-I2V-14B-480P-gguf", must=(q.lower(),),
                          ext=(".gguf",))
    if base is None:
        base, base_all = pick("city96/Wan2.1-I2V-14B-480P-gguf", must=("q3_k_m",), ext=(".gguf",))
        notes.append("基座降级到最小可用档")
    plan.append(("base_unet", "city96/Wan2.1-I2V-14B-480P-gguf", base[0], base[1],
                 "diffusion_models"))

    # ---------- 可选：clip vision ----------
    used = fixed + gb(it_pick[1]) + gb(base[1])
    if BUDGET_GB - used >= 3.2:
        cv, _ = pick("Kijai/WanVideo_comfy", must=("clip_vision_h",), ext=(".safetensors",))
        if cv:
            plan.append(("clip_vision", "Kijai/WanVideo_comfy", cv[0], cv[1], "clip_vision"))
    else:
        notes.append("余量不足，跳过 clip_vision（工作流里可不用）")

    # ---------- 输出 ----------
    total = sum(p[3] for p in plan)
    lines = ["=== PLAN ==="]
    for label, repo, path, size, dest in plan:
        lines.append("%-14s %6.2fG  %s -> models/%s" % (label, gb(size), path, dest))
    lines.append("TOTAL %.2fG / 预算 %.1fG, 剩余 %.2fG" % (gb(total), BUDGET_GB,
                                                         BUDGET_GB - gb(total)))
    if notes:
        lines.append("NOTE: " + " | ".join(notes))
    lines.append("--- InfiniteTalk 全部候选 ---")
    for p, s in sorted(it_all, key=lambda t: t[1]):
        lines.append("  %6.2fG %s" % (gb(s), p))
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(W, "plan.txt"), "w").write(txt)

    if not a.apply:
        return

    # ---------- 下载 ----------
    from huggingface_hub import hf_hub_download
    for label, repo, path, size, dest in plan:
        target = os.path.join(C, "models", dest)
        os.makedirs(target, exist_ok=True)
        # 已存在同体积文件则跳过
        done = any(os.path.exists(os.path.join(r, os.path.basename(path)))
                   and os.path.getsize(os.path.join(r, os.path.basename(path))) == size
                   for r, _, _ in os.walk(target))
        if done:
            print("SKIP(exists) %s %s" % (label, os.path.basename(path)), flush=True)
            continue
        print("GET %s %.2fG %s" % (label, gb(size), os.path.basename(path)), flush=True)
        try:
            hf_hub_download(repo_id=repo, filename=path, local_dir=target)
            print("OK %s" % label, flush=True)
        except Exception as e:
            print("FAIL %s %s" % (label, str(e)[:200]), flush=True)
        st = os.statvfs(W)
        print("   free after: %.2fG" % (st.f_bavail * st.f_frsize / GB), flush=True)

    print("MODELS_DONE")


if __name__ == "__main__":
    main()

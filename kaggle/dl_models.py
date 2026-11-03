# -*- coding: utf-8 -*-
"""InfiniteTalk 模型选型 + 下载（Kaggle working 盘 19.5GiB 预算内）

用法：
  python dl_models.py --plan   只看方案（选哪些文件、多大、放哪），不下载
  python dl_models.py --apply  按方案下载（幂等；下载前检查剩余空间）

要点：
- 文件名不硬编码：用 HF API 查真实文件树，按关键词 + 体积优选
- InfiniteTalk 在多个仓库有不同格式（fp16 safetensors / fp8 scaled / GGUF），跨仓库比大小取最小可用
- 按剩余预算动态选基座量化档，装不下就降档，绝不让磁盘爆
"""
import argparse
import json
import os
import sys
import urllib.request

HF = "https://huggingface.co/api/models/{}/tree/main?recursive=true"
W = "/kaggle/working"
C = os.path.join(W, "ComfyUI")
BUDGET_GB = 18.6
GB = 1024.0 ** 3

IT_REPOS = ["Kijai/WanVideo_comfy_gguf",
            "Kijai/WanVideo_comfy_fp8_scaled",
            "Kijai/WanVideo_comfy"]


def tree(repo):
    with urllib.request.urlopen(HF.format(repo), timeout=90) as r:
        return [x for x in json.load(r) if x.get("type") == "file"]


def gb(n):
    return n / GB


def pick(repo, must=(), any_=(), ext=(), prefer=()):
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
    cands.sort(key=lambda t: t[1])
    for p in prefer:
        for c in cands:
            if p.lower() in c[0].lower():
                return c, cands
    return (cands[0] if cands else None), cands


def it_candidates():
    out, errs = [], []
    for repo in IT_REPOS:
        try:
            for x in tree(repo):
                n = x["path"].lower()
                if "infinitetalk" in n and "single" in n and \
                        (n.endswith(".gguf") or n.endswith(".safetensors")):
                    out.append((repo, x["path"], x.get("size", 0)))
        except Exception as e:
            errs.append("%s: %s" % (repo, str(e)[:60]))
    out.sort(key=lambda t: t[2])
    return out, errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    plan, notes = [], []

    # ---------- 小件 ----------
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

    # ---------- InfiniteTalk ----------
    its, errs = it_candidates()
    if not its:
        print("FATAL: 三个仓库都找不到 InfiniteTalk single 模型")
        for e in errs:
            print("  ", e)
        sys.exit(2)
    it = its[0]                     # 最小档
    plan.append(("infinitetalk", it[0], it[1], it[2], "diffusion_models"))

    # ---------- 基座 ----------
    left = BUDGET_GB - gb(fixed) - gb(it[2]) - 0.6
    order = ["Q4_K_M", "Q3_K_M"] if left >= 8.9 else ["Q3_K_M", "Q4_K_M"]
    base = None
    for q in order:
        base, base_all = pick("city96/Wan2.1-I2V-14B-480P-gguf", must=(q.lower(),), ext=(".gguf",))
        if base and gb(base[1]) <= left:
            break
        base = None
    if base is None:
        base, base_all = pick("city96/Wan2.1-I2V-14B-480P-gguf", ext=(".gguf",))
        notes.append("基座退最小档")
    plan.append(("base_unet", "city96/Wan2.1-I2V-14B-480P-gguf", base[0], base[1],
                 "diffusion_models"))

    # ---------- 可选 clip vision ----------
    used = gb(fixed) + gb(it[2]) + gb(base[1])
    if BUDGET_GB - used >= 3.0:
        cv, _ = pick("Kijai/WanVideo_comfy", must=("clip_vision_h",), ext=(".safetensors",))
        if cv:
            plan.append(("clip_vision", "Kijai/WanVideo_comfy", cv[0], cv[1], "clip_vision"))
    else:
        notes.append("余量不足，跳过 clip_vision")

    # ---------- 报告 ----------
    total = sum(p[3] for p in plan)
    L = ["=== PLAN ==="]
    for label, repo, path, size, dest in plan:
        L.append("%-13s %6.2fG  %s" % (label, gb(size), path))
    L.append("TOTAL %.2fG / 预算 %.1fG / 余 %.2fG" % (gb(total), BUDGET_GB, BUDGET_GB - gb(total)))
    if notes:
        L.append("NOTE: " + " | ".join(notes))
    L.append("--- InfiniteTalk 候选（跨仓库，已按体积升序）---")
    for repo, path, size in its:
        L.append("  %6.2fG %s :: %s" % (gb(size), path, repo.split("/")[-1]))
    for e in errs:
        L.append("  (repo 不可达) " + e)
    txt = "\n".join(L)
    print(txt)
    open(os.path.join(W, "plan.txt"), "w").write(txt)

    if not a.apply:
        return

    # ---------- 下载 ----------
    from huggingface_hub import hf_hub_download
    for label, repo, path, size, dest in plan:
        target = os.path.join(C, "models", dest)
        os.makedirs(target, exist_ok=True)
        base_name = os.path.basename(path)
        hit = None
        for r, _, fs in os.walk(target):
            if base_name in fs:
                hit = os.path.join(r, base_name)
                break
        if hit and os.path.getsize(hit) == size:
            print("SKIP %s" % label, flush=True)
            continue
        st = os.statvfs(W)
        free = st.f_bavail * st.f_frsize
        if free < size * 1.05:
            print("ABORT %s: 剩余 %.2fG 不足（需 %.2fG）" % (label, gb(free), gb(size)), flush=True)
            continue
        print("GET %s %.2fG %s" % (label, gb(size), base_name), flush=True)
        try:
            hf_hub_download(repo_id=repo, filename=path, local_dir=target)
            print("OK %s" % label, flush=True)
        except Exception as e:
            print("FAIL %s %s" % (label, str(e)[:160]), flush=True)
        st = os.statvfs(W)
        print("   free %.2fG" % gb(st.f_bavail * st.f_frsize), flush=True)
    print("MODELS_DONE")


if __name__ == "__main__":
    main()

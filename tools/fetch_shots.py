# -*- coding: utf-8 -*-
# 从 GitHub results 分支拉回 Kaggle 出片 -> 本地 04_shots/
import base64, json, os, sys
import requests

REPO = "zhangpengjuGitHub/music-mv"
BRANCH = "results"
REMOTE_DIR = "results"
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", "mvp01_\u711a\u8840\u9003\u5929_\u526f\u6b4c", "04_shots")
OUTDIR = os.path.abspath(OUTDIR)

TOKEN_PATH = r"D:\tmp\mv_audio\gh_token.txt"
if not os.path.exists(TOKEN_PATH):
    print("MISSING token file:", TOKEN_PATH)
    sys.exit(1)
TOKEN = open(TOKEN_PATH).read().strip()

S = requests.Session()
S.headers.update({
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "music-mv-fetcher",
})


def api(path, **kw):
    r = S.get(f"https://api.github.com{path}", timeout=120, **kw)
    return r


r = api(f"/repos/{REPO}/contents/{REMOTE_DIR}?ref={BRANCH}")
if r.status_code != 200:
    print("LIST FAIL", r.status_code, r.text[:300])
    sys.exit(1)
items = r.json()
if isinstance(items, dict):
    print("results branch not ready yet (no results dir)")
    sys.exit(0)

wanted = [it for it in items if it["type"] == "file" and it["name"].lower().endswith((".mp4", ".webm"))]
if not wanted:
    print("no video files on results branch yet")
    for it in items:
        print("  ", it["name"])
    sys.exit(0)

os.makedirs(OUTDIR, exist_ok=True)
print("OUT:", OUTDIR)
for it in wanted:
    sha = it.get("sha")
    dest = os.path.join(OUTDIR, it["name"])
    if os.path.exists(dest) and os.path.getsize(dest) == it["size"]:
        print("SKIP(already) ", it["name"], it["size"])
        continue
    rb = api(f"/repos/{REPO}/git/blobs/{sha}")
    if rb.status_code != 200:
        print("BLOB FAIL", it["name"], rb.status_code, rb.text[:200])
        continue
    data = base64.b64decode(rb.json()["content"])
    with open(dest, "wb") as f:
        f.write(data)
    print("GOT", it["name"], len(data), "bytes")

print("\nDONE. Drag the mp4 onto 2_qc_frames.bat to check lip-sync.")

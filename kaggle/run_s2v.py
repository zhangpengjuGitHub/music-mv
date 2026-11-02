#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
往已启动的 ComfyUI 实例排队一条 Wan2.2-S2V 任务。

用法：
  python run_s2v.py --port 8188 --audio dseg48a.wav --seed 20261101
  python run_s2v.py --port 8189 --audio dseg48b.wav --seed 20261102 --prefix fanren_b

原理：读取 QuantStack 官方 S2V 工作流 JSON（UI 格式），转换成 ComfyUI API 格式，
替换模型名 / 锚点图 / 音频 / 提示词 / 采样参数后 POST /prompt。
"""
import argparse
import json
import urllib.request

# ---- S2V 提示词（来自 comfy/prompts.txt【3】）----
PROMPT = (
    '东方玄幻修士半身立于崩裂的暗色空间中，黑袍染血，身周暗红灵光燃烧，'
    '人物正对镜头唱歌，面部从压抑转向爆发，口型随歌声开合。'
    '固定机位缓慢推近，血色雾气翻涌，远处追兵法宝的冷光闪烁，暗调，强对比，电影感。'
)
NEGATIVE = (
    '色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，'
    '最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，'
    '画得不好的手部，画得不好的脸，畸形的，毁容的，形态畸形的肢体，手指融合，'
    '静止不动的画面，杂乱的背景，三条腿，'
)

UNET = 'Wan2.2-S2V-14B-Q3_K_M.gguf'
CLIP = 'umt5-xxl-encoder-Q4_K_M.gguf'
VAE = 'wan_2.1_vae.safetensors'
AUDIO_ENC = 'wav2vec2_large_english_fp16.safetensors'
IMAGE = 'anchor_upload.jpg'

KEEP = [61, 54, 62, 6, 7, 63, 57, 58, 56, 52, 55, 3, 8, 59, 60]
DROP = {67, 68, 28, 47, 64, 65, 69}   # 预览/缩放类节点，其依赖包未安装，必须剔除


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8188, help='8188=GPU0, 8189=GPU1')
    ap.add_argument('--audio', default='dseg48a.wav')
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--seed', type=int, default=20261101)
    ap.add_argument('--prefix', default='fanren')
    ap.add_argument('--steps', type=int, default=10)
    ap.add_argument('--length', type=int, default=77, help='帧数，77 帧 ≈ 4.7 秒 @16fps')
    ap.add_argument('--width', type=int, default=832)
    ap.add_argument('--height', type=int, default=480)
    ap.add_argument('--cfg', type=float, default=6.0)
    ap.add_argument('--workflow', default='/kaggle/working/s2v_workflow.json')
    ap.add_argument('--dry', action='store_true', help='只打印不排队')
    a = ap.parse_args()

    host = 'http://127.0.0.1:%d' % a.port

    def u(p):
        return json.load(urllib.request.urlopen(host + p, timeout=60))

    oi = u('/object_info')
    wf = json.load(open(a.workflow))
    nodes = {n['id']: n for n in wf['nodes']}

    def wnames(t):
        spec = oi[t]['input']
        out = []
        for sec in ('required', 'optional'):
            for k, v in (spec.get(sec) or {}).items():
                if isinstance(v, list) and v and isinstance(v[0], str):
                    out.append(k)
        return out

    api = {}
    for i in KEEP:
        n = nodes[i]
        t = n['type']
        ins = {}
        wv = n.get('widgets_values') or []
        if isinstance(wv, dict):
            wv = [wv.get(k) for k in wnames(t)]
        wv = [x for x in wv if x not in ('randomize', 'fixed')]
        for k, val in zip(wnames(t), wv):
            if val is not None:
                ins[k] = val
        for inp in n.get('inputs', []):
            lid = inp.get('link')
            if lid is None:
                continue
            l = next(x for x in wf['links'] if x[0] == lid)
            src, slot = l[1], l[2]
            hops = 0
            while nodes[src]['type'] in ('RerouteNode', 'Reroute') and hops < 5:
                l2 = next(x for x in wf['links'] if x[3] == src)
                src, slot = l2[1], l2[2]
                hops += 1
            if src in DROP:
                continue
            ins[inp['name']] = [str(src), slot]
        api[str(i)] = {'class_type': t, 'inputs': ins}

    # ---- 覆盖为我们项目的参数（工作流默认值有错位，必须手动补）----
    api['61']['inputs']['unet_name'] = UNET
    api['62']['inputs']['clip_name'] = CLIP
    api['62']['inputs']['type'] = 'wan'
    api['63']['inputs']['vae_name'] = VAE
    api['57']['inputs']['audio_encoder_name'] = AUDIO_ENC
    api['52']['inputs']['image'] = a.image
    api['58']['inputs']['audio'] = a.audio
    api['6']['inputs']['text'] = PROMPT
    api['7']['inputs']['text'] = NEGATIVE
    api['6']['inputs']['clip'] = ['62', 0]
    api['7']['inputs']['clip'] = ['62', 0]
    api['55']['inputs'].update({
        'width': a.width, 'height': a.height, 'length': a.length, 'batch_size': 1})
    api['3']['inputs'].update({
        'seed': a.seed, 'steps': a.steps, 'cfg': a.cfg,
        'sampler_name': 'uni_pc', 'scheduler': 'simple', 'denoise': 1.0})
    api['54']['inputs']['shift'] = 8.0
    api['59']['inputs']['fps'] = 16
    api['60']['inputs']['filename_prefix'] = a.prefix

    print('--- 任务参数 ---')
    print('port=%d audio=%s seed=%s steps=%d length=%d %dx%d'
          % (a.port, a.audio, a.seed, a.steps, a.length, a.width, a.height))
    for k, v in sorted(api.items()):
        print(' ', k, v['class_type'],
              json.dumps({kk: str(vv)[:40] for kk, vv in v['inputs'].items()},
                         ensure_ascii=False))

    if a.dry:
        print('--- DRY RUN，未排队 ---')
        return

    body = json.dumps({'prompt': api}).encode('utf-8')
    req = urllib.request.Request(host + '/prompt', body,
                                 {'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    print('--- QUEUED ---')
    print(json.dumps(r, ensure_ascii=False))
    if r.get('node_errors'):
        print('!! 有节点错误，见上')
    else:
        print('OK prompt_id=%s' % r.get('prompt_id'))


if __name__ == '__main__':
    main()

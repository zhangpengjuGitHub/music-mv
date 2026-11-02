# music-mv · AI 音乐 MV 管线（Kaggle 一键运行）

《凡人修仙传》二创：把角色内心独白写成歌，用 AI 生成演唱画面。
当前曲目 **《焚血逃天》**，主角韩立。画面全部 AI 原创生成，不截原番一帧。

## 目录

```
music-mv/
├── kaggle/
│   ├── setup.sh        一键搭环境：ComfyUI + GGUF + 4 个模型 + 双卡服务 + 公网隧道
│   ├── run_s2v.py      参数化排队出片（音频 / seed / 步数 / 长度 / 端口）
│   ├── watch.sh        看进度：日志 + 队列 + 已出片 + 显存
│   ├── push_results.sh 把出片提交回 GitHub results 分支（需 GITHUB_TOKEN）
│   └── CELLS.md        复制粘贴用的 Kaggle 单元格
├── segments/
│   └── cut_wav.py      按起止时间切干声（整首歌分段用）
├── comfy/
│   └── prompts.txt     出歌 / 锚点图 / S2V 三套提示词
└── assets/
    ├── anchor_upload.jpg   锚点图（厚涂正脸，唇线清晰）
    ├── dseg_dry.wav        D 段干声 17 秒（副歌"焚！焚尽寿元开血路！"）
    ├── vocal_dry.wav       整首干声 194 秒
    └── precheck_speech.wav 五官预检用说话音频
```

## Kaggle 一键运行（3 条单元格）

第 1 条（约 8-10 分钟，下 15GB 模型）：

```
!git clone -q https://github.com/zhangpengjuGitHub/music-mv;bash music-mv/kaggle/setup.sh
```

第 2、3 条（两张卡各跑一块）：

```
!cd /kaggle/working/music-mv/kaggle;python run_s2v.py --port 8188 --audio dseg48a.wav --seed 20261101
!cd /kaggle/working/music-mv/kaggle;python run_s2v.py --port 8189 --audio dseg48b.wav --seed 20261102
```

看进度：

```
!cd /kaggle/working/music-mv/kaggle;bash watch.sh
```

## 三条铁律（踩过坑，别犯）

1. **出片必须立刻取回**。Kaggle 会话上限 12 小时，`/kaggle/working` 一清空就全没。
   用 `bash kaggle/push_results.sh`（设好 GITHUB_TOKEN）或从 Kaggle Output 面板手动下载。
2. **音频必须喂干声**。带伴奏的音频会让口型漂移。链路：出歌 → 换声 → Demucs 分离 → 干声喂 S2V。
3. **不要时间拉伸**。换声后不能拉伸，一拉口型就废。

## 模型与算力现状

- 模型：Wan2.2-S2V-14B **Q3_K_M**（11G，16G 卡的甜点档）+ umt5-xxl **Q4_K_M**（3.5G，
  Q8 要 13G 会撑爆 Kaggle 19.5G 磁盘上限）+ wan_2.1_vae + wav2vec2 音频编码器
- Kaggle T4×2 实测：10 步采样约 8 分钟/步，一块 4.7 秒视频约 80 分钟；双卡并行约 1.5 倍加速
- 整首歌（194 秒 ≈ 41 块）在 T4 上跑不完，需要 A100 / MI300X

> 仓库若公开，注意 assets 里有未发布的音乐素材与二创锚点图，建议设为私有。

# Kaggle 单元格（按顺序复制粘贴执行）

## 单元格 1 —— 一键搭环境（约 8-10 分钟，下 15GB 模型）

```
!git clone -q https://github.com/zhangpengjuGitHub/music-mv;bash music-mv/kaggle/setup.sh
```

跑完会打印两个公网地址（GPU0 / GPU1 的 ComfyUI 界面），本地浏览器可直接打开看进度条。

## 单元格 2 —— GPU0 跑第 1 块

```
!cd /kaggle/working/music-mv/kaggle;python run_s2v.py --port 8188 --audio dseg48a.wav --seed 20261101 --prefix fanren_a
```

## 单元格 3 —— GPU1 跑第 2 块（双卡并行）

```
!cd /kaggle/working/music-mv/kaggle;python run_s2v.py --port 8189 --audio dseg48b.wav --seed 20261102 --prefix fanren_b
```

## 单元格 4 —— 看进度 / 取出片

```
!cd /kaggle/working/music-mv/kaggle;bash watch.sh
```

## 单元格 5 —— 出片提交回 GitHub（防会话超时丢成果）

```
!export GITHUB_TOKEN=ghp_你的令牌;cd /kaggle/working/music-mv/kaggle;bash push_results.sh
```

## 提速/调参备忘

| 参数 | 默认 | 说明 |
|---|---|---|
| `--steps` | 10 | 默认工作流是 40 步，10 步对 uni_pc 够用；再降到 6 步可再省 40% 时间 |
| `--length` | 77 | 帧数，77 帧 ≈ 4.7 秒。S2V 按窗口串行处理，块越长总时间越长 |
| `--width/--height` | 832/480 | 降到 640/384 约省 40% 时间，口型质检够用 |
| `--seed` | 20261101 | 固定种子便于对比 |

T4 实测：10 步 × 77 帧 × 832×480 ≈ 80 分钟/块；双卡并行约 1.5 倍。

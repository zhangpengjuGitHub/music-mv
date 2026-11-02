#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按起止时间切 wav（纯标准库，本地和 Kaggle 都能跑）。

用法：
  python cut_wav.py --in vocal_dry.wav --start 138 --dur 4.7 --out seg01.wav
"""
import argparse
import wave


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--start', type=float, default=0.0, help='起始秒')
    ap.add_argument('--dur', type=float, required=True, help='时长秒')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    w = wave.open(a.src, 'rb')
    fr = w.getframerate()
    w.setpos(int(a.start * fr))
    data = w.readframes(int(a.dur * fr))
    o = wave.open(a.out, 'wb')
    o.setnchannels(w.getnchannels())
    o.setsampwidth(w.getsampwidth())
    o.setframerate(fr)
    o.writeframes(data)
    o.close()
    print('%s  <- %s [%ss, +%ss] %dHz' % (a.out, a.src, a.start, a.dur, fr))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""后台进度记录器：每 30s 把 comfy.log 最新一行进度追加到 progress.txt。

启动（Kaggle Console 必须用 subprocess + start_new_session，直接 !nohup 无效）：
    python3 -c "import subprocess;subprocess.Popen(['python3','-u','/kaggle/working/music-mv/kaggle/it_watch.py'],start_new_session=True)"

查看：
    tail -8 /kaggle/working/progress.txt
"""
import datetime
import subprocess
import time

LOG = "/kaggle/working/comfy.log"
OUT = "/kaggle/working/progress.txt"


def last_line():
    try:
        # tail -c 会从多字节字符中间切开，必须 errors=replace，否则整行变成 ERR
        d = subprocess.run(["tail", "-c", "800", LOG],
                           capture_output=True, text=True,
                           errors="replace").stdout
    except Exception as e:
        return "ERR %s" % e
    # tqdm 用 \r 原地刷新，必须切成独立行才能拿到最新一条
    lines = [l.strip() for l in d.replace("\r", "\n").split("\n") if l.strip()]
    if not lines:
        return "(empty)"
    return lines[-1][:78]


def gpu():
    """实测显存/利用率。日志是块缓冲的会滞后，GPU 是唯一实时的信号。"""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True).stdout
        rows = [x.strip().replace(", ", "/") for x in r.strip().split("\n") if x.strip()]
        return " ".join("g%d:%sMiB@%s%%" % (i, v.split("/")[0], v.split("/")[1])
                        for i, v in enumerate(rows))
    except Exception as e:
        return "ERR"


def main():
    f = open(OUT, "a", buffering=1)
    f.write("=== watch start %s ===\n" % datetime.datetime.now().strftime("%H:%M:%S"))
    while True:
        f.write("%s | %s | %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"),
                                    gpu(), last_line()))
        time.sleep(30)


if __name__ == "__main__":
    main()

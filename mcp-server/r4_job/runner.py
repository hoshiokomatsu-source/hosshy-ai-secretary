"""ターミナルで動く。hossy (r4.py) が /tmp/hossy_r4_job.json に書いた R4 のコマンドを動かす。

出力はこの画面とログ(job["log"])の両方に出し、終わったら {"rc": 終了コード, "last_line": 最後の行} を job["result"] に書く。
macOS の /usr/bin/python3 で動く(R4 の venv は動かすコマンドの側で指定する)。
"""

import json
import os
import subprocess
import time
from pathlib import Path

JOB_PATH = "/tmp/hossy_r4_job.json"
job = json.loads(Path(JOB_PATH).read_text(encoding="utf-8"))
Path(job["pid"]).write_text(str(os.getpid()))


def finish(rc, last_line):
    Path(job["result"]).write_text(json.dumps({"rc": rc, "last_line": last_line}, ensure_ascii=False), encoding="utf-8")


def main():
    print(f"ホッシーくん: 「{job['kind']}」をしています({job['label']})。")
    print("終わるまでマウスとキーボードに触らないでください。止めるときは control + C。\n", flush=True)
    last = ""
    with open(job["log"], "a", encoding="utf-8") as log:
        log.write(f"[{time.strftime('%H:%M:%S')}] 開始: {job['kind']} {job['label']}\n")
        log.flush()
        # caffeinate -dimsu: 作業中に画面が消えたり Mac がスリープしたりしないようにする
        proc = subprocess.Popen(["caffeinate", "-dimsu", *job["argv"]], cwd=job["cwd"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            for line in proc.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
                if line.strip():
                    last = line.strip()
            rc = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            rc, last = 130, "ERROR ターミナルで止めました(control + C)"
            log.write(last + "\n")
    finish(rc, last)


try:
    main()
except Exception as e:
    finish(1, f"ERROR ホッシーくんの実行役が失敗: {type(e).__name__}: {e}")

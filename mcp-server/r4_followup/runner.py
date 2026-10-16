"""ターミナルで動く。hossy が作ったプロジェクトに R4自動処理をかけ、保存して Premiere を終了する。

hossy (r4_followup.py) が /tmp/hossy_r4_job.json に書いたプロジェクトを処理し、
結果を result_path に「OK ...」か「ERROR ...」で書く。R4 の venv の Python で動かす。
"""

import json
import os
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

JOB_PATH = "/tmp/hossy_r4_job.json"
job = json.loads(Path(JOB_PATH).read_text(encoding="utf-8"))
R4_DIR = Path(job["r4_dir"])
PROJECT = job["project_path"]
RESULT = job["result_path"]
LOG = job["log_path"]

sys.path.insert(0, str(R4_DIR))
import automate  # noqa: E402


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def finish(msg):
    Path(RESULT).write_text(msg, encoding="utf-8")
    log(msg)


def same_file(a, b):
    # Premiere は「ダ」「ポ」などの濁点・半濁点を分けた形(NFD)でパスを返すので、形をそろえてから比べる
    norm = lambda p: unicodedata.normalize("NFC", os.path.realpath(p))
    return norm(a) == norm(b)


def connect_and_find_project(timeout=300):
    """R4 パネルにつながり、対象プロジェクトが開くまで待つ。(bridge, Premiere 上でのプロジェクトのパス)"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            bridge = automate.PremiereBridge()
            paths = bridge.call("(function(){var o=[];for(var i=0;i<app.projects.numProjects;i++)"
                                "o.push(app.projects[i].path);return JSON.stringify(o);})()")
            for p in paths:
                if same_file(p, PROJECT):
                    return bridge, p
        except (SystemExit, Exception):
            pass
        time.sleep(3)
    return None, None


def save_and_quit(bridge, project_in_premiere):
    """対象プロジェクトを保存し、コピー元(For_copy)は保存せずに閉じて、Premiere を終了する。
    プロジェクトを全部閉じると R4 パネルも閉じて終了の命令が届かなくなるので、対象は開いたまま終了する
    (保存済みなので、終了時に保存の確認は出ない)"""
    js = ("(function(){var t=" + json.dumps(project_in_premiere) + ",c=" + json.dumps(automate.COPY_PROJECT) + ";"
          "for(var i=app.projects.numProjects-1;i>=0;i--){var p=app.projects[i];"
          "if(p.path===t){p.save();}else if(p.path===c){p.closeDocument(0,0);}}"
          "return JSON.stringify(true);})()")
    bridge.call(js)
    time.sleep(2)
    try:
        bridge.call("app.quit(); JSON.stringify(true)")
    except Exception:
        pass  # 終了中は返事が来ないことがある


def screen_is_locked():
    import Quartz
    session = Quartz.CGSessionCopyCurrentDictionary() or {}
    return bool(session.get("CGSSessionScreenIsLocked"))


def main():
    Path(LOG).write_text("", encoding="utf-8")
    log(f"R4自動処理を始めます: {PROJECT}")
    # 画面が消えていたら起こす。ロックされていたら、ロック画面にクリックやキーを送らないよう、ここで止める
    subprocess.run(["caffeinate", "-u", "-t", "3"])
    time.sleep(2)
    if screen_is_locked():
        finish("ERROR 画面がロックされていたので、R4自動処理は始めずに止めました"
               "(プロジェクトとシーケンスはできています。Macのロックを解除してから R4自動処理.command を実行してください)")
        return
    bridge, project_in_premiere = connect_and_find_project()
    if not bridge:
        finish(f"ERROR 5分待ってもプロジェクトが開かないか、R4 AutoEdit パネルにつながりません: {PROJECT}")
        return
    time.sleep(5)  # 開いた直後は画面の準備ができていないことがある

    with open(LOG, "a", encoding="utf-8") as f:
        rc = subprocess.run([str(R4_DIR / "venv" / "bin" / "python"), "-u", "automate.py"],
                            cwd=R4_DIR, stdout=f, stderr=subprocess.STDOUT).returncode
    tail = [l for l in Path(LOG).read_text(encoding="utf-8").splitlines() if l.strip()][-3:]

    # 止まっても、そこまでの処理は残すため保存はする
    bridge, project_in_premiere = connect_and_find_project(timeout=60)
    if bridge:
        save_and_quit(bridge, project_in_premiere)
    saved = "保存して Premiere を終了しました" if bridge else "保存できませんでした(パネルにつながりません)"
    if rc == 0:
        finish(f"OK R4自動処理が完了。{saved}。{tail[-1] if tail else ''}")
    else:
        finish(f"ERROR R4自動処理が途中で止まりました。{saved}。" + " / ".join(tail) + f"(ログ: {LOG})")


try:
    main()
except Exception as e:
    finish(f"ERROR R4自動処理の準備で失敗: {type(e).__name__}: {e}(ログ: {LOG})")

"""R4(~/Documents/src/Movie Edit/R4)のコマンドを「ターミナル」で動かし、終わるまで見守る。

Premiere のセットアップ作業(シーケンス作成・R4自動処理・縦横対応・マスク自動トラッキング)は R4 が持っていて、
ホッシーくんは呼ぶだけ。R4 はキー送信・クリック・画面の読み取りをするので、アクセシビリティと画面収録の許可がある
「ターミナル」で動かす(このサーバーは launchd から起動していて、その許可が無いため)。

一度に動かすのは1つだけ。JOB_PATH に動かすコマンドを書き、r4_job/run.command をターミナルで開くと、
r4_job/runner.py がコマンドを動かして、出力を LOG_PATH に、終了コードと最後の行を RESULT_PATH に書く。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

R4_DIR = Path(os.getenv("R4_DIR", "~/Documents/src/Movie Edit/R4")).expanduser()
R4_PYTHON = R4_DIR / "venv" / "bin" / "python"
MAKE_PROJECT = R4_DIR / "シーケンス作成" / "make_project.py"
TRACKING_DIR = R4_DIR / "マスク自動トラッキング"
TRACKING_PYTHON = TRACKING_DIR / ".venv" / "bin" / "python"

RUN_COMMAND = Path(__file__).parent / "r4_job" / "run.command"
JOB_PATH = "/tmp/hossy_r4_job.json"
PID_PATH = "/tmp/hossy_r4_job.pid"
LOG_PATH = "/tmp/hossy_r4.log"
RESULT_PATH = "/tmp/hossy_r4_result.json"


class R4Error(RuntimeError):
    pass


def check_installed(tracking: bool = False) -> None:
    if not (R4_PYTHON.exists() and MAKE_PROJECT.exists()):
        raise R4Error(f"R4 が見つかりません: {R4_DIR}(venv/bin/python と シーケンス作成/make_project.py が要る)")
    if tracking and not TRACKING_PYTHON.exists():
        raise R4Error(f"マスク自動トラッキングの準備がまだです。{TRACKING_DIR}/セットアップ.command を実行してください")


def _read_json(path: str) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _log_lines() -> list[str]:
    try:
        return [l for l in Path(LOG_PATH).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    except FileNotFoundError:
        return []


def job_status() -> dict:
    """直近のジョブの状態。state は none / running / done(rc=0)/ failed(rc≠0)/ stopped(結果を書かずに終わった)"""
    job = _read_json(JOB_PATH)
    if not job or "kind" not in job:
        return {"state": "none"}
    lines = _log_lines()
    status = {**job, "tail": lines[-8:], "last_line": lines[-1] if lines else "",
              "elapsed_min": round((time.time() - job.get("started", time.time())) / 60, 1)}
    result = _read_json(RESULT_PATH)
    if result:
        status.update(state="done" if result.get("rc") == 0 else "failed",
                      rc=result.get("rc"), last_line=result.get("last_line") or status["last_line"])
        return status
    try:
        pid = int(Path(PID_PATH).read_text().strip())
    except (FileNotFoundError, ValueError):
        pid = None
    if pid is None:
        # ターミナルが開いてコマンドが始まるまで少しかかる
        status["state"] = "running" if time.time() - job.get("started", 0) < 60 else "stopped"
    else:
        status["state"] = "running" if _pid_alive(pid) else "stopped"
    return status


def job_running() -> bool:
    return job_status()["state"] == "running"


def start_job(kind: str, label: str, argv: list[str], cwd: str) -> None:
    """ターミナルで argv を動かす。すぐ返る。ほかのジョブが動いていたら R4Error"""
    current = job_status()
    if current["state"] == "running":
        raise R4Error(f"いま「{current.get('kind')}」({current.get('label')})が動いています。終わってからもう一度頼んでください")
    for p in (RESULT_PATH, PID_PATH, LOG_PATH):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    Path(JOB_PATH).write_text(json.dumps({
        "kind": kind, "label": label, "argv": argv, "cwd": cwd,
        "log": LOG_PATH, "result": RESULT_PATH, "pid": PID_PATH, "started": time.time(),
    }, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["open", "-a", "Terminal", str(RUN_COMMAND)], check=False)


def wait_job(timeout_sec: float, on_progress=None) -> dict:
    """ジョブが終わるまで待つ。on_progress(status) を数秒ごとに呼ぶ"""
    deadline = time.time() + timeout_sec
    status = job_status()
    while time.time() < deadline:
        status = job_status()
        if status["state"] != "running":
            return status
        if on_progress:
            on_progress(status)
        time.sleep(5)
    return {**status, "state": "timeout"}


def make_project_argv(folder: str, orientation: str, exception: bool = False, r4: bool = True) -> list[str]:
    """R4 のシーケンス作成。最後に保存して Premiere を終了する(帰宅後に .prproj を開けばすぐ編集できるように)"""
    argv = [str(R4_PYTHON), "-u", str(MAKE_PROJECT), folder, "--orientation", orientation, "--quit"]
    if exception:
        argv.append("--exception")
    if not r4:
        argv.append("--no-r4")
    return argv


def tracking_argv(track: int = 1) -> list[str]:
    argv = [str(TRACKING_PYTHON), "-u", "track_masks.py", "run"]
    if track != 1:
        argv += ["--track", str(track)]
    return argv

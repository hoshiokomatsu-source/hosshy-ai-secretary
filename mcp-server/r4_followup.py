"""シーケンス作成のあと、R4自動処理(~/src/Movie Edit/R4)をかけて、保存して Premiere を終了する。

R4自動処理はキー送信・クリックをするので、アクセシビリティ許可のある「ターミナル」で動かす
(このサーバーは launchd から起動していて、その許可が無いため)。
ターミナルで動く r4_followup/runner.py に、JOB_PATH でプロジェクトを渡し、RESULT_PATH で結果を受け取る。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

R4_DIR = Path(os.getenv("R4_DIR", "~/src/Movie Edit/R4")).expanduser()
RUNNER_COMMAND = Path(__file__).parent / "r4_followup" / "run_r4.command"
JOB_PATH = "/tmp/hossy_r4_job.json"
RESULT_PATH = "/tmp/hossy_r4_result.txt"
LOG_PATH = "/tmp/hossy_r4.log"


def r4_enabled() -> bool:
    """HOSSY_R4_AFTER=0 で止められる。R4 が入っていない Mac では何もしない"""
    if os.getenv("HOSSY_R4_AFTER", "1") == "0":
        return False
    return (R4_DIR / "automate.py").exists() and (R4_DIR / "venv" / "bin" / "python").exists()


def _premiere_app(premiere_bin: str) -> str:
    """.../Adobe Premiere Pro 2026.app/Contents/MacOS/... から .app のパスを取り出す"""
    return premiere_bin.split(".app/")[0] + ".app"


def read_result() -> str | None:
    if not os.path.exists(RESULT_PATH):
        return None
    return Path(RESULT_PATH).read_text(encoding="utf-8").strip() or None


def run_r4_followup(project_path: str, premiere_bin: str, timeout_sec: float = 3 * 60 * 60) -> tuple[bool, str]:
    """プロジェクトを Premiere で開き、ターミナルで R4自動処理を走らせて、終わるまで待つ。(成功したか, メッセージ)"""
    try:
        os.remove(RESULT_PATH)
    except FileNotFoundError:
        pass
    Path(JOB_PATH).write_text(json.dumps({
        "project_path": project_path,
        "r4_dir": str(R4_DIR),
        "result_path": RESULT_PATH,
        "log_path": LOG_PATH,
    }, ensure_ascii=False), encoding="utf-8")

    subprocess.run(["open", "-a", _premiere_app(premiere_bin), project_path], check=False)
    subprocess.run(["open", "-a", "Terminal", str(RUNNER_COMMAND)], check=False)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        result = read_result()
        if result:
            return result.startswith("OK"), result
        time.sleep(5)
    return False, f"TIMEOUT R4自動処理が {timeout_sec / 3600:.0f} 時間たっても終わりません。ログ: {LOG_PATH}"

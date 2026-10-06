"""ホッシーくんの画面用ステータス。UI が /tmp/hossy_status.json を読む。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime

STATUS_PATH = "/tmp/hossy_status.json"
# working のまま実作業が無いときは、この秒数で待機に戻す
PREMIERE_IDLE_GRACE_SEC = 20
WORKING_STALE_SEC = 20 * 60

POSES = (
    "sleep",
    "listen",
    "link",
    "download",
    "files",
    "sheets",
    "premiere",
    "done",
)

_LINE_POSE = (
    ("premiere", ("premiere", "シーケンス")),
    ("sheets", ("シート",)),
    ("files", ("解凍", "整理", "解析", "ZIP")),
    ("link", ("ページを開", "リンク")),
    ("listen", ("呼んで", "お仕事なんでも")),
    ("download", ("ダウンロード", "保存してる")),
    ("done", ("終わった", "できたよ")),
)

IDLE = {
    "state": "idle",
    "line": "zzz…",
    "detail": "",
    "pose": "sleep",
    "progress": None,
}


def infer_pose(state: str, line: str) -> str:
    text = (line or "").lower()
    if state == "wake":
        return "listen"
    if state == "idle":
        for pose, keys in _LINE_POSE:
            if pose == "done" and any(k.lower() in text for k in keys):
                return "done"
        return "sleep"
    for pose, keys in _LINE_POSE:
        if any(k.lower() in text for k in keys):
            return pose
    return "download"


def mark_finished(line: str = "お仕事終わったよ！また呼んでね", detail: str = "", pose: str = "done") -> None:
    """実作業が終わったら必ずここを通す。working のまま残さない。"""
    set_status("idle", line, detail, pose=pose)


def _premiere_running() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "Adobe Premiere Pro .*\\.app/Contents/MacOS/Adobe Premiere Pro"],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _status_age_sec(data: dict) -> float:
    ts = data.get("updated_ts")
    if isinstance(ts, (int, float)):
        return max(0.0, time.time() - float(ts))
    return WORKING_STALE_SEC


def _is_premiere_job(data: dict) -> bool:
    pose = str(data.get("pose") or "")
    text = f"{data.get('line') or ''} {data.get('detail') or ''}"
    return pose == "premiere" or "Premiere" in text or "シーケンス" in text


def _recover_stale_working(data: dict) -> dict:
    """作業中表示は、実際に Premiere / ダウンロードが動いている間だけ。終わっていたら待機に戻す。"""
    if data.get("state") != "working":
        return data
    age = _status_age_sec(data)
    premiere_up = _premiere_running()
    if _is_premiere_job(data) and not premiere_up and age >= PREMIERE_IDLE_GRACE_SEC:
        mark_finished()
        return _read_raw() or dict(IDLE)
    if not premiere_up and age >= WORKING_STALE_SEC:
        mark_finished()
        return _read_raw() or dict(IDLE)
    return data


def set_status(state: str, line: str, detail: str = "", progress=None, pose: str | None = None) -> None:
    prev = _read_raw() or dict(IDLE)
    if pose not in POSES:
        pose = infer_pose(state, line)
    if state == "idle" and pose not in ("sleep", "done"):
        pose = "sleep"
    if state != "working":
        progress = None
    elif progress is None:
        progress = prev.get("progress")
    try:
        progress = None if progress is None else max(0, min(100, int(progress)))
    except (TypeError, ValueError):
        progress = None
    payload = {
        "state": state,
        "line": line,
        "detail": detail,
        "pose": pose,
        "progress": progress,
        "updated_at": datetime.now().strftime("%H:%M:%S"),
        "updated_ts": time.time(),
    }
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, STATUS_PATH)


def _read_raw() -> dict | None:
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("state"):
            pose = data.get("pose")
            if pose == "laptop":
                data["pose"] = "download"
            elif pose == "desk":
                data["pose"] = "sheets"
            elif pose not in POSES:
                data["pose"] = infer_pose(str(data.get("state")), str(data.get("line") or ""))
            return data
    except Exception:
        pass
    return None


def read_status() -> dict:
    data = _read_raw()
    if not data:
        return dict(IDLE)
    return _recover_stale_working(data)

"""ホッシーくんの画面用ステータス。UI が /tmp/hossy_status.json を読む。"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime

STATUS_PATH = "/tmp/hossy_status.json"
WORK_POSES = ("laptop", "desk")

IDLE = {
    "state": "idle",
    "line": "zzz…",
    "detail": "",
    "pose": "laptop",
    "progress": None,
}


def set_status(state: str, line: str, detail: str = "", progress=None) -> None:
    prev = read_status()
    if state == "working":
        pose = prev.get("pose") if prev.get("state") == "working" else random.choice(WORK_POSES)
        if pose not in WORK_POSES:
            pose = "laptop"
    else:
        pose = prev.get("pose") if prev.get("pose") in WORK_POSES else "laptop"
        progress = None
    if progress is None and state == "working":
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
    }
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, STATUS_PATH)


def read_status() -> dict:
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("state"):
            return data
    except Exception:
        pass
    return dict(IDLE)

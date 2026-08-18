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
}


def set_status(state: str, line: str, detail: str = "") -> None:
    prev = read_status()
    if state == "working":
        pose = prev.get("pose") if prev.get("state") == "working" else random.choice(WORK_POSES)
        if pose not in WORK_POSES:
            pose = "laptop"
    else:
        pose = prev.get("pose") if prev.get("pose") in WORK_POSES else "laptop"
    payload = {
        "state": state,
        "line": line,
        "detail": detail,
        "pose": pose,
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

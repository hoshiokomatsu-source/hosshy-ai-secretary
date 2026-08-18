"""ホッシーくんの画面用ステータス。UI が /tmp/hossy_status.json を読む。"""

from __future__ import annotations

import json
import os
from datetime import datetime

STATUS_PATH = "/tmp/hossy_status.json"

IDLE = {
    "state": "idle",
    "line": "zzz…",
    "detail": "",
}


def set_status(state: str, line: str, detail: str = "") -> None:
    payload = {
        "state": state,
        "line": line,
        "detail": detail,
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

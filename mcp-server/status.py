"""ホッシーくんの画面用ステータス。UI が /tmp/hossy_status.json を読む。"""

from __future__ import annotations

import json
import os
from datetime import datetime

STATUS_PATH = "/tmp/hossy_status.json"

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


def set_status(state: str, line: str, detail: str = "", progress=None, pose: str | None = None) -> None:
    prev = read_status()
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
    return dict(IDLE)

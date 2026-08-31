"""ファイル名の並び。Finder の名前順（数字は若い順、そのあと A→Z）。"""

import re
import unicodedata
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def _compare_name(text: str) -> str:
    name = Path(unicodedata.normalize("NFC", str(text or ""))).name
    if Path(name).suffix.lower() in VIDEO_EXTS:
        return Path(name).stem
    return name


def natural_sort_key(text: str) -> tuple:
    parts = []
    for chunk in re.split(r"(\d+)", _compare_name(text)):
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        elif chunk:
            parts.append((1, chunk.casefold()))
    return tuple(parts)


def sort_file_records(files: list[dict]) -> list[dict]:
    """Finder と同じく、実ファイル名で並べる。stem は使わない。"""
    return sorted(
        files,
        key=lambda f: natural_sort_key(
            str(f.get("name") or f.get("path") or f.get("stem") or "")
        ),
    )

"""ファイル名・識別子の並び。数字は若い順、文字はAから（Finder寄せ）。"""

import re


def natural_sort_key(text: str) -> tuple:
    parts = []
    for chunk in re.split(r"(\d+)", str(text or "")):
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        elif chunk:
            parts.append((1, chunk.casefold()))
    return tuple(parts)

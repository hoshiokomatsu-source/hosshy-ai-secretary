"""Premiere Pro でプロジェクト作成・素材読み込み・シーケンス作成を行う。"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

DEFAULT_SEQUENCE_JSX = os.path.expanduser(
    "~/Dropbox/Movie Edit/R4/my_project/SQ/NewSequence.jsx"
)
RESULT_PATH = "/tmp/hossy_premiere_result.txt"
GENERATED_JSX = "/tmp/hossy_premiere_setup.jsx"
SEQUENCE_RUN_JSX = "/tmp/hossy_NewSequence_run.jsx"


def _premiere_bin() -> str:
    env = os.getenv("PREMIERE_BIN")
    if env:
        return env
    for year in (2026, 2025, 2024):
        path = (
            f"/Applications/Adobe Premiere Pro {year}/"
            f"Adobe Premiere Pro {year}.app/Contents/MacOS/Adobe Premiere Pro {year}"
        )
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Adobe Premiere Pro が見つかりません。")


def _sequence_jsx() -> str:
    return os.getenv("SEQUENCE_JSX", DEFAULT_SEQUENCE_JSX)


def premiere_is_running() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "Adobe Premiere Pro .*\\.app/Contents/MacOS/Adobe Premiere Pro"],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def quit_premiere() -> None:
    """Cmd+S のあと Cmd+Q で Premiere を終了する。tell quit はダイアログ待ちで固まらない。"""
    script = '''
tell application "System Events"
  set procName to ""
  repeat with n in {"Adobe Premiere Pro 2026", "Adobe Premiere Pro 2025", "Adobe Premiere Pro 2024"}
    if exists (process n) then
      set procName to (n as text)
      exit repeat
    end if
  end repeat
  if procName is "" then return
  tell process procName
    set frontmost to true
    delay 0.4
    keystroke "s" using command down
    delay 2
    keystroke "q" using command down
    delay 1
    keystroke return
  end tell
end tell
'''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        pass
    deadline = time.time() + 20
    while time.time() < deadline and premiere_is_running():
        time.sleep(1)



def list_videos(folder: str) -> list[str]:
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return []
    videos = [
        str(p) for p in sorted(folder_path.iterdir())
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.name.startswith(".")
    ]
    return videos


def resolve_media_folder(folder: str | None, download_dir: str) -> str:
    if folder:
        return os.path.abspath(os.path.expanduser(folder))
    download = Path(download_dir)
    if not download.is_dir():
        raise FileNotFoundError(f"ダウンロードフォルダがありません: {download_dir}")

    candidates = []
    for child in download.iterdir():
        if child.is_dir() and not child.name.startswith(".") and list_videos(str(child)):
            candidates.append(child)
    if not candidates:
        raise FileNotFoundError(
            f"動画フォルダが見つかりません。{download_dir} の中にバッチフォルダがあるか確認してください。"
        )
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0])


def _strip_alerts(src: str) -> str:
    return src.replace("alert(", "$.writeln(")


def _write_sequence_copy() -> str:
    original = Path(_sequence_jsx())
    if not original.exists():
        raise FileNotFoundError(f"NewSequence.jsx がありません: {original}")
    text = original.read_text(encoding="utf-8")
    Path(SEQUENCE_RUN_JSX).write_text(_strip_alerts(text), encoding="utf-8")
    return SEQUENCE_RUN_JSX


def _write_setup_jsx(project_path: str, media_paths: list[str], sequence_jsx: str) -> str:
    template_path = Path(__file__).parent / "premiere_scripts" / "setup_project.jsx.tmpl"
    template = template_path.read_text(encoding="utf-8")
    jsx = (
        template
        .replace("__RESULT_PATH__", json.dumps(RESULT_PATH, ensure_ascii=False))
        .replace("__PROJECT_PATH__", json.dumps(project_path, ensure_ascii=False))
        .replace("__MEDIA_PATHS__", json.dumps(media_paths, ensure_ascii=False))
        .replace("__SEQUENCE_JSX__", json.dumps(sequence_jsx, ensure_ascii=False))
    )
    Path(GENERATED_JSX).write_text(jsx, encoding="utf-8")
    return GENERATED_JSX


def _clear_result() -> None:
    try:
        os.remove(RESULT_PATH)
    except FileNotFoundError:
        pass


def read_premiere_result() -> str | None:
    if not os.path.exists(RESULT_PATH):
        return None
    return Path(RESULT_PATH).read_text(encoding="utf-8").strip()


def prepare_premiere_project(folder: str) -> dict:
    """フォルダ名と同名の .prproj を作り、動画を読み込み、NewSequence.jsx でシーケンスを作る。"""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"フォルダがありません: {folder}")

    videos = list_videos(folder)
    if not videos:
        raise FileNotFoundError(f"動画がありません: {folder}")

    name = Path(folder).name
    project_path = os.path.join(folder, f"{name}.prproj")
    sequence_jsx = _write_sequence_copy()
    jsx_path = _write_setup_jsx(project_path, videos, sequence_jsx)
    _clear_result()

    if premiere_is_running():
        sidecar = os.path.join(folder, "hossy_setup.jsx")
        Path(sidecar).write_text(Path(jsx_path).read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "status": "needs_premiere_closed",
            "folder": folder,
            "project_path": project_path,
            "video_count": len(videos),
            "jsx_path": sidecar,
            "message": (
                "Premiere がすでに開いているため、自動実行を止めました。"
                "Premiere を閉じてからもう一度実行するか、"
                f"VS Code の ExtendScript デバッガで {sidecar} を実行してください。"
            ),
        }

    bin_path = _premiere_bin()
    subprocess.Popen(
        [bin_path, "/C", "es.processFile", jsx_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    threading.Thread(target=_ensure_quit_after_success, daemon=True).start()
    return {
        "status": "started",
        "folder": folder,
        "project_path": project_path,
        "video_count": len(videos),
        "jsx_path": jsx_path,
        "message": (
            f"Premiere を起動し、{name}.prproj を作成 → 動画 {len(videos)} 本を読み込み → "
            "シーケンス作成 → 保存して Premiere を終了します。"
            "帰宅後にプロジェクトファイルを開けば、すぐ編集できる状態です。"
        ),
    }


def _ensure_quit_after_success() -> None:
    deadline = time.time() + 300
    while time.time() < deadline:
        result = read_premiere_result()
        if result and result.startswith("OK"):
            time.sleep(3)
            if premiere_is_running():
                quit_premiere()
            return
        if result and result.startswith("ERROR"):
            return
        time.sleep(2)


def wait_for_premiere_result(timeout_sec: float = 300) -> str:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        result = read_premiere_result()
        if result:
            return result
        time.sleep(2)
    return "TIMEOUT Premiere の処理結果がまだ返っていません。Premiere の画面を確認してください。"


def folder_from_downloaded_files(files: list[dict], download_dir: str) -> str | None:
    """ZIP展開後の folder キーがあればそれを使う。"""
    folders = {f.get("folder") for f in files if f.get("folder")}
    folders.discard(None)
    if len(folders) == 1:
        return os.path.join(download_dir, next(iter(folders)))

    dirs = set()
    for f in files:
        path = f.get("path")
        if not path:
            continue
        parent = os.path.dirname(path)
        if os.path.abspath(parent) != os.path.abspath(download_dir):
            dirs.add(parent)
    if len(dirs) == 1:
        return next(iter(dirs))
    return None

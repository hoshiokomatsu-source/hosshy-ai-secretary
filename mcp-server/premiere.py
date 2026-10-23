"""Premiere のセットアップ作業を R4 に頼む(シーケンス作成・縦横対応・マスク自動トラッキング)。

中身は R4(~/Documents/src/Movie Edit/R4)にある。ここでは素材フォルダを決めて、R4 のコマンドをターミナルで動かし、
終わるまで見守ってホッシーくんの画面を更新するだけ。素材フォルダに作業ファイルは残さない。
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

import r4
from natural_sort import natural_sort_key
from status import mark_finished, set_status

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
# シーケンス作成 + R4自動処理は本数が多いと1時間を超える。トラッキングは1シーケンス約9分
SETUP_TIMEOUT_SEC = 3 * 60 * 60
TRACKING_TIMEOUT_SEC = 12 * 60 * 60

PREMIERE_OPEN_MESSAGE = "Premiere が開いています。作業を保存して Premiere を閉じてから、もう一度頼んでください。"


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


def list_videos(folder: str) -> list[str]:
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return []
    videos = [
        str(p) for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.name.startswith(".")
    ]
    videos.sort(key=lambda path: natural_sort_key(Path(path).name))
    return videos


def _count_videos(folder: str) -> int:
    """縦横対応で -横 / -縦 に分けたあとのフォルダも数える"""
    name = Path(folder).name
    return len(list_videos(folder)) + sum(len(list_videos(os.path.join(folder, f"{name}-{o}"))) for o in ("横", "縦"))


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


def _watch(kind: str, label: str, timeout_sec: float, done_line: str) -> None:
    """ジョブが終わるまで待って、ホッシーくんの画面を待機に戻す"""
    def progress(status: dict) -> None:
        set_status("working", f"{kind}してるよ…触らないでね", status.get("last_line", "")[-80:], pose="premiere")

    status = r4.wait_job(timeout_sec, progress)
    state, last = status["state"], status.get("last_line", "")
    print(f"[hossy] {kind}({label}): {state} {last}")
    if state == "done":
        mark_finished(done_line, last)
    elif state == "timeout":
        mark_finished(f"{kind}が終わらない…画面を見てみて", last, pose="sleep")
    else:
        mark_finished(f"{kind}で止まっちゃった…", last, pose="sleep")


def _start(kind: str, label: str, argv: list[str], cwd: str, timeout_sec: float, done_line: str) -> None:
    r4.start_job(kind, label, argv, cwd)
    set_status("working", f"{kind}してるよ…触らないでね", label, pose="premiere")
    threading.Thread(target=_watch, args=(kind, label, timeout_sec, done_line), daemon=True).start()


def _setup(folder: str, kind: str, orientation: str, exception: bool, explain: str) -> dict:
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"フォルダがありません: {folder}")
    video_count = _count_videos(folder)
    if not video_count:
        raise FileNotFoundError(f"動画がありません: {folder}")
    r4.check_installed()

    name = Path(folder).name
    project_path = os.path.join(folder, f"{name}.prproj")
    base = {"folder": folder, "project_path": project_path, "video_count": video_count}
    if os.path.exists(project_path):
        return {**base, "status": "exists",
                "message": f"{name}.prproj はもうあります。上書きしないので、作り直すなら古いものを消すか名前を変えてください。"}
    if premiere_is_running():
        return {**base, "status": "needs_premiere_closed", "message": PREMIERE_OPEN_MESSAGE}
    if r4.job_running():
        return {**base, "status": "busy", "message": "いまほかの Premiere の作業が動いています。終わってからもう一度頼んでください。"}

    with_r4 = os.getenv("HOSSY_R4_AFTER", "1") != "0"
    _start(kind, name, r4.make_project_argv(folder, orientation, exception, with_r4), str(r4.R4_DIR),
           SETUP_TIMEOUT_SEC, "お仕事終わったよ！R4自動処理までできてる" if with_r4 else "お仕事終わったよ！")
    return {**base, "status": "started", "message": (
        f"ターミナルで R4 を動かして、Premiere で {name}.prproj を作ります({explain})。"
        + ("そのあと R4自動処理(⌘6・調整レイヤー3つ・Lumetri自動・オーディオゲイン)をかけ、" if with_r4 else "")
        + "保存して Premiere を終了します。終わるまでマウスとキーボードに触らないでください。"
    )}


def prepare_premiere_project(folder: str) -> dict:
    """横(1920×1080)。フォルダ名と同名の .prproj を作り、動画ごとにシーケンスを作って R4自動処理までかける"""
    return _setup(folder, "シーケンス作成", "横", False, "動画ごとに 1920×1080 のシーケンス")


def prepare_mixed_project(folder: str, exception: bool = False) -> dict:
    """縦横対応。縦横が混ざっていれば -横 / -縦 に分け、b に a の音声を同期して、1つのプロジェクトにする"""
    explain = ("縦横が混ざっていれば「-横」「-縦」フォルダに分け、横は 1920×1080・縦は 1080×1920 のシーケンス"
               + ("。例外なので a/b の音声同期はしない" if exception else "。b の素材には同じ番号の a の音声を同期"))
    return _setup(folder, "縦横対応", "auto", exception, explain)


def start_mask_tracking(track: int = 1) -> dict:
    """タイムラインに開いている全シーケンスのオブジェクトマスクをトラッキングする(track=2 は V2 の素材のマスク)"""
    r4.check_installed(tracking=True)
    if not premiere_is_running():
        return {"status": "needs_premiere", "message": (
            "Premiere が開いていません。マスクを作って、トラッキングするシーケンスをタイムラインに開いてから頼んでください。")}
    if r4.job_running():
        return {"status": "busy", "message": "いまほかの Premiere の作業が動いています。終わってからもう一度頼んでください。"}
    label = "V2 の素材(2周目)" if track == 2 else f"V{track}"
    _start("マスク自動トラッキング", label, r4.tracking_argv(track), str(r4.TRACKING_DIR),
           TRACKING_TIMEOUT_SEC, "トラッキング終わったよ！")
    return {"status": "started", "message": (
        f"ターミナルでマスク自動トラッキング({label} のマスク)を始めました。"
        "タイムラインに開いているシーケンスを順番に ◀▶ で追跡して、1つ終わるごとに保存します(1シーケンス約9分)。"
        "終わるまでマウスとキーボードに触らないでください。")}


def premiere_job_status_text() -> str:
    s = r4.job_status()
    state = s["state"]
    if state == "none":
        return "まだ Premiere の作業(シーケンス作成・縦横対応・トラッキング)を頼まれていません。"
    head = f"「{s['kind']}」({s['label']})"
    tail = "\n".join(f"  {l}" for l in s.get("tail", []))
    if state == "running":
        return f"⏳ {head} を実行中です({s['elapsed_min']} 分経過)。\n最近の出力:\n{tail}"
    if state == "done":
        return f"✅ {head} が終わりました。\n{s['last_line']}\n最近の出力:\n{tail}"
    if state == "failed":
        return f"❌ {head} が途中で止まりました。\n{s['last_line']}\n最近の出力:\n{tail}\n(全部のログ: {r4.LOG_PATH})"
    return f"❌ {head} は結果を残さずに終わりました(ターミナルを閉じた可能性があります)。\n最近の出力:\n{tail}"


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

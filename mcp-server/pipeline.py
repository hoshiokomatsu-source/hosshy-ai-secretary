"""ダウンロード → シート転記 → Premiere までの一連処理。MCP と UI の両方から使う。"""

from __future__ import annotations

import os
from datetime import datetime

from downloader import download_gigafile_url
from premiere import folder_from_downloaded_files, prepare_premiere_project
from sheets import write_files_to_sheet
from status import set_status

last_job_status = "まだダウンロードを実行していません。"


def _download_dir() -> str:
    return os.getenv("DOWNLOAD_DIR", os.path.expanduser(
        "~/Dropbox/komatsu hoshio/Movie Edit/R4/Active"
    ))


async def run_download_pipeline(gigafile_url: str) -> str:
    global last_job_status
    download_dir = _download_dir()
    started_at = datetime.now().strftime("%H:%M:%S")
    set_status("working", "ページを開いてるよ…", gigafile_url, progress=5, pose="link")
    last_job_status = "⏳ ダウンロード実行中です..."

    def _progress(pct: int, line: str, detail: str = "") -> None:
        set_status("working", line, detail, progress=pct)

    try:
        downloaded_files = await download_gigafile_url(
            gigafile_url, download_dir, on_progress=_progress,
        )
    except Exception as e:
        last_job_status = (
            f"❌ [{started_at}開始] ダウンロード処理でエラーが発生しました。\n"
            f"詳細: {type(e).__name__}: {e}\n"
            "URLの有効期限やギガファイル便側の混雑状況を確認し、もう一度試してください。"
        )
        set_status("idle", "うまくいかなかった…もう一回リンクを送って！", str(e), pose="sleep")
        return last_job_status

    print(f"[hossy] ダウンロード結果: {len(downloaded_files)} 件 {[f.get('name') for f in downloaded_files]}")
    if not downloaded_files:
        last_job_status = f"[{started_at}開始] ダウンロードできるファイルが見つかりませんでした。URLを確認してください。"
        print("[hossy] ファイル0件のためシート転記をスキップしました")
        set_status("idle", "ファイルが見つからなかったよ。URLを確認して！", "", pose="sleep")
        return last_job_status

    file_names = [f["name"] for f in downloaded_files]
    set_status("working", "シートに書いてるよ…", f"{len(file_names)} ファイル", progress=88, pose="sheets")
    sheet_result = await write_files_to_sheet(downloaded_files)
    print(f"[hossy] シート転記: {sheet_result}")

    finished_at = datetime.now().strftime("%H:%M:%S")
    lines = [f"✅ [{started_at}開始 → {finished_at}完了] ダウンロード完了: {len(file_names)} ファイル"]
    lines.append(f"📁 保存先: {download_dir}")
    lines.append("")
    lines.extend([f"  - {name}" for name in file_names])
    lines.append("")
    lines.append(f"📊 スプレッドシート: {sheet_result}")

    premiere_folder = folder_from_downloaded_files(downloaded_files, download_dir)
    if premiere_folder:
        set_status("working", "Premiere でシーケンス作ってるよ…", os.path.basename(premiere_folder), progress=95, pose="premiere")
        try:
            premiere = prepare_premiere_project(premiere_folder)
            lines.append("")
            lines.append(f"🎬 Premiere: {premiere['message']}")
        except Exception as e:
            lines.append("")
            lines.append(f"🎬 Premiere: 自動セットアップに失敗しました（{type(e).__name__}: {e}）")

    last_job_status = "\n".join(lines)
    set_status("idle", "お仕事終わったよ！また呼んでね", "", pose="done")
    return last_job_status

"""ギガファイル便 自動ダウンローダー（Playwright使用）"""

import os
import re
import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Download, TimeoutError as PlaywrightTimeoutError

DOWNLOAD_BUTTON_SELECTOR = (
    "input[type='button'][value*='ダウンロード'], "
    "button:has-text('ダウンロード'), "
    "a:has-text('ダウンロード')"
)

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


async def download_gigafile_url(url: str, download_dir: str) -> list[dict]:
    """ギガファイル便のURLにアクセスしてファイルをダウンロードする。

    Returns:
        [{"name": "ファイル名", "path": "保存先フルパス", "size": バイト数}, ...]
    """
    os.makedirs(download_dir, exist_ok=True)
    before = {name: os.path.getmtime(os.path.join(download_dir, name))
              for name in os.listdir(download_dir) if not name.startswith(".")}

    downloaded = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # ギガファイル便は広告・解析スクリプトのバックグラウンド通信が続くため
        # "networkidle" だと（実際にはページが表示済みでも）タイムアウトしやすい。
        # DOM構築完了まで待ち、あとはダウンロードボタンの出現を明示的に待つ。
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        try:
            await page.wait_for_selector(DOWNLOAD_BUTTON_SELECTOR, timeout=30_000)
        except PlaywrightTimeoutError:
            pass  # ボタンが見つからない場合は下のフォールバック検索に任せる

        # ギガファイル便のダウンロードボタンを探す
        # 複数ファイルが含まれる場合を考慮して全ボタンを取得
        download_buttons = await page.query_selector_all(DOWNLOAD_BUTTON_SELECTOR)

        if not download_buttons:
            # フォールバック: ページ内の全ダウンロードリンクを試す
            download_buttons = await page.query_selector_all("[onclick*='download'], [href*='download']")

        for button in download_buttons:
            try:
                async with page.expect_download(timeout=120_000) as download_info:
                    await button.click()

                download: Download = await download_info.value
                original_name = download.suggested_filename or f"file_{datetime.now().strftime('%Y%m%d%H%M%S')}"

                save_path = os.path.join(download_dir, original_name)
                await download.save_as(save_path)

                file_size = os.path.getsize(save_path)
                downloaded.append({
                    "name": original_name,
                    "path": save_path,
                    "size": file_size,
                    "stem": _extract_stem(original_name),
                })

            except Exception as e:
                print(f"[downloader] ボタンのクリック失敗: {e}")
                continue

        await browser.close()

    if not downloaded:
        downloaded = _files_added_since(download_dir, before)
        if downloaded:
            print(f"[downloader] ボタン処理は失敗したが、新規ファイルを {len(downloaded)} 件検出したので転記対象にする")

    return _expand_archives(downloaded, download_dir)


def _files_added_since(download_dir: str, before: dict) -> list[dict]:
    found = []
    for name in os.listdir(download_dir):
        if name.startswith("."):
            continue
        path = os.path.join(download_dir, name)
        if not os.path.isfile(path):
            continue
        mtime = os.path.getmtime(path)
        if name not in before or mtime > before[name]:
            found.append({
                "name": name,
                "path": path,
                "size": os.path.getsize(path),
                "stem": _extract_stem(name),
            })
    return found


def _expand_archives(files: list[dict], download_dir: str) -> list[dict]:
    """ZIPは解凍し、中の動画を転記対象にする。ZIP自体は転記しない。"""
    expanded = []
    for f in files:
        path = f["path"]
        if Path(path).suffix.lower() != ".zip":
            expanded.append(f)
            continue
        folder = Path(path).stem
        extracted = _unzip_archive(path, download_dir, folder)
        if extracted:
            expanded.extend(extracted)
        else:
            expanded.append(f)
    return expanded


def _unzip_archive(zip_path: str, dest_dir: str, folder_name: str) -> list[dict]:
    import zipfile

    print(f"[downloader] ZIP解凍開始: {zip_path}")
    extracted = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = _zip_member_name(info)
                out_name = Path(name).name
                out_path = os.path.join(dest_dir, out_name)
                ext = Path(out_name).suffix.lower()
                if not os.path.exists(out_path) or os.path.getsize(out_path) != info.file_size:
                    print(f"[downloader] 展開中: {out_name}")
                    with zf.open(info) as src, open(out_path, "wb") as dst:
                        while True:
                            chunk = src.read(1024 * 1024 * 8)
                            if not chunk:
                                break
                            dst.write(chunk)
                if ext in VIDEO_EXTS:
                    extracted.append({
                        "name": out_name,
                        "path": out_path,
                        "size": os.path.getsize(out_path),
                        "stem": _extract_stem(out_name),
                        "folder": folder_name,
                    })
        print(f"[downloader] ZIP解凍完了: {len(extracted)} 本")
        return extracted
    except Exception as e:
        print(f"[downloader] ZIP解凍失敗: {e}")
        return []


def _zip_member_name(info) -> str:
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    for enc in ("cp932", "utf-8"):
        try:
            return name.encode("cp437").decode(enc)
        except Exception:
            continue
    return name


def _extract_stem(filename: str) -> str:
    """ファイル名から識別子部分を抽出する。

    例: "32-1ド.mp4" → "32-1"
        "ホシオ0808_36-2.mp4" → "36-2"
    """
    stem = Path(filename).stem
    # 先頭の「数字-数字」パターンを優先抽出
    match = re.search(r"\d+-\d+", stem)
    if match:
        return match.group()
    return stem

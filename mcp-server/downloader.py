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


async def download_gigafile_url(url: str, download_dir: str) -> list[dict]:
    """ギガファイル便のURLにアクセスしてファイルをダウンロードする。

    Returns:
        [{"name": "ファイル名", "path": "保存先フルパス", "size": バイト数}, ...]
    """
    os.makedirs(download_dir, exist_ok=True)

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

    return downloaded


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

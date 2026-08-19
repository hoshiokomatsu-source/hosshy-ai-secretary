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

AD_URL_RE = re.compile(
    r"imobile|doubleclick|googlesyndication|googleadservices|adsystem|"
    r"adnxs|criteo|ad-stir|microad|openx|adsrvr|taboola|outbrain|"
    r"adtrafficquality|pagead2",
    re.I,
)

CLOSE_BUTTON_SELECTOR = (
    "button[aria-label='Close'], button[aria-label='close'], button[aria-label='閉じる'], "
    "button[title='閉じる'], button[title='Close'], "
    ".close, .btn-close, [class*='close-button'], [class*='ad-close'], "
    "img[alt='close'], img[alt='閉じる'], img[alt='閉じるボタン']"
)

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


async def download_gigafile_url(url: str, download_dir: str, on_progress=None) -> list[dict]:
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
        await context.route("**/*", _block_ad_request)
        page = await context.new_page()
        stop_watch = asyncio.Event()
        watch = asyncio.create_task(_watch_gigafile_progress(page, on_progress, stop_watch))
        try:
            # ギガファイル便は広告・解析スクリプトのバックグラウンド通信が続くため
            # "networkidle" だと（実際にはページが表示済みでも）タイムアウトしやすい。
            # DOM構築完了まで待ち、あとはダウンロードボタンの出現を明示的に待つ。
            _emit(on_progress, 8, "ページを開いてるよ…", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            try:
                await page.wait_for_selector(DOWNLOAD_BUTTON_SELECTOR, timeout=30_000)
            except PlaywrightTimeoutError:
                pass  # ボタンが見つからない場合は下のフォールバック検索に任せる

            await _dismiss_ads(page)

            # 「まとめてダウンロード」があればそれ1つだけ。個別ボタンを全部押すと
            # ZIPと中身が Active に二重に溜まる。
            download_buttons = await _select_download_buttons(page)

            total = max(len(download_buttons), 1)
            await _attach_cdp_progress(page, on_progress)

            for i, button in enumerate(download_buttons, 1):
                try:
                    _emit(on_progress, 10 + int(70 * (i - 1) / total), f"ダウンロードしてるよ… {i}/{total}", url)
                    await _dismiss_ads(page)
                    async with page.expect_download(timeout=120_000) as download_info:
                        await _click_download(button)

                    download: Download = await download_info.value
                    original_name = download.suggested_filename or f"file_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    _emit(on_progress, 10 + int(70 * (i - 0.2) / total), f"保存してるよ… {original_name}", f"{i}/{total}")

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
        finally:
            stop_watch.set()
            watch.cancel()
            try:
                await watch
            except asyncio.CancelledError:
                pass
            await browser.close()

    if not downloaded:
        downloaded = _files_added_since(download_dir, before)
        if downloaded:
            print(f"[downloader] ボタン処理は失敗したが、新規ファイルを {len(downloaded)} 件検出したので転記対象にする")

    if any(Path(f["path"]).suffix.lower() == ".zip" for f in downloaded):
        _emit(on_progress, 80, "ZIPを解凍してるよ…", "")
    return _expand_archives(downloaded, download_dir)


async def _block_ad_request(route) -> None:
    url = route.request.url
    if AD_URL_RE.search(url):
        await route.abort()
        return
    await route.continue_()


def _emit(on_progress, pct, line: str, detail: str = "") -> None:
    if not on_progress:
        return
    try:
        on_progress(int(pct), line, detail)
    except Exception:
        pass


async def _watch_gigafile_progress(page, on_progress, stop: asyncio.Event) -> None:
    """ページ上の『12%』表示を拾ってUIに流す。"""
    last = None
    while not stop.is_set():
        try:
            pct = await page.evaluate(
                """() => {
                  const t = document.body ? document.body.innerText : '';
                  const ms = [...t.matchAll(/(\\d{1,3})\\s*%/g)]
                    .map(m => Number(m[1])).filter(n => n >= 0 && n <= 100);
                  if (!ms.length) return null;
                  return Math.max(...ms);
                }"""
            )
            if isinstance(pct, (int, float)) and pct != last:
                last = int(pct)
                mapped = 10 + int(last * 0.7)
                _emit(on_progress, mapped, f"ダウンロードしてるよ… {last}%", f"{last}%")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.8)
        except asyncio.TimeoutError:
            continue


async def _attach_cdp_progress(page, on_progress) -> None:
    """ブラウザの実バイト進捗。Playwrightの保存処理は触らない。"""
    try:
        cdp = await page.context.new_cdp_session(page)

        def _on_prog(params: dict) -> None:
            total = params.get("totalBytes") or 0
            recv = params.get("receivedBytes") or 0
            if total <= 0:
                return
            pct = min(100, int(recv * 100 / total))
            mb = f"{recv/1024/1024:.1f}/{total/1024/1024:.1f} MB"
            _emit(on_progress, 10 + int(pct * 0.7), f"ダウンロードしてるよ… {pct}%", mb)

        cdp.on("Browser.downloadProgress", _on_prog)
        print("[downloader] CDPのダウンロード進捗を監視する")
    except Exception as e:
        print(f"[downloader] CDP進捗は使えない: {e}")


async def _dismiss_ads(page) -> None:
    """オーバーレイ広告の閉じるボタンを押し、残った枠はDOMから外す。"""
    for frame in page.frames:
        try:
            loc = frame.locator(CLOSE_BUTTON_SELECTOR)
            n = await loc.count()
        except Exception:
            continue
        for i in range(min(n, 8)):
            try:
                await loc.nth(i).click(timeout=800, force=True)
            except Exception:
                pass
        try:
            xs = frame.get_by_text("×", exact=True)
            for i in range(min(await xs.count(), 6)):
                await xs.nth(i).click(timeout=500, force=True)
        except Exception:
            pass

    try:
        removed = await page.evaluate(
            """() => {
              const kill = (el) => { try { el.remove(); return 1; } catch (e) { return 0; } };
              let n = 0;
              document.querySelectorAll(
                '[id^="im-"], [id*="imobile"], [data-imobile-creative-width], [class*="imobile"]'
              ).forEach((el) => { n += kill(el); });
              document.querySelectorAll('iframe').forEach((el) => {
                const src = (el.src || '') + (el.getAttribute('data-src') || '');
                if (/imobile|doubleclick|googlesyndication|adsystem/i.test(src)) n += kill(el);
              });
              for (const el of document.querySelectorAll('div, aside, section, iframe')) {
                const s = getComputedStyle(el);
                const z = parseInt(s.zIndex, 10);
                if ((s.position === 'fixed' || s.position === 'absolute') && z > 1000) {
                  const r = el.getBoundingClientRect();
                  if (r.width > 120 && r.height > 60) n += kill(el);
                }
              }
              return n;
            }"""
        )
        if removed:
            print(f"[downloader] 広告オーバーレイを {removed} 件外した")
    except Exception as e:
        print(f"[downloader] 広告除去に失敗: {e}")


async def _select_download_buttons(page) -> list:
    """まとめてダウンロードがあればそれだけ返す。なければ個別ボタン。"""
    buttons = await page.query_selector_all(DOWNLOAD_BUTTON_SELECTOR)
    if not buttons:
        buttons = await page.query_selector_all("[onclick*='download'], [href*='download']")

    bundle = []
    others = []
    for button in buttons:
        label = await _button_label(button)
        if "まとめて" in label:
            bundle.append(button)
        else:
            others.append(button)

    if bundle:
        print("[downloader] 「まとめてダウンロード」があるので、それだけ押す")
        return bundle[:1]
    print(f"[downloader] まとめてボタンなし。個別ボタン {len(others)} 件")
    return others


async def _button_label(button) -> str:
    try:
        value = await button.get_attribute("value") or ""
        text = await button.inner_text() or ""
        return f"{value} {text}"
    except Exception:
        return ""


async def _click_download(button) -> None:
    try:
        await button.click(force=True, timeout=8_000)
        return
    except Exception as e:
        print(f"[downloader] 強制クリック失敗、DOM click に切替: {e}")
    await button.evaluate("el => el.click()")


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

    out_dir = os.path.join(dest_dir, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"[downloader] ZIP解凍開始: {zip_path} → {out_dir}")
    extracted = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = _zip_member_name(info)
                out_name = Path(name).name
                out_path = os.path.join(out_dir, out_name)
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
        "AUDI3-1.mp4" → "AUDI3-1"（数字-数字が名前の途中ならそのまま）
    """
    stem = Path(filename).stem
    leading = re.match(r"^(\d+-\d+)", stem)
    if leading:
        return leading.group(1)
    trailing = re.search(r"_(\d+-\d+)", stem)
    if trailing:
        return trailing.group(1)
    return stem

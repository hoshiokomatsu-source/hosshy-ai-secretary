"""ホッシーくん画面。127.0.0.1:8765 のみ。Tunnel には出さない。"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

import pipeline
from status import read_status, set_status

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
HOST = "127.0.0.1"
PORT = int(os.getenv("UI_PORT", "8765"))
_loop: asyncio.AbstractEventLoop | None = None


def _start_loop() -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[ui] {self.address_string()} {fmt % args}")

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/hosshy.png":
            self._file(UI_DIR / "hosshy.png", "image/png")
            return
        if parsed.path == "/hosshy-sleep.png":
            self._file(UI_DIR / "hosshy-sleep.png", "image/png")
            return
        if parsed.path == "/hosshy-work.png":
            self._file(UI_DIR / "hosshy-work.png", "image/png")
            return
        if parsed.path == "/hosshy-work-desk.png":
            self._file(UI_DIR / "hosshy-work-desk.png", "image/png")
            return
        if parsed.path == "/api/status":
            self._json(200, read_status())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "JSON が読めません"})
            return

        if parsed.path == "/api/wake":
            set_status("wake", "お仕事なんでも欲しがり！リンクを貼って！", "")
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/idle":
            set_status("idle", "zzz… ホッシーくん！って呼んでくれたら起きるよ", "")
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/download":
            url = str(body.get("url") or "").strip()
            if "gigafile" not in url:
                self._json(400, {"ok": False, "error": "ギガファイル便のURLを貼ってね"})
                return
            pipeline.last_job_status = "⏳ ダウンロード実行中です..."
            set_status("working", "ダウンロードしてるよ…ちょっと待ってて！", url)
            assert _loop is not None
            asyncio.run_coroutine_threadsafe(pipeline.run_download_pipeline(url), _loop)
            self._json(200, {"ok": True})
            return

        self.send_error(404)


def main() -> None:
    if not (UI_DIR / "index.html").exists():
        raise SystemExit(f"UI が見つかりません: {UI_DIR}")
    threading.Thread(target=_start_loop, daemon=True).start()
    set_status("idle", "zzz… ホッシーくん！って呼んでくれたら起きるよ", "")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"🦊 ホッシーくん画面: http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

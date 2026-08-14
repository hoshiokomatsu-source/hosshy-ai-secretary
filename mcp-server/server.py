"""ホッシーくん MCP サーバー

起動方法:
  python server.py

Cloudflare Tunnel で外部公開する場合:
  cloudflared tunnel --url http://localhost:8000
  → 発行されたURLを Claude.ai の設定 > Integrations > MCP に登録する
"""

import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from downloader import download_gigafile_url
from sheets import write_files_to_sheet

load_dotenv()

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", os.path.expanduser(
    "~/Dropbox/komatsu hoshio/Movie Edit/R4/Active"
))

PORT = int(os.getenv("PORT", "8000"))

mcp = FastMCP("hosshy-secretary")


@mcp.tool()
async def download_and_record(gigafile_url: str) -> str:
    """ギガファイル便のURLからファイルをダウンロードし、スプレッドシートに転記する。

    Args:
        gigafile_url: ギガファイル便のURL（例: https://gigafile.nu/XXXXXXXX）
    """
    # 1. ダウンロード
    downloaded_files = await download_gigafile_url(gigafile_url, DOWNLOAD_DIR)

    if not downloaded_files:
        return "ダウンロードできるファイルが見つかりませんでした。URLを確認してください。"

    file_names = [f["name"] for f in downloaded_files]

    # 2. スプレッドシート転記
    sheet_result = await write_files_to_sheet(downloaded_files)

    lines = [f"✅ ダウンロード完了: {len(file_names)} ファイル"]
    lines.append(f"📁 保存先: {DOWNLOAD_DIR}")
    lines.append("")
    lines.extend([f"  - {name}" for name in file_names])
    lines.append("")
    lines.append(f"📊 スプレッドシート: {sheet_result}")

    return "\n".join(lines)


@mcp.tool()
async def list_downloaded_files() -> str:
    """ダウンロードフォルダの現在のファイル一覧を返す。"""
    if not os.path.exists(DOWNLOAD_DIR):
        return f"フォルダが存在しません: {DOWNLOAD_DIR}"

    files = [f for f in os.listdir(DOWNLOAD_DIR) if not f.startswith(".")]
    if not files:
        return "ファイルはありません。"

    lines = [f"📁 {DOWNLOAD_DIR}", ""]
    lines.extend([f"  {i+1}. {f}" for i, f in enumerate(sorted(files))])
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="sse", port=PORT)

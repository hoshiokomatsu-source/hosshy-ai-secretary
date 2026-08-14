"""ホッシーくん MCP サーバー

Claude.ai / Claude Cowork の「カスタムコネクタ」はOAuth 2.1認証を
必須にしているため、oauth_provider.py の簡易OAuthプロバイダーを
組み込んだ上で、Cloudflare Tunnel等で公開したHTTPS URLを登録する。

起動方法:
  PUBLIC_URL=https://xxxx.trycloudflare.com python server.py

Cloudflare Tunnel で外部公開する場合:
  cloudflared tunnel --url http://localhost:8000
  → 発行されたURLを PUBLIC_URL に設定してサーバーを起動し直し、
    そのURLを Claude.ai の コネクタ に登録する
"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from downloader import download_gigafile_url
from oauth_provider import SingleUserOAuthProvider
from sheets import write_files_to_sheet

load_dotenv()

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", os.path.expanduser(
    "~/Dropbox/komatsu hoshio/Movie Edit/R4/Active"
))

PORT = int(os.getenv("PORT", "8000"))

# Cloudflare Tunnelで発行されたURL。起動のたびに変わるので毎回 .env か
# 環境変数で渡す。設定されていなければOAuthなしのローカル動作にフォールバックする。
PUBLIC_URL = os.getenv("PUBLIC_URL")

# Cloudflare Tunnel経由だとHostヘッダーがlocalhost以外になるため、
# デフォルトのDNS rebinding protectionを無効化しておく
# （無効化しないとHostヘッダー不一致で例外が発生しサーバーごと落ちる）
_transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

if PUBLIC_URL:
    mcp = FastMCP(
        "hosshy-secretary",
        port=PORT,
        transport_security=_transport_security,
        auth_server_provider=SingleUserOAuthProvider(),
        auth=AuthSettings(
            issuer_url=PUBLIC_URL,
            # Claude.aiに登録するURL（末尾/mcp付き）と完全一致させる必要がある。
            # ここが不一致だと、OAuth自体は成功するのに「MCPサーバーが見つからない」
            # というエラーになる（保護リソースメタデータのresourceフィールド不一致）。
            resource_server_url=f"{PUBLIC_URL}/mcp",
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["hosshy"],
                default_scopes=["hosshy"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )
else:
    mcp = FastMCP("hosshy-secretary", port=PORT, transport_security=_transport_security)


# Claude.ai/Desktop はツール実行を最大5分（300秒）待つと待たずに
# タイムアウト扱いにする（公式ドキュメント記載）。大容量ファイルは
# ダウンロードそのものに5分以上かかることがあるため、ツール呼び出しは
# すぐ返し、実際のダウンロード〜シート転記はバックグラウンドで進める。
_background_tasks: set[asyncio.Task] = set()
_last_job_status: str = "まだダウンロードを実行していません。"


async def _run_download_and_record(gigafile_url: str) -> None:
    global _last_job_status
    started_at = datetime.now().strftime("%H:%M:%S")
    try:
        downloaded_files = await download_gigafile_url(gigafile_url, DOWNLOAD_DIR)
    except Exception as e:
        _last_job_status = (
            f"❌ [{started_at}開始] ダウンロード処理でエラーが発生しました。\n"
            f"詳細: {type(e).__name__}: {e}\n"
            "URLの有効期限やギガファイル便側の混雑状況を確認し、もう一度試してください。"
        )
        return

    if not downloaded_files:
        _last_job_status = f"[{started_at}開始] ダウンロードできるファイルが見つかりませんでした。URLを確認してください。"
        return

    file_names = [f["name"] for f in downloaded_files]
    sheet_result = await write_files_to_sheet(downloaded_files)

    finished_at = datetime.now().strftime("%H:%M:%S")
    lines = [f"✅ [{started_at}開始 → {finished_at}完了] ダウンロード完了: {len(file_names)} ファイル"]
    lines.append(f"📁 保存先: {DOWNLOAD_DIR}")
    lines.append("")
    lines.extend([f"  - {name}" for name in file_names])
    lines.append("")
    lines.append(f"📊 スプレッドシート: {sheet_result}")
    _last_job_status = "\n".join(lines)


@mcp.tool()
async def download_and_record(gigafile_url: str) -> str:
    """ギガファイル便のURLからファイルをダウンロードし、スプレッドシートに転記する。

    ダウンロードはバックグラウンドで実行され、この呼び出しはすぐに応答を返す
    （大容量ファイルはダウンロードだけで5分以上かかることがあり、Claude側の
    ツール実行タイムアウトに引っかかってしまうため）。完了したかどうかは
    `check_download_status` または `list_downloaded_files` で確認できる。

    Args:
        gigafile_url: ギガファイル便のURL（例: https://gigafile.nu/XXXXXXXX）
    """
    global _last_job_status
    _last_job_status = "⏳ ダウンロード実行中です..."
    task = asyncio.create_task(_run_download_and_record(gigafile_url))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return (
        "⏳ ダウンロードをバックグラウンドで開始しました。\n"
        "大きいファイルの場合は完了まで数分かかることがあります。\n"
        "少し時間をおいてから「ダウンロード状況を確認して」または"
        "「ファイル一覧を確認して」と聞いてください。"
    )


@mcp.tool()
async def check_download_status() -> str:
    """直近のdownload_and_recordの進行状況・結果を確認する。"""
    return _last_job_status


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
    import uvicorn
    # Claude.aiの最新コネクタは Streamable HTTP（/mcp）を前提にしているため、
    # 旧来のSSE（/sse）ではなくこちらを使う。
    app = mcp.streamable_http_app()
    print(f"🚀 ホッシーくん起動中... http://0.0.0.0:{PORT}/mcp")
    if PUBLIC_URL:
        print(f"🔐 OAuth有効: {PUBLIC_URL}/mcp をClaudeのコネクタに登録してください")
    else:
        print("⚠️  PUBLIC_URLが未設定のためOAuthは無効です（ローカルテスト用）")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

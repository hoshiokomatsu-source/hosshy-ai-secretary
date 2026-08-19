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
from dotenv import load_dotenv
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from oauth_provider import SingleUserOAuthProvider
import pipeline
from premiere import (
    premiere_is_running,
    prepare_premiere_project,
    read_premiere_result,
    resolve_media_folder,
)
from status import set_status

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


async def _run_download_and_record(gigafile_url: str) -> None:
    await pipeline.run_download_pipeline(gigafile_url)


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
    pipeline.last_job_status = "⏳ ダウンロード実行中です..."
    set_status("working", "ダウンロードしてるよ…ちょっと待ってて！", gigafile_url, pose="download")
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
    return pipeline.last_job_status


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


@mcp.tool()
async def prepare_premiere(folder_path: str = "") -> str:
    """ダウンロード済みフォルダから Premiere プロジェクトを作り、素材を読み込み、動画の数だけシーケンスを作成する。

    プロジェクト名はフォルダ名と同じ（例: みね20260804/ → みね20260804.prproj）。
    シーケンス作成は既存の NewSequence.jsx を実行し、保存して Premiere を終了する。
    帰宅後に .prproj を開くと、素材とシーケンスが入った状態で編集を始められる。

    Args:
        folder_path: 動画が入ったフォルダ。空なら Active 内で一番新しいバッチフォルダを使う。
    """
    try:
        folder = resolve_media_folder(folder_path or None, DOWNLOAD_DIR)
        set_status("working", "Premiere でシーケンス作ってるよ…", folder, pose="premiere")
        result = prepare_premiere_project(folder)
    except Exception as e:
        set_status("idle", "Premiere がうまくいかなかった…", str(e))
        return f"❌ Premiere セットアップを開始できませんでした。\n詳細: {type(e).__name__}: {e}"

    lines = [
        result["message"],
        f"📁 フォルダ: {result['folder']}",
        f"🎞 動画: {result['video_count']} 本",
        f"📄 プロジェクト: {result['project_path']}",
    ]
    if result["status"] == "started":
        lines.append("完了したら Premiere は自動で終了します。状況は「Premiereの状況を確認して」で聞けます。")
    return "\n".join(lines)


@mcp.tool()
async def check_premiere_status() -> str:
    """直近の Premiere セットアップ結果を確認する。"""
    result = read_premiere_result()
    if not result:
        if premiere_running_message := _premiere_running_hint():
            return premiere_running_message
        return "まだ Premiere セットアップの結果がありません。先に prepare_premiere を実行してください。"
    if result.startswith("OK"):
        return f"✅ {result}"
    if result.startswith("TIMEOUT"):
        return f"⏳ {result}"
    return f"❌ {result}"


def _premiere_running_hint() -> str | None:
    if premiere_is_running() and not read_premiere_result():
        return "⏳ Premiere は起動しています。プロジェクト作成〜シーケンス作成の完了を待っています。"
    return None


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

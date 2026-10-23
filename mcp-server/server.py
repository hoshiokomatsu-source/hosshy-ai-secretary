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
    premiere_job_status_text,
    prepare_mixed_project,
    prepare_premiere_project,
    resolve_media_folder,
    start_mask_tracking,
)
from status import mark_finished, set_status
import freee as freee_api
import amazon as amazon_api
import freee_ui

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


def _premiere_reply(result: dict) -> str:
    lines = [result["message"]]
    if "folder" in result:
        lines += [
            f"📁 フォルダ: {result['folder']}",
            f"🎞 動画: {result['video_count']} 本",
            f"📄 プロジェクト: {result['project_path']}",
        ]
    if result["status"] == "started":
        lines.append("時間がかかるので、状況は「Premiereの状況を確認して」(check_premiere_status)で聞いてください。")
    return "\n".join(lines)


@mcp.tool()
async def prepare_premiere(folder_path: str = "") -> str:
    """ダウンロード済みフォルダから Premiere プロジェクトを作り、動画の数だけ横(1920×1080)のシーケンスを作って、
    R4自動処理(⌘6・調整レイヤー3つ・Lumetri自動・オーディオゲイン)までかける。

    中身は R4(~/Documents/src/Movie Edit/R4 の シーケンス作成/make_project.py --orientation 横)。
    プロジェクト名はフォルダ名と同じ（例: みね20260804/ → みね20260804.prproj）。終わると保存して Premiere を終了する。
    時間がかかるのでバックグラウンドで動き、この呼び出しはすぐ返る。状況は check_premiere_status で確認する。
    Premiere が開いていたら何もせず「閉じてからもう一度」と返す。
    縦と横が混ざった素材や、b に a の音声を同期したいときは prepare_premiere_mixed を使う。

    Args:
        folder_path: 動画が入ったフォルダ。空なら Active 内で一番新しいバッチフォルダを使う。
    """
    try:
        folder = resolve_media_folder(folder_path or None, DOWNLOAD_DIR)
        return _premiere_reply(prepare_premiere_project(folder))
    except Exception as e:
        return f"❌ Premiere セットアップを開始できませんでした。\n詳細: {type(e).__name__}: {e}"


@mcp.tool()
async def prepare_premiere_mixed(folder_path: str = "", exception: bool = False) -> str:
    """縦横対応。縦と横が混ざった素材フォルダから、1つの Premiere プロジェクトを作って R4自動処理までかける。
    「縦横対応して」「縦横混ざってるからシーケンス作って」で使う。

    縦か横かは素材の見た目(回転を含む)で判断し、混ざっていればフォルダの中に「<フォルダ名>-横」「<フォルダ名>-縦」を作って移動する。
    横は 1920×1080、縦は 1080×1920 のシーケンス。b の素材には同じ番号の a の音声を同期する(c 以降がある番号は同期しない)。
    中身は R4 の シーケンス作成/make_project.py(縦横の判定 → 仕分け → プロジェクト作成 → R4自動処理)。終わると保存して Premiere を終了する。
    時間がかかるのでバックグラウンドで動き、この呼び出しはすぐ返る。状況は check_premiere_status で確認する。
    Premiere が開いていたら何もせず「閉じてからもう一度」と返す。

    Args:
        folder_path: 素材フォルダ。空なら Active 内で一番新しいバッチフォルダを使う。
        exception: 「例外」と言われたら True。a/b の音声同期をしない。
    """
    try:
        folder = resolve_media_folder(folder_path or None, DOWNLOAD_DIR)
        return _premiere_reply(prepare_mixed_project(folder, exception))
    except Exception as e:
        return f"❌ 縦横対応を開始できませんでした。\n詳細: {type(e).__name__}: {e}"


@mcp.tool()
async def mask_tracking(second_round: bool = False) -> str:
    """マスク自動トラッキング。Premiere のタイムラインに開いている全シーケンスのオブジェクトマスクを、順番に ◀▶ で追跡する。
    「トラッキングして」で使う。「2周目」「V2 のマスクも」と言われたら second_round=True(V2 の素材のマスクを追跡する)。

    先にユーザーが Premiere でマスクを作り、トラッキングするシーケンスをタイムラインに開いておく必要がある。
    1シーケンス約9分かかるのでバックグラウンドで動き、この呼び出しはすぐ返る。状況は check_premiere_status で確認する。
    中身は R4 の マスク自動トラッキング/track_masks.py run(2周目は --track 2)。

    Args:
        second_round: True なら 2周目(V2 の素材のマスク)。
    """
    try:
        return _premiere_reply(start_mask_tracking(2 if second_round else 1))
    except Exception as e:
        return f"❌ トラッキングを開始できませんでした。\n詳細: {type(e).__name__}: {e}"


@mcp.tool()
async def check_premiere_status() -> str:
    """直近の Premiere の作業(prepare_premiere / prepare_premiere_mixed / mask_tracking)の状況と結果を確認する。"""
    return premiere_job_status_text()


@mcp.tool()
async def freee_check() -> str:
    """freeeの未登録口座明細を確認する。「経費チェックして」「freee確認して」で呼び出せる。

    ルール（QuickPay=プライベート、コメダ・スタバ等=会議費）と過去データを
    もとに自動分類し、確認が必要なものをリストアップする。
    """
    set_status("working", "経費チェックしてるよ…ちょっと待ってて！", "", pose="keihi")
    try:
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, freee_api.get_categorization_summary)
    except Exception as e:
        set_status("idle", "zzz…", "", pose="sleep")
        return f"❌ freee API エラー: {e}"
    set_status("idle", "zzz…", "", pose="sleep")

    lines: list[str] = []
    auto = summary["auto"]
    skip = summary["skip"]
    review = summary["review"]
    amazon = summary["amazon"]

    lines.append(f"📊 未登録明細: 自動仕分け {len(auto)}件 / スキップ {len(skip)}件 / 要確認 {len(review)}件 / Amazon {len(amazon)}件\n")

    if auto:
        lines.append("✅ 自動仕分け（確認後に登録できます）")
        for item in auto:
            lines.append(f"  {item['txn'].get('date','')} ¥{item['amount']:,} {item['description']} → {item['category']}")
        lines.append("")

    if amazon:
        lines.append("🛒 Amazon（要確認）")
        for i, item in enumerate(amazon, 1):
            lines.append(f"  [{i}] {item['date']} ¥{item['amount']:,} {item['description']}")
        lines.append("  → 「Amazon の[番号]は経費（消耗品費）」「Amazon の[番号]はプライベート」と教えてください")
        lines.append("")

    if review:
        lines.append("❓ 判断できなかったもの")
        for i, item in enumerate(review, 1):
            lines.append(f"  [{i}] {item['txn'].get('date','')} ¥{item['amount']:,} {item['description']}")
        lines.append("  → 「[番号]は会議費」「[番号]はプライベート」と教えてください")
        lines.append("")

    if skip:
        lines.append(f"⏭ スキップ（プライベート判定）: {len(skip)}件")

    return "\n".join(lines)


@mcp.tool()
async def freee_add(
    txn_date: str,
    description: str,
    amount: int,
    account_item_name: str,
) -> str:
    """freeeに仕訳を1件登録する。「これは会議費で登録して」「[番号]は消耗品費」で呼び出せる。

    Args:
        txn_date: 取引日（YYYY-MM-DD）
        description: 摘要（店名など）
        amount: 金額（正の整数、円）
        account_item_name: 勘定科目名（例: 会議費、消耗品費、交通費）
    """
    set_status("working", "freeeに登録してるよ…", "", pose="keihi")
    try:
        loop = asyncio.get_running_loop()
        txns = await loop.run_in_executor(None, freee_api.get_unregistered_txns)
        txn = next(
            (t for t in txns
             if t.get("date", "") == txn_date
             and abs(int(t.get("amount", 0))) == amount),
            None
        )
        if txn is None:
            set_status("idle", "zzz…", "", pose="sleep")
            return f"❌ {txn_date} ¥{amount:,} の未登録明細が見つかりませんでした。"

        def _register():
            return freee_ui.register_txns(
                registrations=[{"txn": txn, "category": account_item_name}],
                skips=[],
            )

        result = await loop.run_in_executor(None, _register)
        set_status("idle", "zzz…", "", pose="sleep")

        if result.get("error"):
            return f"❌ {result['error']}"
        if result["registered"]:
            return f"✅ 登録しました: {txn_date} ¥{amount:,} {description} → {account_item_name}"
        if result["failed"]:
            err = result["failed"][0].get("error", "不明なエラー")
            return f"❌ 登録エラー: {err}"
        return f"⚠️ 明細が見つかりませんでした: {txn_date} ¥{amount:,}"
    except Exception as e:
        set_status("idle", "zzz…", "", pose="sleep")
        return f"❌ 登録エラー: {e}"


@mcp.tool()
async def freee_amazon_list() -> str:
    """freeeのAmazon未登録明細一覧を返す。「Amazon照合して」「Amazonの経費確認」で呼び出せる。

    このツールでfreeeのAmazon明細を取得後、ブラウザで
    https://www.amazon.co.jp/gp/css/order-history?orderFilter=months-3
    を開いて日付・金額で照合し、各明細が何の購入かを提案してください。
    """
    try:
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, freee_api.get_categorization_summary)
        amazon_txns = summary["amazon"]

        if not amazon_txns:
            return "Amazon の未登録明細はありませんでした。"

        lines = [f"🛒 freeeのAmazon未登録明細 {len(amazon_txns)}件：\n"]
        for i, item in enumerate(amazon_txns, 1):
            lines.append(f"  [{i}] {item['date']} ¥{item['amount']:,}  {item['description']}")

        lines.append("")
        lines.append("↑ これらをAmazonの注文履歴（過去3ヶ月）と照合して商品名を確認し、")
        lines.append("各明細が経費か否かをホシさんに提案してください。")
        lines.append("URL: https://www.amazon.co.jp/gp/css/order-history?orderFilter=months-3")
        return "\n".join(lines)

    except Exception as e:
        return f"❌ freee API エラー: {e}"


@mcp.tool()
async def freee_auto() -> str:
    """自動仕分けできた明細とプライベート判定の明細を一括でfreeeに登録・除外する。
    「自動登録して」「まとめて登録」で呼び出せる。

    ルールと過去データで確実に判断できたものだけを処理する。
    経費 → 勘定科目を付けて登録、プライベート → 対象外にする。
    Amazon・判断不明なものは含まれない。
    """
    set_status("working", "freeeに一括登録してるよ…ちょっと待ってて！", "", pose="keihi")
    try:
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, freee_api.get_categorization_summary)
    except Exception as e:
        set_status("idle", "zzz…", "", pose="sleep")
        return f"❌ freee API エラー: {e}"

    auto = summary["auto"]    # 経費として登録するもの
    skip = summary["skip"]    # 対象外（プライベート）にするもの

    if not auto and not skip:
        set_status("idle", "zzz…", "", pose="sleep")
        return "自動処理できる明細はありませんでした。"

    def _register_all():
        return freee_ui.register_txns(
            registrations=auto,
            skips=skip,
        )

    try:
        result = await loop.run_in_executor(None, _register_all)
    except Exception as e:
        mark_finished("うまくいかなかった…", str(e), pose="sleep")
        return f"❌ 一括登録エラー: {e}"
    mark_finished()

    if result.get("error"):
        return f"❌ {result['error']}"

    reg_count = len(result.get("registered", []))
    skip_count = len(result.get("skipped", []))
    fail_count = len(result.get("failed", []))

    lines = [f"一括処理完了: 経費登録 {reg_count}件 / 対象外 {skip_count}件 / 失敗 {fail_count}件"]

    if result.get("failed"):
        lines.append("\n失敗したもの:")
        for f in result["failed"]:
            lines.append(f"  ❌ txn_id={f['txn_id']}: {f.get('error', '不明')}")

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

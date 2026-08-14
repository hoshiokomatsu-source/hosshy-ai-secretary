"""Google Sheets 転記モジュール

事前準備:
1. Google Cloud Console でサービスアカウントを作成
2. Google Sheets API を有効化
3. credentials.json をダウンロードして GOOGLE_CREDENTIALS_PATH に配置
4. スプレッドシートをそのサービスアカウントのメールアドレスと共有
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.expanduser("~/.config/hosshy/credentials.json")
)

# 書き込む先のシート名と開始列
SHEET_NAME = "シート1"
# カラム順: 月 | フォルダ名 | タイトル | 内容 | 発注日 | 納品日
COLUMNS = ["月", "フォルダ名", "タイトル", "内容", "発注日", "納品日"]


async def write_files_to_sheet(files: list[dict]) -> str:
    """ダウンロードしたファイル情報をスプレッドシートに転記する。

    Args:
        files: downloader.py が返すファイル情報のリスト

    Returns:
        結果メッセージ
    """
    if not SPREADSHEET_ID:
        return "⚠️ SPREADSHEET_ID が未設定のためスキップしました（.env を確認）"

    if not Path(CREDENTIALS_PATH).exists():
        return f"⚠️ credentials.json が見つかりません: {CREDENTIALS_PATH}"

    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        today = datetime.now()
        rows = []
        for f in files:
            order_date = today.strftime("%Y/%m/%d")
            delivery_date = (today + timedelta(days=7)).strftime("%Y/%m/%d")
            folder_name = _extract_folder_name(f["name"], today)

            rows.append([
                today.strftime("%Y/%m"),   # 月
                folder_name,               # フォルダ名
                f["stem"],                 # タイトル
                "動画編集",               # 内容（固定）
                order_date,               # 発注日
                delivery_date,            # 納品日
            ])

        body = {"values": rows}
        result = sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        updated = result.get("updates", {}).get("updatedRows", len(rows))
        return f"{updated} 行を追記しました"

    except Exception as e:
        return f"❌ スプレッドシート書き込みエラー: {e}"


def _extract_folder_name(filename: str, date: datetime) -> str:
    """ファイル名からフォルダ名を生成する。

    例: "ホシオ0808_36-1.mp4" → "ホシオ0808"
        "36-1ド.mp4" → "ホシオ0814"（日付フォールバック）
    """
    stem = Path(filename).stem
    # 先頭の日本語＋数字パターンを抽出（例: ホシオ0808）
    import re
    match = re.match(r"^([\u3040-\u30ff\u4e00-\u9fff\uff66-\uff9fA-Za-z]+\d{4})", stem)
    if match:
        return match.group(1)
    return f"ホシオ{date.strftime('%m%d')}"

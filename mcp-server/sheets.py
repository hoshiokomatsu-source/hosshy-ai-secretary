"""Google Sheets 転記モジュール

事前準備:
1. Google Cloud Console でサービスアカウントを作成
2. Google Sheets API を有効化
3. credentials.json をダウンロードして GOOGLE_CREDENTIALS_PATH に配置
4. スプレッドシートをそのサービスアカウントのメールアドレスと共有
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.expanduser("~/.config/hosshy/credentials.json")
)

# 実シートのタブは「2026/8」形式。列は既存パートナーシートに合わせる。
# A:月  B:フォルダ名  C:タイトル  D:内容  E:発注日  F:納品日
HEADER_ROW = ["", "　撮影日※敬称略", "タイトル", "内容", "発注日", "納品日", "単価/分", "分", "進捗", "小計", "備考"]


async def write_files_to_sheet(files: list[dict]) -> str:
    """ダウンロードしたファイル情報をスプレッドシートに転記する。"""
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
        tab_name = _month_tab_name(today)
        _ensure_month_tab(sheet, tab_name)

        rows = []
        for f in files:
            folder_name = _extract_folder_name(f["name"], today)
            rows.append([
                f"{today.month}月",
                folder_name,
                f["stem"],
                "動画編集",
                _short_date(today),
                _short_date(today + timedelta(days=7)),
            ])

        existing = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A:F",
        ).execute().get("values", [])
        last = 1
        for i, row in enumerate(existing, 1):
            joined = "".join(str(c) for c in row)
            if joined.strip() and "合計" not in joined:
                last = i
        start_row = last + 1

        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A{start_row}",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()

        return f"{tab_name} の {start_row} 行目から {len(rows)} 行を追記しました"

    except Exception as e:
        return f"❌ スプレッドシート書き込みエラー: {e}"


def _month_tab_name(date: datetime) -> str:
    """既存シートに合わせ、先頭ゼロなしの『2026/8』形式にする。"""
    return f"{date.year}/{date.month}"


def _short_date(date: datetime) -> str:
    """既存シートに合わせ『8/18』形式にする。"""
    return f"{date.month}/{date.day}"


def _ensure_month_tab(sheet, tab_name: str) -> None:
    meta = sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if tab_name in existing:
        return

    sheet.batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{tab_name}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADER_ROW]},
    ).execute()


def _extract_folder_name(filename: str, date: datetime) -> str:
    """ファイル名からフォルダ名を生成する。

    例: "ホシオ0808_36-1.mp4" → "ホシオ0808"
        "36-1ド.mp4" → "ホシオ0814"（日付フォールバック）
    """
    stem = Path(filename).stem
    match = re.match(r"^([\u3040-\u30ff\u4e00-\u9fff\uff66-\uff9fA-Za-z]+\d{4})", stem)
    if match:
        return match.group(1)
    return f"ホシオ{date.strftime('%m%d')}"

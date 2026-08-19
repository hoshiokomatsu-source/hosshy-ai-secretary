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

def _spreadsheet_id() -> str:
    return os.getenv("SPREADSHEET_ID", "")


def _credentials_path() -> str:
    return os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        os.path.expanduser("~/.config/hosshy/credentials.json"),
    )

# 実シートのタブは「2026/8」形式。列は既存パートナーシートに合わせる。
# A:月  B:フォルダ名  C:タイトル  D:内容  E:発注日  F:納品日
HEADER_ROW = ["", "　撮影日※敬称略", "タイトル", "内容", "発注日", "納品日", "単価/分", "分", "進捗", "小計", "備考"]


async def write_files_to_sheet(files: list[dict]) -> str:
    """ダウンロードしたファイル情報をスプレッドシートに転記する。"""
    spreadsheet_id = _spreadsheet_id()
    credentials_path = _credentials_path()

    if not spreadsheet_id:
        return "⚠️ SPREADSHEET_ID が未設定のためスキップしました（.env を確認）"

    if not Path(credentials_path).exists():
        return f"⚠️ credentials.json が見つかりません: {credentials_path}"

    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        today = datetime.now()
        tab_name = _month_tab_name(today)
        _ensure_month_tab(sheet, spreadsheet_id, tab_name)

        existing = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A:F",
        ).execute().get("values", [])
        last = 1
        for i, row in enumerate(existing, 1):
            joined = "".join(str(c) for c in row)
            if joined.strip() and "合計" not in joined:
                last = i
        start_row = last + 1

        last_delivery = _last_delivery_date(existing, today)
        if not last_delivery:
            last_delivery = _last_delivery_from_previous_tab(
                sheet, spreadsheet_id, tab_name, today,
            )
        if last_delivery:
            delivery = last_delivery + timedelta(days=2)
        else:
            delivery = today + timedelta(days=14)

        rows = []
        for f in files:
            folder_name = f.get("folder") or _extract_folder_name(f["name"], today)
            rows.append([
                f"{today.month}月",
                folder_name,
                _sheet_title(f["stem"]),
                os.getenv("SHEET_CONTENT", "モザイク処理・加工"),
                _short_date(today),
                _short_date(delivery),
            ])

        sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A{start_row}",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
        sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!J{start_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [
                [f"=G{start_row + i}*H{start_row + i}"]
                for i in range(len(rows))
            ]},
        ).execute()
        _format_title_cells(sheet, spreadsheet_id, tab_name, start_row, len(rows))

        return f"{tab_name} の {start_row} 行目から {len(rows)} 行を追記しました"

    except Exception as e:
        return f"❌ スプレッドシート書き込みエラー: {e}"


def _month_tab_name(date: datetime) -> str:
    """既存シートに合わせ、先頭ゼロなしの『2026/8』形式にする。"""
    return f"{date.year}/{date.month}"


def _short_date(date: datetime) -> str:
    """既存シートに合わせ『8/18』形式にする。"""
    return f"{date.month}/{date.day}"


def _last_delivery_date(existing: list, today: datetime) -> datetime | None:
    """既存行の納品日（F列）を下から探し、最後の日付を返す。"""
    for row in reversed(existing):
        joined = "".join(str(c) for c in row)
        if "合計" in joined:
            continue
        if len(row) < 6:
            continue
        parsed = _parse_sheet_date(row[5], today)
        if parsed:
            return parsed
    return None


def _parse_sheet_date(value, today: datetime) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 20000:
        return datetime(1899, 12, 30) + timedelta(days=int(value))
    text = str(value).strip()
    if not text:
        return None
    patterns = (
        r"^(?P<y>\d{4})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})$",
        r"^(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{4})$",
        r"^(?P<m>\d{1,2})月(?P<d>\d{1,2})日$",
        r"^(?P<m>\d{1,2})/(?P<d>\d{1,2})$",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        parts = match.groupdict()
        year = int(parts["y"]) if parts.get("y") else today.year
        try:
            parsed = datetime(year, int(parts["m"]), int(parts["d"]))
        except ValueError:
            return None
        if "y" not in parts and parsed > today + timedelta(days=180):
            parsed = datetime(year - 1, parsed.month, parsed.day)
        return parsed
    return None


def _ensure_month_tab(sheet, spreadsheet_id: str, tab_name: str) -> None:
    """当月タブが無ければ直前の月タブを複製し、入力値だけ消して計算式を残す。"""
    meta = sheet.get(spreadsheetId=spreadsheet_id).execute()
    props = {s["properties"]["title"]: s["properties"] for s in meta.get("sheets", [])}
    if tab_name in props:
        return

    source_title = _template_tab_title(tab_name, props.keys())
    if source_title:
        sheet.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{
                "duplicateSheet": {
                    "sourceSheetId": props[source_title]["sheetId"],
                    "insertSheetIndex": 0,
                    "newSheetName": tab_name,
                }
            }]},
        ).execute()
        sheet.values().batchClear(
            spreadsheetId=spreadsheet_id,
            body={"ranges": [
                f"'{tab_name}'!A2:I",
                f"'{tab_name}'!K2:AH",
            ]},
        ).execute()
        print(f"[sheets] {source_title} を複製して {tab_name} を作った（小計の計算式は残す）")
        return

    sheet.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()
    sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADER_ROW]},
    ).execute()


def _template_tab_title(tab_name: str, titles) -> str | None:
    """複製元は直前の月。無ければ、それより前で一番新しいタブ。"""
    parsed = []
    for title in titles:
        key = _parse_month_tab(title)
        if key:
            parsed.append((key, title))
    if not parsed:
        return None
    target = _parse_month_tab(tab_name)
    if target:
        year, month = target
        prev = (year, month - 1) if month > 1 else (year - 1, 12)
        for key, title in parsed:
            if key == prev:
                return title
        older = [item for item in parsed if item[0] < target]
        if older:
            older.sort(key=lambda item: item[0], reverse=True)
            return older[0][1]
    parsed.sort(key=lambda item: item[0], reverse=True)
    return parsed[0][1]


def _parse_month_tab(title: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d{4})/(\d{1,2})\s*$", str(title).strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _last_delivery_from_previous_tab(sheet, spreadsheet_id: str, tab_name: str, today: datetime):
    meta = sheet.get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    source = _template_tab_title(tab_name, titles)
    if not source or source == tab_name:
        return None
    existing = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{source}'!A:F",
    ).execute().get("values", [])
    return _last_delivery_date(existing, today)


def _sheet_title(stem: str) -> str:
    """『1-1』などが日付に化けるのを防ぐ。"""
    if re.match(r"^\d+-\d+", stem):
        return f"'{stem}"
    return stem


def _tab_sheet_id(sheet, spreadsheet_id: str, tab_name: str) -> int:
    meta = sheet.get(spreadsheetId=spreadsheet_id).execute()
    for item in meta.get("sheets", []):
        if item["properties"]["title"] == tab_name:
            return item["properties"]["sheetId"]
    raise KeyError(f"タブがありません: {tab_name}")


def _format_title_cells(sheet, spreadsheet_id: str, tab_name: str, start_row: int, count: int) -> None:
    """タイトル列を文字列・左詰めにする。"""
    if count <= 0:
        return
    sheet_id = _tab_sheet_id(sheet, spreadsheet_id, tab_name)
    sheet.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row - 1,
                    "endRowIndex": start_row - 1 + count,
                    "startColumnIndex": 2,
                    "endColumnIndex": 3,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "LEFT",
                        "numberFormat": {"type": "TEXT"},
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.numberFormat",
            }
        }]},
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

"""freee API 連携モジュール

機能:
  - 未登録の口座明細（wallet_txns）取得
  - 過去仕訳データから店名→勘定科目を学習
  - ルールベース自動仕分け
  - freee への仕訳登録
  - アクセストークン自動リフレッシュ
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv, set_key

load_dotenv()

ENV_PATH = Path(__file__).parent / ".env"
COMPANY_ID = int(os.getenv("FREEE_COMPANY_ID", "2818195"))
BASE_URL = "https://api.freee.co.jp/api/1"
TOKEN_URL = "https://accounts.secure.freee.co.jp/public_api/token"

# ─── 仕分けルール（店名に含まれる文字列 → 勘定科目名） ─────────────────────
CATEGORY_RULES: list[tuple[str, str]] = [
    # コーヒー・会議場所
    ("スターバックス", "会議費"),
    ("STARBUCKS", "会議費"),
    ("タリーズ", "会議費"),
    ("TULLYS", "会議費"),
    ("米田コーヒー", "会議費"),
    ("コメダ", "会議費"),
    ("KOMEDA", "会議費"),
    # QuickPay は個人支出なので対象外
    ("QUICK PAY", None),
    ("QUICKPay", None),
    ("クイックペイ", None),
]

# ─── トークン管理 ────────────────────────────────────────────────────────────

def _refresh_token() -> str:
    """リフレッシュトークンでアクセストークンを更新し .env に保存して返す。"""
    client_id = os.getenv("FREEE_CLIENT_ID", "")
    client_secret = os.getenv("FREEE_CLIENT_SECRET", "")
    refresh_token = os.getenv("FREEE_REFRESH_TOKEN", "")
    if not refresh_token:
        raise RuntimeError("FREEE_REFRESH_TOKEN が設定されていません。再認証が必要です。")

    res = httpx.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, timeout=15)
    res.raise_for_status()
    data = res.json()

    new_access = data["access_token"]
    new_refresh = data.get("refresh_token", refresh_token)
    expires_in = data.get("expires_in", 21600)
    expires_at = int(time.time()) + expires_in - 300  # 5分前に期限切れ扱い

    set_key(str(ENV_PATH), "FREEE_ACCESS_TOKEN", new_access)
    set_key(str(ENV_PATH), "FREEE_REFRESH_TOKEN", new_refresh)
    set_key(str(ENV_PATH), "FREEE_TOKEN_EXPIRES_AT", str(expires_at))
    os.environ["FREEE_ACCESS_TOKEN"] = new_access
    os.environ["FREEE_REFRESH_TOKEN"] = new_refresh
    os.environ["FREEE_TOKEN_EXPIRES_AT"] = str(expires_at)
    return new_access


def _access_token() -> str:
    """有効なアクセストークンを返す（期限切れなら自動更新）。"""
    expires_at = int(os.getenv("FREEE_TOKEN_EXPIRES_AT", "0"))
    if time.time() >= expires_at:
        return _refresh_token()
    return os.getenv("FREEE_ACCESS_TOKEN", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }


# ─── API ヘルパー ────────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None) -> Any:
    res = httpx.get(f"{BASE_URL}{path}", headers=_headers(), params=params or {}, timeout=10)
    res.raise_for_status()
    return res.json()


def _post(path: str, body: dict) -> Any:
    res = httpx.post(f"{BASE_URL}{path}", headers=_headers(), json=body, timeout=10)
    res.raise_for_status()
    return res.json()


# ─── 勘定科目キャッシュ ─────────────────────────────────────────────────────

_account_item_cache: dict[str, int] | None = None


def _account_items() -> dict[str, int]:
    """勘定科目名 → ID のマップを返す（キャッシュあり）。"""
    global _account_item_cache
    if _account_item_cache is not None:
        return _account_item_cache
    data = _get("/account_items", {"company_id": COMPANY_ID})
    _account_item_cache = {item["name"]: item["id"] for item in data.get("account_items", [])}
    return _account_item_cache


def _account_item_id(name: str) -> int | None:
    return _account_items().get(name)


# ─── 過去仕訳から店名→勘定科目を学習 ────────────────────────────────────────

def learn_from_history(limit: int = 100) -> dict[str, str]:
    """
    過去の仕訳データを取得して「摘要 → 勘定科目名」の辞書を返す。
    最も多く使われた科目を採用する。
    """
    from collections import Counter, defaultdict

    import datetime
    today = datetime.date.today()
    one_year_ago = today.replace(year=today.year - 1)
    data = _get("/deals", {
        "company_id": COMPANY_ID,
        "limit": limit,
        "offset": 0,
        "start_issue_date": one_year_ago.strftime("%Y-%m-%d"),
        "end_issue_date": today.strftime("%Y-%m-%d"),
    })
    deals = data.get("deals", [])

    mapping: dict[str, Counter] = defaultdict(Counter)
    for deal in deals:
        desc: str = (deal.get("description") or "").strip()
        if not desc:
            continue
        for detail in deal.get("details", []):
            acct = detail.get("account_item_name", "")
            if acct:
                mapping[desc][acct] += 1

    return {desc: counter.most_common(1)[0][0] for desc, counter in mapping.items() if counter}


# ─── 未登録口座明細の取得 ─────────────────────────────────────────────────────

def get_unregistered_txns(limit: int = 100) -> list[dict]:
    """status=unregistered の口座明細を返す。"""
    data = _get("/wallet_txns", {
        "company_id": COMPANY_ID,
        "limit": limit,
        "status": "unregistered",
    })
    return data.get("wallet_txns", [])


# ─── 自動仕分けロジック ──────────────────────────────────────────────────────

def auto_categorize(description: str, history: dict[str, str]) -> str | None:
    """
    店名・摘要から勘定科目名を返す。
    None は「対象外（プライベート）」、空文字は「不明」。
    """
    desc_upper = description.upper()

    # ルールベース（優先）
    for keyword, category in CATEGORY_RULES:
        if keyword.upper() in desc_upper:
            return category  # None = プライベート、文字列 = 科目名

    # 過去データから完全一致
    if description in history:
        return history[description]

    # 過去データから部分一致（店名が含まれていればOK）
    for past_desc, category in history.items():
        if len(past_desc) >= 4 and past_desc in description:
            return category

    return ""  # 不明


# ─── 仕訳登録 ────────────────────────────────────────────────────────────────

def register_deal(
    txn: dict,
    account_item_name: str,
) -> dict:
    """
    口座明細 txn を freee に仕訳として登録する。
    account_item_name: 勘定科目名（例: "会議費"）
    """
    acct_id = _account_item_id(account_item_name)
    if acct_id is None:
        raise ValueError(f"勘定科目 '{account_item_name}' が見つかりません。")

    amount = abs(int(txn.get("amount", 0)))
    # 飲食・会議費など一般的な経費は課対仕入10%（code=136）
    # 振込など不明なものは非課仕入（code=37）
    tax_code = 136

    body = {
        "company_id": COMPANY_ID,
        "issue_date": txn.get("date", ""),
        "type": "expense",
        "due_amount": amount,
        "details": [
            {
                "tax_code": tax_code,
                "account_item_id": acct_id,
                "amount": amount,
                "description": txn.get("description", ""),
            }
        ],
        "payments": [
            {
                "date": txn.get("date", ""),
                "from_walletable_type": txn.get("walletable_type", "credit_card"),
                "from_walletable_id": txn.get("walletable_id"),
                "amount": amount,
            }
        ],
    }
    return _post("/deals", body)


# ─── メイン：仕訳サマリー取得 ────────────────────────────────────────────────

def get_categorization_summary() -> dict:
    """
    未登録明細を取得し、自動仕分け結果をまとめて返す。

    戻り値:
    {
        "auto":   [{"txn": ..., "category": "会議費"}, ...],
        "skip":   [{"txn": ..., "reason": "QuickPay（プライベート）"}, ...],
        "review": [{"txn": ..., "suggestion": "消耗品費?"}, ...],  # Amazon等
        "amazon": [{"txn": ..., "amount": 2800, "date": "2026-08-01"}, ...],
    }
    """
    history = learn_from_history()
    txns = get_unregistered_txns()

    result: dict[str, list] = {"auto": [], "skip": [], "review": [], "amazon": []}

    for txn in txns:
        desc: str = txn.get("description", "")
        amount = abs(int(txn.get("amount", 0)))

        # Amazon は別途照合
        if "AMAZON" in desc.upper() or "アマゾン" in desc:
            result["amazon"].append({
                "txn": txn,
                "amount": amount,
                "date": txn.get("date", ""),
                "description": desc,
            })
            continue

        category = auto_categorize(desc, history)

        if category is None:
            result["skip"].append({"txn": txn, "reason": "プライベート（ルール判定）"})
        elif category == "":
            result["review"].append({"txn": txn, "suggestion": "", "description": desc, "amount": amount})
        else:
            result["auto"].append({"txn": txn, "category": category, "description": desc, "amount": amount})

    return result

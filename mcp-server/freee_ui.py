"""
freee 自動で経理 UI 自動登録モジュール

公開APIでは wallet_txn の消込（自動で経理への反映）ができないため、
Playwright を使って freee の UI から直接登録する。

登録フロー:
  1. freee にログイン（セッションをキャッシュして再利用）
  2. 自動で経理ページで各明細を処理
     - 経費 → 勘定科目をセットして「登録」
     - プライベート → 「プライベート」ボタン
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

FREEE_HOME = "https://secure.freee.co.jp"
AUTO_KEIRI_URL = f"{FREEE_HOME}/wallet_txns/stream?registration_status=unreconciled"
SESSION_FILE = Path(__file__).parent / ".freee_session.json"

# ─── セッション管理 ──────────────────────────────────────────────────────────

def _save_session(context) -> None:
    data = {"cookies": context.cookies(), "saved_at": time.time()}
    SESSION_FILE.write_text(json.dumps(data, default=str), encoding="utf-8")


def _load_session(context) -> bool:
    if not SESSION_FILE.exists():
        return False
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        if time.time() - data.get("saved_at", 0) > 86400:
            return False
        context.add_cookies(data.get("cookies", []))
        return True
    except Exception:
        return False


def _login(page, email: str, password: str) -> None:
    page.goto(f"{FREEE_HOME}/users/sign_in")
    page.wait_for_timeout(3000)
    page.fill('input[name="loginId"], input[id="loginIdField"]', email)
    page.fill('input[name="password"], input[id="passwordField"]', password)
    page.click('button[type="submit"]')
    # 2FA 等があれば人間が操作するまで最大90秒待つ
    try:
        page.wait_for_url(f"{FREEE_HOME}/**", timeout=90_000)
    except Exception:
        pass


def _ensure_logged_in(context, page, email: str, password: str) -> None:
    try:
        page.goto(AUTO_KEIRI_URL, wait_until="domcontentloaded", timeout=25_000)
    except Exception:
        pass
    page.wait_for_timeout(5000)
    if "sign_in" in page.url or "sessions" in page.url:
        _login(page, email, password)
        try:
            page.goto(AUTO_KEIRI_URL, wait_until="domcontentloaded", timeout=25_000)
        except Exception:
            pass
        page.wait_for_timeout(5000)
        _save_session(context)
    # Reactのレンダリングを待つ
    try:
        page.wait_for_selector('tr[data-tour-row]', timeout=15_000)
    except Exception:
        pass
    page.wait_for_timeout(2000)


# ─── 行の処理 ────────────────────────────────────────────────────────────────

def _get_visible_txn_ids(page) -> list[str]:
    """ページに表示中の data-tour-row IDs を返す。"""
    return page.evaluate("""() => {
        return Array.from(document.querySelectorAll('tr[data-tour-row]'))
                    .map(r => r.getAttribute('data-tour-row'));
    }""")


def _load_all_items(page, max_clicks: int = 20) -> None:
    """「次の明細を読み込む」を押してすべての明細を読み込む。"""
    for _ in range(max_clicks):
        next_btn = page.locator('button:has-text("次の明細を読み込む")')
        if next_btn.count() == 0:
            break
        try:
            next_btn.first.click()
            page.wait_for_timeout(2000)
        except Exception:
            break


def _get_row_description(page, txn_id: str) -> str:
    """行の取引内容テキストを返す（td[3] = 口座名＋取引内容）。"""
    return page.evaluate(f"""() => {{
        const row = document.querySelector('tr[data-tour-row="{txn_id}"]');
        if (!row) return '';
        const tds = row.querySelectorAll('td');
        return tds[3] ? tds[3].innerText : '';
    }}""")


def _set_account_item(page, row_locator, category: str) -> None:
    """勘定科目を設定する。"""
    acct_input = row_locator.locator('input[name="account_item"]')
    if acct_input.count() == 0:
        return
    current = acct_input.input_value()
    if current == category:
        return
    acct_input.fill("")
    page.wait_for_timeout(200)
    acct_input.fill(category)
    page.wait_for_timeout(500)
    # ドロップダウン候補から選択
    option = page.locator(f'li:has-text("{category}"), [role="option"]:has-text("{category}")')
    if option.count() > 0:
        option.first.click()
        page.wait_for_timeout(300)


def _click_register(page, row_locator, txn_id: str) -> bool:
    """「登録」ボタンをクリックして登録する。成功すれば True。"""
    btn = row_locator.locator('.btn-registration button:not([disabled])')
    if btn.count() == 0:
        return False
    btn.first.click()
    page.wait_for_timeout(1500)
    # 登録後に行が消えたか確認
    remaining = page.locator(f'tr[data-tour-row="{txn_id}"]')
    return remaining.count() == 0


def _click_private(page, row_locator, txn_id: str) -> bool:
    """「プライベート」ボタンをクリック。成功すれば True。"""
    # ドロップダウン矢印ボタンをクリック
    dropdown_btn = row_locator.locator(
        'button[aria-label*="プライベート"], '
        'button[aria-label*="ignore"], '
        'button[aria-label*="無視"]'
    )
    if dropdown_btn.count() > 0:
        dropdown_btn.first.click()
        page.wait_for_timeout(400)
        priv = page.locator('button:has-text("プライベート"), li:has-text("プライベート")')
        if priv.count() > 0:
            priv.first.click()
            page.wait_for_timeout(1500)
            remaining = page.locator(f'tr[data-tour-row="{txn_id}"]')
            return remaining.count() == 0
    # 直接「プライベート」ボタンがある場合
    priv_btn = row_locator.locator('button:has-text("プライベート")')
    if priv_btn.count() > 0:
        priv_btn.first.click()
        page.wait_for_timeout(1500)
        remaining = page.locator(f'tr[data-tour-row="{txn_id}"]')
        return remaining.count() == 0
    return False


# ─── メイン登録関数 ──────────────────────────────────────────────────────────

def register_txns(
    registrations: list[dict],
    skips: list[dict],
    headless: bool = False,
) -> dict:
    """
    自動で経理の明細を Playwright 経由で登録・除外する。

    registrations: 登録する明細 [{"txn": txn_dict, "category": "会議費"}]
    skips:         対象外にする明細 [{"txn": txn_dict, "reason": "プライベート"}]
    """
    from playwright.sync_api import sync_playwright

    email = os.getenv("FREEE_EMAIL", "")
    password = os.getenv("FREEE_PASSWORD", "")
    if not email or not password:
        return {"error": "FREEE_EMAIL と FREEE_PASSWORD を .env に設定してください。"}

    # txn_id → {action, category} のマップ
    todo: dict[str, dict] = {}
    for item in registrations:
        tid = str(item["txn"]["id"])
        todo[tid] = {"action": "register", "category": item.get("category", ""), "txn": item["txn"]}
    for item in skips:
        tid = str(item["txn"]["id"])
        todo[tid] = {"action": "private", "txn": item["txn"]}

    results: dict[str, list] = {"registered": [], "skipped": [], "failed": [], "not_found": []}

    if not todo:
        return results

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        _load_session(context)
        page = context.new_page()

        _ensure_logged_in(context, page, email, password)

        # すべての明細を読み込む
        _load_all_items(page)

        visible_ids = set(_get_visible_txn_ids(page))
        print(f"[freee_ui] ページ上の明細: {len(visible_ids)}件")

        for txn_id, info in todo.items():
            if txn_id not in visible_ids:
                results["not_found"].append(txn_id)
                continue

            row = page.locator(f'tr[data-tour-row="{txn_id}"]')

            if info["action"] == "register":
                category = info["category"]
                if category:
                    _set_account_item(page, row, category)
                ok = _click_register(page, row, txn_id)
                if ok:
                    results["registered"].append(txn_id)
                else:
                    results["failed"].append({"txn_id": txn_id, "error": "登録ボタンが押せなかった"})
            else:  # private
                ok = _click_private(page, row, txn_id)
                if ok:
                    results["skipped"].append(txn_id)
                else:
                    results["failed"].append({"txn_id": txn_id, "error": "プライベートボタンが押せなかった"})

        _save_session(context)
        browser.close()

    return results


def register_by_rules(
    category_rules: list[tuple[str, str | None]],
    headless: bool = False,
) -> dict:
    """
    ページ上の全明細に対してルールを適用して一括登録する。
    ページに表示されている全行を走査し、説明文にルールキーワードが含まれれば処理する。

    category_rules: [(キーワード, 勘定科目名 or None), ...]
        勘定科目名がNoneの場合はプライベートとして処理。

    例:
        [("コメダ", "会議費"), ("スタバ", "会議費"), ("QUICK PAY", None)]
    """
    from playwright.sync_api import sync_playwright

    email = os.getenv("FREEE_EMAIL", "")
    password = os.getenv("FREEE_PASSWORD", "")
    if not email or not password:
        return {"error": "FREEE_EMAIL と FREEE_PASSWORD を .env に設定してください。"}

    results: dict[str, list] = {"registered": [], "skipped": [], "failed": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        _load_session(context)
        page = context.new_page()

        _ensure_logged_in(context, page, email, password)

        # すべての明細を読み込む
        _load_all_items(page)

        visible_ids = _get_visible_txn_ids(page)
        print(f"[freee_ui] ページ上の明細: {len(visible_ids)}件")

        for txn_id in visible_ids:
            desc = _get_row_description(page, txn_id)
            desc_upper = desc.upper()

            matched_category = None
            matched = False
            for keyword, category in category_rules:
                if keyword.upper() in desc_upper:
                    matched = True
                    matched_category = category  # None = private
                    break

            if not matched:
                continue

            row = page.locator(f'tr[data-tour-row="{txn_id}"]')
            if row.count() == 0:
                continue

            try:
                if matched_category is None:
                    # プライベート
                    ok = _click_private(page, row, txn_id)
                    if ok:
                        results["skipped"].append({"txn_id": txn_id, "desc": desc[:30]})
                    else:
                        results["failed"].append({"txn_id": txn_id, "error": "プライベート失敗", "desc": desc[:30]})
                else:
                    # 経費登録
                    _set_account_item(page, row, matched_category)
                    ok = _click_register(page, row, txn_id)
                    if ok:
                        results["registered"].append({"txn_id": txn_id, "category": matched_category, "desc": desc[:30]})
                    else:
                        results["failed"].append({"txn_id": txn_id, "error": "登録失敗", "desc": desc[:30]})
            except Exception as e:
                results["failed"].append({"txn_id": txn_id, "error": str(e), "desc": desc[:30]})

        _save_session(context)
        browser.close()

    return results

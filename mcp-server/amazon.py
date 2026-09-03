"""Amazon 注文履歴取得モジュール（Playwright使用）"""

from __future__ import annotations

import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

AMAZON_EMAIL = os.getenv("AMAZON_EMAIL", "")
AMAZON_PASSWORD = os.getenv("AMAZON_PASSWORD", "")


def _parse_amount(text: str) -> int:
    """「￥1,234」→ 1234"""
    nums = re.sub(r"[^\d]", "", text)
    return int(nums) if nums else 0


def _parse_date(text: str) -> str:
    """「2026年8月28日」→「2026-08-28」"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def fetch_orders(months: int = 3) -> list[dict]:
    """
    Amazon の注文履歴を取得して返す。

    戻り値:
    [
      {
        "order_id": "503-XXXXXXX",
        "date": "2026-08-28",
        "total": 897,
        "items": ["商品名1", "商品名2"],
      },
      ...
    ]
    """
    from playwright.sync_api import sync_playwright

    orders: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        # ログイン
        page.goto("https://www.amazon.co.jp/ap/signin?openid.return_to=https://www.amazon.co.jp/gp/yourAccount/order-history")
        page.wait_for_load_state("domcontentloaded")

        # メールアドレス入力
        if page.locator("#ap_email").is_visible():
            page.fill("#ap_email", AMAZON_EMAIL)
            page.click("#continue")
            page.wait_for_load_state("domcontentloaded")

        # パスワード入力
        if page.locator("#ap_password").is_visible():
            page.fill("#ap_password", AMAZON_PASSWORD)
            page.click("#signInSubmit")
            page.wait_for_load_state("domcontentloaded")

        # OTP などがあれば待機（最大30秒）
        try:
            page.wait_for_url("**/order-history**", timeout=30000)
        except Exception:
            pass

        # 注文履歴ページへ
        # 期間フィルタ（3ヶ月 or 過去3ヶ月）
        page.goto("https://www.amazon.co.jp/gp/css/order-history?orderFilter=months-3&search=&startIndex=0")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 全ページを取得
        while True:
            order_cards = page.locator(".order").all()
            for card in order_cards:
                try:
                    # 注文日
                    date_text = card.locator(".order-header .a-col-left .a-row:first-child .value").first.inner_text()
                    date = _parse_date(date_text)

                    # 合計金額
                    total_text = card.locator(".order-header .a-col-right .a-row:first-child .value, .grand-total-price").first.inner_text()
                    total = _parse_amount(total_text)

                    # 注文ID
                    order_id_text = card.locator(".order-header .a-col-right .a-row:last-child .value, #orderDetails .order-date-invoice-item").all_inner_texts()
                    order_id = ""
                    for t in order_id_text:
                        if re.search(r"\d{3}-\d{7}-\d{7}", t):
                            order_id = re.search(r"\d{3}-\d{7}-\d{7}", t).group()
                            break

                    # 商品名
                    items = [el.inner_text().strip() for el in card.locator(".yohtmlc-product-title").all()]
                    items = [i for i in items if i][:3]  # 最大3件

                    if date and total:
                        orders.append({
                            "order_id": order_id,
                            "date": date,
                            "total": total,
                            "items": items,
                        })
                except Exception:
                    continue

            # 次のページ
            next_btn = page.locator(".a-last a")
            if next_btn.count() > 0 and next_btn.is_visible():
                next_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(1500)
            else:
                break

        browser.close()

    return orders


def match_transactions(freee_txns: list[dict], orders: list[dict]) -> list[dict]:
    """
    freee の Amazon 明細と注文履歴を日付・金額で照合する。

    戻り値:
    [
      {
        "txn": freee取引,
        "matched": {"order_id": ..., "date": ..., "total": ..., "items": [...]},
        "confidence": "high" | "low",
      },
      ...
    ]
    """
    results = []
    for txn in freee_txns:
        txn_date = txn.get("date", "")
        txn_amount = abs(int(txn.get("amount", 0)))

        # 完全一致（日付 + 金額）
        exact = next(
            (o for o in orders if o["date"] == txn_date and o["total"] == txn_amount),
            None
        )
        if exact:
            results.append({"txn": txn, "matched": exact, "confidence": "high"})
            continue

        # 金額一致（日付が1〜2日ずれ）
        close = next(
            (o for o in orders
             if abs(o["total"] - txn_amount) <= 10
             and abs((datetime.fromisoformat(o["date"]) - datetime.fromisoformat(txn_date)).days) <= 3
             if o["date"] and txn_date),
            None
        )
        if close:
            results.append({"txn": txn, "matched": close, "confidence": "low"})
        else:
            results.append({"txn": txn, "matched": None, "confidence": "none"})

    return results

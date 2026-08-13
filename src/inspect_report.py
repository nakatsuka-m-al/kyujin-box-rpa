"""
実績レポート連携の下調べ用。読み取り専用で、どこにも書き込まない。

確認すること:
  1. 求人ボックスのアカウント一覧ページから、どんな表が取れるか
  2. 書き込み先スプレッドシートの実際のヘッダと既存行
"""

import json
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.sync_api import sync_playwright

import scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPORT_SHEET_ID = os.environ["REPORT_SHEET_ID"]
REPORT_SHEET_TAB = os.environ["REPORT_SHEET_TAB"]


def inspect_sheet() -> None:
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    logger.info(f"サービスアカウント: {info.get('client_email')}")
    logger.info("↑ このアドレスに編集権限が必要です")
    logger.info(f"対象スプレッドシートID: {REPORT_SHEET_ID}")
    logger.info(f"対象タブ: {REPORT_SHEET_TAB!r}")

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    try:
        meta = svc.spreadsheets().get(spreadsheetId=REPORT_SHEET_ID).execute()
    except Exception as e:
        logger.error("スプレッドシートを開けませんでした。原因は次のどちらかです:")
        logger.error("  1. IDが違う（URLの d/ と /edit の間の文字列）")
        logger.error("  2. サービスアカウントに共有されていない")
        logger.error(f"詳細: {e}")
        return
    logger.info(f"スプレッドシート名: {meta['properties']['title']}")
    logger.info(f"タブ一覧: {[s['properties']['title'] for s in meta['sheets']]}")

    rows = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=REPORT_SHEET_ID, range=f"{REPORT_SHEET_TAB}!A1:AZ20")
        .execute()
    ).get("values", [])

    if not rows:
        logger.warning("タブが空です")
        return

    logger.info("--- ヘッダ行（列記号つき）---")
    for i, name in enumerate(rows[0]):
        col = chr(ord("A") + i) if i < 26 else "A" + chr(ord("A") + i - 26)
        logger.info(f"  {col}: {name!r}")

    logger.info(f"--- 既存データ行: {len(rows) - 1} 行 ---")
    for r_i, row in enumerate(rows[1:6], start=2):
        vals = {}
        for i, v in enumerate(row):
            if v != "":
                col = chr(ord("A") + i) if i < 26 else "A" + chr(ord("A") + i - 26)
                vals[col] = v
        logger.info(f"  {r_i}行目: {vals}")


def inspect_page() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        try:
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            scraper.login(page)

            page.goto(scraper.ACCOUNTS_URL)
            page.wait_for_load_state("networkidle")
            page.get_by_role("link", name="直接投稿").click()
            page.wait_for_load_state("networkidle")

            logger.info(f"URL: {page.url}")

            # レポート対象期間がどこに出ているか
            logger.info("--- select 要素 ---")
            for sel in page.locator("select").all():
                name = sel.get_attribute("name") or sel.get_attribute("id") or "(名前なし)"
                try:
                    val = sel.input_value()
                except Exception:
                    val = "?"
                logger.info(f"  name={name!r}  選択値={val!r}")

            logger.info("--- テーブル構造 ---")
            tables = page.locator("table").all()
            logger.info(f"table要素: {len(tables)} 個")

            for t_i, table in enumerate(tables):
                headers = [h.inner_text().strip().replace("\n", "/")
                           for h in table.locator("th").all()]
                rows = table.locator("tbody tr").all()
                logger.info(f"[table {t_i}] th={len(headers)} 個 / tbody行={len(rows)} 行")
                if headers:
                    logger.info(f"  ヘッダ: {headers}")
                for r_i, row in enumerate(rows[:3]):
                    cells = [c.inner_text().strip().replace("\n", "/")
                             for c in row.locator("td").all()]
                    logger.info(f"  {r_i}行目({len(cells)}セル): {cells}")
        finally:
            browser.close()


if __name__ == "__main__":
    logger.info("========== スプレッドシート ==========")
    inspect_sheet()
    logger.info("")
    logger.info("========== 求人ボックスの画面 ==========")
    inspect_page()

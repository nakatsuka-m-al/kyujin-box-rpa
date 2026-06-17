"""
求人部ATS 応募者データ自動取得スクリプト
- Playwright でログイン → 当月分CSV取得 → Google Sheets に差分書き込み
- 差分管理で重複書き込みを防ぐ
"""

import csv
import io
import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from exporters import RawSheetsExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── 設定 ────────────────────────────────────────────────────────────────────

LOGIN_URL  = "https://kyujinbu.com/cms/login/"
BASE_URL   = "https://kyujinbu.com/cms/"

ATS_EMAIL    = os.environ["ATS_EMAIL"]
ATS_PASSWORD = os.environ["ATS_PASSWORD"]

SEEN_IDS_PATH = Path(os.environ.get("SEEN_IDS_PATH", "seen_ats_applicant_ids.json"))

# 差分管理キー列（三つ組で一意性を保証）
KEY_COLUMNS = ("お仕事ID", "お名前", "応募受付日時")


# ─── 差分管理 ─────────────────────────────────────────────────────────────────

def load_seen_ids() -> set[str]:
    if SEEN_IDS_PATH.exists():
        return set(json.loads(SEEN_IDS_PATH.read_text()))
    return set()


def save_seen_ids(ids: set[str]) -> None:
    SEEN_IDS_PATH.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2))


# ─── CSV パース ───────────────────────────────────────────────────────────────

def parse_csv(raw_bytes: bytes) -> list[dict]:
    for encoding in ("utf-8-sig", "shift_jis", "utf-8"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV のエンコーディングを判別できませんでした")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if rows:
        logger.info(f"CSV列名: {list(rows[0].keys())}")
    return rows


# ─── Indeed 備考パース ────────────────────────────────────────────────────────

def parse_indeed_biko(text: str) -> dict:
    """備考の【】ブロックをパースしてdictに変換"""
    result = {}
    pattern = re.compile(r'【([^】]+)】:?\s*(.*?)(?=【|$)', re.DOTALL)
    for match in pattern.finditer(text):
        key = f"[Indeed]{match.group(1).strip()}"
        value = match.group(2).strip()
        result[key] = value
    return result


def enrich_indeed_rows(rows: list[dict]) -> list[dict]:
    """Indeed応募行の備考をパースして列を追加、全行を同じキー構成に正規化"""
    # Indeedの行を拡張
    for row in rows:
        if "Indeed" in row.get("応募経路", ""):
            parsed = parse_indeed_biko(row.get("備考", ""))
            row.update(parsed)

    # 全行のキーを統一（不足分は空文字）
    all_keys = list(dict.fromkeys(k for row in rows for k in row.keys()))
    return [{k: row.get(k, "") for k in all_keys} for row in rows]


# ─── Playwright 操作 ──────────────────────────────────────────────────────────

def login(page) -> None:
    logger.info("ログイン中...")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    page.locator("input[type='text'], input[name*='user'], input[name*='email'], input[name*='id']").first.fill(ATS_EMAIL)
    page.locator("input[type='password']").first.fill(ATS_PASSWORD)
    page.get_by_role("button", name="ログイン").click()
    page.wait_for_load_state("networkidle")

    if "login" in page.url:
        raise RuntimeError("ログインに失敗しました。ID/PASSを確認してください。")
    logger.info(f"ログイン完了 → {page.url}")


ATS_LIST_URL = "https://saiyo.kyujinbu.com/"


ATS_LIST_URL = "https://saiyo.kyujinbu.com/"


ATS_LIST_URL = "https://saiyo.kyujinbu.com/"


def go_to_applicant_list(page, context):
    """applicantLogin() JS経由で採用管理課（saiyo.kyujinbu.com）へ遷移後、日付URLで絞込"""
    from datetime import timedelta

    page.locator("a[href='javascript:applicantLogin()']").click()
    time.sleep(3)

    # 新タブ・同ウィンドウどちらでも対応
    all_pages = context.pages
    app_page = next((p for p in all_pages if "saiyo.kyujinbu.com" in p.url), None)
    if app_page is None:
        page.wait_for_load_state("networkidle")
        app_page = next((p for p in context.pages if "saiyo.kyujinbu.com" in p.url), page)

    app_page.wait_for_load_state("networkidle")

    today = date.today()
    first_day = date(today.year, 4, 1)  # 一時的に4月1日から全件取得

    url = (
        f"{ATS_LIST_URL}"
        f"?date[from_year]={first_day.year}"
        f"&date[from_month]={first_day.month:02d}"
        f"&date[from_day]={first_day.day:02d}"
        f"&date[to_year]={today.year}"
        f"&date[to_month]={today.month:02d}"
        f"&date[to_day]={today.day:02d}"
        f"&list_max=1000"
    )
    app_page.goto(url)
    app_page.wait_for_load_state("networkidle")
    logger.info(f"応募者一覧（{first_day}〜{today}） → {app_page.url}")
    return app_page


def download_csv(page) -> bytes:
    """CSVダウンロード"""
    dl_link = page.locator("a:has-text('CSV'), a:has-text('ダウンロード')")
    if dl_link.count() == 0:
        raise RuntimeError(
            "CSVダウンロードボタンが見つかりません。現在のURL: " + page.url
        )

    logger.info("CSV ダウンロード中...")
    with page.expect_download() as dl:
        dl_link.first.click()
    return Path(dl.value.path()).read_bytes()


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def main() -> None:
    seen_ids = load_seen_ids()
    new_rows: list[dict] = []

    sheets = RawSheetsExporter()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )

        try:
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            login(page)
            app_page = go_to_applicant_list(page, context)
            raw = download_csv(app_page)

        finally:
            browser.close()

    rows = parse_csv(raw)
    rows = enrich_indeed_rows(rows)
    logger.info(f"CSV取得: {len(rows)} 件")

    for row in rows:
        # お仕事ID + お名前 + 応募受付日時 の三つ組で一意管理
        # 同一人物が別求人・別日に応募した場合も別エントリとして保持
        row_id = "__".join(row.get(col, "") for col in KEY_COLUMNS)
        if not row_id or row_id in seen_ids:
            continue
        new_rows.append(row)
        seen_ids.add(row_id)

    logger.info(f"新規: {len(new_rows)} 件")

    if not new_rows:
        logger.info("新規応募者なし。処理終了。")
        return

    sheets.append(new_rows)
    save_seen_ids(seen_ids)
    logger.info("完了")


if __name__ == "__main__":
    main()

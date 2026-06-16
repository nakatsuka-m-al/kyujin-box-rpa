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

SEEN_IDS_PATH = Path("seen_ats_applicant_ids.json")

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


def go_to_applicant_list(page, context):
    """applicantLogin() JS経由で採用管理課（saiyo.kyujinbu.com）へ遷移"""
    page.locator("a[href='javascript:applicantLogin()']").click()
    page.wait_for_load_state("networkidle")
    logger.info(f"応募者一覧 → {page.url}")
    return page


def set_date_range(page) -> None:
    """応募受付期間を当月1日〜本日に設定して絞込"""
    today = date.today()
    first_day = date(today.year, 4, 1)  # 一時的に4月1日から取得

    # 年の値（例: "2026"）を持つselectを全て抽出して日付セレクトを特定
    all_selects = page.locator("select").all()
    date_selects = []
    for sel in all_selects:
        options = sel.locator("option").all()
        values = [o.get_attribute("value") or o.inner_text().strip() for o in options]
        if str(today.year) in values or str(today.year - 1) in values:
            date_selects.append(sel)

    def select_val(sel, val: int) -> None:
        # ゼロ埋めあり・なし両方試す
        for v in (str(val), f"{val:02d}"):
            try:
                sel.select_option(v)
                return
            except Exception:
                pass
        logger.warning(f"セレクト値 {val} の設定に失敗しました")

    if len(date_selects) < 6:
        logger.warning(
            f"日付セレクトが6個見つかりません（{len(date_selects)}個）。"
            "日付設定をスキップして全件取得します。"
        )
    else:
        # [開始年, 開始月, 開始日, 終了年, 終了月, 終了日] の順を想定
        select_val(date_selects[0], first_day.year)
        select_val(date_selects[1], first_day.month)
        select_val(date_selects[2], first_day.day)
        select_val(date_selects[3], today.year)
        select_val(date_selects[4], today.month)
        select_val(date_selects[5], today.day)
        logger.info(f"期間設定: {first_day} 〜 {today}")

    # 読込ボタン
    page.get_by_role("button", name="読込").click()
    page.wait_for_load_state("networkidle")


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
            set_date_range(app_page)
            raw = download_csv(app_page)

        finally:
            browser.close()

    rows = parse_csv(raw)
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

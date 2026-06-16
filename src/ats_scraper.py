"""
求人部ATS 応募者データ自動取得スクリプト
- Playwright でログイン → CSV ダウンロード → Google Sheets に差分書き込み
- 0時・12時・17時（JST）に GitHub Actions で実行
"""

import csv
import io
import json
import logging
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from exporters import RawSheetsExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── 設定 ────────────────────────────────────────────────────────────────────

LOGIN_URL = "https://kyujinbu.com/cms/login/"

ATS_EMAIL    = os.environ["ATS_EMAIL"]
ATS_PASSWORD = os.environ["ATS_PASSWORD"]

SEEN_IDS_PATH = Path("seen_ats_applicant_ids.json")


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
    return [dict(row) for row in reader]


# ─── Playwright 操作 ──────────────────────────────────────────────────────────

def login(page) -> None:
    logger.info("ログイン中...")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    # TODO: 実際のフォームのセレクタに合わせて修正
    page.locator("input[name='username'], input[type='text']").first.fill(ATS_EMAIL)
    page.locator("input[name='password'], input[type='password']").first.fill(ATS_PASSWORD)
    page.get_by_role("button", name="ログイン").click()
    page.wait_for_load_state("networkidle")

    if "login" in page.url:
        raise RuntimeError("ログインに失敗しました。ID/PASSを確認してください。")
    logger.info(f"ログイン完了 → {page.url}")


def download_csv(page) -> bytes:
    """応募者一覧ページからCSVをダウンロードする"""

    # TODO: 実際のURLとボタンセレクタに合わせて修正
    # 応募者一覧ページに移動
    page.get_by_role("link", name="応募者").click()
    page.wait_for_load_state("networkidle")

    # CSVダウンロードボタンを探す
    dl_candidates = [
        "CSVダウンロード",
        "CSV出力",
        "エクスポート",
        "ダウンロード",
    ]
    dl_link = None
    for name in dl_candidates:
        loc = page.get_by_role("link", name=name)
        if loc.count() > 0:
            dl_link = loc.first
            break
        loc = page.get_by_role("button", name=name)
        if loc.count() > 0:
            dl_link = loc.first
            break

    if dl_link is None:
        raise RuntimeError(
            "CSVダウンロードボタンが見つかりません。"
            "セレクタを確認してください。現在のURL: " + page.url
        )

    logger.info("CSV ダウンロード中...")
    with page.expect_download() as dl:
        dl_link.click()
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

            raw = download_csv(page)
            rows = parse_csv(raw)

            for row in rows:
                # 1列目をIDとして差分管理（TODO: 実際のID列名に合わせて修正）
                row_id = list(row.values())[0] if row else ""
                if not row_id or row_id in seen_ids:
                    continue
                new_rows.append(row)
                seen_ids.add(row_id)

            logger.info(f"取得: {len(rows)} 件 / 新規: {len(new_rows)} 件")

        finally:
            browser.close()

    if not new_rows:
        logger.info("新規応募者なし。処理終了。")
        return

    logger.info(f"新規 {len(new_rows)} 件を書き込みます")
    sheets.append(new_rows)
    save_seen_ids(seen_ids)
    logger.info("完了")


if __name__ == "__main__":
    main()

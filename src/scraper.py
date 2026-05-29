"""
求人ボックス 応募者データ自動取得スクリプト
- Playwright でヘッドレス Chromium を使用
- マスターアカウントでログイン後、サブアカウントごとに CSV ダウンロード
- 差分管理は seen_applicant_ids.json で実施
"""

import csv
import io
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from exporters import SheetsExporter, RPMExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── 設定 ────────────────────────────────────────────────────────────────────

LOGIN_URL = "https://employer.kyujinbox.com/login"
APPLICANTS_URL = "https://employer.kyujinbox.com/applicants"

MASTER_EMAIL = os.environ["KYUJIN_MASTER_EMAIL"]
MASTER_PASSWORD = os.environ["KYUJIN_MASTER_PASSWORD"]

# 例: [{"id": "sub001", "name": "店舗A"}, {"id": "sub002", "name": "店舗B"}]
SUB_ACCOUNTS: list[dict] = json.loads(os.environ.get("KYUJIN_SUB_ACCOUNTS", "[]"))

SEEN_IDS_PATH = Path("seen_applicant_ids.json")

# ─── CSV カラムマッピング ──────────────────────────────────────────────────────
# 左辺: 求人ボックスCSVの実際のヘッダ名（要確認・更新）
# 右辺: 社内統一フィールド名
COLUMN_MAP: dict[str, str] = {
    # TODO: 実際のCSVをダウンロードしてヘッダ名を確認してここを埋める
    "応募ID":         "applicant_id",
    "応募日時":       "applied_at",
    "氏名":           "name",
    "氏名（カナ）":   "name_kana",
    "メールアドレス": "email",
    "電話番号":       "phone",
    "住所":           "address",
    "生年月日":       "birthdate",
    "年齢":           "age",
    "性別":           "gender",
    "最終学歴":       "education",
    "職歴":           "work_history",
    "希望職種":       "desired_job",
    "希望勤務地":     "desired_location",
    "希望給与":       "desired_salary",
    "メッセージ":     "message",
    "求人タイトル":   "job_title",
    "求人ID":         "job_id",
    "ステータス":     "status",
}


# ─── 差分管理 ─────────────────────────────────────────────────────────────────

def load_seen_ids() -> set[str]:
    if SEEN_IDS_PATH.exists():
        return set(json.loads(SEEN_IDS_PATH.read_text()))
    return set()


def save_seen_ids(ids: set[str]) -> None:
    SEEN_IDS_PATH.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2))


# ─── CSV パース ───────────────────────────────────────────────────────────────

def parse_csv(raw_bytes: bytes) -> list[dict]:
    """CSVバイト列を読み込み、COLUMN_MAP でフィールド名を変換して返す"""
    # BOM 付き UTF-8 / Shift-JIS どちらにも対応
    for encoding in ("utf-8-sig", "shift_jis", "utf-8"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV のエンコーディングを判別できませんでした")

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        mapped = {}
        for csv_key, internal_key in COLUMN_MAP.items():
            mapped[internal_key] = row.get(csv_key, "").strip()
        # マッピング外の列も保持（デバッグ用）
        mapped["_raw"] = dict(row)
        rows.append(mapped)
    return rows


# ─── Playwright 操作 ──────────────────────────────────────────────────────────

def login(page) -> None:
    logger.info("ログイン中...")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    # TODO: 実際のセレクタに更新（playwright codegen で確認推奨）
    page.fill('input[type="email"], input[name="email"], #email', MASTER_EMAIL)
    page.fill('input[type="password"], input[name="password"], #password', MASTER_PASSWORD)
    page.click('button[type="submit"], input[type="submit"], .login-btn')

    page.wait_for_load_state("networkidle")
    logger.info("ログイン完了")


def switch_to_subaccount(page, sub: dict) -> None:
    """サブアカウントに切り替える"""
    sub_id = sub["id"]
    sub_name = sub.get("name", sub_id)
    logger.info(f"サブアカウント切替: {sub_name} (id={sub_id})")

    # TODO: 実際のアカウント切替UIのセレクタを確認して更新
    # パターンA: ドロップダウンメニュー
    try:
        page.click(
            '[data-testid="account-switcher"], '
            '.account-switcher, '
            '#account-menu, '
            '.js-account-switch'
        )
        time.sleep(0.5)
        page.click(
            f'[data-account-id="{sub_id}"], '
            f'[href*="account_id={sub_id}"], '
            f'[href*="/accounts/{sub_id}"]'
        )
    except PlaywrightTimeoutError:
        # パターンB: URLパラメータで直接切替
        page.goto(f"{APPLICANTS_URL}?account_id={sub_id}")

    page.wait_for_load_state("networkidle")
    time.sleep(1)


def download_csv(page) -> bytes:
    """CSVをダウンロードして bytes で返す"""
    logger.info("CSV ダウンロード中...")
    page.goto(APPLICANTS_URL)
    page.wait_for_load_state("networkidle")

    # TODO: 実際のCSVダウンロードボタンのセレクタを確認して更新
    with page.expect_download() as download_info:
        page.click(
            'a[href*="export"], '
            'a[href*="csv"], '
            'button:has-text("CSV"), '
            'a:has-text("CSVダウンロード"), '
            'a:has-text("CSV出力"), '
            'a:has-text("エクスポート")'
        )
    download = download_info.value
    path = download.path()
    return Path(path).read_bytes()


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def main() -> None:
    seen_ids = load_seen_ids()
    new_applicants: list[dict] = []

    sheets = SheetsExporter()
    rpm = RPMExporter()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = context.new_page()

        try:
            login(page)

            for sub in SUB_ACCOUNTS:
                try:
                    switch_to_subaccount(page, sub)
                    raw = download_csv(page)
                    applicants = parse_csv(raw)

                    for a in applicants:
                        aid = a.get("applicant_id", "")
                        if not aid:
                            logger.warning(f"applicant_id が空の行をスキップ: {a.get('_raw', {})}")
                            continue
                        if aid in seen_ids:
                            continue
                        a["_subaccount_id"] = sub["id"]
                        a["_subaccount_name"] = sub.get("name", sub["id"])
                        new_applicants.append(a)
                        seen_ids.add(aid)

                    logger.info(
                        f"[{sub.get('name', sub['id'])}] "
                        f"取得: {len(applicants)} 件 / 新規: {len(new_applicants)} 件"
                    )
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"サブアカウント {sub} の処理中にエラー: {e}", exc_info=True)
                    continue

        finally:
            browser.close()

    if not new_applicants:
        logger.info("新規応募者なし。処理終了。")
        return

    logger.info(f"新規応募者 {len(new_applicants)} 件を書き込みます")

    sheets.append(new_applicants)
    rpm.post_applicants(new_applicants)

    save_seen_ids(seen_ids)
    logger.info("完了")


if __name__ == "__main__":
    main()

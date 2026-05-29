"""
求人ボックス 応募者データ自動取得スクリプト
- クッキーでセッション復元（CAPTCHA回避）
- マスターアカウントでログイン後、サブアカウントごとに CSV ダウンロード
- 差分管理は seen_applicant_ids.json で実施
"""

import csv
import io
import json
import logging
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from exporters import SheetsExporter, RPMExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── 設定 ────────────────────────────────────────────────────────────────────

BASE_URL = "https://secure.kyujinbox.com"
LOGIN_URL = f"{BASE_URL}/login"

# save_cookies.py で取得して GitHub Secret に登録したセッション情報
# storageState 形式: {"cookies": [...], "origins": [...]}
_cookies_raw = os.environ.get("KYUJIN_COOKIES", "")
KYUJIN_STORAGE_STATE: dict = json.loads(_cookies_raw) if _cookies_raw else {}

# サブアカウントのリスト
# name: 管理画面のアカウント切替メニューに表示される会社名（完全一致）
# 例: [{"name": "株式会社ｃｏｍａｍ"}, {"name": "株式会社〇〇"}]
SUB_ACCOUNTS: list[dict] = json.loads(os.environ.get("KYUJIN_SUB_ACCOUNTS", "[]"))

SEEN_IDS_PATH = Path("seen_applicant_ids.json")

# ─── CSV カラムマッピング ──────────────────────────────────────────────────────
# 左辺: 求人ボックスCSVの実際のヘッダ名（実CSVで確認済みのものに更新すること）
# 右辺: 社内統一フィールド名
COLUMN_MAP: dict[str, str] = {
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
        mapped = {internal_key: row.get(csv_key, "").strip()
                  for csv_key, internal_key in COLUMN_MAP.items()}
        mapped["_raw"] = dict(row)
        rows.append(mapped)
    return rows


# ─── Playwright 操作 ──────────────────────────────────────────────────────────

def check_storage_state() -> None:
    """KYUJIN_COOKIES が設定されているか確認する"""
    if not KYUJIN_STORAGE_STATE:
        raise RuntimeError(
            "KYUJIN_COOKIES が未設定です。\n"
            "ローカルで python3 src/save_cookies.py を実行して\n"
            "GitHub Secret に登録してください。"
        )
    n_cookies = len(KYUJIN_STORAGE_STATE.get("cookies", []))
    n_origins = len(KYUJIN_STORAGE_STATE.get("origins", []))
    logger.info(f"storageState 確認: cookies={n_cookies} 件, origins={n_origins} 件")


def verify_login(page) -> None:
    """セッションが有効か確認する（クッキー期限切れ検知）"""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    logger.info(f"遷移先URL: {page.url}")
    logger.info(f"ページタイトル: {page.title()}")
    if "login" in page.url:
        raise RuntimeError(
            "セッションが切れています。\n"
            "ローカルで python3 src/save_cookies.py を再実行し\n"
            "GitHub Secret「KYUJIN_COOKIES」を更新してください。"
        )
    logger.info("セッション有効確認OK")


def fetch_csv_for_subaccount(page, sub: dict) -> bytes:
    """サブアカウントに切り替えてCSVをダウンロードする"""
    sub_name = sub["name"]
    logger.info(f"サブアカウント切替: {sub_name}")

    # 「直接投稿」メニューを開いてサブアカウントを選択
    page.get_by_role("link", name="直接投稿").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name=sub_name).click()
    page.wait_for_load_state("networkidle")

    # 応募者一覧へ
    page.get_by_role("link", name="応募者一覧").click()
    page.wait_for_load_state("networkidle")

    # CSVダウンロード
    logger.info(f"[{sub_name}] CSV ダウンロード中...")
    with page.expect_download() as download_info:
        page.get_by_role("link", name=" 応募者情報をダウンロード").click()
    download = download_info.value
    return Path(download.path()).read_bytes()


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def main() -> None:
    if not SUB_ACCOUNTS:
        logger.warning("KYUJIN_SUB_ACCOUNTS が空です。処理終了。")
        return

    seen_ids = load_seen_ids()
    new_applicants: list[dict] = []

    check_storage_state()
    sheets = SheetsExporter()
    rpm = RPMExporter()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=KYUJIN_STORAGE_STATE,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )

        try:
            page = context.new_page()
            verify_login(page)

            for sub in SUB_ACCOUNTS:
                try:
                    raw = fetch_csv_for_subaccount(page, sub)
                    applicants = parse_csv(raw)

                    added = 0
                    for a in applicants:
                        aid = a.get("applicant_id", "")
                        if not aid:
                            continue
                        if aid in seen_ids:
                            continue
                        a["_subaccount_name"] = sub["name"]
                        new_applicants.append(a)
                        seen_ids.add(aid)
                        added += 1

                    logger.info(f"[{sub['name']}] 取得: {len(applicants)} 件 / 新規: {added} 件")
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"[{sub.get('name')}] エラー: {e}", exc_info=True)
                    continue

        finally:
            browser.close()

    if not new_applicants:
        logger.info("新規応募者なし。処理終了。")
        return

    logger.info(f"新規応募者 {len(new_applicants)} 件を書き込みます")

    sheets.append(new_applicants)
    # rpm.post_applicants(new_applicants)  # API仕様書受領後に有効化

    save_seen_ids(seen_ids)
    logger.info("完了")


if __name__ == "__main__":
    main()

"""
求人ボックス 応募者データ自動取得スクリプト
- playwright-stealth でボット検知・CAPTCHA を回避
- 毎回ログイン → 即スクレイピング（同一セッション・同一IP）
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

LOGIN_URL = "https://secure.kyujinbox.com/login"
BASE_URL  = "https://secure.kyujinbox.com"

MASTER_EMAIL    = os.environ["KYUJIN_MASTER_EMAIL"]
MASTER_PASSWORD = os.environ["KYUJIN_MASTER_PASSWORD"]

# 例: [{"name": "株式会社ｃｏｍａｍ"}, {"name": "株式会社〇〇"}]
SUB_ACCOUNTS: list[dict] = json.loads(os.environ.get("KYUJIN_SUB_ACCOUNTS", "[]"))

SEEN_IDS_PATH = Path("seen_applicant_ids.json")

# ─── CSV カラムマッピング ──────────────────────────────────────────────────────
COLUMN_MAP: dict[str, str] = {
    "応募No":         "applicant_id",
    "応募日時":       "applied_at",
    "氏名":           "name",
    "性別":           "gender",
    "生年月日":       "birthdate",
    "現在の職業":     "current_job",
    "電話番号":       "phone",
    "メールアドレス": "email",
    "住所":           "address",
    "学校名":         "education",
    "備考・PR":       "message",
    "求人タイトル":   "job_title",
    "求人ID":         "job_id",
    "選考ステータス": "status",
    "選考コメント":   "selection_comment",
    "求人ラベル":     "job_label",
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
        mapped = {v: row.get(k, "").strip() for k, v in COLUMN_MAP.items()}
        # 勤務先_1〜30 を「会社名 / 役職」形式で結合
        history_parts = []
        for i in range(1, 31):
            company = row.get(f"勤務先_{i}", "").strip()
            role    = row.get(f"役職・業務内容など_{i}", "").strip()
            if company:
                history_parts.append(f"{company}{'／' + role if role else ''}")
        mapped["work_history"] = " → ".join(history_parts)
        mapped["_raw"] = dict(row)
        rows.append(mapped)
    return rows


# ─── Playwright 操作 ──────────────────────────────────────────────────────────

def login(page) -> None:
    logger.info("ログイン中...")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    page.locator("#login_email").fill(MASTER_EMAIL)
    page.locator("#login_password").fill(MASTER_PASSWORD)

    # ステルスモードでCAPTCHAが出ない想定だが、出た場合はここでタイムアウト
    page.get_by_role("button", name="ログイン").click()
    page.wait_for_load_state("networkidle")

    if "login" in page.url:
        raise RuntimeError(
            "ログインに失敗しました。"
            "CAPTCHA が表示されているか、ID/PASSが間違っている可能性があります。"
        )
    logger.info(f"ログイン完了 → {page.url}")


ACCOUNTS_URL = "https://saiyo.kyujinbox.com/ptr/l-accounts"


def fetch_csv_for_subaccount(page, sub: dict) -> bytes:
    sub_name = sub["name"]
    logger.info(f"サブアカウント切替: {sub_name}")

    # 毎回アカウント一覧ページに戻ってから切り替える
    page.goto(ACCOUNTS_URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role("link", name="直接投稿").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name=sub_name).click()
    page.wait_for_load_state("networkidle")

    page.get_by_role("link", name="応募者一覧").click()
    page.wait_for_load_state("networkidle")

    logger.info(f"[{sub_name}] CSV ダウンロード中...")
    with page.expect_download() as dl:
        page.get_by_role("link", name=" 応募者情報をダウンロード").click()
    return Path(dl.value.path()).read_bytes()


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def main() -> None:
    if not SUB_ACCOUNTS:
        logger.warning("KYUJIN_SUB_ACCOUNTS が空です。処理終了。")
        return

    seen_ids = load_seen_ids()
    new_applicants: list[dict] = []

    sheets = SheetsExporter()
    rpm = RPMExporter()

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
            # navigator.webdriver を隠してボット検知を回避
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            login(page)

            for sub in SUB_ACCOUNTS:
                try:
                    raw = fetch_csv_for_subaccount(page, sub)
                    applicants = parse_csv(raw)

                    added = 0
                    for a in applicants:
                        aid = a.get("applicant_id", "")
                        if not aid or aid in seen_ids:
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

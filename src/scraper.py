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

# 高速レーンと定期実行でキャッシュを分けるため環境変数で切り替える
SEEN_IDS_PATH = Path(os.environ.get("SEEN_IDS_PATH", "seen_applicant_ids.json"))

# 指定するとそのサブアカウントだけを取得する（メールトリガー用）。
# 値はアカウント一覧のリンク末尾と同じ形式。例: "6617-5385"
TARGET_ACCOUNT_ID = os.environ.get("KYUJIN_TARGET_ACCOUNT_ID", "").strip()

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
        page.screenshot(path="login_failed.png", full_page=True)
        logger.error("ログイン失敗時のスクリーンショットを login_failed.png に保存しました")
        raise RuntimeError(
            "ログインに失敗しました。"
            "CAPTCHA が表示されているか、ID/PASSが間違っている可能性があります。"
        )
    logger.info(f"ログイン完了 → {page.url}")


ACCOUNTS_URL = "https://saiyo.kyujinbox.com/ptr/l-accounts"


EXCLUDE_LINK_TEXTS = {"求人編集", "応募者確認", "直接投稿", "クローリング・フィード"}


def account_id_of(href: str) -> str:
    """/ptr/saiyo_login/6617-5385 → "6617-5385" """
    return href.rstrip("/").rsplit("/", 1)[-1] if href else ""


def fetch_all_subaccounts(page) -> list[dict]:
    """アカウント一覧ページから全サブアカウントの名前とhrefを取得する"""
    page.goto(ACCOUNTS_URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role("link", name="直接投稿").click()
    page.wait_for_load_state("networkidle")

    links = page.locator("table a").all()
    accounts = []
    for link in links:
        text = link.inner_text().strip()
        if not text or text in EXCLUDE_LINK_TEXTS:
            continue
        href = link.get_attribute("href") or ""
        accounts.append({"name": text, "href": href})

    logger.info(f"サブアカウント {len(accounts)} 件を自動検出: {[a['name'] for a in accounts]}")
    return accounts


def fetch_csv_for_subaccount(page, account: dict) -> bytes:
    sub_name = account["name"]
    href = account.get("href", "")
    logger.info(f"サブアカウント切替: {sub_name} ({href})")

    page.goto(ACCOUNTS_URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role("link", name="直接投稿").click()
    page.wait_for_load_state("networkidle")

    # hrefが取れている場合はURLで一意に特定、なければ名前で検索
    if href:
        page.locator(f"a[href='{href}']").click()
    else:
        page.get_by_role("link", name=sub_name, exact=True).click()
    page.wait_for_load_state("networkidle")

    page.get_by_role("link", name="応募者一覧").click()
    page.wait_for_load_state("networkidle")

    dl_link = page.get_by_role("link", name=" 応募者情報をダウンロード")
    if not dl_link.is_visible(timeout=5000):
        logger.info(f"[{sub_name}] 応募者なし（ダウンロードボタン未表示）")
        return b""

    logger.info(f"[{sub_name}] CSV ダウンロード中...")
    with page.expect_download() as dl:
        dl_link.click()
    return Path(dl.value.path()).read_bytes()


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def main() -> None:
    seen_ids = load_seen_ids()
    new_applicants: list[dict] = []

    sheets = SheetsExporter()
    rpm = RPMExporter()

    # シート上の既存IDをキャッシュに統合（キャッシュ消失時の重複防止）
    if sheets._service:
        sheet_ids = sheets.fetch_existing_ids()
        before = len(seen_ids)
        seen_ids |= sheet_ids
        logger.info(f"シートIDをキャッシュに統合: {before} → {len(seen_ids)} 件")

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

            # KYUJIN_SUB_ACCOUNTS が指定されていれば優先、なければ自動取得
            if SUB_ACCOUNTS:
                accounts = [{"name": s["name"], "href": s.get("href", "")} for s in SUB_ACCOUNTS]
            else:
                accounts = fetch_all_subaccounts(page)

            if not accounts:
                logger.warning("サブアカウントが見つかりません。処理終了。")
                return

            # メールトリガー時は対象アカウントだけに絞る
            if TARGET_ACCOUNT_ID:
                accounts = [a for a in accounts
                            if account_id_of(a.get("href", "")) == TARGET_ACCOUNT_ID]
                if not accounts:
                    # 管理外のアカウント宛メールの可能性がある。
                    # 日次スイープが保険になるので失敗扱いにはしない。
                    logger.warning(
                        f"アカウントID '{TARGET_ACCOUNT_ID}' は一覧に見つかりませんでした。"
                        "管理対象外の通知の可能性があります。処理終了。"
                    )
                    return
                logger.info(f"対象を1件に限定: {accounts[0]['name']} ({TARGET_ACCOUNT_ID})")

            for account in accounts:
                sub_name = account["name"]
                try:
                    raw = fetch_csv_for_subaccount(page, account)
                    if not raw:
                        continue
                    applicants = parse_csv(raw)

                    added = 0
                    for a in applicants:
                        aid = a.get("applicant_id", "")
                        if not aid or aid in seen_ids:
                            continue
                        a["_subaccount_name"] = sub_name
                        new_applicants.append(a)
                        seen_ids.add(aid)
                        added += 1

                    logger.info(f"[{sub_name}] 取得: {len(applicants)} 件 / 新規: {added} 件")
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"[{sub_name}] エラー: {e}", exc_info=True)
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

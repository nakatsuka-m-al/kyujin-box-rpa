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
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

import applicant_mail
import notify
import toroo
from exporters import SheetsExporter, RPMExporter, LinkLog

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

# メールトリガー経由か定期実行か。取りこぼしの検知に使う
IMPORT_ROUTE = "メール" if TARGET_ACCOUNT_ID else "定期"

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
    # 応募No → アカウントID。既存行のアカウントIDを埋めるのにも使う。
    account_by_applicant: dict[str, str] = {}

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
                # 32社あるはずのものが0件になるのは、ログイン状態か画面構成が
                # 変わったということ。正常終了にすると誰も気付けないため失敗させる。
                raise RuntimeError(
                    "サブアカウントが1件も検出できませんでした。"
                    f"アカウント一覧の画面構成が変わった可能性があります（URL: {page.url}）"
                )

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
                account_id = account_id_of(account.get("href", ""))
                try:
                    raw = fetch_csv_for_subaccount(page, account)
                    if not raw:
                        continue
                    applicants = parse_csv(raw)

                    added = 0
                    for a in applicants:
                        aid = a.get("applicant_id", "")
                        if not aid:
                            continue
                        # 新規かどうかに関わらず控えておく。
                        # 既にシートにある行のアカウントIDも埋められるようにするため。
                        account_by_applicant[aid] = account_id
                        if aid in seen_ids:
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

    if new_applicants:
        logger.info(f"新規応募者 {len(new_applicants)} 件を書き込みます")
        sheets.append(new_applicants)
        # rpm.post_applicants(new_applicants)  # API仕様書受領後に有効化
    else:
        logger.info("新規応募者なし")

    # 新規行にも既存行にもアカウントIDを入れる
    sheets.fill_account_ids(account_by_applicant)

    if new_applicants:
        deliver(new_applicants, account_by_applicant, sheets)

    save_seen_ids(seen_ids)
    logger.info("完了")


# ─── 応募者ごとの後処理 ───────────────────────────────────────────────────────

def deliver(applicants: list[dict], account_by_applicant: dict, sheets) -> None:
    """
    シートに記録したあと、応募者ごとにメール送信とToroo登録を行う。

    シート書き込みと同じ実行の中で完結させる。別々に走らせると
    求人ボックスへのログインが2回必要になり、片方だけ成功する不整合も起きる。

    記録は専用タブ（連携ログ）に残す。OBSシートには触らない。
    """
    notifier = notify.Notifier(
        client=applicant_mail.CLIENT_NAME, source="求人ボックス 応募者同期"
    )
    log = LinkLog(sheets._service, os.environ.get("GOOGLE_SHEET_ID", ""))
    already_synced = log.fetch_synced_ids() if (log.enabled and toroo.is_enabled()) else set()

    now = time.strftime("%Y/%m/%d %H:%M:%S")
    entries = []

    for applicant in applicants:
        applicant_id = applicant.get("applicant_id", "")
        account_id = account_by_applicant.get(applicant_id, "")
        name = str(applicant.get("name") or "").strip() or "応募者"
        target = toroo.is_target(account_id)

        entry = {
            "応募No": applicant_id,
            "氏名": name,
            "取り込み日時": now,
            "取り込み経路": IMPORT_ROUTE,
        }

        if target and applicant_mail.MAIL_TO:
            entry["メール送信"] = _send_applicant_mail(applicant, name, notifier)

        if target and toroo.is_enabled():
            if applicant_id in already_synced:
                entry["備考"] = "Toroo連携済みのためスキップ"
            else:
                stamp, job_id, note = _sync_to_toroo(applicant, name, notifier)
                entry["Toroo連携日時"] = stamp
                entry["Toroo求人ID"] = job_id
                if note:
                    entry["備考"] = note

        entries.append(entry)

    try:
        log.append(entries)
    except Exception as e:
        # 記録できないと次回また送ってしまう。重複の原因になる
        notifier.urgent(
            "Toroo連携の記録に失敗しました",
            f"連携ログに書き込めませんでした。\n{e}",
            "次回の実行で同じ方をもう一度送る恐れがあります。",
            "Torooの管理画面で重複が発生していないか確認してください。",
        )

    notifier.flush()


def _send_applicant_mail(applicant: dict, name: str, notifier) -> str:
    """連携ログに残す結果を返す"""
    try:
        mail_id = applicant_mail.send(applicant)
        logger.info(f"[{name}] 応募通知メールを送信しました")
    except Exception as e:
        notifier.urgent(
            f"応募通知メールを送信できませんでした（{name}様）",
            f"{name}様の応募情報をメールで送信できませんでした。\n{e}",
            "先方に応募が伝わっていません。スプレッドシートには記録済みです。",
            "復旧後に手動で連絡するか、こちらから再送します。",
        )
        return "送信失敗"

    # 宛先が間違っていても送信自体は成功する。状態を見ないと気づけない
    status = notify.get_mail_status(mail_id)
    if status in ("bounced", "complained"):
        notifier.urgent(
            "応募通知メールが宛先に届いていません",
            f"{name}様の応募情報を送信しましたが、宛先で受け取れませんでした"
            f"（状態: {status}）。",
            "先方に応募が伝わっていません。",
            "宛先アドレスが正しいか確認してください。",
        )
        return f"届きませんでした（{status}）"
    return now_stamp()


def now_stamp() -> str:
    return time.strftime("%Y/%m/%d %H:%M:%S")


def _sync_to_toroo(applicant: dict, name: str, notifier) -> tuple[str, str, str]:
    """(連携日時, 求人ID, 備考) を返す。失敗したら連携日時は空"""
    try:
        recruitment_id = toroo.resolve_recruitment_id(
            applicant.get("job_label", ""), applicant.get("job_title", "")
        )
    except toroo.TorooError as e:
        _notify_toroo_error(e, name, notifier, phase="求人ID解決", applicant=applicant)
        return "", "", f"求人IDを解決できず（{e.kind}）"

    try:
        toroo.create_applicant(applicant, recruitment_id)
    except toroo.TorooError as e:
        _notify_toroo_error(e, name, notifier, phase="応募者登録", applicant=applicant)
        return "", recruitment_id, f"登録できず（{e.kind}）"

    logger.info(f"[{name}] Torooに登録しました（求人ID {recruitment_id}）")
    return now_stamp(), recruitment_id, ""


def _notify_toroo_error(e, name: str, notifier, phase: str, applicant: dict) -> None:
    detail = (
        f"応募者　　{name}様\n"
        f"応募日時　{applicant.get('applied_at', '')}\n"
        f"求人　　　{applicant.get('job_title', '')}\n"
        f"求人ラベル　{applicant.get('job_label', '') or '（空欄）'}"
    )

    if e.kind == "auth":
        notifier.urgent(
            "Torooの認証に失敗しました",
            f"Torooへのログインが拒否されました。\n{e}",
            "応募者をTorooに登録できていません。",
            "APIキーの有効期限とオプション契約の状態を確認してください。",
        )
    elif e.kind == "network":
        notifier.check(
            "Torooに接続できませんでした",
            f"Torooから正常な応答がありませんでした（{phase}）。\n{e}",
            "次回の実行で再送されます。",
            "様子を見てください。2回続く場合は改めて連絡します。",
        )
    elif e.kind == "not_found":
        notifier.check(
            f"Toroo求人IDを特定できません（{name}様）",
            f"{name}様が応募された求人に対応する、Toroo側の求人が"
            f"見つかりませんでした。\n{e}",
            "この方はTorooに登録されていません。"
            "スプレッドシートには記録済みです。",
            "求人ボックスの求人ラベルに、Torooの求人IDを入力してください。"
            "入力後、次回の実行で自動的に再送されます。",
            details=detail,
        )
    elif e.kind == "ambiguous":
        notifier.check(
            f"該当する求人が複数あります（{name}様）",
            f"{name}様が応募された求人の候補がToroo側に2件以上ありました。\n{e}",
            "誤った求人に紐づくのを避けるため、登録していません。",
            "求人ラベルにTorooの求人IDを入力してください。",
            details=detail,
        )
    elif e.kind == "rejected":
        notifier.check(
            f"Torooへの登録が拒否されました（{name}様）",
            f"Torooが応募者データを受け付けませんでした。\n{e}",
            "この方はTorooに登録されていません。"
            "スプレッドシートには記録済みです。",
            "不足している項目を確認してください。",
            details=detail,
        )
    elif e.kind == "unknown_result":
        notifier.urgent(
            f"Toroo登録の結果を確認できません（{name}様）",
            f"送信しましたが応答が返ってきませんでした。\n{e}",
            "登録されたかどうか分かりません。",
            f"Torooの管理画面で{name}様が登録されているか確認してください。"
            "無ければ手動で追加してください。",
            details=detail,
        )
    else:
        notifier.urgent(
            f"Toroo連携で予期しないエラーが発生しました（{name}様）",
            str(e),
            "この方はTorooに登録されていません。",
            "実行ログを確認してください。",
            details=detail,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 想定外の例外もそのまま落とすと英語のログしか残らない。
        # 日本語で1通送ってから、終了コードは失敗のままにする。
        notifier = notify.Notifier(source="求人ボックス 応募者同期")
        notifier.urgent(
            "処理中に予期しないエラーが発生しました",
            f"想定していないエラーで処理が止まりました。\n{type(e).__name__}: {e}",
            "応募を取り込めていない可能性があります。",
            "実行ログを確認してください。",
            details=traceback.format_exc()[-1500:],
        )
        notifier.flush()
        raise

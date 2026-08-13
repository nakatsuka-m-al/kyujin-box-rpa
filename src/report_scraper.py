"""
求人ボックス アカウント一覧の実績値をスプレッドシートに記録する。

- 月ごと・アカウントごとに1行
- 同じ「年月 + ID」の行があれば、対象列だけ上書きする
  （設定CPA・売上・利益など手入力の列には触れない）
- 無ければ行を追加する

対象月は REPORT_MONTHS で指定する（例: "202604,202605"）。
未指定なら当月と前月。月初に前月の確定値を取りこぼさないため2ヶ月見る。
"""

import json
import logging
import os
import re
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.sync_api import sync_playwright

import scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SHEET_ID = os.environ["REPORT_SHEET_ID"]
SHEET_TAB = os.environ["REPORT_SHEET_TAB"]

LIST_URL = "https://saiyo.kyujinbox.com/ptr/s-accounts"

CHANNEL = "求人ボックス"

# シートの列見出し → 画面の列見出し
# ここに無い列（設定CPA・売上・利益など）は手入力のため一切触らない
COLUMN_SOURCE = {
    "ID":        "ID",
    "求人数":     "求人数",
    "公開中":     "公開中",
    "表示回数":   "表示回数",
    "クリック数": "クリック数",
    "CTR":       "CTR",
    "応募数":     "応募数",
    "CVR":       "CVR",
    "平均CPC":    "平均CPC",
    "費用":       "費用",
    "広告費":     "費用",   # 広告費は費用と同じ値
}

# 数値として書き込む列（カンマや ¥ を除去する）
NUMERIC_COLUMNS = {
    "求人数", "公開中", "表示回数", "クリック数", "応募数", "平均CPC", "費用", "広告費",
}

# シート側の見出し（表記ゆれ対策で部分一致させる）
HEADER_YEARMONTH = "年月"
HEADER_CHANNEL = "チャネル"
HEADER_ACCOUNT = "アカウント名"


# ─── 値の整形 ─────────────────────────────────────────────────────────────────

def clean_number(text: str):
    """"¥113,653" → 113653 / "10255" → 10255 / "-" → "" """
    s = re.sub(r"[¥,\s]", "", str(text or "").strip())
    if s in ("", "-", "―"):
        return ""
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return text


def clean_account_name(text: str) -> str:
    """"株式会社iDA/求人編集応募者確認" → "株式会社iDA" """
    return str(text or "").split("/")[0].strip()


def format_yearmonth(term: str) -> str:
    """"202608" → "2026年8月" （既存行の表記に合わせる）"""
    return f"{int(term[:4])}年{int(term[4:6])}月"


def normalize_yearmonth(text: str) -> str:
    """照合用に正規化する。

    Sheets が "2026年8月" を日付と解釈して "2026/08/01" 等で返すことがあるため、
    年と月だけを取り出して比較する。
    """
    nums = re.findall(r"\d+", str(text or ""))
    if len(nums) >= 2 and len(nums[0]) == 4:
        return f"{int(nums[0]):04d}-{int(nums[1]):02d}"
    return str(text or "").strip()


# ─── 画面から取得 ─────────────────────────────────────────────────────────────

def fetch_month(page, term: str) -> list[dict]:
    """指定月のアカウント別実績を取得する。term は "202608" 形式。"""
    url = f"{LIST_URL}?li=1000&type=1&term={term}&s=tp_d"
    page.goto(url)
    page.wait_for_load_state("networkidle")

    table = page.locator("table").first
    headers = [h.inner_text().strip().replace("\n", "/") for h in table.locator("th").all()]
    if not headers:
        raise RuntimeError(f"表の見出しが取得できませんでした（{url}）")

    # 見出しは "アカウント名/権限内容" のように結合されている場合がある
    index = {}
    for i, h in enumerate(headers):
        index[h] = i
        for part in h.split("/"):
            index.setdefault(part, i)

    rows = []
    for tr in table.locator("tbody tr").all():
        cells = [td.inner_text().strip().replace("\n", "/") for td in tr.locator("td").all()]
        if not cells:
            continue
        if cells[0].startswith("合計"):
            continue

        def cell(name: str) -> str:
            i = index.get(name)
            return cells[i] if i is not None and i < len(cells) else ""

        account_id = cell("ID").strip()
        if not account_id:
            continue

        rows.append({
            "term": term,
            "account_id": account_id,
            "account_name": clean_account_name(cells[index.get("アカウント名", 0)]),
            "raw": {name: cell(src) for name, src in COLUMN_SOURCE.items()},
        })

    logger.info(f"[{term}] {len(rows)} アカウント取得")
    return rows


# ─── スプレッドシートへ反映 ────────────────────────────────────────────────────

class ReportSheet:
    def __init__(self) -> None:
        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        logger.info(f"書き込み先タブ: '{SHEET_TAB}'")

        self._sheet_rows = (
            self._svc.spreadsheets().values()
            .get(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!A1:AZ")
            .execute()
        ).get("values", [])

        if not self._sheet_rows:
            raise RuntimeError(f"タブ '{SHEET_TAB}' にヘッダ行がありません")

        self._header = self._sheet_rows[0]
        self._col = self._build_column_index()
        logger.info(f"シートの既存行: {len(self._sheet_rows) - 1} 行")

    def _build_column_index(self) -> dict:
        """見出し → 列番号(0始まり)。部分一致も許容する。"""
        col = {}
        for i, name in enumerate(self._header):
            col[name.strip()] = i

        def resolve(key: str) -> int:
            if key in col:
                return col[key]
            for name, i in col.items():
                if key in name:      # "アカウント名" が "アカウント名権限内容" に一致
                    return i
            raise RuntimeError(
                f"シートに列 '{key}' が見つかりません。実際のヘッダ: {self._header}"
            )

        resolved = {
            HEADER_YEARMONTH: resolve(HEADER_YEARMONTH),
            HEADER_CHANNEL: resolve(HEADER_CHANNEL),
            HEADER_ACCOUNT: resolve(HEADER_ACCOUNT),
        }
        for key in COLUMN_SOURCE:
            resolved[key] = resolve(key)
        return resolved

    def _existing_index(self) -> dict:
        """(正規化した年月, ID) → シートの行番号(1始まり)"""
        ym_i = self._col[HEADER_YEARMONTH]
        id_i = self._col["ID"]
        found = {}
        for r, row in enumerate(self._sheet_rows[1:], start=2):
            ym = row[ym_i] if ym_i < len(row) else ""
            aid = row[id_i] if id_i < len(row) else ""
            if aid:
                found[(normalize_yearmonth(ym), aid.strip())] = r
        return found

    def _values_for(self, item: dict) -> dict:
        """列番号 → 書き込む値"""
        out = {
            self._col[HEADER_YEARMONTH]: format_yearmonth(item["term"]),
            self._col[HEADER_CHANNEL]: CHANNEL,
            self._col[HEADER_ACCOUNT]: item["account_name"],
        }
        for name in COLUMN_SOURCE:
            raw = item["raw"][name]
            out[self._col[name]] = clean_number(raw) if name in NUMERIC_COLUMNS else raw
        return out

    def upsert(self, items: list[dict]) -> None:
        if not items:
            return

        existing = self._existing_index()
        updates, appends = [], []

        for item in items:
            key = (normalize_yearmonth(format_yearmonth(item["term"])), item["account_id"])
            values = self._values_for(item)

            if key in existing:
                row_no = existing[key]
                # 手入力列を壊さないよう、対象列だけを個別に書く
                for col_i, value in values.items():
                    updates.append({
                        "range": f"{SHEET_TAB}!{a1_col(col_i)}{row_no}",
                        "values": [[value]],
                    })
            else:
                width = max(values) + 1
                row = [""] * width
                for col_i, value in values.items():
                    row[col_i] = value
                appends.append(row)

        if updates:
            self._svc.spreadsheets().values().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={"valueInputOption": "USER_ENTERED", "data": updates},
            ).execute()
            logger.info(f"既存 {len(updates) // len(self._col)} 行を更新しました")

        if appends:
            self._svc.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range=f"{SHEET_TAB}!A:AZ",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": appends},
            ).execute()
            logger.info(f"新規 {len(appends)} 行を追加しました")


def a1_col(index: int) -> str:
    """0 → A, 25 → Z, 26 → AA"""
    name = ""
    i = index
    while True:
        name = chr(ord("A") + i % 26) + name
        i = i // 26 - 1
        if i < 0:
            return name


# ─── 対象月 ───────────────────────────────────────────────────────────────────

def target_terms() -> list[str]:
    raw = os.environ.get("REPORT_MONTHS", "").strip()
    if raw:
        terms = [t.strip() for t in raw.split(",") if t.strip()]
        for t in terms:
            if not re.fullmatch(r"\d{6}", t):
                raise ValueError(f"対象月の形式が不正です: '{t}'（YYYYMM で指定）")
        return terms

    # 既定は前月と当月。月初に前月の確定値を取りこぼさないため。
    today = date.today()
    prev_y, prev_m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return [f"{prev_y}{prev_m:02d}", f"{today.year}{today.month:02d}"]


# ─── メイン ───────────────────────────────────────────────────────────────────

def main() -> None:
    terms = target_terms()
    logger.info(f"対象月: {terms}")

    sheet = ReportSheet()

    items = []
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
            for term in terms:
                items.extend(fetch_month(page, term))
        finally:
            browser.close()

    if not items:
        raise RuntimeError("1件も取得できませんでした。画面構成が変わった可能性があります")

    sheet.upsert(items)
    logger.info("完了")


if __name__ == "__main__":
    main()

"""
Google Sheets / RPM (ゼクウ) へのデータ書き込み

RPMExporter は現在未使用。API仕様書受領後に実装する。
インターフェース（post_applicants / FIELD_MAP）はそのまま維持して拡張のみで対応できる設計。
"""

import json
import logging
import os
import re
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# ─── Google Sheets ────────────────────────────────────────────────────────────

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
# GOOGLE_SHEET_TAB でタブ名を変更可能。デフォルトは「シート1」
SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "シート1")
SHEET_RANGE = f"{SHEET_TAB}!A:Z"

# 試験用。タブが存在しない場合に自動作成してよいか。
# 本番では設定しないこと（タブ名の設定ミスに気付けなくなるため）。
ALLOW_CREATE_TAB = os.environ.get("ALLOW_CREATE_TAB", "").lower() == "true"

# Sheets に書き込む列順（COLUMN_MAP の内部キー名と対応）
SHEETS_COLUMNS = [
    "applicant_id",
    "applied_at",
    "name",
    "gender",
    "birthdate",
    "current_job",
    "phone",
    "email",
    "address",
    "education",
    "work_history",
    "message",
    "job_title",
    "job_id",
    "status",
    "selection_comment",
    "job_label",
    "_subaccount_name",
]

HEADER_ROW = [
    "応募No", "応募日時", "氏名", "性別", "生年月日", "現在の職業",
    "電話番号", "メールアドレス", "住所", "学校名", "職歴",
    "備考・PR", "求人タイトル", "求人ID", "選考ステータス",
    "選考コメント", "求人ラベル", "拠点名",
]


class SheetsExporter:
    def __init__(self) -> None:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not sa_json:
            logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON 未設定 — Sheets 書き込みをスキップします")
            self._service = None
            return

        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        logger.info(f"書き込み先タブ: '{SHEET_TAB}'")

    def _ensure_tab_exists(self) -> None:
        """試験用タブが無ければ作る。ALLOW_CREATE_TAB=true のときだけ動く。"""
        if not ALLOW_CREATE_TAB:
            return
        meta = self._service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        if SHEET_TAB in [s["properties"]["title"] for s in meta["sheets"]]:
            return
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET_TAB}}}]},
        ).execute()
        logger.info(f"タブ '{SHEET_TAB}' を新規作成しました")

    def fetch_existing_ids(self) -> set[str]:
        """シート上の既存 applicant_id を取得してキャッシュと合わせて使う"""
        # append より先に呼ばれることがあるため、ここでもタブの存在を保証する
        self._ensure_tab_exists()
        col_index = SHEETS_COLUMNS.index("applicant_id")
        col_letter = chr(ord("A") + col_index)
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!{col_letter}2:{col_letter}10000")
            .execute()
        )
        ids = set()
        for row in result.get("values", []):
            if row and row[0]:
                ids.add(row[0])
        logger.info(f"シート上の既存 applicant_id: {len(ids)} 件")
        return ids

    def append(self, applicants: list[dict]) -> None:
        if not self._service or not SHEET_ID:
            logger.warning("Sheets 書き込みをスキップ（設定未完了）")
            return

        self._ensure_tab_exists()
        self._ensure_header()

        # シート上の既存IDと照合して重複を除外
        existing_ids = self.fetch_existing_ids()
        deduped = [a for a in applicants if a.get("applicant_id", "") not in existing_ids]
        skipped = len(applicants) - len(deduped)
        if skipped:
            logger.info(f"{skipped} 件はシート上に既存のため書き込みをスキップ")
        if not deduped:
            logger.info("新規書き込みなし")
            return

        rows = [
            [a.get(col, "") for col in SHEETS_COLUMNS]
            for a in deduped
        ]

        self._service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=SHEET_RANGE,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()

        logger.info(f"Sheets に {len(rows)} 行追記しました")

    def _ensure_header(self) -> None:
        """1行目が空なら HEADER_ROW を書き込む"""
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!A1:Z1")
            .execute()
        )
        if not result.get("values"):
            self._service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"{SHEET_TAB}!A1",
                valueInputOption="RAW",
                body={"values": [HEADER_ROW]},
            ).execute()
            logger.info("ヘッダ行を書き込みました")


# ─── Raw Sheets（ATS等、列マッピング不要な用途）────────────────────────────────

ATS_SHEET_TAB = os.environ.get("ATS_SHEET_TAB", "ATS")

# ATS の一意キー（ats_scraper.KEY_COLUMNS と揃える）
ATS_KEY_COLUMNS = ("お仕事ID", "お名前", "応募受付日時")


DATETIME_KEY_COLUMNS = {"応募受付日時"}


def normalize_datetime(value: str) -> str:
    """日時をどんな表記でも YYYYMMDDHHMM に揃える。

    Sheets は USER_ENTERED で書き込んだ日時を表示形式に変換するため、
    CSV と同じ文字列では返ってこない。実際に観測された例:
      CSV   : "2026-04-11 21:22:00"
      シート: "2026年4月11日21時22分"   ← 日本語かつゼロ埋めなし
    そのため数字を順に取り出し、年月日時分として組み直す。
    秒は表示形式によって落ちるため比較に含めない。
    """
    s = str(value or "").strip()
    parts = [int(p) for p in re.findall(r"\d+", s)]
    # 年月日が揃っていて、先頭が4桁の年として妥当な場合のみ解釈する
    if len(parts) >= 3 and 1000 <= parts[0] <= 9999:
        nums = (parts[:5] + [0, 0])[:5]
        y, mo, d, h, mi = nums
        return f"{y:04d}{mo:02d}{d:02d}{h:02d}{mi:02d}"
    # 解釈できない形式はそのまま数字を並べる（照合できずとも壊れないように）
    return re.sub(r"\D", "", s)


def normalize_key_value(column: str, value: str) -> str:
    """シート側の表記ゆれを吸収する"""
    if column in DATETIME_KEY_COLUMNS:
        return normalize_datetime(value)
    return re.sub(r"[\s\-/:_.]", "", str(value or "").strip())


def build_ats_key(get_value) -> str:
    """列名から値を引く関数を受け取り、正規化済みの一意キーを組み立てる"""
    return "__".join(normalize_key_value(col, get_value(col)) for col in ATS_KEY_COLUMNS)


class RawSheetsExporter:
    """CSV の列をそのままシートに書き込む汎用エクスポーター"""

    def __init__(self) -> None:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not sa_json:
            logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON 未設定 — Sheets 書き込みをスキップします")
            self._service = None
            return

        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        # 設定ミスに気付けるよう、書き込み先を必ずログに残す
        logger.info(f"[ATS] 書き込み先タブ: '{ATS_SHEET_TAB}'")

    def _ensure_tab_exists(self) -> None:
        """試験用タブが無ければ作る。ALLOW_CREATE_TAB=true のときだけ動く。"""
        if not ALLOW_CREATE_TAB:
            return
        meta = self._service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        titles = [s["properties"]["title"] for s in meta["sheets"]]
        if ATS_SHEET_TAB in titles:
            return
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": ATS_SHEET_TAB}}}]},
        ).execute()
        logger.info(f"[ATS] タブ '{ATS_SHEET_TAB}' を新規作成しました")

    def fetch_existing_keys(self) -> set[str]:
        """シート上の既存行から一意キーの集合を作る。

        キー列がヘッダに無い等で判定できない場合は空集合を返し、
        書き込み自体はブロックしない（取りこぼしより重複の方が復旧しやすいため）。
        """
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=f"{ATS_SHEET_TAB}!A:ZZ")
            .execute()
        )
        sheet_rows = result.get("values", [])
        if not sheet_rows:
            return set()

        header = sheet_rows[0]
        try:
            indices = {col: header.index(col) for col in ATS_KEY_COLUMNS}
        except ValueError as e:
            logger.warning(f"[ATS] キー列がシートに見つからないため重複チェックをスキップ: {e}")
            return set()

        keys = set()
        for row in sheet_rows[1:]:
            key = build_ats_key(
                lambda col: row[indices[col]] if indices[col] < len(row) else ""
            )
            keys.add(key)

        logger.info(f"[ATS] シート上の既存行: {len(keys)} 件")
        return keys

    def append(self, rows: list[dict]) -> None:
        if not self._service or not SHEET_ID:
            logger.warning("Sheets 書き込みをスキップ（設定未完了）")
            return

        if not rows:
            return

        self._ensure_tab_exists()

        # シート上の既存行と照合して重複を除外（キャッシュ消失時の保険）
        existing_keys = self.fetch_existing_keys()
        if existing_keys:
            deduped = [r for r in rows if build_ats_key(lambda c: r.get(c, "")) not in existing_keys]
            skipped = len(rows) - len(deduped)
            if skipped:
                logger.info(f"[ATS] {skipped} 件はシート上に既存のため書き込みをスキップ")
            rows = deduped
            if not rows:
                logger.info("[ATS] 新規書き込みなし")
                return

        # 既存シートのヘッダに合わせて値を並べる。
        # CSV の列順のまま書くと、列が増減したときに値が別の列に入ってしまう。
        header = self._resolve_header(rows)

        values = [[str(row.get(col, "")) for col in header] for row in rows]
        self._service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=f"{ATS_SHEET_TAB}!A:ZZ",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        logger.info(f"[ATS] Sheets に {len(values)} 行追記しました")

        # 応募受付日時列で昇順ソート
        if "応募受付日時" in header:
            self._sort_descending(header.index("応募受付日時"))

    def _get_sheet_gid(self) -> int:
        result = self._service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        for sheet in result["sheets"]:
            if sheet["properties"]["title"] == ATS_SHEET_TAB:
                return sheet["properties"]["sheetId"]
        raise ValueError(f"シートタブ '{ATS_SHEET_TAB}' が見つかりません")

    def _sort_descending(self, col_index: int) -> None:
        """指定列で降順ソート（ヘッダ行を除く）"""
        gid = self._get_sheet_gid()
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{
                "sortRange": {
                    "range": {"sheetId": gid, "startRowIndex": 1},
                    "sortSpecs": [{"dimensionIndex": col_index, "sortOrder": "ASCENDING"}],
                }
            }]},
        ).execute()
        logger.info("[ATS] 応募受付日時で昇順ソートしました")

    def _resolve_header(self, rows: list[dict]) -> list[str]:
        """書き込みに使う列の並びを決める。

        既存シートのヘッダを正とする。CSV 側にしか無い列が現れた場合は
        ヘッダの末尾に追加する（既存列の位置は動かさない）。
        こうしないと、列が増減したときに値が別の列に入る。
        """
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=f"{ATS_SHEET_TAB}!A1:ZZ1")
            .execute()
        )
        existing = (result.get("values") or [[]])[0]

        # 全行のキーを順序を保ったまま集める
        csv_columns = list(dict.fromkeys(k for row in rows for k in row.keys()))

        if not existing:
            self._write_header(csv_columns)
            return csv_columns

        added = [c for c in csv_columns if c not in existing]
        if added:
            logger.info(f"[ATS] 新しい列をヘッダ末尾に追加します: {added}")
            existing = existing + added
            self._write_header(existing)

        dropped = [c for c in csv_columns if c not in existing]
        if dropped:  # 通常は起きない
            logger.warning(f"[ATS] ヘッダに追加できなかった列があります: {dropped}")

        return existing

    def _write_header(self, columns: list[str]) -> None:
        self._service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"{ATS_SHEET_TAB}!A1",
            valueInputOption="RAW",
            body={"values": [columns]},
        ).execute()
        logger.info(f"[ATS] ヘッダ行を書き込みました（{len(columns)} 列）")

    def _ensure_header(self, columns: list[str]) -> None:
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=f"{ATS_SHEET_TAB}!A1:ZZ1")
            .execute()
        )
        if not result.get("values"):
            self._service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"{ATS_SHEET_TAB}!A1",
                valueInputOption="RAW",
                body={"values": [columns]},
            ).execute()
            logger.info("[ATS] ヘッダ行を書き込みました")


# ─── RPM (ゼクウ) ─────────────────────────────────────────────────────────────
# 現在は未使用（Sheets のみ稼働）。
# API仕様書受領後の実装手順:
#   1. FIELD_MAP の右辺を実際の RPM フィールド名に更新
#   2. post_applicants に requests.post を実装
#   3. GitHub Secrets に RPM_API_KEY / RPM_API_ENDPOINT を追加
#   4. scraper.py の rpm.post_applicants() のコメントアウトを外す

# 内部キー → RPM フィールド名（仮。仕様書受領後に更新）
FIELD_MAP: dict[str, str] = {
    "applicant_id": "applicant_code",
    "applied_at":   "application_date",
    "name":         "full_name",
    "name_kana":    "full_name_kana",
    "email":        "email_address",
    "phone":        "phone_number",
    "address":      "address",
    "birthdate":    "birth_date",
    "age":          "age",
    "gender":       "gender",
    "education":    "education",
    "work_history": "career_summary",
    "desired_job":  "desired_position",
    "message":      "message",
    "job_title":    "job_name",
    "job_id":       "job_code",
    "status":       "application_status",
}


class RPMExporter:
    """RPM (ゼクウ) 連携スタブ。API仕様書受領後に post_applicants を実装する。"""

    def post_applicants(self, applicants: list[dict]) -> None:
        # 未実装。API仕様書受領後にここを埋める。
        logger.info("RPM連携はスキップ（未実装）")

    def _build_payload(self, a: dict) -> dict[str, Any]:
        return {rpm_key: a[k] for k, rpm_key in FIELD_MAP.items() if a.get(k)}

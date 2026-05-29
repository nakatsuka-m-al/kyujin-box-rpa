"""
Google Sheets / RPM (ゼクウ) へのデータ書き込み
"""

import json
import logging
import os
from typing import Any

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# ─── Google Sheets ────────────────────────────────────────────────────────────

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
SHEET_RANGE = "応募者!A:Z"  # シート名・範囲は実態に合わせて変更

# Sheets に書き込む列順（COLUMN_MAP の内部キー名と対応）
SHEETS_COLUMNS = [
    "applicant_id",
    "applied_at",
    "name",
    "name_kana",
    "email",
    "phone",
    "address",
    "birthdate",
    "age",
    "gender",
    "education",
    "work_history",
    "desired_job",
    "desired_location",
    "desired_salary",
    "message",
    "job_title",
    "job_id",
    "status",
    "_subaccount_name",
]

# ヘッダ行ラベル（1行目が空の場合に自動挿入）
HEADER_ROW = [
    "応募ID", "応募日時", "氏名", "氏名（カナ）", "メールアドレス", "電話番号",
    "住所", "生年月日", "年齢", "性別", "最終学歴", "職歴",
    "希望職種", "希望勤務地", "希望給与", "メッセージ",
    "求人タイトル", "求人ID", "ステータス", "拠点名",
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

    def append(self, applicants: list[dict]) -> None:
        if not self._service or not SHEET_ID:
            logger.warning("Sheets 書き込みをスキップ（設定未完了）")
            return

        self._ensure_header()

        rows = [
            [a.get(col, "") for col in SHEETS_COLUMNS]
            for a in applicants
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
            .get(spreadsheetId=SHEET_ID, range="応募者!A1:Z1")
            .execute()
        )
        if not result.get("values"):
            self._service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range="応募者!A1",
                valueInputOption="RAW",
                body={"values": [HEADER_ROW]},
            ).execute()
            logger.info("ヘッダ行を書き込みました")


# ─── RPM (ゼクウ) ─────────────────────────────────────────────────────────────

RPM_API_KEY = os.environ.get("RPM_API_KEY", "")
RPM_API_ENDPOINT = os.environ.get("RPM_API_ENDPOINT", "")

# TODO: ゼクウから API 仕様書を受領後、実際のフィールド名に更新
FIELD_MAP: dict[str, str] = {
    "applicant_id": "applicant_code",      # RPM側フィールド名（仮）
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
    def __init__(self) -> None:
        if not RPM_API_KEY or not RPM_API_ENDPOINT:
            logger.warning("RPM_API_KEY / RPM_API_ENDPOINT 未設定 — RPM 連携をスキップします")

    def post_applicants(self, applicants: list[dict]) -> None:
        if not RPM_API_KEY or not RPM_API_ENDPOINT:
            return

        ok = 0
        ng = 0
        for a in applicants:
            payload = self._build_payload(a)
            try:
                resp = requests.post(
                    RPM_API_ENDPOINT,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {RPM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                ok += 1
            except requests.RequestException as e:
                logger.error(f"RPM POST 失敗 (applicant_id={a.get('applicant_id')}): {e}")
                ng += 1

        logger.info(f"RPM: 成功 {ok} 件 / 失敗 {ng} 件")

    def _build_payload(self, a: dict) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for internal_key, rpm_key in FIELD_MAP.items():
            val = a.get(internal_key, "")
            if val:
                payload[rpm_key] = val
        return payload

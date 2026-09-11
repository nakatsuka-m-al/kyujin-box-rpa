"""
基盤シート（応募者取得RPA）の1タブを読んで、応募者ポータルの取り込みAPIへ送る。
最初の全件取り込みと、取りこぼしの救済に使う。何回流しても重複しない（API 側で捨てる）。

環境変数:
  GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID  … 既存と同じ
  PORTAL_INGEST_URL, PORTAL_INGEST_TOKEN         … 送り先
  BACKFILL_TAB       … 読むタブ名（OBS / ATS のタブ名）
  BACKFILL_MEDIA     … kyujinbox または ats
  BACKFILL_FROM_ROW  … 省略可。この行番号（1始まり）から。既定 2（1行目は見出し）
  BACKFILL_DRY_RUN   … "1" なら件数を出すだけで送らない
  BACKFILL_ALLOW_UNKNOWN … "1" なら媒体アカウントが特定できない行があっても送る（既定は中断）

取り込みAPIは同じキーを二度入れない（ignoreDuplicates）ため、間違った内容で一度入れると
再実行では直らない。最初は DRY_RUN で件数を確認してから流すこと。

ログに個人情報を出さない（件数のみ）。
"""

import json
import logging
import os
import re
import sys

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

import portal_exporter
from exporters import HEADER_ROW, SHEETS_COLUMNS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _service():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_tab(tab: str) -> tuple[list[str], list[list[str]]]:
    """1行目を見出し、2行目以降をデータとして返す"""
    svc = _service()
    quoted = "'" + tab.replace("'", "''") + "'"  # 空白や記号を含むタブ名でも通る
    res = svc.spreadsheets().values().get(
        spreadsheetId=os.environ["GOOGLE_SHEET_ID"], range=f"{quoted}!A1:ZZ"
    ).execute()
    values = res.get("values") or []
    if not values:
        return [], []
    header = [str(h).strip() for h in values[0]]
    return header, values[1:]


def rows_to_dicts(header: list[str], rows: list[list[str]]) -> list[dict]:
    """見出しが空の列は捨てる。短い行は空文字で埋める。
    同名の見出しが複数あれば後の列が勝つ（OBS の S列と U列「暗号」は U が残る）"""
    out = []
    for r in rows:
        d = {header[i]: (str(r[i]) if i < len(r) and r[i] is not None else "")
             for i in range(len(header)) if header[i]}
        out.append(d)
    return out


# OBS: シートの見出し（HEADER_ROW）→ 内部キー（SHEETS_COLUMNS）
_OBS_MAP = dict(zip(HEADER_ROW, SHEETS_COLUMNS))


def kyujinbox_items(dicts: list[dict], from_row: int) -> list[dict]:
    """OBS の行を取り込みAPIの形にする。応募No が空の行は飛ばす（行番号はシート通りに進める）"""
    items = []
    for i, d in enumerate(dicts):
        row_no = from_row + i
        a = {_OBS_MAP.get(k, k): v for k, v in d.items()}
        a["_subaccount_name"] = d.get("拠点名", "")
        a["_raw"] = d
        account_id = d.get("アカウントID", "")
        payload = portal_exporter.build_kyujinbox_payload(
            [a], {a.get("applicant_id", ""): account_id}, "initial_import"
        )
        for item in payload["applicants"]:
            item["source_sheet_row"] = row_no
            items.append(item)
    return items


def ats_items(dicts: list[dict], from_row: int) -> list[dict]:
    """ATS タブの行を取り込みAPIの形にする。キーが空の行は飛ばす"""
    items = []
    for i, d in enumerate(dicts):
        payload = portal_exporter.build_ats_payload([d], "initial_import")
        for item in payload["applicants"]:
            item["source_sheet_row"] = from_row + i
            items.append(item)
    return items


def post_all(media: str, items: list[dict]) -> dict:
    """200件ずつ送る。1回でも失敗したら例外（救済実行なので止めてよい）"""
    url = portal_exporter._env("PORTAL_INGEST_URL").rstrip("/") + "/api/ingest"
    headers = {"Authorization": f"Bearer {portal_exporter._env('PORTAL_INGEST_TOKEN')}"}
    total = {"received": 0, "inserted": 0, "skipped": 0, "unassigned": 0}
    sent = 0
    for chunk in portal_exporter.chunked(items, portal_exporter.BATCH):
        r = requests.post(url, json={"media": media, "route": "initial_import", "applicants": chunk},
                          headers=headers, timeout=120)
        if r.status_code >= 300:
            excerpt = re.sub(r"\s+", " ", r.text or "")[:300]
            raise RuntimeError(f"HTTP {r.status_code}（{sent}〜{sent + len(chunk)} 件目）: {excerpt}")
        body = r.json()
        for k in total:
            total[k] += int(body.get(k) or 0)
        sent += len(chunk)
        logger.info(f"{sent}/{len(items)} 送信済み")
    return total


def run() -> int:
    if not portal_exporter.is_enabled():
        logger.error("PORTAL_INGEST_URL / PORTAL_INGEST_TOKEN が未設定です")
        return 1
    tab = os.environ.get("BACKFILL_TAB", "").strip()
    media = os.environ.get("BACKFILL_MEDIA", "").strip()
    if not tab:
        logger.error("BACKFILL_TAB が未設定です")
        return 1
    if media not in ("kyujinbox", "ats"):
        logger.error("BACKFILL_MEDIA は kyujinbox か ats")
        return 1
    try:
        from_row = int(os.environ.get("BACKFILL_FROM_ROW") or "2")
    except ValueError:
        logger.error("BACKFILL_FROM_ROW は整数")
        return 1
    if from_row < 2:
        logger.error("BACKFILL_FROM_ROW は 2 以上（1行目は見出し）")
        return 1
    dry_run = os.environ.get("BACKFILL_DRY_RUN", "").strip() == "1"
    allow_unknown = os.environ.get("BACKFILL_ALLOW_UNKNOWN", "").strip() == "1"

    header, rows = read_tab(tab)
    if media == "kyujinbox" and "アカウントID" not in header:
        logger.error("OBS の見出しに「アカウントID」がありません（Z1 未記入）。全件が未特定になるため中断します")
        return 1
    rows = rows[from_row - 2:]
    dicts = rows_to_dicts(header, rows)
    logger.info(f"タブ読み込み: {len(dicts)} 行（{from_row} 行目から）")

    items = kyujinbox_items(dicts, from_row) if media == "kyujinbox" else ats_items(dicts, from_row)
    unknown = sum(1 for it in items if it["external_id"] == "unknown")
    logger.info(f"送信対象: {len(items)} 件（媒体アカウント未特定: {unknown} 件）")
    if unknown and not allow_unknown:
        logger.error("媒体アカウントを特定できない行があります。シートのアカウントID列を確認するか、"
                     "BACKFILL_ALLOW_UNKNOWN=1 で送ってください（送ると再実行では直りません）")
        return 1
    if dry_run:
        logger.info("DRY_RUN のため送信しません")
        return 0
    if not items:
        return 0

    total = post_all(media, items)
    logger.info(f"完了: {total}")
    return 0


def main() -> int:
    try:
        return run()
    except Exception as e:  # noqa: BLE001 - 手動実行なので1行の日本語で止める
        logger.error(f"中断: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

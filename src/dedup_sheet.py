"""
シートの重複行を自動削除するワンショットスクリプト
applicant_id が同じ行は最初の1件を残して削除する
"""

import json
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SHEET_ID  = os.environ["GOOGLE_SHEET_ID"]
SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "シート1")

def main():
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sheets = service.spreadsheets()

    # 全データ取得
    result = sheets.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A:Z",
    ).execute()
    rows = result.get("values", [])
    if not rows:
        logger.info("データなし")
        return

    header = rows[0]
    try:
        id_col = header.index("応募No")
    except ValueError:
        logger.error("ヘッダに '応募No' が見つかりません")
        return

    # 重複行のインデックスを特定（0始まり、1行目はヘッダ）
    seen = set()
    delete_rows = []  # 削除する行番号（1始まり）
    for i, row in enumerate(rows[1:], start=2):
        aid = row[id_col] if id_col < len(row) else ""
        if not aid:
            continue
        if aid in seen:
            delete_rows.append(i)
        else:
            seen.add(aid)

    if not delete_rows:
        logger.info("重複なし")
        return

    logger.info(f"重複行 {len(delete_rows)} 件を削除します: 行番号 {delete_rows}")

    # シートIDを取得
    meta = sheets.get(spreadsheetId=SHEET_ID).execute()
    gid = next(
        s["properties"]["sheetId"]
        for s in meta["sheets"]
        if s["properties"]["title"] == SHEET_TAB
    )

    # 下から削除（行番号がずれないよう逆順）
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": gid,
                    "dimension": "ROWS",
                    "startIndex": r - 1,
                    "endIndex": r,
                }
            }
        }
        for r in sorted(delete_rows, reverse=True)
    ]

    sheets.batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": requests},
    ).execute()

    logger.info(f"完了: {len(delete_rows)} 行削除しました")


if __name__ == "__main__":
    main()

"""
ATS の重複チェックが正しく機能するかを検証する読み取り専用スクリプト。

シートには一切書き込まない。
CSV から作ったキーが、シート上の既存行のキーと一致するかだけを報告する。
一致率が 100% なら、キャッシュが消えても重複書き込みは起きない。
"""

import logging
import os

from playwright.sync_api import sync_playwright

import ats_scraper as ats
from exporters import ATS_KEY_COLUMNS, RawSheetsExporter, build_ats_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
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
            accept_downloads=True,
        )
        try:
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            ats.login(page)
            app_page = ats.go_to_applicant_list(page, context)
            raw = ats.download_csv(app_page)
        finally:
            browser.close()

    rows = ats.enrich_indeed_rows(ats.parse_csv(raw))
    logger.info(f"CSV取得: {len(rows)} 件")

    exporter = RawSheetsExporter()

    # 診断: シート側の生の値とキーを確認する
    import os as _os
    tab = _os.environ.get("ATS_SHEET_TAB", "ATS")
    raw_sheet = (
        exporter._service.spreadsheets()
        .values()
        .get(spreadsheetId=_os.environ["GOOGLE_SHEET_ID"], range=f"{tab}!A:ZZ")
        .execute()
    ).get("values", [])
    if raw_sheet:
        header = raw_sheet[0]
        logger.info(f"シートのヘッダ（先頭10列）: {header[:10]}")
        idx = {c: (header.index(c) if c in header else None) for c in ATS_KEY_COLUMNS}
        logger.info(f"キー列の位置: {idx}")
        for r in raw_sheet[1:4]:
            vals = {c: (r[i] if i is not None and i < len(r) else "<欠損>") for c, i in idx.items()}
            logger.info(f"シート行のキー列の値: {vals}")

    sheet_keys = exporter.fetch_existing_keys()
    for k in list(sheet_keys)[:5]:
        logger.info(f"シート側キー例: {k}")

    if not sheet_keys:
        logger.error("シートからキーを取得できませんでした。列名を確認してください。")
        logger.error(f"期待するキー列: {ATS_KEY_COLUMNS}")
        raise SystemExit(1)

    matched, unmatched = [], []
    for row in rows:
        key = build_ats_key(lambda c: row.get(c, ""))
        (matched if key in sheet_keys else unmatched).append((key, row))

    logger.info("=" * 60)
    logger.info(f"シート上の既存行 : {len(sheet_keys)} 件")
    logger.info(f"CSV の行         : {len(rows)} 件")
    logger.info(f"  照合できた     : {len(matched)} 件")
    logger.info(f"  照合できない   : {len(unmatched)} 件")
    logger.info("=" * 60)

    if unmatched:
        logger.warning("以下はシート上に見つかりませんでした（本当に未登録なら正常）:")
        for key, row in unmatched[:10]:
            vals = {c: row.get(c, "") for c in ATS_KEY_COLUMNS}
            logger.warning(f"  key={key}")
            logger.warning(f"    元の値={vals}")
        if len(unmatched) > 10:
            logger.warning(f"  ... 他 {len(unmatched) - 10} 件")

    rate = len(matched) / len(rows) * 100 if rows else 0
    logger.info(f"照合率: {rate:.1f}%")
    if rate == 100:
        logger.info("→ 全件が既存として認識されます。キャッシュ消失時も重複しません。")
    else:
        logger.warning("→ 照合できない行があります。上の値を確認してください。")


if __name__ == "__main__":
    main()

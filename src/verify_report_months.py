"""
月の指定が実際に効いているかを確認する。読み取り専用。

URL の term パラメータで月を切り替えているが、
セッション側の値が優先されるなどして無視されている可能性がある。
複数の月を取得して、数字が本当に変わるかを見る。
"""

import logging
import os

from playwright.sync_api import sync_playwright

import report_scraper as rs
import scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TERMS = ["202604", "202605", "202606", "202607", "202608"]


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
        )
        try:
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            scraper.login(page)

            summary = {}
            for term in TERMS:
                url = f"{rs.LIST_URL}?li=1000&type=1&term={term}&s=tp_d"
                page.goto(url)
                page.wait_for_load_state("networkidle")

                # 画面の期間セレクタが実際に何を選んでいるか
                selected = "?"
                for sel in page.locator("select").all():
                    if (sel.get_attribute("name") or "") == "accounts[term]":
                        selected = sel.input_value()

                # 合計行を数字の指紋として使う
                total = []
                for tr in page.locator("table").first.locator("tbody tr").all():
                    cells = [td.inner_text().strip() for td in tr.locator("td").all()]
                    if cells and cells[0].startswith("合計"):
                        total = cells
                        break

                rows = rs.fetch_month(page, term)
                first = rows[0] if rows else {}

                logger.info(
                    f"[要求 {term}] 画面のセレクタ={selected}  "
                    f"合計の表示回数={total[7] if len(total) > 7 else '?'}  "
                    f"合計の費用={total[13] if len(total) > 13 else '?'}"
                )
                if first:
                    logger.info(
                        f"          先頭: {first['account_name']} "
                        f"表示回数={first['raw']['表示回数']} 費用={first['raw']['費用']}"
                    )
                summary[term] = (selected, tuple(total))

            logger.info("=" * 60)
            distinct = {v[1] for v in summary.values()}
            if len(distinct) == 1:
                logger.error("すべての月で数字が同一です。月の指定が効いていません。")
                raise SystemExit(1)
            if len(distinct) < len(TERMS):
                logger.warning(
                    f"{len(TERMS)} ヶ月中 {len(distinct)} 種類の数字しかありません。"
                    "一部の月が同じ内容になっています。"
                )
            else:
                logger.info("すべての月で数字が異なります。月の指定は正しく効いています。")

            for term, (selected, _) in summary.items():
                mark = "OK" if selected == term else "不一致"
                logger.info(f"  {term}: セレクタ={selected}  {mark}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()

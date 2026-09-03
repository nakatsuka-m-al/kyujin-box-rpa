# -*- coding: utf-8 -*-
"""フェーズ1: 正社員(無期)紹介数の多い順に一覧をスキャンし、上位N社を抽出する。

一覧ページに就職者数まで載っているため詳細ページは開かない。
支社は同じ許可番号で複数行出るので、許可番号で1社に集約する
（サイトの数字自体が全社合計なので、これが正しい扱い）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from jinzai_common import (
    check_maintenance_window, new_page, open_sorted_list, goto_page,
    grab_list_rows, now_jst,
)

TARGET = int(os.environ.get("TARGET", "500"))
OUT_JSON = "/Users/masakatsu/Desktop/kyujin_box_rpa/top500_companies.json"
MAX_PAGES = 1200


def main():
    check_maintenance_window()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = new_page(browser)

        total = open_sorted_list(page, nationwide=True, category="2", order="2")
        print(f"全国・有料職業紹介: {total:,}事業所 を無期(正社員)降順で走査", flush=True)

        companies = {}   # 許可番号 -> dict
        rows_seen = 0
        page_num = 1
        t0 = time.time()

        while len(companies) < TARGET and page_num <= MAX_PAGES:
            if page_num > 1:
                try:
                    goto_page(page, page_num)
                except Exception as e:
                    print(f"  ページ{page_num}送り失敗: {str(e)[:60]} — 再確立して再試行", flush=True)
                    try:
                        open_sorted_list(page, nationwide=True, category="2", order="2")
                        goto_page(page, page_num)
                    except Exception as e2:
                        print(f"  再確立も失敗: {str(e2)[:60]} — 打ち切り", flush=True)
                        break

            rows = grab_list_rows(page)
            if not rows:
                print(f"  ページ{page_num}: 行なし。終了", flush=True)
                break
            rows_seen += len(rows)

            for r in rows:
                lic = r["許可番号"]
                if not lic or lic in companies:
                    continue
                if r["うち無期"] is None:
                    continue
                companies[lic] = {
                    "順位": len(companies) + 1,
                    "許可番号": lic,
                    "許可年月日": r["許可年月日"],
                    "事業主名称": r["事業主名称"],
                    "本社所在地": r["所在地"],
                    "電話": r["電話"],
                    "正社員(無期)紹介数": r["うち無期"],
                    "就職者数_4ヶ月以上": r["就職者_4ヶ月以上"],
                    "公式HP": "",
                    "取得日時": now_jst(),
                }
                if len(companies) >= TARGET:
                    break

            if page_num % 20 == 0 or len(companies) >= TARGET:
                el = time.time() - t0
                print(f"  p{page_num}: {rows_seen}行走査 → {len(companies)}社 "
                      f"({el:.0f}秒経過)", flush=True)
            page_num += 1

        browser.close()

    result = sorted(companies.values(), key=lambda x: -x["正社員(無期)紹介数"])
    for i, r in enumerate(result, 1):
        r["順位"] = i

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    print(f"\n===== スキャン完了 =====", flush=True)
    print(f"走査行数: {rows_seen} / 抽出企業: {len(result)}社", flush=True)
    if result:
        print(f"1位: {result[0]['事業主名称']} ({result[0]['正社員(無期)紹介数']:,}件)", flush=True)
        print(f"{len(result)}位: {result[-1]['事業主名称']} ({result[-1]['正社員(無期)紹介数']:,}件)", flush=True)
    print(f"出力: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()

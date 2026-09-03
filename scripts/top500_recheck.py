# -*- coding: utf-8 -*-
"""取得済みの公式HPを現在の検証ロジックで再検査し、不合格のものを空欄に戻す。
検索はせずページ確認のみなので高速。判定ロジックを更新した後に流す。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from jinzai_common import new_page, verify_site, is_bad_url, extract_city

JSON_PATH = "/Users/masakatsu/Desktop/kyujin_box_rpa/top500_companies.json"


def main():
    with open(JSON_PATH, encoding="utf-8") as f:
        rows = json.load(f)

    targets = [r for r in rows if r.get("公式HP")]
    print(f"取得済み {len(targets)}社 を再検証します", flush=True)

    removed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        vp = new_page(browser)
        vp.set_default_timeout(15000)

        for i, r in enumerate(targets, 1):
            url = r["公式HP"]
            name = r["事業主名称"]
            _, city_only = extract_city(r.get("本社所在地", ""))
            if is_bad_url(url):
                ok = ""
            else:
                ok = verify_site(vp, url, name, city_only, r.get("電話", ""), browser)
            if not ok:
                print(f"[{i}/{len(targets)}] 除去: {name[:24]:<26} {url[:46]}", flush=True)
                r["公式HP"] = ""
                removed += 1
            elif ok != url:
                print(f"[{i}/{len(targets)}] 正規化: {name[:24]:<26} {url[:34]} -> {ok[:34]}", flush=True)
                r["公式HP"] = ok

        browser.close()

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    got = len([r for r in rows if r.get("公式HP")])
    print(f"\n再検証完了: 除去{removed}件 / 残り有効{got}件", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""フェーズ2: 抽出済み企業リストに公式HPを付与する。

- 1社ごとにJSONへ即時保存するので、中断しても再開時に続きから処理される
- 検索エンジンのレート制限対策で1社あたり十数秒〜数十秒かかる
- 誤マッチ（法人DB・地図・求人ポータル）は検証段階で弾き、見つからなければ空欄のまま
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from jinzai_common import (
    check_maintenance_window, new_page, find_official_site, is_bad_url, now_jst,
)

JSON_PATH = "/Users/masakatsu/Desktop/kyujin_box_rpa/top500_companies.json"


def load():
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(rows):
    tmp = JSON_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, JSON_PATH)


def main():
    check_maintenance_window()
    rows = load()

    # 未取得（空欄）と、誤マッチが残っている行を対象にする
    targets = [r for r in rows if not r.get("公式HP") or is_bad_url(r.get("公式HP", ""))]
    done = len(rows) - len(targets)
    print(f"全{len(rows)}社 / 取得済み{done}社 / これから{len(targets)}社を処理", flush=True)

    if not targets:
        print("処理対象なし", flush=True)
        return

    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        verify_page = new_page(browser)
        verify_page.set_default_timeout(15000)

        for i, r in enumerate(targets, 1):
            name = r["事業主名称"]
            try:
                hp = find_official_site(
                    browser, verify_page, name, r.get("本社所在地", ""), r.get("電話", "")
                )
            except Exception as e:
                print(f"[{i}/{len(targets)}] {name[:26]} -> エラー: {str(e)[:50]}", flush=True)
                continue

            if hp and is_bad_url(hp):
                hp = ""
            r["公式HP"] = hp
            r["取得日時"] = now_jst()
            save(rows)

            got = len([x for x in rows if x.get("公式HP")])
            el = time.time() - t0
            eta = (el / i) * (len(targets) - i) / 60
            print(f"[{i}/{len(targets)}] {name[:26]:<28} -> {hp[:52] if hp else '(なし)'}"
                  f"  [計{got}/{len(rows)} 残り約{eta:.0f}分]", flush=True)

        browser.close()

    got = len([x for x in rows if x.get("公式HP")])
    print(f"\n===== HP取得完了 =====", flush=True)
    print(f"{len(rows)}社中 {got}社 取得 ({100*got//max(len(rows),1)}%)", flush=True)


if __name__ == "__main__":
    main()

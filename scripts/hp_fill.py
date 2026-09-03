# -*- coding: utf-8 -*-
"""企業リストJSONに公式HPを付与する汎用スクリプト。

  python3 hp_fill.py <json_path> [上位N社のみ]

- 1社ごとにJSONへ即時保存するので中断・再開が可能
- 既に入っている値が誤マッチ判定に該当する場合は空にして再取得する
- 見つからなければ空欄のまま（誤ったURLを載せない方針）
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


def addr_of(r):
    for k in ("本社所在地", "所在地", "事業所所在地"):
        if r.get(k):
            return r[k]
    return ""


def main():
    if len(sys.argv) < 2:
        print("usage: hp_fill.py <json_path> [top_n]")
        sys.exit(1)
    path = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else None

    check_maintenance_window()

    with open(path, encoding="utf-8") as f:
        rows = json.load(f)

    scope = rows[:top_n] if top_n else rows
    targets = [r for r in scope if not r.get("公式HP") or is_bad_url(r.get("公式HP", ""))]
    got0 = len([r for r in scope if r.get("公式HP") and not is_bad_url(r["公式HP"])])
    print(f"対象{len(scope)}社 / 取得済み{got0}社 / これから{len(targets)}社", flush=True)
    if not targets:
        print("処理対象なし")
        return

    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        vp = new_page(browser)
        vp.set_default_timeout(15000)

        for i, r in enumerate(targets, 1):
            name = r.get("事業主名称", "")
            try:
                hp = find_official_site(browser, vp, name, addr_of(r), r.get("電話", ""))
            except Exception as e:
                print(f"[{i}/{len(targets)}] {name[:24]} -> エラー {str(e)[:40]}", flush=True)
                continue
            if hp and is_bad_url(hp):
                hp = ""
            r["公式HP"] = hp
            r["取得日時"] = now_jst()

            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)

            got = len([x for x in scope if x.get("公式HP")])
            el = time.time() - t0
            eta = (el / i) * (len(targets) - i) / 60
            print(f"[{i}/{len(targets)}] {name[:24]:<26} -> {hp[:46] if hp else '(なし)'}"
                  f"  [計{got}/{len(scope)} 残り約{eta:.0f}分]", flush=True)

        browser.close()

    got = len([x for x in scope if x.get("公式HP")])
    print(f"\n===== 完了: {got}/{len(scope)} ({100*got//max(len(scope),1)}%) =====", flush=True)


if __name__ == "__main__":
    main()

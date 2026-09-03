# -*- coding: utf-8 -*-
"""D順(就職者数4ヶ月以上)TOP500の新規158社: HP検索→問い合わせフォーム取得。
進捗は .d500.json に1社ずつ保存(中断再開可)。"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from jinzai_common import UA_POOL, new_page, find_official_site, is_bad_url
from nagekomi_forms import find_form

BASE = "/Users/masakatsu/Desktop/kyujin_box_rpa"
NEW = os.path.join(BASE, "top500_yuki_new.json")
PROG = os.path.join(BASE, ".d500.json")

def main():
    new = json.load(open(NEW, encoding="utf-8"))
    prog = json.load(open(PROG, encoding="utf-8")) if os.path.exists(PROG) else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg_ctx = browser.new_context(user_agent=UA_POOL[0], locale="ja-JP", ignore_https_errors=True)
        pg = pg_ctx.new_page(); pg.set_default_timeout(15000)
        vp = new_page(browser); vp.set_default_timeout(15000)
        t0 = time.time(); done = 0
        for x in new:
            lic = x["許可番号"]
            if lic in prog:
                continue
            name = x["事業主名称"]
            # 個人名(スペース区切りの姓名のみ等)はHP検索対象外
            if re.fullmatch(r"[一-龥ぁ-んァ-ヴー]{1,6}[\s　]+[一-龥ぁ-んァ-ヴー]{1,6}", name):
                prog[lic] = {"name": name, "hp": "", "form": "", "note": "個人事業主"}
                json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                continue
            hp = ""
            try:
                hit = find_official_site(browser, vp, name, x.get("本社所在地", ""), x.get("電話", ""))
            except Exception:
                hit = ""
            if hit and not is_bad_url(hit):
                hp = hit
            form, note = ("", "HPなし")
            if hp:
                try:
                    form, note = find_form(pg, hp)
                except Exception:
                    form, note = "", "エラー"
            prog[lic] = {"name": name, "hp": hp, "form": form, "note": note}
            json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            done += 1
            rem = sum(1 for y in new if y["許可番号"] not in prog)
            eta = (time.time() - t0) / done * rem / 60
            print(f"[{done}] {name[:22]:<24} HP:{'○' if hp else '×'} form:{'○' if form else '×'} {note:<10} 残り約{eta:.0f}分", flush=True)
        browser.close()
    from collections import Counter
    print("完了:", Counter(("HP有" if v["hp"] else "HP無") for v in prog.values()),
          Counter(("form有" if v["form"] else "form無") for v in prog.values()))


if __name__ == "__main__":
    main()

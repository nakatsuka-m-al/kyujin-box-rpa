# -*- coding: utf-8 -*-
"""労働者派遣事業の全事業所を一覧スキャンし、許可番号で企業単位に集約する。

派遣は職業紹介と違い一覧に並び替え機能が無く、規模の指標（派遣労働者数）も
詳細ページにしか無い。そこで一覧に出る情報だけで完結させる:
  - 拠点数（許可番号ごとの事業所数）= 規模の代理指標。これで順位付けする
  - マージン率 / 派遣料金の平均額 / 賃金の平均額 = 拠点平均を属性として付与
数字は事業所ごとで欠測もあるため、記載のある拠点だけで平均し、
記載拠点数も残して信頼度が分かるようにする。

途中経過を逐次保存し、中断しても再開できる。
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from jinzai_common import check_maintenance_window, new_page, now_jst

TOP = "https://jinzai.hellowork.mhlw.go.jp/JinzaiWeb/GICB101010.do?action=initDisp&screenId=GICB101010"
OUT_JSON = "/Users/masakatsu/Desktop/kyujin_box_rpa/haken_companies.json"
STATE_JSON = "/Users/masakatsu/Desktop/kyujin_box_rpa/.haken_scan_state.json"

START_PAGE = int(os.environ.get("START_PAGE", "1"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3000"))


def open_haken_list(page, nationwide=True):
    """派遣事業の検索を実行し、一覧ページを開く。総件数を返す"""
    page.goto(TOP, timeout=25000)
    page.wait_for_timeout(1200)
    with page.expect_navigation(timeout=20000):
        page.evaluate("doPostAction('transition','0')")  # 労働者派遣事業検索へ
    page.wait_for_timeout(1200)
    page.check("#ID_cbZenkoku1" if nationwide else "#ID_cbTokyo1")
    page.check("#ID_cbJigyoshoKbnHan1")  # 区分: 労働者派遣事業
    page.wait_for_timeout(200)
    with page.expect_navigation(timeout=20000):
        page.locator("#id_btnSearch").nth(1).click()
    page.wait_for_timeout(2000)
    text = page.inner_text("body")
    m = re.search(r"検索結果\s*([\d,]+)\s*件", text)
    return int(m.group(1).replace(",", "")) if m else None


def goto_page(page, n):
    with page.expect_navigation(timeout=20000):
        page.evaluate(f"doPostAction('page','{n}')")
    page.wait_for_timeout(600)


def _money(s):
    s = (s or "").split("\n")[0].replace(",", "").replace("円", "").strip()
    return int(s) if re.fullmatch(r"\d+", s) else None


def _pct(s):
    s = (s or "").split("\n")[0].replace("％", "").replace("%", "").strip()
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def grab_haken_rows(page):
    """派遣一覧の各行を構造化。列は
    [0]許可番号/日付 [1]事業主名/事業所名 [2]所在地/電話 [3]派遣料金 [4]賃金 [5]マージン率 [6]労使協定"""
    raw = page.evaluate("""
    () => {
        let out = [], seen = new Set();
        document.querySelectorAll('a[href*="action=detail"]').forEach(a => {
            let lic = a.innerText.trim();
            if (!lic) return;
            let tr = a.closest('tr');
            if (!tr) return;
            let cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText);
            let key = lic + '||' + (cells[1] || '');
            if (seen.has(key)) return;
            seen.add(key);
            out.push(cells);
        });
        return out;
    }
    """)
    rows = []
    for c in raw:
        if len(c) < 6:
            continue
        c0 = [x.strip() for x in c[0].split("\n") if x.strip()]
        c1 = [x.strip() for x in c[1].split("\n") if x.strip()]
        c2 = [x.strip() for x in c[2].split("\n") if x.strip()]
        rows.append({
            "許可番号": c0[0] if c0 else "",
            "許可年月日": c0[1] if len(c0) > 1 else "",
            "事業主名称": c1[0] if c1 else "",
            "事業所名称": c1[1] if len(c1) > 1 else (c1[0] if c1 else ""),
            "所在地": c2[0] if c2 else "",
            "電話": c2[1] if len(c2) > 1 else "",
            "派遣料金": _money(c[3]),
            "賃金": _money(c[4]),
            "マージン率": _pct(c[5]),
        })
    return rows


def merge(companies, rows):
    for r in rows:
        lic = r["許可番号"]
        if not lic:
            continue
        co = companies.get(lic)
        if co is None:
            co = companies[lic] = {
                "許可番号": lic,
                "許可年月日": r["許可年月日"],
                "事業主名称": r["事業主名称"],
                "本社所在地": r["所在地"],
                "電話": r["電話"],
                "拠点数": 0,
                "_margin": [], "_fee": [], "_wage": [],
                "公式HP": "",
            }
        co["拠点数"] += 1
        # 事業所名 == 事業主名 の行を本社とみなして代表の住所・電話にする
        if r["事業所名称"] == r["事業主名称"] and r["所在地"]:
            co["本社所在地"] = r["所在地"]
            co["電話"] = r["電話"] or co["電話"]
        for key, val in (("_margin", r["マージン率"]), ("_fee", r["派遣料金"]), ("_wage", r["賃金"])):
            if val is not None:
                co[key].append(val)


def finalize(companies):
    out = []
    for co in companies.values():
        m, f, w = co.pop("_margin"), co.pop("_fee"), co.pop("_wage")
        co["マージン率_平均"] = round(sum(m) / len(m), 1) if m else None
        co["派遣料金_平均"] = round(sum(f) / len(f)) if f else None
        co["賃金_平均"] = round(sum(w) / len(w)) if w else None
        co["記載のある拠点数"] = len(m)
        co["取得日時"] = now_jst()
        out.append(co)
    out.sort(key=lambda x: (-x["拠点数"], -(x["記載のある拠点数"])))
    for i, co in enumerate(out, 1):
        co["順位"] = i
    return out


def main():
    check_maintenance_window()

    companies = {}
    start_page = START_PAGE
    if os.path.exists(STATE_JSON):
        try:
            st = json.load(open(STATE_JSON, encoding="utf-8"))
            companies = st["companies"]
            for co in companies.values():
                for k in ("_margin", "_fee", "_wage"):
                    co.setdefault(k, [])
            start_page = st["next_page"]
            print(f"[再開] {len(companies)}社 / ページ{start_page}から", flush=True)
        except Exception as e:
            print(f"[再開失敗] {e} — 最初から", flush=True)
            companies, start_page = {}, 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = new_page(browser)

        total = open_haken_list(page, nationwide=True)
        last_page = (total + 19) // 20
        print(f"派遣・全国: {total:,}事業所 = {last_page:,}ページ", flush=True)

        if start_page > 1:
            goto_page(page, start_page)

        t0 = time.time()
        pnum = start_page
        while pnum <= min(last_page, MAX_PAGES):
            if pnum > start_page:
                try:
                    goto_page(page, pnum)
                except Exception as e:
                    print(f"  p{pnum} 送り失敗: {str(e)[:50]} — 再確立", flush=True)
                    try:
                        open_haken_list(page, nationwide=True)
                        goto_page(page, pnum)
                    except Exception as e2:
                        print(f"  再確立失敗: {str(e2)[:50]} — 中断（次回ここから再開）", flush=True)
                        break

            try:
                rows = grab_haken_rows(page)
            except Exception as e:
                print(f"  p{pnum} 取得失敗: {str(e)[:50]} — スキップ", flush=True)
                rows = []
            if not rows and pnum < last_page:
                print(f"  p{pnum} 行なし。中断", flush=True)
                break
            merge(companies, rows)

            if pnum % 50 == 0 or pnum == last_page:
                el = time.time() - t0
                done = pnum - start_page + 1
                eta = (el / max(done, 1)) * (min(last_page, MAX_PAGES) - pnum) / 60
                print(f"  p{pnum}/{last_page}  企業{len(companies):,}社  "
                      f"経過{el/60:.0f}分 残り約{eta:.0f}分", flush=True)
                json.dump({"companies": companies, "next_page": pnum + 1},
                          open(STATE_JSON, "w", encoding="utf-8"), ensure_ascii=False)
            pnum += 1

        browser.close()

    result = finalize(companies)
    json.dump(result, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if os.path.exists(STATE_JSON):
        os.remove(STATE_JSON)

    print(f"\n===== スキャン完了 =====", flush=True)
    print(f"企業数: {len(result):,}社", flush=True)
    print(f"出力: {OUT_JSON}", flush=True)
    for co in result[:10]:
        print(f"  {co['順位']:>3}. {co['事業主名称'][:28]:<30} 拠点{co['拠点数']:>4}  "
              f"マージン{co['マージン率_平均']}%", flush=True)


if __name__ == "__main__":
    main()

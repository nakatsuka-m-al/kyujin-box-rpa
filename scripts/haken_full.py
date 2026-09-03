# -*- coding: utf-8 -*-
"""労働者派遣事業の全事業所について、詳細ページまで取得して企業単位に集約する。

一覧ページには派遣労働者数が無く、詳細ページにしか載っていない。
拠点数だけでは「1拠点で1,500人派遣している会社」を取りこぼすため、
全45,049事業所の詳細を取得して両方の指標を持たせる。

  拠点数        … 事業所の数（許可番号ごと）
  派遣労働者数  … 実数。公開している事業所のぶんを合計
  公開拠点数    … 実数を公開している事業所の数（＝合計値の信頼度）

一覧用と詳細用でページを分ける（同じタブで詳細に飛ぶと一覧のJS関数が失われるため）。
50ページごとに途中保存し、中断しても再開できる。
"""
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from jinzai_common import check_maintenance_window, new_page, now_jst
from haken_scan import open_haken_list, goto_page

BASE = "https://jinzai.hellowork.mhlw.go.jp/JinzaiWeb/"
OUT_JSON = "/Users/masakatsu/Desktop/kyujin_box_rpa/haken_full.json"
STATE_JSON = "/Users/masakatsu/Desktop/kyujin_box_rpa/.haken_full_state.json"

MAX_PAGES = int(os.environ.get("MAX_PAGES", "3000"))


def _int(m):
    return int(m.group(1).replace(",", "")) if m else None


def parse_detail(text):
    """詳細ページのテキストから必要な項目を抜き出す"""
    def field(label):
        m = re.search(re.escape(label) + r"\s*([^\n]*)", text)
        return m.group(1).strip() if m else ""

    return {
        "事業主名称": field("事業主名称"),
        "事業所名称": field("事業所名称"),
        "所在地": field("事業所所在地"),
        "電話": field("電話番号"),
        "許可年月日": field("許可届出受理年月日"),
        "得意職種": field("得意とする職種"),
        "派遣労働者数": _int(re.search(r"派遣労働者数\s*([\d,]+)\s*人", text)),
        "派遣先件数": _int(re.search(r"派遣先件数）\s*([\d,]+)\s*件", text)),
        "派遣料金": _int(re.search(r"派遣料金の平均額\s*([\d,]+)\s*円", text)),
        "賃金": _int(re.search(r"賃金の平均額\s*([\d,]+)\s*円", text)),
        "マージン率": (lambda m: float(m.group(1)) if m else None)(
            re.search(r"マージン率\s*([\d.]+)\s*％", text)),
    }


def merge(companies, lic, d):
    co = companies.get(lic)
    if co is None:
        co = companies[lic] = {
            "許可番号": lic,
            "許可年月日": d["許可年月日"],
            "事業主名称": d["事業主名称"],
            "本社所在地": d["所在地"],
            "電話": d["電話"],
            "得意職種": d["得意職種"],
            "拠点数": 0,
            "公開拠点数": 0,
            "派遣労働者数": 0,
            "派遣先件数": 0,
            "_fee": [], "_wage": [], "_margin": [],
            "公式HP": "",
        }
    co["拠点数"] += 1
    # 事業所名 == 事業主名 の行を本社とみなして代表情報にする
    if d["事業所名称"] == d["事業主名称"] and d["所在地"]:
        co["本社所在地"] = d["所在地"]
        co["電話"] = d["電話"] or co["電話"]
    if d["得意職種"] and not co["得意職種"]:
        co["得意職種"] = d["得意職種"]
    if d["派遣労働者数"] is not None:
        co["公開拠点数"] += 1
        co["派遣労働者数"] += d["派遣労働者数"]
    if d["派遣先件数"] is not None:
        co["派遣先件数"] += d["派遣先件数"]
    for k, v in (("_fee", d["派遣料金"]), ("_wage", d["賃金"]), ("_margin", d["マージン率"])):
        if v is not None:
            co[k].append(v)


def finalize(companies):
    out = []
    for co in companies.values():
        f, w, m = co.pop("_fee"), co.pop("_wage"), co.pop("_margin")
        co["派遣料金_平均"] = round(sum(f) / len(f)) if f else None
        co["賃金_平均"] = round(sum(w) / len(w)) if w else None
        co["マージン率_平均"] = round(sum(m) / len(m), 1) if m else None
        if co["公開拠点数"] == 0:
            co["派遣労働者数"] = None      # 未公開と 0人 を区別する
            co["派遣先件数"] = None
        co["取得日時"] = now_jst()
        out.append(co)
    out.sort(key=lambda x: (-(x["派遣労働者数"] or -1), -x["拠点数"]))
    for i, co in enumerate(out, 1):
        co["派遣労働者数順位"] = i
    return out


def main():
    check_maintenance_window()

    companies, start_page = {}, 1
    if os.path.exists(STATE_JSON):
        try:
            st = json.load(open(STATE_JSON, encoding="utf-8"))
            companies = st["companies"]
            for co in companies.values():
                for k in ("_fee", "_wage", "_margin"):
                    co.setdefault(k, [])
            start_page = st["next_page"]
            print(f"[再開] {len(companies):,}社 / ページ{start_page}から", flush=True)
        except Exception as e:
            print(f"[再開失敗] {e} — 最初から", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        lst = new_page(browser)      # 一覧用
        det = new_page(browser)      # 詳細用
        det.set_default_timeout(20000)

        total = open_haken_list(lst, nationwide=True)
        last_page = (total + 19) // 20
        print(f"派遣・全国 {total:,}事業所 / {last_page:,}ページ", flush=True)

        if start_page > 1:
            goto_page(lst, start_page)

        t0 = time.time()
        seen_details = 0
        pnum = start_page
        while pnum <= min(last_page, MAX_PAGES):
            if pnum > start_page:
                try:
                    goto_page(lst, pnum)
                except Exception as e:
                    print(f"  p{pnum} 送り失敗: {str(e)[:50]} — 再確立", flush=True)
                    try:
                        open_haken_list(lst, nationwide=True)
                        goto_page(lst, pnum)
                    except Exception as e2:
                        print(f"  再確立失敗: {str(e2)[:50]} — 中断（次回ここから）", flush=True)
                        break

            try:
                rows = lst.evaluate("""
                () => { let s=new Set(), o=[];
                    document.querySelectorAll('a[href*="action=detail"]').forEach(a => {
                        let l = a.innerText.trim();
                        let h = a.getAttribute('href');
                        if (!l || !h) return;
                        let k = l + '|' + h;
                        if (s.has(k)) return; s.add(k);
                        o.push([l, h]); });
                    return o; }
                """)
            except Exception as e:
                print(f"  p{pnum} 一覧取得失敗: {str(e)[:50]}", flush=True)
                rows = []

            for lic, href in rows:
                try:
                    det.goto(BASE + href.lstrip("./"), timeout=20000)
                    det.wait_for_timeout(random.randint(150, 350))
                    d = parse_detail(det.inner_text("body"))
                except Exception:
                    continue
                seen_details += 1
                merge(companies, lic, d)

            if pnum % 50 == 0 or pnum == last_page:
                el = time.time() - t0
                done = pnum - start_page + 1
                eta = (el / max(done, 1)) * (min(last_page, MAX_PAGES) - pnum) / 3600
                withnum = len([c for c in companies.values() if c["公開拠点数"] > 0])
                print(f"  p{pnum}/{last_page}  事業所{seen_details:,}  企業{len(companies):,}社 "
                      f"(実数あり{withnum:,}社)  経過{el/3600:.1f}h 残り約{eta:.1f}h", flush=True)
                json.dump({"companies": companies, "next_page": pnum + 1},
                          open(STATE_JSON, "w", encoding="utf-8"), ensure_ascii=False)
            pnum += 1

        browser.close()

    result = finalize(companies)
    json.dump(result, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if os.path.exists(STATE_JSON):
        os.remove(STATE_JSON)

    withnum = [c for c in result if c["派遣労働者数"] is not None]
    print(f"\n===== 完了 =====", flush=True)
    print(f"企業数 {len(result):,}社 / 派遣労働者数の実数あり {len(withnum):,}社", flush=True)
    print(f"出力: {OUT_JSON}", flush=True)
    for co in withnum[:15]:
        print(f"  {co['派遣労働者数']:>6}人  拠点{co['拠点数']:>3}  {co['事業主名称'][:28]}", flush=True)


if __name__ == "__main__":
    main()

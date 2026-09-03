# -*- coding: utf-8 -*-
"""派遣KBリスト（サイト名/会社名 11,539行）に 会社名・会社HP・派遣番号 を付与する。

ステージ構成（kb_resolution.json に解決結果を逐次保存、再開可能）:
  A: A列が会社名の行 → 全国派遣許可DB(haken_full.json 36,226社)と正規化マッチ
     - 部署・支店等の装飾を段階的に剥がしながら照合
     - 同名別会社（許可番号が複数）は誤記入を避けるため空欄+注記
  B: A列がサービス名の行 → ブランド名がそのまま会社名に一致するか照合
  C: 残るサービス名 → Yahoo検索「◯◯ 運営会社」のSERPテキストから
     運営会社候補を抽出し、許可DBと照合（サービス名と同一スニペットに
     現れた会社名のみ候補とする）
  D: 派遣番号が付いた行のHP補完（既存データ流用 → 検索）
  E: 出力xlsx生成

usage: kb_pipeline.py <stage>   (stage = ab | c | d | e | report)
"""
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jinzai_common import normalize_name

BASE_DIR = "/Users/masakatsu/Desktop/kyujin_box_rpa"
XLSX_IN = "/Users/masakatsu/Downloads/派遣KBリスト.xlsx"
XLSX_OUT = os.path.join(BASE_DIR, "派遣KBリスト_付与済み.xlsx")
RESO_PATH = os.path.join(BASE_DIR, ".kb_resolution.json")
DB_PATH = os.path.join(BASE_DIR, "haken_full.json")

CORP_PAT = re.compile(r"株式会社|有限会社|合同会社|合資会社|協同組合|\(株\)|（株）|\(有\)|（有）|法人")

DEPT_SUFFIXES = (
    "人事総務法務部|人事部|人事課|人事グループ|採用担当|採用係|採用グループ|採用チーム|"
    "採用受付|採用窓口|総務部|総務課|管理部|管理本部|本社|本部|事業本部|"
    "人材開発部|人事戦略室|採用センター|採用事務局"
)
BRANCH_SUFFIXES = r"支社|支店|営業所|事業所|事業部|工場|営業部|オフィス|センター"


def load_db():
    db = json.load(open(DB_PATH, encoding="utf-8"))
    idx = {}
    for r in db:
        k = normalize_name(r["事業主名称"])
        idx.setdefault(k, []).append(r)
    return db, idx


def load_reso():
    if os.path.exists(RESO_PATH):
        return json.load(open(RESO_PATH, encoding="utf-8"))
    return {}


def save_reso(reso):
    tmp = RESO_PATH + ".tmp"
    json.dump(reso, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, RESO_PATH)


def load_rows():
    import openpyxl
    wb = openpyxl.load_workbook(XLSX_IN, read_only=True)
    ws = wb.worksheets[0]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is not None and str(r[0]).strip():
            rows.append(str(r[0]).strip())
    return rows


def company_variants(s):
    """会社名の照合候補を、装飾を剥がしながら生成する（先頭が最優先）"""
    s = str(s).strip()
    out = [s]
    t = re.sub(r"[\s　]*[-−–ー―][\s　]*[^-−–ー―]+$", "", s).strip()  # "X - 人事部"
    if t and t != s:
        out.append(t)
    t = re.sub(r"[_＿].+$", "", s).strip()                              # "X_繊維事業部"
    if t and t != s:
        out.append(t)
    t = re.sub(rf"[\s　]*({DEPT_SUFFIXES})$", "", s).strip()            # "X人事部"
    if t and t != s:
        out.append(t)
    t = re.sub(rf"[\s　]+[^\s　]*({BRANCH_SUFFIXES})$", "", s).strip()  # "X 上野支社"
    if t and t != s:
        out.append(t)
    # 装飾を全部まとめて剥がした形
    t = s
    for pat in (r"[\s　]*[-−–ー―][\s　]*[^-−–ー―]+$", r"[_＿].+$",
                rf"[\s　]*({DEPT_SUFFIXES})$", rf"[\s　]*[^\s　]*({BRANCH_SUFFIXES})$"):
        t = re.sub(pat, "", t).strip()
    if t and t not in out:
        out.append(t)
    return out


def clean_service(s):
    s = str(s).strip()
    s = re.sub(r"[\s　]*[-−–ー―]?[\s　]*登録エントリー.*$", "", s)
    s = re.sub(r"[.．]+$", "", s)
    return s.strip()


def match_license(idx, name):
    """正規化名でDBを引く。(status, record) を返す。
    ambiguous = 同名で許可番号が複数（誤記入防止のため採用しない）"""
    k = normalize_name(name)
    if not k or len(k) < 2:
        return "none", None
    cands = idx.get(k)
    if not cands:
        return "none", None
    lics = {c["許可番号"] for c in cands}
    if len(lics) == 1:
        best = max(cands, key=lambda c: c.get("公開拠点数") or 0)
        return "ok", best
    return "ambiguous", None


def make_entry(status, rec=None, method="", note=""):
    e = {"status": status, "method": method, "note": note,
         "会社名": "", "会社HP": "", "派遣番号": ""}
    if rec:
        e["会社名"] = rec["事業主名称"]
        e["派遣番号"] = rec["許可番号"]
        e["会社HP"] = rec.get("公式HP", "") or ""
    return e


# ---------------------------------------------------------------- stage A+B

def stage_ab():
    db, idx = load_db()
    reso = load_reso()
    rows = load_rows()
    uniq = list(dict.fromkeys(rows))
    print(f"ユニーク {len(uniq):,}件 / DB {len(db):,}社", flush=True)

    n_ok = n_amb = n_none = n_svc = 0
    for raw in uniq:
        if raw in reso:
            continue
        if CORP_PAT.search(raw):
            st, rec = "none", None
            for v in company_variants(raw):
                st, rec = match_license(idx, v)
                if st == "ok":
                    reso[raw] = make_entry("matched", rec, "A:会社名ローカル一致")
                    n_ok += 1
                    break
                if st == "ambiguous":
                    reso[raw] = make_entry("ambiguous", None, "A:同名複数社",
                                           "同名の許可事業者が複数あり特定不可")
                    n_amb += 1
                    break
            if st == "none":
                reso[raw] = make_entry("no_license", None, "A:許可DBに無し")
                n_none += 1
        else:
            svc = clean_service(raw)
            st, rec = match_license(idx, svc)
            if st == "ok":
                reso[raw] = make_entry("matched", rec, "B:ブランド名一致")
                n_ok += 1
            elif st == "ambiguous":
                reso[raw] = make_entry("ambiguous", None, "B:同名複数社",
                                       "同名の許可事業者が複数あり特定不可")
                n_amb += 1
            else:
                reso[raw] = {"status": "pending_service", "method": "", "note": "",
                             "会社名": "", "会社HP": "", "派遣番号": ""}
                n_svc += 1
    save_reso(reso)
    print(f"一致 {n_ok:,} / 同名複数 {n_amb:,} / 許可なし {n_none:,} / サービス名(次段へ) {n_svc:,}",
          flush=True)


# ---------------------------------------------------------------- stage C

CORP_NAME_PAT = re.compile(
    r"(株式会社[\w一-龥ぁ-んァ-ヴーА-я・＆&．.\-]{1,20}|"
    r"[\w一-龥ぁ-んァ-ヴー・＆&．.\-]{1,20}株式会社|"
    r"有限会社[\w一-龥ぁ-んァ-ヴー・＆&．.\-]{1,20}|"
    r"合同会社[\w一-龥ぁ-んァ-ヴー・＆&．.\-]{1,20}|"
    r"[\w一-龥ぁ-んァ-ヴー・＆&．.\-]{1,20}合同会社)"
)

STOP_CORP = {"株式会社リクルート"}  # 求人ボックス運営元。SERPに頻出するため既定では除外しない判断も可


def stage_c():
    from playwright.sync_api import sync_playwright
    from jinzai_common import UA_POOL

    db, idx = load_db()
    reso = load_reso()
    targets = [k for k, v in reso.items() if v["status"] == "pending_service"]
    print(f"サービス名の運営会社調査: {len(targets):,}件", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        serp_text = make_serp_fetcher(browser)

        done = 0
        consecutive_fail = 0
        t0 = time.time()
        for raw in targets:
            svc = clean_service(raw)
            svc_key = normalize_name(svc)
            text = serp_text(f"{svc} 運営会社")
            time.sleep(random.uniform(12, 20))
            if text is None:
                consecutive_fail += 1
                done += 1
                if consecutive_fail >= 3:
                    print("  連続ブロックのため中断（未処理分は次回再開）", flush=True)
                    break
                continue
            consecutive_fail = 0

            # サービス名が近く(同じ行塊)に出る会社名を候補にし、
            # 「運営」等の文脈があるブロックを強く加点する。
            # 重要: 許可の有無で候補を選んではいけない（真の運営会社が許可なしのとき、
            # 無関係な許可保有社を掴む誤りが起きる）。まず運営会社を1社決め、
            # その会社の許可を確認する。
            cands = {}
            for blk in re.split(r"\n+", text):
                if not (svc and (svc in blk or (svc_key and len(svc_key) >= 3
                                                and svc_key in normalize_name(blk)))):
                    continue
                bonus = 4 if re.search(r"運営会社|運営元|が運営|運営する|提供元", blk) else 1
                for m in CORP_NAME_PAT.findall(blk):
                    key = normalize_name(m)
                    if not key or key == svc_key:
                        continue
                    cands.setdefault(key, {"name": m, "score": 0})
                    cands[key]["score"] += bonus

            if not cands:
                reso[raw] = make_entry("no_license", None, "C:運営会社検索",
                                       "運営会社を特定できず")
            else:
                ranked = sorted(cands.values(), key=lambda x: -x["score"])
                top = ranked[0]
                # 僅差の2位は同点扱い（どちらか一意に許可があれば採用）
                tops = [r_ for r_ in ranked if r_["score"] >= max(top["score"] - 1, 2)][:2]
                if top["score"] < 2:
                    tops = [top]  # 根拠が弱い場合は筆頭のみ
                hit = None
                for cand in tops:
                    st, rec = match_license(idx, cand["name"])
                    if st == "ok":
                        hit = (cand, rec)
                        break
                if hit and tops.index(hit[0]) == 0:
                    reso[raw] = make_entry("matched", hit[1], "C:運営会社検索",
                                           f"運営会社: {hit[0]['name'][:24]}")
                elif hit:
                    # 2位候補での一致は根拠が弱いので採用せず記録のみ
                    reso[raw] = make_entry("no_license", None, "C:運営会社検索",
                                           f"次点候補{hit[0]['name'][:20]}に許可(未採用)")
                else:
                    reso[raw] = make_entry("no_license", None, "C:運営会社検索",
                                           f"運営会社:{top['name'][:22]}(許可なし)")
            done += 1
            if done % 25 == 0:
                el = time.time() - t0
                eta = (el / done) * (len(targets) - done) / 60
                ok = len([1 for k in targets[:done] if reso[k]["status"] == "matched"])
                print(f"  {done}/{len(targets)}  一致{ok}  残り約{eta:.0f}分", flush=True)
                save_reso(reso)
        browser.close()
    save_reso(reso)
    ok = len([1 for k in targets if reso[k]["status"] == "matched"])
    print(f"完了: {len(targets)}件中 運営会社の許可一致 {ok}件", flush=True)




BLOCK_MARKERS = ["現在表示できません", "captcha", "verify you are human",
                 "unusual traffic", "続行するには", "問題が発生しました"]


def make_serp_fetcher(browser):
    """SERPテキスト取得。ブロックを検知したら None を返す（誤分類を防ぐ）。
    Yahooがブロック中のため Bing を主エンジンにする。"""
    from jinzai_common import UA_POOL

    def fetch(query):
        for attempt in range(2):
            ctx = browser.new_context(user_agent=random.choice(UA_POOL), locale="ja-JP")
            pg = ctx.new_page()
            pg.set_default_timeout(20000)
            try:
                pg.goto("https://www.bing.com/search?q=" + query, timeout=20000)
                pg.wait_for_timeout(2300)
                text = pg.inner_text("body")
            except Exception:
                text = ""
            finally:
                ctx.close()
            low = (text or "").lower()
            blocked = (len(text) < 700) or any(m in low or m in text for m in BLOCK_MARKERS)
            if not blocked and "件の結果" not in text and "結果はありません" not in text and len(text) < 1500:
                blocked = True
            if not blocked:
                return text
            if attempt == 0:
                print("    [ブロック検知] 120秒待機して再試行", flush=True)
                time.sleep(120)
        return None

    return fetch


# ---------------------------------------------------------------- stage AMB

LIC_PAT = re.compile(r"派\s*([0-9０-９]{2})\s*[-−ー–]\s*([0-9０-９]{6})")


def _z2h(s):
    return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def stage_amb():
    """同名複数社の解決: Web上に掲載された派遣許可番号を検索し、
    候補企業の番号と一致したものだけ採用する（自己申告番号との突合なので確実）"""
    from playwright.sync_api import sync_playwright
    from jinzai_common import UA_POOL

    db, idx = load_db()
    reso = load_reso()
    targets = [k for k, v in reso.items() if v["status"] == "ambiguous"]
    print(f"同名複数社の解決: {len(targets)}件", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        serp_text = make_serp_fetcher(browser)

        done = resolved = 0
        consecutive_fail = 0
        t0 = time.time()
        for raw in targets:
            # 候補ライセンス集合
            name = None
            for v_ in company_variants(raw):
                k = normalize_name(v_)
                if k in idx and len({c["許可番号"] for c in idx[k]}) > 1:
                    name = v_
                    cands = {c["許可番号"]: c for c in idx[k]}
                    break
            if name is None:
                k = normalize_name(clean_service(raw))
                if k in idx:
                    name = clean_service(raw)
                    cands = {c["許可番号"]: c for c in idx[k]}
                else:
                    done += 1
                    continue

            text = serp_text(f"{name} 労働者派遣事業 許可番号")
            time.sleep(random.uniform(12, 20))
            if text is None:
                consecutive_fail += 1
                if consecutive_fail >= 3:
                    print("  連続ブロックのため中断（未処理分は次回再開）", flush=True)
                    break
                continue
            consecutive_fail = 0
            found = {f"派{_z2h(m[0])}-{_z2h(m[1])}" for m in LIC_PAT.findall(text)}
            hits = [lic for lic in found if lic in cands]
            if len(hits) == 1:
                rec = cands[hits[0]]
                reso[raw] = make_entry("matched", rec, "AMB:許可番号突合",
                                       "Web掲載の許可番号と一致")
                resolved += 1
            done += 1
            if done % 20 == 0:
                el = time.time() - t0
                eta = (el / done) * (len(targets) - done) / 60
                print(f"  {done}/{len(targets)}  解決{resolved}  残り約{eta:.0f}分", flush=True)
                save_reso(reso)
        browser.close()
    save_reso(reso)
    print(f"完了: {len(targets)}件中 {resolved}件を許可番号突合で解決", flush=True)


# ---------------------------------------------------------------- stage D

def stage_d():
    from playwright.sync_api import sync_playwright
    from jinzai_common import new_page, find_official_site, is_bad_url

    reso = load_reso()

    # 既存の全データソースからHPを流用
    hp_by_lic = {}
    for path in ("haken_full.json", "haken_companies.json", "top500_companies.json"):
        fp = os.path.join(BASE_DIR, path)
        if os.path.exists(fp):
            for r in json.load(open(fp, encoding="utf-8")):
                lic = r.get("許可番号", "")
                hp = r.get("公式HP", "")
                if lic and hp and lic not in hp_by_lic:
                    hp_by_lic[lic] = hp
    reused = 0
    for v in reso.values():
        if v["status"] == "matched" and not v["会社HP"] and v["派遣番号"] in hp_by_lic:
            v["会社HP"] = hp_by_lic[v["派遣番号"]]
            reused += 1
    save_reso(reso)

    # 残りは検索（許可番号ベースで重複排除して1回ずつ）
    need = {}
    for v in reso.values():
        if v["status"] == "matched" and not v["会社HP"]:
            need.setdefault(v["派遣番号"], v["会社名"])
    print(f"HP流用 {reused}件 / これから検索 {len(need)}社", flush=True)

    db = json.load(open(DB_PATH, encoding="utf-8"))
    by_lic = {r["許可番号"]: r for r in db}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        vp = new_page(browser)
        vp.set_default_timeout(15000)
        done = 0
        t0 = time.time()
        for lic, name in need.items():
            rec = by_lic.get(lic, {})
            try:
                hp = find_official_site(browser, vp, name,
                                        rec.get("本社所在地", ""), rec.get("電話", ""))
            except Exception:
                hp = ""
            if hp and is_bad_url(hp):
                hp = ""
            if hp:
                for v in reso.values():
                    if v["status"] == "matched" and v["派遣番号"] == lic and not v["会社HP"]:
                        v["会社HP"] = hp
            done += 1
            if done % 20 == 0:
                el = time.time() - t0
                eta = (el / done) * (len(need) - done) / 3600
                print(f"  {done}/{len(need)}  ({name[:18]} -> {hp[:40] if hp else 'なし'})"
                      f"  残り約{eta:.1f}h", flush=True)
                save_reso(reso)
        browser.close()
    save_reso(reso)
    got = len({v["派遣番号"] for v in reso.values()
               if v["status"] == "matched" and v["会社HP"]})
    print(f"HP取得完了: 許可あり企業のうち {got}社にHP", flush=True)


# ---------------------------------------------------------------- stage E

def stage_e():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    reso = load_reso()
    rows = load_rows()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "派遣KBリスト"
    headers = ["サイト名", "会社名", "会社HP", "派遣番号", "備考"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.fill = PatternFill("solid", start_color="366092")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for i, raw in enumerate(rows, 2):
        v = reso.get(raw, {})
        ws.cell(row=i, column=1, value=raw)
        ws.cell(row=i, column=2, value=v.get("会社名", ""))
        hp = v.get("会社HP", "")
        if hp:
            c3 = ws.cell(row=i, column=3, value=hp)
            c3.hyperlink = hp
            c3.font = Font(color="0563C1", underline="single", name="Arial")
        else:
            ws.cell(row=i, column=3, value="")
        ws.cell(row=i, column=4, value=v.get("派遣番号", ""))
        ws.cell(row=i, column=5, value=v.get("note", ""))
    for col, w in zip("ABCDE", [38, 34, 42, 14, 30]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:E{len(rows)+1}"
    wb.save(XLSX_OUT)
    print(f"出力: {XLSX_OUT} ({len(rows):,}行)", flush=True)


def report():
    reso = load_reso()
    rows = load_rows()
    from collections import Counter
    st = Counter(reso.get(r, {}).get("status", "?") for r in rows)
    print("行ベース集計:", dict(st))
    filled = [r for r in rows if reso.get(r, {}).get("派遣番号")]
    hp = [r for r in rows if reso.get(r, {}).get("会社HP")]
    print(f"派遣番号あり: {len(filled):,}行 / HPあり: {len(hp):,}行 / 全{len(rows):,}行")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "ab"
    {"ab": stage_ab, "amb": stage_amb, "c": stage_c, "d": stage_d, "e": stage_e, "report": report}[stage]()

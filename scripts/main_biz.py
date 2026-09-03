# -*- coding: utf-8 -*-
"""投げ込みリスト統合版の「派遣番号あり」行について、人材派遣が主事業かをA/B/Cで判定する。

判定材料（優先順）:
  1. HPのトップ/会社概要/事業内容ページから「事業内容」を抽出し、派遣が筆頭か・明記されるかを見る
  2. グローバルナビ（メニュー）に派遣関連の独立項目があるか
  3. 社名の派遣系ワード、派遣労働者数（規模）を補助的に加点

区分:
  A: 派遣が主事業   B: 派遣も主要事業   C: 副次的/不明
根拠列に抽出テキストを残し、人が見直せるようにする。
1社ごとに保存し中断・再開可能。
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from playwright.sync_api import sync_playwright
from jinzai_common import UA_POOL

BASE = "/Users/masakatsu/Desktop/kyujin_box_rpa"
XLSX_IN = os.path.join(BASE, "投げ込みリスト_統合版.xlsx")
XLSX_OUT = os.path.join(BASE, "投げ込みリスト_統合版_主事業判定付き.xlsx")
PROGRESS = os.path.join(BASE, ".main_biz.json")

# 派遣を主事業とみなすキーワード群
HAKEN_CORE = ["人材派遣", "労働者派遣", "派遣事業", "派遣サービス", "一般労働者派遣", "特定労働者派遣",
              "紹介予定派遣", "技術者派遣", "技術派遣", "エンジニア派遣", "SES", "常駐", "製造派遣"]
HAKEN_ADJ = ["人材紹介", "有料職業紹介", "製造請負", "業務請負", "請負", "アウトソーシング",
             "業務委託", "人材サービス", "総合人材", "スタッフィング"]
# 派遣以外の本業を示す語（事業内容の筆頭にこれがあれば派遣は副次的）
OTHER_BIZ = ["製造", "加工", "建設", "工事", "設計", "運送", "運輸", "物流", "倉庫", "販売", "小売",
             "卸売", "不動産", "飲食", "介護施設", "医療", "警備", "清掃", "ビル管理", "保険代理",
             "システム開発", "ソフトウェア開発", "受託開発", "コンサルティング", "教育", "学習塾", "農業"]

NAME_HAKEN = re.compile(r"スタッフ|派遣|人材|ワーク|ジョブ|キャリア|ヒューマン|マンパワー|エージェント|"
                        r"リクルート|テクノ|エンジニアリング|アウトソーシング|クルー|staff|work|career|"
                        r"human|tech|engineer", re.I)

INFO_PATHS = ["", "/company", "/company/", "/about", "/about/", "/aboutus", "/corporate",
              "/business", "/service", "/services", "/company/business", "/company/service",
              "/profile", "/outline", "/company/outline", "/jigyou", "/gaiyou"]


def fetch_pages(browser, url):
    """トップ+会社概要/事業内容系ページを取り、(本文結合, ナビ項目) を返す"""
    ctx = browser.new_context(user_agent=UA_POOL[0], locale="ja-JP")
    pg = ctx.new_page()
    pg.set_default_timeout(15000)
    m = re.match(r"(https?://[^/]+)", url)
    origin = m.group(1) if m else url
    texts, navs = [], set()
    seen = set()
    try:
        # トップ
        try:
            pg.goto(url, timeout=15000)
            pg.wait_for_timeout(900)
            texts.append(pg.inner_text("body"))
            for t in pg.evaluate("() => Array.from(document.querySelectorAll('nav a, header a, [class*=menu] a, [class*=nav] a')).map(a=>a.innerText.trim()).filter(t=>t&&t.length<30)"):
                navs.add(t)
            # サイト内リンクから 事業/サービス/会社 系を発見
            links = pg.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a=>[a.getAttribute('href'), a.innerText.trim()])")
            for href, txt in links:
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                if re.search(r"事業|サービス|会社概要|企業情報|business|service|company|about|corporate", (href or "") + txt, re.I):
                    full = href if href.startswith("http") else origin + ("/" if not href.startswith("/") else "") + href
                    if full.startswith(origin) and full not in seen and len(seen) < 6:
                        seen.add(full)
        except Exception:
            pass
        # 発見リンク + 定型パス
        for cand in list(seen) + [origin + p for p in INFO_PATHS[1:]]:
            if len(texts) >= 6:
                break
            if cand.rstrip("/") == url.rstrip("/"):
                continue
            try:
                resp = pg.goto(cand, timeout=12000)
                if resp and resp.status < 400:
                    pg.wait_for_timeout(600)
                    t = pg.inner_text("body")
                    if len(t) > 200:
                        texts.append(t)
            except Exception:
                continue
    finally:
        ctx.close()
    return "\n".join(texts), navs


def extract_business(text):
    """『事業内容』『事業案内』等の見出し直後のテキストを抜く（複数箇所）"""
    out = []
    for m in re.finditer(r"(事業内容|事業概要|事業案内|主な事業|業務内容|事業紹介|サービス内容|Business|BUSINESS)[\s　:：\n]*([^\n]{0,60}(?:\n[^\n]{0,60}){0,6})", text):
        seg = m.group(2).strip()
        if seg:
            out.append(seg)
    return out


def classify(name, hp, worker_count, text, navs):
    """(区分, スコア, 根拠) を返す"""
    reasons = []
    score = 0
    biz_segs = extract_business(text) if text else []
    biz_join = " / ".join(s.replace("\n", " ")[:120] for s in biz_segs[:3])

    # 1) 事業内容の筆頭判定
    first_is_haken = first_is_other = False
    for seg in biz_segs:
        head = seg[:40]
        if any(k in head for k in HAKEN_CORE):
            first_is_haken = True
            break
        if any(k in head for k in OTHER_BIZ) and not any(k in head for k in HAKEN_CORE + HAKEN_ADJ):
            first_is_other = True
            break
    if first_is_haken:
        score += 40; reasons.append("事業内容の筆頭に派遣")
    elif first_is_other:
        score -= 15; reasons.append("事業内容の筆頭が他業種")

    # 2) 派遣語の出現密度
    core_hits = sum(text.count(k) for k in HAKEN_CORE) if text else 0
    adj_hits = sum(text.count(k) for k in HAKEN_ADJ) if text else 0
    if core_hits >= 8:
        score += 25; reasons.append(f"派遣関連語 多数({core_hits})")
    elif core_hits >= 3:
        score += 15; reasons.append(f"派遣関連語 あり({core_hits})")
    elif core_hits >= 1:
        score += 5; reasons.append(f"派遣関連語 少({core_hits})")
    elif text:
        reasons.append("HPに派遣の記述ほぼ無し")
    if adj_hits >= 3:
        score += 8; reasons.append("人材紹介/請負等の隣接事業あり")

    # 3) ナビに派遣/人材の独立項目
    nav_hit = [n for n in navs if re.search(r"派遣|人材|スタッフ|求人|お仕事|登録", n)]
    if nav_hit:
        score += 12; reasons.append(f"メニューに派遣/人材項目({'/'.join(nav_hit[:3])})")

    # 4) 社名・規模
    if NAME_HAKEN.search(name or ""):
        score += 10; reasons.append("社名が派遣系")
    if worker_count:
        if worker_count >= 300:
            score += 12; reasons.append(f"派遣{worker_count}人(大規模)")
        elif worker_count >= 100:
            score += 8; reasons.append(f"派遣{worker_count}人")
        elif worker_count >= 30:
            score += 4

    if not text:
        # HPが無い/取れない会社は社名・規模のみで判定。
        # 派遣数が非常に多い会社（数千人規模）は派遣が主事業でない可能性の方が低いので
        # 「HP未確認」を明記した上でBに寄せる（Cで埋もれさせない）
        reasons.insert(0, "HP取得不可のため社名・規模のみで判定")
        if (worker_count or 0) >= 500 or score >= 22:
            cls = "B"
        else:
            cls = "C"
    elif score >= 50:
        cls = "A"
    elif score >= 25:
        cls = "B"
    else:
        cls = "C"
    return cls, score, "; ".join(reasons), biz_join


def main(limit=None):
    wb = openpyxl.load_workbook(XLSX_IN)
    ws = wb.active
    header = [c.value for c in ws[1]]
    ci = {h: i + 1 for i, h in enumerate(header)}
    targets = []
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=ci["派遣番号"]).value:
            targets.append(row)
    if limit:
        targets = targets[:limit]
    print(f"判定対象: {len(targets)}行", flush=True)

    prog = json.load(open(PROGRESS, encoding="utf-8")) if os.path.exists(PROGRESS) else {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        t0 = time.time()
        done = 0
        for row in targets:
            key = str(ws.cell(row=row, column=ci["派遣番号"]).value)
            if key in prog:
                continue
            name = str(ws.cell(row=row, column=ci["会社名"]).value or "")
            hp = ws.cell(row=row, column=ci["会社HP"]).value or ""
            wc = ws.cell(row=row, column=ci["派遣労働者数"]).value
            wc = int(wc) if isinstance(wc, (int, float)) else None
            text, navs = ("", set())
            if hp:
                try:
                    text, navs = fetch_pages(browser, hp)
                except Exception:
                    pass
            cls, score, why, biz = classify(name, hp, wc, text, navs)
            prog[key] = {"cls": cls, "score": score, "why": why, "biz": biz}
            done += 1
            if done % 10 == 0:
                json.dump(prog, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False)
                el = time.time() - t0
                eta = (el / done) * (len(targets) - done) / 3600
                print(f"[{done}/{len(targets)}] {name[:20]:<22} {cls} ({score})  残り約{eta:.1f}h", flush=True)
        browser.close()
    json.dump(prog, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False)

    # 出力: 列を追加
    add_cols = ["主事業判定", "判定スコア", "判定根拠", "HP事業内容(抽出)"]
    base = len(header)
    for i, h in enumerate(add_cols, 1):
        c = ws.cell(row=1, column=base + i, value=h)
        c.font = Font(bold=True, color="FFFFFF", name="Arial")
        c.fill = PatternFill("solid", start_color="C55A11")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in range(2, ws.max_row + 1):
        key = str(ws.cell(row=row, column=ci["派遣番号"]).value or "")
        v = prog.get(key)
        if v:
            ws.cell(row=row, column=base + 1, value=v["cls"])
            ws.cell(row=row, column=base + 2, value=v["score"])
            ws.cell(row=row, column=base + 3, value=v["why"][:250])
            ws.cell(row=row, column=base + 4, value=v["biz"][:300])
    for col_i, w in zip(range(base + 1, base + 5), [10, 9, 50, 60]):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_i)].width = w
    ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(base + 4)}{ws.max_row}"
    wb.save(XLSX_OUT)

    from collections import Counter
    dist = Counter(v["cls"] for v in prog.values())
    print(f"\n===== 完了 ===== A:{dist.get('A',0)} B:{dist.get('B',0)} C:{dist.get('C',0)}")
    print(f"出力: {XLSX_OUT}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(lim)

# -*- coding: utf-8 -*-
"""新卒向けサービスを展開する会社の母集団を、Web上のまとめ記事・比較記事から収集する。

方針:
- 複数の検索クエリ（業態×切り口）でBing/Yahoo検索 → 上位記事URLを集める
- 各記事をPlaywrightで開き、本文から「株式会社◯◯」等の法人名と、サービス名→運営会社の
  記述（「◯◯（株式会社△△）」「運営：株式会社△△」）を抽出
- 会社名を正規化して重複排除。出現した記事数をカウント（多いほど業界で認知されている）
- 出力: shinsotsu_candidates.json（会社名, 正規化キー, 出現記事数, 出典URL群, 拾ったサービス名）
"""
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from jinzai_common import UA_POOL, normalize_name

BASE = "/Users/masakatsu/Desktop/kyujin_box_rpa"
OUT = os.path.join(BASE, "shinsotsu_candidates.json")
ARTICLES = os.path.join(BASE, ".shinsotsu_articles.json")

QUERIES = [
    # A. 新卒紹介・就活エージェント
    "就活エージェント おすすめ 比較 一覧",
    "新卒紹介 サービス 企業向け 比較",
    "新卒エージェント 会社 一覧",
    "体育会 新卒 紹介 エージェント",
    "理系 新卒 就活エージェント 特化",
    "留学生 新卒 就職エージェント",
    "地方学生 就活エージェント",
    "既卒 第二新卒 就活エージェント 比較",
    "新卒 紹介会社 採用担当 向け",
    # B. 新卒向け求人サイト・ダイレクトリクルーティング・イベント
    "新卒 ダイレクトリクルーティング サービス 比較",
    "新卒 スカウト型 就活サイト 一覧",
    "逆求人 イベント 新卒 運営会社",
    "就活イベント 合同説明会 運営会社 一覧",
    "新卒採用 求人サイト 掲載 比較 ナビサイト",
    "就活 口コミサイト 新卒 運営会社",
    "インターンシップ 募集サイト 新卒 比較",
    "理系 新卒 採用 サービス 比較",
    "エンジニア 新卒採用 サービス 比較",
    # C. 新卒採用支援・RPO・コンサル・ツール
    "新卒採用支援 サービス 比較 一覧",
    "新卒 採用代行 RPO 会社 比較",
    "新卒採用 コンサルティング 会社 一覧",
    "内定者フォロー サービス 比較 新卒",
    "新卒 適性検査 サービス 比較",
    "新卒採用 説明会 動画 制作 サービス",
    "新卒採用 面接代行 サービス",
    "新卒 採用管理システム ATS 比較",
    "学生 アルバイト 長期インターン 採用 サービス",
    "新卒 採用ブランディング 会社",
    "新卒 採用イベント 企画 会社",
    "大学 キャリアセンター 連携 新卒採用 サービス",
]

CORP_PAT = re.compile(
    r"((?:株式会社|有限会社|合同会社|一般社団法人)[\s　]?[\w一-龥ぁ-んァ-ヴー・＆&．.\-'’]{1,24}|"
    r"[\w一-龥ぁ-んァ-ヴー・＆&．.\-'’]{1,24}[\s　]?(?:株式会社|有限会社|合同会社))"
)
# 会社名として拾うべきでない語尾・語（記事の地の文に紛れ込むもの）
BAD_TAIL = re.compile(r"(です|ます|から|まで|など|では|には|また|さん|様|について|による|を通じて|など)$")
NOISE = {"株式会社", "有限会社", "合同会社"}
SKIP_DOMAINS = ["wikipedia", "youtube", "twitter", "x.com", "facebook", "instagram", "amazon", "rakuten"]


def clean_corp(s):
    s = s.strip().replace("　", " ")
    s = re.sub(r"\s+", "", s)
    s = BAD_TAIL.sub("", s)
    # 前後に法人格が両方ついたおかしな形を除外
    if s.count("株式会社") > 1:
        return ""
    core = re.sub(r"株式会社|有限会社|合同会社|一般社団法人", "", s)
    if len(core) < 2 or len(core) > 24:
        return ""
    if s in NOISE:
        return ""
    return s


def serp_urls(browser, query, n=8):
    ctx = browser.new_context(user_agent=random.choice(UA_POOL), locale="ja-JP")
    pg = ctx.new_page()
    pg.set_default_timeout(20000)
    urls = []
    try:
        pg.goto("https://www.bing.com/search?q=" + query, timeout=20000)
        pg.wait_for_timeout(2000)
        raw = pg.evaluate("() => Array.from(document.querySelectorAll('li.b_algo h2 a')).map(a=>a.getAttribute('href'))")
        for h in raw:
            if not h:
                continue
            # Bingリダイレクト復号
            m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", h)
            if m:
                import base64
                b64 = m.group(1).replace("-", "+").replace("_", "/")
                b64 += "=" * (-len(b64) % 4)
                try:
                    h = base64.b64decode(b64).decode("utf-8", "ignore")
                except Exception:
                    pass
            if h.startswith("http") and not any(d in h for d in SKIP_DOMAINS):
                urls.append(h)
        if len(urls) < 3:  # Bingが薄ければYahooも
            pg.goto("https://search.yahoo.co.jp/search?p=" + query, timeout=20000)
            pg.wait_for_timeout(2000)
            raw = pg.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a=>a.getAttribute('href')||'')
                .filter(h=>h.startsWith('http') && !h.includes('yahoo.co.jp'))""")
            urls += [h.split("#")[0] for h in raw if not any(d in h for d in SKIP_DOMAINS)]
    except Exception:
        pass
    finally:
        ctx.close()
    seen, out = set(), []
    for u in urls:
        k = u.split("#")[0]
        if k not in seen:
            seen.add(k); out.append(k)
    return out[:n]


# 記事内の各サービス紹介ブロックを取る: 見出し(h2/h3/h4)=サービス名 とし、
# そのブロック本文から「運営会社: 株式会社X」等の記述を探す。
# 見出しが採用企業名（〜株式会社 だけの見出し）なら対象外。
RUN_PAT = re.compile(
    r"(?:運営会社|運営元|運営|提供会社|提供元|提供|会社名|企業名|サービス提供)[\s　]*[:：]?[\s　]*"
    r"((?:株式会社|有限会社|合同会社|一般社団法人)[\s　]?[\w一-龥ぁ-んァ-ヴー・＆&．.\-'’]{1,24}|"
    r"[\w一-龥ぁ-んァ-ヴー・＆&．.\-'’]{1,24}[\s　]?(?:株式会社|有限会社|合同会社))"
)
HEAD_NOISE = re.compile(r"^(まとめ|目次|はじめに|おわりに|注意点|選び方|メリット|デメリット|よくある質問|Q&A|関連記事|"
                        r"比較表|ランキング|おすすめ|特徴|料金|評判|口コミ|まとめ|コラム|監修|執筆|この記事|"
                        r"\d+位|第\d+位|ステップ\d|STEP\d)")


def extract_from_article(browser, url):
    ctx = browser.new_context(user_agent=random.choice(UA_POOL), locale="ja-JP")
    pg = ctx.new_page()
    pg.set_default_timeout(20000)
    try:
        pg.goto(url, timeout=20000)
        pg.wait_for_timeout(1500)
        title = pg.title() or ""
        # 見出しと、その見出し〜次の見出しまでの本文をブロック化
        blocks = pg.evaluate("""
        () => {
          const hs = Array.from(document.querySelectorAll('h2,h3,h4'));
          const out = [];
          for (let i=0;i<hs.length;i++){
            let txt = '';
            let el = hs[i].nextElementSibling;
            let guard = 0;
            while (el && !/^H[234]$/.test(el.tagName) && guard < 40){
              txt += (el.innerText||'') + '\n'; el = el.nextElementSibling; guard++;
            }
            out.push([hs[i].innerText.trim(), txt]);
          }
          return out;
        }
        """)
    except Exception:
        return "", "", [], []
    finally:
        ctx.close()

    found, svc_pairs = [], []
    for head, body in blocks:
        head = re.sub(r"^[\s　\d\.．:：、\-‐・①-⑳【】\[\]「」『』]+", "", head).strip()
        head = re.sub(r"[\s　]*[（(].*$", "", head)      # 「サービス名（株式会社X）」→ サービス名
        if not head or len(head) > 40 or HEAD_NOISE.search(head):
            continue
        # 見出し自体が「〜株式会社」だけ＝採用企業紹介の可能性が高いが、
        # ブロック内にサービス提供の文脈があれば提供者として採用
        m = RUN_PAT.search(body[:1500])
        corp = clean_corp(m.group(1)) if m else ""
        if not corp:
            # 見出しに運営会社が括弧で併記されているケース
            m2 = re.search(r"[（(]\s*((?:株式会社|有限会社|合同会社)[^）)]{1,24})[）)]", head)
            corp = clean_corp(m2.group(1)) if m2 else ""
        if corp:
            found.append(corp)
            svc_pairs.append((head[:30], corp))
    return title, "", list(dict.fromkeys(found)), svc_pairs


def main():
    cands = {}
    articles = {}
    if os.path.exists(OUT):
        cands = json.load(open(OUT, encoding="utf-8"))
    if os.path.exists(ARTICLES):
        articles = json.load(open(ARTICLES, encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for qi, q in enumerate(QUERIES, 1):
            urls = serp_urls(browser, q)
            print(f"[{qi}/{len(QUERIES)}] {q}  → 記事{len(urls)}本", flush=True)
            time.sleep(random.uniform(6, 10))
            for u in urls:
                if u in articles:
                    continue
                title, text, found, svc = extract_from_article(browser, u)
                articles[u] = {"title": title, "query": q, "n": len(found)}
                for c in found:
                    key = normalize_name(c)
                    if not key:
                        continue
                    e = cands.setdefault(key, {"会社名": c, "出現記事数": 0, "出典": [], "サービス名": [], "クエリ": []})
                    e["出現記事数"] += 1
                    if u not in e["出典"]:
                        e["出典"].append(u)
                    if q not in e["クエリ"]:
                        e["クエリ"].append(q)
                for sname, corp in svc:
                    key = normalize_name(corp)
                    if key in cands and sname not in cands[key]["サービス名"]:
                        cands[key]["サービス名"].append(sname)
                json.dump(cands, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                json.dump(articles, open(ARTICLES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                time.sleep(random.uniform(2, 4))
        browser.close()

    print(f"\n===== 収集完了 =====")
    print(f"記事: {len(articles)}本 / 候補企業: {len(cands)}社")
    multi = [v for v in cands.values() if v["出現記事数"] >= 2]
    print(f"  2記事以上に登場: {len(multi)}社（業界で認知度あり）")
    top = sorted(cands.values(), key=lambda v: -v["出現記事数"])[:25]
    for v in top:
        print(f"  {v['出現記事数']:>3}本  {v['会社名'][:26]:<28} {'/'.join(v['サービス名'][:3])[:30]}")
    print(f"出力: {OUT}")


if __name__ == "__main__":
    main()

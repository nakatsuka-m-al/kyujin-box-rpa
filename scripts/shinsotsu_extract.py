# -*- coding: utf-8 -*-
"""比較・まとめ記事（shinsotsu_articles.txt）から
 サービス名（見出し）と運営会社を抽出し、shinsotsu_candidates.json に蓄積する。

抽出ロジック（見出しブロック単位）:
  1. 見出し(h2/h3/h4) = サービス名候補。雑見出しは HEAD_NOISE で除外
  2. ブロック内テキストから運営会社を検出:
     a. 「運営会社：株式会社X」「運営：X株式会社」「提供会社…」
     b. 「株式会社Xが運営/提供/展開」「X株式会社の〜サービス」
     c. 見出し括弧「サービス名（株式会社X）」
     d. 表の行 "運営会社 | 株式会社X" (innerTextで改行/タブ区切り)
  3. ブロック内の外部リンク(記事ドメイン以外, 広告/SNS除く) = サービスURL候補
運営会社が取れない見出しも service_only として記録（後段で検索解決する）
"""
import json, os, re, sys, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from jinzai_common import UA_POOL, normalize_name

BASE = "/Users/masakatsu/Desktop/kyujin_box_rpa"
LIST = os.environ.get("SLIST", os.path.join(BASE, "shinsotsu_articles.txt"))
OUT = os.path.join(BASE, "shinsotsu_candidates.json")
SVC = os.path.join(BASE, "shinsotsu_services.json")      # サービス名→{corp, urls, 出典}
ART = os.path.join(BASE, ".shinsotsu_articles.json")

CORP = r"((?:株式会社|有限会社|合同会社|一般社団法人|学校法人)[\s　]?[\w一-龥ぁ-んァ-ヴー・＆&．.\-'’]{1,24}|[\w一-龥ぁ-んァ-ヴー・＆&．.\-'’]{1,24}[\s　]?(?:株式会社|有限会社|合同会社))"
P_LABEL = re.compile(r"(?:運営会社|運営元|運営企業|運営法人|運営|提供会社|提供元|提供企業|提供|会社名|企業名|サービス提供|販売元|開発元|運営者)[\s　]*[:：|｜\t]?[\s　]*" + CORP)
P_VERB = re.compile(CORP + r"[\s　]*(?:が|の)[\s　]*(?:運営|提供|展開|手がけ|手掛け|開発|主催|運営する|提供する)")
P_PAREN = re.compile(r"[（(]\s*" + CORP + r"\s*[）)]")
BAD_TAIL = re.compile(r"(です|ます|から|まで|など|では|には|また|さん|様|について|による|を通じて|といった|という|のような|として|にて|へ|は|が|を|に|で|と|も|の)$")
HEAD_NOISE = re.compile(
    r"^(まとめ|目次|はじめに|おわりに|最後に|注意点|選び方|メリット|デメリット|よくある質問|Q&A|FAQ|関連記事|比較表|"
    r"ランキング|おすすめ|特徴|料金|費用|評判|口コミ|コラム|監修|執筆|この記事|ポイント|流れ|手順|"
    r"\d+位|第\d+位|ステップ|STEP|そもそも|.*とは[？?]?$|.*(の|を)(選び方|比較|種類|メリット|デメリット|ポイント|注意点|流れ|方法|コツ|違い|相場|料金|費用|特徴|まとめ|一覧|活用|使い方|導入|事例)|"
    r".*(サービス|エージェント|会社|ツール|サイト|媒体)(比較|一覧|\d+選|ランキング)|お問い合わせ|資料|無料|人気|新着|関連|カテゴリ|タグ|著者|プロフィール|シェア|SNS|"
    r"(株式会社|有限会社|合同会社)?[\w一-龥ぁ-んァ-ヴー・]{0,24}(株式会社|有限会社|合同会社)$)", re.I)
AD_DOMAINS = ["twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com", "line.me", "google.", "amazon", "rakuten", "a8.net", "af.moshimo", "valuecommerce", "accesstrade", "linksynergy", "felmat", "hatena", "note.com", "wikipedia", "apple.com", "play.google", "prtimes"]


def clean_corp(s):
    s = s.strip().replace("　", " ")
    s = re.sub(r"\s+", "", s)
    s = BAD_TAIL.sub("", s)
    if s.count("株式会社") > 1:
        return ""
    # 「〜する大手総合人材サービスパーソルキャリア株式会社」のような前置き語を落とす
    if re.search(r"(株式会社|有限会社|合同会社)$", s):
        s = re.sub(r"^.*(?:の|は|が|を|に|で|と|や|、|。|する|した|である|大手|業界|サービス|運営|提供|展開|人材|会社|企業|有名な|老舗|新興|上場)(?=[^の-ん]*(株式会社|有限会社|合同会社)$)", "", s)
    core = re.sub(r"株式会社|有限会社|合同会社|一般社団法人|学校法人", "", s)
    if len(core) < 2 or len(core) > 24:
        return ""
    if re.search(r"(運営|提供|サービス|エージェント|こちら|詳細|公式|比較|おすすめ|ランキング|記事|弊社|当社|自社|貴社|御社)$", core):
        return ""
    if re.match(r"^(弊社|当社|自社|貴社|御社|同社|各社|他社|大手|多くの|一部の|その|この|同じ|人材|採用)$", core):
        return ""
    return s


def find_corp(head, body):
    m = P_PAREN.search(head)
    if m:
        c = clean_corp(m.group(1))
        if c: return c, "見出し括弧"
    text = body[:2500]
    m = P_LABEL.search(text)
    if m:
        c = clean_corp(m.group(1))
        if c: return c, "運営会社表記"
    m = P_VERB.search(text)
    if m:
        c = clean_corp(m.group(1))
        if c: return c, "〜が運営"
    return "", ""


def clean_head(h):
    h = re.sub(r"^[\s　\d\.．:：、\-‐・①-⑳【】\[\]「」『』]+", "", h).strip()
    h = re.sub(r"^(第?\d+[位選]|No\.?\d+|NO\.?\d+)[\s　:：.．]*", "", h)
    h = re.sub(r"[\s　]*[（(【\[].*$", "", h)       # 括弧以降を落とす
    h = re.sub(r"[\s　]*[｜|/／:：〜~\-–—].*$", "", h)  # 区切り以降
    # 「Xに登録するデメリット」「Xで就活するメリット」「Xの評判」などの後置きを落とす
    h = re.sub(r"[\s　]*(?:に|で|を|の|は|が|と|へ)(?:登録|就活|就職活動|利用|活用|申し込|相談|口コミ|評判|料金|費用|特徴|強み|弱み|注意|メリット|デメリット|おすすめ|向いて|使う|使っ|選ぶ|向き|概要|基本情報|サービス内容|実績|求人|サポート|面談|内定|の).*$", "", h)
    h = re.sub(r"(?:の|は|が|も)$", "", h)
    return h.strip()


def main():
    urls = [l.strip() for l in open(LIST, encoding="utf-8") if l.strip() and not l.startswith("#")]
    cat = {}
    cur = ""
    for l in open(LIST, encoding="utf-8"):
        l = l.strip()
        if l.startswith("#"):
            cur = l[1:].strip()[:1]
        elif l:
            cat[l] = cur
    cands = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    svcs = json.load(open(SVC, encoding="utf-8")) if os.path.exists(SVC) else {}
    arts = json.load(open(ART, encoding="utf-8")) if os.path.exists(ART) else {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, u in enumerate(urls, 1):
            if u in arts:
                continue
            host = urlparse(u).netloc
            ctx = browser.new_context(user_agent=random.choice(UA_POOL), locale="ja-JP")
            pg = ctx.new_page(); pg.set_default_timeout(25000)
            try:
                pg.goto(u, timeout=25000); pg.wait_for_timeout(1500)
                title = pg.title() or ""
                blocks = pg.evaluate("""
                () => {
                  const hs = Array.from(document.querySelectorAll('h2,h3,h4'));
                  const out = [];
                  for (let i=0;i<hs.length;i++){
                    let txt=''; let links=[]; let el=hs[i].nextElementSibling; let g=0;
                    while (el && !/^H[234]$/.test(el.tagName) && g<40){
                      txt += (el.innerText||'')+'\\n';
                      el.querySelectorAll && el.querySelectorAll('a[href]').forEach(a=>links.push(a.href));
                      el=el.nextElementSibling; g++;
                    }
                    // 見出し自身の中のリンク
                    hs[i].querySelectorAll('a[href]').forEach(a=>links.push(a.href));
                    out.push([hs[i].innerText.trim(), txt, links]);
                  }
                  return out;
                }""")
            except Exception as e:
                print(f"[{i}/{len(urls)}] NG {u} {str(e)[:60]}", flush=True)
                arts[u] = {"title": "", "n": 0, "ng": True}
                ctx.close(); continue
            ctx.close()
            n_corp = n_svc = 0
            for head_raw, body, links in blocks:
                head = clean_head(head_raw)
                if not head or len(head) > 30 or HEAD_NOISE.search(head):
                    continue
                corp, how = find_corp(head_raw, body)
                ext = []
                for l in links:
                    h = urlparse(l).netloc
                    if h and host.split(".")[-2] not in h and not any(d in l for d in AD_DOMAINS):
                        ext.append(l.split("?")[0].split("#")[0])
                ext = list(dict.fromkeys(ext))[:3]
                skey = normalize_name(head)
                if not skey:
                    continue
                s = svcs.setdefault(skey, {"サービス名": head, "運営会社": "", "根拠": "", "URL候補": [], "出典": [], "区分": set() if False else []})
                if corp and not s["運営会社"]:
                    s["運営会社"] = corp; s["根拠"] = how
                for e in ext:
                    if e not in s["URL候補"] and len(s["URL候補"]) < 5:
                        s["URL候補"].append(e)
                if u not in s["出典"]:
                    s["出典"].append(u)
                if cat.get(u) and cat[u] not in s["区分"]:
                    s["区分"].append(cat[u])
                n_svc += 1
                if corp:
                    n_corp += 1
                    ck = normalize_name(corp)
                    c = cands.setdefault(ck, {"会社名": corp, "出現記事数": 0, "出典": [], "サービス名": [], "区分": []})
                    if u not in c["出典"]:
                        c["出典"].append(u); c["出現記事数"] += 1
                    if head not in c["サービス名"]:
                        c["サービス名"].append(head)
                    if cat.get(u) and cat[u] not in c["区分"]:
                        c["区分"].append(cat[u])
            arts[u] = {"title": title, "n": n_corp, "svc": n_svc}
            print(f"[{i}/{len(urls)}] 見出し{n_svc:>3} 運営会社{n_corp:>3}  {title[:50]}", flush=True)
            for f, d in ((OUT, cands), (SVC, svcs), (ART, arts)):
                json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            time.sleep(random.uniform(1.5, 3))
        browser.close()
    print(f"\n記事{len(arts)} / サービス見出し{len(svcs)} / 運営会社つき{sum(1 for s in svcs.values() if s['運営会社'])} / 会社{len(cands)}")


if __name__ == "__main__":
    main()

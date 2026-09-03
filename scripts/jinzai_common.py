# -*- coding: utf-8 -*-
"""厚労省 人材サービス総合サイト スクレイピング共通モジュール

これまでの試行錯誤で確立した知見を集約:
- 検索は画面遷移型。トップの検索ボタンは同じidが2つあり、2つ目でないと一覧に出ない
- 一覧の並び替え: ucCategory(2=就職者4ヶ月以上無期) × ucSort(2=降順) → id_btnSort
- 一覧ページに就職者数まで載っているので、ランキング用途なら詳細ページ不要
- 支社は同じ許可番号で複数行出る。数字は全社合計なので許可番号で1社に集約するのが正しい
- HP検索は Yahoo → Bing の多段。法人DB/地図/求人ポータルは公式サイトではないので除外
- 検証は「社名一致」または「市区名一致」。都道府県だけの一致は誤検出が多いので不可
"""
import base64
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta

BASE = "https://jinzai.hellowork.mhlw.go.jp/JinzaiWeb/"
TOP_URL = BASE + "GICB101010.do?action=transition&screenId=GICB101010&params=1"

JST = timezone(timedelta(hours=9))

UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

YAHOO_MIN_INTERVAL, YAHOO_MAX_INTERVAL = 12, 20
BING_MIN_INTERVAL, BING_MAX_INTERVAL = 25, 40
BING_BLOCK_BACKOFF = 100

NON_COMPANY_DOMAINS = [
    # 検索エンジン・SNS・百科事典
    "google.", "duckduckgo.", "bing.", "yahoo.", "wikipedia.org",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "note.com", "ameblo.jp", "hatenablog",
    # 官公庁
    "mhlw.go.jp", "hellowork.mhlw.go.jp", "jinzai.hellowork", "gbiz.go.jp",
    "houjin-bangou.nta.go.jp",
    # 法人番号・企業データベース
    "houjin.info", "houjin.jp", "houjin.goo.to", "houjin-search", "houjin-navi.com",
    "kaisharesearch.com", "baseconnect.in", "musubu.co.jp", "compalyze.co.jp",
    "companyinformation.jp", "salesnow.jp", "alarmbox.jp", "helloboss.com",
    "biz-maps.com", "kigyoubank.com", "kaisyahoumu.com", "initial.inc",
    "creditsafe", "corp-list.com", "company-search", "corp-search", "biz.ne.jp",
    "nikkei.com", "ureru.co", "targma.jp", "findglocal.com", "ecareerbox.com",
    # 地図・電話帳・口コミポータル
    # 電話番号検索サイトは特に注意。電話番号一致で判定するため必ず引っかかる
    "navitime.co.jp", "mapion.co.jp", "itp.ne.jp", "ekiten.jp", "goo.ne.jp",
    "tabelog.com", "jpnumber.com", "care-net.biz",
    "telnavi.jp", "telsearch", "denwabangou", "jpon.xyz", "chiku-navi",
    # プレスリリース・団体
    "prtimes.jp", "jesra.or.jp", "minshokyo.or.jp",
    # 注意: 求人・転職ポータル(mynavi.jp, doda.jp 等)はここに入れてはいけない。
    # 本リストの対象企業はポータル運営会社そのものであり、それらのドメインが
    # 各社の公式サイトになる。ポータルの「他社求人ページ」を拾う問題は
    # URLパターンとトップページ確認で弾く。
    # 口コミ・評判サイト（企業ページがあるので社名が一致してしまう。必ず除外）
    "hyouban", "hyoban", "vorkers", "openwork.jp", "lighthouse", "career-picks",
    "kuchikomi", "jobtalk.jp", "career-connection", "tenshoku-antenna",
]

NON_COMPANY_URL_PATTERNS = [
    "/corporations/", "/corporation/", "/hojin/", "/houjin/",
    "/company/detail/", "/companies/", "/corp/detail/", "/corp/",
    "/jobs/", "/kyujin", "/detail/", "/shopdetail", "/phonebook",
]

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]


def now_jst():
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def check_maintenance_window():
    """日曜22:00〜月曜8:00はサイトメンテナンスのため実行しない"""
    now = datetime.now(JST)
    hm = now.hour * 60 + now.minute
    if (now.weekday() == 6 and hm >= 22 * 60) or (now.weekday() == 0 and hm < 8 * 60):
        print("!! 日曜22:00〜月曜8:00はメンテナンス時間帯のため中止します。", flush=True)
        sys.exit(1)


def extract_city(address):
    """住所から (検索用の都道府県+市区, 照合用の市区のみ) を返す"""
    addr = (address or "").strip()
    for pref in PREFECTURES:
        if addr.startswith(pref):
            rest = addr[len(pref):]
            m = re.match(r"([^0-9０-９\s　]{1,8}?[市区町村])", rest)
            if m:
                return pref + m.group(1), m.group(1)
            return pref, ""
    return "", ""


def looks_like_directory_url(url):
    low = (url or "").lower()
    if any(pat in low for pat in NON_COMPANY_URL_PATTERNS):
        return True
    # 日本の法人番号は13桁。URLに13桁の数字が入るのは企業データベースの詳細ページ
    if re.search(r"\d{13}", low):
        return True
    m = re.match(r"https?://([^/]+)", low)
    domain = m.group(1) if m else low
    return "houjin" in domain


def is_bad_url(url):
    if not url:
        return False
    low = url.lower()
    return any(nd in low for nd in NON_COMPANY_DOMAINS) or looks_like_directory_url(url)


def normalize_name(s):
    """社名照合用に正規化: 全角→半角、法人格・記号・空白を除去"""
    if not s:
        return ""
    s = s.translate(str.maketrans(
        "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz",
    )).lower()
    for token in ["株式会社", "有限会社", "合同会社", "協同組合", "一般社団法人",
                  "社団法人", "公益社団法人", "特定非営利活動法人", "医療法人"]:
        s = s.replace(token, "")
    # 「ー」(katakana長音)は社名の一部なので削ってはいけない。
    # 削るとギークリー→ギクリ、クーリエ→クリエと別物になり照合が壊れる
    return re.sub(r"[\s　・･,，.。\-‐－‑–—_（）()「」『』/]", "", s)


# ---------------------------------------------------------------- browser


def new_page(browser):
    page = browser.new_page(user_agent=UA_POOL[0])
    page.set_default_timeout(25000)
    return page


def open_sorted_list(page, nationwide=True, category="2", order="2"):
    """検索を実行し、指定カテゴリ・順序で並び替えた一覧ページを開く。総件数を返す"""
    page.goto(TOP_URL, timeout=25000)
    page.wait_for_timeout(1200)
    page.check("#ID_cbZenkoku1" if nationwide else "#ID_cbTokyo1")
    page.check("#ID_cbJigyoshoKbnYu1")  # 有料職業紹介事業
    page.wait_for_timeout(200)

    # 同idの検索ボタンが2つあり、2つ目でないと一覧に遷移しない
    with page.expect_navigation(timeout=20000):
        page.locator("#id_btnSearch").nth(1).click()
    page.wait_for_timeout(1500)

    page.select_option("#ID_ucCategory", category)
    page.select_option("#ID_ucSort", order)
    page.wait_for_timeout(200)
    with page.expect_navigation(timeout=20000):
        page.click("#id_btnSort")
    page.wait_for_timeout(2000)

    text = page.inner_text("body")
    m = re.search(r"検索結果\s*([\d,]+)\s*件", text)
    return int(m.group(1).replace(",", "")) if m else None


def goto_page(page, n):
    with page.expect_navigation(timeout=20000):
        page.evaluate(f"doPostAction('page','{n}')")
    page.wait_for_timeout(700)


def grab_list_rows(page):
    """一覧ページの各行を構造化して返す"""
    raw = page.evaluate("""
    () => {
        let out = [];
        document.querySelectorAll('a[href*="action=detail"]').forEach(a => {
            let lic = a.innerText.trim();
            if (!lic) return;
            let tr = a.closest('tr');
            if (!tr) return;
            out.push(Array.from(tr.querySelectorAll('td')).map(td => td.innerText));
        });
        return out;
    }
    """)

    def num(s):
        s = (s or "").replace(",", "").strip()
        return int(s) if re.fullmatch(r"-?\d+", s) else None

    rows = []
    for cells in raw:
        if len(cells) < 5:
            continue
        c0 = [x.strip() for x in cells[0].split("\n") if x.strip()]
        c1 = [x.strip() for x in cells[1].split("\n") if x.strip()]
        c2 = [x.strip() for x in cells[2].split("\n") if x.strip()]
        rows.append({
            "許可番号": c0[0] if c0 else "",
            "許可年月日": c0[1] if len(c0) > 1 else "",
            "事業主名称": c1[0] if c1 else "",
            "事業所名称": c1[1] if len(c1) > 1 else (c1[0] if c1 else ""),
            "所在地": c2[0] if c2 else "",
            "電話": c2[1] if len(c2) > 1 else "",
            "就職者_4ヶ月以上": num(cells[3]),
            "うち無期": num(cells[4]),
            "就職者_4ヶ月未満": num(cells[5]) if len(cells) > 5 else None,
        })
    return rows


# ---------------------------------------------------------------- HP search

_last_yahoo = [0.0]
_last_bing = [0.0]


def _throttle(last_ref, lo, hi, label):
    elapsed = time.time() - last_ref[0]
    wait = random.uniform(lo, hi)
    if elapsed < wait:
        time.sleep(wait - elapsed)


def _decode_bing_redirect(href):
    m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", href or "")
    if not m:
        return href
    b64 = m.group(1).replace("-", "+").replace("_", "/")
    b64 += "=" * (-len(b64) % 4)
    try:
        return base64.b64decode(b64).decode("utf-8", "ignore")
    except Exception:
        return href


def _is_blocked(page):
    try:
        title = (page.title() or "").lower()
        url = (page.url or "").lower()
    except Exception:
        return False
    markers = ["unusual traffic", "続行するには", "captcha", "verify you are human"]
    return any(m in title for m in markers) or "sorry" in url


def _yahoo_query(browser, query):
    ctx = browser.new_context(user_agent=random.choice(UA_POOL), locale="ja-JP")
    page = ctx.new_page()
    page.set_default_timeout(20000)
    try:
        page.goto("https://search.yahoo.co.jp/search?p=" + query, timeout=20000)
        page.wait_for_timeout(1800)
        return page.evaluate("""
        () => {
            let seen = new Set(), out = [];
            document.querySelectorAll('a').forEach(a => {
                let h = a.getAttribute('href') || '';
                if (!h.startsWith('http')) return;
                if (h.includes('yahoo.co.jp') || h.includes('yahoo.com')) return;
                h = h.split('#')[0];
                if (!seen.has(h)) { seen.add(h); out.push(h); }
            });
            return out;
        }
        """)
    except Exception:
        return None
    finally:
        ctx.close()


def _bing_query(browser, query):
    ctx = browser.new_context(user_agent=random.choice(UA_POOL), locale="ja-JP")
    page = ctx.new_page()
    page.set_default_timeout(20000)
    try:
        page.goto("https://www.bing.com/search?q=" + query, timeout=20000)
        page.wait_for_timeout(2500)
        if _is_blocked(page):
            return None
        raw = page.evaluate(
            "() => Array.from(document.querySelectorAll('li.b_algo h2 a')).map(a=>a.getAttribute('href'))"
        )
        if not raw:
            page.wait_for_timeout(4000)
            raw = page.evaluate(
                "() => Array.from(document.querySelectorAll('li.b_algo h2 a')).map(a=>a.getAttribute('href'))"
            )
        return [_decode_bing_redirect(h) for h in raw if h]
    except Exception:
        return None
    finally:
        ctx.close()


ERROR_PAGE_MARKERS = [
    "403", "forbidden", "access denied", "could not be satisfied",
    "404", "not found", "error", "attention required", "just a moment",
]


def _looks_like_error_page(title, body):
    if body is None:
        return True
    if len(body.strip()) < 200:
        return True
    t = (title or "").lower()
    return any(m in t for m in ERROR_PAGE_MARKERS)


HEADINGS_JS = """
() => {
    let parts = [];
    ['og:site_name','og:title','application-name'].forEach(n => {
        let m = document.querySelector(`meta[property="${n}"]`) || document.querySelector(`meta[name="${n}"]`);
        if (m && m.content) parts.push(m.content);
    });
    document.querySelectorAll('h1, h2').forEach(h => parts.push(h.innerText || ''));
    document.querySelectorAll('header img[alt], .logo img[alt], #logo img[alt], a[href="/"] img[alt]')
        .forEach(i => parts.push(i.alt || ''));
    return parts.join(' ');
}
"""


def _read_page(page):
    title = page.title() or ""
    body = page.inner_text("body")
    try:
        heads = page.evaluate(HEADINGS_JS) or ""
    except Exception:
        heads = ""
    return title, body, heads


def _fetch_text(verify_page, url, browser=None):
    """(title, body, headings) を返す。取得失敗時は (None, None, "")。

    大手企業サイトはbot対策で403を返すことがあるため、
    エラーページらしき応答なら別UA・別コンテキストで一度だけ再取得する。
    """
    try:
        verify_page.goto(url, timeout=15000)
        verify_page.wait_for_timeout(800)
        title, body, heads = _read_page(verify_page)
    except Exception:
        title, body, heads = None, None, ""

    if browser is None or not _looks_like_error_page(title, body):
        return title, body, heads

    ctx = None
    try:
        ctx = browser.new_context(
            user_agent=random.choice(UA_POOL),
            locale="ja-JP",
            extra_http_headers={
                "Accept-Language": "ja,en-US;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        pg = ctx.new_page()
        pg.set_default_timeout(15000)
        pg.goto(url, timeout=15000)
        pg.wait_for_timeout(1500)
        t2, b2, h2 = _read_page(pg)
        if not _looks_like_error_page(t2, b2):
            return t2, b2, h2
    except Exception:
        pass
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
    return title, body, heads



def _short_name_ok(hay, key):
    """2文字社名の安全な一致判定。正規化hayの中で key の直後が
    「同種の文字（かな同士・漢字同士・英数同士）」で続かなければ一致とみなす。
    例: 'エン' → 'エンeninc' はOK（カナ→英字で切れる）、'エンジニアリング' はNG（カナが続く）"""
    import re as _re
    if key not in hay:
        return False
    def kind(ch):
        if _re.match(r"[ぁ-んァ-ヴー]", ch): return "kana"
        if _re.match(r"[一-龥]", ch): return "kanji"
        if _re.match(r"[a-z0-9]", ch): return "alnum"
        return "other"
    kk = kind(key[-1]); k0 = kind(key[0])
    for m in _re.finditer(_re.escape(key), hay):
        after = hay[m.end():m.end()+1]
        before = hay[max(0, m.start()-1):m.start()]
        if (not after or kind(after) != kk) and (not before or kind(before) != k0):
            return True
    return False


def name_matches(hay, name_key):
    """社名の照合。

    登記名とサイトのブランド名がずれる例（登記「ミライプロジェクトHR」/ サイト
    「ミライプロジェクト」）に対応するため前方一致も許容するが、緩くすると
    「スタッフサービス」の先頭4文字が「メカロスタッフ」に当たるような誤検出が
    起きるので、十分に長い社名かつ大部分が一致する場合に限定する。
    """
    if not name_key:
        return False
    if len(name_key) < 3:
        # 2文字社名（エン、学情など）は本文照合だと誤爆するが、
        # ページタイトル/見出し(hay)に「株式会社」隣接で現れるなら十分な確証。
        # 呼び出し側は title+headings を渡す運用なので、ここでは前後に法人格が
        # 付いた形の一致のみ許可する
        return _short_name_ok(hay, name_key)
    if name_key in hay:
        return True
    if len(name_key) < 9:
        return False  # 短い社名は前方一致を使わない（一般名詞に当たりやすい）
    cut = max(6, int(len(name_key) * 0.75))
    return len(name_key) > cut and name_key[:cut] in hay


def phone_matches(body, phone):
    """電話番号の一致。ハイフン有無の両方を見る。社名ブランドが全く違う場合の決め手になる"""
    if not body or not phone:
        return False
    p = phone.strip()
    digits = re.sub(r"\D", "", p)
    if len(digits) < 9:
        return False
    return p in body or digits in re.sub(r"[-‐－ー\s　()（）]", "", body)


COMPANY_INFO_PATHS = [
    "/about", "/aboutus", "/about-us", "/company", "/company/profile",
    "/corporate", "/profile", "/outline", "/companyinfo", "/overview",
]


def _is_company_info_path(url, origin):
    """URLが「その会社の会社概要ページ」の典型パスかどうか"""
    path = url[len(origin):].split("?")[0].split("#")[0].rstrip("/").lower()
    path = re.sub(r"\.(html?|php|aspx)$", "", path)
    return path in COMPANY_INFO_PATHS


def domain_matches(url, name_key):
    """社名（英字表記の場合）がドメインに含まれるか。XMile→xmile.co.jp のように強い根拠になる"""
    if not name_key or len(name_key) < 4 or not name_key.isascii():
        return False
    m = re.match(r"https?://([^/]+)", (url or "").lower())
    if not m:
        return False
    return name_key in re.sub(r"[^a-z0-9]", "", m.group(1))


def _page_confirms(url, title, body, heads, name_key, phone=""):
    """このページが対象企業「自身の」ページだと確証できるか。

    本文に社名が出るだけでは根拠にならない。実際に次の誤検出が起きた:
      - 他社サイトの採用情報に「マイナビ2027」と書いてあるだけで一致
      - グループ会社が会社概要ページで系列各社を列挙しており別会社に一致
    そのため、ページの主題を表す箇所（タイトル・見出し・ロゴ・OGP）と
    ドメイン・電話番号のみを根拠とする。
    """
    if body is None:
        return False
    if phone_matches(body, phone):
        return True
    if domain_matches(url, name_key):
        return True
    return name_matches(normalize_name((title or "") + " " + (heads or "")), name_key)


def verify_site(verify_page, url, company_name, city_only, phone="", browser=None):
    """候補URLがその会社の公式サイトか検証し、採用すべきURL（原則トップページ）を返す。
    公式でなければ空文字。

    誤検出対策の要は「トップページ確認」:
    法人DB・地図・求人ポータルは、詳細ページには社名も住所も載っているため
    ページ単体では公式サイトと区別できない。しかしトップページは自社サービスの
    紹介であり対象企業名が出てこないので、そこで確実に弾ける。
    """
    name_key = normalize_name(company_name)
    m = re.match(r"(https?://[^/]+)", url)
    if not m:
        return ""
    origin = m.group(1)
    is_deep = url.rstrip("/") != origin.rstrip("/")

    # 1) 候補ページ自体を判定
    title, body, heads = _fetch_text(verify_page, url, browser)
    if _page_confirms(url, title, body, heads, name_key, phone):
        if not is_deep:
            return origin
        # /about や /company のような会社概要ページのタイトルが対象企業名なら、
        # そのドメインは対象企業のものと断定できる（他社DBの自己紹介ページが
        # 別会社名を名乗ることはない）。英語ブランドでトップに日本語社名が
        # 出ないサイトを救うため、この場合はトップページ確認を省く
        if _is_company_info_path(url, origin):
            return origin
        # それ以外の深いページはトップページ確認。そのドメインのトップが
        # 対象企業のものでなければ、他社運営のDB/ポータルの掲載ページと判断する
        ht, hb, hh = _fetch_text(verify_page, origin, browser)
        if hb is None:
            return url  # トップが取得できない場合のみ候補ページを採用
        return origin if _page_confirms(origin, ht, hb, hh, name_key, phone) else ""

    # 2) トップページと会社概要ページも見る（候補が深いページだった場合の救済）
    for path in ["", "/company", "/about", "/aboutus", "/corporate", "/profile",
                 "/company/profile", "/outline", "/companyinfo"]:
        cand = origin + path
        if cand.rstrip("/") == url.rstrip("/"):
            continue
        t2, b2, h2 = _fetch_text(verify_page, cand, browser)
        if _page_confirms(cand, t2, b2, h2, name_key, phone):
            return origin
    return ""


def _pick(verify_page, links, company_name, city_only, phone="", browser=None):
    for href in (links or [])[:5]:
        if is_bad_url(href):
            continue
        confirmed = verify_site(verify_page, href, company_name, city_only, phone, browser)
        if confirmed:
            return confirmed
    return ""


def find_official_site(browser, verify_page, company_name, address, phone=""):
    """公式サイトを多段検索で探す。見つからなければ空文字"""
    pref_city, city_only = extract_city(address)
    name = (company_name or "").replace("　", " ").strip()
    if not name:
        return ""

    # 1) Yahoo: 社名+市区
    _throttle(_last_yahoo, YAHOO_MIN_INTERVAL, YAHOO_MAX_INTERVAL, "Yahoo")
    links = _yahoo_query(browser, f"{name} {pref_city}".strip())
    _last_yahoo[0] = time.time()
    hit = _pick(verify_page, links, name, city_only, phone, browser)
    if hit:
        return hit

    # 2) Yahoo: 社名のみ
    _throttle(_last_yahoo, YAHOO_MIN_INTERVAL, YAHOO_MAX_INTERVAL, "Yahoo")
    links = _yahoo_query(browser, name)
    _last_yahoo[0] = time.time()
    hit = _pick(verify_page, links, name, city_only, phone, browser)
    if hit:
        return hit

    # 3) Bing: 社名+市区
    _throttle(_last_bing, BING_MIN_INTERVAL, BING_MAX_INTERVAL, "Bing")
    links = _bing_query(browser, f"{name} {pref_city}".strip())
    _last_bing[0] = time.time()
    if links is None:
        time.sleep(BING_BLOCK_BACKOFF)
    else:
        hit = _pick(verify_page, links, name, city_only, phone, browser)
        if hit:
            return hit

    # 4) Yahoo: 電話番号
    if phone and phone.strip():
        _throttle(_last_yahoo, YAHOO_MIN_INTERVAL, YAHOO_MAX_INTERVAL, "Yahoo")
        links = _yahoo_query(browser, f'"{phone.strip()}"')
        _last_yahoo[0] = time.time()
        hit = _pick(verify_page, links, name, city_only, phone, browser)
        if hit:
            return hit
    return ""

# -*- coding: utf-8 -*-
"""投げ込み_更新.xlsx
 ① 人材紹介: E列(公式HP)空欄を検索で補完 → F列に問い合わせフォームURL
 ③ 投げ込み完了派遣: 送信不可×お問い合わせフォーム無し の行 → F列にフォームURL
フォーム判定: リンク文言/URLが問い合わせ系 → 遷移先に <form>(textarea or input≧2) か
 外部フォーム(Googleフォーム/HubSpot/formrun等) があれば採用。法人向け/企業向け を優先。
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from urllib.parse import urlparse, urljoin
import openpyxl
from openpyxl.styles import Font
from playwright.sync_api import sync_playwright
from jinzai_common import UA_POOL, new_page, find_official_site, is_bad_url, extract_city

BASE = "/Users/masakatsu/Desktop/kyujin_box_rpa"
XLSX = os.path.join(BASE, "投げ込み_更新.xlsx")
PROG = os.path.join(BASE, ".nagekomi_forms.json")

LINK_PAT = re.compile(r"問い?合わ?せ|問合せ|お問合|contact|inquiry|toiawase|otoiawase|ご相談|資料請求|form", re.I)
BIZ_PAT = re.compile(r"法人|企業|採用担当|求人|人事|ご依頼|導入|サービスに関する|お仕事を(依頼|お探しの企業)|クライアント|corporate|business|client", re.I)
NEG_PAT = re.compile(r"求職|転職希望|お仕事をお探し|登録|エントリー|応募|スタッフ|採用情報|recruit|entry|login|ログイン|mypage|マイページ|faq|privacy|個人情報|tel:|mailto:|採用に関する|応募者|会員|kaiin|member|signup|sign-up|register|/ir/|ir\.|投資家|株主|取材|報道|press|media|広報|苦情|通報|ホットライン|hotline|whistle|support\.google|chrome|twitter|facebook|instagram|youtube|line\.me|password|forgot|/search|survey|enquete|seminar|event|document|download|whitepaper|資料ダウンロード", re.I)
EXT_FORM_PROVIDERS = re.compile(r"msgs\.jp|form\.run|formrun|docs\.google\.com/forms|forms\.gle|hubspot|tayori|formzu|ssl-form|form-mailer|kintoneapp|formok|secure-link|jotform|typeform|salesforce|pardot|marketo|satori|ferret-one|b-form|synergy|cuenote|mailform|shanon|list-finder|bowlab|formcreator|smartforms|fofa\.jp|formmailer|sbm\.jp|cybozu|kintone|zoho|hsforms|clickform|formz|secure\.|contactform|form\.", re.I)
EXT_FORM = re.compile(r"docs\.google\.com/forms|forms\.gle|hubspot|form\.run|formrun|tayori|formzu|ssl-form|form-mailer|kintoneapp|formok|secure-link|jotform|typeform|salesforce|pardot|marketo|satori|ferret-one|b-form|formzu|synergy|cuenote|mailform|shanon|list-finder|bowlab|formcreator|smartforms", re.I)
PATHS = ["/contact/", "/contact", "/inquiry/", "/inquiry", "/contact/corporate/", "/contact/company/", "/company/contact/", "/contactus/", "/contact-us/", "/form/", "/toiawase/", "/otoiawase/", "/contact/index.html", "/inquiry/index.html", "/contact.html", "/inquiry.html", "/contact.php", "/contact/form/", "/contact/business/", "/contact/corp/", "/corporate/contact/"]


def has_form(pg):
    """現在ページに入力フォームがあるか (score, kind)"""
    try:
        info = pg.evaluate("""
        () => {
          const forms = Array.from(document.querySelectorAll('form'));
          let best = 0;
          for (const f of forms) {
            const ta = f.querySelectorAll('textarea').length;
            const inp = Array.from(f.querySelectorAll('input')).filter(i=>!['hidden','submit','button','image'].includes((i.type||'').toLowerCase())).length;
            const isSearch = (f.getAttribute('role')==='search') || /search|検索/i.test(f.className+' '+f.id+' '+(f.getAttribute('action')||''));
            if (isSearch) continue;
            const s = ta*3 + inp;
            if (s > best) best = s;
          }
          const ifr = Array.from(document.querySelectorAll('iframe')).map(i=>i.src||'').join(' ');
          const txt = (document.body.innerText||'').slice(0,20000);
          return {best, ifr, txt, url: location.href};
        }""")
    except Exception:
        return 0, "", "", ""
    score = info["best"]
    kind = "form" if score >= 3 else ""
    if not kind and EXT_FORM.search(info["ifr"] or ""):
        score, kind = 5, "埋め込みフォーム"
    return score, kind, info["txt"], info["url"]


def find_form(pg, hp):
    """会社HPから問い合わせフォームURLを探す。(url, note)"""
    if not hp or not hp.startswith("http"):
        return "", "HPなし"
    origin = "{0.scheme}://{0.netloc}".format(urlparse(hp))
    try:
        r = pg.goto(hp, timeout=20000); pg.wait_for_timeout(800)
    except Exception:
        try:
            r = pg.goto(hp, timeout=20000); pg.wait_for_timeout(800)
        except Exception:
            return "", "サイトが開けない"
    if r and r.status >= 400:
        return "", f"サイトエラー{r.status}"
    hp = pg.url
    origin = "{0.scheme}://{0.netloc}".format(urlparse(hp))
    try:
        links = pg.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a=>[a.href, ((a.innerText||'')+' '+(a.getAttribute('aria-label')||'')+' '+(a.querySelector('img')?a.querySelector('img').alt||'':'')).trim().slice(0,60)])")
    except Exception:
        links = []
    cands = []
    for href, txt in links:
        if not href.startswith("http") or NEG_PAT.search(txt) or NEG_PAT.search(href):
            continue
        if not (LINK_PAT.search(txt) or LINK_PAT.search(href)):
            continue
        if EXT_FORM.search(href) or EXT_FORM_PROVIDERS.search(href):
            cands.append((10, href)); continue
        reg = lambda n: ".".join(n.split(".")[-3:]) if n.endswith((".co.jp", ".or.jp", ".ne.jp", ".ac.jp")) else ".".join(n.split(".")[-2:])
        hn, on = urlparse(href).netloc, urlparse(origin).netloc
        same = hn.replace("www.", "") == on.replace("www.", "")
        if not same and reg(hn) != reg(on):
            continue   # 他社ドメインは外部フォームサービス以外採用しない
        sc = 5 if same else 3
        if BIZ_PAT.search(txt) or BIZ_PAT.search(href): sc += 4
        if re.search(r"corporate|business|company|houjin|kigyou|client", href, re.I): sc += 2
        cands.append((sc, href.split("#")[0]))
    # 定型パス
    for i, p in enumerate(PATHS):
        cands.append((4 if i < 4 else 1, origin + p))
    seen, tried = set(), 0
    cands.sort(key=lambda x: -x[0])
    best = None
    for sc, u in cands:
        if u in seen or tried >= 10:
            continue
        seen.add(u); tried += 1
        try:
            r = pg.goto(u, timeout=15000); pg.wait_for_timeout(700)
        except Exception:
            continue
        if r and r.status >= 400:
            continue
        score, kind, txt, cur = has_form(pg)
        if not kind:
            # フォームページへの更なるリンク（「法人のお客様」「フォームはこちら」）を1段だけ辿る
            try:
                sub = pg.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a=>[a.href, (a.innerText||'').trim().slice(0,60)])")
            except Exception:
                sub = []
            for h2, t2 in sub:
                if h2.startswith("http") and (BIZ_PAT.search(t2) or re.search(r"フォーム|form", t2 + h2, re.I)) and not NEG_PAT.search(t2 + h2) and h2 not in seen:
                    seen.add(h2)
                    try:
                        r2 = pg.goto(h2, timeout=15000); pg.wait_for_timeout(700)
                        if r2 and r2.status < 400:
                            score, kind, txt, cur = has_form(pg)
                            if kind:
                                u = h2; break
                    except Exception:
                        continue
            if not kind:
                continue
        if NEG_PAT.search(txt[:300]) and not BIZ_PAT.search(txt[:2000]) and re.search(r"求職者|お仕事をお探し|転職をお考え", txt[:1500]):
            # 求職者向けフォームの可能性 → 候補として保持しつつ継続
            if best is None: best = (cur or u, "求職者向けの可能性")
            continue
        return (cur or u).split("#")[0], kind
    if best:
        return best
    return "", "フォーム見つからず"


def main(limit=None):
    wb = openpyxl.load_workbook(XLSX)
    ws = wb["人材紹介"]; wh = wb["投げ込み完了派遣"]
    prog = json.load(open(PROG, encoding="utf-8")) if os.path.exists(PROG) else {}
    jobs = []
    for r in range(2, ws.max_row + 1):
        jobs.append(("人材紹介", r, ws.cell(r, 2).value, ws.cell(r, 5).value, ws.cell(r, 7).value))
    for r in range(2, wh.max_row + 1):
        reason = str(wh.cell(r, 5).value or "")
        if wh.cell(r, 3).value == "送信不可" and re.search(r"フォーム\s*(無し|なし|ない)", reason):
            jobs.append(("派遣", r, wh.cell(r, 1).value, wh.cell(r, 2).value, ""))
    if limit: jobs = jobs[:limit]
    print("対象", len(jobs), flush=True)
    with sync_playwright() as p:
        state = {}

        def launch():
            state["browser"] = p.chromium.launch(headless=True)
            ctx = state["browser"].new_context(user_agent=UA_POOL[0], locale="ja-JP", ignore_https_errors=True)
            state["pg"] = ctx.new_page(); state["pg"].set_default_timeout(15000)
            state["vp"] = new_page(state["browser"]); state["vp"].set_default_timeout(15000)

        def alive():
            try:
                return state["browser"].is_connected() and not state["pg"].is_closed()
            except Exception:
                return False

        launch()
        t0 = time.time(); done = 0
        for sheet, r, name, hp, addr in jobs:
            if not alive():
                print("  ブラウザ再起動", flush=True)
                try:
                    state["browser"].close()
                except Exception:
                    pass
                launch()
            browser, pg, vp = state["browser"], state["pg"], state["vp"]
            key = f"{sheet}|{r}"
            if key in prog: continue
            hp = str(hp or "").strip()
            hp_how = ""
            if not hp or not hp.startswith("http"):
                try:
                    hit = find_official_site(browser, vp, str(name), str(addr or ""), "")
                except Exception:
                    hit = ""
                if hit and not is_bad_url(hit):
                    hp, hp_how = hit, "検索で補完"
            form, note = ("", "HPなし")
            if hp:
                try:
                    form, note = find_form(pg, hp)
                except Exception as e:
                    form, note = "", "エラー"
            prog[key] = {"name": name, "hp": hp, "hp_how": hp_how, "form": form, "note": note}
            json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            done += 1
            rem = len([j for j in jobs if f"{j[0]}|{j[1]}" not in prog])
            eta = (time.time() - t0) / done * rem / 60
            print(f"[{done}] {sheet} {str(name)[:20]:<22} {note:<10} {form[:60] or '-'}  残り約{eta:.0f}分", flush=True)
        try:
            state["browser"].close()
        except Exception:
            pass
    write(wb, ws, wh, prog)


def write(wb, ws, wh, prog):
    n1 = n2 = n3 = 0
    for key, v in prog.items():
        sheet, r = key.split("|"); r = int(r)
        if sheet == "人材紹介":
            if v["hp_how"] and v["hp"] and not ws.cell(r, 5).value:
                c = ws.cell(r, 5); c.value = v["hp"]; c.hyperlink = v["hp"]; c.font = Font(color="0563C1", underline="single"); n1 += 1
            if v["form"]:
                c = ws.cell(r, 6); c.value = v["form"]; c.hyperlink = v["form"]; c.font = Font(color="0563C1", underline="single"); n2 += 1
            elif v["note"] and v["note"] != "HPなし":
                ws.cell(r, 6).value = None
        else:
            if v["form"]:
                c = wh.cell(r, 6); c.value = v["form"]; c.hyperlink = v["form"]; c.font = Font(color="0563C1", underline="single"); n3 += 1
    wb.save(XLSX)
    print(f"HP補完 {n1} / 人材紹介フォーム {n2} / 派遣フォーム {n3}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "write":
        wb = openpyxl.load_workbook(XLSX)
        write(wb, wb["人材紹介"], wb["投げ込み完了派遣"], json.load(open(PROG, encoding="utf-8")))
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else None)

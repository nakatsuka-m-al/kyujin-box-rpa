# -*- coding: utf-8 -*-
"""取得済みフォームURL・補完HPを監査し、疑わしいものを消して再取得対象に戻す。

監査:
 A) 除外パターン（パスワード再発行/検索/アンケート/セミナー/資料DL/IR等）に当たるURL → 破棄
 B) トップページそのもの（パス無し）→ 要確認フラグ（フォームが本当にトップにあるかは has_form 済みなので残すが印をつける）
 C) 会社HPと別ドメイン かつ 既知フォームサービスでない → 破棄
 D) 検索で補完したHPを厳格再検証（社名がタイトル/見出しに出るか）→ NGなら HPもフォームも破棄
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from jinzai_common import new_page, verify_site

BASE = "/Users/masakatsu/Desktop/kyujin_box_rpa"
PROG = os.path.join(BASE, ".nagekomi_forms.json")

BAD_URL = re.compile(r"password|forgot|/search|survey|enquete|seminar|/event|document|download|whitepaper|"
                     r"資料|/ir/|ir\.|投資家|株主|press|media|広報|苦情|通報|hotline|whistle|"
                     r"support\.google|chrome|twitter|facebook|instagram|youtube|line\.me|"
                     r"login|signup|sign-up|register|mypage|会員|kaiin|member|entry|エントリー", re.I)
FORM_SVC = re.compile(r"msgs\.jp|form\.run|formrun|docs\.google\.com/forms|forms\.gle|hubspot|tayori|formzu|"
                      r"ssl-form|form-mailer|kintoneapp|formok|jotform|typeform|salesforce|pardot|marketo|satori|"
                      r"ferret-one|cuenote|shanon|list-finder|formcreator|fofa\.jp|k3r\.jp|my\.site\.com|"
                      r"secure|hsforms|zoho|cybozu|kintone|f\.msgs|wcform|contact|inquiry|form", re.I)


def reg(host):
    host = host.replace("www.", "")
    return ".".join(host.split(".")[-3:]) if host.endswith((".co.jp", ".or.jp", ".ne.jp", ".ac.jp")) else ".".join(host.split(".")[-2:])


def main(apply=False):
    prog = json.load(open(PROG, encoding="utf-8"))
    drop_a = drop_c = drop_d = 0
    top_only = []
    recheck_hp = [(k, v) for k, v in prog.items() if v.get("hp_how")]

    # D) 補完HPの厳格再検証
    bad_hp = set()
    if recheck_hp:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            vp = new_page(browser); vp.set_default_timeout(15000)
            for k, v in recheck_hp:
                ok = ""
                try:
                    ok = verify_site(vp, v["hp"], str(v["name"]), "", "", browser)
                except Exception:
                    ok = ""
                if not ok:
                    bad_hp.add(k)
                    print(f"  HP不採用: {v['name'][:20]} {v['hp']}", flush=True)
            browser.close()

    for k, v in list(prog.items()):
        f = v.get("form") or ""
        if k in bad_hp:
            v["hp"], v["hp_how"], v["form"], v["note"] = "", "", "", "HP特定できず(検証NG)"
            drop_d += 1
            continue
        if not f:
            continue
        if BAD_URL.search(f):
            prog.pop(k); drop_a += 1
            continue
        hp = v.get("hp") or ""
        if hp:
            fh, hh = urlparse(f).netloc, urlparse(hp).netloc
            if reg(fh) != reg(hh) and not FORM_SVC.search(f):
                prog.pop(k); drop_c += 1
                continue
        if urlparse(f).path.strip("/") == "":
            top_only.append((v["name"], f))
    print(f"\n除外URL {drop_a} / 別ドメイン {drop_c} / HP検証NG {drop_d}")
    print(f"トップページのみ(要確認) {len(top_only)}")
    for n, f in top_only[:20]:
        print("   ", n[:22], f)
    if apply:
        json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("progress更新済み（未取得扱いに戻した行は再実行で拾われます）")


if __name__ == "__main__":
    main(apply=(len(sys.argv) > 1 and sys.argv[1] == "apply"))

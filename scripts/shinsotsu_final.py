# -*- coding: utf-8 -*-
"""キャッシュ済みHPテキストから判定ルールv2で再判定し、手動補正を当ててExcel出力"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shinsotsu_judge import write_excel, CAND, PROG, TXTDIR, SELF_RECRUIT, LICENSE_LINE, SECOND
from jinzai_common import normalize_name

W = {  # 重み
 "転職エージェント":1,"転職サイト":1,"転職支援":1,"転職サービス":1,"中途採用支援":1,"中途採用を支援":1,"中途採用の支援":1,
 "中途採用向け":1,"中途採用サービス":1,"中途人材":1,"中途紹介":1,"中途向け":1,"キャリア採用支援":1,"ハイクラス":1,"ミドル層":1,
 "ミドル人材":1,"人材派遣":1,"派遣サービス":1,"派遣事業":1,"労働者派遣事業":1,"スカウト型転職":1,"転職希望者":1,"転職活動":1,
 "転職相談":1,"転職成功":1,"転職情報":1,"転職求人":1,"中途採用代行":1,"中途採用のご担当":1,
 "中途採用":0.5,"転職":0.5,"キャリア採用":0.5,"経験者採用":0.5,"即戦力人材":0.5,"求人サイト":0.5,
}
NAV_MID = re.compile(r"転職|中途採用(支援|代行)|【中途】|中途採用ご担当|ハイクラス|ミドル")
NAV_SKIP = re.compile(r"採用情報|中途採用$|キャリア採用$|中途採用(はこちら|情報|ページ|サイト|募集|エントリー)")

def analyze2(texts, navs, name):
    hits, snippets, second = {}, [], {}
    for t in texts:
        for line in t.split("\n"):
            l = line.strip()
            if not l or len(l) > 400 or SELF_RECRUIT.search(l) or LICENSE_LINE.search(l):
                continue
            for k in W:
                if k in l:
                    hits[k] = hits.get(k, 0) + 1
                    if len(snippets) < 6 and all(k not in s for s in snippets):
                        snippets.append(l[:80])
            for k in SECOND:
                if k in l:
                    second[k] = second.get(k, 0) + 1
    nav = []
    for n in navs:
        n1 = n.replace("\n", " ")
        if NAV_MID.search(n1) and not NAV_SKIP.search(n1):
            if "doda" in n1 and not re.search(r"ベネッセ|パーソル", name):
                continue  # dodaキャンパス側のナビ混入
            if n1 not in nav:
                nav.append(n1[:30])
    # 重複カウント抑制: 「転職」は「転職〜」複合語と二重に数えるので差し引く
    comp = sum(v for k, v in hits.items() if k.startswith("転職") and k != "転職")
    if "転職" in hits:
        hits["転職"] = max(0, hits["転職"] - comp)
        if hits["転職"] == 0: del hits["転職"]
    comp = sum(v for k, v in hits.items() if k.startswith("中途採用") and k != "中途採用")
    if "中途採用" in hits:
        hits["中途採用"] = max(0, hits["中途採用"] - comp)
        if hits["中途採用"] == 0: del hits["中途採用"]
    score = sum(W[k] * min(v, 5) for k, v in hits.items())
    return hits, second, nav, snippets, score

def judge2(hits, second, nav, score, has_hp):
    kinds = len([k for k in hits if W[k] >= 1])
    why = []
    if nav: why.append("メニューに中途系(" + "/".join(nav[:3]) + ")")
    if hits: why.append("中途語: " + ", ".join(f"{k}{v}" for k, v in sorted(hits.items(), key=lambda x: -x[1])[:6]))
    if second: why.append("第二新卒系語: " + ", ".join(f"{k}{v}" for k, v in second.items()))
    w = "; ".join(why)
    if nav or score >= 4 or (kinds >= 2 and score >= 3) or hits.get("中途採用", 0) >= 5 or hits.get("転職", 0) >= 8:
        return "あり", w
    if not has_hp:
        return "不明", "公式HP特定できず" + ("（" + w + "）" if w else "")
    sec_strong = second.get("第二新卒", 0) >= 2 or second.get("既卒", 0) >= 3 or second.get("フリーター", 0) >= 2 or second.get("20代", 0) >= 3
    if score < 2 and sec_strong:
        return "第二新卒のみ", w
    if score > 0:
        return "なし(要確認)", w + "（中途語が少数のみ）"
    return "なし", "中途向けサービスの記述なし"

# 手動補正: 会社名 → (判定, HP, 理由)   ※HPが空なら既存を維持
OVERRIDE = {
 "パーソルキャリア株式会社": ("あり", "https://www.persol-career.co.jp", "doda（転職）運営"),
 "エン・ジャパン株式会社": ("あり", "https://corp.en-japan.com", "エン転職運営"),
 "株式会社ディスコ": ("あり", "https://www.disc.co.jp", "キャリタス転職あり"),
 "株式会社リクルートキャリア": ("あり", "https://www.recruit.co.jp", "リクルートエージェント等（現リクルート）"),
 "株式会社リクルートホールディングス": ("あり", "https://recruit-holdings.com", "リクルートグループ"),
 "リンクトイン・ジャパン株式会社": ("あり", "https://about.linkedin.com", "LinkedInは中途主体"),
 "パーソルプロセス＆テクノロジー株式会社": ("あり", "https://www.persol-pt.co.jp", "パーソルグループ（派遣/BPO）"),
 "ウォンテッドリー株式会社": ("あり", "https://wantedlyinc.com", "Wantedlyは中途採用でも主要媒体"),
 "株式会社グッドパッチ": ("あり", "https://goodpatch.com", "ReDesigner（中途デザイナー紹介）あり"),
 "株式会社カケハシスカイソリューションズ": ("あり", "https://www.kakehashi-skysol.co.jp", "中途採用支援・中途採用の知恵袋運営"),
 "株式会社i-plug": ("なし", "https://i-plug.co.jp", "OfferBox（新卒）主体。dodaキャンパス連携ナビの誤検知を補正"),
 "株式会社リアライブ": ("第二新卒のみ", "", "ジョブトラ20s（第二新卒）あり"),
 "株式会社Xcuu": ("なし(要確認)", "", "エンジニア採用代行（中途含む可能性）"),
 "株式会社ライボ": ("あり", "https://laibo.jp", "JobQ（転職口コミ）"),
 "株式会社地方ミカタ": ("なし", "", "地方のミカタ（新卒・地方学生）"),
 "株式会社YOUTRUST": ("あり", "", "YOUTRUST（中途向けキャリアSNS）"),
 "株式会社Brotial": ("なし(要確認)", "", "UT-Board（学生向け）。『ハイクラス学生』の語が誤検知"),
 "株式会社ベネッセ": ("あり", "https://www.benesse.co.jp", "ベネッセi-キャリア親会社（doda新卒）"),
}
# 削除（誤抽出・重複）
DROP = {"株式会社カケハシ", "プレイライフ株式会社", "Wantedly株式会社", "ディグ株式会社", "株式会社リクルートキャリア", "株式会社onecareer",
        "レジェンダ・コーポレーション株式会社", "株式会社カケハシ スカイソリューションズ", "株式会社ベネッセ", "株式会社ベースミー", "株式会社ミカタ"}
SVC_NOISE = re.compile(r"^(▶|X|i|UT|HIGH|next»|理由|株式会社|運営者情報|参考文献|新卒|関東|地方|イベント|コンテンツ|出会いの場)$|】|件$|^[①-⑳㉑-㉟]")

def main():
    cands = json.load(open(CAND, encoding="utf-8"))
    prog = json.load(open(PROG, encoding="utf-8"))
    for k in list(cands):
        name = cands[k]["会社名"]
        if name in DROP:
            cands.pop(k); prog.pop(k, None); continue
        # サービス名クリーニング
        cands[k]["サービス名"] = [re.sub(r"(と|に|で|の)$", "", s) for s in cands[k]["サービス名"] if not SVC_NOISE.search(s) and len(s) >= 2]
        cands[k]["サービス名"] = list(dict.fromkeys(cands[k]["サービス名"]))
        v = prog.get(k)
        if not v: continue
        f = os.path.join(TXTDIR, k[:60] + ".json")
        if os.path.exists(f):
            d = json.load(open(f, encoding="utf-8"))
            hits, second, nav, snippets, score = analyze2(d["texts"], d["navs"], name)
            cls, why = judge2(hits, second, nav, score, bool(v["hp"]))
            v.update({"cls": cls, "why": why, "snip": snippets})
        if name in OVERRIDE:
            cls, hp, note = OVERRIDE[name]
            v["cls"] = cls
            if hp: v["hp"] = hp
            v["why"] = "【手動補正】" + note + "｜" + v["why"]
    json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cands, open(CAND, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_excel(cands, prog)

if __name__ == "__main__":
    main()

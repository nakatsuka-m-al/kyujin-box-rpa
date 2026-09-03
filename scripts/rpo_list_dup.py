# -*- coding: utf-8 -*-
"""RPOリスト_完成.xlsx: RPOシートに紹介/派遣投げ込みとの重複フラグを付ける"""
import re, sys, unicodedata
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

XLSX = "/Users/masakatsu/Desktop/kyujin_box_rpa/RPOリスト_完成.xlsx"

def key(s):
    s = unicodedata.normalize("NFKC", str(s or "")).strip()
    s = re.sub(r"[\s　]+", "", s)
    s = re.sub(r"株式会社|有限会社|合同会社|（株）|\(株\)|㈱|（有）|\(有\)", "", s)
    return s.upper()

def dom(u):
    m = re.search(r"https?://(?:www\.)?([^/]+)", str(u or ""))
    return m.group(1).lower() if m else None

def main():
    wb = openpyxl.load_workbook(XLSX)
    rpo, syo, hak = wb["RPO"], wb["紹介投げ込み"], wb["派遣投げ込み"]
    # 照合辞書
    syo_name, syo_dom = {}, {}
    for r in range(2, syo.max_row + 1):
        nm = syo.cell(r, 2).value
        if not nm: continue
        syo_name[key(nm)] = nm
        d = dom(syo.cell(r, 5).value)
        if d: syo_dom[d] = nm
    hak_name, hak_dom = {}, {}
    STAT = {"送信成功", "送信不可", "送信済", "送信失敗"}
    for r in range(2, hak.max_row + 1):
        nm = hak.cell(r, 4).value
        if not nm: continue
        status = ""
        for c in range(24, 30):   # 行によって1列ズレがあるためスキャンで特定
            v = str(hak.cell(r, c).value or "").strip()
            if v in STAT:
                status = v
                break
        hak_name[key(nm)] = (nm, status)
        d = dom(hak.cell(r, 5).value)
        if d: hak_dom[d] = (nm, status)
    # RPOシートにJ列=重複フラグ
    col = 10
    c = rpo.cell(1, col); c.value = "重複"
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", start_color="C00000")
    c.alignment = Alignment(horizontal="center", vertical="center")
    from collections import Counter
    cnt = Counter()
    for r in range(2, rpo.max_row + 1):
        nm = rpo.cell(r, 4).value
        if not nm: continue
        k = key(nm); d = dom(rpo.cell(r, 5).value)
        flag = ""
        if k in syo_name or (d and d in syo_dom):
            flag = "紹介重複"
        hit = hak_name.get(k) or (hak_dom.get(d) if d else None)
        if hit:
            nm2, status = hit
            tag = "派遣重複" if status in ("送信成功", "送信済") else f"派遣リスト掲載({status or '未送信'})"
            flag = (flag + "・" + tag) if flag else tag
        rpo.cell(r, col).value = flag or None
        if flag: cnt[flag] += 1
    wb.save(XLSX)
    total = sum(cnt.values())
    print(f"RPO {rpo.max_row-1}社中 フラグあり {total}社 / 未投げ込み {rpo.max_row-1-total}社")
    for k2, v in cnt.most_common(): print(f"  {v:>3}  {k2}")

if __name__ == "__main__":
    main()

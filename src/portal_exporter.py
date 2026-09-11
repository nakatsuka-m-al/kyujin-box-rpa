"""
応募者ポータル（Web）への取り込みAPI送信。

シートへの書き込みが終わった後に呼ぶ。設定が空なら何もしない。
失敗しても例外を外に出さず、通知だけする（RPA の終了コードを変えない）。
ログに個人情報を出さない（件数のみ）。
1回の送信は200件まで（Vercel のリクエスト上限に収める）。
"""

import logging
import os
import re
from typing import Iterator

import requests

from exporters import SHEETS_COLUMNS, build_ats_key

logger = logging.getLogger(__name__)

BATCH = 200


def _env(name: str, default: str = "") -> str:
    """GitHub Actions は未設定の secrets を空文字で渡すので、空なら既定値"""
    v = os.environ.get(name, "").strip()
    return v if v else default


def route_from_env(default: str = "rpa_scheduled") -> str:
    """ワークフローが渡す PORTAL_ROUTE（rpa_scheduled / rpa_mail_trigger）"""
    return _env("PORTAL_ROUTE", default)


def is_enabled() -> bool:
    return bool(_env("PORTAL_INGEST_URL")) and bool(_env("PORTAL_INGEST_TOKEN"))


def chunked(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


# 求人ボックス: applicants は scraper.parse_csv の出力（SHEETS_COLUMNS のキー + _raw）
_KB_FIELD_KEYS = [c for c in SHEETS_COLUMNS if c not in ("applicant_id", "applied_at", "_subaccount_name")]


def build_kyujinbox_payload(applicants: list[dict], account_by_applicant: dict, route: str) -> dict:
    items = []
    for a in applicants:
        applicant_id = str(a.get("applicant_id") or "").strip()
        if not applicant_id:
            continue
        account_id = str(account_by_applicant.get(applicant_id) or "").strip() or "unknown"
        fields = {k: str(a.get(k) or "") for k in _KB_FIELD_KEYS}
        fields["subaccount_name"] = str(a.get("_subaccount_name") or "")
        items.append({
            "media": "kyujinbox",
            "external_id": account_id,
            "display_name": str(a.get("_subaccount_name") or ""),
            "external_key": applicant_id,
            "applied_at": str(a.get("applied_at") or ""),
            "fields": {k: v for k, v in fields.items() if v},
            "raw": {k: ("" if v is None else str(v)) for k, v in (a.get("_raw") or {}).items()},
        })
    return {"media": "kyujinbox", "route": route, "applicants": items}


# ATS: rows は ats_scraper.parse_csv + enrich_indeed_rows の出力（CSV 列名がキー）
_ATS_FIELD_MAP = {
    "name": "お名前",
    "email": "メールアドレス",
    "phone": "電話番号",
    "job_id": "お仕事ID",
    "subaccount_name": "拠点名・管理NO",
}


def build_ats_payload(rows: list[dict], route: str) -> dict:
    items = []
    for row in rows:
        key = build_ats_key(lambda c: str(row.get(c) or ""))
        if not key.strip("_"):
            continue
        fields = {k: str(row.get(col) or "") for k, col in _ATS_FIELD_MAP.items()}
        items.append({
            "media": "ats",
            "external_id": str(row.get("拠点名・管理NO") or "").strip() or "unknown",
            "display_name": str(row.get("拠点名・管理NO") or ""),
            "external_key": key,
            "applied_at": str(row.get("応募受付日時") or ""),
            "fields": {k: v for k, v in fields.items() if v},
            "raw": {k: ("" if v is None else str(v)) for k, v in row.items()},
        })
    return {"media": "ats", "route": route, "applicants": items}


def send(payload: dict, notifier=None) -> None:
    """取り込みAPIへ200件ずつ送る。失敗は通知して握る。"""
    if not is_enabled():
        logger.info("[portal] 未設定のためスキップ")
        return
    applicants = payload.get("applicants") or []
    if not applicants:
        return
    url = _env("PORTAL_INGEST_URL").rstrip("/") + "/api/ingest"
    headers = {"Authorization": f"Bearer {_env('PORTAL_INGEST_TOKEN')}"}
    total = {"received": 0, "inserted": 0, "skipped": 0, "unassigned": 0}
    failed = 0
    for chunk in chunked(applicants, BATCH):
        try:
            body = {"media": payload["media"], "route": payload["route"], "applicants": chunk}
            r = requests.post(url, json=body, headers=headers, timeout=60)
            if r.status_code >= 300:
                excerpt = re.sub(r"\s+", " ", r.text or "")[:300]
                raise RuntimeError(f"HTTP {r.status_code}: {excerpt}")
            res = r.json()
            for k in total:
                total[k] += int(res.get(k) or 0)
        except Exception as e:  # noqa: BLE001 - 何があっても RPA を止めない
            failed += len(chunk)
            logger.error(f"[portal] 送信に失敗（{len(chunk)} 件分）: {e}")
    logger.info(
        f"[portal] 送信 {total['received']} 件 / 新規 {total['inserted']} / "
        f"既存 {total['skipped']} / 未割当 {total['unassigned']} / 失敗 {failed}"
    )
    if failed and notifier is not None:
        notifier.check(
            "応募者ポータルへの送信に失敗しました",
            f"取り込みAPIへの送信で {failed} 件分が送れませんでした。",
            "シートには書き込み済みなので取り込みは止まっていません。ポータル側にだけ反映されていません。",
            "ポータルの「基盤シートから再取り込み」で該当期間を取り込んでください。",
        )

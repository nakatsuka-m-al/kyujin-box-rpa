"""
応募者ポータル（Web）への実績送信。

report_scraper がシートへ書き終えた後に呼ぶ。設定が空なら何もしない。
失敗しても例外を外に出さず、通知だけする（RPA の終了コードを変えない）。
ログに顧客名・アカウント名を出さない（このリポジトリは公開）。
1回の送信は200行まで。
"""

import logging
import os
import re
from typing import Iterator

import requests

logger = logging.getLogger(__name__)

BATCH = 200


def _env(name: str, default: str = "") -> str:
    """GitHub Actions は未設定の secrets を空文字で渡すので、空なら既定値"""
    v = os.environ.get(name, "").strip()
    return v if v else default


def is_enabled() -> bool:
    return bool(_env("PORTAL_INGEST_URL")) and bool(_env("PORTAL_INGEST_TOKEN"))


def chunked(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def month_of(term: str) -> str:
    """"202608" → "2026-08" """
    t = str(term or "").strip()
    if not re.fullmatch(r"\d{6}", t):
        raise ValueError(f"対象月の形式が不正です: '{t}'")
    return f"{t[:4]}-{t[4:6]}"


def _int(text) -> int | None:
    """"¥113,653" → 113653 / "-" → None / 負の数は None（1チャンク200行が丸ごと落ちるのを防ぐ）"""
    s = re.sub(r"[¥,\s]", "", str(text if text is not None else "").strip())
    if s in ("", "-", "―"):
        return None
    try:
        v = int(float(s))
    except ValueError:
        return None
    return None if v < 0 else v


def _rate(text) -> float | None:
    """"4.0%" → 0.04 / "0.04" → 0.04 / "-" → None"""
    s = str(text if text is not None else "").strip().replace(",", "")
    if s in ("", "-", "―"):
        return None
    percent = s.endswith("%")
    s = s.rstrip("%")
    try:
        v = float(s)
    except ValueError:
        return None
    if percent:
        v = v / 100
    if v < 0:
        return None
    return round(v, 5)


def build_payload(items: list[dict], route: str = "rpa_scheduled") -> dict:
    """report_scraper.fetch_month の出力（term / account_id / account_name / raw）を送信形にする"""
    rows = []
    for item in items:
        account_id = str(item.get("account_id") or "").strip()
        if not account_id:
            continue
        raw = item.get("raw") or {}
        rows.append({
            "month": month_of(item.get("term")),
            "external_id": account_id,
            "account_name": str(item.get("account_name") or "") or None,
            "jobs": _int(raw.get("求人数")),
            "public_jobs": _int(raw.get("公開中")),
            "impressions": _int(raw.get("表示回数")),
            "clicks": _int(raw.get("クリック数")),
            "ctr": _rate(raw.get("CTR")),
            "applications": _int(raw.get("応募数")),
            "cvr": _rate(raw.get("CVR")),
            "avg_cpc": _int(raw.get("平均CPC")),
            "cost": _int(raw.get("費用")),
        })
    return {"channel": "kyujinbox", "route": route, "rows": rows}


def send(payload: dict, notifier=None) -> None:
    """実績の取り込みAPIへ200行ずつ送る。失敗は通知して握る。"""
    if not is_enabled():
        logger.info("[portal] 未設定のためスキップ")
        return
    rows = payload.get("rows") or []
    if not rows:
        return
    url = _env("PORTAL_INGEST_URL").rstrip("/") + "/api/stats"
    headers = {"Authorization": f"Bearer {_env('PORTAL_INGEST_TOKEN')}"}
    total = {"received": 0, "upserted": 0, "accounts_created": 0}
    failed = 0
    for chunk in chunked(rows, BATCH):
        try:
            body = {"channel": payload["channel"], "route": payload["route"], "rows": chunk}
            r = requests.post(url, json=body, headers=headers, timeout=60)
            if r.status_code >= 300:
                # 応答本文はログに出さない（このリポジトリは公開）。status_code だけ
                raise RuntimeError(f"HTTP {r.status_code}")
            res = r.json()
            for k in total:
                total[k] += int(res.get(k) or 0)
        except Exception as e:  # noqa: BLE001 - 何があっても RPA を止めない
            failed += len(chunk)
            logger.error(f"[portal] 実績の送信に失敗（{len(chunk)} 行分）: {e}")
    logger.info(
        f"[portal] 実績 {total['received']} 行 / 反映 {total['upserted']} / "
        f"新規アカウント {total['accounts_created']} / 失敗 {failed}"
    )
    if failed and notifier is not None:
        notifier.check(
            "応募者ポータルへの実績送信に失敗しました",
            f"実績の取り込みAPIへの送信で {failed} 行分が送れませんでした。",
            "スプレッドシートには書き込み済みなので、シート側の数字は最新です。ポータルの請求集計だけが古いままです。",
            "次の実行で同じ月を送り直すので、続けて失敗する場合だけ調べてください。",
        )

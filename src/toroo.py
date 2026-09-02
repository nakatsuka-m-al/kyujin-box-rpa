"""
Toroo（トルー）への応募者登録。

求人ボックスの応募CSVを、そのままトルーの応募者として登録する。

必要な環境変数:
  TOROO_CLIENT_ID      企業管理画面から取得（TorooSyncAPIオプション契約が前提）
  TOROO_API_SECRET     同上
  TOROO_ACCOUNT_IDS    連携対象の求人ボックスアカウントID。カンマ区切り
                       例: "3610-5384,1234-5678"

未確認のまま実装している点:
  - 求人IDの照合が完全一致か部分一致か（トルー社に確認中）
  - 同じ応募者を2回登録したときの挙動（同上）
  ここが分かるまでは、二重送信をこちら側で確実に止める作りにしている。
"""

import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    """
    環境変数を読む。

    GitHub Actions は未設定の secrets / vars を「空文字」として渡すため、
    os.environ.get の第2引数（既定値）が効かない。空なら既定値を使う。
    """
    return os.environ.get(name, "").strip() or default


BASE = "https://toroo.jp/api/toroo_sync"
TIMEOUT = 30

CLIENT_ID = _env("TOROO_CLIENT_ID")
API_SECRET = _env("TOROO_API_SECRET")

ACCOUNT_IDS = {
    a.strip()
    for a in os.environ.get("TOROO_ACCOUNT_IDS", "").split(",")
    if a.strip()
}

# 応募経路。トルー側で定義されている値を使う。
#   93  求人ボックス (オーガニック)  無料掲載
#   94  求人ボックス (広告)          スポンサー求人＝有料掲載
#   128 求人ボックス（代理店）        代理店経由
#
# 直接投稿の有料枠からの応募なので既定は94。
# 代理店別に集計したい場合は128に変える。環境変数で上書きできる。
RECRUITMENT_ROUTE_ID = int(_env("TOROO_ROUTE_ID", "94"))

# トークンは最終アクセスから24時間有効。実行のたびに取り直す必要はない
TOKEN_CACHE = Path(_env("TOROO_TOKEN_CACHE", "toroo_token.json"))


class TorooError(Exception):
    """呼び出し側で通知の文面を変えるため、種類を持たせる"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # auth / network / rejected / unknown_result / not_found / ambiguous


def is_enabled() -> bool:
    return bool(CLIENT_ID and API_SECRET and ACCOUNT_IDS)


def is_target(account_id: str) -> bool:
    return str(account_id or "").strip() in ACCOUNT_IDS


def _json(res) -> dict:
    """
    応答を辞書にする。JSON でなければ空の辞書を返す。

    登録が成功したのに本文が空だと res.json() が例外を投げる。
    それを呼び出し側が失敗と受け取ると、記録が残らないまま
    次回もう一度同じ人を送ってしまう。二重登録を避けるため、
    ここで握りつぶして「本文なしの成功」として扱う。
    """
    try:
        return res.json() or {}
    except ValueError:
        logger.warning(f"JSONとして読めない応答でした: {res.text[:200]!r}")
        return {}


# ─── 認証 ────────────────────────────────────────────────────────────────────

def _load_token() -> str:
    if not TOKEN_CACHE.exists():
        return ""
    try:
        data = json.loads(TOKEN_CACHE.read_text())
    except Exception:
        return ""
    # 24時間ぎりぎりで使うと途中で切れるので、余裕をみて23時間で捨てる
    if time.time() - data.get("at", 0) > 23 * 3600:
        return ""
    return data.get("access_token", "")


def _save_token(token: str) -> None:
    try:
        TOKEN_CACHE.write_text(
            json.dumps({"access_token": token, "at": time.time()}, ensure_ascii=False)
        )
    except Exception as e:
        # 保存できなくても毎回取り直せば動く
        logger.warning(f"トークンを保存できませんでした: {e}")


def get_token(force: bool = False) -> str:
    if not force:
        cached = _load_token()
        if cached:
            return cached

    try:
        res = requests.post(
            f"{BASE}/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "api_secret": API_SECRET,
            },
            timeout=TIMEOUT,
        )
    except Exception as e:
        raise TorooError("network", f"トークン取得で接続に失敗しました: {e}")

    if res.status_code == 401 or res.status_code == 403:
        raise TorooError("auth", f"認証情報が受け付けられませんでした（{res.status_code}）")
    if res.status_code >= 300:
        raise TorooError("network", f"トークン取得に失敗しました: {res.status_code} {res.text[:200]}")

    token = _json(res).get("access_token", "")
    if not token:
        raise TorooError("auth", "トークンが返ってきませんでした")
    _save_token(token)
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-Toroo-Client-Id": CLIENT_ID,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, **kw):
    """401 なら1回だけトークンを取り直して再試行する"""
    token = get_token()
    try:
        res = requests.request(
            method, f"{BASE}{path}", headers=_headers(token), timeout=TIMEOUT, **kw
        )
    except requests.Timeout as e:
        raise TorooError("unknown_result", f"応答がありませんでした: {e}")
    except Exception as e:
        raise TorooError("network", f"接続に失敗しました: {e}")

    if res.status_code == 401:
        token = get_token(force=True)
        try:
            res = requests.request(
                method, f"{BASE}{path}", headers=_headers(token), timeout=TIMEOUT, **kw
            )
        except requests.Timeout as e:
            raise TorooError("unknown_result", f"応答がありませんでした: {e}")
        except Exception as e:
            raise TorooError("network", f"接続に失敗しました: {e}")
        if res.status_code == 401:
            raise TorooError("auth", "トークンを取り直しても認証されませんでした")
    return res


# ─── 求人ID の解決 ────────────────────────────────────────────────────────────

def resolve_recruitment_id(job_label: str, job_title: str) -> str:
    """
    応募先の求人に対応するトルーの求人IDを決める。

    1. 求人ボックスの求人ラベルに入っている値を使う（確実）
    2. 無ければ求人検索APIで求人タイトルから引く

    トルーの求人IDは「ID / 職種 / 都道府県・市区町村 / 求人タイトル」を
    つないだ文字列で、求人ラベルの20文字制限には収まらない。
    そのためラベルには数字部分だけを入れる運用にしている。
    """
    label = str(job_label or "").strip()
    if label:
        # ラベルには複数の値がカンマで入りうる。数字だけのものを求人IDとみなす。
        # ハイフンを含む 9129-0641 のような値は求人ボックス側のIDなので拾わない
        for part in label.replace("，", ",").split(","):
            part = part.strip()
            if part.isdigit():
                return part

    title = str(job_title or "").strip()
    if not title:
        raise TorooError("not_found", "求人ラベルが空で、求人タイトルもありません")

    # search_word は配列。title または work_content への部分一致（OR検索）。
    # 求人IDでの検索はできないため、ラベルが空のときはタイトルで引くしかない
    res = _request(
        "POST", "/v2/jobs/search",
        json={"search_word": [title], "preview": True, "per": 30},
    )
    if res.status_code >= 300:
        raise TorooError("network", f"求人検索に失敗しました: {res.status_code} {res.text[:200]}")

    results = _json(res).get("results", []) or []
    if not results:
        raise TorooError("not_found", f"「{title}」に一致する求人が見つかりませんでした")
    if len(results) > 1:
        names = " / ".join(str(r.get("title", "")) for r in results[:5])
        raise TorooError("ambiguous", f"候補が {len(results)} 件ありました: {names}")

    return str(results[0].get("id", ""))


# ─── 応募者登録 ───────────────────────────────────────────────────────────────

GENDER_MAP = {"男性": 1, "女性": 0}


def build_payload(applicant: dict, recruitment_id: str) -> dict:
    raw = applicant.get("_raw") or {}

    payload = {
        "name": str(applicant.get("name") or "").strip(),
        "offer_date": _to_datetime(applicant.get("applied_at")),
        "recruitment_id": recruitment_id,
        "recruitment_route_id": RECRUITMENT_ROUTE_ID,
        "applicant_detail": {},
    }

    birthday = _to_date(applicant.get("birthdate"))
    if birthday:
        payload["birthday"] = birthday

    gender = GENDER_MAP.get(str(applicant.get("gender") or "").strip())
    if gender is not None:
        payload["gender"] = gender

    for key, field in (
        ("email", "email"),
        ("phone", "phone_number"),
        ("work_history", "job_career"),
    ):
        value = str(applicant.get(key) or "").strip()
        if value:
            payload[field] = value

    for key, field in (
        ("address", "address"),
        ("message", "self_promotion"),
        ("education", "graduate_school"),
    ):
        value = str(applicant.get(key) or "").strip()
        if value:
            payload["applicant_detail"][field] = value

    # 勤務先_1〜30 を配列にする。結合した文字列より扱いやすい
    history = []
    for i in range(1, 31):
        company = str(raw.get(f"勤務先_{i}", "")).strip()
        role = str(raw.get(f"役職・業務内容など_{i}", "")).strip()
        if company:
            history.append({"company_name": company, "job_description": role})
    if history:
        payload["work_history"] = history

    return payload


def create_applicant(applicant: dict, recruitment_id: str) -> dict:
    res = _request("POST", "/v1/applicants", json=build_payload(applicant, recruitment_id))

    if res.status_code == 400:
        raise TorooError("rejected", f"登録を拒否されました: {res.text[:300]}")
    if res.status_code >= 500:
        # 登録されたかどうか分からない。二重送信を避けるため成功扱いにしない。
        # 本文には原因が書かれていることがあるので残す。400と同じ扱い
        raise TorooError(
            "unknown_result", f"サーバーエラー: {res.status_code} {res.text[:300]}"
        )
    if res.status_code >= 300:
        raise TorooError("network", f"登録に失敗しました: {res.status_code} {res.text[:200]}")

    return _json(res)


# ─── 書式 ────────────────────────────────────────────────────────────────────

def _to_datetime(value: str) -> str:
    """
    「2026/08/23 22:30」→「2026-08-23 22:30:00」

    仕様書に3種類の書式が混在しているため、まず一般的な形で送り、
    実際に叩いて弾かれたら合わせる。
    """
    import re

    text = str(value or "").strip()
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})", text)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:00"
    date = _to_date(text)
    return f"{date} 00:00:00" if date else text


def _to_date(value: str) -> str:
    """「1993年07月23日 (33歳)」→「1993-07-23」"""
    import re

    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(value or ""))
    if not m:
        return ""
    y, mo, d = (int(x) for x in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"

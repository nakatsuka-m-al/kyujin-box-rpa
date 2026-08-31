"""
Toroo API の疎通確認。読み取り専用で、どこにも書き込まない。

テストのフェーズ1で使う。求人ボックスのアカウントが無くても実行できる。

確認できること:
  1. 認証が通るか（client_id / api_secret が正しいか）
  2. 求人を取得できるか
  3. **求人IDの実物**（形式・桁数・求人ラベルの20文字に収まるか）
  4. 求人検索が求人IDや職種で当たるか

必要な環境変数:
  TOROO_CLIENT_ID / TOROO_API_SECRET
  TOROO_SEARCH_WORD  検索の動きを試したいとき。省略可
"""

import json
import logging
import os
import sys

import toroo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 求人ボックスの求人ラベルの上限。ここに収まるかが設計の分かれ目
LABEL_LIMIT = 20


def mask(value: str) -> str:
    """秘密情報はログに出さない。設定されているかだけ分かればよい"""
    if not value:
        return "（未設定）"
    return f"{value[:4]}…{value[-2:]}（{len(value)}文字）"


def check_auth() -> bool:
    logger.info("=" * 60)
    logger.info("1. 認証")
    logger.info("=" * 60)
    logger.info(f"クライアントID: {mask(toroo.CLIENT_ID)}")
    logger.info(f"APIシークレット: {mask(toroo.API_SECRET)}")

    if not toroo.CLIENT_ID or not toroo.API_SECRET:
        logger.error("認証情報が設定されていません。Secretsを確認してください")
        return False

    try:
        token = toroo.get_token(force=True)
    except toroo.TorooError as e:
        logger.error(f"認証に失敗しました（{e.kind}）: {e}")
        return False

    logger.info(f"認証に成功しました。トークン: {mask(token)}")
    return True


def check_jobs() -> list:
    logger.info("")
    logger.info("=" * 60)
    logger.info("2. 求人の取得")
    logger.info("=" * 60)

    jobs = []
    page = 1
    while page <= 10:  # 暴走よけ
        body = {"preview": True, "page": page}
        word = os.environ.get("TOROO_SEARCH_WORD", "").strip()
        if word:
            body["search_word"] = word

        try:
            res = toroo._request("POST", "/v2/jobs/search", json=body)
        except toroo.TorooError as e:
            logger.error(f"求人検索に失敗しました（{e.kind}）: {e}")
            return jobs

        if res.status_code >= 300:
            logger.error(f"求人検索が {res.status_code} を返しました: {res.text[:400]}")
            return jobs

        data = res.json() or {}
        results = data.get("results", []) or []
        jobs.extend(results)
        logger.info(f"{page}ページ目: {len(results)} 件")

        if not data.get("more_flg"):
            break
        page += 1

    logger.info(f"合計 {len(jobs)} 件")

    if jobs:
        logger.info("")
        logger.info("--- レスポンスの1件目（項目を確認する）---")
        logger.info(json.dumps(jobs[0], ensure_ascii=False, indent=2)[:3000])

    return jobs


def check_ids(jobs: list) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info("3. 求人IDの形式")
    logger.info("=" * 60)

    if not jobs:
        logger.warning("求人が0件のため確認できません。Toroo側にテスト求人を作ってください")
        return

    over = 0
    for job in jobs[:20]:
        job_id = str(job.get("id", ""))
        title = str(job.get("title", ""))[:30]
        public = "公開" if job.get("is_public") else "非公開"
        fits = len(job_id) <= LABEL_LIMIT
        if not fits:
            over += 1
        mark = "" if fits else "  ← 求人ラベルに収まりません"
        logger.info(f"  id={job_id!r} ({len(job_id)}文字) {public}  {title}{mark}")

    logger.info("")
    if over == 0:
        logger.info(
            f"すべての求人IDが {LABEL_LIMIT} 文字以内でした。"
            "求人ラベルにそのまま入れられます"
        )
    else:
        logger.warning(
            f"{over} 件が {LABEL_LIMIT} 文字を超えています。"
            "求人ラベルに入れられないため、検索APIでの解決が必要です"
        )


def check_search(jobs: list) -> None:
    """求人IDだけで引けるか。部分一致が効くかを見る"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("4. 求人IDでの検索")
    logger.info("=" * 60)

    if not jobs:
        logger.warning("求人が0件のため確認できません")
        return

    job_id = str(jobs[0].get("id", ""))
    logger.info(f"検索語に求人ID {job_id!r} を渡してみます")

    try:
        res = toroo._request("POST", "/v2/jobs/search", json={"search_word": job_id, "preview": True})
    except toroo.TorooError as e:
        logger.error(f"検索に失敗しました: {e}")
        return

    if res.status_code >= 300:
        logger.error(f"{res.status_code} を返しました: {res.text[:300]}")
        return

    results = (res.json() or {}).get("results", []) or []
    logger.info(f"結果: {len(results)} 件")
    if len(results) == 1 and str(results[0].get("id")) == job_id:
        logger.info("求人IDだけで1件に絞れました。この方式が使えます")
    elif not results:
        logger.warning("求人IDでは引けませんでした。求人タイトルでの検索が必要です")
    else:
        logger.warning(f"{len(results)} 件ヒットしました。一意に決まりません")


def main() -> None:
    ok = check_auth()
    if not ok:
        sys.exit(1)

    jobs = check_jobs()
    check_ids(jobs)
    check_search(jobs)

    logger.info("")
    logger.info("=" * 60)
    logger.info("疎通確認が完了しました。書き込みは一切していません")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

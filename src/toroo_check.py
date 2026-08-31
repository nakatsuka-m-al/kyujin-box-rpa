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

import logging
import os
import sys

import toroo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 求人ボックスの求人ラベルの上限。ここに収まるかが設計の分かれ目
LABEL_LIMIT = 20

# 取得するページ数の上限。暴走よけ。per=30 なので 100ページで3000件
MAX_PAGES = 100


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


def count_jobs() -> int:
    """
    求人の総数を調べる。

    全ページ取るとページ数に比例して時間がかかるので、
    「そのページに結果があるか」を二分探索して最終ページを見つける。
    3000件なら100回のリクエストが、10回程度で済む。
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("2-1. 求人の総数")
    logger.info("=" * 60)

    def has_results(page: int) -> bool:
        res = toroo._request(
            "POST", "/v2/jobs/search",
            json={"preview": True, "page": page, "per": 30},
        )
        if res.status_code >= 300:
            return False
        return bool((res.json() or {}).get("results"))

    if not has_results(1):
        logger.info("求人は0件です")
        return 0

    # 上限を倍々で広げて、結果が無くなるページを探す
    low, high = 1, 2
    while has_results(high):
        low = high
        high *= 2
        if high > 100000:
            break

    # low には結果があり、high には無い。境界を挟み撃ちにする
    while high - low > 1:
        mid = (low + high) // 2
        if has_results(mid):
            low = mid
        else:
            high = mid

    logger.info(f"最終ページ: {low}（1ページ30件）")
    logger.info(f"求人はおよそ {(low - 1) * 30 + 1}〜{low * 30} 件です")
    return low


def check_jobs() -> list:
    logger.info("")
    logger.info("=" * 60)
    logger.info("2. 求人の取得")
    logger.info("=" * 60)

    jobs = []
    page = 1
    truncated = False
    while True:
        if page > MAX_PAGES:
            truncated = True
            break
        # per は最大30。1回あたりの件数を増やしてページ数を減らす
        body = {"preview": True, "page": page, "per": 30}
        word = os.environ.get("TOROO_SEARCH_WORD", "").strip()
        if word:
            body["search_word"] = [word]   # 配列で渡す

        try:
            res = toroo._request("POST", "/v2/jobs/search", json=body)
        except toroo.TorooError as e:
            logger.error(f"求人検索に失敗しました（{e.kind}）: {e}")
            return jobs

        if res.status_code >= 300:
            # エラー本文にも求人の情報が入りうるため、状態コードだけを出す
            logger.error(f"求人検索が {res.status_code} を返しました")
            return jobs

        data = res.json() or {}
        results = data.get("results", []) or []
        jobs.extend(results)
        logger.info(f"{page}ページ目: {len(results)} 件")

        if not data.get("more_flg"):
            break
        page += 1

    logger.info(f"合計 {len(jobs)} 件")
    if truncated:
        logger.warning(
            f"{MAX_PAGES} ページで打ち切りました。まだ続きがあります。"
            "実際の求人数はこれより多いです"
        )

    # 求人票の中身はログに出さない。
    # このリポジトリは公開で、実行ログは誰でも読める。
    # 非公開求人も含まれるため、項目名だけを出して中身は伏せる。
    if jobs:
        logger.info("")
        logger.info("--- レスポンスに含まれる項目名 ---")
        logger.info(", ".join(sorted(jobs[0].keys())))

    return jobs


def check_ids(jobs: list) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info("3. 求人IDの形式")
    logger.info("=" * 60)

    if not jobs:
        logger.warning("求人が0件のため確認できません。Toroo側にテスト求人を作ってください")
        return

    # 求人IDと桁数だけを出す。求人タイトルは出さない
    over = 0
    lengths = {}
    public_count = 0
    for job in jobs:
        job_id = str(job.get("id", ""))
        if job.get("is_public"):
            public_count += 1
        lengths[len(job_id)] = lengths.get(len(job_id), 0) + 1
        if len(job_id) > LABEL_LIMIT:
            over += 1

    logger.info(f"公開 {public_count} 件 / 非公開 {len(jobs) - public_count} 件")
    logger.info("求人IDの桁数の内訳:")
    for n in sorted(lengths):
        mark = "" if n <= LABEL_LIMIT else "  ← 求人ラベルに収まりません"
        logger.info(f"  {n}文字: {lengths[n]} 件{mark}")

    sample = str(jobs[0].get("id", ""))
    logger.info(f"求人IDの例: {sample!r}（形式の確認用に1件だけ）")

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
    """
    求人タイトルで検索して、1件に絞れるかを見る。

    求人IDでの検索はできない（search_word は title と work_content にしか効かない）。
    求人ラベルが空だったときの受け皿として、タイトル検索が使えるかを確かめる。
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("4. 求人タイトルでの検索")
    logger.info("=" * 60)

    if not jobs:
        logger.warning("求人が0件のため確認できません")
        return

    target = jobs[0]
    title = str(target.get("title", "")).strip()
    if not title:
        logger.warning("1件目に求人タイトルがありません")
        return

    logger.info("1件目の求人タイトルで検索してみます（タイトルはログに出しません）")

    try:
        res = toroo._request(
            "POST", "/v2/jobs/search",
            json={"search_word": [title], "preview": True, "per": 30},
        )
    except toroo.TorooError as e:
        logger.error(f"検索に失敗しました: {e}")
        return

    if res.status_code >= 300:
        logger.error(f"{res.status_code} を返しました")
        return

    results = (res.json() or {}).get("results", []) or []
    logger.info(f"結果: {len(results)} 件")

    if len(results) == 1:
        logger.info("1件に絞れました。ラベルが空でもタイトルから解決できます")
    elif not results:
        logger.warning("引けませんでした。ラベルが空の求人は解決できません")
    else:
        logger.warning(
            f"{len(results)} 件ヒットしました。タイトルだけでは一意に決まりません。"
            "求人ラベルへのID入力が必須です"
        )


def main() -> None:
    ok = check_auth()
    if not ok:
        sys.exit(1)

    count_jobs()

    if os.environ.get("TOROO_COUNT_ONLY", "").strip():
        logger.info("")
        logger.info("総数のみ確認しました")
        return

    jobs = check_jobs()
    check_ids(jobs)
    check_search(jobs)

    logger.info("")
    logger.info("=" * 60)
    logger.info("疎通確認が完了しました。書き込みは一切していません")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

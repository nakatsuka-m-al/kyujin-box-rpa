"""
Toroo に架空の応募者を1件だけ登録する。テストのフェーズ1で使う。

求人ボックスには一切ログインしない。シートにも書かない。
実在の応募者は扱わず、ここで作った架空データだけを送る。

必要な環境変数:
  TOROO_CLIENT_ID / TOROO_API_SECRET
  TOROO_TEST_RECRUITMENT_ID  先方に作ってもらうテスト求人のID
  APPLICANT_MAIL_TO          メールも試すとき（省略可）

求人IDを workflow_dispatch の入力ではなく Secret にしているのは、
入力値が公開リポジトリの実行画面にそのまま残るため。
先方の求人情報は外に出さない。
"""

import json
import logging
import os
import sys

import applicant_mail
import toroo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 架空の応募者。本番の scraper が組み立てるものと同じ形にしてある。
# 実在しないと分かる名前・番号にする。
DUMMY = {
    "applicant_id": "TEST-0001",
    "name": "検証 太郎",
    "gender": "男性",
    "birthdate": "1990年01月23日 (36歳)",
    "current_job": "テスト",
    "phone": "09000000000",
    "email": "test@example.com",
    "address": "東京都テスト区テスト1-2-3",
    "education": "テスト大学",
    "applied_at": "2026/09/01 12:00",
    "job_title": "【テスト】連携確認用",
    "message": "これは連携確認のためのテストデータです。実在の応募者ではありません。",
    "work_history": (
        "テスト株式会社（2015年4月〜2020年3月）／営業 → "
        "サンプル商事（2020年4月〜現在）／店舗運営"
    ),
    "_raw": {
        "勤務先_1": "テスト株式会社",
        "役職・業務内容など_1": "営業",
        "勤務先_2": "サンプル商事",
        "役職・業務内容など_2": "店舗運営",
    },
}


def main() -> None:
    recruitment_id = os.environ.get("TOROO_TEST_RECRUITMENT_ID", "").strip()
    confirm = os.environ.get("CONFIRM", "").strip()
    with_mail = os.environ.get("WITH_MAIL", "").strip()

    if not toroo.CLIENT_ID or not toroo.API_SECRET:
        logger.error("TOROO_CLIENT_ID / TOROO_API_SECRET が未設定です")
        sys.exit(1)
    if not recruitment_id:
        logger.error(
            "TOROO_TEST_RECRUITMENT_ID が未設定です。"
            "先方に作ってもらったテスト求人のIDを Secrets に入れてください"
        )
        sys.exit(1)

    payload = toroo.build_payload(DUMMY, recruitment_id)

    logger.info("=" * 60)
    logger.info("Toroo に送る内容（すべて架空データ）")
    logger.info("=" * 60)
    # recruitment_id は先方の情報なので伏せる。桁数だけ出す
    shown = dict(payload)
    shown["recruitment_id"] = f"（{len(recruitment_id)}文字。ログには出しません）"
    logger.info(json.dumps(shown, ensure_ascii=False, indent=2))

    if confirm != "SEND":
        logger.info("")
        logger.info("下書きのみで終了しました。まだ何も登録していません。")
        logger.info("実際に送るには confirm に SEND と入力して再実行してください")
        return

    logger.info("")
    logger.info("登録します")
    try:
        result = toroo.create_applicant(DUMMY, recruitment_id)
    except toroo.TorooError as e:
        logger.error(f"登録に失敗しました（{e.kind}）: {e}")
        sys.exit(1)

    logger.info(f"登録しました。応答: {json.dumps(result, ensure_ascii=False)[:300]}")

    if with_mail:
        if not applicant_mail.MAIL_TO:
            logger.warning("APPLICANT_MAIL_TO が未設定のためメールは送りません")
        else:
            logger.info(f"メールを送ります（宛先 {len(applicant_mail.MAIL_TO)} 件）")
            try:
                mail_id = applicant_mail.send(DUMMY)
                logger.info(f"送信しました: {mail_id}")
            except Exception as e:
                logger.error(f"メール送信に失敗しました: {e}")
                sys.exit(1)

    logger.info("")
    logger.info("=" * 60)
    logger.info("完了しました。Torooの管理画面で「検証 太郎」を確認してください")
    logger.info("確認が済んだら、テスト求人ごと消してもらって構いません")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

"""
Toroo に架空の応募者を1件だけ登録する。テストのフェーズ1で使う。

求人ボックスには一切ログインしない。シートにも書かない。
実在の応募者は扱わず、ここで作った架空データだけを送る。

本番と同じ経路を通す。求人IDは求人ラベルから取り出す。
本番の scraper.deliver() は求人ラベルしか持っていないため、
ここで直接 recruitment_id を渡してしまうと、最初に効く解決処理を
一度も試さないまま本番を迎えることになる。

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

def _now() -> str:
    """日本時間の現在時刻。GitHub Actions は UTC で動くため9時間足す"""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y/%m/%d %H:%M")


# 架空の応募者。求人ボックスの応募CSVを scraper.parse_csv() に通した後の形と
# そろえてある（COLUMN_MAP の全項目 + work_history + _raw）。
# 実在しないと分かる名前・番号にする。
#
# work_history は parse_csv と同じ組み立て方にする:
#   「勤務先_N／役職・業務内容など_N」を " → " でつなぐ。
#   期間は CSV に無いため入れない。
DUMMY = {
    "applicant_id": "TEST-0001",
    # 実行した時刻。固定値だと「なぜ昨日なのか」と混乱のもとになる。
    # 本番は求人ボックスの応募CSVの「応募日時」がそのまま入る
    "applied_at": _now(),
    "name": "検証 太郎",
    "gender": "男性",
    "birthdate": "1990年01月23日 (36歳)",
    "current_job": "テスト",
    "phone": "09000000000",
    "email": "test@example.com",
    "address": "東京都テスト区テスト1-2-3",
    "education": "テスト大学",
    "message": "これは連携確認のためのテストデータです。実在の応募者ではありません。",
    "job_title": "【テスト】連携確認用",
    "job_id": "0000-0000",
    "status": "未対応",
    "selection_comment": "",
    # 本番はここから Toroo の求人IDを取り出す。実行時に埋める
    "job_label": "",
    "work_history": "テスト株式会社／営業 → サンプル商事／店舗運営",
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

    # 本番と同じ形にする。求人ボックスの応募CSVには求人ラベルが入ってくるので、
    # ここでも求人ラベルに入れて、そこから取り出せるかを確かめる。
    #
    # 実際のラベルは求人ボックス側のIDと併記されることがあるため、
    # 数字だけを拾えるかも同時に試す。
    applicant = dict(DUMMY)
    applicant["job_label"] = f"{applicant['job_id']},{recruitment_id}"

    logger.info("=" * 60)
    logger.info("1. 求人ラベルから Toroo の求人IDを取り出す")
    logger.info("=" * 60)
    logger.info("求人ラベルには「求人ボックスのID, Torooの求人ID」を入れています")

    try:
        resolved = toroo.resolve_recruitment_id(
            applicant.get("job_label", ""), applicant.get("job_title", "")
        )
    except toroo.TorooError as e:
        logger.error(f"求人IDを解決できませんでした（{e.kind}）: {e}")
        sys.exit(1)

    if resolved != recruitment_id:
        logger.error(
            "取り出した求人IDが Secrets の値と一致しません。"
            f"（取り出した値は {len(resolved)} 文字）"
        )
        sys.exit(1)
    logger.info("求人ラベルから正しく取り出せました")

    payload = toroo.build_payload(applicant, resolved)

    if os.environ.get("MINIMAL", "").strip():
        # 切り分け用。仕様書で必須とされている項目だけに削る。
        # ここで通れば、原因はこちらが足した任意項目のどれかに絞れる。
        keep = {"name", "offer_date", "recruitment_id"}
        payload = {k: v for k, v in payload.items() if k in keep}
        logger.info("最小構成で送ります（必須項目のみ）")

    logger.info("")
    logger.info("=" * 60)
    logger.info("2. Toroo に送る内容（すべて架空データ）")
    logger.info("=" * 60)
    # recruitment_id は先方の情報なので伏せる。桁数だけ出す
    shown = dict(payload)
    shown["recruitment_id"] = f"（{len(resolved)}文字。ログには出しません）"
    logger.info(json.dumps(shown, ensure_ascii=False, indent=2))

    if confirm != "SEND":
        logger.info("")
        logger.info("下書きのみで終了しました。まだ何も登録していません。")
        logger.info("実際に送るには confirm に SEND と入力して再実行してください")
        return

    logger.info("")
    logger.info("=" * 60)
    logger.info("3. 応募者を登録")
    logger.info("=" * 60)
    try:
        result = toroo.post_applicant(payload)
    except toroo.TorooError as e:
        logger.error(f"登録に失敗しました（{e.kind}）: {e}")
        sys.exit(1)

    logger.info(f"登録しました。応答: {json.dumps(result, ensure_ascii=False)[:300]}")

    if with_mail:
        logger.info("")
        logger.info("=" * 60)
        logger.info("4. 応募通知メール")
        logger.info("=" * 60)
        if not applicant_mail.MAIL_TO:
            logger.warning("APPLICANT_MAIL_TO が未設定のためメールは送りません")
        else:
            logger.info(f"送ります（宛先 {len(applicant_mail.MAIL_TO)} 件）")
            try:
                mail_id = applicant_mail.send(applicant)
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

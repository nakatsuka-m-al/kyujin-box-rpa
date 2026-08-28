"""
エラー通知。Resend でメールを送る。

なぜ独立させているか:
  これまで障害の通知は GitHub と Apps Script の標準メールに頼っていた。
  英語で、件名からは深刻度も原因も分からず、開いてログを追わないと
  対処すべきかどうか判断できなかった。

  ここでは「何が起きたか・影響・対処」を日本語で書いて送る。
  件名の先頭に【至急】【要確認】を付け、クライアント固有の処理は
  クライアント名も入れて、開かずに判断できるようにする。

必要な環境変数:
  RESEND_API_KEY  未設定ならログに出すだけで、処理は止めない
  NOTIFY_TO       通知の宛先。カンマ区切りで複数可
  NOTIFY_FROM     差出人。既定は Oubo Pay通知 <oubopay@blaze-ltd.com>
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"

API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
NOTIFY_TO = [a.strip() for a in os.environ.get("NOTIFY_TO", "").split(",") if a.strip()]
NOTIFY_FROM = os.environ.get(
    "NOTIFY_FROM", "Oubo Pay通知 <oubopay@blaze-ltd.com>"
).strip()

# 深刻度
URGENT = "至急"      # データが失われている、または止まっている
CHECK = "要確認"     # 一部だけ失敗。次回の実行で回復する見込み

TIMEOUT = 20


def send_mail_from(
    sender: str, to: list[str], subject: str, html: str, text: str
) -> str:
    """Resend で1通送る。送信IDを返す。失敗したら例外を投げる"""
    if not API_KEY:
        raise RuntimeError("RESEND_API_KEY が未設定です")
    if not to:
        raise RuntimeError("宛先が指定されていません")

    res = requests.post(
        RESEND_ENDPOINT,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": sender,
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
        },
        timeout=TIMEOUT,
    )
    if res.status_code >= 300:
        raise RuntimeError(f"Resend がエラーを返しました: {res.status_code} {res.text[:300]}")
    return (res.json() or {}).get("id", "")


def send_mail(to: list[str], subject: str, html: str, text: str) -> str:
    """通知用の差出人で1通送る"""
    return send_mail_from(NOTIFY_FROM, to, subject, html, text)


def get_mail_status(mail_id: str) -> str:
    """
    送信済みメールの状態を問い合わせる。

    宛先が間違っていても送信自体は成功するため、これを見ないと
    「届いていない」ことに気づけない。Webhook の受け口を用意しなくても
    ここで bounced を拾える。
    """
    if not API_KEY or not mail_id:
        return ""
    try:
        res = requests.get(
            f"{RESEND_ENDPOINT}/{mail_id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=TIMEOUT,
        )
        if res.status_code >= 300:
            return ""
        return (res.json() or {}).get("last_event", "")
    except Exception as e:
        logger.warning(f"送信状態を確認できませんでした: {e}")
        return ""


class Notifier:
    """
    1回の実行で起きた問題をためて、最後にまとめて送る。

    実行中に都度送ると、1つの障害で何通も届いて埋もれる。
    同じ内容は1通にまとめ、応募者ごとに分けたいものだけ個別に送る。
    """

    def __init__(self, client: str = "", source: str = ""):
        # client: 「クックビズ様」など。そのクライアント固有の処理のときだけ入れる
        self.client = client
        # source: どの処理から出た通知か。本文の末尾に入れる
        self.source = source
        self._queue: list[dict] = []
        self._seen: set[str] = set()

    def add(
        self,
        severity: str,
        title: str,
        what: str,
        impact: str,
        action: str,
        details: str = "",
        client: str | None = None,
    ) -> None:
        """通知を1件ためる。同じ件名のものは1通にまとめる"""
        name = self.client if client is None else client
        subject = f"【{severity}】{name + ' ' if name else ''}{title}"
        if subject in self._seen:
            return
        self._seen.add(subject)
        self._queue.append({
            "severity": severity,
            "subject": subject,
            "what": what,
            "impact": impact,
            "action": action,
            "details": details,
        })
        level = logger.error if severity == URGENT else logger.warning
        level(f"{subject} / {what}")

    def urgent(self, title: str, what: str, impact: str, action: str, **kw) -> None:
        self.add(URGENT, title, what, impact, action, **kw)

    def check(self, title: str, what: str, impact: str, action: str, **kw) -> None:
        self.add(CHECK, title, what, impact, action, **kw)

    def has_problems(self) -> bool:
        return bool(self._queue)

    def flush(self) -> None:
        """ためた通知を送る。送信自体に失敗しても処理は止めない"""
        if not self._queue:
            return

        if not API_KEY or not NOTIFY_TO:
            logger.warning(
                f"通知の宛先かAPIキーが未設定のため、{len(self._queue)} 件の通知を送れません"
            )
            for item in self._queue:
                logger.warning(f"  未送信: {item['subject']}")
            self._queue.clear()
            return

        for item in self._queue:
            try:
                send_mail(
                    NOTIFY_TO,
                    item["subject"],
                    _html(item, self.source),
                    _text(item, self.source),
                )
                logger.info(f"通知を送信しました: {item['subject']}")
            except Exception as e:
                # 通知が送れないこと自体は処理を止める理由にならない。
                # ここで落とすと本来の処理まで巻き添えになる。
                logger.error(f"通知を送信できませんでした: {item['subject']} / {e}")
        self._queue.clear()


def _footer(source: str) -> list[str]:
    lines = []
    if source:
        lines.append(f"発生元: {source}")
    run = os.environ.get("GITHUB_RUN_URL", "")
    if not run:
        server = os.environ.get("GITHUB_SERVER_URL", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        if server and repo and run_id:
            run = f"{server}/{repo}/actions/runs/{run_id}"
    if run:
        lines.append(f"実行ログ: {run}")
    return lines


def _text(item: dict, source: str) -> str:
    parts = [
        item["subject"],
        "",
        "■ 何が起きたか",
        item["what"],
        "",
        "■ 影響",
        item["impact"],
        "",
        "■ 対処",
        item["action"],
    ]
    if item["details"]:
        parts += ["", "■ 詳細", item["details"]]
    footer = _footer(source)
    if footer:
        parts += ["", "----------", *footer]
    return "\n".join(parts)


def _html(item: dict, source: str) -> str:
    color = "#B3261E" if item["severity"] == URGENT else "#8A5A00"

    def block(label: str, body: str) -> str:
        return (
            f'<div style="margin:0 0 20px">'
            f'<div style="font-size:12px;letter-spacing:.08em;color:#6B7671;'
            f'margin-bottom:4px">{_esc(label)}</div>'
            f'<div style="white-space:pre-wrap">{_esc(body)}</div>'
            f"</div>"
        )

    body = block("何が起きたか", item["what"])
    body += block("影響", item["impact"])
    body += block("対処", item["action"])
    if item["details"]:
        body += block("詳細", item["details"])

    footer = _footer(source)
    foot = ""
    if footer:
        foot = (
            '<div style="margin-top:28px;padding-top:14px;border-top:1px solid #DCE0DC;'
            'font-size:12px;color:#6B7671">'
            + "<br>".join(_esc(f) for f in footer)
            + "</div>"
        )

    return (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
        "'Noto Sans JP',sans-serif;font-size:14px;line-height:1.9;color:#181C1A;"
        'max-width:640px">'
        f'<div style="font-weight:700;font-size:16px;color:{color};margin-bottom:20px">'
        f'{_esc(item["subject"])}</div>'
        f"{body}{foot}"
        "</div>"
    )


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

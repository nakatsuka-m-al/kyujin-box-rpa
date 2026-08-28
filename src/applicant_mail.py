"""
応募者情報のメール送信。

シートに記録したのと同じ内容を、先方の担当者にそのまま送る。
CSV の値は1行に詰まっていて読めないので、人が読める形に直す。

必要な環境変数:
  APPLICANT_MAIL_TO       宛先。カンマ区切りで複数可
  APPLICANT_MAIL_FROM     差出人。既定は Oubo Pay応募通知 <oubopay@blaze-ltd.com>
  APPLICANT_MAIL_CLIENT   件名に入れるクライアント名。例: クックビズ様
"""

import logging
import os
import re

import notify

logger = logging.getLogger(__name__)

MAIL_TO = [a.strip() for a in os.environ.get("APPLICANT_MAIL_TO", "").split(",") if a.strip()]
MAIL_FROM = notify._env(
    "APPLICANT_MAIL_FROM", "Oubo Pay応募通知 <oubopay@blaze-ltd.com>"
)
CLIENT_NAME = notify._env("APPLICANT_MAIL_CLIENT")

# 本文に出す項目と順番。左が見出し、右が応募者データのキー
FIELDS_PERSON = [
    ("氏名", "name"),
    ("性別", "gender"),
    ("生年月日", "birthdate"),
    ("現在の職業", "current_job"),
    ("電話番号", "phone"),
    ("メール", "email"),
    ("住所", "address"),
    ("学校名", "education"),
]
FIELDS_APPLICATION = [
    ("応募日時", "applied_at"),
    ("求人タイトル", "job_title"),
    ("応募No", "applicant_id"),
]


def format_phone(value: str) -> str:
    """
    09000000001 のように届く電話番号にハイフンを入れる。

    判別できない形は元の値をそのまま返す。
    無理に整形して壊すより、そのまま見せた方が使える。
    """
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return str(value or "")

    # フリーダイヤル・ナビダイヤルは区切りが違う
    if len(digits) == 10 and digits[:4] in ("0120", "0800", "0570"):
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    # 携帯・IP電話
    if len(digits) == 11 and digits[0] == "0":
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10 and digits.startswith("0"):
        # 03/06 で始まる2桁市外局番
        if digits[1] in "36":
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return str(value or "")


def format_career(value: str) -> list[tuple[str, str]]:
    """
    「会社名（期間）／内容 → 会社名（期間）／内容」を
    [(会社名（期間）, 内容), ...] に分ける。

    ／ で改行しないと1行に全部つながって読めない。
    """
    text = str(value or "").strip()
    if not text:
        return []

    entries = []
    for chunk in text.split("→"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "／" in chunk:
            head, _, body = chunk.partition("／")
            entries.append((head.strip(), body.strip()))
        else:
            entries.append((chunk, ""))
    return entries


def build_subject(applicant: dict) -> str:
    """
    件名。

    「新着応募のお知らせ」という文字列は入れない。
    差出人が求人ボックスの通知を受けている転送リストと同じアドレスのため、
    その件名にすると自分が送ったメールをメール監視が拾いに行ってしまう。
    """
    name = str(applicant.get("name") or "").strip() or "応募者"
    label = f"{CLIENT_NAME} " if CLIENT_NAME else ""
    return f"【Oubo Pay】{label}新規応募 {name} 様"


def build_text(applicant: dict) -> str:
    lines = [
        "求人ボックスに新しい応募が入りました。",
        "",
        "■ 応募者",
    ]
    for label, key in FIELDS_PERSON:
        lines.append(f"{label}　{_value(applicant, key)}")

    lines += ["", "■ 応募内容"]
    for label, key in FIELDS_APPLICATION:
        lines.append(f"{label}　{_value(applicant, key)}")

    career = format_career(applicant.get("work_history"))
    if career:
        lines += ["", "■ 職歴", ""]
        for company, role in career:
            lines.append(company)
            if role:
                for row in role.splitlines():
                    lines.append(f"　{row}")
            lines.append("")

    message = str(applicant.get("message") or "").strip()
    if message:
        lines += ["■ 備考・PR", "", message]

    return "\n".join(lines)


def build_html(applicant: dict) -> str:
    def row(label: str, value: str) -> str:
        return (
            "<tr>"
            f'<td style="padding:4px 16px 4px 0;color:#6B7671;white-space:nowrap;'
            f'vertical-align:top">{_esc(label)}</td>'
            f'<td style="padding:4px 0">{_esc(value)}</td>'
            "</tr>"
        )

    def section(title: str, inner: str) -> str:
        return (
            f'<div style="margin:0 0 24px">'
            f'<div style="font-weight:700;font-size:13px;letter-spacing:.06em;'
            f'color:#0E6152;margin-bottom:8px">{_esc(title)}</div>'
            f"{inner}</div>"
        )

    person = "".join(row(l, _value(applicant, k)) for l, k in FIELDS_PERSON)
    application = "".join(row(l, _value(applicant, k)) for l, k in FIELDS_APPLICATION)

    body = section("応募者", f'<table style="border-collapse:collapse">{person}</table>')
    body += section("応募内容", f'<table style="border-collapse:collapse">{application}</table>')

    career = format_career(applicant.get("work_history"))
    if career:
        inner = ""
        for company, role in career:
            inner += (
                '<div style="margin:0 0 14px">'
                f'<div style="font-weight:500">{_esc(company)}</div>'
                + (
                    f'<div style="margin-left:1em;color:#3E4744;white-space:pre-wrap">'
                    f"{_esc(role)}</div>"
                    if role
                    else ""
                )
                + "</div>"
            )
        body += section("職歴", inner)

    message = str(applicant.get("message") or "").strip()
    if message:
        body += section(
            "備考・PR",
            f'<div style="white-space:pre-wrap">{_esc(message)}</div>',
        )

    return (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Hiragino Sans\','
        "'Noto Sans JP',sans-serif;font-size:14px;line-height:1.9;color:#181C1A;"
        'max-width:640px">'
        '<div style="margin-bottom:24px">求人ボックスに新しい応募が入りました。</div>'
        f"{body}</div>"
    )


def send(applicant: dict) -> str:
    """1人分を1通送る。送信IDを返す。失敗したら例外を投げる"""
    if not MAIL_TO:
        raise RuntimeError("APPLICANT_MAIL_TO が未設定です")

    return notify.send_mail_from(
        MAIL_FROM,
        MAIL_TO,
        build_subject(applicant),
        build_html(applicant),
        build_text(applicant),
    )


def _value(applicant: dict, key: str) -> str:
    value = str(applicant.get(key) or "").strip()
    if key == "phone":
        return format_phone(value)
    return value or "—"


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

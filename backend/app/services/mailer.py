"""보고서 이메일 발송(2026-09-12) — ARWS와 같은 하이웍스 SMTP를 쓰되, ARWS처럼 n8n에
맡기지 않고(CLAUDE.md n8n 금지) 백엔드가 표준 라이브러리 smtplib로 직접 보낸다. 새 의존성을
안 늘리려고 별도 이메일 라이브러리는 안 쓴다.

관리자가 "발송" 버튼을 눌렀을 때만 실행(자동 발송 없음, CLAUDE.md 원칙 3과 같은 취지) —
정기 자동발송(뉴스레터 구독)은 아직 범위 밖(project_newsletter_monetization 참고, 향후 과제).
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


class SmtpNotConfiguredError(Exception):
    pass


def send_email(*, to: list[str], subject: str, html_body: str, text_body: str) -> None:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise SmtpNotConfiguredError("SMTP가 설정되지 않았습니다 — infra/.env에 SMTP_HOST·SMTP_USER·SMTP_PASSWORD를 추가한 뒤 재기동하세요.")
    if not to:
        raise ValueError("수신자가 없습니다 — 고객 상세 화면에서 보고서 수신자 이메일을 먼저 등록하세요.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    # 하이웍스는 465포트 암시적 SSL(smtps.hiworks.com)만 지원 — STARTTLS(587)가 아니다
    # (2026-09-12 실제 안내 화면 확인). SMTP_SSL로 연결 시작부터 TLS를 건다.
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

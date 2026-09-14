"""보고서 이메일 발송(2026-09-12) — ARWS와 같은 하이웍스 SMTP를 쓰되, ARWS처럼 n8n에
맡기지 않고(CLAUDE.md n8n 금지) 백엔드가 표준 라이브러리 smtplib로 직접 보낸다. 새 의존성을
안 늘리려고 별도 이메일 라이브러리는 안 쓴다.

2026-09-12~14 — 처음엔 "관리자가 '발송' 버튼을 눌렀을 때만 실행"이었으나, 2026-09-14
사용자 지시로 고객별 요일·시간 자동발송(app/scheduler.py run_due_customer_emails)이
추가됐다. 이는 의사결정_로그 9번이 이미 짚은 리스크 — 하이웍스 이용약관 제29조2항이
"자체 제작 프로그램·자동화 스크립트를 통한 메일 대량발송"을 금지하고 있고, 개발 단계에서
"완화 조치(발송 간격 두기, 발신자 정보 명시, List-Unsubscribe 헤더)를 적용하며 임시로
감수, 정식 출시 시 외부 ESP로 전환 재검토"로 결정된 바 있다. 자동발송 도입 시점에 그
완화 조치 중 List-Unsubscribe 헤더(RFC 2369)를 추가한다(발송 간격은 scheduler.py에서
처리) — 다만 수신자가 스스로 처리할 수 있는 원클릭 수신거부 페이지는 아직 없다(mailto:로만
안내), 완전한 자기서비스 수신거부는 다음 과제로 남는다.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


class SmtpNotConfiguredError(Exception):
    pass


def send_email(
    *, to: list[str], subject: str, html_body: str, text_body: str, list_unsubscribe: str | None = None
) -> None:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise SmtpNotConfiguredError("SMTP가 설정되지 않았습니다 — infra/.env에 SMTP_HOST·SMTP_USER·SMTP_PASSWORD를 추가한 뒤 재기동하세요.")
    if not to:
        raise ValueError("수신자가 없습니다 — 고객 상세 화면에서 보고서 수신자 이메일을 먼저 등록하세요.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    if list_unsubscribe:
        msg["List-Unsubscribe"] = list_unsubscribe
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    # 하이웍스는 465포트 암시적 SSL(smtps.hiworks.com)만 지원 — STARTTLS(587)가 아니다
    # (2026-09-12 실제 안내 화면 확인). SMTP_SSL로 연결 시작부터 TLS를 건다.
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

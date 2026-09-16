"""관심주제(S7) 매칭 결과를 모아 요약하는 뉴스레터식 리포트. 카탈로그(S9)·LLM(S8) 없이,
이미 계산된 관심도 공식(customer_interest.py)만으로 만든다 — 제품 카탈로그가 비어 있어도
이 리포트는 완전히 동작한다(오늘 결정).
"""

from __future__ import annotations

import html
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, desc, insert, select, update
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import analysis, customer, newsletter_report, report_send_log, source
from app.services.analysis.structure import (
    LLMNotConfiguredError,
    StructuringInProgressError,
    run_structuring_for_notice,
)
from app.services.analysis_pilot import AnalysisInProgressError, UnsupportedSourceError, run_extraction_pilot
from app.services.analysis_worker import submit as submit_background
from app.services.app_settings import get_report_retention_days
from app.services.customer_interest import draft_from_profile, get_interest_profile, top_matches
from app.services.email_assets import logo_data_uri
from app.services.report_commentary import ReportNotFoundError

REPORT_LIMIT = 50  # 2026-09-12 사용자 지시로 20→50 (customer_interest.py의 SECTION_LIMITS도 같이 조정)

_KST = ZoneInfo("Asia/Seoul")  # D-day·기준일 표시는 사용자가 보는 시각(한국 표준시) 기준


def _build_summary(notices: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=7)
    closing_soon = 0
    for n in notices:
        if not n["close_dt"]:
            continue
        close_dt = datetime.fromisoformat(n["close_dt"])
        if now <= close_dt <= soon:
            closing_soon += 1
    return {
        "total": len(notices),
        "closing_soon": closing_soon,
        "top_score": notices[0]["score"] if notices else 0,
    }


def _attributions_for(conn: Connection, notices: list[dict]) -> list[str]:
    """리포트에 실제로 담긴 공고들의 출처(source.attribution_text)를 중복 없이 모은다
    (advisory INBOX #7) — 사람이 문구를 기억해 붙이는 게 아니라 스냅샷 생성 시점에 자동으로
    확정해서 넣는다. 문구가 아직 없는 소스는 조용히 빠진다(빈 리스트가 정상 — 필수 아님)."""
    source_ids = {n["source_id"] for n in notices if n.get("source_id")}
    if not source_ids:
        return []
    rows = conn.execute(
        select(source.c.attribution_text)
        .where(source.c.id.in_(source_ids), source.c.attribution_text.is_not(None))
        .distinct()
        .order_by(source.c.attribution_text)
    ).scalars().all()
    return list(rows)


def _extract_one_for_report(notice_id: int) -> None:
    try:
        with engine.begin() as conn:
            run_extraction_pilot(conn, notice_id)
    except (AnalysisInProgressError, UnsupportedSourceError):
        pass
    except Exception:  # noqa: BLE001 — 공고 하나의 추출 실패가 다른 공고 처리를 막으면 안 됨
        pass


def _ensure_notices_extracted(notice_ids: list[int]) -> None:
    """리포트에 실릴 공고들의 첨부문서 자동분석(A1)을 미리 끝내둔다(2026-09-05 사용자 지시)
    — 고객이 "사업 추진 전략"을 눌렀을 때 A1부터 새로 기다리지 않도록. 결과는 그대로 analysis
    테이블에 남아 공고 탐색(내부 관리자 화면)에도 그대로 반영된다(같은 테이블을 쓰므로 별도
    반영 로직 불필요).

    이미 A1을 한 번이라도 시도한 공고(성공이든 실패든 0건이든)는 건너뛴다(2026-09-07 발견 —
    pending_analysis.py의 자동 패스와 같은 규칙, 무한 재시도 방지).

    2026-09-15 — analysis_worker(동시 2개 제한 스레드풀, app/services/analysis_worker.py)에
    제출만 하고 기다리지 않는다. 예전엔 여기서 공고 하나마다 동기로 완료를 기다렸는데, 매칭
    상위 50건 중 처음 보는 공고가 여럿이면(특히 나라장터) generate_report() 전체가 몇 분씩
    걸려 "지금 발송"·예약 자동발송이 타임아웃으로 실패한 것처럼 보이는 사고로 실제 이어졌다
    (2026-09-07에도 A1만으로 같은 클래스의 사고가 있었는데, 어제 A2를 추가하면서 재발).
    A1/A2 완료 시점과 무관하게 report의 공고 목록·요약은 이미 top_matches()가 반환한 값(notice
    테이블 기준, A1/A2 결과에 의존하지 않음)으로 즉시 저장되므로 기다릴 필요가 애초에 없었다."""
    if not notice_ids:
        return
    with engine.connect() as conn:
        already_attempted = set(
            conn.execute(
                select(analysis.c.notice_id.distinct()).where(
                    analysis.c.notice_id.in_(notice_ids), analysis.c.step == "A1_extract"
                )
            ).scalars()
        )
    for notice_id in notice_ids:
        if notice_id in already_attempted:
            continue
        submit_background(_extract_one_for_report, notice_id)


def _structure_one_for_report(notice_id: int) -> None:
    try:
        with engine.begin() as conn:
            run_structuring_for_notice(conn, notice_id, model="claude-haiku-4-5-20251001")
    except (LLMNotConfiguredError, StructuringInProgressError, ValueError):
        pass
    except Exception:  # noqa: BLE001 — 공고 하나의 구조화 실패가 다른 공고 처리를 막으면 안 됨
        pass


def _ensure_notices_structured(notice_ids: list[int]) -> None:
    """리포트에 실릴 공고들의 AI 구조화(A2)를 미리 끝내둔다(2026-09-15 사용자 지시 — "메일
    발송 시점이 되면 ... 필요시 A1/A2 분석까지 처리").

    A1이 성공(status="done")한 공고 중 아직 A2를 한 번도 안 한 것만 대상으로 한다 — A1이
    실패했거나 아직 안 끝난 공고, 이미 A2까지 끝난 공고는 자동으로 건너뛴다(전자는 시도해도
    "추출된 문서 텍스트 없음"으로 실패할 게 뻔하고, 후자는 재시도가 아니라 새 비용 발생이라
    pending_analysis.py의 자동 패스와 같은 원칙 — 항상 Haiku 고정, 모델 선택은 자동화 안 함).
    이 조회는 이 함수를 부르는 시점(=`_ensure_notices_extracted`가 막 제출한 A1이 아직
    끝나기 전) 기준이라 방금 새로 뽑은 공고의 A2는 대부분 여기서 못 잡는다 — 그건
    run_pending_backlog(10분마다, app/scheduler.py)가 이어받는다. 아래 background 제출도
    같은 이유(analysis_worker.py) — 동기로 기다리면 A1과 똑같이 타임아웃 사고가 난다."""
    if not notice_ids:
        return
    with engine.connect() as conn:
        latest_ver_sq = (
            select(analysis.c.notice_id, analysis.c.id.label("analysis_id"))
            .distinct(analysis.c.notice_id)
            .order_by(analysis.c.notice_id, analysis.c.ver.desc())
            .subquery()
        )
        candidates = conn.execute(
            select(analysis.c.notice_id)
            .select_from(latest_ver_sq)
            .join(analysis, analysis.c.id == latest_ver_sq.c.analysis_id)
            .where(
                analysis.c.notice_id.in_(notice_ids),
                analysis.c.step == "A1_extract",
                analysis.c.status == "done",
            )
        ).scalars().all()
    for notice_id in candidates:
        submit_background(_structure_one_for_report, notice_id)


def delete_expired_reports(conn: Connection) -> int:
    """보관기간(app_settings.get_report_retention_days, 설정 안 하면 자동 삭제 없음)이 지난
    리포트를 지운다(2026-09-12 사용자 지시 — "생성 후 N일 지나면 자동 삭제"). notice_cleanup.py의
    "수집 시 자동 정리"와 같은 방식으로, 별도 스케줄러 없이 generate_report() 호출 시마다 같이
    돈다."""
    retention_days = get_report_retention_days(conn)
    if retention_days is None:
        return 0
    result = conn.execute(
        delete(newsletter_report).where(newsletter_report.c.generated_at < datetime.now(timezone.utc) - timedelta(days=retention_days))
    )
    return result.rowcount


def delete_report(conn: Connection, customer_id: int, report_id: int) -> bool:
    result = conn.execute(
        delete(newsletter_report).where(
            newsletter_report.c.id == report_id, newsletter_report.c.customer_id == customer_id
        )
    )
    return result.rowcount > 0


def generate_report(customer_id: int) -> dict | None:
    """이번 시점 관심도 계산 결과를 스냅샷으로 고정해 저장한다. 이후 재계산되지 않으므로,
    이메일에 링크를 실어 보낸 뒤 원본 데이터가 바뀌어도 고객이 보는 리포트는 안 흔들린다."""
    with engine.begin() as conn:
        delete_expired_reports(conn)

    with engine.connect() as conn:
        profile = get_interest_profile(conn, customer_id)
        if profile is None:
            return None
        draft = draft_from_profile(profile)
        matches = top_matches(conn, draft, limit=REPORT_LIMIT)

    _ensure_notices_extracted([n["id"] for n in matches])
    _ensure_notices_structured([n["id"] for n in matches])

    with engine.begin() as conn:
        summary = _build_summary(matches)
        summary["attributions"] = _attributions_for(conn, matches)
        token = secrets.token_urlsafe(24)

        row = conn.execute(
            insert(newsletter_report)
            .values(customer_id=customer_id, token=token, notices=matches, summary=summary)
            .returning(newsletter_report.c.id, newsletter_report.c.generated_at)
        ).one()

    return {
        "id": row.id,
        "token": token,
        "customer_id": customer_id,
        "notices": matches,
        "summary": summary,
        "generated_at": row.generated_at.isoformat(),
    }


_EMAIL_SECTION_LABELS = {"plan": "발주계획", "prenotice": "사전규격 · 접수예정", "active": "입찰접수 · 접수중"}
_EMAIL_SECTION_ORDER = ["active", "prenotice", "plan"]  # PublicReportPage.tsx SECTION_ORDER와 동일


def _email_section_of(n: dict) -> str:
    """PublicReportPage.tsx의 sectionOf()와 같은 로직 — 스냅샷(notices JSONB)은 이미 직렬화된
    필드(stage/notice_type/bid_status)를 쓰므로 customer_interest._section_of(원본 raw 필드
    기준)를 그대로 재사용할 수 없어 이메일 전용으로 다시 둔다."""
    if n["stage"] == "발주계획":
        return "plan"
    if n["stage"] == "사전규격":
        return "prenotice"
    if n["notice_type"] == "정부지원" and n["bid_status"] in ("upcoming", "unscheduled"):
        return "prenotice"
    return "active"


def _email_format_price(value: int | None) -> str:
    if value is None:
        return "미공개"
    eok = value / 100_000_000
    return f"{eok:.1f}억원" if eok >= 1 else f"{value / 10_000:.0f}만원"


def _email_format_date(value: str | None) -> str:
    """PublicReportPage.tsx의 toLocaleDateString('ko-KR') 표기("2026. 9. 15.")와 맞춘다."""
    if not value:
        return "미상"
    d = datetime.fromisoformat(value)
    return f"{d.year}. {d.month}. {d.day}."


_BID_STATUS_LABELS = {  # frontend/src/api/notices.ts의 BID_STATUS_LABELS와 동일
    "unscheduled": "입찰미정",
    "upcoming": "입찰예정",
    "in_progress": "입찰접수",
    "closed": "입찰마감",
}


def _email_dday_info(close_dt: str | None) -> dict | None:
    """PublicReportPage.tsx의 ddayInfo()와 같은 계산(자정 기준 날짜 차이) — 이메일도 사용자가
    보는 한국 시각(KST) 자정 기준이어야 "오늘 마감"이 D-0으로 정확히 맞는다."""
    if not close_dt:
        return None
    close_date = datetime.fromisoformat(close_dt).astimezone(_KST).date()
    today = datetime.now(_KST).date()
    days = (close_date - today).days
    if days < 0:
        return None
    return {"label": "D-Day" if days == 0 else f"D-{days}", "urgent": days <= 3}


def _email_badge(text: str, *, bg: str, color: str, border: str = "transparent") -> str:
    return (
        '<span style="display:inline-block;padding:2px 8px;margin:0 4px 4px 0;border-radius:12px;'
        f'font-size:11px;font-weight:600;white-space:nowrap;background:{bg};color:{color};'
        f'border:1px solid {border};">{html.escape(text)}</span>'
    )


EMAIL_NOTICE_LIMIT = 20  # 2026-09-15 사용자 지시 — "메일에서는 공고가 많으면 보기 힘드니
# 최대 20개만" (웹 리포트는 그대로 최대 REPORT_LIMIT=50건 전부 보여준다 — 이메일 표시 상한일
# 뿐 스냅샷 자체를 자르지 않음).


def _build_notice_card_html(n: dict, token: str, base_url: str) -> str:
    """요약카드(2026-09-15 사용자 지시 — "2열로 요약카드 형태면 좋겠다") — 2열 배치라 카드
    폭이 좁아(~320px) 상세 카드(배지 3종+관심주제 태그까지)를 다 담을 수 없어, 판단에 바로
    필요한 것(입찰상태·제목·발주기관·마감일·사업비·D-day)만 남긴다."""
    notice_url = f"{base_url}/r/{token}/notices/{n['id']}"
    bid_status = n.get("bid_status")
    bid_status_label = _BID_STATUS_LABELS.get(bid_status, bid_status or "")
    bid_badge = (
        _email_badge(bid_status_label, bg="#d32f2f", color="#fff")
        if bid_status == "in_progress"
        else _email_badge(bid_status_label, bg="#fff", color="#333", border="#bbb")
    )
    dday = _email_dday_info(n.get("close_dt"))
    dday_badge = (
        _email_badge(dday["label"], bg="#d32f2f" if dday["urgent"] else "#ed6c02", color="#fff")
        if dday
        else ""
    )
    org = html.escape(n.get("org_name") or "발주기관 미상")

    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #e5e5e5;border-radius:8px;height:100%;"><tr><td style="padding:12px 14px;">'
        f"<div>{bid_badge}{dday_badge}</div>"
        f'<a href="{notice_url}" style="display:block;margin-top:6px;font-size:14px;font-weight:700;'
        f'color:#1a1a1a;text-decoration:none;line-height:1.35;">{html.escape(n["title"])}</a>'
        f'<div style="font-size:12px;color:#666;margin-top:6px;">{org}</div>'
        f'<div style="font-size:12px;color:#888;margin-top:2px;">마감 {_email_format_date(n.get("close_dt"))}</div>'
        f'<div style="font-size:15px;font-weight:700;color:#1565c0;margin-top:6px;">{_email_format_price(n.get("est_price"))}</div>'
        "</td></tr></table>"
    )


def _build_notice_grid_html(section_notices: list[dict], token: str, base_url: str) -> str:
    """PublicReportPage.tsx의 2열 그리드(gridTemplateColumns 1fr 1fr)를 표(table)로 재현 —
    이메일 클라이언트가 CSS grid를 지원 안 함."""
    rows = []
    for i in range(0, len(section_notices), 2):
        pair = section_notices[i : i + 2]
        cells = "".join(
            f'<td width="50%" style="vertical-align:top;padding:{"0 6px 12px 0" if j == 0 else "0 0 12px 6px"};">'
            f"{_build_notice_card_html(n, token, base_url)}</td>"
            for j, n in enumerate(pair)
        )
        if len(pair) == 1:
            cells += '<td width="50%"></td>'
        rows.append(f"<tr>{cells}</tr>")
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + "".join(rows) + "</table>"


def _build_notices_html(notices: list[dict], token: str, base_url: str) -> str:
    by_section: dict[str, list[dict]] = {"plan": [], "prenotice": [], "active": []}
    for n in notices[:EMAIL_NOTICE_LIMIT]:
        by_section[_email_section_of(n)].append(n)

    parts = []
    for section in _EMAIL_SECTION_ORDER:
        section_notices = by_section[section]
        if not section_notices:
            continue
        parts.append(
            f'<h3 style="margin:24px 0 8px;font-size:15px;color:#555;">'
            f"{_EMAIL_SECTION_LABELS[section]} ({len(section_notices)}건)</h3>"
        )
        parts.append(_build_notice_grid_html(section_notices, token, base_url))
    return "".join(parts)


def send_report_email(conn: Connection, customer_id: int, report_id: int) -> dict:
    """설정된 보고서 수신자 이메일(customer.report_recipient_emails)로 리포트를 보낸다.
    관리자가 "발송" 버튼을 눌렀을 때만 실행 — 자동 발송 아님. 공고 목록을 이메일 본문에
    직접 표로 담고(2026-09-12 사용자 지시), 공고별 상세·AI 사업 추진 전략은 여전히 토큰
    링크로 유도한다(reports.py 모듈 설명과 같은 설계, 2026-09-01 결정)."""
    from app.config import settings
    from app.services.mailer import send_email

    row = conn.execute(
        select(
            newsletter_report.c.token, newsletter_report.c.summary, newsletter_report.c.notices,
            newsletter_report.c.generated_at, customer.c.name, customer.c.report_recipient_emails,
        )
        .select_from(newsletter_report)
        .join(customer, customer.c.id == newsletter_report.c.customer_id)
        .where(newsletter_report.c.id == report_id, newsletter_report.c.customer_id == customer_id)
    ).mappings().first()
    if row is None:
        raise ReportNotFoundError(f"보고서를 찾을 수 없습니다: {report_id}")

    recipients = row["report_recipient_emails"] or []
    if not recipients:
        raise ValueError("보고서 수신자 이메일이 설정되지 않았습니다 — 고객 상세 화면에서 먼저 등록하세요.")
    report_url = f"{settings.public_base_url}/r/{row['token']}"
    summary = row["summary"]
    notices = row["notices"]
    subject = f"[BidRadar] {row['name']} 관심 공고 리포트 — 신규 {summary.get('total', 0)}건"
    text_body = (
        f"{row['name']}님을 위한 관심 공고 리포트가 도착했습니다.\n\n"
        f"총 {summary.get('total', 0)}건, 마감임박 {summary.get('closing_soon', 0)}건.\n\n"
        f"자세히 보기: {report_url}\n"
    )
    generated_label = _email_format_date(row["generated_at"].astimezone(_KST).isoformat())
    closing_soon = summary.get("closing_soon", 0)
    closing_line = f" · 7일 내 마감 {closing_soon}건" if closing_soon > 0 else ""
    # 2026-09-16 — 외부 URL(`{public_base_url}/email-logo.png`)로 참조했다가 실제 수신함에서
    # 깨짐(Gmail이 prod의 자체서명 TLS 인증서를 신뢰 안 해 이미지 프록시가 못 가져옴) —
    # base64 data URI로 본문에 직접 담아 외부 요청 자체를 없앤다(email_assets.py).
    logo_url = logo_data_uri()
    cta_button = (
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr><td '
        'style="background:#DE5B21;border-radius:6px;">'
        f'<a href="{report_url}" style="display:inline-block;padding:10px 20px;font-size:14px;'
        'font-weight:700;color:#fff;text-decoration:none;">웹에서 전체 리포트 보기 →</a>'
        "</td></tr></table>"
    )
    # PublicReportPage.tsx 상단(로고+고객명 배지, "관심 공고" 제목, 기준일·건수)을 그대로
    # 재현한다(2026-09-15 사용자 지시 — "메일 본문을 첨부된 이미지 양식을 그대로 사용해줘").
    # 로고 이미지·상단/하단 "전체 리포트 보기" 버튼도 같은 날 추가 지시.
    html_body = (
        f'<div style="font-family:sans-serif;max-width:680px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;"><tr>'
        f'<td><img src="{logo_url}" alt="BidRadar" width="145" height="36" style="display:block;border:0;"></td>'
        f'<td style="text-align:right;"><span style="display:inline-block;padding:2px 10px;border:1px solid #ccc;'
        f'border-radius:12px;font-size:12px;color:#555;">{html.escape(row["name"])}</span></td>'
        "</tr></table>"
        f'<div style="margin-bottom:20px;">{cta_button}</div>'
        '<h2 style="font-size:20px;margin:0 0 4px;">관심 공고</h2>'
        f'<p style="font-size:13px;color:#777;margin:0 0 4px;">{generated_label} 기준 · 총 '
        f"{summary.get('total', 0)}건{closing_line}</p>"
        + (
            f'<p style="font-size:12px;color:#999;margin:0 0 16px;">메일에는 상위 {EMAIL_NOTICE_LIMIT}건만 '
            f'표시됩니다 — 전체 {len(notices)}건은 <a href="{report_url}" style="color:#1565c0;">웹 리포트</a>에서 확인하세요.</p>'
            if len(notices) > EMAIL_NOTICE_LIMIT
            else '<div style="margin-bottom:16px;"></div>'
        )
        + f"{_build_notices_html(notices, row['token'], settings.public_base_url)}"
        f'<div style="margin-top:24px;">{cta_button}</div>'
        "</div>"
    )
    send_email(
        to=recipients, subject=subject, html_body=html_body, text_body=text_body,
        list_unsubscribe=f"<mailto:{settings.smtp_from}?subject=수신거부>",
    )
    conn.execute(
        insert(report_send_log).values(report_id=report_id, customer_id=customer_id, recipients=recipients)
    )
    conn.commit()
    return {"sent_to": recipients}


def list_reports(conn: Connection, customer_id: int) -> list[dict]:
    """보고서 목록(2026-09-15부터 발송 이력 포함 — 사용자 지시: "각 보고서에는 메일 발송
    이력이 표시되어야 한다"). report_send_log는 send_report_email()이 실제 발송에 성공할
    때마다 한 행씩 남기므로(수신자 목록·발송 시각), 보고서당 여러 번 발송됐을 수 있어
    리스트로 붙인다 — 최신 발송이 먼저 오도록 정렬."""
    rows = conn.execute(
        select(
            newsletter_report.c.id,
            newsletter_report.c.token,
            newsletter_report.c.generated_at,
            newsletter_report.c.summary,
            newsletter_report.c.view_count,
            newsletter_report.c.ai_generated_at,
        )
        .where(newsletter_report.c.customer_id == customer_id)
        .order_by(desc(newsletter_report.c.generated_at))
    ).mappings().all()
    reports = [dict(r) for r in rows]
    if not reports:
        return reports

    report_ids = [r["id"] for r in reports]
    send_rows = conn.execute(
        select(report_send_log.c.report_id, report_send_log.c.recipients, report_send_log.c.sent_at)
        .where(report_send_log.c.report_id.in_(report_ids))
        .order_by(desc(report_send_log.c.sent_at))
    ).all()
    sends_by_report: dict[int, list[dict]] = {}
    for send_row in send_rows:
        sends_by_report.setdefault(send_row.report_id, []).append(
            {"recipients": send_row.recipients, "sent_at": send_row.sent_at.isoformat()}
        )
    for report in reports:
        report["sends"] = sends_by_report.get(report["id"], [])
    return reports


def get_report_by_token(conn: Connection, token: str, *, record_view: bool = True) -> dict | None:
    """서명된 공유 링크(로그인 없음)로 들어오는 조회 — 회사 단위 공용 링크라 여러 사람이
    반복 열람해도 되고, 조회수는 정확한 인원수가 아니라 근사치로만 집계한다(2026-09-01 결정)."""
    row = conn.execute(
        select(
            newsletter_report.c.id,
            newsletter_report.c.customer_id,
            newsletter_report.c.notices,
            newsletter_report.c.summary,
            newsletter_report.c.generated_at,
            newsletter_report.c.view_count,
            customer.c.name.label("customer_name"),
        )
        .select_from(newsletter_report)
        .join(customer, customer.c.id == newsletter_report.c.customer_id)
        .where(newsletter_report.c.token == token)
    ).mappings().first()
    if row is None:
        return None

    if record_view:
        conn.execute(
            update(newsletter_report)
            .where(newsletter_report.c.id == row["id"])
            .values(view_count=newsletter_report.c.view_count + 1, last_viewed_at=datetime.now(timezone.utc))
        )

    return dict(row)

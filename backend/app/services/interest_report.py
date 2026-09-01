"""관심주제(S7) 매칭 결과를 모아 요약하는 뉴스레터식 리포트. 카탈로그(S9)·LLM(S8) 없이,
이미 계산된 관심도 공식(customer_interest.py)만으로 만든다 — 제품 카탈로그가 비어 있어도
이 리포트는 완전히 동작한다(오늘 결정).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, insert, select, update
from sqlalchemy.engine import Connection

from app.models import customer, newsletter_report
from app.services.customer_interest import draft_from_profile, get_interest_profile, top_matches

REPORT_LIMIT = 20


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


def generate_report(conn: Connection, customer_id: int) -> dict | None:
    """이번 시점 관심도 계산 결과를 스냅샷으로 고정해 저장한다. 이후 재계산되지 않으므로,
    이메일에 링크를 실어 보낸 뒤 원본 데이터가 바뀌어도 고객이 보는 리포트는 안 흔들린다."""
    profile = get_interest_profile(conn, customer_id)
    if profile is None:
        return None

    draft = draft_from_profile(profile)
    matches = top_matches(conn, draft, limit=REPORT_LIMIT)
    summary = _build_summary(matches)
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


def list_reports(conn: Connection, customer_id: int) -> list[dict]:
    rows = conn.execute(
        select(
            newsletter_report.c.id,
            newsletter_report.c.token,
            newsletter_report.c.generated_at,
            newsletter_report.c.summary,
            newsletter_report.c.view_count,
        )
        .where(newsletter_report.c.customer_id == customer_id)
        .order_by(desc(newsletter_report.c.generated_at))
    ).mappings().all()
    return [dict(r) for r in rows]


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

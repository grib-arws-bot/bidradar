"""관심주제(S7) 매칭 결과를 모아 요약하는 뉴스레터식 리포트. 카탈로그(S9)·LLM(S8) 없이,
이미 계산된 관심도 공식(customer_interest.py)만으로 만든다 — 제품 카탈로그가 비어 있어도
이 리포트는 완전히 동작한다(오늘 결정).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, insert, select, update
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import analysis, customer, newsletter_report, source
from app.services.analysis_pilot import AnalysisInProgressError, UnsupportedSourceError, run_extraction_pilot
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


def _ensure_notices_extracted(notice_ids: list[int]) -> None:
    """리포트에 실릴 공고들의 첨부문서 자동분석(A1)을 미리 끝내둔다(2026-09-05 사용자 지시)
    — 고객이 "사업 추진 전략"을 눌렀을 때 A1부터 새로 기다리지 않도록. 공고 하나마다 별도의
    짧은 트랜잭션으로 처리한다(app/services/pending_analysis.py와 같은 이유 — 리포트
    생성 하나의 트랜잭션 안에서 여러 건의 첨부파일 다운로드를 전부 묶으면 오래 열려있는
    트랜잭션이 다른 작업을 막을 수 있다, 2026-09-05 실제 사고). 실패해도(추출 불가 사이트,
    이미 진행 중 등) 리포트 생성 자체는 계속 진행 — 결과는 그대로 analysis 테이블에 남아
    공고 탐색(내부 관리자 화면)에도 그대로 반영된다(같은 테이블을 쓰므로 별도 반영 로직 불필요).

    이미 A1을 한 번이라도 시도한 공고(성공이든 실패든 0건이든)는 건너뛴다(2026-09-07 발견 —
    pending_analysis.py의 자동 패스와 같은 규칙). 전에는 매번 리포트를 생성할 때마다 상위
    20건 전부를 무조건 다시 추출 시도해서, 실측상 20건 중 16건이 나라장터(용역) 소스라
    apis.data.go.kr이 느려지거나 타임아웃 나는 날엔 "지금 생성"이 몇 분씩 걸리다 nginx
    프록시 타임아웃(300초)에 걸려 실패한 것처럼 보이는 원인이었다."""
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
        try:
            with engine.begin() as conn:
                run_extraction_pilot(conn, notice_id)
        except (AnalysisInProgressError, UnsupportedSourceError):
            pass
        except Exception:  # noqa: BLE001 — 공고 하나의 추출 실패가 리포트 생성 전체를 막으면 안 됨
            pass


def generate_report(customer_id: int) -> dict | None:
    """이번 시점 관심도 계산 결과를 스냅샷으로 고정해 저장한다. 이후 재계산되지 않으므로,
    이메일에 링크를 실어 보낸 뒤 원본 데이터가 바뀌어도 고객이 보는 리포트는 안 흔들린다."""
    with engine.connect() as conn:
        profile = get_interest_profile(conn, customer_id)
        if profile is None:
            return None
        draft = draft_from_profile(profile)
        matches = top_matches(conn, draft, limit=REPORT_LIMIT)

    _ensure_notices_extracted([n["id"] for n in matches])

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


def list_reports(conn: Connection, customer_id: int) -> list[dict]:
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

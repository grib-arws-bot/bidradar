"""고객 관리 CRUD(2026-09-05 요청) — 고객 엔티티 자체(이름·담당자·보고서 수신자·소개서 파일)를
다룬다. 관심주제·저장검색·리포트는 app/services/customer_interest.py·interest_report.py 등
기존 S7 모듈이 그대로 담당한다(여긴 그 위에 얹히는 고객 "카드" 정보만)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection

from app.models import customer, customer_document

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # 소개서 문서 하나당 20MB 상한 — DB에 무제한으로 안 쌓이게


# price_min/price_max/regions는 이 draft에 없다 — customer 테이블 컬럼은 맞지만, 실제 소유·
# 편집은 관심주제 매칭 설정(app/services/customer_interest.py의 InterestDraft)이 전담한다.
# 한때 이 화면에도 중복으로 있었는데(2026-09-05), 같은 컬럼을 두 화면이 각자 저장하면 나중에
# 저장한 쪽이 이긴다는 게 드러나 여기서는 제거(사용자 지시 — "고객 정보에 추정가격·지역 불필요").
@dataclass
class CustomerDraft:
    name: str
    plan_tier: str = "standard"
    contact_email: str | None = None
    contact_name: str | None = None
    contact_title: str | None = None
    contact_phone: str | None = None
    report_recipient_emails: list[str] = field(default_factory=list)
    reference_urls: list[str] = field(default_factory=list)
    active: bool = True


def _serialize(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "plan_tier": row["plan_tier"],
        "contact_email": row["contact_email"],
        "contact_name": row["contact_name"],
        "contact_title": row["contact_title"],
        "contact_phone": row["contact_phone"],
        "report_recipient_emails": row["report_recipient_emails"] or [],
        "reference_urls": row["reference_urls"] or [],
        "active": row["active"],
        "profile_summary_md": row["profile_summary_md"],
        "profile_summarized_at": row["profile_summarized_at"].isoformat() if row["profile_summarized_at"] else None,
        "profile_summary_cost": float(row["profile_summary_cost"]),
        "report_auto_send_schedule": row["report_auto_send_schedule"] or [],
    }


def list_customers_full(conn: Connection) -> list[dict]:
    rows = conn.execute(select(customer).order_by(customer.c.id)).mappings().all()
    return [_serialize(r) for r in rows]


def get_customer(conn: Connection, customer_id: int) -> dict | None:
    row = conn.execute(select(customer).where(customer.c.id == customer_id)).mappings().first()
    return _serialize(row) if row else None


def create_customer(conn: Connection, draft: CustomerDraft) -> int:
    return conn.execute(
        insert(customer)
        .values(
            name=draft.name,
            plan_tier=draft.plan_tier,
            contact_email=draft.contact_email,
            contact_name=draft.contact_name,
            contact_title=draft.contact_title,
            contact_phone=draft.contact_phone,
            report_recipient_emails=draft.report_recipient_emails,
            reference_urls=draft.reference_urls,
            active=draft.active,
        )
        .returning(customer.c.id)
    ).scalar_one()


def update_customer(conn: Connection, customer_id: int, draft: CustomerDraft) -> bool:
    result = conn.execute(
        customer.update()
        .where(customer.c.id == customer_id)
        .values(
            name=draft.name,
            plan_tier=draft.plan_tier,
            contact_email=draft.contact_email,
            contact_name=draft.contact_name,
            contact_title=draft.contact_title,
            contact_phone=draft.contact_phone,
            report_recipient_emails=draft.report_recipient_emails,
            reference_urls=draft.reference_urls,
            active=draft.active,
        )
    )
    return result.rowcount > 0


def delete_customer(conn: Connection, customer_id: int) -> bool:
    """internal(그립 자신) 고객은 삭제 금지 — 실수로 자기 자신을 지우는 사고 방지."""
    row = conn.execute(select(customer.c.plan_tier).where(customer.c.id == customer_id)).first()
    if row is None:
        return False
    if row.plan_tier == "internal":
        raise ValueError("내부(그립 자신) 고객은 삭제할 수 없습니다.")
    conn.execute(delete(customer).where(customer.c.id == customer_id))
    return True


# ---- 보고서 메일 자동발송 요일·시간(2026-09-14) -----------------------------------------
# app/scheduler.py의 소스 수집 스케줄(schedule_times)과 같은 패턴 — 여기서 검증만 하고,
# 실제로 그 시각에 발송을 실행하는 건 scheduler.py의 run_due_customer_emails().


class EmailScheduleError(ValueError):
    pass


MAX_EMAIL_SCHEDULE_ENTRIES = 3  # source.schedule_times와 같은 상한(app/services/source_registry.py)


def validate_email_schedule(schedule: list[dict]) -> None:
    """schedule은 [{"day": ISO요일(1=월~7=일), "time": "HH:MM"}, ...] — 2026-09-15 재설계.
    이전엔 요일 목록·시각 목록을 따로 받아 카르테시안 곱으로 실행됐는데("월,목" + "13:00,14:00"을
    주면 4가지 조합 전부 발송), 사용자가 원한 건 "월 13시, 목 14시"처럼 요일마다 다른 시각을
    지정하는 것이었다 — 그래서 (요일,시각) 쌍 하나하나를 원소로 받는다."""
    if len(schedule) > MAX_EMAIL_SCHEDULE_ENTRIES:
        raise EmailScheduleError(f"발송 일정은 최대 {MAX_EMAIL_SCHEDULE_ENTRIES}개까지 설정할 수 있습니다.")
    seen: set[tuple[int, str]] = set()
    for entry in schedule:
        day = entry.get("day")
        time = entry.get("time")
        if not isinstance(day, int) or day < 1 or day > 7:
            raise EmailScheduleError(f"요일은 1(월)~7(일) 사이의 값이어야 합니다: {day!r}")
        if not isinstance(time, str):
            raise EmailScheduleError(f"시각이 지정되지 않았습니다: {entry!r}")
        try:
            hour_str, minute_str = time.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except (ValueError, AttributeError) as exc:
            raise EmailScheduleError(f"시간 형식이 올바르지 않습니다(HH:MM, 00:00~23:59): {time!r}") from exc
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise EmailScheduleError(f"시간은 00:00~23:59 범위여야 합니다: {time!r}")
        key = (day, time)
        if key in seen:
            raise EmailScheduleError(f"같은 요일·시각을 중복해서 지정할 수 없습니다: {day}요일 {time}")
        seen.add(key)


def set_email_schedule(conn: Connection, customer_id: int, schedule: list[dict]) -> bool:
    validate_email_schedule(schedule)
    result = conn.execute(
        update(customer)
        .where(customer.c.id == customer_id)
        .values(report_auto_send_schedule=schedule)
    )
    return result.rowcount > 0


# ---- 소개서 파일(다중 업로드, DB 바이너리 저장) -----------------------------------------


def list_documents(conn: Connection, customer_id: int) -> list[dict]:
    rows = conn.execute(
        select(
            customer_document.c.id, customer_document.c.filename, customer_document.c.content_type,
            customer_document.c.size_bytes, customer_document.c.uploaded_at, customer_document.c.uploaded_by,
        )
        .where(customer_document.c.customer_id == customer_id)
        # uploaded_at은 트랜잭션 시작 시각(server_default=func.now())이라 한 번에 여러 파일을
        # 올리면 전부 같은 값을 가져 순서가 안정적이지 않다(2026-09-11 사용자 발견 — 방금
        # 올린 파일이 목록에 안 보이는 것처럼 느껴짐). id를 보조 정렬키로 둬 항상 최신이
        # 위로 오게 한다.
        .order_by(customer_document.c.uploaded_at.desc(), customer_document.c.id.desc())
    ).mappings().all()
    return [
        {
            "id": r["id"], "filename": r["filename"], "content_type": r["content_type"],
            "size_bytes": r["size_bytes"], "uploaded_at": r["uploaded_at"].isoformat(), "uploaded_by": r["uploaded_by"],
        }
        for r in rows
    ]


def add_document(
    conn: Connection, customer_id: int, *, filename: str, content_type: str | None, content: bytes, uploaded_by: str,
) -> int:
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"파일이 너무 큽니다(최대 {MAX_DOCUMENT_BYTES // 1024 // 1024}MB): {filename}")
    return conn.execute(
        insert(customer_document)
        .values(
            customer_id=customer_id, filename=filename, content_type=content_type,
            size_bytes=len(content), content=content, uploaded_by=uploaded_by,
        )
        .returning(customer_document.c.id)
    ).scalar_one()


def get_document(conn: Connection, customer_id: int, document_id: int) -> dict | None:
    row = conn.execute(
        select(customer_document.c.filename, customer_document.c.content_type, customer_document.c.content).where(
            customer_document.c.id == document_id, customer_document.c.customer_id == customer_id
        )
    ).mappings().first()
    return dict(row) if row else None


def delete_document(conn: Connection, customer_id: int, document_id: int) -> bool:
    result = conn.execute(
        delete(customer_document).where(
            customer_document.c.id == document_id, customer_document.c.customer_id == customer_id
        )
    )
    return result.rowcount > 0

"""관심주제 기반 요약 리포트(뉴스레터 스냅샷). 08절에는 없던 테이블 — 서명된 공유 링크
(의사결정_로그 8·9번, 로그인 없는 고객용 열람)를 실제로 구현하며 신설.

이메일에는 요약만, 상세는 이 스냅샷을 가리키는 토큰 링크로 — 링크는 회사(고객) 단위 공용,
여러 번·여러 사람이 봐도 되고(재사용 가능), 조회수만 근사치로 집계한다(2026-09-01 결정).
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import metadata

newsletter_report = Table(
    "newsletter_report",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("token", String(64), nullable=False, unique=True),
    Column("notices", JSONB, nullable=False),  # 생성 시점 스냅샷 — 이후 재계산되지 않음(고정)
    Column("summary", JSONB, nullable=False),  # 총 건수, 신규/마감임박 건수 등
    Column("view_count", Integer, nullable=False, server_default="0"),
    Column("last_viewed_at", DateTime(timezone=True)),
    Column("generated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

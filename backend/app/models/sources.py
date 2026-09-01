"""소스 레지스트리 (구현스펙 08절, 설계안 04절). 소스 설정 변경은 항상 새 source_config 버전을
만든다 — 기존 행을 덮어쓰지 않는다(CLAUDE.md 코드 규칙).
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import metadata

source = Table(
    "source",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("org_name", String(200)),  # 이 소스를 운영하는 기관
    Column("base_url", Text, nullable=False),
    Column("stage", String(30), nullable=False),  # 사전규격/입찰공고/낙찰 등 (설계안 04-2)
    Column("adapter_type", String(10), nullable=False),  # openapi/feed/html (설계안 04-1)
    Column("frequency_minutes", Integer, nullable=False, server_default="60"),
    # is_system=true인 소스(나라장터 등 기본 제공)는 관리자가 못 지움(구현스펙 U12 인수조건)
    Column("is_system", Boolean, nullable=False, server_default="false"),
    # 관리자가 추가한 소스는 품명번호·업종코드가 없어 L1을 자동 통과시켜야 함(설계안 05절 L1 주의2)
    Column("skip_l1", Boolean, nullable=False, server_default="false"),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

source_config = Table(
    "source_config",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("source.id", ondelete="CASCADE"), nullable=False),
    Column("ver", Integer, nullable=False),
    Column("config", JSONB, nullable=False),  # 어댑터별 상세(서비스ID/오퍼레이션, 선택자 등)
    Column("created_by", String(255), nullable=False, server_default="report@grib.co.kr"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("source_id", "ver", name="uq_source_config_ver"),
)

source_field_map = Table(
    "source_field_map",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_config_id", Integer, ForeignKey("source_config.id", ondelete="CASCADE"), nullable=False),
    # 공통 스키마 필드: title/notice_no/org_name/open_dt/close_dt/est_price/url (설계안 04-2)
    Column("target_field", String(50), nullable=False),
    Column("source_path", Text, nullable=False),  # JSONPath 또는 CSS 선택자
    Column("format_hint", String(50)),  # 날짜형식·통화단위 등
)

source_credential = Table(
    "source_credential",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("source.id", ondelete="CASCADE"), nullable=False),
    Column("kind", String(30), nullable=False),  # service_key 등
    Column("value", Text, nullable=False),  # UI에는 절대 노출 안 함(마스킹)
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

source_run = Table(
    "source_run",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("source.id", ondelete="CASCADE"), nullable=False),
    Column("run_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("status", String(10), nullable=False),  # ok/warn/fail/inactive (S5 상태 배지 4종)
    Column("items_fetched", Integer, nullable=False, server_default="0"),
    Column("duration_ms", Integer),
    Column("error_message", Text),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    # 단일 공유 계정이라 행위자는 사실상 항상 고정값 — 03절 v0.3 트레이드오프로 수용
    Column("actor", String(255), nullable=False, server_default="report@grib.co.kr"),
    Column("action", String(100), nullable=False),  # 예: source.create, keyword.update
    Column("target_type", String(50), nullable=False),
    Column("target_id", String(50)),
    Column("detail", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

"""소스 레지스트리 (구현스펙 08절, 설계안 04절). 소스 설정 변경은 항상 새 source_config 버전을
만든다 — 기존 행을 덮어쓰지 않는다(CLAUDE.md 코드 규칙).
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    # base_url은 실제 호출 엔드포인트라 사람이 보기엔 불친절함(예: API 베이스 URL) — 관리자 페이지
    # "소스 관리" 표에서 기관/서비스를 확인하러 갈 수 있는 사람용 링크(data.go.kr 데이터셋 페이지 등)
    Column("homepage_url", Text),
    Column("stage", String(30), nullable=False),  # 사전규격/입찰공고/낙찰 등 (설계안 04-2)
    Column("adapter_type", String(10), nullable=False),  # openapi/feed/html (설계안 04-1)
    Column("frequency_minutes", Integer, nullable=False, server_default="60"),
    # is_system=true인 소스(나라장터 등 기본 제공)는 관리자가 못 지움(구현스펙 U12 인수조건)
    Column("is_system", Boolean, nullable=False, server_default="false"),
    # 관리자가 추가한 소스는 품명번호·업종코드가 없어 L1을 자동 통과시켜야 함(설계안 05절 L1 주의2)
    Column("skip_l1", Boolean, nullable=False, server_default="false"),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # 법적 등급(advisory INBOX #5, 2026-09-01) — 관리자 체크박스가 아니라 코드가 강제하는 값.
    # A(자유): 이용허락범위 "제한 없음" — 원문 전재·자동 출처표시 가능.
    # B(조건부): robots 허용·명시적 금지 없음 — 원문 저장 금지, 최소 필드만, 출처 링크 필수,
    #            최소 수집 간격 강제(app/collector/runner.py run_source에서 검사).
    # C(금지): robots 차단 또는 약관상 명시적 금지 — 활성화 자체를 거부(체크박스로도 못 뒤집음).
    Column("legal_tier", String(1), nullable=False),
    CheckConstraint("legal_tier in ('A', 'B', 'C')", name="ck_source_legal_tier"),
    Column("license_note", Text),  # 등급 판단 근거(조문·이용허락범위 등, 사람이 읽는 설명)
    Column("license_evidence_url", Text),  # 근거 페이지(이용약관·데이터셋 상세 등) 링크
    Column("legal_verified_at", DateTime(timezone=True)),  # 마지막 준법 확인 시각(S5 배지, INBOX #6)
    Column("robots_hash", Text),  # 마지막 확인 시점 robots.txt 해시 — 변경 감지용(INBOX #6)
    # 출처표시 문구(advisory INBOX #7) — 공공데이터포털 정책상 제0유형 외 전 유형 의무.
    # 뉴스레터/공유리포트/향후 S8 내보내기 템플릿이 이 값을 자동으로 붙인다(사람이 안 잊게).
    Column("attribution_text", Text),
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

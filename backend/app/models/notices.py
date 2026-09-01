"""공고 · 분석 계열 (구현스펙 08절) + org/award/keyword_rule.

notice_score.domain은 v0.3에서 interest_topic_id(FK)로 바꿨다 — L2-b가 도메인 2개 고정에서
대분류 15~25개로 넓어졌으므로(설계안 05절 L2-b) 문자열 이진값으로는 더 이상 표현이 안 된다.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import metadata

org = Table(
    "org",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("code", String(50)),  # 나라장터 등 발주기관 코드
    Column("category", String(100)),  # 교육청/공기업/중앙부처 등
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

raw_payload = Table(
    "raw_payload",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("source.id", ondelete="CASCADE"), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("endpoint", Text, nullable=False),
    Column("body", JSONB, nullable=False),
)

notice = Table(
    "notice",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("source.id"), nullable=False),
    Column("source_ver", Integer, nullable=False),  # 이 건을 수집한 시점의 source_config.ver
    Column("notice_no", String(100)),
    Column("ord", Integer, nullable=False, server_default="0"),  # 차수
    Column("stage", String(30), nullable=False),  # 사전규격/입찰공고/낙찰/계약
    Column("title", Text, nullable=False),
    Column("org_id", Integer, ForeignKey("org.id")),
    Column("est_price", Numeric(16, 0)),
    Column("region", String(100)),
    Column("open_dt", DateTime(timezone=True)),
    Column("close_dt", DateTime(timezone=True)),
    Column("url", Text, nullable=False),
    Column("pipeline_stage", String(30), nullable=False, server_default="collected"),  # S2 칸반 단계
    Column("assignee_name", String(100)),  # 자유텍스트 담당자명(개별 계정 없음, 03절 v0.3)
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

notice_version = Table(
    "notice_version",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("notice_id", Integer, ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
    Column("ver", Integer, nullable=False),
    Column("changed_fields", JSONB, nullable=False),
    Column("changed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

notice_score = Table(
    "notice_score",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("notice_id", Integer, ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
    Column("interest_topic_id", Integer, ForeignKey("interest_topic.id"), nullable=False),
    Column("l2_score", Integer, nullable=False),
    Column("l3_conf", Numeric(4, 3)),  # 0.000~1.000
    Column("priority", Numeric(8, 3)),  # 06절 우선순위 스코어링 결과
    Column("reason", Text),  # 판정 근거 — "왜 이게 떴는지" 담당자가 확인 가능해야 함(05절 원칙)
    Column("rule_ver", Integer, nullable=False),  # 이 판정에 쓰인 키워드 사전 버전
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

requirement = Table(
    "requirement",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("notice_id", Integer, ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
    Column("type", String(50), nullable=False),  # 실적/인증/지역제한 등
    Column("value", Text, nullable=False),
    Column("we_qualify", Boolean),
)

award = Table(
    "award",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("notice_id", Integer, ForeignKey("notice.id")),
    Column("org_id", Integer, ForeignKey("org.id")),
    Column("winner_name", String(200), nullable=False),
    Column("amount", Numeric(16, 0)),
    Column("awarded_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

keyword_rule = Table(
    "keyword_rule",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("interest_topic_id", Integer, ForeignKey("interest_topic.id", ondelete="CASCADE"), nullable=False),
    Column("term", String(100), nullable=False),
    Column("weight_class", String(10), nullable=False),  # core/tech/ctx/block (설계안 05절 L2)
    Column("weight", Integer, nullable=False),  # +3/+2/+1/-5 등
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

classification_correction = Table(
    "classification_correction",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("notice_id", Integer, ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
    Column("action", String(20), nullable=False),  # confirm/recategorize/irrelevant (S1 v0.3)
    Column("categories", JSONB),  # recategorize 시 interest_topic_id 배열
    Column("reason", Text),  # irrelevant 시 서비스 레이어에서 필수화
    Column("corrected_by", String(255), nullable=False, server_default="report@grib.co.kr"),
    Column("corrected_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

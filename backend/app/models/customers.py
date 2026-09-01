"""관심 · 검색 (구현스펙 08절). v0.3 — user_* 대신 customer_* (03절·S7, 단일 계정 로그인 결정).

그립 자신도 customer 테이블의 행 하나(plan_tier='internal')로 취급한다(의사결정_로그 9번).
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import metadata

customer = Table(
    "customer",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False),
    # internal = 그립 자신, standard/premium = 외부 유료 고객 (의사결정_로그 8번)
    Column("plan_tier", String(20), nullable=False, server_default="standard"),
    Column("contact_email", String(255)),
    Column("active", Boolean, nullable=False, server_default="true"),
    # S7 관심도 공식(설계안 08절)의 "금액 부합"·"지역 부합" 조건 — 설정 안 하면(NULL) 그 조건은
    # 적용 안 됨(가산도 제외도 없음). 설정하면 어긋나는 공고는 가산이 아니라 목록에서 제외.
    Column("price_min", Numeric(16, 0)),
    Column("price_max", Numeric(16, 0)),
    Column("regions", JSONB),  # 문자열 배열
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# L2-b 고객 대면 대분류 프리셋 (설계안 05절 L2-b, 15~25개)
interest_topic = Table(
    "interest_topic",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("description", String(300)),
    Column("sort_order", Integer, nullable=False, server_default="0"),
    Column("active", Boolean, nullable=False, server_default="true"),
)

customer_interest = Table(
    "customer_interest",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("interest_topic_id", Integer, ForeignKey("interest_topic.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("customer_id", "interest_topic_id", name="uq_customer_interest"),
)

customer_interest_term = Table(
    "customer_interest_term",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("term", String(100), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

customer_followed_org = Table(
    "customer_followed_org",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("org_id", Integer, ForeignKey("org.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("customer_id", "org_id", name="uq_customer_followed_org"),
)

saved_search = Table(
    "saved_search",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("query_params", JSONB, nullable=False),  # 검색어+필터 스냅샷 (S1 URL 쿼리스트링 그대로)
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

"""제품 카탈로그 ★ (구현스펙 08절, S9). v0.3 — product.customer_id로 고객별 카탈로그 격리
(그립 자신도 1건). 고객 A의 카탈로그가 고객 B의 대조표 계산에 절대 섞이면 안 된다(의사결정_로그 9번).
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

from app.models.base import metadata

product = Table(
    "product",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("category", String(100)),
    Column("description", Text),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

product_spec = Table(
    "product_spec",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("product.id", ondelete="CASCADE"), nullable=False),
    Column("key", String(100), nullable=False),
    Column("value", String(200), nullable=False),
    Column("unit", String(20)),
    Column("op", String(10), nullable=False),  # gte/lte/eq/contains/manual — 대조 규칙의 근거
)

product_cert = Table(
    "product_cert",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("product.id", ondelete="CASCADE"), nullable=False),
    Column("kind", String(50), nullable=False),  # GS/CC/KC/방폭/국정원 검증 등
    Column("detail", String(200)),
    Column("issued_at", DateTime(timezone=True)),
    Column("expires_at", DateTime(timezone=True)),  # 만료 임박(90일) 경고에 사용
)

product_reference = Table(
    "product_reference",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("product.id", ondelete="CASCADE"), nullable=False),
    Column("org_name", String(200), nullable=False),
    Column("project", String(300), nullable=False),
    Column("amount", Numeric(16, 0)),
    Column("completed_at", DateTime(timezone=True)),
    Column("has_proof", Boolean, nullable=False, server_default="false"),
)

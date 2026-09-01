"""심층 분석 ★ (구현스펙 08절, S8). 판정은 권고이지 결정이 아니다 — cite(조문 위치) 없는 판정은
화면에 내보내지 않는다는 CLAUDE.md 원칙이 analysis_requirement.cite에 그대로 반영됨.
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

analysis = Table(
    "analysis",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("notice_id", Integer, ForeignKey("notice.id")),  # url/upload 입력은 nullable
    Column("source_kind", String(10), nullable=False),  # notice/url/upload
    Column("input_ref", Text, nullable=False),
    Column("status", String(20), nullable=False, server_default="queued"),  # queued/running/done/failed
    Column("step", String(50)),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("verdict", Text),
    Column("confidence", Numeric(4, 3)),
    Column("llm_tokens", Integer, nullable=False, server_default="0"),
    Column("llm_cost", Numeric(10, 4), nullable=False, server_default="0"),  # USD, A2·A5·A6 호출 누계
    Column("created_by", String(255), nullable=False, server_default="report@grib.co.kr"),
    Column("ver", Integer, nullable=False, server_default="1"),  # 동일 공고 재분석 시 버전으로 쌓임
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

analysis_doc = Table(
    "analysis_doc",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("analysis_id", Integer, ForeignKey("analysis.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("kind", String(10), nullable=False),  # hwp/hwpx/pdf/html
    Column("bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("extract_method", String(30)),  # 폴백 사슬 중 성공한 단계 — 조용한 빈 결과 금지
    Column("extract_ok", Boolean, nullable=False, server_default="false"),
    Column("error", Text),
)

analysis_requirement = Table(
    "analysis_requirement",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("analysis_id", Integer, ForeignKey("analysis.id", ondelete="CASCADE"), nullable=False),
    Column("category", String(50), nullable=False),
    Column("req_text", Text, nullable=False),
    Column("req_value", String(100)),
    Column("req_unit", String(20)),
    Column("op", String(10), nullable=False),  # gte/lte/eq/contains/manual
    Column("cite", Text, nullable=False),  # 규격서 조문 위치 — 근거 없는 판정 금지(S8 원칙 2)
    Column("matched_product_id", Integer, ForeignKey("product.id")),
    Column("judgement", String(10), nullable=False, server_default="unknown"),  # ok/no/unknown
    Column("note", Text),
)

analysis_flag = Table(
    "analysis_flag",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("analysis_id", Integer, ForeignKey("analysis.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200), nullable=False),
    Column("quote", Text, nullable=False),
    Column("judgement", String(20), nullable=False),
    Column("action", Text),
)

analysis_check = Table(
    "analysis_check",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("analysis_id", Integer, ForeignKey("analysis.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200), nullable=False),
    Column("detail", Text),
    Column("critical", Boolean, nullable=False, server_default="false"),
    Column("done", Boolean, nullable=False, server_default="false"),
    Column("done_by", String(255)),
    Column("done_at", DateTime(timezone=True)),
)

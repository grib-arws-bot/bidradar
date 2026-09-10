"""관심주제 기반 요약 리포트(뉴스레터 스냅샷). 08절에는 없던 테이블 — 서명된 공유 링크
(의사결정_로그 8·9번, 로그인 없는 고객용 열람)를 실제로 구현하며 신설.

이메일에는 요약만, 상세는 이 스냅샷을 가리키는 토큰 링크로 — 링크는 회사(고객) 단위 공용,
여러 번·여러 사람이 봐도 되고(재사용 가능), 조회수만 근사치로 집계한다(2026-09-01 결정).
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, UniqueConstraint, func
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
    # AI 코멘트(2026-09-05, "Phase 1" 보고서 최적화) — 공고 선별 자체는 여전히 규칙 기반
    # (customer_interest.py top_matches, CLAUDE.md 원칙 1과 같은 이유로 LLM이 안 함). 이미
    # 선별된 목록에 "왜 이 고객에게 의미있는지" 설명만 LLM(Sonnet)이 덧붙인다 — notices(JSONB)
    # 각 항목에 commentary 키로 병합해 저장. 관리자가 수동으로 실행(자동 실행 금지 원칙).
    Column("ai_generated_at", DateTime(timezone=True)),
    Column("ai_tokens", Integer, nullable=False, server_default="0"),
    Column("ai_cost_usd", Numeric(10, 4), nullable=False, server_default="0"),
)

# 공고별 "AI 사업 추진 전략"(2026-09-05) — 공개 리포트에서 고객이 공고를 눌러 들어가면 보는
# 별도 페이지. 미리 만들어두지 않고 고객이 처음 열 때만 생성하되, (customer_id, notice_id)
# unique 제약으로 중복 생성을 막는다 — INSERT ... ON CONFLICT DO NOTHING이 원자적 "선점"
# 역할(여러 번 눌러도 한 번만 LLM 호출). 리포트(newsletter_report)가 아니라 고객 단위로
# 캐싱하는 이유: 같은 공고가 여러 주의 리포트에 반복 등장할 수 있는데, 그때마다 다시 생성하면
# 낭비이고 내용도 리포트 스냅샷과 무관하게 고객+공고 조합에만 의존하기 때문.
notice_strategy = Table(
    "notice_strategy",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("notice_id", Integer, ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
    Column("status", String(20), nullable=False, server_default="pending"),  # pending/done/failed
    Column("strategy_md", Text),
    Column("model", String(50)),
    Column("input_tokens", Integer, nullable=False, server_default="0"),
    Column("output_tokens", Integer, nullable=False, server_default="0"),
    Column("cost_usd", Numeric(10, 4), nullable=False, server_default="0"),
    Column("error_message", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("customer_id", "notice_id", name="uq_notice_strategy_customer_notice"),
)

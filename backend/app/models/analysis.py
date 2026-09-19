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
from sqlalchemy.dialects.postgresql import JSONB

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
    # A2가 요구사양(analysis_requirement)과 별개로 뽑는 서술형 요약 — 사업개요·사업내용·평가기준처럼
    # 항목/값/연산자로 쪼갤 수 없는 내용(2026-09-05, 공고 상세페이지 종합 요청). 판정이 아니라
    # 추출·정리이므로 원칙 1과 무관.
    Column("summary", JSONB, nullable=True),
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
    # 원본 파일은 저장하지 않는다(2026-09-03 결정) — notice.url이 항상 있어 필요하면 재다운로드
    # 가능하고, 저장공간이 무한정 느는 것도 피한다. 추출된 텍스트만 여기 남긴다.
    Column("text", Text),
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
    # 이 요구사항이 특정 과제(analysis.summary.content_items[].title)에 속하면 그 title을 그대로
    # 담는다(2026-09-05, "성능 요구사항은 과제 개요의 각 과제 하위에" 요청) — 화면에서 과제별로
    # 묶어 보여주기 위한 용도일 뿐, 판정 로직(match.py)엔 영향 없음.
    Column("task_ref", String(200)),
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

# 사내 sLLM(B, extract-requirements) 요구사항 추출 미리보기(2026-09-20, 의사결정_로그 178번).
# analysis_requirement(A2, Haiku)와 물리적으로 분리된 테이블이다 — match.py(A3)는 이 테이블을
# 절대 읽지 않는다. sLLM 추출은 A2만큼 검증되지 않은 무료 미리보기일 뿐, 실제 제품 매칭
# 판정의 근거가 되면 안 된다(두 계층 LLM 설계: sLLM=미리보기, Haiku=확정).
analysis_sllm_preview = Table(
    "analysis_sllm_preview",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("analysis_id", Integer, ForeignKey("analysis.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("status", String(20), nullable=False),  # sLLM job 상태 값 그대로: queued/running/done/failed
    Column("sllm_job_id", String(100)),
    Column("chunks_processed", Integer),
    Column("chunks_total", Integer),
    # sllm_verification.sanitize_sllm_requirements()를 거친 결과만 저장(근거 검증+중복 제거 후)
    Column("requirements", JSONB),
    Column("rejected_ungrounded_count", Integer),
    Column("duplicate_count", Integer),
    Column("error", Text),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True)),
)

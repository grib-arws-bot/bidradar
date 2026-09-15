"""관심 · 검색 (구현스펙 08절). v0.3 — user_* 대신 customer_* (03절·S7, 단일 계정 로그인 결정).

그립 자신도 customer 테이블의 행 하나(plan_tier='internal')로 취급한다(의사결정_로그 9번).
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Table,
    Text,
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
    # 담당자 상세(2026-09-05, 고객 관리 CRUD 요청) — 담당자 1명 기준(복수 담당자가 필요해지면
    # 별도 테이블로 승격).
    Column("contact_name", String(100)),
    Column("contact_title", String(100)),
    Column("contact_phone", String(50)),
    # 보고서 수신자 이메일 목록(2026-09-05) — contact_email(주 담당자)과 별개로, 리포트를
    # 참조로 받을 추가 수신자들. 문자열 배열.
    Column("report_recipient_emails", JSONB, nullable=False, server_default="[]"),
    # AI 고객 분석(2026-09-11, "소개서 파일"에서 개명)에 파일과 함께 넣을 참고 URL 목록 —
    # report_recipient_emails와 같은 방식(JSONB 문자열 배열).
    Column("reference_urls", JSONB, nullable=False, server_default="[]"),
    Column("active", Boolean, nullable=False, server_default="true"),
    # 고객 프로필 요약(2026-09-05, "Phase 1" 보고서 최적화 설계) — 소개서 파일(customer_document)
    # 원문을 매 보고서 생성마다 LLM에 넣는 대신, 한 번 요약해 MD로 캐싱해둔다(사용자 확정 — 비용
    # 절감·검증 가능성). 소개서를 새로 올리거나 바꿔도 자동 재요약하지 않는다 — 관리자가 수동
    # 버튼으로만("고객사 AI 재분석은 관리자가 수동으로", CLAUDE.md 원칙 3과 같은 이유).
    Column("profile_summary_md", Text),
    Column("profile_summarized_at", DateTime(timezone=True)),
    Column("profile_summary_tokens", Integer, nullable=False, server_default="0"),
    Column("profile_summary_cost", Numeric(10, 4), nullable=False, server_default="0"),
    # 관심 공고 추천 시 적용할 금액 하한(2026-09-07 사용자 지시) — 이 값 이상인 est_price를
    # 가진 공고만 추천 대상이 된다(app/services/customer_interest.py). NULL이면 필터 없음.
    # 2026-09-05엔 추정가격 조건을 "안 쓴다"고 뺐었는데(→ 이 항목에서 하한선만 다시 도입,
    # 의사결정_로그 참고), est_price가 아예 없는(미공개) 공고는 하한을 만족하는지 확인할 수
    # 없어 필터가 걸려 있을 때는 함께 제외된다.
    Column("interest_price_min", Numeric(16, 0)),
    # 보고서 메일 자동발송 (요일,시각) 쌍의 배열(2026-09-14 도입, 2026-09-15 두 차례 수정).
    # 처음엔 days(요일 여러 개)·times(시각 여러 개)를 따로 둬서 "요일 아무거나 × 시각
    # 아무거나"(카르테시안 곱)로 실행됐는데, 사용자가 실제로 원한 건 "월 13시, 목 14시"처럼
    # 요일마다 다른 시각을 지정하는 것이었다 — 그 둘은 다른 데이터 모델이라 뒤늦게 재설계.
    # 각 원소는 {"day": ISO 요일번호(1=월~7=일), "time": "HH:MM"} — source.schedule_times와
    # 같은 이유(로케일 비의존)로 요일도 숫자로 저장. 최대 3쌍(source.schedule_times와 동일
    # 상한). 자동발송은 이 배열이 비어있지 않아야 실제로 동작한다(app/scheduler.py
    # run_due_customer_emails) — 관리자가 명시적으로 켜는 설정이라 CLAUDE.md 원칙 3
    # "자동 실행 금지"와 충돌하지 않는다(source의 auto_extract/auto_analyze와 같은 논리).
    Column("report_auto_send_schedule", JSONB, nullable=False, server_default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# 고객 보유 소개서 파일(2026-09-05, 다중 업로드) — 별도 업로드 볼륨 없이 DB에 바이너리로
# 저장한다(사용자 확정) — 백엔드 이미지가 자주 재배포돼 로컬 디스크에 두면 파일이 사라지고,
# DB(db_data 볼륨)는 이미 영속적이라 새 인프라 없이 안전하다. 고객당 파일 수·크기가 크지
# 않을 것으로 보여(내부 소개서 문서) 이 방식으로 충분하다.
customer_document = Table(
    "customer_document",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("content_type", String(100)),
    Column("size_bytes", Integer, nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("uploaded_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("uploaded_by", String(255), nullable=False, server_default="report@grib.co.kr"),
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
    # 관심주제별 3단계 우선순위(2026-09-05, 사용자 지시) — 회사 핵심 사업 주제(예: 산업안전)와
    # 부차적 관심사(예: 농수산)를 매칭 점수에서 구분하기 위함. high/normal/low 세 값만 허용
    # (app/services/customer_interest.py TOPIC_PRIORITY_SCORE).
    Column("priority", String(10), nullable=False, server_default="normal"),
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


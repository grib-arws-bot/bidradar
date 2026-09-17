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
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import metadata

# BAAI/bge-m3(자체 호스팅, app/services/embeddings.py) dense 임베딩 출력 차원(2026-09-16) —
# 규칙 매칭과 나란히 비교할 코사인 유사도 매칭용. 새 외부 벤더 키 없이 서버에서 직접 추론
# (다국어 검색 벤치마크에서 OpenAI text-embedding-3-small을 앞서는 경우가 많고, 한국어
# 성능도 좋음 — 조사 결론).
EMBEDDING_DIM = 1024

org = Table(
    "org",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("code", String(50)),  # 나라장터 등 발주기관 코드
    Column("category", String(100)),  # 교육청/공기업/중앙부처 등
    Column("abbr", String(30)),  # 기관약자(NIPA 등) — 관리자 페이지 "소스 관리" 발주기관 목록용
    Column("notice_url", Text),  # 기관별 공고 페이지 링크. 없으면 프론트가 source.homepage_url로 대체
    # 이 기관 공고를 어느 소스(공고기관/채널)로 수집하는지. 나라장터처럼 여러 기관을 한 소스가
    # 커버하는 경우가 대부분이라 nullable — 아직 채널이 정해지지 않은 기관도 있을 수 있다
    Column("source_id", ForeignKey("source.id", ondelete="SET NULL")),
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
    # 업무구분(물품/용역/공사/외자) — 나라장터 API는 이 값을 응답 필드가 아니라 "어느 오퍼레이션을
    # 호출했는지"로 구분한다(설계안 03절). source_config.config의 정적 힌트에서 채운다.
    Column("biz_type", String(20)),
    # 사업유형(개발/운영/유지보수/구축/구매/공사 등) — 제목 키워드 기반 근사 추정(2026-09-01
    # 요청). 첨부파일까지 봐야 정확해지는 건 S8 심층분석의 몫 — 여기는 전체 공고에 자동으로
    # 도는 가벼운 1차 추정치일 뿐이라 오판 가능성을 인지하고 쓴다. (2026-09-06 — A2 구조화
    # 결과 기반으로 연구/개발/유지보수/운영/공사/임대 등을 정확히 분류하는 후속 기능 예정,
    # 구현스펙 07절 참고. 아직 미착수.)
    Column("work_type", String(20)),
    Column("title", Text, nullable=False),
    Column("org_id", Integer, ForeignKey("org.id")),
    Column("est_price", Numeric(16, 0)),
    Column("region", String(100)),
    Column("open_dt", DateTime(timezone=True)),
    Column("close_dt", DateTime(timezone=True)),
    Column("url", Text, nullable=False),
    Column("pipeline_stage", String(30), nullable=False, server_default="collected"),  # S2 칸반 단계
    Column("assignee_name", String(100)),  # 자유텍스트 담당자명(개별 계정 없음, 03절 v0.3)
    # 소스별 부가 메타데이터(2026-09-02) — IRIS 공모유형·소관부처·접수상태·D-day처럼 명명 컬럼에
    # 안 들어가는 나머지 필드. 소스마다 필드가 달라 전용 컬럼을 늘리지 않고 JSONB로 받는다
    # (설계안 04-1 "범용 매퍼" 원칙). PII는 여기에도 절대 들어가면 안 됨 — mapper.py의
    # PII_BANNED_TARGET_FIELDS가 "extra:"로 시작하는 target_field에도 동일하게 적용됨.
    Column("extra", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # 같은 사업이 발주계획→사전규격→입찰공고로 단계 진행되면 여러 notice 행으로 각각 수집된다
    # (2026-09-06, 사용자 지시). "동일 발주기관+동일 사업명"으로 묶어 가장 최근 공고만 남기고
    # 나머지는 이 컬럼에 최신 건의 id를 채워 무효화 표시한다 — 하드 삭제는 안 함(감사·추적
    # 가능성 유지). NULL이면 아직 유효(최신)한 공고. app/services/notice_dedup.py.
    Column("superseded_by_notice_id", Integer, ForeignKey("notice.id", ondelete="SET NULL")),
    # 코사인 유사도 매칭(2026-09-16) — 제목+발주기관+지역+단계를 자체 호스팅 bge-m3로 임베딩한
    # 벡터(자체 호스팅 전환은 의사결정_로그 159번). 배치(app/services/embeddings.py)가 서서히
    # 채우므로 NULL이 정상(아직 처리 안 됨).
    Column("embedding", Vector(EMBEDDING_DIM)),
    # 임베딩이 실제로 채워진 시각(2026-09-17, 전체 현황 "누적 데이터" 그래프의 "임베딩 완료
    # 누적" 계열용) — embedding 자체엔 시각 정보가 없어 이 컬럼 없이는 "언제 얼마나 채워졌는지"
    # 과거 추이를 재구성할 방법이 없다. NULL이면 아직 미완료.
    Column("embedded_at", DateTime(timezone=True)),
    # 2026-09-17 — 제목만으로는 규칙 매칭(첨부 전체를 이미 반영, rule_ver=2)과 정보량 차이가
    # 너무 커서(20건 중 2~3건만 일치) 비교가 무의미하다는 지적 — A1 첨부 전체 추출 텍스트를
    # 더한 두 번째 임베딩을 별도 컬럼에 둔다. embedding을 덮어쓰지 않는 이유: 덮어쓰면
    # "제목만" 결과가 사라져 매칭 방식 비교 화면에서 3방향 비교(규칙/코사인-제목/코사인-첨부)
    # 자체가 불가능해진다.
    Column("embedding_a1", Vector(EMBEDDING_DIM)),
    Column("embedded_a1_at", DateTime(timezone=True)),
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

# 공고 탐색 화면의 제목 제외 키워드(2026-09-13 사용자 지시) — keyword_rule(L2 관심주제
# 채점용)과는 완전히 별개: 이건 "이 단어가 제목에 있으면 화면에서 아예 안 보이게" 하는
# 조회 시점 필터일 뿐, 수집·채점 로직에는 전혀 관여하지 않는다. 관리 편의를 위해 그룹을
# 여러 개 두지 않고 딱 하나의 목록으로만 관리한다(그룹 테이블 자체가 불필요) — 화면에서는
# 이 목록 전체를 "켜고 끌 수 있는 하나의 필터 그룹"으로 노출하고, 그때그때 추가하는 즉석
# 단어는 DB에 저장하지 않고 조회 시 파라미터로만 합쳐진다(app/services/notice_query.py).
notice_title_exclude_word = Table(
    "notice_title_exclude_word",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("term", String(100), nullable=False, unique=True),
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

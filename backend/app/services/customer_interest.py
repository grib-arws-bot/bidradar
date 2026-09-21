"""S7 고객 관심 주제 관리(U5b, 의사결정_로그 8·9번). 관심도는 조회 시점 계산·캐시 없음
(설계안 08절 공식 그대로) — 고객 수십 곳 규모에서 사전 계산은 재계산 부담만 만든다."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection

from app.collector.work_type import WORK_TYPE_CATALOG, WORK_TYPE_PREFERENCES
from app.models import (
    customer,
    customer_followed_org,
    customer_interest,
    customer_interest_term,
    interest_topic,
    notice,
    notice_score,
    org,
    source,
)
from app.services.notice_classification import notice_status_label, notice_type_of, work_type_label
from app.services.notice_query import compute_bid_status

# 스펙에 구체적 수치가 없어 U5b에서 확정. 고객별로 달라져야 하면 그때 customer 컬럼으로 승격.
MIN_SCORE = 30

# 관심주제 3단계 우선순위(2026-09-05, 사용자 지시) — "관심주제로 선택만 하면 전부 +30으로
# 동일하게 취급돼, 회사 핵심 사업(예: 산업안전)과 부차적 관심사(예: 농수산)가 구분이 안
# 된다"는 지적에 따라 도입. normal(30)은 각 우선순위가 "매칭 강도 최대일 때" 받는 만점이다
# (2026-09-08 재설계 이후 의미 — 아래 TOPIC_STRENGTH 참고).
TOPIC_PRIORITIES = ("high", "normal", "low")
TOPIC_PRIORITY_SCORE = {"high": 40, "normal": 30, "low": 15}

# 추천 알고리즘 재설계(2026-09-08, 사용자 지시 — 심층 기술 조사 후 결정, docs/구현스펙.md
# "향후 과제" 참고). 예전엔 "우선순위 점수를 그대로 더하기 + 매칭된 주제 중 최고 우선순위
# 하나만 사용"이었다 — 매칭 강도(l2_score)를 완전히 무시했고, 우선순위만 높으면 키워드가
# 거의 안 맞아도 항상 40점이 보장돼 오탐(false positive)을 점수로 못 눌렀다(GIS 키워드
# 오탐 사고와 같은 근본 원인). 조사 결과(AHP 다기준의사결정의 가중 기하평균, 신용평점표의
# 구간화 가산) 기준으로 두 가지를 바꾼다:
#   1) 우선순위 점수를 매칭 강도(0.15~1.0으로 정규화한 l2_score)와 곱한다 — 강도가 약하면
#      우선순위가 높아도 점수가 크게 깎인다("보상 효과" 차단).
#   2) 여러 관심주제에 매칭되면 noisy-OR(1 - Π(1-p))로 결합한다 — 최고값 하나만 쓰고
#      나머지를 버리던 것과 달리, 여러 주제에 걸치는 공고를 원칙 있게 더 우대하되 강한
#      신호 하나가 약한 신호들에 희석되지 않는다.
# 분석 심화도(제목만/첨부분석/AI분석)는 의도적으로 이 점수에 안 넣는다 — "관심 여부"와
# "판단 근거를 얼마나 자세히 확인했는가"는 다른 질문이고, 섞으면 분석이 끝날 때마다 순위가
# 설명 없이 바뀌어 신뢰 문제가 생긴다(조사 결론, RFP 매칭 업계·IR 메타데이터 완전성 연구
# 공통 관행). 그 정보는 notice_status_label 등 별도 배지로만 노출한다.
TOPIC_STRENGTH_REFERENCE = 10  # 이 이상이면 "매우 강한 매치"로 보고 강도를 1.0으로 포화
TOPIC_STRENGTH_FLOOR = 0.15  # 승격 기준(L2_PROMOTE_THRESHOLD=2)을 겨우 넘긴 약한 매치도
# 완전히 죽이지는 않는다 — 진짜 약한 관심사까지 추천에서 사라지면 안 됨.


def _topic_strength(l2_score: int) -> float:
    return max(TOPIC_STRENGTH_FLOOR, min(1.0, l2_score / TOPIC_STRENGTH_REFERENCE))


def _strength_label(strength: float) -> str:
    if strength >= 0.66:
        return "강한 일치"
    if strength >= 0.33:
        return "보통 일치"
    return "약한 일치"


@dataclass
class InterestDraft:
    topic_ids: list[int] = field(default_factory=list)
    topic_priorities: dict[int, str] = field(default_factory=dict)  # topic_id -> high/normal/low, 없으면 normal
    terms: list[str] = field(default_factory=list)
    followed_org_ids: list[int] = field(default_factory=list)
    # 관심 공고 추천 시 적용할 금액 하한(2026-09-07 사용자 지시) — 이 값 이상인 est_price를
    # 가진 공고만 추천 대상. None이면 필터 없음(기존 동작과 동일).
    price_min: int | None = None
    # 관심 사업유형 선호(2026-09-21, 의사결정_로그 192번) — app/collector/work_type.
    # WORK_TYPE_CATALOG 중 값 -> "positive"(선호)/"negative"(비선호). 지정 안 한 사업유형은
    # 중립(신호 자체가 안 켜짐). 같은 날 후속 지시로 단순 선택(있다/없다)에서 3단계로
    # 확장 — 감리·구매처럼 "들어가면 오히려 감점해야 할" 사업유형이 있다는 지적 때문.
    # 지금은 매칭 방식 비교(recommendation_signals.py)에서만 쓰이고 top_matches(실제
    # 리포트)에는 반영되지 않는다.
    work_type_prefs: dict[str, str] = field(default_factory=dict)


def list_customers(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(customer.c.id, customer.c.name, customer.c.plan_tier).order_by(customer.c.id)
    ).mappings().all()
    return [dict(r) for r in rows]


def get_topic_catalog(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(interest_topic.c.id, interest_topic.c.name)
        .where(interest_topic.c.active.is_(True))
        .order_by(interest_topic.c.sort_order)
    ).mappings().all()
    return [dict(r) for r in rows]


def get_interest_profile(conn: Connection, customer_id: int) -> dict | None:
    cust = conn.execute(
        select(
            customer.c.id, customer.c.name, customer.c.interest_price_min, customer.c.interest_work_types
        ).where(customer.c.id == customer_id)
    ).mappings().first()
    if cust is None:
        return None

    interest_rows = conn.execute(
        select(customer_interest.c.interest_topic_id, customer_interest.c.priority)
        .where(customer_interest.c.customer_id == customer_id)
    ).all()
    topic_ids = [r.interest_topic_id for r in interest_rows]
    topic_priorities = {r.interest_topic_id: r.priority for r in interest_rows if r.priority != "normal"}
    terms = [r[0] for r in conn.execute(
        select(customer_interest_term.c.term).where(customer_interest_term.c.customer_id == customer_id)
    )]
    followed_org_ids = [r[0] for r in conn.execute(
        select(customer_followed_org.c.org_id).where(customer_followed_org.c.customer_id == customer_id)
    )]

    return {
        "customer_id": cust["id"],
        "customer_name": cust["name"],
        "topic_ids": topic_ids,
        "topic_priorities": topic_priorities,
        "terms": terms,
        "followed_org_ids": followed_org_ids,
        "price_min": int(cust["interest_price_min"]) if cust["interest_price_min"] is not None else None,
        "topics": get_topic_catalog(conn),
        "work_type_prefs": cust["interest_work_types"] if isinstance(cust["interest_work_types"], dict) else {},
        "work_types": list(WORK_TYPE_CATALOG),
    }


def save_interest_profile(conn: Connection, customer_id: int, draft: InterestDraft) -> None:
    """전체 치환 — 부분 업데이트가 아니라 항상 화면의 현재 상태 전체로 동기화한다."""
    for priority in draft.topic_priorities.values():
        if priority not in TOPIC_PRIORITIES:
            raise ValueError(f"허용되지 않은 우선순위: {priority} (허용: {', '.join(TOPIC_PRIORITIES)})")
    if draft.price_min is not None and draft.price_min < 0:
        raise ValueError(f"금액 하한은 0 이상이어야 합니다: {draft.price_min}")
    for work_type, pref in draft.work_type_prefs.items():
        if work_type not in WORK_TYPE_CATALOG:
            raise ValueError(f"허용되지 않은 사업유형: {work_type} (허용: {', '.join(WORK_TYPE_CATALOG)})")
        if pref not in WORK_TYPE_PREFERENCES:
            raise ValueError(f"허용되지 않은 사업유형 선호: {pref} (허용: {', '.join(WORK_TYPE_PREFERENCES)})")

    conn.execute(
        customer.update().where(customer.c.id == customer_id)
        .values(interest_price_min=draft.price_min, interest_work_types=draft.work_type_prefs)
    )

    conn.execute(delete(customer_interest).where(customer_interest.c.customer_id == customer_id))
    for topic_id in draft.topic_ids:
        priority = draft.topic_priorities.get(topic_id, "normal")
        conn.execute(
            insert(customer_interest).values(customer_id=customer_id, interest_topic_id=topic_id, priority=priority)
        )

    conn.execute(delete(customer_interest_term).where(customer_interest_term.c.customer_id == customer_id))
    for term in draft.terms:
        if term.strip():
            conn.execute(insert(customer_interest_term).values(customer_id=customer_id, term=term.strip()))

    conn.execute(delete(customer_followed_org).where(customer_followed_org.c.customer_id == customer_id))
    for org_id in draft.followed_org_ids:
        conn.execute(insert(customer_followed_org).values(customer_id=customer_id, org_id=org_id))


def _candidate_notices(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(
            notice.c.id,
            notice.c.notice_no,
            notice.c.title,
            notice.c.stage,
            notice.c.biz_type,
            notice.c.work_type,
            notice.c.org_id,
            notice.c.source_id,
            notice.c.est_price,
            notice.c.region,
            notice.c.open_dt,
            notice.c.close_dt,
            org.c.name.label("org_name"),
            source.c.channel_name,
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
        .join(source, source.c.id == notice.c.source_id, isouter=True)
        # 단계별 중복 공고 중 최신 건이 아닌 것은 매칭·리포트 대상에서 제외한다
        # (2026-09-06, notice_dedup.find_and_mark_superseded).
        .where(notice.c.superseded_by_notice_id.is_(None))
        # 발주계획은 매칭·리포트 대상에서 아예 제외한다(2026-09-15 사용자 지시) — 규격서·
        # 첨부문서 없이 사업명 한 줄만 있어 관심주제 매칭 신호(l2_score)가 구조적으로 약해,
        # SECTION_LIMITS가 10자리를 예약해도 채울 후보가 거의 없었다(실측: 그립 매칭
        # 820건 중 발주계획 0건). 공고 탐색(공고 목록 화면)에서는 그대로 보인다 — 여기서
        # 빼는 건 "관심 리포트" 매칭 대상에서만이다.
        .where(notice.c.stage != "발주계획")
    ).mappings().all()
    return [dict(r) for r in rows]


def _notice_topic_scores(conn: Connection) -> dict[int, dict[int, int]]:
    """공고별로 매칭된 관심주제 → l2_score(매칭 강도). 같은 (공고,주제) 조합에 제목 매칭·
    첨부문서 매칭 등 여러 행이 있을 수 있어(2026-09-07 첨부분석 채점 도입) 그중 가장 강한
    신호(최댓값)를 쓴다 — 약한 신호가 강한 신호를 희석하면 안 된다는 원칙(2026-09-08)과 같다."""
    mapping: dict[int, dict[int, int]] = {}
    for notice_id, topic_id, l2_score in conn.execute(
        select(notice_score.c.notice_id, notice_score.c.interest_topic_id, notice_score.c.l2_score)
    ):
        bucket = mapping.setdefault(notice_id, {})
        bucket[topic_id] = max(bucket.get(topic_id, 0), l2_score)
    return mapping


def _serialize(n: dict, score: int, topics: list[str]) -> dict:
    bid_status = compute_bid_status(n.get("open_dt"), n.get("close_dt"), datetime.now(timezone.utc))
    notice_type = notice_type_of(n.get("channel_name"))
    return {
        "id": n["id"],
        "notice_no": n["notice_no"],
        "title": n["title"],
        "stage": n["stage"],
        "org_name": n["org_name"],
        "source_id": n["source_id"],  # 리포트 생성 시 출처표시 문구(source.attribution_text)를
        # 붙이는 데만 씀(advisory INBOX #7) — 화면에 그대로 노출하지 않음.
        "est_price": int(n["est_price"]) if n["est_price"] is not None else None,
        "region": n.get("region"),
        "open_dt": n["open_dt"].isoformat() if n.get("open_dt") else None,
        "close_dt": n["close_dt"].isoformat() if n["close_dt"] else None,
        "score": score,
        # 공개 리포트 카드에 내부 공고 탐색과 같은 배지를 보여주기 위함(2026-09-05 요청).
        "notice_type": notice_type,
        "bid_status": bid_status,
        "notice_status_label": notice_status_label(notice_type, n["stage"], bid_status),
        "work_type_label": work_type_label(notice_type, n.get("biz_type")),
        # 이 공고가 왜 관심공고로 떴는지(어느 관심주제와 일치했는지) 표시하기 위함
        # (2026-09-06 요청) — 고객이 선택한 관심주제 중 실제로 매칭된 것만, sort_order 순.
        "topics": topics,
    }


def _passes_hard_filters(n: dict, draft: InterestDraft, now: datetime) -> bool:
    """점수 계산 방식(규칙 매칭·코사인 유사도 등)과 무관하게 항상 먼저 적용하는 하드 필터.
    2026-09-16 — 코사인 유사도 매칭(cosine_matching.py)이 규칙 매칭과 공정하게 비교되려면
    같은 후보 풀·같은 필터를 써야 해서 _score_all()에서 분리했다."""
    # 이미 마감된 공고는 추천 대상에서 제외한다(2026-09-12 사용자 발견 — "입찰마감된
    # 항목이 추천항목에 추가된게 있다"). notice_cleanup.py가 마감 후 며칠은 DB에 그대로
    # 남겨두므로(공고 탐색에서 참고용으로 볼 수 있게) 존재 자체는 정상이지만, 추천은
    # "아직 참여할 수 있는 것"만 의미가 있어 별개로 걸러야 한다. close_dt가 없는 소스
    # (발주계획·사전규격 등)는 마감 여부를 판단할 근거가 없어 제외 대상이 아니다.
    if n["close_dt"] is not None and n["close_dt"] < now:
        return False
    # 금액 하한(2026-09-07) — est_price가 하한 미만이거나 아예 미공개(None)면 제외한다.
    # 미공개 공고는 하한을 만족하는지 확인할 방법이 없어 점수와 무관하게 하드 필터한다.
    if draft.price_min is not None and (n["est_price"] is None or n["est_price"] < draft.price_min):
        return False
    return True


def _score_all(conn: Connection, draft: InterestDraft, *, min_score: int) -> list[tuple[dict, int, dict[int, float]]]:
    """관심도 점수를 조회 시점에 그대로 계산해 전체 매칭 목록을 점수 내림차순으로 반환한다
    (2026-09-08 재설계 — 위 상수 블록 주석 참고). top_matches(리포트 생성)가 이 함수를 그대로
    쓴다. 세 번째 값(매칭된 관심주제 id → 매칭 강도)은 "왜 이 공고가 떴는지"와 강도 라벨을
    화면에 보여주기 위함(2026-09-06 도입, 2026-09-08 강도 포함으로 확장)."""
    notices = _candidate_notices(conn)
    topic_map = _notice_topic_scores(conn)
    topic_id_set = set(draft.topic_ids)
    terms = [t.strip() for t in draft.terms if t.strip()]
    org_id_set = set(draft.followed_org_ids)
    now = datetime.now(timezone.utc)

    scored: list[tuple[dict, int, dict[int, float]]] = []
    for n in notices:
        if not _passes_hard_filters(n, draft, now):
            continue

        score = 0.0
        notice_topics = topic_map.get(n["id"], {})
        matched_strengths = {t: _topic_strength(notice_topics[t]) for t in notice_topics if t in topic_id_set}
        if matched_strengths:
            # 우선순위 점수 × 매칭 강도(0.15~1.0) — 강도가 약하면 우선순위가 높아도 점수가
            # 크게 깎인다("보상 효과" 차단, 2026-09-08). 여러 주제가 매칭되면 noisy-OR로
            # 결합해 강한 신호 하나가 약한 신호들에 희석되지 않으면서도 결합도를 반영한다.
            topic_probs = [
                (TOPIC_PRIORITY_SCORE[draft.topic_priorities.get(t, "normal")] * strength) / 100
                for t, strength in matched_strengths.items()
            ]
            combined = 1 - math.prod(1 - p for p in topic_probs)
            score += combined * 100
        if terms and any(t.lower() in n["title"].lower() for t in terms):
            score += 25
        if org_id_set and n["org_id"] in org_id_set:
            score += 20
        score = round(min(score, 100))

        if score < min_score:
            continue
        scored.append((n, score, matched_strengths))

    # 관심주제 일치 점수가 최우선, 동점이면 마감이 임박한(D-day가 짧은) 공고를 위로
    # (2026-09-05 사용자 지시). 마감일 미상인 공고는 그다음(맨 뒤)으로 민다.
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    scored.sort(key=lambda triple: (-triple[1], triple[0]["close_dt"] is None, triple[0]["close_dt"] or far_future))
    return scored


# 리포트 2단계 섹션(2026-09-07 사용자 지시) — "발주계획·사전규격 단계에서 관심 공고를
# 찾아내는 것도 중요하다"는 지적. 예전엔 점수 하나로 전체를 줄세워 상위 20건만 뽑다 보니,
# 이미 마감 임박한 "입찰접수" 건들이 점수·마감임박 정렬 특성상 상위를 차지해 "사전규격"
# 단계 공고가 상위 20건에 아예 안 들 수 있었다. 섹션별로 자리를 미리 배정해서 이른 단계
# 공고도 항상 일정 수는 노출되게 한다. 프런트가 이 값(stage/notice_type/bid_status)으로
# 같은 분류를 다시 계산해 탭으로 나눠 보여준다.
# 2026-09-12 — 전체 상한을 20→50으로 올리며(사용자 지시) 기존 5:5:10(1:1:2) 비율을 그대로
# 유지해 10:10:30으로 스케일업.
# 2026-09-15 — 발주계획을 _candidate_notices()에서 아예 제외하면서(매칭 신호가 구조적으로
# 약해 이 자리를 채울 후보가 실질적으로 없었음) "plan" 섹션·자리를 제거했다.
# 2026-09-16 — 사용자 지시로 리포트 전체 상한을 30으로 낮추며(interest_report.py의
# REPORT_LIMIT도 같이 조정), prenotice:active 기존 1:2 비율을 유지해 10:20으로 스케일다운.
SECTION_LIMITS = {"prenotice": 10, "active": 20}


def _section_of(n: dict) -> str:
    if n["stage"] == "사전규격":
        return "prenotice"
    if notice_type_of(n.get("channel_name")) == "정부지원":
        bid_status = compute_bid_status(n.get("open_dt"), n.get("close_dt"), datetime.now(timezone.utc))
        # "!= in_progress"로 걸렀더니 이미 접수 마감(closed)된 건까지 "접수예정"으로 잘못
        # 분류되는 버그가 실제 리포트에서 확인됨(2026-09-07) — 접수 시작 전(upcoming·
        # unscheduled)일 때만 예정으로 본다. 마감된 건은 아래 기본값(active)으로 떨어진다
        # (공공입찰 stage=입찰공고의 마감건도 이미 active에 같이 있어 일관됨).
        if bid_status in ("upcoming", "unscheduled"):
            return "prenotice"
    return "active"


def top_matches(conn: Connection, draft: InterestDraft, *, limit: int = 20, min_score: int = MIN_SCORE) -> list[dict]:
    """리포트(뉴스레터) 생성용 — 섹션별 상한(SECTION_LIMITS)까지 채운 뒤 limit으로 최종 상한을
    건다. interest_report.py가 스냅샷을 만들 때 쓴다."""
    scored = _score_all(conn, draft, min_score=min_score)
    topic_rows = conn.execute(
        select(interest_topic.c.id, interest_topic.c.name).order_by(interest_topic.c.sort_order)
    ).all()
    topic_order = [r.id for r in topic_rows]
    topic_names = {r.id: r.name for r in topic_rows}

    section_counts = dict.fromkeys(SECTION_LIMITS, 0)
    picked: list[tuple[dict, int, dict[int, float]]] = []
    for n, score, matched in scored:
        section = _section_of(n)
        if section_counts[section] >= SECTION_LIMITS[section]:
            continue
        section_counts[section] += 1
        picked.append((n, score, matched))
        if len(picked) >= limit:
            break

    return [
        # 주제 이름 옆에 매칭 강도 라벨을 같이 보여준다(2026-09-08) — "왜 이 점수인지"를
        # 사람이 바로 검증할 수 있어야 한다는 원칙(CLAUDE.md S8 원칙 2와 같은 취지).
        _serialize(n, score, [f"{topic_names[t]}({_strength_label(matched[t])})" for t in topic_order if t in matched])
        for n, score, matched in picked
    ]


def draft_from_profile(profile: dict) -> InterestDraft:
    """저장된 프로필을 다시 InterestDraft로 — 리포트 생성(interest_report.py)이 쓴다."""
    return InterestDraft(
        topic_ids=profile["topic_ids"],
        topic_priorities=profile["topic_priorities"],
        terms=profile["terms"],
        followed_org_ids=profile["followed_org_ids"],
        price_min=profile["price_min"],
        work_type_prefs=profile["work_type_prefs"],
    )

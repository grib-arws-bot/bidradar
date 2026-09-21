"""공고 추천 다중 신호 — 비교 샌드박스 전용(2026-09-21, 의사결정_로그 192번).

규칙(키워드) 매칭 하나로만 순위를 매기던 걸 여러 신호로 확장해보되, "한꺼번에 다 넣지 않고
껐다 켰다 하며 비교"하고 싶다는 요청에 따라 신호를 이름별로 등록해두고 프로필(이름 조합)마다
다르게 켜서 비교한다. **`customer_interest.top_matches`(실제 고객 리포트 발송 경로)는 이
모듈을 쓰지 않는다** — 비교해서 결정하기 전까지는 실제 추천에 영향이 없다.

각 신호는 0~1 강도(1이 가장 강함) 또는 None(이 공고에 대해 이 신호를 평가할 수 없음 —
noisy-OR 결합에서 자동 제외한다, CLAUDE.md "확인 필요는 사람에게" 원칙과 같은 이유로 0점
벌점을 주지 않는다)을 후보 전체에 대해 **배치로** 계산한다(N+1 쿼리 금지).

입찰 자격요건은 여기 없다 — 사용자 지시로 점수에 안 섞고 별도 필터로만 쓸 예정(아직 그
필터 기능 자체가 없음).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Connection

from app.models import analysis, analysis_requirement, interest_topic, notice_score, notice_strategy
from app.services.cosine_matching import _query_embedding_for_profile, weighted_cosine_scores
from app.services.customer_interest import (
    InterestDraft,
    TOPIC_STRENGTH_FLOOR,
    TOPIC_STRENGTH_REFERENCE,
    _score_all,
    _serialize,
    _strength_label,
)

# A3(제품 대조) 판정이 있다는 것 자체가 "관심"보다는 "실행 가능성"에 가까운 강한 신호라
# 고정값을 쓴다(요구사항별로 세분화하지 않음 — 하나라도 ok가 있으면 유의미하다고 봄).
A3_MATCH_STRENGTH = 0.9
# notice_strategy 열람은 "고객이 이 공고를 이미 진지하게 들여다봤다"는 명시적 행동 신호.
# 2026-09-21 사용자 결정 — 열람했다고 감점·제외하지 않고 항상 긍정 신호로만 쓴다(고객이
# 명시적으로 "관심없음"을 표시하는 별도 기능이 생기기 전까지는).
STRATEGY_VIEWED_STRENGTH = 0.7
# 사업유형 신호 — notice.work_type/notice.biz_type이 전부 제목 기반 추정이거나(연구 등)
# API가 주는 값(물품/용역 등)이라도 "고객이 실제로 관심 있다고 밝힌 유형과 일치"라는
# 사실 자체의 신뢰도는 규칙(키워드 L2) 매칭보다는 약하게 잡는다.
WORK_TYPE_MATCH_STRENGTH = 0.6


def topic_strength(l2_score: int) -> float:
    """customer_interest._topic_strength와 동일 스케일 — 노이즈-OR 결합에 쓰는 다른 신호들과
    같은 0~1 축에 놓기 위해 이 모듈에서도 노출."""
    return max(TOPIC_STRENGTH_FLOOR, min(1.0, l2_score / TOPIC_STRENGTH_REFERENCE))


def work_type_signal(candidates: list[dict], work_type_ids: list[str]) -> dict[int, float | None]:
    """notice.work_type 또는 notice.biz_type이 고객이 선택한 사업유형 목록에 있으면
    WORK_TYPE_MATCH_STRENGTH, 없으면 None(둘 다 값이 없거나 안 겹치면 "이 신호로는 판단
    불가"로 취급 — 0점을 줘서 다른 신호를 깎으면 안 됨)."""
    wanted = set(work_type_ids)
    if not wanted:
        return {n["id"]: None for n in candidates}
    scores: dict[int, float | None] = {}
    for n in candidates:
        matched = n.get("work_type") in wanted or n.get("biz_type") in wanted
        scores[n["id"]] = WORK_TYPE_MATCH_STRENGTH if matched else None
    return scores


def sllm_confidence_signal(conn: Connection, notice_ids: list[int], topic_id_set: set[int]) -> dict[int, float | None]:
    """notice_score.sllm_confidence — 고객이 선택한 관심주제와 일치하는 행 중 최댓값(여러
    주제에 걸치면 noisy-OR가 아니라 최댓값만 쓴다 — 이 신호 자체가 이미 confidence라
    이중으로 결합할 이유가 없음). sLLM이 아직 그 공고를 확인 안 했으면(행 자체가 없음)
    None."""
    if not notice_ids or not topic_id_set:
        return dict.fromkeys(notice_ids, None)
    rows = conn.execute(
        select(notice_score.c.notice_id, notice_score.c.interest_topic_id, notice_score.c.sllm_confidence)
        .where(
            notice_score.c.notice_id.in_(notice_ids),
            notice_score.c.interest_topic_id.in_(topic_id_set),
            notice_score.c.sllm_confidence.is_not(None),
        )
    ).all()
    best: dict[int, float] = {}
    for row in rows:
        confidence = float(row.sllm_confidence)
        best[row.notice_id] = max(best.get(row.notice_id, 0.0), confidence)
    return {notice_id: best.get(notice_id) for notice_id in notice_ids}


def a3_match_signal(conn: Connection, notice_ids: list[int]) -> dict[int, float | None]:
    """이 공고의 **가장 최근** analysis에 판정('ok')이 하나라도 있으면 A3_MATCH_STRENGTH,
    분석 자체가 없거나 ok 판정이 없으면 None(= "확인 안 됨", 0점이 아님)."""
    if not notice_ids:
        return {}
    latest_ver = (
        select(analysis.c.notice_id, func.max(analysis.c.ver).label("max_ver"))
        .where(analysis.c.notice_id.in_(notice_ids))
        .group_by(analysis.c.notice_id)
        .subquery()
    )
    latest_analysis = (
        select(analysis.c.id, analysis.c.notice_id)
        .join(
            latest_ver,
            and_(analysis.c.notice_id == latest_ver.c.notice_id, analysis.c.ver == latest_ver.c.max_ver),
        )
        .subquery()
    )
    matched_notice_ids = {
        row.notice_id
        for row in conn.execute(
            select(latest_analysis.c.notice_id)
            .join(analysis_requirement, analysis_requirement.c.analysis_id == latest_analysis.c.id)
            .where(analysis_requirement.c.judgement == "ok")
            .distinct()
        )
    }
    return {notice_id: (A3_MATCH_STRENGTH if notice_id in matched_notice_ids else None) for notice_id in notice_ids}


def strategy_viewed_signal(conn: Connection, customer_id: int, notice_ids: list[int]) -> dict[int, float | None]:
    """notice_strategy에 (customer_id, notice_id) 행이 status='done'으로 있으면
    STRATEGY_VIEWED_STRENGTH, 없으면 None."""
    if not notice_ids:
        return {}
    viewed_ids = {
        row.notice_id
        for row in conn.execute(
            select(notice_strategy.c.notice_id).where(
                notice_strategy.c.customer_id == customer_id,
                notice_strategy.c.notice_id.in_(notice_ids),
                notice_strategy.c.status == "done",
            )
        )
    }
    return {notice_id: (STRATEGY_VIEWED_STRENGTH if notice_id in viewed_ids else None) for notice_id in notice_ids}


def _signal_weights(enabled_signals: frozenset[str]) -> dict[str, float]:
    return {"rule": 1.0, **dict.fromkeys(enabled_signals, 1.0)}


def score_with_profile(
    conn: Connection,
    draft: InterestDraft,
    profile: dict,
    *,
    customer_id: int,
    enabled_signals: frozenset[str],
    limit: int = 20,
) -> list[dict]:
    """`customer_interest.top_matches`와 같은 후보 풀·하드 필터·규칙(키워드) 점수를 기준
    축으로 삼고(min_score=0으로 걸러내지 않은 전체), enabled_signals에 있는 추가 신호를
    noisy-OR로 얹어 재정렬한다. min_score=0을 쓰는 이유 — 규칙 점수가 0이라도(키워드가
    전혀 안 맞아도) 다른 신호(코사인·sLLM 등)만으로 새로 떠오를 후보를 배제하면 안 됨."""
    scored = _score_all(conn, draft, min_score=0)
    if not scored:
        return []
    candidates = [n for n, _, _ in scored]
    notice_ids = [n["id"] for n in candidates]

    signal_values: dict[str, dict[int, float | None]] = {}
    if "work_type" in enabled_signals:
        signal_values["work_type"] = work_type_signal(candidates, draft.work_type_ids)
    if "cosine_weighted" in enabled_signals:
        query_embedding = _query_embedding_for_profile(conn, profile)
        signal_values["cosine_weighted"] = weighted_cosine_scores(conn, notice_ids, query_embedding)
    if "sllm_confidence" in enabled_signals:
        signal_values["sllm_confidence"] = sllm_confidence_signal(conn, notice_ids, set(draft.topic_ids))
    if "a3_match" in enabled_signals:
        signal_values["a3_match"] = a3_match_signal(conn, notice_ids)
    if "strategy_viewed" in enabled_signals:
        signal_values["strategy_viewed"] = strategy_viewed_signal(conn, customer_id, notice_ids)

    weights = _signal_weights(enabled_signals)
    combined: list[tuple[dict, int, dict[int, float]]] = []
    for n, rule_score, matched_strengths in scored:
        per_notice: dict[str, float | None] = {"rule": rule_score / 100}
        for name, values in signal_values.items():
            per_notice[name] = values.get(n["id"])
        combined_score = combine_noisy_or(per_notice, weights)
        combined.append((n, combined_score, matched_strengths))

    far_future = datetime.max.replace(tzinfo=timezone.utc)
    combined.sort(key=lambda triple: (-triple[1], triple[0]["close_dt"] is None, triple[0]["close_dt"] or far_future))
    picked = combined[:limit]

    topic_rows = conn.execute(select(interest_topic.c.id, interest_topic.c.name).order_by(interest_topic.c.sort_order)).all()
    topic_order = [r.id for r in topic_rows]
    topic_names = {r.id: r.name for r in topic_rows}
    return [
        _serialize(n, score, [f"{topic_names[t]}({_strength_label(matched[t])})" for t in topic_order if t in matched])
        for n, score, matched in picked
    ]


# 사용자 지시(2026-09-21) — 신호를 한꺼번에 다 넣지 않고 몇 개 조합을 만들어 비교한다.
# 자격요건은 여기 없다(별도 필터로만 쓸 예정, 점수에 안 섞음).
PROFILE_PRESETS: dict[str, dict] = {
    "rule": {"label": "규칙 매칭", "signals": frozenset()},
    "rule_worktype": {"label": "규칙+사업유형", "signals": frozenset({"work_type"})},
    "rule_cosine": {"label": "규칙+코사인(제목가중)", "signals": frozenset({"cosine_weighted"})},
    "rule_sllm": {"label": "규칙+sLLM confidence", "signals": frozenset({"sllm_confidence"})},
    "rule_a3": {"label": "규칙+A3 판정", "signals": frozenset({"a3_match"})},
    "rule_strategy": {"label": "규칙+전략열람", "signals": frozenset({"strategy_viewed"})},
    "all": {
        "label": "전체 신호",
        "signals": frozenset({"work_type", "cosine_weighted", "sllm_confidence", "a3_match", "strategy_viewed"}),
    },
}


def combine_noisy_or(scores: dict[str, float | None], weights: dict[str, float]) -> float:
    """1 - Π(1 - weight_i * score_i) — customer_interest.py의 관심주제 noisy-OR 결합과
    같은 철학. None인 신호는 결합에서 제외한다(그 신호가 "이 공고를 못 봤다/평가 못 했다"는
    뜻이지 "관련 없다"는 뜻이 아니므로 0으로 넣으면 안 됨). 활성 신호가 하나도 없으면 0.0."""
    complement = 1.0
    any_active = False
    for name, score in scores.items():
        if score is None:
            continue
        weight = weights.get(name, 1.0)
        complement *= 1 - max(0.0, min(1.0, weight * score))
        any_active = True
    return round((1 - complement) * 100) if any_active else 0

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
from typing import Callable

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
# 사실 자체의 신뢰도는 규칙(키워드 L2) 매칭보다는 약하게 잡는다. 2026-09-21 — 사용자 지시로
# "선호(+)/중립(0)/비선호(-)" 3단계로 확장(감리·구매처럼 오히려 감점해야 할 유형이 있다는
# 지적) — 음수는 combine_noisy_or()가 "억제 강도"로 해석해 기존 점수를 깎는다.
WORK_TYPE_MATCH_STRENGTH = 0.6


def topic_strength(l2_score: int) -> float:
    """customer_interest._topic_strength와 동일 스케일 — 노이즈-OR 결합에 쓰는 다른 신호들과
    같은 0~1 축에 놓기 위해 이 모듈에서도 노출."""
    return max(TOPIC_STRENGTH_FLOOR, min(1.0, l2_score / TOPIC_STRENGTH_REFERENCE))


def work_type_signal(candidates: list[dict], work_type_prefs: dict[str, str]) -> dict[int, float | None]:
    """notice.work_type 또는 notice.biz_type이 고객이 지정한 사업유형 선호(work_type_prefs:
    값 -> "positive"/"negative")에 있으면 그 부호의 WORK_TYPE_MATCH_STRENGTH, 지정 안 한
    사업유형(중립)이거나 애초에 선호를 하나도 안 정했으면 None — 0점을 줘서 다른 신호를
    깎으면 안 됨(중립은 "관련 없다"가 아니라 "이 축으로는 판단 안 함")."""
    if not work_type_prefs:
        return {n["id"]: None for n in candidates}
    scores: dict[int, float | None] = {}
    for n in candidates:
        pref = work_type_prefs.get(n.get("work_type")) or work_type_prefs.get(n.get("biz_type"))
        if pref == "positive":
            scores[n["id"]] = WORK_TYPE_MATCH_STRENGTH
        elif pref == "negative":
            scores[n["id"]] = -WORK_TYPE_MATCH_STRENGTH
        else:
            scores[n["id"]] = None
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
    weights: dict[str, float] | None = None,
    combine_fn: Callable[[dict[str, float | None], dict[str, float]], int] | None = None,
    signal_floor: dict[str, float] | None = None,
) -> list[dict]:
    """`customer_interest.top_matches`와 같은 후보 풀·하드 필터·규칙(키워드) 점수를 기준
    축으로 삼고(min_score=0으로 걸러내지 않은 전체), enabled_signals에 있는 추가 신호를
    결합해 재정렬한다. min_score=0을 쓰는 이유 — 규칙 점수가 0이라도(키워드가 전혀 안
    맞아도) 다른 신호(코사인·sLLM 등)만으로 새로 떠오를 후보를 배제하면 안 됨.

    2026-09-21 후속 — "전체 신호"(다섯 개를 한꺼번에 노이즈-OR로 결합)가 다른 프로필과
    너무 다르게 나온다는 실측 지적에, 결합 방식 자체를 실험해볼 수 있게 `weights`(기본
    전부 1.0 대신 신호별로 낮출 수 있음)·`combine_fn`(noisy-OR 대신 가중평균 등으로
    교체 가능)·`signal_floor`(예: 코사인이 0.5 미만이면 아예 None 취급 — 항상 어떤
    값이든 나오는 신호가 약한 값으로도 점수를 만들어내는 걸 막음)를 열어뒀다
    (의사결정_로그 198번, 신호 비교 팝업 전용)."""
    scored = _score_all(conn, draft, min_score=0)
    if not scored:
        return []
    candidates = [n for n, _, _ in scored]
    notice_ids = [n["id"] for n in candidates]

    signal_values: dict[str, dict[int, float | None]] = {}
    if "work_type" in enabled_signals:
        signal_values["work_type"] = work_type_signal(candidates, draft.work_type_prefs)
    if "cosine_weighted" in enabled_signals:
        query_embedding = _query_embedding_for_profile(conn, profile)
        signal_values["cosine_weighted"] = weighted_cosine_scores(conn, notice_ids, query_embedding)
    if "sllm_confidence" in enabled_signals:
        signal_values["sllm_confidence"] = sllm_confidence_signal(conn, notice_ids, set(draft.topic_ids))
    if "a3_match" in enabled_signals:
        signal_values["a3_match"] = a3_match_signal(conn, notice_ids)
    if "strategy_viewed" in enabled_signals:
        signal_values["strategy_viewed"] = strategy_viewed_signal(conn, customer_id, notice_ids)

    resolved_weights = weights if weights is not None else _signal_weights(enabled_signals)
    resolved_combine_fn = combine_fn if combine_fn is not None else combine_noisy_or
    combined: list[tuple[dict, int, dict[int, float], dict[str, float | None]]] = []
    for n, rule_score, matched_strengths in scored:
        # 2026-09-21 — 화면에서 "왜 이 점수인지" 신호별로 확인할 수 있어야 한다는 요청
        # (CLAUDE.md S8 원칙 2 "판정 근거를 붙인다"와 같은 취지) — per_notice를 그대로
        # breakdown으로 응답에 실어 보낸다. None은 "이 신호로는 평가 못 함"이지 0점이 아니다.
        per_notice: dict[str, float | None] = {"rule": rule_score / 100}
        for name, values in signal_values.items():
            value = values.get(n["id"])
            if signal_floor and name in signal_floor and value is not None and abs(value) < signal_floor[name]:
                value = None
            per_notice[name] = value
        combined_score = resolved_combine_fn(per_notice, resolved_weights)
        combined.append((n, combined_score, matched_strengths, per_notice))

    far_future = datetime.max.replace(tzinfo=timezone.utc)
    combined.sort(key=lambda item: (-item[1], item[0]["close_dt"] is None, item[0]["close_dt"] or far_future))
    picked = combined[:limit]

    topic_rows = conn.execute(select(interest_topic.c.id, interest_topic.c.name).order_by(interest_topic.c.sort_order)).all()
    topic_order = [r.id for r in topic_rows]
    topic_names = {r.id: r.name for r in topic_rows}
    return [
        {
            **_serialize(n, score, [f"{topic_names[t]}({_strength_label(matched[t])})" for t in topic_order if t in matched]),
            "signals": breakdown,
        }
        for n, score, matched, breakdown in picked
    ]


# 사용자 지시(2026-09-21) — 신호를 한꺼번에 다 넣지 않고 몇 개 조합을 만들어 비교한다.
# 자격요건은 여기 없다(별도 필터로만 쓸 예정, 점수에 안 섞음). description은 화면(매칭 방식
# 비교 페이지)에 컬럼 제목 아래 그대로 노출된다 — 입력 데이터와 계산 방식을 사람이 읽고
# 바로 이해할 수 있게 쓴다.
PROFILE_PRESETS: dict[str, dict] = {
    "rule": {
        "label": "규칙 매칭",
        "signals": frozenset(),
        "description": "키워드 사전(notice_score.l2_score)과 고객이 선택한 관심주제 우선순위만으로 계산합니다. LLM·임베딩 관여 없음 — 다른 모든 방식의 기준 축입니다.",
    },
    "rule_worktype": {
        "label": "규칙+사업유형",
        "signals": frozenset({"work_type"}),
        "description": "규칙 매칭에 사업유형(notice.work_type/biz_type) 선호를 더합니다. 고객이 사업유형마다 선호(+)/중립/비선호(-) 3단계로 지정할 수 있고, 선호는 점수를 올리고 비선호(예: 감리·구매)는 오히려 점수를 깎습니다. 중립이거나 아직 설정 안 한 사업유형은 이 신호가 아예 빠집니다.",
    },
    "rule_cosine": {
        "label": "규칙+코사인(제목가중)",
        "signals": frozenset({"cosine_weighted"}),
        "description": "규칙 매칭에 코사인 유사도를 더합니다. 고객 프로필(관심주제+키워드+AI 소개서 요약)과 공고(제목만 임베딩·제목+첨부 임베딩)를 bge-m3로 비교해 제목 60%·첨부 40%로 가중 평균합니다. 키워드가 정확히 안 맞아도 의미가 비슷하면 잡아낼 수 있습니다.",
    },
    "rule_sllm": {
        "label": "규칙+sLLM confidence",
        "signals": frozenset({"sllm_confidence"}),
        "description": "규칙 매칭에 사내 sLLM(Qwen3-4B)이 공고 제목만 보고 판단한 관심주제 일치 확신도(notice_score.sllm_confidence)를 더합니다. sLLM이 아직 그 공고를 안 봤으면 이 신호는 빠집니다.",
    },
    "rule_a3": {
        "label": "규칙+A3 판정",
        "signals": frozenset({"a3_match"}),
        "description": "규칙 매칭에 A3(제품 스펙 대조, 규칙 기반 — LLM 아님) 판정에서 'ok'가 하나라도 있는지를 더합니다. \"관심이 있는가\"가 아니라 \"우리가 실제로 충족할 제품이 있는가\"를 보는 성격이 다른 신호입니다. A2/A3 분석이 아직 안 된 공고는 빠집니다.",
    },
    "rule_strategy": {
        "label": "규칙+전략열람",
        "signals": frozenset({"strategy_viewed"}),
        "description": "규칙 매칭에 그 고객이 그 공고의 \"AI 사업 추진 전략\"을 실제로 열람했는지를 더합니다. 열람 자체를 관심의 긍정 신호로만 쓰고 감점·제외에는 안 씁니다. 같은 고객의 다른 공고에는 영향이 없습니다(공고별 1:1).",
    },
}


def combine_noisy_or(scores: dict[str, float | None], weights: dict[str, float]) -> int:
    """양의 신호(0~1)는 `1 - Π(1 - weight_i * score_i)`로 결합해 "기본 점수"를 만든다
    (customer_interest.py의 관심주제 noisy-OR 결합과 같은 철학). 2026-09-21 — 음의 신호
    (감리·구매처럼 "들어가면 감점해야 할" 사업유형 등, work_type_signal() 참고)는 이
    기본 점수에 별도로 곱해서 깎는 억제형(inhibitory) 노이즈-OR로 확장했다 — 음의 신호가
    있다고 없던 관련성을 만들어내면 안 되므로(양의 근거가 하나도 없으면 기본 점수 자체가
    0이라 음의 신호를 곱해도 여전히 0), 양쪽을 같은 곱에 섞지 않고 분리한다.

    None인 신호는 어느 쪽 계산에서도 제외한다(그 신호가 "평가 못 했다"는 뜻이지 "관련
    없다"·"감점 대상 아님"이라는 뜻이 아니므로 0으로 넣으면 안 됨)."""
    positive_complement = 1.0
    negative_complement = 1.0
    any_positive = False
    for name, score in scores.items():
        if score is None:
            continue
        weight = weights.get(name, 1.0)
        if score >= 0:
            positive_complement *= 1 - max(0.0, min(1.0, weight * score))
            any_positive = True
        else:
            suppression = max(0.0, min(1.0, weight * -score))
            negative_complement *= 1 - suppression
    base = (1 - positive_complement) if any_positive else 0.0
    return round(base * negative_complement * 100)


def combine_weighted_average(scores: dict[str, float | None], weights: dict[str, float]) -> int:
    """noisy-OR의 대안(2026-09-21, 의사결정_로그 198번) — 활성화된(None 아닌) 신호들의
    가중평균만 낸다. 곱셈이 아니라 평균이라 여러 신호가 동시에 켜져도 noisy-OR처럼
    빠르게 100점 근처로 포화되지 않는다. 음의 신호(비선호 사업유형 등)도 그냥 평균에
    끌어내리는 값으로 섞는다 — noisy-OR처럼 양/음을 분리하지 않는다(가중평균 자체가
    이미 "여러 근거를 뭉뚱그려 본다"는 성격이라 분리할 이유가 약함)."""
    active = [(weights.get(name, 1.0), score) for name, score in scores.items() if score is not None]
    if not active:
        return 0
    total_weight = sum(w for w, _ in active)
    if total_weight <= 0:
        return 0
    average = sum(w * s for w, s in active) / total_weight
    return round(max(0.0, min(1.0, average)) * 100)


# 2026-09-21 후속 — "전체 신호"(다섯 개를 한꺼번에 노이즈-OR로 결합)를 메인 비교 화면에서
# 빼고, 결합 방식 자체를 실험하는 별도 팝업으로 옮겼다(의사결정_로그 198번) — 실측해보니
# 신호 하나만 강해도 노이즈-OR이 100점 근처로 빠르게 포화되는데, 다섯 개를 한꺼번에
# 켜면 서로 다른 공고가 서로 다른 신호로 각자 포화돼 결과가 예측하기 어렵게 달라짐.
ALL_SIGNALS = frozenset({"work_type", "cosine_weighted", "sllm_confidence", "a3_match", "strategy_viewed"})
_ALL_SIGNALS_LOW_WEIGHTS = {"rule": 1.0, **dict.fromkeys(ALL_SIGNALS, 0.5)}

ALL_SIGNAL_VARIANTS: dict[str, dict] = {
    "all_current": {
        "label": "현재 방식(노이즈-OR, 가중치 1.0)",
        "description": "다섯 신호(사업유형·코사인·sLLM·A3·전략열람)를 전부 가중치 1.0으로 노이즈-OR 결합합니다. 신호 하나만 강해도 빠르게 100점 근처로 포화될 수 있습니다.",
        "weights": None,
        "combine_fn": combine_noisy_or,
        "signal_floor": None,
    },
    "all_low_weight": {
        "label": "가중치 완화(추가 신호 0.5)",
        "description": "규칙은 그대로 1.0, 나머지 다섯 신호는 가중치를 0.5로 낮춰 노이즈-OR로 결합합니다. 포화 속도를 늦춥니다.",
        "weights": _ALL_SIGNALS_LOW_WEIGHTS,
        "combine_fn": combine_noisy_or,
        "signal_floor": None,
    },
    "all_cosine_floor": {
        "label": "코사인 최소값 적용(0.5 미만은 미평가 취급)",
        "description": "코사인 유사도가 0.5 미만이면 신호가 아예 없는(None) 것으로 취급합니다 — 코사인은 완전히 무관한 공고에도 항상 어떤 값이든 나오는 경향이 있어, 약한 유사도로 점수를 만들어내는 걸 막습니다. 나머지는 현재 방식과 동일.",
        "weights": None,
        "combine_fn": combine_noisy_or,
        "signal_floor": {"cosine_weighted": 0.5},
    },
    "all_weighted_avg": {
        "label": "가중평균 결합",
        "description": "노이즈-OR 대신 활성화된 신호들의 가중평균을 씁니다. 곱셈 방식이 아니라서 여러 신호가 동시에 켜져도 빠르게 포화되지 않습니다.",
        "weights": None,
        "combine_fn": combine_weighted_average,
        "signal_floor": None,
    },
}

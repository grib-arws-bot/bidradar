"""app/services/recommendation_signals.py 검증(2026-09-21, 의사결정_로그 192번) — 각 신호가
배치로 정확히 계산되는지, None(평가 불가)과 0(관련 없음)을 혼동하지 않는지, noisy-OR
결합이 신호를 껐다 켰다 해도 안전한지 확인한다.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import (
    analysis,
    analysis_requirement,
    interest_topic,
    notice,
    notice_score,
    notice_strategy,
    source,
)
from app.services.customer_interest import InterestDraft
from app.services.recommendation_signals import (
    a3_match_signal,
    combine_noisy_or,
    combine_weighted_average,
    sllm_confidence_signal,
    strategy_viewed_signal,
    work_type_signal,
    score_with_profile,
)


def _make_notice(conn, source_id: int, *, work_type=None, biz_type=None, title="[테스트] 신호") -> int:
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title=title,
            url=f"https://example.grib-test.kr/notice/signal-{id(object())}",
            work_type=work_type, biz_type=biz_type,
        ).returning(notice.c.id)
    ).scalar_one()


def _cleanup(notice_ids: list[int]) -> None:
    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(notice_ids)))
        conn.execute(delete(notice_strategy).where(notice_strategy.c.notice_id.in_(notice_ids)))
        analysis_ids = [
            r[0] for r in conn.execute(select(analysis.c.id).where(analysis.c.notice_id.in_(notice_ids)))
        ]
        if analysis_ids:
            conn.execute(delete(analysis_requirement).where(analysis_requirement.c.analysis_id.in_(analysis_ids)))
            conn.execute(delete(analysis).where(analysis.c.id.in_(analysis_ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))


# ---- work_type_signal (순수 함수, DB 불필요) ---------------------------------------


def test_work_type_signal_matches_work_type_or_biz_type():
    candidates = [
        {"id": 1, "work_type": "고도화", "biz_type": "용역"},
        {"id": 2, "work_type": "구매", "biz_type": "물품"},
        {"id": 3, "work_type": None, "biz_type": "용역"},
    ]
    scores = work_type_signal(candidates, {"고도화": "positive", "물품": "positive"})
    assert scores[1] > 0  # work_type 매칭(선호)
    assert scores[2] > 0  # biz_type 매칭(선호)
    assert scores[3] is None  # 둘 다 지정 안 함(중립) — 0점이 아니라 None


def test_work_type_signal_negative_preference_returns_negative_value():
    """2026-09-21 사용자 지시 — 감리·구매처럼 "들어가면 오히려 감점해야 할" 사업유형은
    음수로 반환돼야 한다(combine_noisy_or가 이걸 억제 강도로 해석)."""
    candidates = [{"id": 1, "work_type": "감리", "biz_type": None}]
    scores = work_type_signal(candidates, {"감리": "negative"})
    assert scores[1] < 0


def test_work_type_signal_all_none_when_customer_has_no_preference():
    candidates = [{"id": 1, "work_type": "개발", "biz_type": "용역"}]
    scores = work_type_signal(candidates, {})
    assert scores[1] is None


# ---- sllm_confidence_signal ---------------------------------------------------------


def test_sllm_confidence_signal_picks_max_across_matched_topics():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id, interest_topic_id=topic_id, l2_score=0, rule_ver=0,
                sllm_confidence=0.73, reason="sLLM 테스트",
            )
        )
    try:
        with engine.connect() as conn:
            scores = sllm_confidence_signal(conn, [notice_id], {topic_id})
        assert scores[notice_id] == pytest.approx(0.73)
    finally:
        _cleanup([notice_id])


def test_sllm_confidence_signal_none_when_not_yet_checked():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
    try:
        with engine.connect() as conn:
            scores = sllm_confidence_signal(conn, [notice_id], {topic_id})
        assert scores[notice_id] is None
    finally:
        _cleanup([notice_id])


# ---- a3_match_signal ----------------------------------------------------------------


def _insert_analysis(conn, notice_id: int, *, ver: int, judgement: str | None) -> int:
    analysis_id = conn.execute(
        insert(analysis).values(notice_id=notice_id, source_kind="notice", input_ref="x", ver=ver, status="done")
        .returning(analysis.c.id)
    ).scalar_one()
    if judgement is not None:
        conn.execute(
            insert(analysis_requirement).values(
                analysis_id=analysis_id, category="성능", req_text="테스트 요구사항", op="manual",
                cite="테스트 조문", judgement=judgement,
            )
        )
    return analysis_id


def test_a3_match_signal_true_when_latest_analysis_has_ok_judgement():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
        _insert_analysis(conn, notice_id, ver=1, judgement="ok")
    try:
        with engine.connect() as conn:
            scores = a3_match_signal(conn, [notice_id])
        assert scores[notice_id] is not None
    finally:
        _cleanup([notice_id])


def test_a3_match_signal_none_when_no_analysis():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
    try:
        with engine.connect() as conn:
            scores = a3_match_signal(conn, [notice_id])
        assert scores[notice_id] is None
    finally:
        _cleanup([notice_id])


def test_a3_match_signal_only_looks_at_latest_analysis_version():
    """재분석으로 이전 버전의 'ok' 판정이 최신 버전에서 사라지면(v2에 ok 요구사항이
    없음) 더 이상 매치로 치면 안 된다 — 최신 버전 기준으로만 판단해야 함."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
        _insert_analysis(conn, notice_id, ver=1, judgement="ok")
        _insert_analysis(conn, notice_id, ver=2, judgement="no")
    try:
        with engine.connect() as conn:
            scores = a3_match_signal(conn, [notice_id])
        assert scores[notice_id] is None
    finally:
        _cleanup([notice_id])


# ---- strategy_viewed_signal -----------------------------------------------------------


def test_strategy_viewed_signal_true_when_done():
    from app.models import customer as customer_table

    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
        customer_id = conn.execute(select(customer_table.c.id).limit(1)).scalar_one()
        conn.execute(
            insert(notice_strategy).values(customer_id=customer_id, notice_id=notice_id, status="done", strategy_md="x")
        )
    try:
        with engine.connect() as conn:
            scores = strategy_viewed_signal(conn, customer_id, [notice_id])
        assert scores[notice_id] is not None
    finally:
        _cleanup([notice_id])


def test_strategy_viewed_signal_none_when_not_viewed():
    from app.models import customer as customer_table
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        customer_id = conn.execute(select(customer_table.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
    try:
        with engine.connect() as conn:
            scores = strategy_viewed_signal(conn, customer_id, [notice_id])
        assert scores[notice_id] is None
    finally:
        _cleanup([notice_id])


# ---- combine_noisy_or -----------------------------------------------------------------


def test_combine_noisy_or_excludes_none_signals():
    # rule=0.3 하나만 활성 — cosine은 None(평가 불가)이라 결합에서 빠져야 하고, 0으로 넣었을
    # 때보다(곱해서 깎임) 결과가 더 높아야 한다.
    only_rule = combine_noisy_or({"rule": 0.3, "cosine_weighted": None}, {"rule": 1.0, "cosine_weighted": 1.0})
    with_zero = combine_noisy_or({"rule": 0.3, "cosine_weighted": 0.0}, {"rule": 1.0, "cosine_weighted": 1.0})
    assert only_rule == 30
    assert with_zero == 30  # noisy-OR에서 0인 신호는 곱해도 1을 그대로 곱하는 것과 같아 사실 동일
    # 대신 두 신호가 다 켜져 있을 때는 값이 있는 쪽이 항상 더 높거나 같아야 한다.
    both_active = combine_noisy_or({"rule": 0.3, "cosine_weighted": 0.5}, {"rule": 1.0, "cosine_weighted": 1.0})
    assert both_active > only_rule


def test_combine_noisy_or_zero_when_all_none():
    assert combine_noisy_or({"rule": None, "cosine_weighted": None}, {"rule": 1.0, "cosine_weighted": 1.0}) == 0


def test_combine_noisy_or_negative_signal_suppresses_positive_base():
    """2026-09-21 사용자 지시 — 감리·구매처럼 비선호 사업유형은 점수를 깎아야 한다.
    양의 신호로 만든 기본 점수에 음의 신호(억제 강도)를 곱해서 깎이는지 확인."""
    without_penalty = combine_noisy_or({"rule": 0.6}, {"rule": 1.0, "work_type": 1.0})
    with_penalty = combine_noisy_or({"rule": 0.6, "work_type": -0.6}, {"rule": 1.0, "work_type": 1.0})
    assert with_penalty < without_penalty
    assert with_penalty == round(without_penalty * (1 - 0.6))


def test_combine_noisy_or_negative_signal_alone_cannot_create_relevance():
    """양의 근거가 하나도 없으면 음의 신호가 있어도 여전히 0점이어야 한다 — 음의 신호는
    "있던 관련성을 깎는" 것이지 "없던 관련성을 만드는" 게 아니다."""
    assert combine_noisy_or({"work_type": -0.6}, {"work_type": 1.0}) == 0


# ---- combine_weighted_average(2026-09-21, 의사결정_로그 198번) -----------------------


def test_combine_weighted_average_does_not_saturate_like_noisy_or():
    """신호 두 개가 각각 중간 강도(0.5)일 때, 노이즈-OR은 0.75로 훌쩍 뛰지만 가중평균은
    그대로 0.5 — "전체 신호"가 노이즈-OR 때문에 다른 프로필과 너무 달라진다는 지적에
    나온 대안이 실제로 포화되지 않는지 확인."""
    scores = {"rule": 0.5, "cosine_weighted": 0.5}
    weights = {"rule": 1.0, "cosine_weighted": 1.0}
    assert combine_noisy_or(scores, weights) == 75
    assert combine_weighted_average(scores, weights) == 50


def test_combine_weighted_average_ignores_none_signals():
    scores = {"rule": 0.4, "cosine_weighted": None}
    weights = {"rule": 1.0, "cosine_weighted": 1.0}
    assert combine_weighted_average(scores, weights) == 40


def test_combine_weighted_average_zero_when_all_none():
    assert combine_weighted_average({"rule": None}, {"rule": 1.0}) == 0


def test_combine_weighted_average_respects_relative_weights():
    # cosine 가중치가 rule의 절반이면, 평균이 rule 쪽으로 더 치우쳐야 한다.
    scores = {"rule": 0.8, "cosine_weighted": 0.2}
    weights = {"rule": 1.0, "cosine_weighted": 0.5}
    # (1.0*0.8 + 0.5*0.2) / 1.5 = 0.9/1.5 = 0.6
    assert combine_weighted_average(scores, weights) == 60


# ---- score_with_profile 통합 -----------------------------------------------------------


def test_score_with_profile_matches_rule_baseline_when_no_extra_signals():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id)
        conn.execute(
            insert(notice_score).values(notice_id=notice_id, interest_topic_id=topic_id, l2_score=10, rule_ver=1, reason="x")
        )
    try:
        draft = InterestDraft(topic_ids=[topic_id])
        profile = {"customer_id": 1, "topics": [], "topic_ids": [topic_id], "topic_priorities": {}, "terms": []}
        with engine.connect() as conn:
            results = score_with_profile(conn, draft, profile, customer_id=1, enabled_signals=frozenset(), limit=50)
        match = next(m for m in results if m["id"] == notice_id)
        assert match["score"] == 30  # normal 우선순위 만점(TOPIC_PRIORITY_SCORE["normal"]=30), 강도 포화
    finally:
        _cleanup([notice_id])


def test_score_with_profile_boosts_when_work_type_signal_enabled():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id, work_type="고도화")
        conn.execute(
            insert(notice_score).values(notice_id=notice_id, interest_topic_id=topic_id, l2_score=10, rule_ver=1, reason="x")
        )
    try:
        draft = InterestDraft(topic_ids=[topic_id], work_type_prefs={"고도화": "positive"})
        profile = {"customer_id": 1, "topics": [], "topic_ids": [topic_id], "topic_priorities": {}, "terms": []}
        with engine.connect() as conn:
            baseline = score_with_profile(conn, draft, profile, customer_id=1, enabled_signals=frozenset(), limit=50)
            boosted = score_with_profile(
                conn, draft, profile, customer_id=1, enabled_signals=frozenset({"work_type"}), limit=50
            )
        baseline_score = next(m for m in baseline if m["id"] == notice_id)["score"]
        boosted_score = next(m for m in boosted if m["id"] == notice_id)["score"]
        assert boosted_score > baseline_score
    finally:
        _cleanup([notice_id])


def test_score_with_profile_lowers_score_when_work_type_is_disliked():
    """2026-09-21 사용자 지시 — 감리·구매처럼 비선호로 지정한 사업유형은 규칙 매칭
    점수보다 낮아져야 한다(끝까지 통합 테스트로 확인)."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id, work_type="감리")
        conn.execute(
            insert(notice_score).values(notice_id=notice_id, interest_topic_id=topic_id, l2_score=10, rule_ver=1, reason="x")
        )
    try:
        draft = InterestDraft(topic_ids=[topic_id], work_type_prefs={"감리": "negative"})
        profile = {"customer_id": 1, "topics": [], "topic_ids": [topic_id], "topic_priorities": {}, "terms": []}
        with engine.connect() as conn:
            baseline = score_with_profile(conn, draft, profile, customer_id=1, enabled_signals=frozenset(), limit=50)
            penalized = score_with_profile(
                conn, draft, profile, customer_id=1, enabled_signals=frozenset({"work_type"}), limit=50
            )
        baseline_score = next(m for m in baseline if m["id"] == notice_id)["score"]
        penalized_score = next(m for m in penalized if m["id"] == notice_id)["score"]
        assert penalized_score < baseline_score
    finally:
        _cleanup([notice_id])


def test_score_with_profile_includes_signal_breakdown():
    """2026-09-21 — 화면에서 신호별로 왜 이 점수인지 확인할 수 있어야 한다는 요청. 활성화
    안 한 신호는 breakdown에 아예 안 들어가야 하고(계산도 안 했으므로), 활성화했는데 값이
    없는 신호는 None으로 남아야 한다(0점과 구분)."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id, work_type="고도화")
        conn.execute(
            insert(notice_score).values(notice_id=notice_id, interest_topic_id=topic_id, l2_score=10, rule_ver=1, reason="x")
        )
    try:
        draft = InterestDraft(topic_ids=[topic_id], work_type_prefs={"고도화": "positive"})
        profile = {"customer_id": 1, "topics": [], "topic_ids": [topic_id], "topic_priorities": {}, "terms": []}
        with engine.connect() as conn:
            rule_only = score_with_profile(conn, draft, profile, customer_id=1, enabled_signals=frozenset(), limit=50)
            with_worktype = score_with_profile(
                conn, draft, profile, customer_id=1, enabled_signals=frozenset({"work_type", "a3_match"}), limit=50
            )
        rule_match = next(m for m in rule_only if m["id"] == notice_id)
        assert set(rule_match["signals"].keys()) == {"rule"}  # 끈 신호는 아예 안 들어있음

        boosted_match = next(m for m in with_worktype if m["id"] == notice_id)
        assert boosted_match["signals"]["work_type"] == pytest.approx(0.6)  # 실제 값이 그대로 노출됨
        assert boosted_match["signals"]["a3_match"] is None  # A2/A3 분석이 없으니 None(0점 아님)
    finally:
        _cleanup([notice_id])


# ---- score_with_profile의 weights/combine_fn/signal_floor 오버라이드(198번) ------------


def test_score_with_profile_signal_floor_treats_weak_value_as_none():
    """2026-09-21 — 코사인처럼 항상 어떤 값이든 나오는 신호가 약한 값으로도 점수를
    만들어내지 못하게, signal_floor 미만이면 None 취급되는지 확인."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id, work_type="고도화")
    try:
        draft = InterestDraft(topic_ids=[topic_id], work_type_prefs={"고도화": "positive"})
        profile = {"customer_id": 1, "topics": [], "topic_ids": [topic_id], "topic_priorities": {}, "terms": []}
        with engine.connect() as conn:
            # 공유 개발 DB에 이미 점수 있는 실제 공고가 많을 수 있어(다른 테스트 파일의
            # 선례와 같은 이유) 이 공고(점수 0)가 반드시 포함되도록 limit을 크게 준다.
            floored = score_with_profile(
                conn, draft, profile, customer_id=1, enabled_signals=frozenset({"work_type"}), limit=50_000,
                signal_floor={"work_type": 0.7},  # WORK_TYPE_MATCH_STRENGTH(0.6) < 0.7 → None 처리돼야 함
            )
        match = next(m for m in floored if m["id"] == notice_id)
        assert match["signals"]["work_type"] is None
        assert match["score"] == 0  # 규칙 매칭도 안 걸려 있으니(l2_score 없음) 0점이어야 함
    finally:
        _cleanup([notice_id])


def test_score_with_profile_accepts_custom_combine_fn_and_weights():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
        notice_id = _make_notice(conn, source_id, work_type="고도화")
        conn.execute(
            insert(notice_score).values(notice_id=notice_id, interest_topic_id=topic_id, l2_score=10, rule_ver=1, reason="x")
        )
    try:
        draft = InterestDraft(topic_ids=[topic_id], work_type_prefs={"고도화": "positive"})
        profile = {"customer_id": 1, "topics": [], "topic_ids": [topic_id], "topic_priorities": {}, "terms": []}
        with engine.connect() as conn:
            via_noisy_or = score_with_profile(
                conn, draft, profile, customer_id=1, enabled_signals=frozenset({"work_type"}), limit=50,
            )
            via_avg = score_with_profile(
                conn, draft, profile, customer_id=1, enabled_signals=frozenset({"work_type"}), limit=50,
                combine_fn=combine_weighted_average,
            )
        noisy_or_score = next(m for m in via_noisy_or if m["id"] == notice_id)["score"]
        avg_score = next(m for m in via_avg if m["id"] == notice_id)["score"]
        assert noisy_or_score != avg_score  # 결합 방식을 실제로 갈아끼울 수 있어야 함
    finally:
        _cleanup([notice_id])

"""app/services/sllm_topic_match.py 검증 — 사내 sLLM(B, classify-topic) 배치 처리.

pending_analysis.py/test_embeddings.py와 동일한 패턴: 임시 소스 하나로 범위를 좁혀
공유 dev DB의 실제 데이터를 안 건드리게 하고, 실제 커밋된 DB 상태를 다시 조회해 확인한다.
sLLM 호출 자체는 항상 mock — 실제 모델을 부르지 않는다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import interest_topic, keyword_rule, notice, notice_score, source
from app.services.sllm_client import SllmError, SllmNotConfiguredError
from app.services.sllm_topic_match import run_pending_sllm_topic_match


def _make_temp_source(conn) -> int:
    return conn.execute(
        insert(source)
        .values(
            name="테스트 소스(sLLM 시맨틱 매칭)", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://example.grib-test.kr/api", stage="입찰공고", adapter_type="openapi",
            frequency_minutes=1440, is_system=False, skip_l1=True, active=True, legal_tier="A",
        )
        .returning(source.c.id)
    ).scalar_one()


def _make_notice(conn, source_id: int, title: str) -> int:
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title=title,
            url=f"https://www.iris.go.kr/test/{title}",
        ).returning(notice.c.id)
    ).scalar_one()


def _make_topic(conn, name: str) -> int:
    return conn.execute(
        insert(interest_topic).values(name=name, sort_order=9999).returning(interest_topic.c.id)
    ).scalar_one()


def _cleanup(source_id: int, notice_ids: list[int], topic_id: int) -> None:
    with engine.begin() as conn:
        if notice_ids:
            conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(notice_ids)))
            conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))
        conn.execute(delete(keyword_rule).where(keyword_rule.c.interest_topic_id == topic_id))
        conn.execute(delete(interest_topic).where(interest_topic.c.id == topic_id))
        conn.execute(delete(source).where(source.c.id == source_id))


def test_run_pending_sllm_topic_match_adds_new_match_and_marks_checked():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        topic_id = _make_topic(conn, "[테스트] 로봇/자동화")
        notice_id = _make_notice(conn, source_id, "자동화 설비 구축 사업")

    sllm_result = {"output": {"matches": [{"topic_id": topic_id, "confidence": 0.98, "reason": "자동화 설비는 로봇 주제와 근접"}]}}
    try:
        with mock.patch("app.services.sllm_topic_match.classify_topic", return_value=sllm_result) as mock_classify:
            result = run_pending_sllm_topic_match(source_id, batch_limit=200)

        assert result == {"candidates": 1, "checked": 1, "matched": 1}
        mock_classify.assert_called_once()

        with engine.connect() as conn:
            row = conn.execute(
                select(notice_score.c.l2_score, notice_score.c.sllm_confidence, notice_score.c.rule_ver, notice_score.c.reason)
                .where(notice_score.c.notice_id == notice_id, notice_score.c.interest_topic_id == topic_id)
            ).mappings().one()
            checked_at = conn.execute(select(notice.c.sllm_topic_checked_at).where(notice.c.id == notice_id)).scalar_one()

        assert row["l2_score"] == 0
        assert float(row["sllm_confidence"]) == pytest.approx(0.98)
        assert row["rule_ver"] == 0
        assert "확인 필요" in row["reason"]
        assert checked_at is not None
    finally:
        _cleanup(source_id, [notice_id], topic_id)


def test_run_pending_sllm_topic_match_does_not_duplicate_existing_rule_match():
    """규칙이 이미 잡은 (notice_id, topic_id) 조합은 sLLM이 같은 주제를 또 반환해도
    건드리지 않는다 — 순수 추가 원칙(keyword_registry.rescan_notice_scores와 동일)."""
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        topic_id = _make_topic(conn, "[테스트] 기존 규칙 매칭")
        notice_id = _make_notice(conn, source_id, "로봇 자동화 설비 공고")
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id, interest_topic_id=topic_id, l2_score=3,
                reason="키워드 매칭: 로봇", rule_ver=1,
            )
        )

    sllm_result = {"output": {"matches": [{"topic_id": topic_id, "confidence": 0.9, "reason": "..."}]}}
    try:
        with mock.patch("app.services.sllm_topic_match.classify_topic", return_value=sllm_result):
            result = run_pending_sllm_topic_match(source_id, batch_limit=200)

        assert result["matched"] == 0  # 이미 규칙이 잡아서 신규 추가 없음
        with engine.connect() as conn:
            rows = conn.execute(
                select(notice_score.c.l2_score, notice_score.c.rule_ver)
                .where(notice_score.c.notice_id == notice_id, notice_score.c.interest_topic_id == topic_id)
            ).all()
        assert len(rows) == 1  # 중복 안 생김
        assert rows[0].l2_score == 3  # 기존 규칙 매칭 행 그대로 — 덮어쓰지 않음
    finally:
        _cleanup(source_id, [notice_id], topic_id)


def test_run_pending_sllm_topic_match_ignores_unknown_topic_id():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        topic_id = _make_topic(conn, "[테스트] 알수없는주제방어")
        notice_id = _make_notice(conn, source_id, "무관한 공고")

    sllm_result = {"output": {"matches": [{"topic_id": 999999999, "confidence": 0.5, "reason": "..."}]}}
    try:
        with mock.patch("app.services.sllm_topic_match.classify_topic", return_value=sllm_result):
            result = run_pending_sllm_topic_match(source_id, batch_limit=200)

        assert result["matched"] == 0
        with engine.connect() as conn:
            rows = conn.execute(select(notice_score).where(notice_score.c.notice_id == notice_id)).all()
        assert rows == []
    finally:
        _cleanup(source_id, [notice_id], topic_id)


def test_run_pending_sllm_topic_match_stops_batch_on_sllm_failure_without_marking_checked():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        topic_id = _make_topic(conn, "[테스트] sLLM 실패 격리")
        notice_id = _make_notice(conn, source_id, "sLLM 실패 시나리오 공고")

    try:
        with mock.patch(
            "app.services.sllm_topic_match.classify_topic",
            side_effect=SllmNotConfiguredError("설정 안 됨"),
        ):
            result = run_pending_sllm_topic_match(source_id, batch_limit=200)

        assert result["checked"] == 0
        assert result["matched"] == 0
        with engine.connect() as conn:
            checked_at = conn.execute(select(notice.c.sllm_topic_checked_at).where(notice.c.id == notice_id)).scalar_one()
        assert checked_at is None  # 다음 회차에 재시도되도록 안 찍혀 있어야 함
    finally:
        _cleanup(source_id, [notice_id], topic_id)


def test_run_pending_sllm_topic_match_no_candidates_returns_zero_counts():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
    try:
        result = run_pending_sllm_topic_match(source_id, batch_limit=200)
        assert result == {"candidates": 0, "checked": 0, "matched": 0}
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source).where(source.c.id == source_id))

"""app/services/notice_topic_scoring.py + app/collector/scorer.py의 score_topics_weighted
검증(2026-09-10 사용자 지시 — "첨부분석에서 LLM 없이 키워드로 관심주제를 지정, 제목 키워드는
가중치를 높여서, 최대 3개까지만"). 순수 채점 로직은 score_topics_weighted 단위 테스트로,
DB 반영(상위 3개 제한·수동 주제 보존)은 rescan_notice_topics_from_documents 통합 테스트로
나눠서 검증한다."""

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

from app.collector.scorer import TITLE_OCCURRENCE_WEIGHT, score_topics_weighted
from app.db import engine
from app.models import analysis, analysis_doc, interest_topic, keyword_rule, notice, notice_score, source
from app.services.notice_topic_scoring import (
    DOCUMENT_RULE_VER,
    MAX_TOPICS_PER_NOTICE,
    rescan_notice_topics_from_documents,
)
from app.services.notice_topics import MANUAL_RULE_VER


def test_score_topics_weighted_counts_occurrences_not_just_presence():
    rules = [(1, "스마트팩토리", 4)]
    scores = score_topics_weighted(rules=rules, title="", document_text="스마트팩토리 스마트팩토리 스마트팩토리")
    assert scores[1]["score"] == 4 * 3  # weight × 3회


def test_score_topics_weighted_weighs_title_occurrence_higher_than_document():
    rules = [(1, "로봇", 4)]
    title_only = score_topics_weighted(rules=rules, title="로봇 활용 공고", document_text="")
    doc_only = score_topics_weighted(rules=rules, title="", document_text="로봇")
    assert title_only[1]["score"] == 4 * TITLE_OCCURRENCE_WEIGHT
    assert doc_only[1]["score"] == 4 * 1
    assert title_only[1]["score"] > doc_only[1]["score"]


def test_score_topics_weighted_combines_title_and_document_counts():
    rules = [(1, "로봇", 2)]
    scores = score_topics_weighted(rules=rules, title="로봇 개발 공고", document_text="로봇 로봇")
    assert scores[1]["score"] == 2 * (1 * TITLE_OCCURRENCE_WEIGHT + 2)


def test_score_topics_weighted_no_match_excludes_topic():
    rules = [(1, "로봇", 4)]
    scores = score_topics_weighted(rules=rules, title="무관한 공고", document_text="전혀 관련 없는 내용")
    assert scores == {}


@pytest.fixture
def rescan_topics():
    """점수가 서로 다른 4개 임시 주제 — 상위 3개만 남는지 확인하려면 최소 4개 필요."""
    with engine.begin() as conn:
        topic_ids = []
        for i, (term, weight) in enumerate([("가나다라마", 4), ("바사아자차", 3), ("카타파하가", 2), ("나다라마바", 1)]):
            topic_id = conn.execute(
                insert(interest_topic).values(name=f"[테스트] 재채점상한{i}", sort_order=9990 + i).returning(interest_topic.c.id)
            ).scalar_one()
            conn.execute(insert(keyword_rule).values(interest_topic_id=topic_id, term=term, weight_class="core", weight=weight))
            topic_ids.append(topic_id)
    yield topic_ids
    with engine.begin() as conn:
        for topic_id in topic_ids:
            conn.execute(delete(keyword_rule).where(keyword_rule.c.interest_topic_id == topic_id))
            conn.execute(delete(interest_topic).where(interest_topic.c.id == topic_id))


@pytest.fixture
def rescan_notice_with_analysis():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 재채점 대상 공고",
                url="https://example.grib-test.kr/notice/topic-rescan-test",
            ).returning(notice.c.id)
        ).scalar_one()
        analysis_id = conn.execute(
            insert(analysis).values(notice_id=notice_id, source_kind="notice", input_ref="test", status="done", ver=1)
            .returning(analysis.c.id)
        ).scalar_one()
    yield notice_id, analysis_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.id == analysis_id))  # cascade로 analysis_doc도 지움
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_rescan_keeps_only_top_n_topics(rescan_topics, rescan_notice_with_analysis):
    notice_id, analysis_id = rescan_notice_with_analysis
    text = "가나다라마 바사아자차 카타파하가 나다라마바"  # 4개 주제 전부 1회씩 매칭
    with engine.begin() as conn:
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="test.pdf", kind="pdf", bytes=10, sha256="x",
                extract_ok=True, text=text,
            )
        )
        added = rescan_notice_topics_from_documents(conn, notice_id, analysis_id)
        rows = conn.execute(
            select(notice_score.c.interest_topic_id).where(notice_score.c.notice_id == notice_id)
        ).scalars().all()
    assert added == MAX_TOPICS_PER_NOTICE == 3
    # weight가 가장 낮은(1) 주제(nada라마바)는 상위 3개에서 밀려나야 함
    assert set(rows) == set(rescan_topics[:3])
    assert rescan_topics[3] not in rows


def test_rescan_preserves_manually_added_topic(rescan_topics, rescan_notice_with_analysis):
    notice_id, analysis_id = rescan_notice_with_analysis
    with engine.begin() as conn:
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id, interest_topic_id=rescan_topics[3], l2_score=99,
                reason="관리자 수동 추가", rule_ver=MANUAL_RULE_VER,
            )
        )
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="test.pdf", kind="pdf", bytes=10, sha256="x",
                extract_ok=True, text="가나다라마",
            )
        )
        rescan_notice_topics_from_documents(conn, notice_id, analysis_id)
        rows = conn.execute(
            select(notice_score.c.interest_topic_id, notice_score.c.rule_ver).where(notice_score.c.notice_id == notice_id)
        ).all()
    by_topic = {r.interest_topic_id: r.rule_ver for r in rows}
    assert by_topic[rescan_topics[3]] == MANUAL_RULE_VER  # 수동 주제는 그대로 남아 있음
    assert by_topic[rescan_topics[0]] == DOCUMENT_RULE_VER  # 문서 기반 재채점 결과는 새로 붙음


def test_rescan_replaces_previous_rule_based_topics_not_additive(rescan_topics, rescan_notice_with_analysis):
    # 예전 죽은 코드(_classify_from_attachments)는 기존 결과에 "추가만" 했는데, 새 구현은
    # "재채점"이라 규칙 기반(rule_ver != 0) 결과를 통째로 교체한다 — 이전 회차에 붙었던
    # 주제가 이번 회차 상위 3개에 없으면 사라져야 한다.
    notice_id, analysis_id = rescan_notice_with_analysis
    with engine.begin() as conn:
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id, interest_topic_id=rescan_topics[3], l2_score=1,
                reason="이전 회차 결과", rule_ver=1,
            )
        )
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="test.pdf", kind="pdf", bytes=10, sha256="x",
                extract_ok=True, text="가나다라마 바사아자차 카타파하가",  # 상위 3개 주제만 매칭
            )
        )
        rescan_notice_topics_from_documents(conn, notice_id, analysis_id)
        rows = conn.execute(
            select(notice_score.c.interest_topic_id).where(notice_score.c.notice_id == notice_id)
        ).scalars().all()
    assert rescan_topics[3] not in rows


def test_rescan_ignores_failed_extraction_docs():
    """extract_ok=False인 문서 텍스트는 재채점에 안 쓴다 — 실패한 추출 결과를 신뢰하면 안 됨."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 실패문서 제외 확인",
                url="https://example.grib-test.kr/notice/topic-rescan-failed-doc",
            ).returning(notice.c.id)
        ).scalar_one()
        analysis_id = conn.execute(
            insert(analysis).values(notice_id=notice_id, source_kind="notice", input_ref="test", status="done", ver=1)
            .returning(analysis.c.id)
        ).scalar_one()
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="broken.pdf", kind="pdf", bytes=10, sha256="x",
                extract_ok=False, text=None, error="추출 실패",
            )
        )
        added = rescan_notice_topics_from_documents(conn, notice_id, analysis_id)
        conn.execute(delete(analysis).where(analysis.c.id == analysis_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))
    assert added == 0

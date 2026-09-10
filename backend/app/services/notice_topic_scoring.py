"""공고별 관심주제를 첨부문서 본문 키워드 등장 횟수로 재산정한다(2026-09-10 사용자 지시).

L2(`app/collector/scorer.py`의 `score_l2`)는 수집 시점에 제목만 보고 관심주제를 붙인다 —
짧은 텍스트라 용어가 있는지(0/1)만으로 충분했다. 하지만 첨부문서 전문은 분량이 훨씬 커서
"몇 번 나오는지"가 실제 관련도를 더 잘 보여준다는 판단(LLM 없이 규칙만으로 가능한 개선,
CLAUDE.md S8 원칙 1 — 판정은 규칙, LLM은 추출만).

첨부분석(A1)이 성공적으로 끝난 공고에 한해, 제목+본문을 합쳐 다시 채점하고(제목 등장은
가중치를 높여 계산 — 사용자 지시) 점수가 가장 높은 상위 MAX_TOPICS_PER_NOTICE개만 남긴다
(사용자 지시 — "이 방식이 정확하지 않을 수 있으니 최대 3개까지만"). 관리자가 수동으로 붙인
주제(rule_ver=0, `app/services/notice_topics.py`)는 절대 건드리지 않는다 — 사람의 직접
판단을 규칙이 덮어쓰면 안 된다.
"""

from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection

from app.collector.scorer import score_topics_weighted
from app.models import analysis_doc, notice, notice_score
from app.services.notice_topics import MANUAL_RULE_VER

# rule_ver=1은 수집 시점 제목 전용 L2(app/collector/runner.py) — 2는 첨부문서 본문까지 반영한
# 재채점임을 구분해서 "왜 이 주제가 붙었는지" 추적 가능하게 한다(notice_topics.py의
# MANUAL_RULE_VER=0과 같은 관례).
DOCUMENT_RULE_VER = 2
MAX_TOPICS_PER_NOTICE = 3


def rescan_notice_topics_from_documents(conn: Connection, notice_id: int, analysis_id: int) -> int:
    """첨부분석(A1)이 성공적으로 끝난 직후 같은 트랜잭션에서 호출한다. 새로 반영한 주제
    개수를 반환(0이면 매칭된 키워드가 전혀 없었다는 뜻)."""
    title = conn.execute(select(notice.c.title).where(notice.c.id == notice_id)).scalar_one_or_none()
    if title is None:
        return 0
    doc_texts = conn.execute(
        select(analysis_doc.c.text).where(
            analysis_doc.c.analysis_id == analysis_id, analysis_doc.c.extract_ok.is_(True)
        )
    ).scalars().all()
    document_text = "\n".join(t for t in doc_texts if t)

    scores = score_topics_weighted(conn, title=title, document_text=document_text)
    top = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)[:MAX_TOPICS_PER_NOTICE]

    # 규칙 기반 결과(rule_ver != 0)만 교체 — 사람이 수동으로 붙인 주제는 그대로 둔다.
    conn.execute(
        delete(notice_score).where(notice_score.c.notice_id == notice_id, notice_score.c.rule_ver != MANUAL_RULE_VER)
    )
    for topic_id, info in top:
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id,
                interest_topic_id=topic_id,
                l2_score=info["score"],
                reason="첨부문서 키워드 매칭: " + ", ".join(info["matched_terms"]),
                rule_ver=DOCUMENT_RULE_VER,
            )
        )
    return len(top)

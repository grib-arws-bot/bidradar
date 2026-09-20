"""관심주제 시맨틱 필터(사내 sLLM B, classify-topic) 배치 처리(2026-09-20, 의사결정_로그
175/177번).

키워드 규칙(L2, app/collector/scorer.py)은 순수 부분일치라 "로봇"은 잡아도 "자동화 설비"
같은 표현 변형은 놓친다 — sLLM으로 제목을 한 번 더 확인해 규칙이 놓친 관련 공고를 보조
신호로 잡는다. **규칙을 대체하지 않는다**: 이미 규칙이 잡은 (notice_id, topic_id) 조합은
절대 건드리지 않고, 규칙이 못 잡은 조합만 sLLM이 관련 있다고 하면 새로 추가한다
(keyword_registry.rescan_notice_scores와 동일한 "순수 추가" 원칙).

sLLM confidence는 자동 판정에 쓰지 않는다 — notice_score.reason에 "확인 필요"를 명시해
사람이 검토하는 후보로만 남긴다(sLLM팀과 합의된 원칙, sLLM팀 자체 경험상 confidence 단독
임계값은 신뢰할 수 없었다고 함).

10분마다 도는 run_pending_backlog(app/scheduler.py)에서 title 임베딩과 나란히 호출된다.

**2026-09-20 병렬화(의사결정_로그 186번)** — sLLM팀이 classify-topic 등 3개 엔드포인트를
전용 GPU로 옮기면서 최대 4건까지 실제 동시 처리가 가능해졌고(요청당 지연도 7~8초→약
1.7초로 개선), 이전엔 "서버가 순차 단일 인스턴스라 장애=서버 전체 다운"으로 보고 한 건만
실패해도 배치 전체를 중단했는데, 이제는 그 전제가 약해졌다 — 공고마다 독립적으로
처리하고 개별 실패는 그 건만 다음 회차로 미룬다(배치 전체를 막지 않음).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import interest_topic, keyword_rule, notice, notice_score
from app.services.sllm_client import SllmError, SllmNotConfiguredError, classify_topic

logger = logging.getLogger("bidradar.sllm_topic_match")

DEFAULT_BATCH_LIMIT = 200  # embeddings.py/pending_analysis.py와 동일한 상한 원칙 — 무제한 배치 방지
_MAX_KEYWORDS_PER_TOPIC = 8  # 프롬프트가 너무 길어지지 않게 대표 키워드만(weight 높은 순)
_PARALLEL_WORKERS = 4  # sLLM팀이 확인해준 동시 처리 상한(2026-09-20) — 그 이상은 이득 없이 대기만 늘어남


def _pending_notice_ids(conn: Connection, source_id: int | None, batch_limit: int) -> list[int]:
    """sLLM으로 아직 확인 안 한 공고 id 목록 — embeddings.py의 _pending_embedding_notice_ids와
    동일 패턴. 무효화된(단계 진행으로 대체된) 공고는 매칭 대상이 아니다. source_id는
    pending_analysis.py와 동일한 목적(테스트가 임시 소스 하나로 범위를 좁혀 실제 운영
    데이터를 안 건드리게)으로 둔 선택적 필터."""
    stmt = (
        select(notice.c.id)
        .where(notice.c.sllm_topic_checked_at.is_(None), notice.c.superseded_by_notice_id.is_(None))
        .order_by(notice.c.id)
        .limit(batch_limit)
    )
    if source_id is not None:
        stmt = stmt.where(notice.c.source_id == source_id)
    return conn.execute(stmt).scalars().all()


def _active_topics_context(conn: Connection) -> list[dict]:
    """classify_topic()에 넘길 주제 목록 — 이름 + 대표 키워드. keyword_rule 전체를 다 넘기면
    프롬프트가 너무 길어지니 weight 높은 것 위주로 추린다."""
    topics = conn.execute(
        select(interest_topic.c.id, interest_topic.c.name).where(interest_topic.c.active.is_(True))
    ).all()
    result = []
    for topic_id, name in topics:
        keywords = conn.execute(
            select(keyword_rule.c.term)
            .where(
                keyword_rule.c.interest_topic_id == topic_id,
                keyword_rule.c.active.is_(True),
                keyword_rule.c.weight > 0,
            )
            .order_by(keyword_rule.c.weight.desc())
            .limit(_MAX_KEYWORDS_PER_TOPIC)
        ).scalars().all()
        result.append({"topic_id": topic_id, "name": name, "keywords": list(keywords)})
    return result


def _match_one_notice(notice_id: int, topics: list[dict]) -> int:
    """공고 1건을 sLLM으로 확인하고 규칙이 못 잡은 신규 매칭만 추가한다. 새로 추가된 건수를
    반환한다. sLLM 호출 자체의 예외(SllmNotConfiguredError/SllmError)는 여기서 삼키지 않고
    그대로 올린다 — 호출부(run_pending_sllm_topic_match)가 이 건을 다음 회차로 미룬다.
    여러 공고가 동시에(스레드) 이 함수를 부를 수 있다 — 각자 자기 DB 커넥션(engine.begin())을
    쓰므로 서로 간섭하지 않는다."""
    with engine.begin() as conn:
        row = conn.execute(select(notice.c.title).where(notice.c.id == notice_id)).first()
        if row is None:
            return 0
        title = row.title

        result = classify_topic(title, topics, trace_id=f"topic_match_{notice_id}")

        existing_pairs = set(
            conn.execute(
                select(notice_score.c.interest_topic_id).where(notice_score.c.notice_id == notice_id)
            ).scalars().all()
        )
        valid_topic_ids = {t["topic_id"] for t in topics}
        added = 0
        for match in result.get("output", {}).get("matches", []):
            topic_id = match.get("topic_id")
            if topic_id not in valid_topic_ids:
                logger.warning("sLLM이 존재하지 않는 topic_id를 반환함: %s (notice_id=%s)", topic_id, notice_id)
                continue
            if topic_id in existing_pairs:
                continue  # 규칙이 이미 잡은 조합 — 순수 추가 원칙, 덮어쓰지 않음
            reason = match.get("reason", "")
            conn.execute(
                notice_score.insert().values(
                    notice_id=notice_id,
                    interest_topic_id=topic_id,
                    l2_score=0,  # 규칙 매칭이 아님을 나타내는 값
                    sllm_confidence=match.get("confidence"),
                    reason=f"sLLM 시맨틱 매칭(확인 필요): {reason}" if reason else "sLLM 시맨틱 매칭(확인 필요)",
                    rule_ver=0,  # 규칙 사전 버전 없음(sLLM 매칭)을 나타내는 값
                )
            )
            existing_pairs.add(topic_id)
            added += 1

        conn.execute(notice.update().where(notice.c.id == notice_id).values(sllm_topic_checked_at=func.now()))
        return added


def run_pending_sllm_topic_match(source_id: int | None = None, *, batch_limit: int = DEFAULT_BATCH_LIMIT) -> dict:
    """대기 중인 공고를 최대 _PARALLEL_WORKERS건까지 동시에 처리한다(2026-09-20, sLLM
    서버가 전용 GPU로 옮겨가며 실제 동시 처리를 지원하게 됨 — 의사결정_로그 186번). 공고마다
    독립적으로 처리되므로 한 건이 실패해도(SllmNotConfiguredError/SllmError) 그 건만
    checked_at을 안 찍어 다음 회차로 미루고, 나머지는 계속 진행한다. source_id는 테스트가
    임시 소스로 범위를 좁힐 때만 쓰는 선택적 필터."""
    with engine.connect() as conn:
        candidates = _pending_notice_ids(conn, source_id, batch_limit)
        topics = _active_topics_context(conn)

    if not candidates:
        return {"candidates": 0, "checked": 0, "matched": 0}
    if not topics:
        logger.info("활성 관심주제가 없어 sLLM 시맨틱 매칭을 건너뜀")
        return {"candidates": len(candidates), "checked": 0, "matched": 0}

    checked = 0
    matched = 0
    logged_failure = False
    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {executor.submit(_match_one_notice, notice_id, topics): notice_id for notice_id in candidates}
        for future in as_completed(futures):
            try:
                matched += future.result()
                checked += 1
            except (SllmNotConfiguredError, SllmError) as exc:
                if not logged_failure:
                    logger.info("sLLM 시맨틱 매칭 중 일부 실패(%s) — 실패한 건만 다음 회차로 미룸", exc)
                    logged_failure = True
    return {"candidates": len(candidates), "checked": checked, "matched": matched}

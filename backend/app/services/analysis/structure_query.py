"""A2(structure.py) 곁가지 — LLM 호출과 무관한 조회·후처리 함수. structure.py가 500줄
상한을 넘어(2026-09-23 자격요건 구조화 추가로 더 커짐) 여기로 분리했다(CLAUDE.md 500줄
상한 규칙).
"""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.collector.scorer import L2_PROMOTE_THRESHOLD, score_l2
from app.models import analysis, analysis_requirement, notice_score


def rescan_interest_topics(conn: Connection, notice_id: int, summary: dict) -> int:
    """AI분석(A2) 완료 후 관심주제를 내용 기반으로 재매칭한다(2026-09-05, 사용자 지시).

    수집 시점의 키워드 매칭(app/collector/scorer.py)은 공고 **제목**만 본다 — 로봇 관련
    공고가 실제로는 AI·센서 기술도 다루는데 제목에 "로봇"만 있으면 AI/데이터·IoT/센서 같은
    관련 주제를 놓친다(사용자 발견). 같은 규칙(키워드 사전) 엔진을 그대로 재사용하되, A2가
    뽑은 요약(제목보다 훨씬 풍부한 내용)을 입력으로 준다 — 새 LLM 호출 없이 순수 규칙
    기반이라 비용 없음, S8 원칙과도 무관(판정이 아니라 키워드 매칭).

    이미 매칭된 주제는 건드리지 않고, 새로 발견된 주제만 추가한다(중복 방지 겸 기존
    수집 시점 판정을 덮어쓰지 않기 위함). 반환값은 새로 추가된 주제 수."""
    parts = [summary.get("purpose") or "", summary.get("sub_business") or ""]
    for item in summary.get("content_items") or []:
        parts.append(item.get("title") or "")
        parts.append(item.get("summary") or "")
    parts.append(summary.get("other_notes") or "")
    content = " ".join(p for p in parts if p)
    if not content:
        return 0

    existing_topic_ids = {
        row[0]
        for row in conn.execute(select(notice_score.c.interest_topic_id).where(notice_score.c.notice_id == notice_id))
    }
    added = 0
    for topic_id, info in score_l2(conn, content).items():
        if topic_id in existing_topic_ids or info["score"] < L2_PROMOTE_THRESHOLD:
            continue
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id,
                interest_topic_id=topic_id,
                l2_score=info["score"],
                reason=f"AI분석 내용 기반 매칭: {', '.join(info['matched_terms'])}",
                rule_ver=1,
            )
        )
        added += 1
    return added


def get_requirements(conn: Connection, notice_id: int) -> dict | None:
    """공고 상세 화면 조회용 — 가장 최근 분석의 요구사양 목록. judgement/matched_product_id는
    A2 단계에선 의미 없는 값(항상 unknown/NULL)이라 화면에 혼동을 주지 않도록 응답에서 뺀다
    (A3가 실제 판정을 붙이기 전까지).

    2026-09-13 발견 — 첨부분석(A1)만 다시 실행하면(재추출) 새 ver가 쌓이는데, 그 새 ver는
    아직 AI분석(A2)을 안 거쳐 summary가 없다. 여기서 무조건 "가장 최근 ver"만 보면, 이전
    ver에서 이미 완료된 A2 결과(사업비 등)가 화면에서 통째로 사라져 "AI분석 미공개"로
    잘못 보였다(실사례: notice_id=5476, ver=1 A2 완료 뒤 ver=2가 A1만 재실행). 목록 카드
    (notice_query.py의 _latest_analysis_summary_subquery)는 원래부터 "summary가 있는
    ver 중 최신"만 봐서 이 문제가 없었다 — 상세 화면도 같은 방식으로 맞춘다. 단 step/status는
    여전히 "진짜 최신 ver" 기준으로 둬서 재분석 버튼 라벨·재추출 재사용 판단(canReuse)이
    틀어지지 않게 하고, summary만 이전 ver에서 가져왔다면 summary_outdated로 알린다."""
    row = conn.execute(
        select(analysis.c.id, analysis.c.status, analysis.c.step, analysis.c.summary)
        .where(analysis.c.notice_id == notice_id)
        .order_by(analysis.c.ver.desc())
    ).first()
    if row is None:
        return None

    summary = row.summary
    summary_analysis_id = row.id
    summary_outdated = False
    if summary is None:
        fallback = conn.execute(
            select(analysis.c.id, analysis.c.summary)
            .where(analysis.c.notice_id == notice_id, analysis.c.summary.is_not(None))
            .order_by(analysis.c.ver.desc())
            .limit(1)
        ).first()
        if fallback is not None:
            summary = fallback.summary
            summary_analysis_id = fallback.id
            summary_outdated = True

    reqs = conn.execute(
        select(
            analysis_requirement.c.category,
            analysis_requirement.c.req_text,
            analysis_requirement.c.req_value,
            analysis_requirement.c.req_unit,
            analysis_requirement.c.op,
            analysis_requirement.c.cite,
            analysis_requirement.c.task_ref,
        )
        .where(analysis_requirement.c.analysis_id == summary_analysis_id)
        .order_by(analysis_requirement.c.id)
    ).mappings().all()

    return {
        "analysis_id": row.id,
        "status": row.status,
        "step": row.step,
        "summary": summary,
        "summary_outdated": summary_outdated,
        "requirements": [dict(r) for r in reqs],
    }

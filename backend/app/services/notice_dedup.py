"""동일 사업이 발주계획→사전규격→입찰공고로 단계 진행되며 여러 notice 행으로 중복 수집되는
문제 정리(2026-09-06 사용자 지시, "가장 최근에 공고된 것을 기준으로 하고 이전 것들은
무효화"). "동일 발주기관+동일 사업명"으로 묶어 그룹 안에서 가장 최근 공고 1건만 유효로
남기고 나머지는 notice.superseded_by_notice_id에 그 최신 건의 id를 채운다. 하드 삭제는 안
한다 — 감사·추적 가능성 유지(다른 레지스트리들의 "비활성화만" 원칙과 같은 이유).

keyword_registry.rescan_notice_scores()와 같은 이유로 **항상 전체를 재계산**하는 멱등 함수다.
자동 수집에 끼워 넣지 않고 관리자가 버튼으로 수동 실행한다(2026-09-06 결정) — 새로 생긴
그룹이 잘못 묶이는 경우를 사람이 검수할 여지를 남기기 위함(GIS 키워드 사고처럼 자동화가
조용히 틀릴 수 있다는 이번 세션의 반복된 교훈).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import notice

# 발주계획→사전규격→입찰공고 한 사업의 단계 간 간격은 실측(2026-09-06 스크린샷)상 수 주~
# 두 달 안팎이었다 — 같은 발주기관·같은 사업명이라도 이보다 훨씬 크게 벌어져 있으면 "매년
# 반복되는 유지보수 용역"처럼 별개 계약일 가능성이 커 묶지 않는다(안전판, 넉넉하게 잡음).
_MAX_GROUP_SPAN_DAYS = 400


class _NoticeRow(NamedTuple):
    id: int
    org_id: int
    title: str
    open_dt: datetime | None
    created_at: datetime


def _normalize_title(title: str) -> str:
    """공백 정규화만 한다 — 실측(2026-09-06)으로 같은 사업명인데 중간에 이중 공백만 다른
    사례("2026년  스마트 공원...")를 확인. 그 이상의 유사도 매칭(오타 교정 등)은 오탐
    위험이 커 이번 범위에서는 넣지 않는다."""
    return " ".join(title.split())


def _anchor_dt(row: _NoticeRow) -> datetime:
    """게시일(open_dt)을 우선 쓰고 없으면 수집 시각(created_at) — 정렬·최신 판정 기준."""
    return row.open_dt or row.created_at


def _cluster_by_gap(members: list[_NoticeRow], max_gap_days: int) -> list[list[_NoticeRow]]:
    """같은 (발주기관, 정규화 제목) 그룹이라도 기준일이 max_gap_days 넘게 벌어지면 별개
    클러스터로 쪼갠다."""
    ordered = sorted(members, key=_anchor_dt)
    clusters: list[list[_NoticeRow]] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        if (_anchor_dt(cur) - _anchor_dt(prev)).days > max_gap_days:
            clusters.append([cur])
        else:
            clusters[-1].append(cur)
    return clusters


def find_and_mark_superseded(conn: Connection) -> dict:
    """org_id가 있는 전체 notice를 대상으로 재계산한다 — 항상 전체를 다시 훑는 멱등 함수라
    이전 실행 이후 새로 수집된 공고·삭제된 공고(retention 정리 등)가 있어도 매번 정확한
    최신 상태로 맞춰진다."""
    rows = [
        _NoticeRow(r.id, r.org_id, r.title, r.open_dt, r.created_at)
        for r in conn.execute(
            select(notice.c.id, notice.c.org_id, notice.c.title, notice.c.open_dt, notice.c.created_at).where(
                notice.c.org_id.isnot(None)
            )
        ).all()
    ]

    groups: dict[tuple[int, str], list[_NoticeRow]] = defaultdict(list)
    for row in rows:
        groups[(row.org_id, _normalize_title(row.title))].append(row)

    # notice.id -> 새 superseded_by_notice_id(유효하면 None). org_id가 있는 모든 공고를
    # 매번 다시 계산해 채워 넣는다 — 그룹이 줄어들어 더 이상 중복이 아니게 된 공고의 낡은
    # 포인터도 이 자리에서 함께 정리된다.
    new_values: dict[int, int | None] = {}
    groups_with_duplicates = 0
    for members in groups.values():
        for cluster in _cluster_by_gap(members, _MAX_GROUP_SPAN_DAYS):
            if len(cluster) < 2:
                new_values[cluster[0].id] = None
                continue
            groups_with_duplicates += 1
            latest = max(cluster, key=lambda r: (r.open_dt is not None, _anchor_dt(r), r.id))
            for member in cluster:
                new_values[member.id] = None if member.id == latest.id else latest.id

    updated = 0
    for notice_id, superseded_by in new_values.items():
        result = conn.execute(
            notice.update()
            .where(notice.c.id == notice_id, notice.c.superseded_by_notice_id.is_distinct_from(superseded_by))
            .values(superseded_by_notice_id=superseded_by)
        )
        updated += result.rowcount

    return {"groups_with_duplicates": groups_with_duplicates, "notices_updated": updated}

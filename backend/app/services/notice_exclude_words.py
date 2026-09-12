"""공고 탐색 제목 제외 키워드 관리(2026-09-13) — keyword_rule(L2 관심주제 채점)과 무관한
순수 조회 필터용 단어 목록. 그룹이 여러 개일 필요가 없다는 사용자 확인(관리 편의)에 따라
그룹 개념 자체를 테이블로 만들지 않고, 이 목록 전체가 곧 하나의 그룹이다 — 화면에서
"켜고 끄는" 단위도 이 목록 전체(app/services/notice_query.py가 exclude_words로 받는다)."""

from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.models import notice_title_exclude_word


def list_exclude_words(conn: Connection) -> list[dict]:
    stmt = select(notice_title_exclude_word.c.id, notice_title_exclude_word.c.term).order_by(
        notice_title_exclude_word.c.term
    )
    return [dict(r) for r in conn.execute(stmt).mappings().all()]


def create_exclude_word(conn: Connection, term: str) -> dict:
    term = term.strip()
    if not term:
        raise ValueError("제외 단어를 입력하세요.")
    try:
        row = conn.execute(
            insert(notice_title_exclude_word)
            .values(term=term)
            .returning(notice_title_exclude_word.c.id, notice_title_exclude_word.c.term)
        ).mappings().one()
    except IntegrityError as exc:
        raise ValueError(f"이미 등록된 단어입니다: {term}") from exc
    return dict(row)


def delete_exclude_word(conn: Connection, word_id: int) -> bool:
    result = conn.execute(delete(notice_title_exclude_word).where(notice_title_exclude_word.c.id == word_id))
    return result.rowcount > 0

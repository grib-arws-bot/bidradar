"""라우터는 얇게 — 실제 로직은 app/services/topic_registry.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services import audit
from app.services.keyword_registry import (
    create_keyword,
    delete_keyword,
    list_keywords,
    rescan_notice_scores,
    update_keyword,
)
from app.services.topic_registry import DuplicateTopicNameError, create_topic, list_topics, update_topic

router = APIRouter(prefix="/api/admin/topics", tags=["topics"])


class TopicCreate(BaseModel):
    name: str
    description: str | None = None
    sort_order: int = 0


class TopicUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None
    active: bool | None = None


@router.get("")
def get_topics_route(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_topics(conn)


@router.post("", status_code=status.HTTP_201_CREATED)
def post_topic_route(payload: TopicCreate, email: str = Depends(require_auth)) -> dict:
    if not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이름을 입력하세요.")
    try:
        with engine.begin() as conn:
            row = create_topic(conn, name=payload.name.strip(), description=payload.description, sort_order=payload.sort_order)
            audit.record(conn, actor=email, action="topic.create", target_type="interest_topic", target_id=row["id"], detail=payload.model_dump())
    except DuplicateTopicNameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return row


@router.patch("/{topic_id}")
def patch_topic_route(topic_id: int, payload: TopicUpdate, email: str = Depends(require_auth)) -> dict:
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이름을 빈 값으로 바꿀 수 없습니다.")
    try:
        with engine.begin() as conn:
            row = update_topic(
                conn,
                topic_id,
                name=payload.name.strip() if payload.name else None,
                description=payload.description,
                sort_order=payload.sort_order,
                active=payload.active,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="분류를 찾을 수 없습니다.")
            audit.record(
                conn, actor=email, action="topic.update", target_type="interest_topic", target_id=topic_id,
                detail=payload.model_dump(exclude_none=True),
            )
    except DuplicateTopicNameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return row


# ---- 관심주제 키워드(L2 규칙) — 2026-09-05 신설 -------------------------------------


class KeywordCreate(BaseModel):
    term: str
    weight_class: str = "tech"
    weight: int = 2


class KeywordUpdate(BaseModel):
    term: str | None = None
    weight_class: str | None = None
    weight: int | None = None
    active: bool | None = None


@router.get("/{topic_id}/keywords")
def get_keywords_route(topic_id: int, _email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_keywords(conn, topic_id)


@router.post("/{topic_id}/keywords", status_code=status.HTTP_201_CREATED)
def post_keyword_route(topic_id: int, payload: KeywordCreate, email: str = Depends(require_auth)) -> dict:
    if not payload.term.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="키워드를 입력하세요.")
    with engine.begin() as conn:
        try:
            row = create_keyword(
                conn, topic_id=topic_id, term=payload.term, weight_class=payload.weight_class, weight=payload.weight,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        audit.record(conn, actor=email, action="keyword.create", target_type="keyword_rule", target_id=row["id"], detail=payload.model_dump())
    return row


@router.patch("/keywords/{keyword_id}")
def patch_keyword_route(keyword_id: int, payload: KeywordUpdate, email: str = Depends(require_auth)) -> dict:
    with engine.begin() as conn:
        try:
            row = update_keyword(
                conn, keyword_id, term=payload.term, weight_class=payload.weight_class, weight=payload.weight, active=payload.active,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="키워드를 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="keyword.update", target_type="keyword_rule", target_id=keyword_id,
            detail=payload.model_dump(exclude_none=True),
        )
    return row


@router.delete("/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_keyword_route(keyword_id: int, email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        found = delete_keyword(conn, keyword_id)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="키워드를 찾을 수 없습니다.")
        audit.record(conn, actor=email, action="keyword.delete", target_type="keyword_rule", target_id=keyword_id, detail={})


@router.post("/keywords/rescan")
def post_keywords_rescan_route(email: str = Depends(require_auth)) -> dict:
    """키워드를 추가·수정한 뒤 관리자가 눌러서 실행 — 이미 수집된 공고에도 새 규칙을
    소급 적용한다(자동 실행 금지, S8 원칙 3). 기존 매칭은 절대 건드리지 않고 새로 통과하는
    조합만 추가한다."""
    with engine.begin() as conn:
        result = rescan_notice_scores(conn)
        audit.record(conn, actor=email, action="keyword.rescan", target_type="keyword_rule", target_id=None, detail=result)
    return result

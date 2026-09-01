"""라우터는 얇게 — 실제 로직은 app/services/topic_registry.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services import audit
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

"""라우터는 얇게 — 실제 로직은 app/services/notice_exclude_words.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services import audit
from app.services.notice_exclude_words import create_exclude_word, delete_exclude_word, list_exclude_words

router = APIRouter(prefix="/api/admin/notice-exclude-words", tags=["notice-exclude-words"])


class ExcludeWordCreate(BaseModel):
    term: str


@router.get("")
def get_exclude_words_route(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_exclude_words(conn)


@router.post("", status_code=status.HTTP_201_CREATED)
def post_exclude_word_route(payload: ExcludeWordCreate, email: str = Depends(require_auth)) -> dict:
    with engine.begin() as conn:
        try:
            row = create_exclude_word(conn, payload.term)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        audit.record(
            conn, actor=email, action="notice_exclude_word.create", target_type="notice_title_exclude_word",
            target_id=row["id"], detail=payload.model_dump(),
        )
    return row


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_exclude_word_route(word_id: int, email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        found = delete_exclude_word(conn, word_id)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="단어를 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="notice_exclude_word.delete", target_type="notice_title_exclude_word",
            target_id=word_id, detail={},
        )

"""라우터는 얇게 — S7 관심주제 로직은 app/services/customer_interest.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services.customer_interest import (
    InterestDraft,
    compute_matches,
    get_interest_profile,
    list_customers,
    save_interest_profile,
)
from app.services.saved_search import create_saved_search, delete_saved_search, list_saved_searches

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("")
def get_customers(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_customers(conn)


class InterestPayload(BaseModel):
    topic_ids: list[int] = []
    terms: list[str] = []
    followed_org_ids: list[int] = []
    price_min: int | None = None
    price_max: int | None = None
    regions: list[str] = []

    def to_draft(self) -> InterestDraft:
        return InterestDraft(
            topic_ids=self.topic_ids,
            terms=self.terms,
            followed_org_ids=self.followed_org_ids,
            price_min=self.price_min,
            price_max=self.price_max,
            regions=self.regions,
        )


@router.get("/{customer_id}/interests")
def get_interests(customer_id: int, _email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        profile = get_interest_profile(conn, customer_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
    return profile


@router.put("/{customer_id}/interests", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def put_interests(customer_id: int, payload: InterestPayload, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        if get_interest_profile(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        save_interest_profile(conn, customer_id, payload.to_draft())


@router.post("/{customer_id}/interests/preview")
def post_interests_preview(customer_id: int, payload: InterestPayload, _email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        if get_interest_profile(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        return compute_matches(conn, payload.to_draft())


@router.get("/{customer_id}/searches")
def get_searches(customer_id: int, _email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_saved_searches(conn, customer_id)


class SavedSearchPayload(BaseModel):
    name: str
    query_params: dict


@router.post("/{customer_id}/searches", status_code=status.HTTP_201_CREATED)
def post_search(customer_id: int, payload: SavedSearchPayload, _email: str = Depends(require_auth)) -> dict:
    with engine.begin() as conn:
        search_id = create_saved_search(conn, customer_id, payload.name, payload.query_params)
    return {"id": search_id}


@router.delete("/{customer_id}/searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_search(customer_id: int, search_id: int, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        found = delete_saved_search(conn, customer_id, search_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="저장한 검색을 찾을 수 없습니다.")

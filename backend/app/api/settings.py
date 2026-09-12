"""범용 앱 설정(2026-09-12) — 첫 항목은 보고서 자동 삭제 보관기간. 설정이 늘어나도
이 라우터의 GET/PUT 하나로 계속 대응한다(app/services/app_settings.py 참고)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services.app_settings import get_report_retention_days, set_report_retention_days

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    report_retention_days: int | None


@router.get("")
def get_settings(_email: str = Depends(require_auth)) -> SettingsResponse:
    with engine.connect() as conn:
        return SettingsResponse(report_retention_days=get_report_retention_days(conn))


class SettingsUpdateRequest(BaseModel):
    report_retention_days: int | None


@router.put("")
def put_settings(payload: SettingsUpdateRequest, _email: str = Depends(require_auth)) -> SettingsResponse:
    with engine.begin() as conn:
        try:
            set_report_retention_days(conn, payload.report_retention_days)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return SettingsResponse(report_retention_days=get_report_retention_days(conn))

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.customers import router as customers_router
from app.api.notice_exclude_words import router as notice_exclude_words_router
from app.api.notices import router as notices_router
from app.api.overview import router as overview_router
from app.api.public import router as public_router
from app.api.settings import router as settings_router
from app.api.sources import router as sources_router
from app.api.topics import router as topics_router
from app.config import settings

app = FastAPI(title="BidRadar API")
app.include_router(auth_router)
app.include_router(notices_router)
app.include_router(notice_exclude_words_router)
app.include_router(customers_router)
app.include_router(overview_router)
app.include_router(public_router)
app.include_router(settings_router)
app.include_router(sources_router)
app.include_router(topics_router)


@app.get("/api/health")
def health() -> dict[str, object]:
    # dev_autologin_enabled: 프론트 로그인 화면이 자동로그인 버튼을 보여줄지 판단하는 데 씀
    # (인증 불필요 정보). is_dev와 별개 — stg도 기본값 False라 로그인 절차를 그대로 거친다.
    return {"status": "ok", "dev_autologin_enabled": settings.enable_dev_autologin}

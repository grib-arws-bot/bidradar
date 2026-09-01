from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.customers import router as customers_router
from app.api.notices import router as notices_router
from app.api.overview import router as overview_router
from app.api.public import router as public_router

app = FastAPI(title="BidRadar API")
app.include_router(auth_router)
app.include_router(notices_router)
app.include_router(customers_router)
app.include_router(overview_router)
app.include_router(public_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

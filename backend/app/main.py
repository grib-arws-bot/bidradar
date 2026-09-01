from fastapi import FastAPI

from app.api.auth import router as auth_router

app = FastAPI(title="BidRadar API")
app.include_router(auth_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bidradar:bidradar@localhost:5432/bidradar"
    session_secret: str = "dev-only-change-me"
    admin_email: str = "report@grib.co.kr"
    admin_password_hash: str = ""
    environment: str = "development"
    # 자동로그인은 environment(=is_dev)와 별개 스위치 — 기본 False. stg(docker-compose 로컬
    # 기동)도 prod와 동일하게 로그인 절차를 거쳐야 육안 확인 때 로그인 버그를 놓치지 않는다
    # (2026-09-03). 진짜로 필요한 경우(예: 반복 재기동이 잦은 로컬 개발 루프)에만 로컬
    # .env에 ENABLE_DEV_AUTOLOGIN=true를 직접 켠다.
    enable_dev_autologin: bool = False
    # S8 A2·A5·A6 LLM 호출(구현스펙 07절) — Anthropic Console에서 발급한 API 키(개인 Claude
    # Code OAuth 로그인 아님, ARWS 결정로그 78번 근거). 미설정이면 A2 등 LLM 단계는 명시적으로
    # 거부한다(조용히 빈 결과로 진행하지 않음).
    anthropic_api_key: str = ""

    @property
    def is_dev(self) -> bool:
        return self.environment != "production"


settings = Settings()

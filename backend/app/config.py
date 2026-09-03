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

    @property
    def is_dev(self) -> bool:
        return self.environment != "production"


settings = Settings()

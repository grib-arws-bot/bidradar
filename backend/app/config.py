from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bidradar:bidradar@localhost:5432/bidradar"
    session_secret: str = "dev-only-change-me"
    admin_email: str = "report@grib.co.kr"
    admin_password_hash: str = ""


settings = Settings()

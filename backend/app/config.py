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

    # 보고서 이메일 발송(2026-09-12) — ARWS와 동일하게 하이웍스 SMTP를 쓴다(개발 단계 결정,
    # 의사결정_로그 8번 — 정식 오픈 시점에 전용 ESP 전환 재검토). n8n 없이 백엔드가 smtplib로
    # 직접 발송한다(CLAUDE.md n8n 금지). 미설정이면 발송 API가 명시적으로 거부한다.
    smtp_host: str = ""
    smtp_port: int = 465  # 하이웍스는 465(암시적 SSL)만 지원 — 587(STARTTLS) 아님
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "report@grib.co.kr"
    # 이메일 본문의 리포트 링크(/r/{token})를 완전한 URL로 만들 때 쓴다 — 백엔드는 요청 Host를
    # 신뢰하지 않고(프록시 헤더 위조 우려) 이 값으로 고정한다. prod는 실제 도메인으로 덮어씀.
    public_base_url: str = "http://localhost:13200"

    # 사내 sLLM(Qwen3-4B, 자체 호스팅) 연동(2026-09-20, 의사결정_로그 175번) — 첨부문서
    # 공통문서 분류(C)·관심주제 시맨틱 필터(B)·나라장터 A2 미리보기(A) 세 곳에 쓴다.
    # BidRadar와 같은 사내망에 있어 비용이 안 드는 대신, 호스트가 사설 IP라 url_guard의
    # SSRF 차단 대역에 걸린다 — 실제 호스트 확정 후 url_guard에 좁은 예외를 추가해야 한다
    # (app/security/url_guard.py 주석 참고). 미설정이면 명시적으로 거부한다(조용한 실패 금지).
    sllm_base_url: str = ""
    sllm_api_token: str = ""

    @property
    def is_dev(self) -> bool:
        return self.environment != "production"


settings = Settings()

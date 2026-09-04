"""공유 pytest 픽스처. 이 프로젝트 테스트는 격리된 테스트 DB가 아니라 로컬 dev DB를 그대로
쓴다(여러 파일이 `postgresql://...127.0.0.1:15432/bidradar`를 직접 가리킴) — 즉 관리자가
브라우저로 실제 로그인해 쓰고 있는 바로 그 DB다.

2026-09-05 발견 — 각 테스트 파일이 저마다 `_clean_auth_tables` 픽스처로 매 테스트 전에
auth_session을 통째로 delete했는데, 이게 테스트가 만든 세션뿐 아니라 **관리자의 실제 로그인
세션까지 같이 지워버려서** pytest를 돌릴 때마다 브라우저에서 갑자기 로그아웃되는 부작용이
있었다(단일 공유 계정이라 "테스트 세션"과 "실제 세션"을 이메일로 구분할 수도 없음). 여기서
기존 세션을 스냅샷 → 삭제(테스트에 깨끗한 상태 제공) → 테스트 종료 후 복원하는 식으로 바꿔서,
실제 세션이 사라지는 창을 "테스트 1건 실행 시간"(수십 ms) 수준으로 줄인다 — 근본적으로는
격리된 테스트 DB를 쓰는 게 맞지만 그건 더 큰 인프라 변경이라 지금은 이 완화책으로 막는다.

conftest.py는 pytest가 어떤 테스트 파일보다도 먼저 수집하므로, 여기서도 각 테스트 파일과
동일하게 DATABASE_URL 등을 app.db 임포트 전에 고정한다 — 안 그러면 의사결정_로그 35번에서
고친 "가장 먼저 수집된 파일이 app.config.settings 싱글턴을 실제 .env 값으로 굳혀버리는" 버그가
이 파일 때문에 재발한다.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

import pytest
from sqlalchemy import delete, insert

from app.db import engine
from app.models import auth_session, login_attempt


@pytest.fixture(autouse=True)
def _clean_auth_tables():
    with engine.begin() as conn:
        existing_sessions = [dict(row) for row in conn.execute(auth_session.select()).mappings()]
        existing_attempts = [dict(row) for row in conn.execute(login_attempt.select()).mappings()]
        conn.execute(delete(auth_session))
        conn.execute(delete(login_attempt))
    yield
    with engine.begin() as conn:
        conn.execute(delete(auth_session))
        conn.execute(delete(login_attempt))
        if existing_sessions:
            conn.execute(insert(auth_session), existing_sessions)
        if existing_attempts:
            conn.execute(insert(login_attempt), existing_attempts)

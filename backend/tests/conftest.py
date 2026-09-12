"""공유 pytest 픽스처.

2026-09-13 — 격리된 테스트 DB로 전환(사용자 지시, 105·118번 이후 계속 지적돼온 기술부채).
**별도 DB·별도 인프라를 새로 만드는 게 아니다** — 로컬 dev DB(`postgresql://...127.0.0.1:15432/
bidradar`)를 그대로 쓰되, 테스트 1건마다 커넥션 하나 + 진짜 트랜잭션 하나를 열어두고
`app.db.engine`의 `connect()`/`begin()`이 그 트랜잭션 위의 SAVEPOINT만 만들도록 가로챈 뒤,
테스트가 끝나면 그 트랜잭션 전체를 롤백한다 — 테스트가 무엇을 얼마나 쓰든 DB에는 흔적이
전혀 안 남는다. 별도 DB 볼륨·재수집·LLM 재호출이 필요 없어 디스크·API 비용이 전혀 늘지
않는다(사용자 우려 확인 답변) — SQLAlchemy 공식 "외부 트랜잭션에 조인" 패턴을 ORM Session이
아니라 이 프로젝트가 쓰는 Core Connection에 맞게 적용한 것.

**이게 이전엔 왜 없었는지**: 서비스 계층 전체가 `conn: Connection`을 받는 함수형 구조라 이
패턴이 잘 들어맞는다는 게 이번에 확인한 전제 — 스레드나 별도 프로세스로 DB에 동시 접근하는
테스트가 없음(확인 완료)도 전제로 깔려 있다. 그런 테스트가 새로 생기면(예: 실제
스케줄러/스레드를 띄우는 통합테스트) 이 자동격리와 충돌할 수 있어 별도 처리가 필요하다.

`auth_session`/`login_attempt` 스냅샷-복원 완화책(2026-09-05)은 이제 불필요 — 롤백이
그 역할을 이미 포함하므로 제거했다(관리자의 실제 로그인 세션도 테스트가 열어본 트랜잭션
안에서만 안 보이는 게 아니라 애초에 안 건드려짐).

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

from contextlib import contextmanager

import pytest

from app.db import engine


class _NonClosingConnectionProxy:
    """`engine.connect()`/`engine.begin()`이 매번 새 커넥션을 여는 대신 이 테스트의 유일한
    실제 커넥션(`_real`)을 재사용하게 하는 얇은 프록시. `close()`는 no-op(진짜 종료는
    `_isolate_db_per_test`의 teardown에서만) — 그래야 "각 요청/서비스 호출이 자기 커넥션을
    열고 끝에 닫는다"는 기존 코드 패턴이 그대로 동작하면서도, 물리적으로는 계속 같은 트랜잭션
    안에 머문다.

    **`commit()`/`rollback()`을 직접 가로챈다(2026-09-13, 이벤트 기반 방식 폐기 후 확정)** —
    처음엔 SQLAlchemy의 `release_savepoint`/`rollback_savepoint` 이벤트로 "SAVEPOINT가 끝나면
    자동으로 새 SAVEPOINT를 연다"를 구현했는데, 실제로 단독 스크립트로 재현해보니 그 이벤트가
    SAVEPOINT release 직후 곧바로(동기적으로) 발동하지 않고 그 다음 트랜잭션 작업 시점에야
    반영되는 걸 확인했다(타이밍이 결정적이지 않음 — 실제로 `test_send_report_*` 두 테스트가
    이 지연 때문에 "already deassociated" 오류를 냈다). 이벤트에 기대는 대신, 이 프록시가
    "지금 이 스코프가 책임지는 SAVEPOINT가 뭔지"를 `holder`(1칸짜리 mutable box, 여러 프록시가
    공유 가능)로 직접 들고 있다가, `commit()`/`rollback()` 호출 시 그 자리에서 바로 커밋하고
    새 SAVEPOINT로 교체한다 — 타이밍 문제 없이 완전히 결정론적이다. `app/services/
    interest_report.py`의 `send_report_email`처럼 `with engine.connect() as conn:` 로 얻은
    커넥션에 나중에 **직접** `conn.commit()`을 부르는 코드(라우터가 `.begin()`이 아니라
    `.connect()`를 쓰고 명시 커밋이 필요하다는 114번 설계)가 이 경로를 탄다.

    `begin()`은 진짜 BEGIN 대신 새 SAVEPOINT(`begin_nested`)를 만들어 "그 안에서 또 begin()을
    호출하는" 기존 중첩 패턴(예: analysis_pilot.py의 `with conn.begin_nested():`)이 그대로
    유효하게 한다 — 이건 이 프록시의 `holder`와 무관한, 완전히 새로운 독립 SAVEPOINT다."""

    def __init__(self, real_conn, holder: list):
        self._real = real_conn
        self._holder = holder  # holder[0] = 이 프록시가 책임지는 "현재" SAVEPOINT

    def __getattr__(self, name):
        return getattr(self._real, name)

    def begin(self):
        return self._real.begin_nested()

    def commit(self) -> None:
        self._holder[0].commit()
        self._holder[0] = self._real.begin_nested()

    def rollback(self) -> None:
        self._holder[0].rollback()
        self._holder[0] = self._real.begin_nested()

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.fixture(autouse=True)
def _isolate_db_per_test(request, monkeypatch):
    """테스트 1건 = 커넥션 1개 + 트랜잭션 1개. 끝나면 무조건 롤백 — 테스트가 INSERT/UPDATE/
    DELETE를 얼마나 하든 실제 dev DB(관리자가 실제로 쓰는 그 DB)에는 아무 흔적도 안 남는다.

    `engine.connect()`로 얻는 커넥션들은 전부 `_shared_holder`(테스트 전체가 공유하는
    "현재 SAVEPOINT" 1칸)를 참조한다 — 그중 하나가 `conn.commit()`을 직접 불러도 그건 이
    SAVEPOINT만 끝내고 새 SAVEPOINT로 교체할 뿐, `outer_trans`는 절대 건드리지 못한다.
    `engine.begin()`은 매번 호출마다 **자기 전용의 새 지역 SAVEPOINT**를 만든다 — 공유
    holder를 쓰면 중첩 호출(서비스 함수가 또 다른 서비스 함수를 부르며 각자 `with
    engine.begin()`을 쓰는 경우) 시 안쪽 블록이 먼저 커밋해버려 바깥 블록이 "이미 끝난
    트랜잭션"을 또 커밋하려다 에러가 난다(2026-09-13 실측 확인).

    `@pytest.mark.no_db_isolation`이 붙은 테스트는 이 전체를 건너뛴다 — `app/collector/
    runner.py`의 `_record_run`처럼 "호출부 트랜잭션과 무관하게 독립적으로 즉시 커밋"하는 게
    그 코드 자체의 정상 동작(실패 기록이 호출부 롤백에 휩쓸리면 안 됨)인 경우, 이 프록시가
    모든 `engine.begin()`/`connect()`을 같은 커넥션으로 묶어버려서 그 "독립성"까지 없애버린다
    (실제로 `test_run_source_records_failure_and_reraises`에서 발견). 이런 케이스는 격리를
    끄고 실제 커밋으로 검증하되, 테스트가 남긴 행은 해당 테스트가 직접 지워야 한다."""
    if request.node.get_closest_marker("no_db_isolation"):
        yield
        return

    real_conn = engine.connect()
    outer_trans = real_conn.begin()
    shared_holder = [real_conn.begin_nested()]

    def _fake_connect(*args, **kwargs):
        return _NonClosingConnectionProxy(real_conn, shared_holder)

    @contextmanager
    def _fake_begin(*args, **kwargs):
        local_holder = [real_conn.begin_nested()]
        proxy = _NonClosingConnectionProxy(real_conn, local_holder)
        try:
            yield proxy
            local_holder[0].commit()
        except BaseException:
            local_holder[0].rollback()
            raise

    monkeypatch.setattr(engine, "connect", _fake_connect)
    monkeypatch.setattr(engine, "begin", _fake_begin)

    yield

    outer_trans.rollback()
    real_conn.close()

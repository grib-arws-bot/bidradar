"""app/services/analysis_worker.py 검증 — A1/A2를 수집 스레드와 분리하는 작은 백그라운드
워커 풀(2026-09-15, 나라장터 2시간 지연이 다른 소스 수집까지 막은 사고 이후 도입).
"""

from __future__ import annotations

import time

import pytest

from app.services.analysis_worker import submit


def test_submit_runs_function_and_returns_immediately():
    calls: list[int] = []

    def _slow(value: int) -> int:
        time.sleep(0.05)
        calls.append(value)
        return value * 2

    future = submit(_slow, 21)
    # submit()은 완료를 기다리지 않고 즉시 반환해야 한다 — 호출 직후에는 아직 안 끝나 있어야 함.
    assert calls == []
    assert future.result(timeout=2) == 42
    assert calls == [21]


def test_submit_logs_but_does_not_raise_when_function_fails(caplog):
    def _boom() -> None:
        raise RuntimeError("의도된 테스트 실패")

    future = submit(_boom)
    # 예외는 future 안에 담기고, 호출부(submit)는 터지지 않는다.
    with caplog.at_level("ERROR", logger="bidradar.analysis_worker"):
        with pytest.raises(RuntimeError):
            future.result(timeout=2)
        # done_callback은 별도 스레드에서 비동기로 로깅한다 — 고정 sleep(예: 0.05초)은 CI
        # 러너가 다른 프로세스와 CPU를 다툴 때 스레드 스케줄링이 그만큼 늦어지면 그대로
        # 깨진다(2026-09-17 실측: 이 테스트만 재현 없이 간헐적으로 실패). 대신 로그가 찍힐
        # 때까지 짧게 폴링하되 상한(2초)을 둬서, 정말 안 찍히는 회귀는 여전히 잡아낸다.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if any("실패" in record.message for record in caplog.records):
                break
            time.sleep(0.01)
    assert any("실패" in record.message for record in caplog.records)

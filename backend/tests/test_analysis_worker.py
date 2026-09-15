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
        time.sleep(0.05)  # done_callback이 별도 스레드에서 로깅할 시간을 준다
    assert any("실패" in record.message for record in caplog.records)

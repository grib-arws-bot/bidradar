"""app/logging_config.py — 콘솔+영속 파일 로그 설정 검증(2026-09-14)."""

from __future__ import annotations

import logging

from app.logging_config import configure_logging


def test_configure_logging_falls_back_when_log_dir_unwritable(monkeypatch, tmp_path):
    # 컨테이너 볼륨이 없는 로컬 실행/테스트 환경 — 파일 핸들러 초기화가 실패해도 예외 없이
    # 콘솔 로깅은 계속 동작해야 한다(app/logging_config.py의 "조용히 넘어간다" 원칙).
    # 상위 경로 자체를 파일로 만들어 mkdir(parents=True)가 확실히 실패하도록 강제한다.
    blocker = tmp_path / "impossible"
    blocker.write_text("i am a file, not a directory")
    monkeypatch.setattr("app.logging_config.LOG_DIR", blocker / "too" / "deep")
    monkeypatch.setattr("app.logging_config.LOG_FILE", blocker / "too" / "deep" / "bidradar.log")

    configure_logging("test-component")  # 예외가 나면 이 테스트가 그 자체로 실패한다


def test_configure_logging_writes_to_file_when_dir_exists(tmp_path):
    log_dir = tmp_path / "logs"
    log_file = log_dir / "bidradar.log"

    import app.logging_config as logging_config

    original_dir, original_file = logging_config.LOG_DIR, logging_config.LOG_FILE
    logging_config.LOG_DIR, logging_config.LOG_FILE = log_dir, log_file
    try:
        configure_logging("test-component")
        logging.getLogger("bidradar.test").info("파일 로그 기록 확인용 메시지")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert log_file.exists()
        assert "파일 로그 기록 확인용 메시지" in log_file.read_text(encoding="utf-8")
    finally:
        # 이 테스트가 루트 로거에 추가한 핸들러를 제거해 다른 테스트에 영향이 안 가게 한다.
        for handler in list(logging.getLogger().handlers):
            if getattr(handler, "baseFilename", None) and str(log_file) in handler.baseFilename:
                logging.getLogger().removeHandler(handler)
                handler.close()
        logging_config.LOG_DIR, logging_config.LOG_FILE = original_dir, original_file

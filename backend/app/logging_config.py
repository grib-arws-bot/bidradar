"""콘솔 + 영속 파일 로그 설정(2026-09-14, OpenAPI 일일 요청한도 초과 사고 조사 후속).

지금까지는 `logging.basicConfig`로 표준출력에만 로그를 남겼다 — docker 컨테이너가 재생성되면
(예: `docker compose up -d` 재기동, 다른 컨테이너 문제로 인한 연쇄 recreate) 그 컨테이너의
표준출력 로그는 통째로 사라진다. 실제로 2026-09-13 나라장터 입찰공고정보서비스 쿼터 초과
사고를 다음날 조사하려 했을 때, 스케줄러 컨테이너가 그사이 재기동되면서 당시 호출 로그가
전부 사라져 "정확히 몇 번 호출했는지"를 재구성할 수 없었다.

`/app/logs/bidradar.log`(볼륨 마운트, 컨테이너 재생성과 무관하게 남음)에 로테이션 파일로도
같이 남긴다 — 표준출력(docker logs)은 그대로 유지해 기존 확인 방법을 안 바꾼다. 파일 쓰기가
실패해도(마운트 안 된 로컬 실행·테스트 등) 표준출력 로깅은 계속 동작해야 하므로 조용히
넘어간다.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("/app/logs")
LOG_FILE = LOG_DIR / "bidradar.log"
MAX_BYTES = 20 * 1024 * 1024  # 20MB
BACKUP_COUNT = 5


def configure_logging(component: str) -> None:
    fmt = f"%(asctime)s [{component}] %(levelname)s %(message)s"
    # force=True — basicConfig는 루트 로거에 이미 핸들러가 있으면(pytest의 기본 로그 캡처 등)
    # 조용히 아무 것도 안 한다. 여러 컴포넌트·테스트가 이 함수를 반복 호출해도 우리가 원하는
    # 레벨·포맷이 항상 실제로 적용되도록 강제한다.
    logging.basicConfig(level=logging.INFO, format=fmt, force=True)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(fmt))
        logging.getLogger().addHandler(file_handler)
    except OSError:
        # 볼륨이 마운트되지 않은 환경(로컬 스크립트 실행, 일부 테스트 등) — 표준출력 로깅만으로 계속.
        logging.getLogger(__name__).warning("%s 파일 로그(%s) 초기화 실패 — 표준출력 로깅만 사용", component, LOG_FILE)

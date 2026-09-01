"""python -m app.cli <command>. 라우터·서비스와 분리된 운영용 진입점(회원가입 화면 없음, 03절)."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from app.db import engine
from app.security.passwords import hash_password

# backend/app/cli.py 기준 ../../infra/.env — 호스트에서 실행할 때만 존재(컨테이너 안에서
# 실행하면 infra/는 마운트돼 있지 않으므로 자동 반영을 건너뛰고 값만 출력한다).
INFRA_ENV_PATH = Path(__file__).resolve().parents[2] / "infra" / ".env"


def _update_env_file(path: Path, key: str, raw_value: str) -> bool:
    """path의 key=... 줄을 raw_value로 교체한다. $는 $$로 이스케이프해서 쓴다 —

    docker-compose가 .env 값 안의 $를 변수 참조로 해석해서, argon2 해시($로 구간을 나눔)를
    그대로 넣으면 깨지는 사고가 있었다(의사결정 로그 참고). 여기서 항상 자동으로 처리한다.
    """
    if not path.exists():
        return False
    escaped = raw_value.replace("$", "$$")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={escaped}\n"
            found = True
            break
    if not found:
        return False
    path.write_text("".join(lines), encoding="utf-8")
    return True


def create_admin() -> None:
    """단일 공유 계정(report@grib.co.kr, 03절 v0.3)의 비밀번호를 새로 정하거나 바꾼다.

    DB에 사용자 테이블이 없으므로(역할 구분 폐기) 해시를 infra/.env에 직접 반영한다 —
    "비밀번호 찾기" 같은 셀프서비스 기능은 만들지 않는다(단일 공유 계정이라 이메일 인증
    수신자가 모호함). 운영자가 원할 때 이 명령을 다시 실행하면 그때마다 새 비밀번호로 바뀐다.
    """
    password = getpass.getpass("새 비밀번호: ")
    confirm = getpass.getpass("비밀번호 확인: ")
    if password != confirm:
        print("비밀번호가 일치하지 않습니다.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 8:
        print("비밀번호는 8자 이상이어야 합니다.", file=sys.stderr)
        raise SystemExit(1)

    new_hash = hash_password(password)
    if _update_env_file(INFRA_ENV_PATH, "ADMIN_PASSWORD_HASH", new_hash):
        print(f"\n{INFRA_ENV_PATH}의 ADMIN_PASSWORD_HASH를 갱신했습니다.")
        print("적용하려면 백엔드를 재기동하세요:")
        print("  docker compose -f infra/docker-compose.yml up -d --no-deps backend")
    else:
        print(f"\n{INFRA_ENV_PATH}를 찾지 못해 자동 반영을 건너뜁니다.")
        print("아래 값을 ADMIN_PASSWORD_HASH에 직접 붙여넣으세요(이미 $를 $$로 이스케이프했습니다):\n")
        print(new_hash.replace("$", "$$"))


def seed() -> None:
    from app.seed_data import run_seed

    run_seed(engine)
    print("시드 완료.")


def collect(source_id: int, service_key: str | None) -> None:
    """수동 1회 수집(U11). 공공데이터포털 인증키가 아직 없으면 --service-key 없이 호출해도
    되지만, 실제 나라장터 호출은 서비스키 없이는 거의 항상 실패한다(정상 — 발급 후 재시도)."""
    from sqlalchemy import update

    from app.collector.runner import run_source
    from app.models import source_credential

    with engine.begin() as conn:
        if service_key:
            conn.execute(
                update(source_credential)
                .where(source_credential.c.source_id == source_id, source_credential.c.kind == "service_key")
                .values(value=service_key)
            )
        result = run_source(conn, source_id)

    print(f"수집 완료: fetched={result['fetched']} inserted={result['inserted']} "
          f"skipped={result['skipped']} scored={result['scored']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin")
    subparsers.add_parser("seed")

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--source-id", type=int, required=True)
    collect_parser.add_argument("--service-key", default=None, help="공공데이터포털 인증키(발급받은 경우)")

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()
    elif args.command == "seed":
        seed()
    elif args.command == "collect":
        collect(args.source_id, args.service_key)


if __name__ == "__main__":
    main()

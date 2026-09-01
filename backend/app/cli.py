"""python -m app.cli <command>. 라우터·서비스와 분리된 운영용 진입점(회원가입 화면 없음, 03절)."""

from __future__ import annotations

import argparse
import getpass
import sys

from app.db import engine
from app.security.passwords import hash_password


def create_admin() -> None:
    """단일 공유 계정(report@grib.co.kr, 03절 v0.3)의 비밀번호 해시를 만든다.

    DB에 사용자 테이블이 없으므로(역할 구분 폐기) 해시를 출력만 한다 — 운영자가
    infra/.env의 ADMIN_PASSWORD_HASH에 직접 붙여넣는다.
    """
    password = getpass.getpass("새 비밀번호: ")
    confirm = getpass.getpass("비밀번호 확인: ")
    if password != confirm:
        print("비밀번호가 일치하지 않습니다.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 12:
        print("비밀번호는 12자 이상이어야 합니다.", file=sys.stderr)
        raise SystemExit(1)

    print("\nADMIN_PASSWORD_HASH 값을 infra/.env에 붙여넣으세요:\n")
    print(hash_password(password))


def seed() -> None:
    from app.seed_data import run_seed

    run_seed(engine)
    print("시드 완료.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin")
    subparsers.add_parser("seed")

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()
    elif args.command == "seed":
        seed()


if __name__ == "__main__":
    main()

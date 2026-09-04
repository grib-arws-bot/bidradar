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


def collect(source_id: int, service_key: str | None, force: bool, max_lookback_days: int | None) -> None:
    """수동 1회 수집(U11). 공공데이터포털 인증키가 아직 없으면 --service-key 없이 호출해도
    되지만, 실제 나라장터 호출은 서비스키 없이는 거의 항상 실패한다(정상 — 발급 후 재시도).

    --force는 B등급 소스의 최소 수집 간격을 관리자가 의도적으로 우회할 때만 쓴다(INBOX #5).
    --max-lookback-days는 데이터를 전부 지우고 특정 기간치를 재수집할 때만 쓴다 — 직전 성공
    수집 이력이 남아있으면 거기서부터 이어받으므로(runner.py의 _collection_window), 이 옵션이
    실제로 먹으려면 그 소스의 source_run 이력도 같이 비워야 한다."""
    from sqlalchemy import update

    from app.collector.runner import DEFAULT_MAX_LOOKBACK_DAYS, run_source
    from app.models import source_credential

    with engine.begin() as conn:
        if service_key:
            conn.execute(
                update(source_credential)
                .where(source_credential.c.source_id == source_id, source_credential.c.kind == "service_key")
                .values(value=service_key)
            )
        result = run_source(
            conn, source_id, force=force, max_lookback_days=max_lookback_days or DEFAULT_MAX_LOOKBACK_DAYS
        )

    print(f"수집 완료: fetched={result['fetched']} inserted={result['inserted']} "
          f"skipped={result['skipped']} scored={result['scored']} out_of_window={result['out_of_window']} "
          f"already_closed={result['already_closed']} auto_extracted={result['auto_extracted']}")


def structure(analysis_id: int, model: str) -> None:
    """S8 A2(요구사양 구조화, LLM) 수동 1회 실행. 반드시 관리자가 analysis id를 지정해서
    부를 때만 동작한다(CLAUDE.md S8 원칙 3 "자동 실행 금지") — auto_extract처럼 수집 파이프라인에
    자동으로 연결하지 않는다."""
    from app.services.analysis.structure import MODEL_ALIASES, run_structuring

    resolved_model = MODEL_ALIASES.get(model, model)
    with engine.begin() as conn:
        result = run_structuring(conn, analysis_id, model=resolved_model)

    print(
        f"구조화 완료: 추출={result['extracted']} 저장={result['saved']} "
        f"근거없음제외={result['skipped_no_cite']} 토큰(입력/출력)={result['input_tokens']}/{result['output_tokens']} "
        f"비용=${result['cost_usd']}"
    )


def check_compliance(source_id: int | None) -> None:
    """분기별 준법 재확인(advisory INBOX #6) 수동 실행. 스케줄러 인프라가 아직 없어(설계안
    스택 표에만 있음) 지금은 사람이나 cron으로 이 명령을 직접 돌린다."""
    from app.collector.compliance import check_all_sources, check_source

    with engine.begin() as conn:
        results = [check_source(conn, source_id)] if source_id else check_all_sources(conn)

    if not results:
        print("재확인 대상 소스(법적등급 B·C)가 없습니다.")
        return
    for r in results:
        status = "변경 감지 — 비활성화됨" if r["changed"] else ("확인 완료" if r["fetch_ok"] else f"확인 실패({r['error']})")
        print(f"[{r['source_id']}] {r['name']}: {status}")


def cleanup_closed(retention_days: int) -> None:
    """마감 후 retention_days일 지난 공고 삭제(2026-09-04 사용자 결정). 스케줄러 인프라가
    아직 없어 지금은 사람이나 cron으로 이 명령을 직접 돌린다."""
    from app.services.notice_cleanup import delete_expired_notices

    with engine.begin() as conn:
        deleted = delete_expired_notices(conn, retention_days=retention_days)
    print(f"삭제 완료: {deleted}건 (마감 후 {retention_days}일 경과 기준)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin")
    subparsers.add_parser("seed")

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--source-id", type=int, required=True)
    collect_parser.add_argument("--service-key", default=None, help="공공데이터포털 인증키(발급받은 경우)")
    collect_parser.add_argument("--force", action="store_true", help="B등급 최소 수집 간격 무시(관리자 수동 재수집)")
    collect_parser.add_argument(
        "--max-lookback-days", type=int, default=None, help="이 기간까지만 거슬러 수집(해당 소스 source_run 이력도 비워야 실제로 적용됨)"
    )

    compliance_parser = subparsers.add_parser("check-compliance")
    compliance_parser.add_argument("--source-id", type=int, default=None, help="생략하면 B·C등급 전체 재확인")

    cleanup_parser = subparsers.add_parser("cleanup-closed")
    cleanup_parser.add_argument("--retention-days", type=int, default=30, help="마감 후 이 일수가 지나면 삭제(기본 30일)")

    structure_parser = subparsers.add_parser("structure")
    structure_parser.add_argument("--analysis-id", type=int, required=True)
    structure_parser.add_argument(
        "--model", default="haiku", help="haiku/sonnet/opus 또는 정식 모델 ID(기본 haiku — 비용 절감)"
    )

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()
    elif args.command == "seed":
        seed()
    elif args.command == "collect":
        collect(args.source_id, args.service_key, args.force, args.max_lookback_days)
    elif args.command == "check-compliance":
        check_compliance(args.source_id)
    elif args.command == "cleanup-closed":
        cleanup_closed(args.retention_days)
    elif args.command == "structure":
        structure(args.analysis_id, args.model)


if __name__ == "__main__":
    main()

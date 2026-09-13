"""python -m app.cli <command>. 라우터·서비스와 분리된 운영용 진입점(회원가입 화면 없음, 03절)."""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from pathlib import Path

from app.db import engine
from app.security.passwords import hash_password

# app/scheduler.py·app/main.py와 같은 이유(2026-09-13) — 루트 로거 기본 레벨(WARNING)로는
# app/collector/adapters/openapi.py의 "OpenAPI 호출" INFO 로그가 CLI 실행(collect·
# process-pending 등) 중엔 하나도 안 보였다.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [cli] %(levelname)s %(message)s")

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


def seed_prod() -> None:
    """prod 전용 최소 시드(2026-09-10) — 관심주제·키워드·소스·발주기관만 채우고 고객(customer)은
    비워둔다. 관리자가 직접 실제 고객(그립 AI/IoT/Robot, Safety/Factory, AX/Service 3개 기관)을
    등록할 계획이라 가짜 데모 데이터를 넣지 않는다(app/seed_data.py의 run_seed_prod 참고)."""
    from app.seed_data import run_seed_prod

    run_seed_prod(engine)
    print("prod 최소 시드 완료(관심주제·키워드·소스·발주기관만 — 고객은 비워둠).")


def add_source_cmd(name: str) -> None:
    """이미 운영 중인 DB에 SOURCE_SEED 소스 하나만 추가한다(2026-09-13 신설) — seed-prod는
    전체를 다시 넣어 중복이 나므로, 새 소스가 하나씩 추가되는 지금 단계엔 이 명령이 맞다."""
    from app.seed_data import add_source

    source_id = add_source(engine, name)
    print(f"소스 추가 완료: {name!r} (id={source_id})")


def backfill_org_categories_cmd() -> None:
    """이미 수집된 발주기관 중 category(업종/분야)가 비어있는 행을 기관명 패턴으로 일괄
    분류한다(2026-09-11) — 신규 기관은 수집 시점에 자동 분류되므로 1회만 실행하면 된다."""
    from app.services.org_classification import backfill_org_categories

    with engine.begin() as conn:
        counts = backfill_org_categories(conn)
    total = sum(counts.values())
    print(f"분류 완료: {total}건")
    for category, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {category}: {count}건")


def collect(source_id: int, service_key: str | None, max_lookback_days: int | None) -> None:
    """수동 1회 수집(U11). 공공데이터포털 인증키가 아직 없으면 --service-key 없이 호출해도
    되지만, 실제 나라장터 호출은 서비스키 없이는 거의 항상 실패한다(정상 — 발급 후 재시도).

    --max-lookback-days는 데이터를 전부 지우고 특정 기간치를 재수집할 때만 쓴다 — 직전 성공
    수집 이력이 남아있으면 거기서부터 이어받으므로(runner.py의 _collection_window), 이 옵션이
    실제로 먹으려면 그 소스의 source_run 이력도 같이 비워야 한다.

    수집 뒤 중복체크·첨부분석(A1)·AI분석(A2)까지 한 번에 이어진다(2026-09-07,
    run_source_and_process_pending) — 첨부분석·AI분석은 그 소스의 auto_extract/auto_analyze
    설정을 그대로 따르므로 꺼져 있으면 자연히 건너뛴다."""
    from urllib.parse import unquote
    from sqlalchemy import update

    from app.collector.runner import CollectionInProgressError, DEFAULT_MAX_LOOKBACK_DAYS, run_source_and_process_pending
    from app.models import source_credential

    if service_key:
        # data.go.kr 마이페이지는 키를 "일반 인증키(Encoding)"(%2B·%3D 등 퍼센트 인코딩된 형태)와
        # "일반 인증키(Decoding)"(원문, +·/·= 그대로) 두 가지로 같이 보여준다. url_guard.fetch()가
        # 넘겨받은 값을 쿼리스트링에 넣을 때 자체적으로 다시 인코딩하므로, 이미 인코딩된 형태를
        # 그대로 넣으면 %가 %25로 이중 인코딩돼 "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"로 실패한다
        # (2026-09-10 prod 최초 배포 시 실제 발생 — xlsx의 Encoding 키를 그대로 붙여넣어 재현).
        # unquote()는 %XX 패턴이 없는 입력(이미 Decoding 형태)엔 아무 영향이 없어 안전하게 항상
        # 적용한다 — 사용자가 어느 쪽을 붙여넣어도 저장되는 값은 항상 Decoding 형태로 통일된다.
        service_key = unquote(service_key)
        with engine.begin() as conn:
            conn.execute(
                update(source_credential)
                .where(source_credential.c.source_id == source_id, source_credential.c.kind == "service_key")
                .values(value=service_key)
            )

    try:
        result = run_source_and_process_pending(
            source_id, max_lookback_days=max_lookback_days or DEFAULT_MAX_LOOKBACK_DAYS
        )
    except CollectionInProgressError as exc:
        print(f"수집 건너뜀: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"수집 완료: fetched={result['fetched']} inserted={result['inserted']} "
          f"skipped={result['skipped']} scored={result['scored']} out_of_window={result['out_of_window']} "
          f"already_closed={result['already_closed']}")
    print(f"중복 무효화: {result['dedup_notices_updated']}건(그룹 {result['dedup_groups_with_duplicates']}개)")
    print(f"첨부 자동추출: 대상 {result['extraction_candidates']}건 중 {result['auto_extracted']}건 처리, "
          f"AI 자동분석: 대상 {result['analyze_candidates']}건 중 {result['auto_analyzed']}건 처리")


def process_pending(source_id: int | None) -> None:
    """첨부문서 자동 추출(A1)·AI 자동분석(A2)을 목록 수집과 분리한 후속 패스(2026-09-05) —
    공고 단위로 각각 짧은 트랜잭션을 써서, 신규 건이 많을 때 하나의 긴 트랜잭션이 DB 락을
    오래 쥐는 문제(스키마 마이그레이션까지 막았던 실사고)를 피한다."""
    from app.services.pending_analysis import run_pending_analysis

    result = run_pending_analysis(source_id)
    print(
        f"후속 처리 완료: 추출대상={result['extraction_candidates']} 추출성공={result['auto_extracted']} "
        f"분석대상={result['analyze_candidates']} 분석성공={result['auto_analyzed']}"
    )


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
        f"비용=${result['cost_usd']} 관심주제추가={result['topics_added']}"
    )


def reprocess_attachments(source_id: int) -> None:
    """이미 A1을 시도했지만 첨부 0건으로 남은 공고를 캐시된 raw_payload로 재시도한다
    (2026-09-08, 의사결정 로그 82번 버그의 과거 잔여분 백필). 라이브 API를 호출하지 않으므로
    apis.data.go.kr 상태와 무관하게 안전하게 여러 번 실행해도 된다."""
    from app.services.reprocess_attachments import reprocess_empty_extractions

    result = reprocess_empty_extractions(source_id)
    print(
        f"재처리 완료: 대상={result['candidates']} 캐시없음(건너뜀)={result['no_cache_match']} "
        f"재시도={result['reprocessed']} 첨부발견={result['found_docs']}"
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


def cleanup_closed(retention_days: int, no_close_retention_days: int) -> None:
    """마감(close_dt) 후 retention_days일, 또는 마감일이 없는 공고는 공고일 기준
    no_close_retention_days일 지난 공고를 삭제한다(2026-09-04 결정, 2026-09-10 기준 변경).
    2026-09-10부터 매 수집(run_source) 직후 자동으로도 실행되므로(app/collector/runner.py),
    이 명령은 수집 자체가 오래 안 도는 소스를 수동으로 정리하고 싶을 때 쓴다."""
    from app.services.notice_cleanup import delete_expired_notices

    with engine.begin() as conn:
        deleted = delete_expired_notices(conn, retention_days=retention_days, no_close_retention_days=no_close_retention_days)
    print(f"삭제 완료: {deleted}건 (마감 후 {retention_days}일 경과, 또는 마감일 없이 공고일 기준 {no_close_retention_days}일 경과)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin")
    subparsers.add_parser("seed")
    subparsers.add_parser("seed-prod")
    subparsers.add_parser("backfill-org-categories")

    add_source_parser = subparsers.add_parser("add-source")
    add_source_parser.add_argument("--name", required=True, help="app/seed_constants.py SOURCE_SEED의 소스명과 정확히 일치해야 함")

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--source-id", type=int, required=True)
    collect_parser.add_argument("--service-key", default=None, help="공공데이터포털 인증키(발급받은 경우)")
    collect_parser.add_argument(
        "--max-lookback-days", type=int, default=None, help="이 기간까지만 거슬러 수집(해당 소스 source_run 이력도 비워야 실제로 적용됨)"
    )

    compliance_parser = subparsers.add_parser("check-compliance")
    compliance_parser.add_argument("--source-id", type=int, default=None, help="생략하면 B·C등급 전체 재확인")

    cleanup_parser = subparsers.add_parser("cleanup-closed")
    cleanup_parser.add_argument("--retention-days", type=int, default=3, help="마감 후 이 일수가 지나면 삭제(기본 3일)")
    cleanup_parser.add_argument(
        "--no-close-retention-days", type=int, default=60, help="마감일이 없는 공고는 공고일 기준 이 일수가 지나면 삭제(기본 60일)"
    )

    structure_parser = subparsers.add_parser("structure")
    structure_parser.add_argument("--analysis-id", type=int, required=True)
    structure_parser.add_argument(
        "--model", default="haiku", help="haiku/sonnet/opus 또는 정식 모델 ID(기본 haiku — 비용 절감)"
    )

    process_pending_parser = subparsers.add_parser("process-pending")
    process_pending_parser.add_argument(
        "--source-id", type=int, default=None, help="생략하면 auto_extract/auto_analyze가 켜진 모든 소스 대상"
    )

    reprocess_parser = subparsers.add_parser("reprocess-attachments")
    reprocess_parser.add_argument("--source-id", type=int, required=True)

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()
    elif args.command == "seed":
        seed()
    elif args.command == "seed-prod":
        seed_prod()
    elif args.command == "backfill-org-categories":
        backfill_org_categories_cmd()
    elif args.command == "add-source":
        add_source_cmd(args.name)
    elif args.command == "collect":
        collect(args.source_id, args.service_key, args.max_lookback_days)
    elif args.command == "check-compliance":
        check_compliance(args.source_id)
    elif args.command == "cleanup-closed":
        cleanup_closed(args.retention_days, args.no_close_retention_days)
    elif args.command == "structure":
        structure(args.analysis_id, args.model)
    elif args.command == "process-pending":
        process_pending(args.source_id)
    elif args.command == "reprocess-attachments":
        reprocess_attachments(args.source_id)


if __name__ == "__main__":
    main()

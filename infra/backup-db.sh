#!/bin/bash
# BidRadar Postgres 자동 백업 (2026-09-10, ARWS의 backup-baserow.sh와 동일 패턴을 복제 —
# 의사결정_로그 6번/97번).
#
# 순수 pg_dump를 커스텀 포맷(-Fc, 단일 파일 통짜 덤프)으로 직접 실행한다. "최소" 백업이 목표라
# 압축 자동화/보관 정리 정도만 하고, 원격 업로드 등은 범위 밖.
#
# BidRadar는 나라장터·IRIS 등 공개 데이터를 언제든 재수집할 수 있고(의사결정_로그 93번, prod
# 데이터는 재수집으로 확정) 마감·공고일 기준 자동삭제까지 도는(92번) 서비스라, 백업의 실제
# 존재 이유는 "재수집 불가능한 데이터"(고객·관심주제·리포트 설정 등 직접 입력값) 보호다 —
# ARWS와 동일하게 짧은 보관기간(기본 3일)으로 충분하다고 판단.
#
# 사용법: infra/backup-db.sh [백업디렉토리] [보관일수]
#   백업디렉토리 기본값: ~/bidradar-backups(저장소 워킹트리 밖 — `git clean -fdx` 한 번에 그동안
#   쌓인 백업이 날아가지 않도록)
#   보관일수 기본값: 3일
#
# cron 예시(prod, 매일 00:30 KST 실행 — 서버 시스템 시간대가 UTC이므로 KST 00:30 = UTC(전날) 15:30):
#   30 15 * * * /path/to/bidradar/infra/backup-db.sh >> /home/grib/bidradar-backups/backup.log 2>&1

set -euo pipefail

CONTAINER="${BIDRADAR_DB_CONTAINER:-bidradar-db-1}"
DB_USER="${POSTGRES_USER:-bidradar}"
DB_NAME="${POSTGRES_DB:-bidradar}"
BACKUP_DIR="${1:-$HOME/bidradar-backups}"
RETENTION_DAYS="${2:-3}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="bidradar_${TIMESTAMP}.dump"
TMP_PATH_IN_CONTAINER="/tmp/${FILENAME}"

mkdir -p "$BACKUP_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[backup-db] 실패: 컨테이너 '${CONTAINER}'가 실행 중이 아님" >&2
  exit 1
fi

echo "[backup-db] pg_dump 실행 중 (container=${CONTAINER})..."
MSYS_NO_PATHCONV=1 docker exec -u postgres "$CONTAINER" pg_dump -Fc -U "$DB_USER" -d "$DB_NAME" -f "$TMP_PATH_IN_CONTAINER"

echo "[backup-db] 덤프 무결성 확인 중..."
if ! MSYS_NO_PATHCONV=1 docker exec -u postgres "$CONTAINER" pg_restore --list "$TMP_PATH_IN_CONTAINER" > /dev/null 2>&1; then
  echo "[backup-db] 실패: pg_restore --list 검증 실패 - 손상된 덤프로 간주, 복사하지 않음" >&2
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" rm -f "$TMP_PATH_IN_CONTAINER"
  exit 1
fi

if command -v cygpath > /dev/null 2>&1; then
  DEST_PATH="$(cygpath -w "$BACKUP_DIR")\\${FILENAME}"
else
  DEST_PATH="${BACKUP_DIR}/${FILENAME}"
fi
MSYS_NO_PATHCONV=1 docker cp "${CONTAINER}:${TMP_PATH_IN_CONTAINER}" "$DEST_PATH"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" rm -f "$TMP_PATH_IN_CONTAINER"

chmod 600 "${BACKUP_DIR}/${FILENAME}" 2>/dev/null || echo "[backup-db] 경고: 파일 권한 설정 실패(무시하고 계속)" >&2

SIZE=$(du -h "${BACKUP_DIR}/${FILENAME}" | cut -f1)
echo "[backup-db] 완료: ${BACKUP_DIR}/${FILENAME} (${SIZE})"

DELETED=$(find "$BACKUP_DIR" -name 'bidradar_*.dump' -mtime +"$RETENTION_DAYS" -print -delete 2>&1) || {
  echo "[backup-db] 경고: 오래된 백업 정리 중 오류 발생(백업 자체는 성공) — 수동 확인 필요: $DELETED" >&2
  exit 0
}
if [ -n "$DELETED" ]; then
  echo "[backup-db] 보관기간(${RETENTION_DAYS}일) 초과로 삭제됨:"
  echo "$DELETED"
fi

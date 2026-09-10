#!/bin/sh
# 자체 서명(self-signed) TLS 인증서 생성 (2026-09-10, ARWS의 동일 스크립트를 그대로 복제 — CLAUDE.md
# "infra/는 ARWS 구조를 복제" 원칙, 의사결정_로그 6번).
#
# 정식 인증서(Let's Encrypt 등)를 받으려면 도메인 소유 증명(포트 80 외부 개방 또는 DNS API 접근)이
# 필요한데 지금은 둘 다 없어 자체 서명 인증서로 대체 — 브라우저가 최초 접속 시 "안전하지 않음"
# 경고를 띄우고, "고급 → 계속 진행"을 한 번 눌러줘야 한다.
#
# 인증서는 git에 커밋하지 않음(.gitignore 처리) — stg(로컬)·prod 각 환경에서 이 스크립트를 한 번씩
# 직접 실행해서 자기 몫을 만든다. 유효기간 10년 — 내부 전용 인증서라 짧은 주기 갱신 불필요.
#
# 사용법: sh infra/tls-proxy/gen-cert.sh (infra/ 디렉토리 기준으로 실행)

set -e
cd "$(dirname "$0")"
mkdir -p certs

if [ -f certs/selfsigned.crt ]; then
    echo "이미 인증서가 있습니다(certs/selfsigned.crt) — 다시 만들려면 파일을 먼저 지우세요."
    exit 0
fi

openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout certs/selfsigned.key \
    -out certs/selfsigned.crt \
    -subj "/CN=thingx.grib-iot.com" \
    -addext "subjectAltName=DNS:thingx.grib-iot.com,DNS:localhost,IP:127.0.0.1"

chmod 600 certs/selfsigned.key 2>/dev/null || echo "경고: 개인키 권한 설정 실패(무시하고 계속)" >&2

echo "생성 완료: certs/selfsigned.crt, certs/selfsigned.key"

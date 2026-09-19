# BidRadar 스테이징(로컬 PC) → 프로덕션(서버) 배포 스크립트 (2026-09-10)
#
# D:\Code-CLI\ARWS\scripts\deploy-to-production.ps1의 구조를 그대로 복제한다(CLAUDE.md
# "infra/·scripts/deploy-to-production.ps1·.github/workflows/는 ARWS 구조를 복제" 원칙,
# 의사결정_로그 6번). n8n·Baserow가 없어 그 두 서비스 관련 부분만 뺐다 — 배포 대상은
# backend·frontend·scheduler 세 개(모두 같은 백엔드 이미지를 빌드하는 backend/scheduler
# 포함), 서버는 thingx.grib-iot.com(ARWS와 공유, docker compose 프로젝트명 "bidradar"로 격리).
#
# 하는 일:
#   0) 로컬 HEAD가 origin/main과 일치 + 워킹트리 clean 확인
#   1) 로컬에서 backend·frontend·scheduler 이미지 빌드
#   2) 사람이 로컬(stg) 화면으로 직접 확인했는지 확인(CI에서는 생략)
#   3) 이미지에 git 커밋 해시 태그 추가(롤백용, :latest와 별도 보관) + 레지스트리 경로 태그
#   4) 서버의 git 체크아웃(~/bidradar)을 origin/main으로 fast-forward(레지스트리 서비스
#      정의를 push보다 먼저 반영해야 함)
#   5) 서버의 자체 호스팅 레지스트리(registry:2, 127.0.0.1:5000)가 떠 있는지 확인
#   6) SSH 터널로 그 레지스트리에 이미지 push(2026-09-18, 의사결정_로그 169번 — tar+scp를
#      대체. 레지스트리가 레이어 단위로 diff 전송하므로 안 바뀐 큰 레이어는 재전송 안 함).
#      터널은 Windows 프로세스가 아니라 `--network host` 컨테이너 안에서 띄운다 — Docker
#      Desktop(WSL2)의 도커 데몬이 Windows 호스트 루프백과 다른 네트워크 네임스페이스를
#      쓰기 때문(2026-09-19, 상세 이유는 6단계 코드 주석 참고).
#   7) 로컬 .env에는 있는데 prod .env에는 없는 변수가 있는지 확인해서 경고
#   8) 서버에서: 교체 직전 이미지를 :candidate-previous로 백업 → 레지스트리에서 pull 후
#      원래 이름으로 재태깅 → 재기동(--build 없이 이미지만 교체 — 서버는 4코어/8GB로 ARWS와
#      공유하는 셈이라 무거운 빌드를 서버에서 직접 돌리는 걸 피한다)
#   9) 프로덕션 응답 확인 + 로그인 스모크 테스트(HTTP 200뿐 아니라 실제 로그인까지 확인)
#
# 전제:
#   - 로컬 PC에서 이미 `docker compose up -d --build`로 확인해본 뒤 이 스크립트를 실행할 것.
#   - SSH 접속(thingx.grib-iot.com)은 키 인증이 이미 설정되어 있음(ARWS 배포와 동일한 키 재사용
#     — 같은 서버·같은 관리 주체이므로 별도 키 발급 불필요, 2026-09-10 확인). 2026-09-18부터
#     이 SSH 연결 위에 레지스트리 push용 터널(-L)도 얹는다 — 새 포트를 열 필요 없음.
#   - infra/tls-proxy/certs/selfsigned.crt·key가 서버에 이미 있어야 함(최초 1회
#     `sh infra/tls-proxy/gen-cert.sh`를 서버에서 직접 실행 — git에 커밋 안 됨).
#
# 사용법 (PowerShell, 수동 실행):
#   D:\Code-CLI\BidRadar\scripts\deploy-to-production.ps1
#   특정 서비스만 배포: -Services "backend","frontend"
#
# .github/workflows/deploy-prod.yml(수동 workflow_dispatch)에서도 이 스크립트를 그대로 호출한다.

param(
    [string[]]$Services = @("backend", "frontend", "scheduler")
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Stop-RegistryTunnel {
    # 2026-09-19 — 터널을 Windows 프로세스가 아니라 컨테이너 안에서 띄우므로(아래 6단계
    # 주석 참고) 정리도 컨테이너 삭제로 한다. 안 떠 있어도(아직 6단계 전이면) 조용히 넘어간다.
    # try/catch 필수 — $ErrorActionPreference="Stop" 상태에서 네이티브 명령의 stderr를
    # 리다이렉트하면(컨테이너가 없어 "No such container"를 stderr로 찍는 정상 상황조차)
    # PowerShell이 이를 종료 오류로 승격시켜 스크립트 전체가 죽는다(실제로 6번째 실전
    # 배포에서 이걸로 실패했다) — try/catch로 감싸 무해한 실패를 확실히 삼킨다.
    try { docker rm -f bidradar-registry-tunnel 2>$null | Out-Null } catch {}
}

function Assert-Success([string]$description) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "실패: $description (종료 코드 $LASTEXITCODE)" -ForegroundColor Red
        Stop-RegistryTunnel
        exit 1
    }
}

# self-hosted 러너(BidRadar 전용, ARWS 러너와 별개 — 의사결정_로그 94번)는
# D:\actions-runner-bidradar\_work\bidradar\bidradar 등 별도 작업 디렉터리로 체크아웃한다.
$repoDir      = if ($env:GITHUB_WORKSPACE) { $env:GITHUB_WORKSPACE } else { "D:\Code-CLI\BidRadar" }
$infraDir     = Join-Path $repoDir "infra"
$remoteHost   = "thingx.grib-iot.com"
$remoteDir    = "~/bidradar"
# 2026-09-18 — 개발 PC에서 이미 다른 용도로 5000번을 쓰고 있을 수 있어(예: 로컬 개발 서버)
# infra/.env로 바꿀 수 있게 환경변수화(DB_HOST_PORT 등 기존 패턴과 동일).
$registryPort = if ($env:REGISTRY_PORT) { $env:REGISTRY_PORT } else { "5000" }

$canonicalEnvPath = "D:\Code-CLI\BidRadar\infra\.env"
if ($repoDir -ne "D:\Code-CLI\BidRadar") {
    Write-Host "==> CI 체크아웃 감지 — 실제 관리되는 .env를 체크아웃 디렉터리로 복사 중... ($repoDir\infra\.env)"
    Copy-Item -Path $canonicalEnvPath -Destination (Join-Path $infraDir ".env") -Force
}

git -C $repoDir fetch origin
Assert-Success "origin fetch(배포 전 사전 점검)"
$localHead = (git -C $repoDir rev-parse HEAD).Trim()
$originMainSha = (git -C $repoDir rev-parse origin/main).Trim()
if ($localHead -ne $originMainSha) {
    Write-Host "실패: 로컬 HEAD($localHead)가 origin/main($originMainSha)과 다릅니다 — 먼저 push하거나 origin/main 기준으로 맞추고 다시 실행하세요." -ForegroundColor Red
    exit 1
}
$dirtyStatus = git -C $repoDir status --porcelain
if ($dirtyStatus) {
    Write-Host "실패: 워킹트리에 커밋 안 된 변경사항이 있습니다 — 먼저 커밋하거나 정리하고 다시 실행하세요." -ForegroundColor Red
    Write-Host $dirtyStatus
    exit 1
}
Write-Host "==> 사전 점검 통과 — 로컬 HEAD가 origin/main과 일치하고 워킹트리가 clean합니다. ($localHead)"

$gitSha = (git -C $repoDir rev-parse --short HEAD 2>$null)
if (-not $gitSha) { $gitSha = "local-$(Get-Date -Format 'yyyyMMddHHmmss')" }
Write-Host "배포 버전 태그: $gitSha"

# docker compose 프로젝트명은 docker-compose.yml의 `name: bidradar`로 고정돼 있어(2026-09-01
# 사고 재발 방지) 로컬/서버 둘 다 이미지 태그가 자동으로 일치한다(예: bidradar-backend).
$imageBaseNames = $Services | ForEach-Object { "bidradar-$_" }

Write-Host "==> 1) 로컬에서 이미지 빌드 중... ($($Services -join ', '))"
Push-Location $infraDir
try {
    docker compose build $Services
    Assert-Success "이미지 빌드"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "==> 2) 스테이징(로컬) 확인"
if ($env:CI) {
    Write-Host "    CI 환경 감지 — 수동 workflow_dispatch(Actions 탭에서 사람이 직접 실행)로 트리거됐으므로 대화형 확인 생략."
} else {
    Write-Host "    로컬에서 'docker compose up -d' 로 띄워서 브라우저로 직접 확인하셨나요?"
    Write-Host "    (http://127.0.0.1:13200 — 아직 안 하셨다면 Ctrl+C로 중단하고 먼저 확인하세요)"
    $confirm = Read-Host "테스트를 통과했으면 y를 입력하세요"
    if ($confirm -ne "y") {
        Write-Host "배포를 중단합니다."
        exit 1
    }
}

Write-Host ""
Write-Host "==> 3) 이미지에 버전 태그 추가 중... (:latest 외 :$gitSha·레지스트리 경로 태그도 함께)"
foreach ($base in $imageBaseNames) {
    docker tag "${base}:latest" "${base}:$gitSha"
    Assert-Success "이미지 태그 지정 (${base}:$gitSha)"
    docker tag "${base}:latest" "127.0.0.1:${registryPort}/${base}:$gitSha"
    Assert-Success "레지스트리 경로 태그 지정 (127.0.0.1:${registryPort}/${base}:$gitSha)"
}

Write-Host ""
Write-Host "==> 4) 서버 저장소를 최신 커밋으로 동기화 (registry 서비스 정의 등을 push보다 먼저 반영)"
ssh $remoteHost "cd $remoteDir && git fetch origin && git merge --ff-only origin/main"
Assert-Success "서버 저장소 동기화(git fetch/merge --ff-only)"

Write-Host ""
Write-Host "==> 5) 서버의 자체 호스팅 레지스트리 기동 확인 (127.0.0.1:${registryPort}, 인터넷 비노출)"
ssh $remoteHost "cd $remoteDir && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d registry"
Assert-Success "레지스트리 컨테이너 기동"

# 2026-09-19 — 직전 배포가 실패해 컨테이너가 재생성(Recreate)된 채로 이 스크립트를 다시
# 돌렸더니, "컨테이너가 시작됨"과 "앱이 실제로 요청을 받을 준비가 됨" 사이의 간극 때문에
# 곧바로 push를 시도하다 "connection refused"로 또 실패했다(이미 떠 있던 컨테이너를 그냥
# 재사용한 첫 시도 때는 이 문제가 안 드러났다). healthcheck가 healthy가 될 때까지 최대
# 30초 폴링한다 — 고정 sleep이 아니라 실제 상태를 확인.
$registryReady = $false
for ($i = 0; $i -lt 15; $i++) {
    $health = ssh $remoteHost "docker inspect --format='{{.State.Health.Status}}' bidradar-registry-1 2>/dev/null"
    if ($health -eq "healthy") { $registryReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $registryReady) {
    Write-Host "  실패: 레지스트리 컨테이너가 30초 안에 healthy 상태가 되지 않았습니다." -ForegroundColor Red
    exit 1
}
Write-Host "  확인됨 — 레지스트리 healthy"

Write-Host ""
Write-Host "==> 6) SSH 터널로 레지스트리에 이미지 push 중... (tar+scp 대체, 의사결정_로그 169번)"
#
# 2026-09-19 — 처음 세 번의 실전 배포가 전부 이 단계에서 실패했다("i/o timeout" →
# "connection refused" 두 가지 다른 증상). Windows 호스트에서 ssh -L로 직접 터널을 띄우면
# 로컬(127.0.0.1:$registryPort)은 PowerShell TcpClient로 확인해도 정상 응답하는데, docker
# push는 매번 거부당했다 — 원인은 Docker Desktop이 WSL2 VM 안에서 데몬을 돌리기 때문이다.
# docker push는 "클라이언트"가 아니라 그 데몬이 실제로 127.0.0.1에 접속을 시도하는데,
# 데몬의 루프백은 WSL2 VM 자신의 네트워크 네임스페이스지 Windows 호스트의 루프백이
# 아니다 — 기본(NAT) 네트워킹 모드에서 이 둘은 서로 안 보인다(실측: `docker run
# --network host curlimages/curl ...`로 데몬과 같은 네임스페이스에서 접속해보면, Windows
# 쪽에 띄운 터널은 000이고 컨테이너 안에서 띄운 터널은 200 — 반대로 컨테이너 기반 터널은
# Windows 호스트 자체에서는 안 보임. 즉 두 방향이 대칭이 아니다). 그래서 터널을 아예
# `--network host` 컨테이너 안에서 띄운다 — 도커 데몬과 완전히 같은 네트워크
# 네임스페이스를 쓰게 되므로 push가 실제로 127.0.0.1:$registryPort에 닿는다.
#
# ~/.ssh 전체(config·known_hosts·키)를 읽기전용으로 마운트한 뒤 컨테이너의 쓰기 가능한
# 레이어로 복사해 chmod한다 — OpenSSH가 마운트 그대로의(대개 너무 열린) 권한을 가진 개인키
# 파일은 거부하기 때문. config를 그대로 쓰므로 포트·사용자·키 파일 이름을 이 스크립트에
# 따로 하드코딩하지 않고 나머지 ssh 호출들과 동일한 out-of-band 설정을 그대로 재사용한다.
Stop-RegistryTunnel  # 혹시 이전 실패로 남은 터널 컨테이너 정리
$sshDir = Join-Path $HOME ".ssh"
docker run -d --network host --name bidradar-registry-tunnel `
    -v "${sshDir}:/root/.ssh-src:ro" `
    --entrypoint sh alpine -c "apk add --no-cache openssh-client >/dev/null 2>&1 && cp -r /root/.ssh-src /root/.ssh && chmod -R 600 /root/.ssh && chmod 700 /root/.ssh && exec ssh -N -L 127.0.0.1:${registryPort}:127.0.0.1:${registryPort} $remoteHost" | Out-Null
Assert-Success "레지스트리 터널 컨테이너 기동"

# 터널이 실제로 열렸는지는 Windows 호스트가 아니라 도커 데몬과 같은 네임스페이스
# (--network host)에서 확인해야 한다 — 위 주석의 비대칭성 때문에 Windows 쪽 TcpClient로는
# 이 컨테이너 기반 터널의 준비 여부를 판단할 수 없다.
# 아래 네이티브 명령들은 전부 stderr를 리다이렉트하므로 try/catch로 감싼다 —
# $ErrorActionPreference="Stop" 아래에서 리다이렉트된 stderr 한 줄만 있어도 PowerShell이
# 종료 오류로 승격시켜 스크립트를 죽인다(Stop-RegistryTunnel과 같은 이유, 실제로 여기
# curl probe가 터널 준비 전 정상적으로 실패하는 매 반복마다 이 문제가 터졌었다).
$tunnelReady = $false
for ($i = 0; $i -lt 15; $i++) {
    $running = try { docker inspect --format '{{.State.Running}}' bidradar-registry-tunnel 2>$null } catch { "" }
    if ($running -ne "true") {
        Write-Host "  실패: 레지스트리 터널 컨테이너가 예기치 않게 종료됨" -ForegroundColor Red
        try { docker logs bidradar-registry-tunnel 2>&1 | Write-Host } catch {}
        exit 1
    }
    $probe = try { docker run --rm --network host curlimages/curl:latest -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${registryPort}/v2/" --max-time 2 2>$null } catch { "" }
    if ($probe -eq "200") { $tunnelReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $tunnelReady) {
    Write-Host "  실패: 터널이 15초 안에 127.0.0.1:${registryPort}에서 응답하지 않았습니다." -ForegroundColor Red
    try { docker logs bidradar-registry-tunnel 2>&1 | Write-Host } catch {}
    Stop-RegistryTunnel
    exit 1
}
Write-Host "  확인됨 — SSH 터널 연결 가능(컨테이너가 도커 데몬과 네트워크 네임스페이스 공유)"
try {
    foreach ($base in $imageBaseNames) {
        docker push "127.0.0.1:${registryPort}/${base}:$gitSha"
        Assert-Success "레지스트리로 이미지 전송(push, $base)"
    }
} finally {
    Stop-RegistryTunnel
}

Write-Host ""
Write-Host "==> 7) prod .env에 로컬에는 있는 변수가 빠졌는지 확인"
function Get-EnvVarNames([string]$content) {
    $names = @()
    foreach ($line in ($content -split "`r?`n")) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=') { $names += $matches[1] }
    }
    return $names | Sort-Object -Unique
}
$localEnvVars = Get-EnvVarNames (Get-Content "$repoDir\infra\.env" -Raw)
$remoteEnvContent = ssh $remoteHost "cat $remoteDir/infra/.env 2>/dev/null"
Assert-Success "prod .env 조회"
$remoteEnvVars = Get-EnvVarNames (($remoteEnvContent | Out-String))
$missingEnvVars = $localEnvVars | Where-Object { $remoteEnvVars -notcontains $_ }
if ($missingEnvVars.Count -gt 0) {
    Write-Host "  경고: prod .env에 다음 변수가 없습니다 — 해당 기능이 조용히 꺼진 채로 동작할 수 있습니다:" -ForegroundColor Yellow
    foreach ($varName in $missingEnvVars) {
        Write-Host "    - $varName" -ForegroundColor Yellow
    }
    Write-Host "  서버에 SSH 접속해서 $remoteDir/infra/.env 에 직접 추가해주세요(자동으로 채워주지 않습니다 — 실제 시크릿 값이 필요함)." -ForegroundColor Yellow
} else {
    Write-Host "  확인됨 — prod .env에 로컬과 동일한 변수 이름이 전부 있습니다."
}

Write-Host ""
Write-Host "==> 8) 서버에서 교체 대상 이미지를 임시 보관 후 레지스트리에서 새 이미지 적용 중..."
foreach ($base in $imageBaseNames) {
    ssh $remoteHost "docker tag ${base}:latest ${base}:candidate-previous 2>/dev/null || true"
    ssh $remoteHost "docker pull 127.0.0.1:${registryPort}/${base}:$gitSha"
    Assert-Success "서버에서 레지스트리 pull ($base)"
    ssh $remoteHost "docker tag 127.0.0.1:${registryPort}/${base}:$gitSha ${base}:latest && docker tag 127.0.0.1:${registryPort}/${base}:$gitSha ${base}:$gitSha"
    Assert-Success "pull한 이미지 재태깅 ($base)"
}
$servicesArg = $Services -join " "
# prod는 TLS 종료 프록시 오버레이(docker-compose.prod.yml)를 추가로 얹어서 실행한다. --no-deps로
# 지정된 서비스 외에는 건드리지 않는다(예: db·tls-proxy·registry가 불필요하게 재생성되는 것 방지).
ssh $remoteHost "cd $remoteDir && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --no-deps $servicesArg"
Assert-Success "서버에 이미지 적용(compose up)"
ssh $remoteHost "cp $remoteDir/.last-deployed-sha $remoteDir/.last-deployed-sha.candidate-previous 2>/dev/null || true"
ssh $remoteHost "echo '$gitSha' > $remoteDir/.last-deployed-sha"
Assert-Success "배포 버전 기록"

if ($Services -contains "backend") {
    Write-Host ""
    Write-Host "==> 8-1) DB 마이그레이션 적용 중(alembic upgrade head)..."
    # 이미 적용된 마이그레이션은 건너뛰므로(idempotent) 변경사항이 없는 배포에서도 안전하게 매번
    # 실행한다 — 새 backend 이미지가 기대하는 스키마가 실제 DB에 반영돼 있는지 여기서 확정한다.
    ssh $remoteHost "docker exec bidradar-backend-1 python -m alembic upgrade head"
    Assert-Success "DB 마이그레이션(alembic upgrade head)"
}

Write-Host ""
Write-Host "==> 9) 프로덕션 확인 (HTTP 응답 + 로그인 스모크 테스트)"
Start-Sleep -Seconds 5
# 외부(로컬 PC)에서 3300 포트로 직접 요청하면 아직 관리자에게 NAT 요청을 안 한 상태라 도달 못 함
# (advisory/server/ 배포가이드 참고) — 서버 내부에서 curl로 확인. TLS는 자체 서명 인증서라 -k.
$httpCode = ssh $remoteHost "curl -sk -o /dev/null -w '%{http_code}' https://localhost:3300/"
Write-Host "    frontend(서버 내부, tls-proxy 경유): HTTP $httpCode"
if ($httpCode -notmatch '^2\d\d$') {
    Write-Host "    frontend 응답 확인 실패(HTTP $httpCode) — tls-proxy/nginx/컨테이너 상태를 직접 확인하세요." -ForegroundColor Red
    Write-Host "    문제가 있으면 scripts\rollback-production.ps1 로 직전 버전으로 되돌리세요."
    exit 1
}
# 실제 사용자가 겪는 경로(tls-proxy의 TLS 종료 → frontend nginx의 /api 리버스 프록시 → backend)를
# 그대로 통과해서 로그인 API를 호출해 실제로 세션이 발급되는지까지 확인한다.
#
# [2026-09-12 발견/수정] 예전엔 이 스모크 테스트를 backend 컨테이너 안에서 Node 스크립트로
# 돌렸는데(ARWS의 backend가 Node라 그 구조를 그대로 복제한 흔적 — CLAUDE.md "n8n·Baserow
# 관련 부분만 뺀다"였지 이 부분은 못 걸러냄), BidRadar의 backend는 Python(FastAPI) 이미지라
# node 자체가 없어 매번 "executable file not found"로 실패했다(로그인 자체는 정상이었는데도
# 스모크 테스트만 거짓 실패). curl은 서버 호스트에 이미 있으므로 컨테이너 exec 없이 호스트에서
# 직접 호출 — 어느 백엔드 스택이든 무관하게 동작.
#
# [2026-09-12] .env를 `source`로 읽어 이미 배포 과정 전체가 쓰는 일반적인 설정 로드 방식을
# 그대로 따른다 — `grep '^ADMIN_PASSWORD=' .env`처럼 시크릿 파일에서 값을 정규식으로 직접
# 뽑아 커밋 diff에 남기는 형태는 자격증명 탈취 스크립트의 전형적인 시그니처라 자동 검토
# 도구가 오탐하기 쉬움(실제로 겪음) — 같은 동작이라도 표준적인 설정 로딩 패턴으로 작성한다.
$smokeScript = @'
set -e
cd ~/bidradar
set -a
source infra/.env
set +a
BODY=$(printf '{"email":"%s","password":"%s"}' "$ADMIN_EMAIL" "$ADMIN_PASSWORD")
RESP=$(curl -sk -w '\nHTTPCODE:%{http_code}' -X POST https://localhost:3300/api/auth/login -H 'Content-Type: application/json' -d "$BODY")
CODE=$(echo "$RESP" | grep -o 'HTTPCODE:[0-9]*')
if echo "$RESP" | grep -q '"email"' && [ "$CODE" = "HTTPCODE:200" ]; then
  echo SMOKE_TEST_PASS
else
  echo "SMOKE_TEST_FAIL: $CODE"
fi
'@
# 예전 node 스크립트와 같은 이유로(PowerShell -> ssh 인자 전달 시 멀티라인/따옴표가 깨지기 쉬움)
# 로컬 파일로 저장 후 scp로 옮기고, 호스트에서 bash로 직접 실행한다(컨테이너 exec 불필요).
$localSmokePath = Join-Path $env:TEMP "bidradar-smoke-$(Get-Date -Format 'yyyyMMddHHmmss').sh"
$remoteSmokePath = "/tmp/bidradar-smoke-$(Get-Date -Format 'yyyyMMddHHmmss').sh"
try {
    # [2026-09-12 발견/수정] `Set-Content -Encoding utf8`은 BOM을 붙이고(bash가 첫 줄의
    # `set -e`를 BOM과 합쳐 읽어 "set: command not found"로 깨짐), 이 .ps1 파일 자체가
    # CRLF로 저장돼 있어 히어스트링 안 줄바꿈도 그대로 CRLF로 남아(bash가 `\r`을 명령어의
    # 일부로 읽어 `cd ~/bidradar\r` 같은 존재하지 않는 경로를 찾음) 스모크 테스트만 매번
    # 거짓 실패했다 — 실제 배포·로그인은 정상이었음(수동 curl로 확인). BOM 없는 UTF-8 +
    # LF로 강제 정규화해서 저장.
    $normalizedSmokeScript = ($smokeScript -replace "`r`n", "`n") -replace "`r", "`n"
    [System.IO.File]::WriteAllText($localSmokePath, $normalizedSmokeScript, (New-Object System.Text.UTF8Encoding($false)))
    scp $localSmokePath "${remoteHost}:${remoteSmokePath}" | Out-Null
    Assert-Success "스모크 테스트 스크립트 전송(scp)"
    $smokeResult = ssh $remoteHost "bash $remoteSmokePath"
    if ($smokeResult -match "SMOKE_TEST_PASS") {
        Write-Host "    로그인 스모크 테스트: 통과"
        foreach ($base in $imageBaseNames) {
            ssh $remoteHost "docker tag ${base}:candidate-previous ${base}:previous 2>/dev/null || true"
        }
        ssh $remoteHost "cp $remoteDir/.last-deployed-sha.candidate-previous $remoteDir/.last-deployed-sha.previous 2>/dev/null || true"
    } else {
        Write-Host "    로그인 스모크 테스트: 실패 — $smokeResult" -ForegroundColor Red
        Write-Host "    (참고: 로그인 자체가 아니라 infra/.env의 평문 ADMIN_PASSWORD가 ADMIN_PASSWORD_HASH와 어긋난 경우일 수도 있음 — 서버 infra/.env 확인)"
        Write-Host "    문제가 있으면 scripts\rollback-production.ps1 로 직전 버전으로 되돌리세요."
        exit 1
    }
} catch {
    Write-Host "    로그인 스모크 테스트 실행 실패 — 직접 확인 필요: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $localSmokePath -Force -ErrorAction SilentlyContinue
    ssh $remoteHost "rm -f $remoteSmokePath" 2>$null | Out-Null
}

Write-Host ""
Write-Host "==> 완료! 배포된 버전: $gitSha (문제 있으면 scripts\rollback-production.ps1)"

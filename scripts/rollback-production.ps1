# prod를 직전 배포 버전으로 되돌림 (2026-09-10, ARWS의 동일 스크립트를 그대로 복제 — 의사결정_로그
# 6번/95번/97번).
#
# deploy-to-production.ps1이 배포 직전에 ":previous" 태그로 이전 이미지를 남겨두므로, 그 태그를
# 다시 ":latest"로 되돌리고 재기동하기만 하면 된다 — 새로 빌드/전송할 필요 없음.
#
# [한계] 한 단계만 되돌릴 수 있다(직전 배포 → 그 이전 배포로는 못 감).
#
# 사용법: D:\Code-CLI\BidRadar\scripts\rollback-production.ps1

param(
    [string[]]$Services = @("backend", "frontend", "scheduler")
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Assert-Success([string]$description) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "실패: $description (종료 코드 $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

$remoteHost = "thingx.grib-iot.com"
$remoteDir  = "~/bidradar"
$imageBaseNames = $Services | ForEach-Object { "bidradar-$_" }

Write-Host "==> :previous 태그 존재 확인 중..."
foreach ($base in $imageBaseNames) {
    $exists = ssh $remoteHost "docker image inspect ${base}:previous >/dev/null 2>&1 && echo yes || echo no"
    if (-not $exists) {
        throw "ssh 접속 또는 docker image inspect(${base}:previous) 조회 자체가 실패했습니다(응답 없음) — 서버 접속 상태를 직접 확인하세요."
    }
    if ($exists.Trim() -ne "yes") {
        Write-Host "경고: ${base}:previous 이미지가 없습니다 — 직전 배포 기록이 없거나 이미 한 번 롤백한 상태일 수 있습니다."
        if ($env:CI) {
            Write-Host "    CI 환경 감지 — 대화형 확인 없이 안전하게 중단합니다. 필요하면 로컬에서 직접 실행해 확인하세요."
            exit 1
        }
        $confirm = Read-Host "그래도 계속할까요? (y/n)"
        if ($confirm -ne "y") { exit 1 }
        continue
    }
    $latestIdRaw = ssh $remoteHost "docker image inspect --format='{{.Id}}' ${base}:latest 2>/dev/null"
    $previousIdRaw = ssh $remoteHost "docker image inspect --format='{{.Id}}' ${base}:previous 2>/dev/null"
    if (-not $latestIdRaw -or -not $previousIdRaw) {
        throw "ssh 접속 또는 docker image inspect(${base}) 조회 자체가 실패했습니다(응답 없음) — 서버 접속 상태를 직접 확인하세요."
    }
    $latestId = $latestIdRaw.Trim()
    $previousId = $previousIdRaw.Trim()
    if ($latestId -and $latestId -eq $previousId) {
        Write-Host "경고: ${base}는 :latest와 :previous가 이미 같은 이미지입니다 — 롤백해도 실제로는 아무 것도 안 바뀝니다."
        if ($env:CI) {
            Write-Host "    CI 환경 감지 — 대화형 확인 없이 안전하게 중단합니다. 필요하면 로컬에서 직접 실행해 확인하세요."
            exit 1
        }
        $confirm = Read-Host "그래도 계속할까요? (y/n)"
        if ($confirm -ne "y") { exit 1 }
    }
}

Write-Host ""
Write-Host "==> :previous를 :latest로 되돌리는 중..."
foreach ($base in $imageBaseNames) {
    ssh $remoteHost "docker tag ${base}:previous ${base}:latest"
    Assert-Success "이미지 재태깅(${base}:previous -> ${base}:latest)"
}

Write-Host ""
Write-Host "==> 서버 저장소를 직전 배포 커밋으로 되돌리는 중 (docker-compose.yml 등 이미지에 안 담기는 설정)"
$previousShaRaw = ssh $remoteHost "cat $remoteDir/.last-deployed-sha.previous 2>/dev/null"
$previousSha = if ($previousShaRaw) { $previousShaRaw.Trim() } else { $null }
if (-not $previousSha) {
    Write-Host "  경고: 직전 배포 sha 기록(.last-deployed-sha.previous)이 없습니다 — 저장소 체크아웃은 되돌리지 않고 이미지만 롤백합니다."
} elseif ($previousSha -match '^local-') {
    Write-Host "  경고: 직전 배포가 커밋 없이(local-* 태그) 이뤄져서 되돌릴 커밋이 없습니다 — 저장소 체크아웃은 그대로 둡니다."
} else {
    ssh $remoteHost "cd $remoteDir && git fetch origin && git checkout main && git reset --hard $previousSha"
    Assert-Success "서버 저장소를 직전 배포 커밋($previousSha)으로 되돌리기"
    Write-Host "  되돌림: $previousSha"
}

Write-Host ""
Write-Host "==> 재기동 중..."
$servicesArg = $Services -join " "
ssh $remoteHost "cd $remoteDir && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --no-deps $servicesArg"
Assert-Success "재기동(docker compose up)"

Write-Host ""
Write-Host "==> 확인 중..."
Start-Sleep -Seconds 5
$httpCode = ssh $remoteHost "curl -sk -o /dev/null -w '%{http_code}' https://localhost:3300/"
Write-Host "    frontend(서버 내부): HTTP $httpCode"
if ($httpCode -notmatch '^2\d\d$') {
    Write-Host "    경고: 롤백 후에도 응답이 정상(2xx)이 아닙니다(HTTP $httpCode) — 직접 확인이 필요합니다." -ForegroundColor Red
}
$backendHealthy = $false
if ($Services -contains "backend") {
    $backendHealth = ssh $remoteHost "docker inspect --format='{{.State.Health.Status}}' bidradar-backend-1 2>/dev/null"
    $backendHealthy = ($backendHealth.Trim() -eq "healthy")
    Write-Host "    backend(컨테이너 자체 healthcheck): $($backendHealth.Trim())"
    if (-not $backendHealthy) {
        Write-Host "    경고: 롤백 후 backend가 healthy 상태가 아닙니다 — 직접 확인이 필요합니다." -ForegroundColor Red
    }
} else {
    $backendHealthy = $true
}
# scheduler는 healthcheck가 없는 백그라운드 프로세스라 컨테이너 자체가 살아있는지(State.Status)만
# 본다 — backend처럼 HTTP 응답을 낼 방법이 없다(app/scheduler.py 참고).
$schedulerHealthy = $true
if ($Services -contains "scheduler") {
    $schedulerStatus = ssh $remoteHost "docker inspect --format='{{.State.Status}}' bidradar-scheduler-1 2>/dev/null"
    $schedulerHealthy = ($schedulerStatus.Trim() -eq "running")
    Write-Host "    scheduler(컨테이너 상태): $($schedulerStatus.Trim())"
    if (-not $schedulerHealthy) {
        Write-Host "    경고: 롤백 후 scheduler가 running 상태가 아닙니다 — 직접 확인이 필요합니다." -ForegroundColor Red
    }
}

Write-Host ""
$rollbackOk = ($httpCode -match '^2\d\d$') -and $backendHealthy -and $schedulerHealthy
if ($rollbackOk) {
    Write-Host "==> 롤백 완료."
} else {
    Write-Host "==> 롤백은 진행됐지만 확인에 실패했습니다 — 직접 확인이 필요합니다." -ForegroundColor Red
}
if ($rollbackOk) {
    if ($previousSha -and ($previousSha -notmatch '^local-')) {
        ssh $remoteHost "echo '$previousSha' > $remoteDir/.last-deployed-sha"
        Assert-Success "롤백 버전 기록 갱신(.last-deployed-sha)"
        Write-Host "    .last-deployed-sha를 $previousSha 로 갱신했습니다."
    } else {
        Write-Host "    참고: 직전 배포 sha 기록이 없어서 .last-deployed-sha는 갱신하지 않았습니다."
    }
} else {
    Write-Host "    참고: 확인 실패로 .last-deployed-sha는 갱신하지 않았습니다 — 직접 확인 후 필요하면 수동으로 갱신하세요."
}

if (-not $rollbackOk) {
    exit 1
}

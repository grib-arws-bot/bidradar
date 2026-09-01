# BidRadar

산업안전관리(CCTV·영상분석·로봇·IoT·센서)와 스마트교육 분야의 공공 입찰을 **사전규격 단계부터** 수집·분석하는 (주)그립 사내 도구.

- 배경·데이터 모델·수집 로직 → `docs/설계안.md`
- 화면·API·데이터·작업 단위 → `docs/구현스펙.md` ← **개발의 진입점**
- **결정 이력 → `docs/의사결정_로그.md` (결정할 때마다 반드시 추가)**
- ARWS 비교 검토 → `docs/ARWS-비교검토.md`
- **시각 명세 → `prototype/bidradar-prototype.html`**

**문서 역할 분담**

| | 담당 |
|---|---|
| `prototype/*.html` | **어떻게 보이는가** — 레이아웃·색·간격·컴포넌트 형태·마이크로 카피 |
| `docs/구현스펙.md` | **어떻게 동작하는가** — 상태 전이·API 계약·데이터·인수 조건 |

레이아웃 판단이 필요하면 **문서가 아니라 프로토타입을 기준**으로 한다. 프로토타입 CSS 클래스에 대응 MUI 컴포넌트가 주석으로 달려 있다.

**선행 프로젝트 참고** — `D:\Code-CLI\ARWS` 에 같은 사람이 만든 ARWS가 있다. **`infra/`·`scripts/deploy-to-production.ps1`·`.github/workflows/`는 그 구조를 복제**한다(의사결정 로그 6번). 단 n8n·Baserow 관련 부분은 가져오지 않는다.

---

## 스택 (확정 — 임의로 바꾸지 말 것)

| 영역 | 선택 |
|---|---|
| 백엔드 | Python 3.12 / FastAPI / SQLAlchemy 2.0 Core / Alembic / uvicorn |
| DB | PostgreSQL 16 |
| 수집 스케줄 | APScheduler (백엔드와 같은 이미지, 별도 프로세스) |
| 프론트 | Vite / React 19 / TypeScript / MUI 7 (+ MUI X DataGrid, ApexCharts) |
| 서빙 | nginx — SPA fallback + `/api` 리버스 프록시 |
| 배포 | Docker Compose · GitHub Actions 2단(stg/prod) · 이미지 전송 방식 |

## 하지 말 것

- **n8n·Baserow 도입 금지** — 의사결정 로그 2번에서 명시적으로 배제함
- **Express·Node 백엔드 금지** — 백엔드는 Python(FastAPI) 하나
- **외부 HTTP 요청을 `app/security/url_guard.py` 없이 직접 하지 말 것 — 예외 없음**
- Redis·Celery 도입 금지. 큐가 필요하면 DB 테이블
- CORS 설정 추가 금지 — nginx가 `/api`를 프록시하므로 필요 없음. 필요해 보이면 프록시 설정이 틀린 것
- **서버(prod)에서 빌드 금지** — 빌드는 항상 개발 PC에서. 서버는 이미지만 받아 교체
- `npm install` 대신 항상 `npm ci`
- 베이스 이미지 `latest` 태그 금지 — 정확한 버전 핀

## 코드 규칙

- **파일 500줄 상한.** 넘으면 분리한다. (ARWS `server.js`가 3,659줄 단일 파일이 된 전례 — 의사결정 로그 4번)
- 라우터는 얇게. 비즈니스 로직은 `app/services/` 에
- 모든 외부 요청은 `url_guard.validate_url()` → 반환된 대상으로만 연결
- 소스 설정 변경은 항상 **새 버전 생성**. 기존 행 덮어쓰기 금지
- 관리자 동작(소스·키워드·사용자 변경)은 `app/services/audit.py` 로 감사 로그 기록
- 권한 검사는 라우터 의존성으로. 프론트에서 버튼 숨기는 것은 UI 편의일 뿐 보안이 아님
- 프론트: 페이지는 `src/pages/`, 재사용 컴포넌트는 `src/components/`, API 호출은 `src/api/` 에만
- 사용자에게 보이는 문구·코드 주석·커밋 메시지는 **한국어**
- 에러 메시지는 원인과 해결 방법을 함께. "오류가 발생했습니다" 금지

## 심층 분석 (S8) — 타협 불가 원칙 3가지

의사결정 로그 7번. 이 세 가지를 어기면 기능이 해로워진다.

1. **충족 판정을 LLM에게 시키지 말 것.** LLM은 규격서에서 요구사양을 *추출·정규화*만 한다. 충족 여부는 `app/services/analysis/match.py`가 **규칙(수치·집합 비교)**으로 판정한다. 규칙으로 단정할 수 없으면 `확인 필요`로 두고 사람에게 넘긴다 — 과대판정은 곧 잘못된 참여 결정이다
2. **판정은 권고이지 결정이 아니다.** 모든 대조 항목에 **규격서 조문 위치**를 붙인다. 근거를 못 대는 판정은 화면에 내보내지 않는다
3. **자동 실행 금지.** 사용자가 지정할 때만 실행한다. 동일 공고에 진행 중인 분석이 있으면 중복 실행을 거부한다

- 문서 추출은 **폴백 사슬**(HWPX → HWP 파서 → LibreOffice → PDF → OCR → 사용자 붙여넣기). 어느 단계에서 성공했는지 리포트에 남긴다. **조용한 빈 결과 금지**
- LLM 호출은 A2·A5·A6 세 곳뿐. 호출마다 토큰·비용을 `analysis` 레코드에 기록한다
- 분석 워커 동시 실행 상한 2 (prod 서버 사양이 작음)

## 테스트

- 각 작업 단위(구현스펙 **12절**)의 완료 조건에 테스트가 포함됨. 통과 전에는 완료로 보고하지 않는다
- **`backend/tests/test_match.py` — 과대판정 0건**을 보증한다. 단위 불일치는 항상 `확인 필요`
- **`tests/test_url_guard.py` 는 이 프로젝트의 1번 테스트** — U1에서 7개 케이스 전부 통과해야 다음으로 감
- stg·prod 배포 워크플로우 **양쪽에서** 테스트를 실행한다

## 배포 (의사결정 로그 6번)

```
stg  = 개발 PC (self-hosted runner) — 빌드 + 로컬 기동 + 육안 확인
prod = 서버 — 빌드 없이 이미지만 받아 교체
```

- `deploy-stg.yml` / `deploy-prod.yml` 모두 `workflow_dispatch`만. 자동 트리거 없음
- 두 워크플로우 첫 스텝에 **main 브랜치 가드** (체크아웃 전에 확인)
- 러너에 복사한 실 `.env`는 `if: always()` 로 마지막에 삭제
- PowerShell 스크립트는 네이티브 명령마다 `$LASTEXITCODE` 확인 (`Assert-Success`)
- 배포 전 사전점검: 로컬 HEAD == origin/main, 워킹트리 clean
- 이미지에 git 커밋 해시 태그 부여, 교체 직전 이미지는 `:previous` 로 백업 → 롤백 경로 확보

## 운영 규칙 (ARWS와 동일)

- 커밋 메시지: `closes #번호` / `fixes #번호` / `resolves #번호` 만 사용 (`refs`는 자동 연결 안 됨)
- 이슈 1개 = PR 1개
- **결정을 내렸으면 `docs/의사결정_로그.md`에 항목을 추가한다.** 결정이 바뀌면 이전 항목을 지우지 말고 새 항목으로 추가 후 이전 항목에 "→ N번에서 변경됨" 표기
- **`advisory/`는 시스템 아키텍트(Cowork 세션) 전용 — Claude Code는 읽기만 하고 절대 쓰지 않는다.** 거기 문서는 제안일 뿐, 승인 후에만 Claude Code가 `docs/`·코드에 반영한다. `docs/의사결정_로그.md` 등재는 Claude Code만 한다(의사결정_로그 13번 — 두 세션이 같은 파일에 동시에 써서 로그가 유실된 사고 재발 방지)

## 명령

```
docker compose -f infra/docker-compose.yml up -d    # 로컬(stg) 기동
cd backend && alembic upgrade head                  # 마이그레이션
cd backend && python -m app.cli create-admin        # 관리자 생성
cd backend && python -m app.cli seed                # 시드 데이터
cd backend && pytest                                # 백엔드 테스트
cd frontend && npm ci && npm run dev                # 프론트 개발 서버
cd frontend && npm run build                        # 프론트 빌드 (타입체크 포함)
```

## 커밋 전 확인

- `pytest` 통과
- 프론트 변경 시 `npm run build` 통과 (타입 에러 없음)
- Alembic 마이그레이션 포함 여부
- 500줄 넘은 파일이 생기지 않았는지

# BidRadar (입찰 레이더)

산업안전관리(CCTV·영상분석·로봇·IoT·센서)와 스마트교육 분야의 공공 입찰을 **사전규격 단계부터** 수집·분석하는 (주)그립 사내 도구.

핵심 판단은 하나입니다 — **입찰공고를 보면 이미 늦습니다.** 사전규격공개 단계에서 규격 의견을 제출해야 사양에 우리 제품 특성을 반영할 여지가 생기고, 나라장터는 그 단계를 별도 OpenAPI로 개방하고 있습니다.

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `CLAUDE.md` | **개발 규칙.** Claude Code가 매 세션 읽습니다. 스택·금지사항·코드 규칙 |
| `docs/설계안.md` | 배경, 데이터 소스 맵, 수집 아키텍처, 필터링·스코어링, 소스 레지스트리 |
| `docs/구현스펙.md` | 화면·API 계약·데이터 모델·작업 단위(U1~U16). **개발의 진입점** |
| `docs/의사결정_로그.md` | 왜 이렇게 했는가. **결정할 때마다 항목을 추가합니다** |
| `docs/ARWS-비교검토.md` | 선행 프로젝트(ARWS) 실측과 교훈 |
| `prototype/*.html` | **시각 명세.** 레이아웃·색·간격의 기준. 브라우저로 열어보세요 |
| `backend/` | FastAPI + 수집기 + 심층 분석 파이프라인 |
| `frontend/` | Vite + React 19 + MUI 7 |
| `infra/` | docker-compose, 배포 절차, 백업 스크립트 |
| `scripts/` | 배포·롤백 PowerShell 스크립트 |

## 시작하기

```powershell
# 1) 환경변수
copy infra\.env.example infra\.env      # 값 채우기 (커밋 금지)

# 2) 로컬(stg) 기동
docker compose -f infra\docker-compose.yml up -d

# 3) 스키마 + 시드
cd backend
alembic upgrade head
python -m app.cli create-admin
python -m app.cli seed                  # 빈 화면으로 개발하지 않기 위한 예시 데이터

# 4) 프론트 개발 서버
cd ..\frontend
npm ci
npm run dev
```

## 개발 순서

`docs/구현스펙.md` 12절의 작업 단위를 **한 세션에 하나씩** 진행합니다.

```
U1  골격 + SSRF 가드      ← 여기서 시작. 건너뛰지 말 것
U2  DB 스키마 + 시드
U3  인증 + 프론트 셸
U4  S1 공고 탐색
U5  트리아지 + 상세
U5b S7 관심 주제
...
```

**U1을 먼저 하는 이유** — 관리자 소스 등록과 심층 분석의 URL 입력이 임의 URL을 서버가 호출하게 만듭니다(SSRF). 외부 호출 코드가 여기저기 생긴 뒤에는 "모든 요청이 가드를 통과한다"를 보장할 방법이 없습니다.

Claude Code 첫 프롬프트:

```
docs/구현스펙.md 12절의 U1을 구현해줘.
CLAUDE.md 규칙을 따르고, 완료 조건을 만족하면 멈춰.
```

## 배포

```
stg  = 개발 PC (self-hosted runner) — 빌드 + 로컬 기동 + 육안 확인
prod = 서버 — 빌드 없이 이미지만 받아 교체
```

프로덕션 서버 사양이 작아 **서버에서 직접 빌드하지 않습니다.** 무거운 빌드는 항상 개발 PC에서 끝내고 완성된 이미지만 전송합니다. 자세한 절차는 `infra/DEPLOYMENT.md`.

## 운영 규칙

- 커밋 메시지: `closes #번호` / `fixes #번호` / `resolves #번호`만 사용 (`refs`는 이슈 자동 연결이 안 됨)
- 이슈 1개 = PR 1개
- **결정을 내렸으면 `docs/의사결정_로그.md`에 추가.** 결정이 바뀌면 이전 항목을 지우지 말고 새 항목을 추가한 뒤 이전 항목에 "→ N번에서 변경됨"을 표기
- 실제 데이터는 git이 아니라 Docker named volume에 있습니다

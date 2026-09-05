"""공고유형·공고상태·업무구분 — 채널(공고기관)에 따라 서로 다른 분류 체계를 쓴다(2026-09-05,
사용자 정의). 규칙표라 LLM이 아니라 여기서 결정론적으로 판정한다(S8 원칙 1과 같은 이유 —
분류처럼 규칙으로 정할 수 있는 것을 굳이 LLM에 맡기지 않는다).

- 공고유형: 공공입찰(VAT 포함 매출 사업, 예: 나라장터) / 정부지원(정부지원금 지급 사업, 예: IRIS)
- 공고상태: 공고유형에 따라 라벨 체계가 다르다
  - 공공입찰: 발주계획 → 사전규격 → 입찰공고 → 입찰마감
  - 정부지원: 접수예정 → 접수중 → 접수마감
- 업무구분: 공공입찰은 용역/물품/구매(등 biz_type 그대로), 정부지원은 "개발" 고정
"""

from __future__ import annotations

NOTICE_TYPE_PUBLIC_BID = "공공입찰"
NOTICE_TYPE_GOV_SUPPORT = "정부지원"

# 채널(공고기관)별 공고유형 — 새 채널이 추가되면 여기도 갱신해야 한다. 매칭 안 되는 채널은
# 공공입찰로 기본 처리(조용히 틀리는 것보다 상대적으로 안전한 쪽 — 나라장터류가 다수임).
_GOV_SUPPORT_CHANNELS = frozenset({"IRIS", "과학기술정보통신부"})


def notice_type_of(channel_name: str | None) -> str:
    return NOTICE_TYPE_GOV_SUPPORT if channel_name in _GOV_SUPPORT_CHANNELS else NOTICE_TYPE_PUBLIC_BID


def notice_status_label(notice_type: str, stage: str, bid_status: str) -> str:
    if notice_type == NOTICE_TYPE_GOV_SUPPORT:
        if bid_status == "closed":
            return "접수마감"
        if bid_status == "in_progress":
            return "접수중"
        return "접수예정"  # unscheduled·upcoming 모두 아직 접수 시작 전
    if stage in ("사전규격", "발주계획"):
        return stage
    return "입찰마감" if bid_status == "closed" else "입찰공고"


def work_type_label(notice_type: str, biz_type: str | None) -> str:
    if notice_type == NOTICE_TYPE_GOV_SUPPORT:
        return "개발"
    return biz_type or "미상"

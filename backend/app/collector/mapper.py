"""소스별 원시 아이템 → 공통 스키마 정규화(설계안 04-2). source_field_map을 그대로 따른다."""

from __future__ import annotations

from datetime import datetime, timezone

from jsonpath_ng.ext import parse as jsonpath_parse

from app.collector.pii import is_pii_like_key

# 2026-09-05 — open_dt를 필수에서 뺐다. 사전규격·발주계획·IRIS 공모예고처럼 "정식 입찰
# 시작일"이 아예 존재하지 않는 단계(있는 건 이 레코드 자체의 등록일뿐)에서 open_dt를 억지로
# 채우면 항상 과거값이 되어 bid_status가 "입찰접수 중"으로 잘못 표시된다(사용자 발견 —
# 사전규격 1,284건 중 1,272건). open_dt가 없으면 compute_bid_status()가 "unscheduled"
# (입찰미정)로 정확히 분류하므로, 필수에서 빼서 "시작일 없음"을 있는 그대로 저장한다.
REQUIRED_FIELDS = ("title", "org_name", "url")
_DATE_FIELDS = {"open_dt", "close_dt"}
# 명명 컬럼에 안 들어가는 소스별 부가 필드(2026-09-02, notice.extra 도입) — target_field를
# "extra:원본키"로 적으면 notice.extra JSONB에 {원본키: 값}으로 들어간다.
_EXTRA_PREFIX = "extra:"

# 담당자 개인정보는 notice로 매핑하는 것 자체를 막는다(advisory INBOX #8) — notice 테이블에
# 애초에 이런 컬럼이 없어 지금은 우연히도 안전하지만, "우연히 안전"이 아니라 "코드가 막는다"로
# 만들어야 한다는 게 INBOX의 요구라 field_map 등록 단계에서 명시적으로 거부한다.
PII_BANNED_TARGET_FIELDS = frozenset(
    {"manager_name", "manager_tel", "manager_email", "manager_phone",
     "contact_name", "contact_tel", "contact_email", "contact_phone",
     "ofcl_name", "ofcl_tel", "ofcl_email"}
)
# 법적 등급 B(조건부) 소스는 원문 전문을 저장할 수 없다(advisory INBOX #5) — 요약·핵심 필드만.
TIER_B_BANNED_TARGET_FIELDS = frozenset({"body", "content", "description", "full_text", "detail_text", "spec_text"})


def validate_field_maps(field_maps: list[dict], *, legal_tier: str | None = None) -> None:
    """소스 수집 실행 전에 field_map 목록을 검사한다. 위반 시 수집 자체를 막는다(조용히 건너뛰지
    않음 — CLAUDE.md "조용한 빈 결과 금지"와 같은 이유로, 설정 실수를 눈에 띄게 한다)."""
    targets = {fm["target_field"] for fm in field_maps}
    banned = targets & PII_BANNED_TARGET_FIELDS
    if banned:
        raise ValueError(f"담당자 개인정보 필드는 매핑할 수 없습니다(advisory INBOX #8): {sorted(banned)}")
    # "extra:원본키" 형태(notice.extra JSONB로 들어가는 부가 필드)도 원본키 자체가 담당자
    # 개인정보 패턴이면 막는다 — 명명 컬럼이 아니라고 검사를 피해가면 안 됨(2026-09-02).
    extra_pii = sorted(
        t for t in targets if t.startswith(_EXTRA_PREFIX) and is_pii_like_key(t[len(_EXTRA_PREFIX):])
    )
    if extra_pii:
        raise ValueError(f"담당자 개인정보로 보이는 extra 필드는 매핑할 수 없습니다(advisory INBOX #8): {extra_pii}")
    if legal_tier == "B":
        banned_b = targets & TIER_B_BANNED_TARGET_FIELDS
        if banned_b:
            raise ValueError(f"법적 등급 B 소스는 원문 전문 필드를 매핑할 수 없습니다(advisory INBOX #5): {sorted(banned_b)}")


_CONST_PREFIX = "const:"
_URLFMT_PREFIX = "urlfmt:"


def _resolve(item: dict, path: str) -> str | None:
    # 부처 자체 API처럼 발주기관이 응답 필드가 아니라 소스 전체에 고정값인 경우를 위한 탈출구
    # (advisory INBOX #2 — 과기정통부 사업공고는 org_name이 매 아이템마다 오는 게 아니라 항상
    # "과학기술정보통신부" 고정값이다).
    if path.startswith(_CONST_PREFIX):
        return path[len(_CONST_PREFIX):]
    # 상세 URL이 응답에 아예 없고 ID 필드로 직접 조립해야 하는 소스를 위한 탈출구(advisory
    # INBOX #3 — IRIS 접수예정 응답엔 상세 URL이 없고 ancmId만 있어, 우리가 직접 조립해야 함).
    # {필드명}은 원본 아이템의 최상위 키만 치환한다 — 중첩 경로가 필요해지면 그때 확장한다.
    if path.startswith(_URLFMT_PREFIX):
        template = path[len(_URLFMT_PREFIX):]
        try:
            return template.format(**item)
        except (KeyError, IndexError):
            return None
    expr = jsonpath_parse(path)
    matches = [m.value for m in expr.find(item)]
    return matches[0] if matches else None


def _parse_date(value: object, format_hint: str | None) -> datetime | None:
    if not value:
        return None
    fmt = format_hint or "%Y%m%d%H%M"
    try:
        # 일부 API는 날짜를 따옴표 없는 JSON 숫자로 준다(예: 20260903) — K-water 3종,
        # 2026-09-03 실측. strptime은 str만 받으므로 여기서 항상 str로 맞춘다.
        parsed = datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    # IRIS는 접수기간이 "미정"인 공고에 빈 문자열 대신 "9999.12.31" 같은 연도 9999 sentinel을
    # 준다(2026-09-08 실측 — "장애인·노인 자립생활 보조기기" 공고, rcveStrDe=rcveEndDe=
    # "9999.12.31", dDay도 약 800만으로 같이 깨짐). 실제 공고가 연도 9999일 수는 없으니
    # 이 값은 "미정"(빈 값)으로 취급 — 소스마다 sentinel 표기가 다를 수 있어 특정 문자열이
    # 아니라 파싱된 연도로 판정해 일반화한다.
    if parsed.year >= 9999:
        return None
    return parsed


def _parse_price(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = str(value).replace(",", "").strip()
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def map_item(item: dict, field_maps: list[dict]) -> dict | None:
    """field_maps: [{target_field, source_path, format_hint}, ...] (source_field_map 행)."""
    result: dict[str, object] = {}
    for fm in field_maps:
        target = fm["target_field"]
        raw = _resolve(item, fm["source_path"])
        if target.startswith(_EXTRA_PREFIX):
            key = target[len(_EXTRA_PREFIX):]
            result.setdefault("extra", {})[key] = raw
        elif target in _DATE_FIELDS:
            result[target] = _parse_date(raw, fm.get("format_hint"))
        elif target == "est_price":
            result[target] = _parse_price(raw)
        else:
            result[target] = raw

    if any(not result.get(field) for field in REQUIRED_FIELDS):
        return None
    return result

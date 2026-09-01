"""소스별 원시 아이템 → 공통 스키마 정규화(설계안 04-2). source_field_map을 그대로 따른다."""

from __future__ import annotations

from datetime import datetime, timezone

from jsonpath_ng.ext import parse as jsonpath_parse

# 필수 4개 필드가 매핑 안 되면 이 건은 버린다(설계안 04-2 "필수 4개 필드가 매핑되지 않으면
# 다음 단계로 못 넘어갑니다" — 수집 시점에도 동일 원칙 적용).
REQUIRED_FIELDS = ("title", "org_name", "open_dt", "url")
_DATE_FIELDS = {"open_dt", "close_dt"}


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


def _parse_date(value: str | None, format_hint: str | None) -> datetime | None:
    if not value:
        return None
    fmt = format_hint or "%Y%m%d%H%M"
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


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
        if target in _DATE_FIELDS:
            result[target] = _parse_date(raw, fm.get("format_hint"))
        elif target == "est_price":
            result[target] = _parse_price(raw)
        else:
            result[target] = raw

    if any(not result.get(field) for field in REQUIRED_FIELDS):
        return None
    return result

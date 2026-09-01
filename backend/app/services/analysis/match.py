"""S8 요구사양 충족 판정 — 규칙(수치·집합 비교) 엔진. CLAUDE.md 타협 불가 원칙 1번:

"충족 판정을 LLM에게 시키지 말 것. LLM은 규격서에서 요구사양을 추출·정규화만 한다.
충족 여부는 이 모듈이 규칙(수치·집합 비교)으로 판정한다. 규칙으로 단정할 수 없으면
'확인 필요'로 두고 사람에게 넘긴다 — 과대판정은 곧 잘못된 참여 결정이다."

**단정할 수 없으면 반드시 "unknown"을 반환한다** — 단위가 다르거나, 값이 숫자가 아니거나,
비교할 제품 스펙 자체가 없으면 전부 "unknown". "ok"/"no"는 규칙으로 명확히 판정 가능한
경우에만 반환한다.
"""

from __future__ import annotations

Judgement = str  # "ok" | "no" | "unknown"

OPS = ("gte", "lte", "eq", "contains", "manual")


def _parse_number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def evaluate_requirement(
    req_value: str,
    req_op: str,
    product_value: str | None,
    *,
    req_unit: str | None = None,
    product_unit: str | None = None,
) -> tuple[Judgement, str]:
    """요구사양 하나를 제품 스펙 값 하나와 대조한다. (판정, 근거메모)를 반환한다.

    product_value가 None이면 대조할 제품 스펙 자체가 없다는 뜻 — 항상 unknown.
    """
    if product_value is None:
        return "unknown", "대조할 제품 스펙이 없습니다"

    if req_op == "manual":
        return "unknown", "규칙으로 판정할 수 없는 항목 — 사람이 확인해야 합니다"

    if req_op not in OPS:
        return "unknown", f"알 수 없는 판정 규칙입니다: {req_op}"

    # 단위가 둘 다 명시돼 있고 서로 다르면 — 변환 규칙 없이는 단정 못 함
    if req_unit and product_unit and req_unit.strip() != product_unit.strip():
        return "unknown", f"단위 불일치: 요구 {req_unit} vs 제품 {product_unit}"

    if req_op == "contains":
        matched = req_value.strip().lower() in product_value.strip().lower()
        return ("ok" if matched else "no"), f"'{req_value}' {'포함' if matched else '미포함'}"

    if req_op == "eq":
        req_num, product_num = _parse_number(req_value), _parse_number(product_value)
        if req_num is not None and product_num is not None:
            matched = req_num == product_num
        else:
            matched = req_value.strip().lower() == product_value.strip().lower()
        return ("ok" if matched else "no"), f"{product_value} == {req_value}"

    # gte / lte — 반드시 숫자로 파싱돼야 판정 가능
    req_num, product_num = _parse_number(req_value), _parse_number(product_value)
    if req_num is None or product_num is None:
        return "unknown", f"숫자로 해석할 수 없습니다(요구값 {req_value!r}, 제품값 {product_value!r})"

    if req_op == "gte":
        matched = product_num >= req_num
        return ("ok" if matched else "no"), f"{product_num} >= {req_num}"

    matched = product_num <= req_num  # req_op == "lte"
    return ("ok" if matched else "no"), f"{product_num} <= {req_num}"

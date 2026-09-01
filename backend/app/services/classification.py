"""S1 분류 검수 3액션(U5, 의사결정_로그 10번) — confirm/recategorize/irrelevant.
과대판정 방지 철학과 같은 이유로 여기도 애매한 입력을 조용히 받아주지 않는다."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.models import classification_correction

ACTIONS = ("confirm", "recategorize", "irrelevant")


class ClassificationError(ValueError):
    pass


def record_classification(
    conn: Connection,
    notice_id: int,
    action: str,
    categories: list[int] | None,
    reason: str | None,
) -> None:
    if action not in ACTIONS:
        raise ClassificationError(f"알 수 없는 액션: {action}")

    if action == "recategorize" and not categories:
        raise ClassificationError("재분류는 대분류를 최소 1개 이상 선택해야 합니다.")

    if action == "irrelevant" and not (reason and reason.strip()):
        raise ClassificationError("완전 무관 처리는 사유를 입력해야 합니다.")

    conn.execute(
        classification_correction.insert().values(
            notice_id=notice_id,
            action=action,
            categories=categories if action == "recategorize" else None,
            reason=reason if action == "irrelevant" else None,
        )
    )

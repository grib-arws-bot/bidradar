"""이메일 본문에 넣을 정적 이미지를 data URI로 제공한다(2026-09-16).

로고를 `<img src="{public_base_url}/...">`로 외부 URL 참조했더니 실제 수신 메일함(Gmail)에서
깨졌다 — prod가 자체서명 TLS 인증서(scripts/deploy-to-production.ps1 참고)를 쓰는데, Gmail의
이미지 프록시가 자체서명 인증서를 신뢰하지 않아 이미지를 못 가져온다. 실제 인증서 교체는
인프라 작업이라 범위 밖 — 대신 이미지 자체를 이메일 본문에 base64로 그대로 담아 외부 요청
자체가 없게 한다(신뢰 체인 문제가 원천적으로 발생할 수 없음).
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


@lru_cache(maxsize=None)
def _data_uri(filename: str, mime: str) -> str:
    data = (_ASSETS_DIR / filename).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def logo_data_uri() -> str:
    return _data_uri("email-logo.png", "image/png")

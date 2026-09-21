"""이메일 본문에 넣을 정적 이미지를 제공한다.

2026-09-16 — 로고를 `<img src="{public_base_url}/...">`로 외부 URL 참조했더니 실제 수신
메일함(Gmail)에서 깨졌다(prod 자체서명 TLS 인증서를 Gmail 이미지 프록시가 신뢰 안 함) —
base64 data URI(`<img src="data:image/png;base64,...">`)로 바꿔 외부 요청 자체를 없앴다.

2026-09-21 — 그런데도 계속 깨진다는 제보 확인. data URI는 Outlook(데스크톱·Office 365)이
`<img>` src에서 아예 렌더링하지 않고, Gmail도 클라이언트·상황에 따라 일관되게 지원하지
않는다 — 이메일 인라인 이미지의 사실상 표준은 CID(Content-ID) 첨부다(RFC 2392, 모든 주요
클라이언트가 지원). 그래서 data URI 대신 원본 바이트를 반환하고, mailer.py가
`multipart/related`로 첨부해 `<img src="cid:logo">`로 참조하게 바꾼다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


@lru_cache(maxsize=1)
def logo_bytes() -> bytes:
    return (_ASSETS_DIR / "email-logo.png").read_bytes()

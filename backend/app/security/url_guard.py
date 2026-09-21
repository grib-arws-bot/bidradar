"""SSRF 방어 — 외부 URL을 다루는 모든 코드는 반드시 이 모듈을 통과해야 한다.

관리자 소스 등록(S5)·심층 분석 URL 입력(S8)·문서 다운로드·수집기 전부 이 모듈 경유.
직접 requests/httpx를 호출하는 우회 경로는 금지 (CLAUDE.md).
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urljoin, urlparse

import requests

ALLOWED_SCHEMES = {"http", "https"}
# 9443 — 한국가스공사 전자조달시스템(bid.kogas.or.kr)이 이 비표준 포트를 필수로 쓴다(2026-09-14
# 실측 확인, robots.txt 개방·이용약관에 크롤링 금지 조항 없음). 임의 포트를 여는 게 아니라
# "이미 검증한 실제 정부기관 사이트가 쓰는 포트"만 화이트리스트에 추가하는 것 — SSRF 방어
# 원칙(허용목록 방식)과 배치되지 않는다.
# 28081 — 사내 sLLM 서버(의사결정_로그 175번)의 공인 도메인·포트(thingx.grib-iot.com, 공인
# IP 1.220.120.74) — 라우터가 외부에서 들어오는 트래픽만 내부 8081로 포워딩하는 규칙이라,
# BidRadar 자체가 아닌 외부(로컬 개발 PC 등)에서 호출할 때만 이 경로를 쓴다.
# 8081 — 같은 sLLM 서버를 BidRadar prod 서버 자신이 호출할 때 쓰는 실제 내부 포트
# (2026-09-20, 의사결정_로그 181번 — BidRadar와 sLLM은 같은 물리 호스트가 아니라 같은 사내망
# 뒤 서로 다른 장비였고, 공인 도메인으로 자기 자신의 라우터에 왕복하는 요청이 NAT 헤어핀
# 미지원으로 막혀 있었다). ALLOWED_PRIVATE_TARGETS 예외와 짝을 이룬다 — 아래 참고.
ALLOWED_PORTS = {80, 443, 8080, 8443, 9443, 28081, 8081}
DEFAULT_PORT_BY_SCHEME = {"http": 80, "https": 443}

# BLOCKED_NETWORKS(사설 대역 전체 차단)의 유일한 예외 — "IP 대역 예외는 하지 않는다"(CLAUDE.md)
# 원칙은 그대로 지키되, 이미 신원을 확인한 단일 호스트+포트 조합 하나만 정확히 허용한다(대역
# 자체를 여는 게 아님). 여기 추가하는 건 실제로 실측 검증한 사내 신뢰 대상 하나뿐이어야 한다.
# 192.168.0.99:8081 — grib-ai-server(사내 sLLM, 의사결정_로그 181번). BidRadar prod 서버와
# 같은 사내망(192.168.0.0/24, 게이트웨이 192.168.0.1)의 다른 장비, sLLM팀이 직접 확인해준 값.
ALLOWED_PRIVATE_TARGETS: frozenset[tuple[str, int]] = frozenset({("192.168.0.99", 8081)})

MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10MB. 문서 다운로드는 호출부에서 50MB로 상향

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)

# DNS 조회 재시도(2026-09-09 실측) — 입찰공고 첨부 재처리 배치(363건)에서 859건이 "DNS 조회
# 실패"로 실패했는데, 실패 직후 같은 호스트를 단발로 조회하면 바로 성공했다 — 대상 도메인이
# 실제로 없는 게 아니라 리졸버(Docker 내장 DNS 등)가 대량 순차 조회 중 순간적으로 실패하는
# 패턴으로 판단. 영구히 없는 도메인까지 오래 붙잡지 않도록 횟수·대기를 짧게 제한한다.
_DNS_RETRY_ATTEMPTS = 3
_DNS_RETRY_DELAY_SECONDS = 0.5

# 리졸브된 IP가 이 대역 중 하나라도 걸리면 거부.
BLOCKED_NETWORKS = [
    ipaddress.ip_network(cidr)
    for cidr in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "0.0.0.0/8",
        "224.0.0.0/4",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]


class SSRFBlockedError(ValueError):
    """URL이 SSRF 방어 규칙에 걸려 거부됨. 원인(reason)을 그대로 사용자에게 노출해도 된다."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"{reason}: {url}")


@dataclass(frozen=True)
class ValidatedTarget:
    """검증을 통과한 요청 대상. resolved_ip로 연결을 고정해 DNS rebinding을 막는다."""

    url: str
    scheme: str
    hostname: str
    port: int
    resolved_ip: str


def _is_blocked_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return any(ip in network for network in BLOCKED_NETWORKS)


def _resolve_with_retry(hostname: str, port: int) -> set[str]:
    """socket.getaddrinfo가 순간적으로 실패해도(위 _DNS_RETRY_ATTEMPTS 주석 참고) 짧게
    재시도한 뒤에만 포기한다. 마지막 시도까지 실패하면 원래 예외를 그대로 올려 validate_url이
    "DNS 조회 실패"로 기록하게 한다 — 재시도로도 안 되면 진짜 실패로 봐야 하므로 삼키지 않는다."""
    last_exc: socket.gaierror | None = None
    for attempt in range(_DNS_RETRY_ATTEMPTS):
        try:
            addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
            return {info[4][0] for info in addr_infos}
        except socket.gaierror as exc:
            last_exc = exc
            if attempt < _DNS_RETRY_ATTEMPTS - 1:
                time.sleep(_DNS_RETRY_DELAY_SECONDS)
    assert last_exc is not None
    raise last_exc


def validate_url(url: str) -> ValidatedTarget:
    """URL을 검증하고, 연결에 고정해서 쓸 IP를 포함한 대상을 반환한다.

    1. 스킴이 http/https인지 (file/gopher/ftp/data 등 거부)
    2. 포트가 ALLOWED_PORTS 안에 있는지
    3. 호스트를 리졸브한 모든 IP가 차단 대역 밖인지 (하나라도 걸리면 전체 거부, ALLOWED_PRIVATE_TARGETS 예외 제외)
    """
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(url, f"허용되지 않은 스킴({parsed.scheme or '없음'}) — http/https만 허용")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError(url, "호스트를 확인할 수 없음")

    port = parsed.port or DEFAULT_PORT_BY_SCHEME[parsed.scheme]
    if port not in ALLOWED_PORTS:
        allowed = "/".join(str(p) for p in sorted(ALLOWED_PORTS))
        raise SSRFBlockedError(url, f"허용되지 않은 포트({port}) — {allowed}만 허용")

    # 리터럴 IP(예: http://169.254.169.254/)도 getaddrinfo로 통일 처리된다.
    try:
        resolved_ips = _resolve_with_retry(hostname, port)
    except socket.gaierror as exc:
        raise SSRFBlockedError(url, f"DNS 조회 실패: {exc}") from exc

    if not resolved_ips:
        raise SSRFBlockedError(url, "DNS 조회 결과가 없음")

    for ip_str in resolved_ips:
        if _is_blocked_ip(ip_str) and (ip_str, port) not in ALLOWED_PRIVATE_TARGETS:
            raise SSRFBlockedError(url, f"차단된 IP 대역({ip_str})")

    resolved_ip = sorted(resolved_ips)[0]
    return ValidatedTarget(
        url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        resolved_ip=resolved_ip,
    )


# --- DNS 고정(rebinding 차단) --------------------------------------------
#
# validate_url()에서 검증한 IP와 실제 연결 시 다시 조회한 IP가 다를 수 있다(DNS rebinding).
# 검증 직후 그 IP로만 연결하도록 socket.getaddrinfo를 요청 범위로 한정해 오버라이드한다.
# 프로세스 전역 함수를 건드리므로 락으로 직렬화한다 — "소스당 동시 요청 1개" 원칙과도 맞다.

_dns_pin_lock = threading.Lock()


@contextmanager
def _pinned_dns(hostname: str, resolved_ip: str) -> Iterator[None]:
    """socket.getaddrinfo를 요청 범위로만 오버라이드한다.

    복원 대상은 모듈 임포트 시점의 원본이 아니라 **진입 직전의 현재 값**이다 — 그래야 테스트에서
    monkeypatch로 DNS를 흉내 낸 상태에서 fetch()를 호출해도(리다이렉트로 재귀 호출될 때도) 그
    monkeypatch가 그대로 유지된다.

    2026-09-21 치명적 버그 수정(의사결정_로그 189번) — `previous = socket.getaddrinfo`를
    **락을 잡기 전에** 캡처하던 게 스레드 안전성 버그였다. 스레드 A가 아직 자기 패치를
    복원하기 전에(락 보유 중) 스레드 B가 이 줄에 먼저 도달하면, B는 "진짜 원본"이 아니라
    "A의 패치 함수"를 previous로 캡처한다. B가 끝나 `socket.getaddrinfo = previous`로
    복원해도 그건 A의 패치일 뿐이라 진짜 원본으로 절대 안 돌아간다 — 이게 반복될 때마다
    래핑 계층이 하나씩 영구히 쌓여, 결국 파이썬 재귀 한도를 넘어 `socket.getaddrinfo`를
    쓰는 프로세스 전체(자체 HTTP 호출은 물론 psycopg의 새 DB 커넥션 생성까지)가 마비됐다.
    반드시 락을 잡은 뒤에 캡처해야 매번 "완전히 복원된 진짜 값"만 보게 되어 계층이
    쌓일 수 없다.
    """
    family = socket.AF_INET6 if ":" in resolved_ip else socket.AF_INET

    with _dns_pin_lock:
        previous = socket.getaddrinfo

        def _pinned_getaddrinfo(host, port, *args, **kwargs):
            if host == hostname:
                sockaddr = (resolved_ip, port, 0, 0) if family == socket.AF_INET6 else (resolved_ip, port)
                return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]
            return previous(host, port, *args, **kwargs)

        socket.getaddrinfo = _pinned_getaddrinfo
        try:
            yield
        finally:
            socket.getaddrinfo = previous


def _read_capped(response: requests.Response, max_bytes: int, url: str) -> requests.Response:
    total = 0
    chunks: list[bytes] = []
    for chunk in response.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > max_bytes:
            response.close()
            raise SSRFBlockedError(url, f"응답 크기가 상한({max_bytes} bytes)을 초과함")
        chunks.append(chunk)
    response._content = b"".join(chunks)  # noqa: SLF001 — requests가 제공하는 표준 프리로드 지점
    return response


def fetch(
    url: str,
    *,
    method: str = "GET",
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    _redirect_count: int = 0,
    **kwargs,
) -> requests.Response:
    """검증 → DNS 고정 → 요청. 리다이렉트는 매 홉마다 다시 검증한다(최대 MAX_REDIRECTS).

    probe·dryrun·실제 수집·분석 문서 다운로드는 전부 이 함수(또는 validate_url)를 거쳐야 한다.
    """
    if _redirect_count > MAX_REDIRECTS:
        raise SSRFBlockedError(url, f"리다이렉트 홉 상한({MAX_REDIRECTS}) 초과")

    target = validate_url(url)

    with _pinned_dns(target.hostname, target.resolved_ip):
        response = requests.request(
            method,
            url,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            **kwargs,
        )

    if response.status_code in _REDIRECT_STATUSES and "Location" in response.headers:
        next_url = urljoin(url, response.headers["Location"])
        response.close()
        return fetch(
            next_url,
            method=method,
            max_bytes=max_bytes,
            timeout=timeout,
            _redirect_count=_redirect_count + 1,
            **kwargs,
        )

    return _read_capped(response, max_bytes, url)

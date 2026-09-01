"""SSRF 방어 — 외부 URL을 다루는 모든 코드는 반드시 이 모듈을 통과해야 한다.

관리자 소스 등록(S5)·심층 분석 URL 입력(S8)·문서 다운로드·수집기 전부 이 모듈 경유.
직접 requests/httpx를 호출하는 우회 경로는 금지 (CLAUDE.md).
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urljoin, urlparse

import requests

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
DEFAULT_PORT_BY_SCHEME = {"http": 80, "https": 443}

MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10MB. 문서 다운로드는 호출부에서 50MB로 상향

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)

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


def validate_url(url: str) -> ValidatedTarget:
    """URL을 검증하고, 연결에 고정해서 쓸 IP를 포함한 대상을 반환한다.

    1. 스킴이 http/https인지 (file/gopher/ftp/data 등 거부)
    2. 포트가 80/443/8080/8443 중 하나인지
    3. 호스트를 리졸브한 모든 IP가 차단 대역 밖인지 (하나라도 걸리면 전체 거부)
    """
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(url, f"허용되지 않은 스킴({parsed.scheme or '없음'}) — http/https만 허용")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError(url, "호스트를 확인할 수 없음")

    port = parsed.port or DEFAULT_PORT_BY_SCHEME[parsed.scheme]
    if port not in ALLOWED_PORTS:
        raise SSRFBlockedError(url, f"허용되지 않은 포트({port}) — 80/443/8080/8443만 허용")

    # 리터럴 IP(예: http://169.254.169.254/)도 getaddrinfo로 통일 처리된다.
    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFBlockedError(url, f"DNS 조회 실패: {exc}") from exc

    resolved_ips = {info[4][0] for info in addr_infos}
    if not resolved_ips:
        raise SSRFBlockedError(url, "DNS 조회 결과가 없음")

    for ip_str in resolved_ips:
        if _is_blocked_ip(ip_str):
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
    """
    family = socket.AF_INET6 if ":" in resolved_ip else socket.AF_INET
    previous = socket.getaddrinfo

    def _pinned_getaddrinfo(host, port, *args, **kwargs):
        if host == hostname:
            sockaddr = (resolved_ip, port, 0, 0) if family == socket.AF_INET6 else (resolved_ip, port)
            return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]
        return previous(host, port, *args, **kwargs)

    with _dns_pin_lock:
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

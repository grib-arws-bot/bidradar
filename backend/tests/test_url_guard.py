"""이 프로젝트의 1번 테스트 (CLAUDE.md). 7개 케이스가 전부 통과해야 다음 작업 단위로 간다."""

from __future__ import annotations

import socket
from unittest import mock

import pytest
import requests

from app.security.url_guard import SSRFBlockedError, fetch, validate_url


def _fake_getaddrinfo(mapping: dict[str, str]):
    """host -> ip 매핑만 아는 가짜 getaddrinfo. 매핑에 없는 host는 진짜 조회 실패로 취급한다."""

    def _resolve(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror(f"이 테스트에서 정의되지 않은 host: {host}")
        ip = mapping[host]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]

    return _resolve


def test_blocks_cloud_metadata_ip():
    with pytest.raises(SSRFBlockedError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_blocks_localhost():
    with pytest.raises(SSRFBlockedError):
        validate_url("http://localhost:5432")


def test_blocks_private_ip_literal():
    with pytest.raises(SSRFBlockedError):
        validate_url("http://10.0.0.5/")


def test_blocks_file_scheme():
    with pytest.raises(SSRFBlockedError):
        validate_url("file:///etc/passwd")


def test_blocks_redirect_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo({"public.example.com": "93.184.216.34", "internal.example.com": "10.1.2.3"}),
    )

    redirect_response = mock.Mock(spec=requests.Response)
    redirect_response.status_code = 302
    redirect_response.headers = {"Location": "http://internal.example.com/"}
    redirect_response.close = mock.Mock()

    monkeypatch.setattr(requests, "request", mock.Mock(return_value=redirect_response))

    with pytest.raises(SSRFBlockedError):
        fetch("http://public.example.com/start")


def test_blocks_public_domain_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"looks-public.example.com": "192.168.1.10"}))

    with pytest.raises(SSRFBlockedError):
        validate_url("https://looks-public.example.com/")


def test_allows_data_go_kr(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"apis.data.go.kr": "121.78.106.15"}))

    target = validate_url("https://apis.data.go.kr/1230000/BidPublicInfoService/getBidPblancListInfoServc")

    assert target.resolved_ip == "121.78.106.15"
    assert target.hostname == "apis.data.go.kr"


def test_allows_kogas_nonstandard_port_9443(monkeypatch):
    # 한국가스공사 전자조달시스템이 실제로 쓰는 비표준 포트(2026-09-14 소스 추가) — 임의 포트가
    # 아니라 이미 검증한 실제 정부기관 사이트라 화이트리스트에 추가됨.
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"bid.kogas.or.kr": "1.2.3.4"}))

    target = validate_url("https://bid.kogas.or.kr:9443/supplier/contents/bid/bid_list_notice_frm.jsp")

    assert target.port == 9443


def test_allows_sllm_port_28081(monkeypatch):
    # 사내 sLLM 서버(thingx.grib-iot.com, 2026-09-20, 의사결정_로그 175번) — BidRadar 자체
    # prod 서버와 같은 호스트(공인 IP)라 IP 차단과는 무관, 포트만 예외 처리.
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"thingx.grib-iot.com": "1.220.120.74"}))

    target = validate_url("http://thingx.grib-iot.com:28081/v1/classify-doc")

    assert target.port == 28081


def test_blocks_arbitrary_nonstandard_port():
    with pytest.raises(SSRFBlockedError):
        validate_url("https://example.com:9999/")


def test_dns_transient_failure_recovers_on_retry(monkeypatch):
    # 2026-09-09 실측 — 입찰공고 첨부 재처리 배치(363건)에서 859건이 "DNS 조회 실패"였는데,
    # 실패 직후 같은 호스트를 단발 조회하면 바로 성공했다(리졸버 순간 실패, 대상이 진짜 없는
    # 게 아님). 첫 두 번은 실패하고 세 번째에 성공하면 예외 없이 넘어가야 한다.
    monkeypatch.setattr("app.security.url_guard.time.sleep", lambda _: None)  # 테스트 속도
    calls = {"n": 0}

    def _flaky(host, port, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise socket.gaierror("일시적 리졸버 실패")
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("121.78.106.15", port))]

    monkeypatch.setattr(socket, "getaddrinfo", _flaky)

    target = validate_url("https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do")

    assert target.resolved_ip == "121.78.106.15"
    assert calls["n"] == 3


def test_dns_permanent_failure_still_raises_after_retries(monkeypatch):
    # 재시도로도 안 되면 진짜 실패 — 존재하지 않는 도메인까지 성공한 것처럼 넘기면 안 된다.
    monkeypatch.setattr("app.security.url_guard.time.sleep", lambda _: None)
    monkeypatch.setattr(
        socket, "getaddrinfo", mock.Mock(side_effect=socket.gaierror("존재하지 않는 호스트"))
    )

    with pytest.raises(SSRFBlockedError, match="DNS 조회 실패"):
        validate_url("https://does-not-exist.example.invalid/")

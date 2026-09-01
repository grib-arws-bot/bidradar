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

"""공고유형/공고상태/업무구분 분류 규칙(2026-09-05, 사용자 정의) — app/services/notice_classification.py."""

from __future__ import annotations

from app.services.notice_classification import notice_status_label, notice_type_of, work_type_label


def test_notice_type_of_gov_support_channels():
    assert notice_type_of("IRIS") == "정부지원"
    assert notice_type_of("과학기술정보통신부") == "정부지원"


def test_notice_type_of_public_bid_channels():
    assert notice_type_of("나라장터") == "공공입찰"
    assert notice_type_of("K-water") == "공공입찰"


def test_notice_type_of_unknown_channel_defaults_to_public_bid():
    assert notice_type_of(None) == "공공입찰"
    assert notice_type_of("새로운채널") == "공공입찰"


def test_notice_status_label_public_bid_pre_notice_stages_pass_through():
    assert notice_status_label("공공입찰", "사전규격", "unscheduled") == "사전규격"
    assert notice_status_label("공공입찰", "발주계획", "upcoming") == "발주계획"


def test_notice_status_label_public_bid_bidding_stage():
    assert notice_status_label("공공입찰", "입찰공고", "in_progress") == "입찰공고"
    assert notice_status_label("공공입찰", "입찰공고", "upcoming") == "입찰공고"
    assert notice_status_label("공공입찰", "입찰공고", "closed") == "입찰마감"


def test_notice_status_label_gov_support_collapses_unscheduled_and_upcoming():
    assert notice_status_label("정부지원", "공모예고", "unscheduled") == "접수예정"
    assert notice_status_label("정부지원", "공모예고", "upcoming") == "접수예정"
    assert notice_status_label("정부지원", "입찰공고", "in_progress") == "접수중"
    assert notice_status_label("정부지원", "입찰공고", "closed") == "접수마감"


def test_work_type_label():
    assert work_type_label("정부지원", "용역") == "개발"  # biz_type이 있어도 정부지원은 고정
    assert work_type_label("정부지원", None) == "개발"
    assert work_type_label("공공입찰", "용역") == "용역"
    assert work_type_label("공공입찰", None) == "미상"

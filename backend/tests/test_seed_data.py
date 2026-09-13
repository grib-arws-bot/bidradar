"""app/seed_data.py의 add_source() 검증 — 운영 DB에 이미 시드된 소스 목록에 새 소스 하나만
안전하게 추가하는 경로(2026-09-13 신설, seed-prod 전체 재실행 없이 국가철도공단 추가 건).

실제 SOURCE_SEED 항목("국가철도공단 입찰공고" 등)은 이 테스트가 실행되는 dev DB에도 이미
등록돼 있을 수 있어(실제로 이 기능으로 막 추가한 것이므로) 그 이름을 그대로 쓰면 "이미 존재"
분기만 항상 타게 된다 — 테스트 전용 가짜 SOURCE_SEED 항목을 몽키패치해서 "새로 추가하는"
경로 자체를 검증한다."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

import pytest
from sqlalchemy import delete, select

from app.db import engine
from app.models import source, source_config, source_credential, source_field_map
from app.seed_data import add_source

_FAKE_SEED_ROW = (
    "[테스트] add_source 전용 임시 소스", "테스트기관", "https://example.grib-test.kr/bid/list",
    "https://example.grib-test.kr/", "입찰공고", "html", False, False, 60,
    "B", "테스트용 — 실제 검증된 근거 아님", "https://example.grib-test.kr/robots.txt",
)


@pytest.fixture
def fake_seed(monkeypatch):
    monkeypatch.setattr("app.seed_data.SOURCE_SEED", [_FAKE_SEED_ROW])
    yield _FAKE_SEED_ROW[0]


def test_add_source_inserts_source_config_and_field_maps_and_credential(fake_seed):
    source_id = add_source(engine, fake_seed)
    try:
        with engine.connect() as conn:
            row = conn.execute(select(source).where(source.c.id == source_id)).mappings().first()
            assert row["adapter_type"] == "html"
            assert row["legal_tier"] == "B"

            cfg = conn.execute(select(source_config).where(source_config.c.source_id == source_id)).mappings().first()
            # REAL_OPENAPI_CONFIG에 없는 이름이라 placeholder config({"adapter":..., "endpoint":...})로 떨어진다.
            assert cfg["config"]["endpoint"] == _FAKE_SEED_ROW[2]

            field_maps = conn.execute(
                select(source_field_map.c.target_field).where(source_field_map.c.source_config_id == cfg["id"])
            ).scalars().all()
            assert "title" in field_maps
            assert "org_name" in field_maps

            cred = conn.execute(
                select(source_credential.c.value).where(source_credential.c.source_id == source_id)
            ).scalar_one()
            assert cred == "__NOT_SET__"
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source).where(source.c.id == source_id))  # cascade로 config·field_map·credential도 지움


def test_add_source_rejects_unknown_name(fake_seed):
    with pytest.raises(ValueError, match="SOURCE_SEED에 없는"):
        add_source(engine, "존재하지-않는-소스-이름")


def test_add_source_rejects_duplicate_name(fake_seed):
    source_id = add_source(engine, fake_seed)
    try:
        with pytest.raises(ValueError, match="이미 존재하는 소스"):
            add_source(engine, fake_seed)
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source).where(source.c.id == source_id))

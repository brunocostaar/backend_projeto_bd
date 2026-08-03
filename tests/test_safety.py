"""Barreiras que impedem a suíte de tocar o banco normal ou de produção."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.engine import make_url

from tests import conftest


pytestmark = pytest.mark.db


def test_url_ativa_e_exclusivamente_a_porta_descartavel():
    url = make_url(conftest.TEST_DATABASE_URL)

    assert url.host in {"localhost", "127.0.0.1", "::1"}
    assert url.port == 5434
    assert os.environ["DATABASE_URL"] == conftest.TEST_DATABASE_URL
    assert os.environ["TEST_DATABASE_URL"] == conftest.TEST_DATABASE_URL


@pytest.mark.parametrize(
    "url_insegura",
    (
        "postgresql://postgres:postgres@localhost:5432/hospital_universitario",
        "postgresql://postgres:postgres@127.0.0.1:5432/hospital_universitario",
        "postgresql://postgres:postgres@db-producao:5434/hospital_universitario",
        "sqlite:///hospital.db",
    ),
)
def test_guarda_recusa_porta_normal_host_remoto_e_outro_sgbd(
    monkeypatch, url_insegura: str
):
    monkeypatch.setenv("TEST_DATABASE_URL", url_insegura)

    with pytest.raises(pytest.UsageError):
        conftest._carregar_url_de_teste()


def test_engine_e_todas_as_fabricas_globais_usam_o_engine_de_teste(engine):
    import concorrencia
    import database

    assert database.engine is engine
    assert database.engine.url == make_url(conftest.TEST_DATABASE_URL)
    assert database.SessionLocal.kw["bind"] is engine
    assert database.SessionORM.kw["bind"] is engine
    assert concorrencia.SessionORM.kw["bind"] is engine

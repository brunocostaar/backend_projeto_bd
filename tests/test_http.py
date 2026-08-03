"""Contratos HTTP canônicos da API da Etapa 2."""

from __future__ import annotations

import pytest
from sqlalchemy.orm.exc import StaleDataError
from unittest.mock import Mock

from routers.comum import confirmar


ROTAS_FIXAS = (
    "/atendimentos/tempo-medio-por-residente",
    "/atendimentos/estatisticas-mensais",
    "/atendimentos/tempo-medio-espera",
    "/pacientes/internados",
    "/pacientes/ultimo-atendimento",
    "/preceptores/supervisionados-flamenguistas",
    "/residentes/sem-supervisor-doutor",
    "/residentes/percentual-alto-risco",
)


@pytest.mark.http
@pytest.mark.parametrize("caminho", ROTAS_FIXAS)
def test_oito_caminhos_fixos_nao_sao_capturados_por_id(client, caminho: str):
    resposta = client.get(caminho)
    assert resposta.status_code == 200, resposta.text
    assert isinstance(resposta.json(), list)


@pytest.mark.http
@pytest.mark.parametrize(
    "caminho",
    (
        "/pacientes/",
        "/atendimentos/",
        "/internacoes/",
        "/analiticas/ranking-residentes",
    ),
)
def test_listagens_canonicas_respondem_sem_prefixo_legado(client, caminho: str):
    resposta = client.get(caminho)
    assert resposta.status_code == 200, resposta.text
    assert isinstance(resposta.json(), list)


@pytest.mark.http
@pytest.mark.parametrize(
    "caminho_removido",
    (
        "/orm/pacientes/",
        "/orm/analiticas/ranking-residentes",
        "/etapa2/views/pacientes-internados",
        "/etapa2/procedures/tempo-medio-espera",
        "/etapa2/consultas/lazy-vs-eager",
        "/etapa2/concorrencia/simular",
    ),
)
def test_prefixos_orm_e_etapa2_foram_removidos(client, caminho_removido: str):
    assert client.get(caminho_removido).status_code == 404


@pytest.mark.http
def test_lazy_eager_no_caminho_canonico(client):
    resposta = client.get("/consultas/lazy-vs-eager")

    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["atendimentos"] >= 1
    assert dados["consultas_lazy"] > dados["consultas_eager"]
    assert dados["resultados_iguais"] is True


@pytest.mark.http
def test_erros_http_de_validacao_referencia_e_conflito(client):
    assert client.post("/atendimentos/", json={}).status_code == 422

    referencia_invalida = {
        "data_hora": "2026-08-02T10:00:00",
        "duracao_minutos": 20,
        "id_paciente": 999999,
        "id_residente": 11,
        "id_preceptor": 6,
        "id_unidade": 1,
    }
    assert client.post("/atendimentos/", json=referencia_invalida).status_code == 404
    assert client.get("/pacientes/999999").status_code == 404

    # O residente 11 já está na segunda/manhã na unidade 1. Outra unidade é o
    # caso que só o trigger (não a UNIQUE original) consegue barrar.
    conflito = {
        "id_unidade": 3,
        "dia_semana": "segunda",
        "turno": "manha",
        "id_residente": 11,
        "id_preceptor": 6,
    }
    assert client.post("/escalas/", json=conflito).status_code == 409


@pytest.mark.http
def test_posts_canonicos_validam_corpo_sem_gravar(client):
    assert client.post("/atendimentos/completo", json={}).status_code == 422
    assert client.post("/escalas/reajustar", json={}).status_code == 422


@pytest.mark.http
def test_put_de_escala_recusa_versao_stale_com_409(client):
    criada = client.post(
        "/escalas/",
        json={
            "id_unidade": 4,
            "dia_semana": "domingo",
            "turno": "tarde",
            "id_residente": 15,
            "id_preceptor": 10,
        },
    )
    assert criada.status_code == 201, criada.text
    escala = criada.json()
    assert escala["versao"] == 1

    primeira_edicao = {
        "id_unidade": 3,
        "dia_semana": "domingo",
        "turno": "tarde",
        "id_residente": 15,
        "id_preceptor": 10,
        "versao": escala["versao"],
    }
    atualizada = client.put(f"/escalas/{escala['id_escala']}", json=primeira_edicao)
    assert atualizada.status_code == 200, atualizada.text
    assert atualizada.json()["versao"] == 2

    stale = {**primeira_edicao, "id_unidade": 2}
    recusada = client.put(f"/escalas/{escala['id_escala']}", json=stale)
    assert recusada.status_code == 409
    assert "desatualizada" in recusada.json()["detail"].lower()


def test_confirmar_faz_rollback_e_preserva_staledataerror():
    db = Mock()
    conflito = StaleDataError("linha alterada por outra transacao")
    db.commit.side_effect = conflito

    with pytest.raises(StaleDataError) as erro:
        confirmar(db)

    assert erro.value is conflito
    db.rollback.assert_called_once_with()

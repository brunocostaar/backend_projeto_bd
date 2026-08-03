"""Casos adversariais de integridade e concorrência da Etapa 2.

Os testes concorrentes usam conexões independentes e COMMIT real. Cada linha
criada é identificada pelo seu id e removida no ``finally``; nenhum cleanup
usa filtros amplos que possam apagar dados legítimos.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from concorrencia import cenario_sem_protecao


pytestmark = [pytest.mark.db, pytest.mark.adversarial]


def _sqlstate(erro: BaseException) -> str | None:
    origem = getattr(erro, "orig", erro)
    return getattr(origem, "sqlstate", None) or getattr(origem, "pgcode", None)


def _constraint_name(erro: BaseException) -> str | None:
    origem = getattr(erro, "orig", erro)
    diagnostico = getattr(origem, "diag", None)
    return getattr(diagnostico, "constraint_name", None)


def _limpar_escalas_por_id(engine: Engine, ids_escala: list[int]) -> None:
    if not ids_escala:
        return
    with engine.begin() as conexao:
        for id_escala in set(ids_escala):
            conexao.execute(
                text("DELETE FROM Escala WHERE id_escala = :id"),
                {"id": id_escala},
            )


def _limpar_atendimentos_por_id(
    engine: Engine,
    ids_atendimento: list[int],
    id_procedimento_reparar: int | None = None,
) -> None:
    if not ids_atendimento:
        return
    with engine.begin() as conexao:
        for id_atendimento in set(ids_atendimento):
            conexao.execute(
                text("DELETE FROM Atendimento WHERE id_atendimento = :id"),
                {"id": id_atendimento},
            )
        for id_atendimento in set(ids_atendimento):
            conexao.execute(
                text(
                    "DELETE FROM Auditoria_Atendimento "
                    "WHERE id_atendimento = :id"
                ),
                {"id": id_atendimento},
            )
        if id_procedimento_reparar is not None:
            conexao.execute(
                text("SELECT fn_recalcula_media_procedimento(:id)"),
                {"id": id_procedimento_reparar},
            )


def _criar_atendimento_com_procedimento(
    engine: Engine,
    chegada: datetime,
    id_procedimento: int = 8,
) -> int:
    """Cria um par válido e confirma a constraint diferida de completude."""

    with engine.begin() as conexao:
        id_atendimento = conexao.execute(
            text(
                "INSERT INTO Atendimento "
                "(data_hora, duracao_minutos, id_preceptor, id_paciente, "
                " id_residente, id_unidade) "
                "VALUES (:chegada, 20, 6, 1, 11, 1) "
                "RETURNING id_atendimento"
            ),
            {"chegada": chegada},
        ).scalar_one()
        conexao.execute(
            text(
                "INSERT INTO Procedimento_Realizado "
                "(id_atendimento, id_procedimento, quantidade, "
                " tempo_real_minutos, data_hora_inicio, faturado) "
                "VALUES (:atendimento, :procedimento, 1, 20, "
                " :inicio, FALSE)"
            ),
            {
                "atendimento": id_atendimento,
                "procedimento": id_procedimento,
                "inicio": chegada + timedelta(minutes=5),
            },
        )
    return id_atendimento


@pytest.mark.concurrency
def test_cleanup_da_simulacao_preserva_escala_legitima(engine: Engine):
    """A simulação limpa seus ids, não todas as escalas do residente/dia."""

    with engine.begin() as conexao:
        id_legitimo = conexao.execute(
            text(
                "INSERT INTO Escala "
                "(dia_semana, turno, id_preceptor, id_residente, id_unidade) "
                "VALUES ('domingo', 'manha', 10, 15, 4) "
                "RETURNING id_escala"
            )
        ).scalar_one()

    try:
        resultado = cenario_sem_protecao()
        assert resultado["conflito_evitado"] is True

        with engine.connect() as conexao:
            escala = conexao.execute(
                text(
                    "SELECT dia_semana, turno, id_residente, id_unidade "
                    "FROM Escala WHERE id_escala = :id"
                ),
                {"id": id_legitimo},
            ).one_or_none()

        assert escala is not None
        assert tuple(escala) == ("domingo", "manha", 15, 4)
    finally:
        _limpar_escalas_por_id(engine, [id_legitimo])


@pytest.mark.concurrency
def test_corrida_cross_unit_permite_exatamente_um_commit(engine: Engine):
    """A chave definitiva cobre duas unidades ainda invisíveis entre si."""

    with engine.connect() as conexao:
        preexistentes = conexao.execute(
            text(
                "SELECT COUNT(*) FROM Escala "
                "WHERE id_residente = 15 AND dia_semana = 'domingo' "
                "AND turno = 'tarde'"
            )
        ).scalar_one()
    assert preexistentes == 0

    barreira = threading.Barrier(2)

    def inserir(id_unidade: int) -> tuple[str, int | str | None]:
        with engine.connect() as conexao:
            transacao = conexao.begin()
            try:
                conexao.execute(text("SET LOCAL lock_timeout = '8s'"))
                conexao.execute(text("SET LOCAL statement_timeout = '12s'"))
                barreira.wait(timeout=8)
                id_escala = conexao.execute(
                    text(
                        "INSERT INTO Escala "
                        "(dia_semana, turno, id_preceptor, id_residente, id_unidade) "
                        "VALUES ('domingo', 'tarde', 10, 15, :unidade) "
                        "RETURNING id_escala"
                    ),
                    {"unidade": id_unidade},
                ).scalar_one()
                transacao.commit()
                return ("gravou", id_escala)
            except Exception as erro:
                if transacao.is_active:
                    transacao.rollback()
                return ("recusado", _sqlstate(erro) or type(erro).__name__)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [executor.submit(inserir, unidade) for unidade in (1, 2)]
        resultados = [futuro.result(timeout=20) for futuro in futuros]

    ids_criados = [int(valor) for estado, valor in resultados if estado == "gravou"]
    try:
        assert [estado for estado, _ in resultados].count("gravou") == 1, resultados
        assert [estado for estado, _ in resultados].count("recusado") == 1, resultados
        assert [
            valor for estado, valor in resultados if estado == "recusado"
        ] == ["23505"]

        with engine.connect() as conexao:
            quantidade = conexao.execute(
                text(
                    "SELECT COUNT(*) FROM Escala "
                    "WHERE id_residente = 15 AND dia_semana = 'domingo' "
                    "AND turno = 'tarde'"
                )
            ).scalar_one()
        assert quantidade == 1
    finally:
        _limpar_escalas_por_id(engine, ids_criados)


@pytest.mark.concurrency
def test_sp_reajustar_escala_serializa_chamadas_concorrentes(engine: Engine):
    """Duas chamadas não podem anunciar que moveram a mesma escala."""

    with engine.connect() as conexao:
        original = conexao.execute(
            text(
                "SELECT id_escala, dia_semana, turno, versao FROM Escala "
                "WHERE id_residente = 14 AND dia_semana = 'sexta' "
                "AND turno = 'manha'"
            )
        ).mappings().one()

    barreira = threading.Barrier(2)

    def reajustar(dia_destino: str) -> tuple[str, int | str | None]:
        with engine.connect() as conexao:
            transacao = conexao.begin()
            try:
                conexao.execute(text("SET LOCAL statement_timeout = '12s'"))
                barreira.wait(timeout=8)
                resultado = conexao.execute(
                    text(
                        "CALL sp_reajustar_escala("
                        "14, 'sexta', 'manha', :dia, 'noite', NULL)"
                    ),
                    {"dia": dia_destino},
                )
                movidas = resultado.scalar_one() if resultado.returns_rows else 0
                transacao.commit()
                return ("ok", int(movidas or 0))
            except Exception as erro:
                if transacao.is_active:
                    transacao.rollback()
                return ("erro", _sqlstate(erro) or type(erro).__name__)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futuros = [
                executor.submit(reajustar, dia) for dia in ("terca", "quinta")
            ]
            resultados = [futuro.result(timeout=20) for futuro in futuros]

        assert all(estado == "ok" for estado, _ in resultados), resultados
        assert sorted(int(valor) for _, valor in resultados) == [0, 1]

        with engine.connect() as conexao:
            final = conexao.execute(
                text(
                    "SELECT dia_semana, turno FROM Escala "
                    "WHERE id_escala = :id"
                ),
                {"id": original["id_escala"]},
            ).one()
        assert tuple(final) in {("terca", "noite"), ("quinta", "noite")}
    finally:
        with engine.begin() as conexao:
            conexao.execute(
                text(
                    "UPDATE Escala SET dia_semana = :dia, turno = :turno, "
                    "versao = :versao WHERE id_escala = :id"
                ),
                {
                    "id": original["id_escala"],
                    "dia": original["dia_semana"],
                    "turno": original["turno"],
                    "versao": original["versao"],
                },
            )


@pytest.mark.concurrency
def test_media_materializada_permanece_correta_em_inserts_concorrentes(
    engine: Engine,
):
    id_procedimento = 2
    with engine.connect() as conexao:
        antes = conexao.execute(
            text(
                "SELECT soma_tempo_procedimento AS soma, "
                "quantidade_tempos_procedimento AS quantidade "
                "FROM Procedimento WHERE id_procedimento = :id"
            ),
            {"id": id_procedimento},
        ).mappings().one()

    barreira = threading.Barrier(2)

    def registrar(indice: int, tempo: int) -> tuple[str, int | str | None]:
        chegada = datetime(2099, 1, 1, 10 + indice, 0)
        with engine.connect() as conexao:
            transacao = conexao.begin()
            id_atendimento: int | None = None
            try:
                conexao.execute(text("SET LOCAL statement_timeout = '12s'"))
                id_atendimento = conexao.execute(
                    text(
                        "INSERT INTO Atendimento "
                        "(data_hora, duracao_minutos, id_preceptor, id_paciente, "
                        " id_residente, id_unidade) "
                        "VALUES (:chegada, 20, 6, 1, 11, 1) "
                        "RETURNING id_atendimento"
                    ),
                    {"chegada": chegada},
                ).scalar_one()
                barreira.wait(timeout=8)
                conexao.execute(
                    text(
                        "INSERT INTO Procedimento_Realizado "
                        "(id_atendimento, id_procedimento, quantidade, "
                        " tempo_real_minutos, data_hora_inicio, faturado) "
                        "VALUES (:atendimento, :procedimento, 1, :tempo, "
                        " :inicio, FALSE)"
                    ),
                    {
                        "atendimento": id_atendimento,
                        "procedimento": id_procedimento,
                        "tempo": tempo,
                        "inicio": chegada + timedelta(minutes=5),
                    },
                )
                transacao.commit()
                return ("ok", id_atendimento)
            except Exception as erro:
                if transacao.is_active:
                    transacao.rollback()
                return ("erro", _sqlstate(erro) or type(erro).__name__)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [
            executor.submit(registrar, indice, tempo)
            for indice, tempo in enumerate((41, 59))
        ]
        resultados = [futuro.result(timeout=20) for futuro in futuros]

    ids_criados = [int(valor) for estado, valor in resultados if estado == "ok"]
    try:
        assert len(ids_criados) == 2, resultados

        with engine.connect() as conexao:
            depois = conexao.execute(
                text(
                    "SELECT p.soma_tempo_procedimento AS soma, "
                    "p.quantidade_tempos_procedimento AS quantidade, "
                    "p.media_tempo_procedimento AS armazenada, "
                    "ROUND(AVG(pr.tempo_real_minutos), 2) AS real "
                    "FROM Procedimento p "
                    "LEFT JOIN Procedimento_Realizado pr "
                    "  ON pr.id_procedimento = p.id_procedimento "
                    "WHERE p.id_procedimento = :id "
                    "GROUP BY p.id_procedimento"
                ),
                {"id": id_procedimento},
            ).mappings().one()

        assert depois["soma"] == antes["soma"] + 100
        assert depois["quantidade"] == antes["quantidade"] + 2
        assert depois["armazenada"] == depois["real"]
    finally:
        _limpar_atendimentos_por_id(engine, ids_criados, id_procedimento)


def test_commit_recusa_atendimento_sem_procedimento(engine: Engine):
    id_atendimento: int | None = None
    conexao = engine.connect()
    transacao = conexao.begin()
    try:
        id_atendimento = conexao.execute(
            text(
                "INSERT INTO Atendimento "
                "(data_hora, duracao_minutos, id_preceptor, id_paciente, "
                " id_residente, id_unidade) "
                "VALUES ('2099-02-01 10:00', 20, 6, 1, 11, 1) "
                "RETURNING id_atendimento"
            )
        ).scalar_one()
        with pytest.raises(DBAPIError) as erro:
            transacao.commit()
        assert _sqlstate(erro.value) == "23514"
        assert _constraint_name(erro.value) == "atendimento_exige_procedimento"
        assert "procedimento" in str(erro.value.orig).lower()
    finally:
        if transacao.is_active:
            transacao.rollback()
        conexao.close()
        if id_atendimento is not None:
            _limpar_atendimentos_por_id(engine, [id_atendimento])


def test_recusa_procedimento_iniciado_antes_do_atendimento(engine: Engine):
    id_atendimento: int | None = None
    conexao = engine.connect()
    transacao = conexao.begin()
    try:
        id_atendimento = conexao.execute(
            text(
                "INSERT INTO Atendimento "
                "(data_hora, duracao_minutos, id_preceptor, id_paciente, "
                " id_residente, id_unidade) "
                "VALUES ('2099-02-02 10:00', 20, 6, 1, 11, 1) "
                "RETURNING id_atendimento"
            )
        ).scalar_one()
        with pytest.raises(DBAPIError) as erro:
            conexao.execute(
                text(
                    "INSERT INTO Procedimento_Realizado "
                    "(id_atendimento, id_procedimento, quantidade, "
                    " tempo_real_minutos, data_hora_inicio, faturado) "
                    "VALUES (:atendimento, 8, 1, 20, "
                    " '2099-02-02 09:59', FALSE)"
                ),
                {"atendimento": id_atendimento},
            )
        assert _sqlstate(erro.value) == "23514"
        assert (
            _constraint_name(erro.value)
            == "chk_procedimento_inicio_apos_atendimento"
        )
        assert "antes" in str(erro.value.orig).lower()
    finally:
        if transacao.is_active:
            transacao.rollback()
        conexao.close()
        if id_atendimento is not None:
            _limpar_atendimentos_por_id(engine, [id_atendimento], 8)


def test_titulacao_descritiva_e_normalizada_e_invalida_e_recusada(db: Session):
    antes = db.execute(
        text(
            "SELECT COUNT(*) FROM vw_residentes_sem_supervisor "
            "WHERE id_preceptor = 9"
        )
    ).scalar_one()
    assert antes >= 1

    normalizada = db.execute(
        text(
            "UPDATE Preceptor SET titulacao = 'Doutorado em Medicina' "
            "WHERE id_profissional = 9 RETURNING titulacao"
        )
    ).scalar_one()
    assert normalizada == "doutor"
    assert db.execute(
        text(
            "SELECT COUNT(*) FROM vw_residentes_sem_supervisor "
            "WHERE id_preceptor = 9"
        )
    ).scalar_one() == 0

    with pytest.raises(DBAPIError) as erro:
        with db.begin_nested():
            db.execute(
                text(
                    "UPDATE Preceptor SET titulacao = 'bacharel' "
                    "WHERE id_profissional = 9"
                )
            )
    assert _sqlstate(erro.value) == "23514"


def test_profissional_nao_pode_ser_preceptor_e_residente(db: Session):
    with pytest.raises(DBAPIError) as erro:
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO Residente (id_profissional, ano_residencia) "
                    "VALUES (6, 'R1')"
                )
            )

    assert _sqlstate(erro.value) == "23514"
    assert "preceptor" in str(erro.value.orig).lower()
    assert db.execute(
        text("SELECT COUNT(*) FROM Residente WHERE id_profissional = 6")
    ).scalar_one() == 0


def test_recusa_mover_atendimento_para_depois_do_primeiro_procedimento(
    engine: Engine,
):
    id_procedimento = 8
    id_atendimento = _criar_atendimento_com_procedimento(
        engine,
        datetime(2099, 2, 3, 10, 0),
        id_procedimento,
    )
    try:
        with engine.connect() as conexao:
            transacao = conexao.begin()
            try:
                with pytest.raises(DBAPIError) as erro:
                    conexao.execute(
                        text(
                            "UPDATE Atendimento SET data_hora = '2099-02-03 10:10' "
                            "WHERE id_atendimento = :id"
                        ),
                        {"id": id_atendimento},
                    )
                assert _sqlstate(erro.value) == "23514"
                assert (
                    _constraint_name(erro.value)
                    == "chk_atendimento_antes_procedimentos"
                )
            finally:
                if transacao.is_active:
                    transacao.rollback()
    finally:
        _limpar_atendimentos_por_id(engine, [id_atendimento], id_procedimento)


def test_commit_recusa_remocao_do_ultimo_procedimento(engine: Engine):
    id_procedimento = 8
    id_atendimento = _criar_atendimento_com_procedimento(
        engine,
        datetime(2099, 2, 4, 10, 0),
        id_procedimento,
    )
    conexao = engine.connect()
    transacao = conexao.begin()
    try:
        conexao.execute(
            text(
                "DELETE FROM Procedimento_Realizado "
                "WHERE id_atendimento = :atendimento "
                "AND id_procedimento = :procedimento"
            ),
            {"atendimento": id_atendimento, "procedimento": id_procedimento},
        )
        with pytest.raises(DBAPIError) as erro:
            transacao.commit()
        assert _sqlstate(erro.value) == "23514"
        assert _constraint_name(erro.value) == "atendimento_exige_procedimento"
    finally:
        if transacao.is_active:
            transacao.rollback()
        conexao.close()
        _limpar_atendimentos_por_id(engine, [id_atendimento], id_procedimento)


@pytest.mark.concurrency
def test_exclusividade_de_papel_resiste_a_inserts_concorrentes(engine: Engine):
    sufixo = uuid.uuid4().hex
    with engine.begin() as conexao:
        id_profissional = conexao.execute(
            text(
                "WITH pessoa AS ("
                "  INSERT INTO Pessoa "
                "  (CPF, nome, is_flamengo, data_nascimento) "
                "  VALUES (:cpf, 'Profissional Concorrente', FALSE, '1990-01-01') "
                "  RETURNING id_pessoa"
                ") "
                "INSERT INTO Profissional "
                "(id_pessoa, CRM, data_admissao, especialidade) "
                "SELECT id_pessoa, :crm, '2099-01-01', 'Teste' FROM pessoa "
                "RETURNING id_pessoa"
            ),
            {"cpf": sufixo[:11], "crm": f"ADV-{sufixo[:20]}"},
        ).scalar_one()

    barreira = threading.Barrier(2)

    def reservar(papel: str) -> tuple[str, str | None]:
        with engine.connect() as conexao:
            transacao = conexao.begin()
            try:
                conexao.execute(text("SET LOCAL statement_timeout = '12s'"))
                barreira.wait(timeout=8)
                if papel == "PRECEPTOR":
                    conexao.execute(
                        text(
                            "INSERT INTO Preceptor (id_profissional, titulacao) "
                            "VALUES (:id, 'mestre')"
                        ),
                        {"id": id_profissional},
                    )
                else:
                    conexao.execute(
                        text(
                            "INSERT INTO Residente "
                            "(id_profissional, ano_residencia) VALUES (:id, 'R1')"
                        ),
                        {"id": id_profissional},
                    )
                transacao.commit()
                return ("gravou", papel)
            except Exception as erro:
                if transacao.is_active:
                    transacao.rollback()
                return ("recusado", _sqlstate(erro) or type(erro).__name__)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futuros = [
                executor.submit(reservar, papel)
                for papel in ("PRECEPTOR", "RESIDENTE")
            ]
            resultados = [futuro.result(timeout=20) for futuro in futuros]

        assert [estado for estado, _ in resultados].count("gravou") == 1, resultados
        assert [
            valor for estado, valor in resultados if estado == "recusado"
        ] == ["23514"]

        with engine.connect() as conexao:
            papeis = conexao.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM Preceptor WHERE id_profissional = :id) "
                    "+ (SELECT COUNT(*) FROM Residente WHERE id_profissional = :id)"
                ),
                {"id": id_profissional},
            ).scalar_one()
        assert papeis == 1
    finally:
        with engine.begin() as conexao:
            conexao.execute(
                text("DELETE FROM Preceptor WHERE id_profissional = :id"),
                {"id": id_profissional},
            )
            conexao.execute(
                text("DELETE FROM Residente WHERE id_profissional = :id"),
                {"id": id_profissional},
            )
            conexao.execute(
                text("DELETE FROM Profissional WHERE id_pessoa = :id"),
                {"id": id_profissional},
            )
            conexao.execute(
                text("DELETE FROM Pessoa WHERE id_pessoa = :id"),
                {"id": id_profissional},
            )

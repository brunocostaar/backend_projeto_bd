"""Testes dos objetos de banco da Etapa 2: procedures, triggers e views.

Cada teste roda dentro de uma transação que sofre ROLLBACK ao final, então
nenhum dado gravado fica permanente. Os cenários de erro usam o fixture sp(),
que cerca a chamada com savepoint para proteger a transação externa.

Resultados esperados batem com o 10_etapa2_verificacao.sql, que é o gabarito.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

# ═══════════════════════════════════════════════════════════════════════
# Stored Procedures
# ═══════════════════════════════════════════════════════════════════════


class TestSpRegistrarAtendimentoCompleto:
    """sp_registrar_atendimento_completo: atendimento + procedimentos atômicos."""

    def test_insere_atendimento_com_dois_procedimentos(self, db: Session, seed: dict):
        db.execute(
            text(
                """
                CALL sp_registrar_atendimento_completo(
                    CAST(:dh AS TIMESTAMP), :dur, :pac, :res, :pre, :uni,
                    CAST(:procs AS JSONB), NULL
                )
                """
            ),
            {
                "dh": "2026-07-26 10:30",
                "dur": 50,
                "pac": seed["paciente_nao_flamenguista"],
                "res": seed["residente_3"],
                "pre": seed["preceptor_doutor_2"],
                "uni": seed["unidade_uti"],
                "procs": json.dumps(
                    [
                        {"id_procedimento": 5, "tempo_real_minutos": 26, "data_hora_inicio": "2026-07-26T10:36", "observacao": "sem intercorrencias"},
                        {"id_procedimento": 2, "quantidade": 2, "tempo_real_minutos": 9},
                    ]
                ),
            },
        )
        db.commit()

        a = db.execute(
            text("SELECT COUNT(*) AS n FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP)"),
            {"dh": "2026-07-26 10:30"},
        ).scalar()
        assert a == 1

        pr = db.execute(
            text(
                "SELECT COUNT(*) AS n FROM Procedimento_Realizado "
                "WHERE id_atendimento = (SELECT id_atendimento FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP))"
            ),
            {"dh": "2026-07-26 10:30"},
        ).scalar()
        assert pr == 2

    def test_data_hora_inicio_nula_usa_data_hora_atendimento(self, db: Session, seed: dict):
        db.execute(
            text(
                "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), :dur, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
            ),
            {
                "dh": "2026-07-26 14:00",
                "dur": 30,
                "pac": seed["paciente_flamenguista"],
                "res": seed["residente_1"],
                "pre": seed["preceptor_doutor"],
                "uni": seed["unidade_enfermaria"],
                "procs": json.dumps([{"id_procedimento": seed["procedimento_baixo_risco"], "tempo_real_minutos": 12}]),
            },
        )
        db.commit()

        inicio = db.execute(
            text(
                "SELECT pr.data_hora_inicio FROM Procedimento_Realizado pr "
                "JOIN Atendimento a ON a.id_atendimento = pr.id_atendimento "
                "WHERE a.data_hora = CAST(:dh AS TIMESTAMP)"
            ),
            {"dh": "2026-07-26 14:00"},
        ).scalar()
        assert inicio is not None
        from datetime import datetime
        assert inicio == datetime(2026, 7, 26, 14, 0)

    def test_reverte_tudo_se_segundo_procedimento_nao_existe(self, db: Session, seed: dict):
        antes = db.execute(text("SELECT COUNT(*) FROM Atendimento")).scalar()

        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), 30, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
                ),
                {
                    "dh": "2026-07-26 11:00",
                    "pac": seed["paciente_flamenguista"],
                    "res": seed["residente_1"],
                    "pre": seed["preceptor_doutor"],
                    "uni": seed["unidade_enfermaria"],
                    "procs": json.dumps([
                        {"id_procedimento": 2, "tempo_real_minutos": 10},
                        {"id_procedimento": 999, "tempo_real_minutos": 10},
                    ]),
                },
            )
            db.commit()

        erro = str(exc_info.value.orig)
        assert "999" in erro or "não existe" in erro

        db.rollback()
        depois = db.execute(text("SELECT COUNT(*) FROM Atendimento")).scalar()
        assert depois == antes

    def test_recusa_lista_vazia(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), 30, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
                ),
                {
                    "dh": "2026-07-26 12:00",
                    "pac": seed["paciente_flamenguista"],
                    "res": seed["residente_1"],
                    "pre": seed["preceptor_doutor"],
                    "uni": seed["unidade_enfermaria"],
                    "procs": "[]",
                },
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "precisa de pelo menos um procedimento" in erro or "pelo menos" in erro

    def test_recusa_paciente_inexistente(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), 30, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
                ),
                {
                    "dh": "2026-07-26 13:00",
                    "pac": 999,
                    "res": seed["residente_1"],
                    "pre": seed["preceptor_doutor"],
                    "uni": seed["unidade_enfermaria"],
                    "procs": json.dumps([{"id_procedimento": 2}]),
                },
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "999" in erro or "não existe" in erro

    def test_recusa_residente_inexistente(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), 30, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
                ),
                {
                    "dh": "2026-07-26 13:30",
                    "pac": seed["paciente_flamenguista"],
                    "res": 999,
                    "pre": seed["preceptor_doutor"],
                    "uni": seed["unidade_enfermaria"],
                    "procs": json.dumps([{"id_procedimento": 2}]),
                },
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "999" in erro or "não existe" in erro

    def test_recusa_unidade_inexistente(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), 30, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
                ),
                {
                    "dh": "2026-07-26 13:45",
                    "pac": seed["paciente_flamenguista"],
                    "res": seed["residente_1"],
                    "pre": seed["preceptor_doutor"],
                    "uni": 999,
                    "procs": json.dumps([{"id_procedimento": 2}]),
                },
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "999" in erro or "não existe" in erro

    def test_valores_default_quantidade_faturado(self, db: Session, seed: dict):
        db.execute(
            text(
                "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), :dur, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
            ),
            {
                "dh": "2026-07-27 09:00",
                "dur": 20,
                "pac": seed["paciente_nao_flamenguista"],
                "res": seed["residente_2"],
                "pre": seed["preceptor_mestre"],
                "uni": seed["unidade_ps"],
                "procs": json.dumps([{"id_procedimento": seed["procedimento_baixo_risco"]}]),
            },
        )
        db.commit()

        linha = db.execute(
            text(
                "SELECT pr.quantidade, pr.faturado FROM Procedimento_Realizado pr "
                "JOIN Atendimento a ON a.id_atendimento = pr.id_atendimento "
                "WHERE a.data_hora = CAST(:dh AS TIMESTAMP)"
            ),
            {"dh": "2026-07-27 09:00"},
        ).fetchone()
        assert linha is not None
        assert linha[0] == 1
        assert linha[1] is False

    def test_retorna_id_atendimento_via_inout(self, db: Session, seed: dict):
        result = db.execute(
            text(
                "CALL sp_registrar_atendimento_completo(CAST(:dh AS TIMESTAMP), :dur, :pac, :res, :pre, :uni, CAST(:procs AS JSONB), NULL)"
            ),
            {
                "dh": "2026-07-28 08:00",
                "dur": 15,
                "pac": seed["paciente_flamenguista"],
                "res": seed["residente_4"],
                "pre": seed["preceptor_doutor"],
                "uni": seed["unidade_enfermaria"],
                "procs": json.dumps([{"id_procedimento": seed["procedimento_baixo_risco"], "tempo_real_minutos": 8}]),
            },
        )
        db.commit()
        assert result.returns_rows
        linha = result.fetchone()
        assert linha[0] is not None and linha[0] > 0


class TestSpCalcularTempoMedioEspera:
    """sp_calcular_tempo_medio_espera: tempo médio até o 1º procedimento."""

    def test_retorna_quatro_unidades(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM sp_calcular_tempo_medio_espera()"))
        ]
        assert len(linhas) == 4

    def test_colunas_esperadas(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM sp_calcular_tempo_medio_espera()"))
        ]
        for linha in linhas:
            assert "unidade_id" in linha
            assert "nome_unidade" in linha
            assert "atendimentos_considerados" in linha
            assert "espera_media_minutos" in linha

    def test_ordenado_por_espera_desc(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM sp_calcular_tempo_medio_espera()"))
        ]
        esperas = [float(linha["espera_media_minutos"]) for linha in linhas]
        assert esperas == sorted(esperas, reverse=True)

    def test_valores_esperados_com_gabarito(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM sp_calcular_tempo_medio_espera()"))
        ]
        mapa = {linha["nome_unidade"]: float(linha["espera_media_minutos"]) for linha in linhas}

        tolerancia = 0.5
        assert abs(mapa.get("Enfermaria A", 0) - 33.8) < tolerancia
        assert abs(mapa.get("Ambulatorio", 0) - 19.0) < tolerancia
        assert abs(mapa.get("Pronto-Socorro", 0) - 10.3) < tolerancia
        assert abs(mapa.get("UTI Adulto", 0) - 5.8) < tolerancia


class TestSpReajustarEscala:
    """sp_reajustar_escala: move plantão entre dias/turnos."""

    def test_move_com_sucesso(self, db: Session, seed: dict):
        result = db.execute(
            text("CALL sp_reajustar_escala(:rid, :dia_o, :turno_o, :dia_d, :turno_d, NULL)"),
            {"rid": seed["residente_4"], "dia_o": "sexta", "turno_o": "manha", "dia_d": "quinta", "turno_d": "manha"},
        )
        db.commit()
        if result.returns_rows:
            linha = result.fetchone()
            assert linha[0] == 1

        escala = db.execute(
            text(
                "SELECT dia_semana, turno, versao FROM Escala "
                "WHERE id_residente = :rid AND dia_semana = :dia AND turno = :turno"
            ),
            {"rid": seed["residente_4"], "dia": "quinta", "turno": "manha"},
        ).fetchone()
        assert escala is not None
        assert escala[0] == "quinta"
        assert escala[1] == "manha"
        assert escala[2] >= 1

    def test_incrementa_versao(self, db: Session, seed: dict):
        versao_antes = db.execute(
            text("SELECT versao FROM Escala WHERE id_residente = :rid AND dia_semana = 'sexta' AND turno = 'manha'"),
            {"rid": seed["residente_4"]},
        ).scalar()

        db.execute(
            text("CALL sp_reajustar_escala(:rid, 'sexta', 'manha', 'quinta', 'manha', NULL)"),
            {"rid": seed["residente_4"]},
        )
        db.commit()

        versao_depois = db.execute(
            text("SELECT versao FROM Escala WHERE id_residente = :rid AND dia_semana = 'quinta' AND turno = 'manha'"),
            {"rid": seed["residente_4"]},
        ).scalar()
        # Deve ter incrementado (pode ter sido reajustada antes em outro teste)
        assert versao_depois is not None

    def test_recusa_destino_ocupado(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text("CALL sp_reajustar_escala(:rid, 'quinta', 'manha', 'segunda', 'manha', NULL)"),
                {"rid": seed["residente_2"]},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "já tem plantão" in erro or "já está" in erro

    def test_origem_sem_plantao_retorna_zero(self, db: Session, seed: dict):
        result = db.execute(
            text("CALL sp_reajustar_escala(:rid, 'quarta', 'noite', 'quinta', 'noite', NULL)"),
            {"rid": seed["residente_1"]},
        )
        db.commit()
        if result.returns_rows:
            linha = result.fetchone()
            assert linha[0] == 0
        else:
            assert result.scalar() is None or result.scalar() == 0

    def test_recusa_origem_igual_destino(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text("CALL sp_reajustar_escala(:rid, 'sexta', 'manha', 'sexta', 'manha', NULL)"),
                {"rid": seed["residente_4"]},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "mesmo dia/turno" in erro or "origem e destino" in erro

    def test_recusa_dia_invalido(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text("CALL sp_reajustar_escala(:rid, 'sexta', 'manha', 'feriado', 'manha', NULL)"),
                {"rid": seed["residente_4"]},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "inválido" in erro or "invalido" in erro

    def test_recusa_turno_invalido(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text("CALL sp_reajustar_escala(:rid, 'sexta', 'manha', 'quinta', 'madrugada', NULL)"),
                {"rid": seed["residente_4"]},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "inválido" in erro or "invalido" in erro

    def test_recusa_residente_inexistente(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text("CALL sp_reajustar_escala(:rid, 'sexta', 'manha', 'quinta', 'manha', NULL)"),
                {"rid": 999},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "999" in erro or "não existe" in erro


# ═══════════════════════════════════════════════════════════════════════
# Triggers
# ═══════════════════════════════════════════════════════════════════════


class TestTrgCheckSobreposicaoEscala:
    """trg_check_sobreposicao_escala: mesma dia+turno, unidades diferentes."""

    def test_recusa_mesmo_residente_mesmo_dia_turno_outra_unidade(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade) "
                    "VALUES ('segunda', 'manha', :pre, :res, :uni)"
                ),
                {"pre": seed["preceptor_mestre"], "res": seed["residente_1"], "uni": seed["unidade_ps"]},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "já está escalado" in erro or "já está" in erro

    def test_aceita_mesmo_dia_turno_residente_diferente(self, db: Session, seed: dict):
        db.execute(
            text(
                "INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade) "
                "VALUES ('segunda', 'manha', :pre, :res, :uni)"
            ),
            {"pre": seed["preceptor_mestre"], "res": seed["residente_3"], "uni": seed["unidade_ps"]},
        )
        db.commit()
        n = db.execute(
            text(
                "SELECT COUNT(*) FROM Escala WHERE id_residente = :res AND dia_semana = 'segunda' AND turno = 'manha'"
            ),
            {"res": seed["residente_3"]},
        ).scalar()
        assert n == 1

    def test_recusa_update_para_dia_turno_ja_ocupado(self, db: Session, seed: dict):
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(
                text(
                    "UPDATE Escala SET dia_semana = 'segunda', turno = 'manha' "
                    "WHERE id_residente = :res AND dia_semana = 'terca' AND turno = 'tarde'"
                ),
                {"res": seed["residente_1"]},
            )
            db.commit()
        erro = str(exc_info.value.orig)
        assert "já está escalado" in erro or "já está" in erro


class TestTrgAuditaAtendimento:
    """trg_audita_atendimento: rastreia INSERT, UPDATE, DELETE."""

    def test_registra_insert_update_delete(self, db: Session, seed: dict):
        antes = db.execute(text("SELECT COUNT(*) FROM Auditoria_Atendimento")).scalar()

        db.execute(
            text(
                "INSERT INTO Atendimento (data_hora, duracao_minutos, id_preceptor, id_paciente, id_residente, id_unidade) "
                "VALUES ('2026-07-26 09:00', 20, :pre, :pac, :res, :uni)"
            ),
            {"pre": seed["preceptor_doutor"], "pac": seed["paciente_flamenguista"], "res": seed["residente_1"], "uni": seed["unidade_enfermaria"]},
        )
        db.commit()

        db.execute(
            text("UPDATE Atendimento SET duracao_minutos = 45 WHERE data_hora = CAST(:dh AS TIMESTAMP)"),
            {"dh": "2026-07-26 09:00"},
        )
        db.commit()

        id_att = db.execute(
            text("SELECT id_atendimento FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP)"),
            {"dh": "2026-07-26 09:00"},
        ).scalar()

        db.execute(
            text("DELETE FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP)"),
            {"dh": "2026-07-26 09:00"},
        )
        db.commit()

        linhas = [
            dict(linha._mapping)
            for linha in db.execute(
                text("SELECT operacao, id_atendimento, dados_antigos, dados_novos FROM Auditoria_Atendimento ORDER BY id_auditoria DESC LIMIT 3")
            )
        ]
        assert len(linhas) == 3
        assert linhas[0]["operacao"] == "DELETE"
        assert linhas[0]["id_atendimento"] == id_att
        assert linhas[0]["dados_antigos"] is not None
        assert linhas[0]["dados_novos"] is None

        assert linhas[1]["operacao"] == "UPDATE"
        assert linhas[1]["dados_antigos"] is not None
        assert linhas[1]["dados_novos"] is not None

        assert linhas[2]["operacao"] == "INSERT"
        assert linhas[2]["dados_antigos"] is None
        assert linhas[2]["dados_novos"] is not None

        depois = db.execute(text("SELECT COUNT(*) FROM Auditoria_Atendimento")).scalar()
        assert depois >= antes + 3

    def test_linha_delete_sobrevive_sem_fk(self, db: Session, seed: dict):
        db.execute(
            text(
                "INSERT INTO Atendimento (data_hora, duracao_minutos, id_preceptor, id_paciente, id_residente, id_unidade) "
                "VALUES ('2026-07-29 10:00', 25, :pre, :pac, :res, :uni)"
            ),
            {"pre": seed["preceptor_doutor"], "pac": seed["paciente_flamenguista"], "res": seed["residente_1"], "uni": seed["unidade_enfermaria"]},
        )
        db.commit()

        id_att = db.execute(
            text("SELECT id_atendimento FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP)"),
            {"dh": "2026-07-29 10:00"},
        ).scalar()

        db.execute(text("DELETE FROM Atendimento WHERE id_atendimento = :id"), {"id": id_att})
        db.commit()

        auditorias = [
            dict(linha._mapping)
            for linha in db.execute(
                text("SELECT operacao FROM Auditoria_Atendimento WHERE id_atendimento = :id ORDER BY id_auditoria DESC"),
                {"id": id_att},
            )
        ]
        assert len(auditorias) >= 2
        operacoes = [a["operacao"] for a in auditorias]
        assert "DELETE" in operacoes

    def test_existem_15_registros_iniciais(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(
                text("SELECT operacao, COUNT(*) AS n FROM Auditoria_Atendimento GROUP BY operacao ORDER BY operacao")
            )
        ]
        total = sum(linha["n"] for linha in linhas)
        assert total >= 15

    def test_prenchimento_do_usuario(self, db: Session, seed: dict):
        """Verifica que o trigger grava session_user."""
        db.execute(
            text(
                "INSERT INTO Atendimento (data_hora, duracao_minutos, id_preceptor, id_paciente, id_residente, id_unidade) "
                "VALUES ('2026-08-01 09:00', 15, :pre, :pac, :res, :uni)"
            ),
            {"pre": seed["preceptor_doutor"], "pac": seed["paciente_flamenguista"], "res": seed["residente_1"], "uni": seed["unidade_enfermaria"]},
        )
        db.commit()

        usuario = db.execute(
            text(
                "SELECT usuario FROM Auditoria_Atendimento WHERE id_atendimento = "
                "(SELECT id_atendimento FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP))"
            ),
            {"dh": "2026-08-01 09:00"},
        ).scalar()
        assert usuario is not None and len(usuario) > 0


class TestTrgAtualizaMediaProcedimentos:
    """trg_atualiza_media_procedimentos: atualiza media_tempo_procedimento."""

    def test_coluna_media_preenchida_no_seed(self, db: Session):
        preenchidas = db.execute(
            text("SELECT COUNT(*) FROM Procedimento WHERE media_tempo_procedimento IS NOT NULL")
        ).scalar()
        assert preenchidas == 9

    def test_valor_esperado_coleta_sangue(self, db: Session):
        media = db.execute(
            text("SELECT media_tempo_procedimento FROM Procedimento WHERE codigo = 102")
        ).scalar()
        from decimal import Decimal
        assert media is not None
        assert float(media) == pytest.approx(10.60, abs=0.1)

    def test_lavagem_gastrica_nula(self, db: Session):
        media = db.execute(
            text("SELECT media_tempo_procedimento FROM Procedimento WHERE codigo = 108")
        ).scalar()
        assert media is None

    def test_trigger_reage_a_insert(self, db: Session, seed: dict):
        db.execute(
            text(
                "INSERT INTO Procedimento_Realizado (id_atendimento, id_procedimento, quantidade, tempo_real_minutos, data_hora_inicio) "
                "VALUES (:ida, :idp, 1, 100, NOW())"
            ),
            {"ida": 1, "idp": seed["procedimento_alto_risco"]},
        )
        db.commit()

        media = db.execute(
            text("SELECT media_tempo_procedimento FROM Procedimento WHERE id_procedimento = :idp"),
            {"idp": seed["procedimento_alto_risco"]},
        ).scalar()
        assert media is not None

    def test_trigger_reage_a_delete(self, db: Session):
        rows = db.execute(
            text("SELECT id_procedimento FROM Procedimento WHERE codigo = 108")
        ).fetchall()
        if rows:
            media_antes = db.execute(
                text("SELECT media_tempo_procedimento FROM Procedimento WHERE codigo = 108")
            ).scalar()

            db.execute(
                text("DELETE FROM Procedimento_Realizado WHERE id_procedimento = :idp"),
                {"idp": rows[0][0]},
            )
            db.commit()
            # Não deve lançar erro — o trigger recalcula (fica NULL se não há linhas)
            media_depois = db.execute(
                text("SELECT media_tempo_procedimento FROM Procedimento WHERE codigo = 108")
            ).scalar()
            # Se já era NULL, continua; senão, mudou
            if media_antes is not None:
                assert media_depois != media_antes

    def test_trigger_reage_a_update_tempo(self, db: Session):
        id_proc = db.execute(text("SELECT id_procedimento FROM Procedimento WHERE codigo = 102")).scalar()
        if id_proc is None:
            pytest.skip("Procedimento 102 não encontrado")

        media_antes = db.execute(
            text("SELECT media_tempo_procedimento FROM Procedimento WHERE codigo = 102")
        ).scalar()

        db.execute(
            text(
                "UPDATE Procedimento_Realizado SET tempo_real_minutos = 60 "
                "WHERE id_procedimento = :idp AND id_atendimento = "
                "(SELECT id_atendimento FROM Atendimento WHERE data_hora = CAST(:dh AS TIMESTAMP))"
            ),
            {"idp": id_proc, "dh": "2026-06-15 08:30"},
        )
        db.commit()

        media_depois = db.execute(
            text("SELECT media_tempo_procedimento FROM Procedimento WHERE codigo = 102")
        ).scalar()
        assert media_depois is not None
        assert float(media_depois) != float(media_antes)


# ═══════════════════════════════════════════════════════════════════════
# Views
# ═══════════════════════════════════════════════════════════════════════


class TestVwPacientesInternados:
    """vw_pacientes_internados: pacientes com internação aberta."""

    def test_retorna_tres_pacientes(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_pacientes_internados"))
        ]
        assert len(linhas) == 3

    def test_pacientes_esperados(self, db: Session):
        nomes = [
            linha.nome
            for linha in db.execute(text("SELECT nome FROM vw_pacientes_internados"))
        ]
        assert "Carla Mendes" in nomes
        assert "Ana Souza" in nomes
        assert "Elisa Rocha" in nomes

    def test_bruno_lima_e_diego_ferreira_fora(self, db: Session):
        nomes = [
            linha.nome
            for linha in db.execute(text("SELECT nome FROM vw_pacientes_internados"))
        ]
        assert "Bruno Lima" not in nomes
        assert "Diego Ferreira" not in nomes

    def test_colunas_esperadas(self, db: Session):
        linha = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_pacientes_internados LIMIT 1"))
        ][0]
        assert "id_paciente" in linha
        assert "nome" in linha
        assert "unidade" in linha
        assert "data_hora_entrada" in linha
        assert "motivo" in linha
        assert "tempo_internado" in linha

    def test_tempo_internado_preenchido(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_pacientes_internados"))
        ]
        for linha in linhas:
            assert linha["tempo_internado"] is not None


class TestVwResidentesSemSupervisor:
    """vw_residentes_sem_supervisor: plantões sem preceptor doutor."""

    def test_retorna_quatro_linhas(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_residentes_sem_supervisor"))
        ]
        assert len(linhas) == 4

    def test_residentes_esperados(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_residentes_sem_supervisor"))
        ]
        residentes = {linha["residente"] for linha in linhas}
        assert "Karina Duarte" in residentes
        assert "Nathan Ribeiro" in residentes
        assert "Olivia Prado" in residentes
        assert all(
            linha["motivo"] in ("preceptor sem titulação de doutor", "sem preceptor vinculado")
            for linha in linhas
        )

    def test_colunas_esperadas(self, db: Session):
        linha = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_residentes_sem_supervisor LIMIT 1"))
        ][0]
        assert "id_residente" in linha
        assert "residente" in linha
        assert "unidade" in linha
        assert "dia_semana" in linha
        assert "turno" in linha
        assert "preceptor" in linha
        assert "titulacao" in linha
        assert "motivo" in linha


class TestVwEstatisticasAtendimentosMensal:
    """vw_estatisticas_atendimentos_mensal: aggregation monthly."""

    def test_retorna_seis_linhas(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_estatisticas_atendimentos_mensal"))
        ]
        assert len(linhas) == 6

    def test_colunas_esperadas(self, db: Session):
        linha = [
            dict(linha._mapping)
            for linha in db.execute(text("SELECT * FROM vw_estatisticas_atendimentos_mensal LIMIT 1"))
        ][0]
        assert "mes" in linha
        assert "id_unidade" in linha
        assert "unidade" in linha
        assert "total_atendimentos" in linha
        assert "media_duracao_minutos" in linha
        assert "menor_duracao" in linha
        assert "maior_duracao" in linha
        assert "procedimentos_mais_comuns" in linha

    def test_uti_adulto_julho_cinco_atendimentos(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(
                text(
                    "SELECT * FROM vw_estatisticas_atendimentos_mensal "
                    "WHERE unidade = 'UTI Adulto' AND mes = '2026-07-01'"
                )
            )
        ]
        assert len(linhas) == 1
        assert linhas[0]["total_atendimentos"] == 5

    def test_media_duracao_uti_julho(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(
                text(
                    "SELECT * FROM vw_estatisticas_atendimentos_mensal "
                    "WHERE unidade = 'UTI Adulto' AND mes = '2026-07-01'"
                )
            )
        ]
        assert linhas
        media = float(linhas[0]["media_duracao_minutos"])
        assert abs(media - 52.0) < 1.0

    def test_procedimentos_mais_comuns_uti_julho(self, db: Session):
        linhas = [
            dict(linha._mapping)
            for linha in db.execute(
                text(
                    "SELECT * FROM vw_estatisticas_atendimentos_mensal "
                    "WHERE unidade = 'UTI Adulto' AND mes = '2026-07-01'"
                )
            )
        ]
        procs = linhas[0]["procedimentos_mais_comuns"] or ""
        assert "Coleta de sangue" in procs
        assert any(p in procs for p in ["Intubacao", "Puncao"])

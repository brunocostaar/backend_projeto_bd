"""Testes da camada ORM da Etapa 2: CRUD, consultas avançadas e concorrência.

Testa:
  - Item 4: Reimplementação das operações da Etapa 1 via ORM (CRUD de todas as
    entidades, uso de sessões/transações, relacionamentos, lazy vs eager)
  - Item 5: Consultas avançadas com a DSL da ORM (preceptores-flamenguistas,
    último atendimento, percentual de alto risco, lazy vs eager)
  - Item 6: Concorrência (3 cenários de disputa pela mesma escala)
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from modelos import (
    Atendimento,
    Escala,
    Paciente,
    Pessoa,
    Preceptor,
    Procedimento,
    ProcedimentoRealizado,
    Profissional,
    Residente,
    Unidade,
)
from analiticas_db import (
    pacientes_sem_procedimento_de_alto_risco,
    plantoes_por_unidade_no_mes,
    plantoes_por_unidade_semanal,
    preceptores_acima_de,
    ranking_residentes,
)
from consultas import (
    comparar_lazy_e_eager,
    percentual_alto_risco_por_residente,
    preceptores_de_pacientes_flamenguistas,
    ultimo_atendimento_por_paciente,
)
from concorrencia import simular


# ═══════════════════════════════════════════════════════════════════════
# Item 4: ORM CRUD — Mapeamento, sessões, relacionamentos
# ═══════════════════════════════════════════════════════════════════════


class TestOrmPessoaPaciente:
    """CRUD de Pessoa/Paciente via ORM, demonstrando relacionamentos."""

    def test_criar_paciente(self, db: Session):
        pessoa = Pessoa(
            CPF="17171717171",
            nome="Teste Silva",
            data_nascimento=date(1993, 5, 20),
            is_flamengo=False,
        )
        db.add(pessoa)
        db.flush()

        paciente = Paciente(
            id_pessoa=pessoa.id_pessoa,
            numero_convenio="TEST-0001",
            grupo_sanguineo="A+",
        )
        db.add(paciente)
        db.commit()

        carregado = db.get(Pessoa, pessoa.id_pessoa)
        assert carregado is not None
        assert carregado.nome == "Teste Silva"
        assert carregado.paciente is not None
        assert carregado.paciente.numero_convenio == "TEST-0001"

    def test_ler_paciente_com_relacionamento(self, db: Session):
        carregado = db.get(Paciente, 1)
        assert carregado is not None
        assert carregado.pessoa.nome == "Ana Souza"
        assert carregado.grupo_sanguineo == "O+"

    def test_alterar_nome_paciente(self, db: Session):
        pessoa = db.get(Pessoa, 1)
        assert pessoa is not None
        original = pessoa.nome
        pessoa.nome = "Ana Souza Modificada"
        db.commit()

        pessoa = db.get(Pessoa, 1)
        assert pessoa.nome == "Ana Souza Modificada"
        pessoa.nome = original
        db.commit()

    def test_deletar_paciente_cascade(self, db: Session):
        """Ao deletar Pessoa, Paciente some em cascata."""
        pessoa = Pessoa(
            CPF="18181818181",
            nome="Para Deletar",
            data_nascimento=date(2000, 5, 10),
        )
        db.add(pessoa)
        db.flush()
        db.add(Paciente(id_pessoa=pessoa.id_pessoa, numero_convenio="DEL-0001", grupo_sanguineo="O+"))
        db.commit()

        id_p = pessoa.id_pessoa
        db.delete(pessoa)
        db.commit()

        assert db.get(Pessoa, id_p) is None
        assert db.get(Paciente, id_p) is None


class TestOrmProfissional:
    """CRUD de Profissional/Preceptor/Residente via ORM."""

    def test_criar_preceptor(self, db: Session):
        pessoa = Pessoa(
            CPF="19191919191",
            nome="Preceptor Teste",
            data_nascimento=date(1980, 1, 15),
        )
        db.add(pessoa)
        db.flush()
        prof = Profissional(
            id_pessoa=pessoa.id_pessoa,
            CRM="CRM-TEST-001",
            especialidade="Teste",
        )
        db.add(prof)
        db.flush()
        prec = Preceptor(id_profissional=prof.id_pessoa, titulacao="doutor")
        db.add(prec)
        db.commit()

        carregado = db.get(Pessoa, pessoa.id_pessoa)
        assert carregado.profissional.preceptor.titulacao == "doutor"

    def test_criar_residente(self, db: Session):
        pessoa = Pessoa(
            CPF="20202020202",
            nome="Residente Teste",
            data_nascimento=date(1999, 3, 10),
        )
        db.add(pessoa)
        db.flush()
        prof = Profissional(
            id_pessoa=pessoa.id_pessoa,
            CRM="CRM-TEST-002",
            especialidade="Clinica Medica",
        )
        db.add(prof)
        db.flush()
        res = Residente(id_profissional=prof.id_pessoa, ano_residencia="R1")
        db.add(res)
        db.commit()

        carregado = db.get(Residente, prof.id_pessoa)
        assert carregado.ano_residencia == "R1"
        assert carregado.profissional.pessoa.nome == "Residente Teste"


class TestOrmUnidade:
    """CRUD de Unidade."""

    def test_listar_unidades(self, db: Session):
        unidades = db.execute(select(Unidade).order_by(Unidade.id_unidade)).scalars().all()
        assert len(unidades) == 4
        nomes = {u.nome for u in unidades}
        assert nomes == {"Enfermaria A", "UTI Adulto", "Pronto-Socorro", "Ambulatorio"}


class TestOrmAtendimento:
    """CRUD de Atendimento com procedimentos realizados."""

    def test_criar_atendimento_com_relacionamentos(self, db: Session, seed: dict):
        att = Atendimento(
            data_hora=datetime(2026, 8, 1, 10, 0),
            duracao_minutos=45,
            id_paciente=seed["paciente_flamenguista"],
            id_residente=seed["residente_1"],
            id_preceptor=seed["preceptor_doutor"],
            id_unidade=seed["unidade_uti"],
        )
        db.add(att)
        db.flush()
        db.add(
            ProcedimentoRealizado(
                id_atendimento=att.id_atendimento,
                id_procedimento=seed["procedimento_baixo_risco"],
                quantidade=1,
                tempo_real_minutos=15,
                data_hora_inicio=datetime(2026, 8, 1, 10, 5),
            )
        )
        db.commit()

        carregado = db.get(Atendimento, att.id_atendimento)
        assert carregado.paciente.pessoa.nome == "Ana Souza"
        assert carregado.residente.profissional.pessoa.nome == "Karina Duarte"
        assert carregado.unidade.nome == "UTI Adulto"
        assert len(carregado.procedimentos_realizados) == 1

    def test_listar_atendimentos(self, db: Session):
        total = db.execute(select(Atendimento)).scalars().all()
        assert len(total) >= 15


class TestOrmEscala:
    """CRUD de Escala demonstrando lazy loading e otimista."""

    def test_criar_escala(self, db: Session, seed: dict):
        escala = Escala(
            dia_semana="domingo",
            turno="manha",
            id_residente=seed["residente_3"],
            id_preceptor=seed["preceptor_doutor"],
            id_unidade=seed["unidade_enfermaria"],
        )
        db.add(escala)
        db.commit()

        carregado = db.get(Escala, escala.id_escala)
        assert carregado.versao == 1
        assert carregado.residente is not None

    def test_versao_incrementa_em_update(self, db: Session, seed: dict):
        escala = db.get(
            Escala,
            db.execute(
                select(Escala.id_escala).where(
                    Escala.id_residente == seed["residente_4"],
                    Escala.dia_semana == "sexta",
                    Escala.turno == "manha",
                )
            ).scalar(),
        )
        assert escala is not None
        v_antes = escala.versao
        escala.turno = "noite"
        db.commit()
        assert escala.versao == v_antes + 1

        escala.turno = "manha"
        db.commit()


class TestOrmLazyVsEager:
    """Demonstração de lazy loading contra eager loading."""

    def test_comparacao_lazy_eager_retorna_resultado(self, db: Session):
        resultado = comparar_lazy_e_eager(db)
        assert resultado["atendimentos"] >= 15
        assert resultado["resultados_iguais"] is True
        assert resultado["consultas_eager"] < resultado["consultas_lazy"]

    def test_eager_loading_com_joinedload(self, db: Session):
        stmt = (
            select(Atendimento)
            .options(
                joinedload(Atendimento.paciente).joinedload(Paciente.pessoa),
                joinedload(Atendimento.residente)
                .joinedload(Residente.profissional)
                .joinedload(Profissional.pessoa),
            )
            .order_by(Atendimento.id_atendimento)
            .limit(5)
        )
        resultados = db.execute(stmt).unique().scalars().all()
        for a in resultados:
            nome = a.paciente.pessoa.nome
            assert nome is not None and len(nome) > 0

    def test_lazy_loading_carrega_sob_demanda(self, db: Session):
        db.expunge_all()
        atendimento = db.execute(
            select(Atendimento).order_by(Atendimento.id_atendimento).limit(1)
        ).scalar()
        assert atendimento is not None
        # Acesso ao paciente dispara consulta sob demanda
        nome = atendimento.paciente.pessoa.nome
        assert nome is not None and len(nome) > 0

    def test_selectinload_para_colecoes(self, db: Session):
        stmt = (
            select(Atendimento)
            .options(
                selectinload(Atendimento.procedimentos_realizados).joinedload(
                    ProcedimentoRealizado.procedimento
                )
            )
            .order_by(Atendimento.id_atendimento)
            .limit(5)
        )
        resultados = db.execute(stmt).unique().scalars().all()
        for a in resultados:
            for pr in a.procedimentos_realizados:
                assert pr.procedimento.nome is not None


class TestOrmRelacionamentos:
    """Verifica que os relacionamentos bidirecionais funcionam."""

    def test_paciente_tem_atendimentos(self, db: Session):
        paciente = db.get(Paciente, 1)
        assert paciente is not None
        assert len(paciente.atendimentos) >= 1

    def test_preceptor_tem_escalas(self, db: Session):
        prec = db.get(Preceptor, 6)
        assert prec is not None
        assert len(prec.escalas) >= 1

    def test_residente_tem_escalas(self, db: Session):
        res = db.get(Residente, 11)
        assert res is not None
        assert len(res.escalas) >= 1

    def test_unidade_tem_escalas(self, db: Session):
        uni = db.get(Unidade, 1)
        assert uni is not None
        assert len(uni.escalas) >= 1


class TestOrmTransacoes:
    """Uso de transações via ORM (commit/rollback)."""

    def test_commit_persiste_dados(self, db: Session):
        pessoa = Pessoa(
            CPF="21212121212",
            nome="Transacao Teste",
            data_nascimento=date(1990, 1, 1),
        )
        db.add(pessoa)
        db.commit()
        carregado = db.get(Pessoa, pessoa.id_pessoa)
        assert carregado is not None

    def test_rollback_descarta_alteracoes(self, db: Session):
        pessoa = Pessoa(
            CPF="22222222200",
            nome="Rollback Teste",
            data_nascimento=date(1990, 1, 1),
        )
        db.add(pessoa)
        db.flush()
        id_p = pessoa.id_pessoa
        db.rollback()

        db_releitura = db.get(Pessoa, id_p)
        assert db_releitura is None


# ═══════════════════════════════════════════════════════════════════════
# Item 5: Consultas avançadas com a DSL da ORM
# ═══════════════════════════════════════════════════════════════════════


class TestAnaliticasEtapa1Orm:
    """Item 4: Consultas analíticas da Etapa 1, reimplementadas via ORM DSL."""

    def test_ranking_residentes(self, db: Session):
        resultado = ranking_residentes(db)
        assert len(resultado) == 5
        nomes = [r["nome"] for r in resultado]
        assert "Karina Duarte" in nomes
        for r in resultado:
            assert r["total_atendimentos"] >= 0

    def test_preceptores_acima_de_cinco(self, db: Session):
        resultado = preceptores_acima_de(db, date(2026, 7, 15), minimo=5)
        assert len(resultado) >= 1
        fernando = [r for r in resultado if r["nome"] == "Fernando Alves"]
        assert len(fernando) == 1
        assert fernando[0]["total_supervisionados"] == 6

    def test_preceptores_abaixo_do_limite_ignorados(self, db: Session):
        resultado = preceptores_acima_de(db, date(2026, 6, 1), minimo=10)
        assert len(resultado) == 0

    def test_plantoes_por_unidade_semanal(self, db: Session):
        resultado = plantoes_por_unidade_semanal(db)
        assert len(resultado) >= 5
        for r in resultado:
            assert "unidade" in r
            assert "residente" in r
            assert r["plantoes_semanais"] >= 1

    def test_plantoes_por_unidade_no_mes(self, db: Session):
        resultado = plantoes_por_unidade_no_mes(db)
        assert len(resultado) >= 5

    def test_pacientes_sem_alto_risco(self, db: Session):
        resultado = pacientes_sem_procedimento_de_alto_risco(db)
        assert len(resultado) >= 1
        nomes = [r["nome"] for r in resultado]
        assert "Ana Souza" in nomes or "Bruno Lima" in nomes


class TestConsultasAvancadas:
    """As 3 consultas do item 5, mais lazy vs eager."""

    def test_preceptores_de_flamenguistas(self, db: Session):
        resultado = preceptores_de_pacientes_flamenguistas(db)
        nomes = {r["preceptor"] for r in resultado}
        assert len(nomes) == 4
        assert "Fernando Alves" in nomes
        assert "Gabriela Pinto" in nomes
        assert "Henrique Costa" in nomes
        assert "Isabela Martins" in nomes
        assert "Joao Nogueira" not in nomes

        for r in resultado:
            assert r["atendimentos_com_flamenguista"] >= 1

    def test_ultimo_atendimento_por_paciente(self, db: Session):
        resultado = ultimo_atendimento_por_paciente(db)
        assert len(resultado) == 5

        pacientes = {r["paciente"] for r in resultado}
        assert "Ana Souza" in pacientes
        assert "Bruno Lima" in pacientes
        assert "Carla Mendes" in pacientes
        assert "Diego Ferreira" in pacientes
        assert "Elisa Rocha" in pacientes

        for r in resultado:
            assert r["data_hora"] is not None
            assert r["residente"] is not None
            assert r["preceptor"] is not None
            assert isinstance(r["procedimentos"], list)

        ana = [r for r in resultado if r["paciente"] == "Ana Souza"][0]
        assert ana["data_hora"].date() == date(2026, 7, 20)

    def test_percentual_alto_risco(self, db: Session):
        resultado = percentual_alto_risco_por_residente(db)
        assert len(resultado) == 5

        mariana = [r for r in resultado if r["residente"] == "Mariana Teles"][0]
        assert mariana["total_procedimentos"] == 5
        assert mariana["procedimentos_alto_risco"] == 2
        assert float(mariana["percentual_alto_risco"]) == pytest.approx(40.0, abs=0.1)

        karina = [r for r in resultado if r["residente"] == "Karina Duarte"][0]
        assert karina["total_procedimentos"] == 6
        assert karina["procedimentos_alto_risco"] == 2
        assert float(karina["percentual_alto_risco"]) == pytest.approx(33.33, abs=0.1)

        nathan = [r for r in resultado if r["residente"] == "Nathan Ribeiro"][0]
        assert nathan["procedimentos_alto_risco"] == 0
        assert float(nathan["percentual_alto_risco"]) == 0.0


class TestConsultasAvancadasEstrutura:
    """Verifica a estrutura/colunas de cada consulta."""

    def test_preceptores_flamenguistas_colunas(self, db: Session):
        resultado = preceptores_de_pacientes_flamenguistas(db)
        if resultado:
            r = resultado[0]
            assert "id_preceptor" in r
            assert "preceptor" in r
            assert "titulacao" in r
            assert "especialidade" in r
            assert "atendimentos_com_flamenguista" in r
            assert "residentes_supervisionados" in r

    def test_ultimo_atendimento_colunas(self, db: Session):
        resultado = ultimo_atendimento_por_paciente(db)
        if resultado:
            r = resultado[0]
            assert "id_paciente" in r
            assert "paciente" in r
            assert "id_atendimento" in r
            assert "data_hora" in r
            assert "duracao_minutos" in r
            assert "residente" in r
            assert "preceptor" in r
            assert "procedimentos" in r
            for p in r["procedimentos"]:
                assert "nome" in p
                assert "nivel_risco" in p
                assert "quantidade" in p

    def test_percentual_alto_risco_colunas(self, db: Session):
        resultado = percentual_alto_risco_por_residente(db)
        if resultado:
            r = resultado[0]
            assert "id_residente" in r
            assert "residente" in r
            assert "ano_residencia" in r
            assert "total_procedimentos" in r
            assert "procedimentos_alto_risco" in r
            assert "percentual_alto_risco" in r


# ═══════════════════════════════════════════════════════════════════════
# Item 6: Concorrência — 3 cenários
# ═══════════════════════════════════════════════════════════════════════


class TestConcorrencia:
    """Simulação de duas transações disputando a mesma escala."""

    def test_simulacao_retorna_tres_cenarios(self):
        resultado = simular()
        assert len(resultado["cenarios"]) == 3

    def test_sem_protecao_conflito_evitado(self):
        resultado = simular()
        sem = resultado["cenarios"][0]
        assert sem["cenario"] == "sem proteção explícita"
        assert sem["conflito_evitado"] is True
        assert len(sem["log"]) >= 4
        # Apenas uma transação gravou
        desfecho = sem["desfecho"]
        assert "1 transação gravou" in desfecho

    def test_lock_pessimista_conflito_evitado(self):
        resultado = simular()
        pes = resultado["cenarios"][1]
        assert pes["cenario"] == "lock pessimista"
        assert pes["conflito_evitado"] is True
        assert any("SELECT" in entrada["mensagem"] or "FOR UPDATE" in entrada["mensagem"]
                   for entrada in pes["log"])

    def test_lock_otimista_conflito_evitado(self):
        resultado = simular()
        oti = resultado["cenarios"][2]
        assert oti["cenario"] == "lock otimista"
        assert oti["conflito_evitado"] is True
        assert any("StaleDataError" in entrada["mensagem"] or "versão mudou" in entrada["mensagem"]
                   for entrada in oti["log"])

    def test_logs_capturam_disputa(self):
        resultado = simular()
        for cenario in resultado["cenarios"]:
            atores = {entrada["ator"] for entrada in cenario["log"]}
            assert "sessao A" in atores or len(cenario["log"]) > 0

    def test_todos_tres_cenarios_evitam_inconsistencia(self):
        resultado = simular()
        todos_ok = all(c["conflito_evitado"] for c in resultado["cenarios"])
        assert todos_ok, (
            "Pelo menos um cenário não evitou a inconsistência: "
            + "; ".join(f"{c['cenario']}={c['conflito_evitado']}" for c in resultado["cenarios"])
        )

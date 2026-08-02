"""Fixtures para a bateria de testes da Etapa 2.

Cada teste roda dentro de uma transação no nível da conexão. Ao fim do teste a
transação sofre ROLLBACK: nenhum dado gravado nos testes contamina o banco.
Para testar cenários de erro que abortam a transação (RAISE EXCEPTION nas
procedures, violações de constraint nos triggers), savepoints protegem a
transação externa que os testes veem.
"""

from __future__ import annotations

import os
import sys
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hospital_universitario")
_SKIP_REASON = (
    f"Banco de testes indisponivel em {_URL}. "
    "Suba com: docker compose up -d"
)


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Engine compartilhado por toda a sessão de testes."""
    try:
        eng = create_engine(_URL, connect_args={"connect_timeout": 3})
        eng.connect().close()
        return eng
    except Exception:
        pytest.skip(_SKIP_REASON)


@pytest.fixture
def db(engine: Engine) -> Generator[Session, None, None]:
    """Sessão ORM isolada por teste.

    Tudo que o teste gravar dentro desta sessão é desfeito no ROLLBACK final,
    inclusive o que a aplicação gravar via CALL de stored procedures.
    """
    connection = engine.connect()
    transacao = connection.begin()
    sessao = Session(bind=connection, autoflush=False, autocommit=False)
    try:
        yield sessao
    finally:
        sessao.close()
        if transacao.is_active:
            transacao.rollback()
        connection.close()


@pytest.fixture
def sp(db: Session) -> Generator[callable, None, None]:
    """Helper que executa CALL dentro de um savepoint.

    Quando o teste espera um erro (RAISE EXCEPTION da procedure), ele precisa
    que a transação principal não seja abortada. O savepoint resolve: o erro
    consome o savepoint, a transação externa continua viva e o rollback final
    funciona.
    """

    def chamar(sql: str, **params) -> dict | None:
        db.execute(text("SAVEPOINT antes_do_call"))
        try:
            result = db.execute(text(sql), params)
            db.execute(text("RELEASE SAVEPOINT antes_do_call"))
            if result.returns_rows:
                linhas = [dict(linha._mapping) for linha in result]
                return linhas[0] if len(linhas) == 1 else linhas
            return None
        except Exception:
            db.execute(text("ROLLBACK TO SAVEPOINT antes_do_call"))
            raise

    yield chamar


@pytest.fixture
def sql(db: Session) -> Generator[callable, None, None]:
    """Helper para executar SQL textual simples."""

    def executar(sql_str: str, **params):
        result = db.execute(text(sql_str), params)
        if result.returns_rows:
            return [dict(linha._mapping) for linha in result]
        return None

    yield executar


# Valores fixos que correspondem aos dados do seed (02 + 09).
@pytest.fixture
def seed() -> dict:
    return {
        "paciente_flamenguista": 1,             # Ana Souza
        "paciente_nao_flamenguista": 2,         # Bruno Lima
        "paciente_internado": 3,                # Carla Mendes
        "paciente_flamenguista_2": 4,           # Diego Ferreira
        "paciente_internado_2": 5,              # Elisa Rocha
        "preceptor_doutor": 6,                  # Fernando Alves
        "preceptor_mestre": 7,                  # Gabriela Pinto
        "preceptor_doutor_2": 8,                # Henrique Costa
        "preceptor_especialista": 9,            # Isabela Martins (não-doutor)
        "preceptor_mestre_2": 10,               # Joao Nogueira (não-doutor)
        "residente_1": 11,                      # Karina Duarte (R1)
        "residente_2": 12,                      # Lucas Barbosa (R2)
        "residente_3": 13,                      # Mariana Teles (R3)
        "residente_4": 14,                      # Nathan Ribeiro (R1)
        "residente_5": 15,                      # Olivia Prado (R2)
        "unidade_enfermaria": 1,
        "unidade_uti": 2,
        "unidade_ps": 3,
        "unidade_amb": 4,
        "procedimento_alto_risco": 5,           # Intubacao (ALTO)
        "procedimento_baixo_risco": 2,          # Coleta de sangue (BAIXO)
        "procedimento_medio_risco": 1,          # Sutura (MEDIO)
        "total_pessoas": 15,
        "total_atendimentos": 15,
        "total_escalas": 10,
    }

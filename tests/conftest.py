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
from collections.abc import Callable, Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DEFAULT_TEST_DATABASE_URL = (
    "postgresql://postgres:postgres@localhost:5434/hospital_universitario"
)


def _carregar_url_de_teste() -> str:
    """Obtém e valida a conexão antes que qualquer fixture abra um socket.

    A porta 5432 local pertence ao ambiente normal do projeto. Mesmo que alguém
    copie essa URL para TEST_DATABASE_URL, a suíte para durante a carga do
    conftest, antes de importar a aplicação ou executar uma consulta.
    """

    valor = os.getenv("TEST_DATABASE_URL") or _DEFAULT_TEST_DATABASE_URL
    try:
        url = make_url(valor)
    except Exception as erro:
        raise pytest.UsageError(f"TEST_DATABASE_URL inválida: {erro}") from erro

    if not url.drivername.startswith("postgresql"):
        raise pytest.UsageError(
            "TEST_DATABASE_URL deve apontar para um PostgreSQL isolado de testes."
        )

    host = (url.host or "localhost").strip("[]").lower()
    porta = url.port or 5432
    hosts_locais = {"localhost", "127.0.0.1", "::1"}
    if host not in hosts_locais or porta != 5434:
        raise pytest.UsageError(
            "Execução recusada: TEST_DATABASE_URL deve apontar exclusivamente "
            "para o PostgreSQL descartável em localhost:5434. A porta 5432 e "
            "hosts remotos/produção nunca são aceitos pela suíte."
        )

    return valor


TEST_DATABASE_URL = _carregar_url_de_teste()
# Mantém uma única fonte para fixtures, a aplicação e módulos auxiliares.
# Isto ocorre antes da coleta importar main/database/concorrencia, portanto até
# engines globais nascem apontando para o banco descartável.
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
_SKIP_REASON = (
    f"Banco de testes indisponivel em {TEST_DATABASE_URL}. "
    "Suba com: docker compose -f docker-compose.test.yml up -d --wait"
)


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """Engine compartilhado por toda a sessão de testes."""
    try:
        eng = create_engine(
            TEST_DATABASE_URL,
            connect_args={"connect_timeout": 3},
            pool_pre_ping=True,
        )
        eng.connect().close()
    except Exception as erro:
        raise pytest.UsageError(_SKIP_REASON) from erro
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def test_session_factory(engine: Engine):
    """Vincula aplicação e simulação concorrente somente ao engine de teste."""

    import concorrencia
    import database

    factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    anteriores = {
        "engine": database.engine,
        "SessionLocal": database.SessionLocal,
        "SessionORM": database.SessionORM,
        "concorrencia_SessionORM": concorrencia.SessionORM,
    }
    database.engine = engine
    database.SessionLocal = factory
    database.SessionORM = factory
    concorrencia.SessionORM = factory
    try:
        yield factory
    finally:
        concorrencia.SessionORM = anteriores["concorrencia_SessionORM"]
        database.SessionORM = anteriores["SessionORM"]
        database.SessionLocal = anteriores["SessionLocal"]
        database.engine = anteriores["engine"]


@pytest.fixture
def db(engine: Engine) -> Generator[Session, None, None]:
    """Sessão ORM isolada por teste.

    Tudo que o teste gravar dentro desta sessão é desfeito no ROLLBACK final,
    inclusive o que a aplicação gravar via CALL de stored procedures.
    """
    connection = engine.connect()
    transacao = connection.begin()
    sessao = Session(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield sessao
    finally:
        sessao.close()
        if transacao.is_active:
            transacao.rollback()
        connection.close()


@pytest.fixture
def sp(db: Session) -> Generator[Callable[..., object], None, None]:
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
def sql(db: Session) -> Generator[Callable[..., object], None, None]:
    """Helper para executar SQL textual simples."""

    def executar(sql_str: str, **params):
        result = db.execute(text(sql_str), params)
        if result.returns_rows:
            return [dict(linha._mapping) for linha in result]
        return None

    yield executar


@pytest.fixture
def client(db: Session):
    """TestClient cuja injeção de sessão participa do rollback do teste."""

    from fastapi.testclient import TestClient

    import database
    from main import app

    def override_db():
        yield db

    app.dependency_overrides[database.get_db] = override_db
    app.dependency_overrides[database.get_orm_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


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

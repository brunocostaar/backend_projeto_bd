"""Sessão do SQLAlchemy usada pela camada ORM da Etapa 2.

O engine é o mesmo do database.py, criado uma vez para todo o processo. Reusar
o engine significa reusar o pool de conexões: as rotas em SQL puro da Etapa 1 e
as rotas com ORM da Etapa 2 disputam as mesmas conexões, em vez de abrir dois
pools contra o mesmo banco.

A diferença entre as duas camadas está no que a sessão faz, não na conexão. Em
routers/, a sessão só transporta text() para o banco. Aqui ela mantém o mapa de
identidade, acompanha as mudanças dos objetos e decide quando emitir INSERT,
UPDATE e DELETE.
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from database import engine

SessionORM = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_orm_db() -> Iterator[Session]:
    """Injeção de dependência das rotas com ORM.

    Sem commit automático no fim: cada rota decide quando confirmar. O finally
    devolve a conexão ao pool mesmo quando a rota levanta exceção, e o rollback
    implícito do close() descarta o que não foi confirmado.
    """
    db = SessionORM()
    try:
        yield db
    finally:
        db.close()

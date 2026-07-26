"""Escalas com ORM (Etapa 2). Espelha routers/escala.py.

A Etapa 1 conferia o conflito com um SELECT antes do INSERT. Aqui a checagem
prévia sai: quem recusa é o banco, pela UNIQUE do esquema e pelo
trg_check_sobreposicao_escala. A tradução do erro em 409 fica em comum.py, que
mapeia o SQLSTATE devolvido.

O motivo da mudança é a corrida entre o SELECT e o INSERT. Duas requisições
simultâneas podem passar as duas pela verificação antes de qualquer uma gravar;
a restrição no banco não tem esse buraco. O item 6 da Etapa 2 mede isso.

A resposta traz a coluna versao, usada no controle de concorrência otimista.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from orm.modelos import Escala, Preceptor, Residente, Unidade
from orm.sessao import get_orm_db
from routers_orm.comum import confirmar, nao_encontrado
from schemas.etapa2 import EscalaOrmCreate, EscalaOrmRead

router = APIRouter(prefix="/orm/escalas", tags=["ORM - Escalas"])


def _validar_referencias(db: Session, dados: EscalaOrmCreate) -> None:
    if db.get(Unidade, dados.id_unidade) is None:
        raise nao_encontrado(f"Unidade {dados.id_unidade} não existe.")
    if db.get(Residente, dados.id_residente) is None:
        raise nao_encontrado(f"Residente {dados.id_residente} não existe.")
    if db.get(Preceptor, dados.id_preceptor) is None:
        raise nao_encontrado(f"Preceptor {dados.id_preceptor} não existe.")


def _buscar(db: Session, id_escala: int) -> Escala:
    escala = db.get(Escala, id_escala)
    if escala is None:
        raise nao_encontrado("Escala não encontrada.")
    return escala


@router.post("/", response_model=EscalaOrmRead, status_code=status.HTTP_201_CREATED)
def criar_escala(dados: EscalaOrmCreate, db: Session = Depends(get_orm_db)):
    """Cria a escala. Conflito de dia/turno vira 409, vindo do trigger."""
    _validar_referencias(db, dados)
    escala = Escala(**dados.model_dump())
    db.add(escala)
    confirmar(db)
    return escala


@router.get("/", response_model=list[EscalaOrmRead])
def listar_escalas(
    id_unidade: int | None = None,
    id_residente: int | None = None,
    id_preceptor: int | None = None,
    dia_semana: str | None = None,
    turno: str | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = select(Escala)
    if id_unidade is not None:
        stmt = stmt.where(Escala.id_unidade == id_unidade)
    if id_residente is not None:
        stmt = stmt.where(Escala.id_residente == id_residente)
    if id_preceptor is not None:
        stmt = stmt.where(Escala.id_preceptor == id_preceptor)
    if dia_semana:
        stmt = stmt.where(Escala.dia_semana == dia_semana)
    if turno:
        stmt = stmt.where(Escala.turno == turno)
    stmt = stmt.order_by(Escala.id_unidade, Escala.dia_semana, Escala.turno)
    return list(db.execute(stmt).scalars())


@router.get("/{id_escala}", response_model=EscalaOrmRead)
def buscar_escala(id_escala: int, db: Session = Depends(get_orm_db)):
    return _buscar(db, id_escala)


@router.put("/{id_escala}", response_model=EscalaOrmRead)
def atualizar_escala(
    id_escala: int, dados: EscalaOrmCreate, db: Session = Depends(get_orm_db)
):
    """Atualiza a escala com verificação otimista de versão.

    O UPDATE gerado inclui a versão lida no WHERE. Se outra transação alterou a
    mesma escala nesse intervalo, nenhuma linha casa e o SQLAlchemy levanta
    StaleDataError, que vira 409 em vez de sobrescrever silenciosamente.
    """
    escala = _buscar(db, id_escala)
    _validar_referencias(db, dados)
    for campo, valor in dados.model_dump().items():
        setattr(escala, campo, valor)
    try:
        confirmar(db)
    except StaleDataError as erro:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Esta escala foi alterada por outra operação depois que você a "
                "carregou. Recarregue e tente de novo."
            ),
        ) from erro
    return escala


@router.delete("/{id_escala}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_escala(id_escala: int, db: Session = Depends(get_orm_db)):
    db.delete(_buscar(db, id_escala))
    confirmar(db)
    return None

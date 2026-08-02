"""Procedimentos com ORM (Etapa 2).

A resposta inclui media_tempo_procedimento, coluna que o
trg_atualiza_media_procedimentos mantém. Nenhuma rota daqui escreve nesse campo:
quem o atualiza é o banco, a cada procedimento realizado.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from modelos import Procedimento
from database import get_orm_db
from routers.comum import confirmar, nao_encontrado
from schemas.etapa2 import ProcedimentoOrmRead
from schemas.procedimento import ProcedimentoCreate

router = APIRouter(prefix="/procedimentos", tags=["Procedimentos"])


def _buscar(db: Session, id_procedimento: int) -> Procedimento:
    procedimento = db.get(Procedimento, id_procedimento)
    if procedimento is None:
        raise nao_encontrado("Procedimento não encontrado.")
    return procedimento


@router.post("/", response_model=ProcedimentoOrmRead, status_code=status.HTTP_201_CREATED)
def criar_procedimento(dados: ProcedimentoCreate, db: Session = Depends(get_orm_db)):
    procedimento = Procedimento(**dados.model_dump())
    db.add(procedimento)
    confirmar(db)
    return procedimento


@router.get("/", response_model=list[ProcedimentoOrmRead])
def listar_procedimentos(
    nome: str | None = None,
    nivel_risco: str | None = None,
    codigo: int | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = select(Procedimento)
    if nome:
        stmt = stmt.where(Procedimento.nome.ilike(f"%{nome}%"))
    if nivel_risco:
        stmt = stmt.where(Procedimento.nivel_risco == nivel_risco)
    if codigo is not None:
        stmt = stmt.where(Procedimento.codigo == codigo)
    return list(db.execute(stmt.order_by(Procedimento.nome)).scalars())


@router.get("/{id_procedimento}", response_model=ProcedimentoOrmRead)
def buscar_procedimento(id_procedimento: int, db: Session = Depends(get_orm_db)):
    return _buscar(db, id_procedimento)


@router.put("/{id_procedimento}", response_model=ProcedimentoOrmRead)
def atualizar_procedimento(
    id_procedimento: int, dados: ProcedimentoCreate, db: Session = Depends(get_orm_db)
):
    procedimento = _buscar(db, id_procedimento)
    for campo, valor in dados.model_dump().items():
        setattr(procedimento, campo, valor)
    confirmar(db)
    return procedimento


@router.delete("/{id_procedimento}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_procedimento(id_procedimento: int, db: Session = Depends(get_orm_db)):
    db.delete(_buscar(db, id_procedimento))
    confirmar(db)
    return None

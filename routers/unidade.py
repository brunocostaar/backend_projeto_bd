"""Unidades com ORM (Etapa 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from modelos import Unidade
from database import get_orm_db
from routers.comum import confirmar, nao_encontrado
from schemas.unidade import UnidadeCreate, UnidadeRead

router = APIRouter(prefix="/unidades", tags=["Unidades"])


def _buscar(db: Session, id_unidade: int) -> Unidade:
    unidade = db.get(Unidade, id_unidade)
    if unidade is None:
        raise nao_encontrado("Unidade não encontrada.")
    return unidade


@router.post("/", response_model=UnidadeRead, status_code=status.HTTP_201_CREATED)
def criar_unidade(dados: UnidadeCreate, db: Session = Depends(get_orm_db)):
    unidade = Unidade(**dados.model_dump())
    db.add(unidade)
    confirmar(db)
    return unidade


@router.get("/", response_model=list[UnidadeRead])
def listar_unidades(
    nome: str | None = None,
    tipo: str | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = select(Unidade)
    if nome:
        stmt = stmt.where(Unidade.nome.ilike(f"%{nome}%"))
    if tipo:
        stmt = stmt.where(Unidade.tipo.ilike(f"%{tipo}%"))
    return list(db.execute(stmt.order_by(Unidade.nome)).scalars())


@router.get("/{id_unidade}", response_model=UnidadeRead)
def buscar_unidade(id_unidade: int, db: Session = Depends(get_orm_db)):
    return _buscar(db, id_unidade)


@router.put("/{id_unidade}", response_model=UnidadeRead)
def atualizar_unidade(
    id_unidade: int, dados: UnidadeCreate, db: Session = Depends(get_orm_db)
):
    unidade = _buscar(db, id_unidade)
    for campo, valor in dados.model_dump().items():
        setattr(unidade, campo, valor)
    confirmar(db)
    return unidade


@router.delete("/{id_unidade}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_unidade(id_unidade: int, db: Session = Depends(get_orm_db)):
    db.delete(_buscar(db, id_unidade))
    confirmar(db)
    return None

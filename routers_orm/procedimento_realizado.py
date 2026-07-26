"""Procedimentos realizados com ORM (Etapa 2).

Espelha routers/procedimento_realizado.py, incluindo a regra de faturamento, e
acrescenta data_hora_inicio, usada por sp_calcular_tempo_medio_espera.

Toda escrita aqui dispara o trigger que recalcula
procedimento.media_tempo_procedimento.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from orm.modelos import Atendimento, Procedimento, ProcedimentoRealizado
from orm.sessao import get_orm_db
from routers_orm.comum import confirmar, nao_encontrado
from schemas.etapa2 import (
    ProcedimentoRealizadoOrmBase,
    ProcedimentoRealizadoOrmCreate,
    ProcedimentoRealizadoOrmRead,
)

router = APIRouter(
    prefix="/orm/procedimentos-realizados", tags=["ORM - Procedimentos Realizados"]
)


def _para_dict(registro: ProcedimentoRealizado) -> dict:
    return {
        "id_atendimento": registro.id_atendimento,
        "id_procedimento": registro.id_procedimento,
        "quantidade": registro.quantidade,
        "tempo_real_minutos": registro.tempo_real_minutos,
        "observacao": registro.observacao,
        "faturado": registro.faturado,
        "data_hora_inicio": registro.data_hora_inicio,
        "nome_procedimento": registro.procedimento.nome if registro.procedimento else None,
        "nivel_risco": registro.procedimento.nivel_risco if registro.procedimento else None,
    }


def _buscar(db: Session, id_atendimento: int, id_procedimento: int) -> ProcedimentoRealizado:
    # A chave primária é composta: db.get recebe a tupla na ordem em que as
    # colunas foram declaradas no modelo.
    registro = db.get(ProcedimentoRealizado, (id_atendimento, id_procedimento))
    if registro is None:
        raise nao_encontrado("Esse procedimento não está registrado para este atendimento.")
    return registro


@router.post("/", response_model=ProcedimentoRealizadoOrmRead, status_code=status.HTTP_201_CREATED)
def registrar(dados: ProcedimentoRealizadoOrmCreate, db: Session = Depends(get_orm_db)):
    if db.get(Atendimento, dados.id_atendimento) is None:
        raise nao_encontrado(f"Atendimento {dados.id_atendimento} não existe.")
    if db.get(Procedimento, dados.id_procedimento) is None:
        raise nao_encontrado(f"Procedimento {dados.id_procedimento} não existe.")
    if db.get(ProcedimentoRealizado, (dados.id_atendimento, dados.id_procedimento)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este procedimento já está registrado neste atendimento. "
                "Repetições do mesmo procedimento vão na coluna quantidade."
            ),
        )

    registro = ProcedimentoRealizado(**dados.model_dump())
    db.add(registro)
    confirmar(db)
    db.refresh(registro)
    return _para_dict(registro)


@router.get("/", response_model=list[ProcedimentoRealizadoOrmRead])
def listar(
    id_atendimento: int | None = None,
    id_procedimento: int | None = None,
    faturado: bool | None = None,
    nivel_risco: str | None = None,
    db: Session = Depends(get_orm_db),
):
    """O nome do procedimento vem do relacionamento, não de um JOIN escrito à mão."""
    stmt = (
        select(ProcedimentoRealizado)
        .join(ProcedimentoRealizado.procedimento)
        .options(contains_eager(ProcedimentoRealizado.procedimento))
    )
    if id_atendimento is not None:
        stmt = stmt.where(ProcedimentoRealizado.id_atendimento == id_atendimento)
    if id_procedimento is not None:
        stmt = stmt.where(ProcedimentoRealizado.id_procedimento == id_procedimento)
    if faturado is not None:
        stmt = stmt.where(ProcedimentoRealizado.faturado.is_(faturado))
    if nivel_risco:
        stmt = stmt.where(Procedimento.nivel_risco == nivel_risco)
    stmt = stmt.order_by(
        ProcedimentoRealizado.id_atendimento, ProcedimentoRealizado.id_procedimento
    )

    return [_para_dict(r) for r in db.execute(stmt).unique().scalars()]


@router.get("/{id_atendimento}/{id_procedimento}", response_model=ProcedimentoRealizadoOrmRead)
def buscar(id_atendimento: int, id_procedimento: int, db: Session = Depends(get_orm_db)):
    return _para_dict(_buscar(db, id_atendimento, id_procedimento))


@router.put("/{id_atendimento}/{id_procedimento}", response_model=ProcedimentoRealizadoOrmRead)
def atualizar(
    id_atendimento: int,
    id_procedimento: int,
    dados: ProcedimentoRealizadoOrmBase,
    db: Session = Depends(get_orm_db),
):
    """Corrigir o tempo real recalcula a média do procedimento, via trigger."""
    registro = _buscar(db, id_atendimento, id_procedimento)
    for campo, valor in dados.model_dump().items():
        setattr(registro, campo, valor)
    confirmar(db)
    db.refresh(registro)
    return _para_dict(registro)


@router.delete("/{id_atendimento}/{id_procedimento}", status_code=status.HTTP_204_NO_CONTENT)
def remover(id_atendimento: int, id_procedimento: int, db: Session = Depends(get_orm_db)):
    """Procedimento já faturado não sai. Mesma regra da Etapa 1."""
    registro = _buscar(db, id_atendimento, id_procedimento)
    if registro.faturado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este procedimento realizado já foi faturado e não pode ser removido.",
        )
    db.delete(registro)
    confirmar(db)
    return None

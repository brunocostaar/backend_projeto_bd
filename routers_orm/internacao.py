"""Internações (Etapa 2).

Entidade nova, sem equivalente na Etapa 1. Ela existe porque a
vw_pacientes_internados precisa de algum lugar de onde tirar quem está internado.

Regra que o banco garante: um paciente não pode ter duas internações abertas ao
mesmo tempo. Quem impede é o índice parcial uq_internacao_aberta, criado em
05_etapa2_estrutura.sql, que só vale para as linhas com data_hora_saida nula.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from orm.modelos import Internacao, Paciente, Unidade
from orm.sessao import get_orm_db
from routers_orm.comum import confirmar, nao_encontrado
from schemas.internacao import InternacaoAlta, InternacaoCreate, InternacaoRead

router = APIRouter(prefix="/orm/internacoes", tags=["ORM - Internações"])


def _buscar(db: Session, id_internacao: int) -> Internacao:
    internacao = db.get(Internacao, id_internacao)
    if internacao is None:
        raise nao_encontrado("Internação não encontrada.")
    return internacao


@router.post("/", response_model=InternacaoRead, status_code=status.HTTP_201_CREATED)
def internar(dados: InternacaoCreate, db: Session = Depends(get_orm_db)):
    if db.get(Paciente, dados.id_paciente) is None:
        raise nao_encontrado(f"Paciente {dados.id_paciente} não existe.")
    if db.get(Unidade, dados.id_unidade) is None:
        raise nao_encontrado(f"Unidade {dados.id_unidade} não existe.")

    internacao = Internacao(**dados.model_dump())
    db.add(internacao)
    # O índice parcial recusa a segunda internação aberta; comum.confirmar
    # transforma a violação de unicidade em 409.
    confirmar(db)
    return internacao


@router.get("/", response_model=list[InternacaoRead])
def listar_internacoes(
    id_paciente: int | None = None,
    id_unidade: int | None = None,
    apenas_abertas: bool = False,
    db: Session = Depends(get_orm_db),
):
    stmt = select(Internacao)
    if id_paciente is not None:
        stmt = stmt.where(Internacao.id_paciente == id_paciente)
    if id_unidade is not None:
        stmt = stmt.where(Internacao.id_unidade == id_unidade)
    if apenas_abertas:
        stmt = stmt.where(Internacao.data_hora_saida.is_(None))
    stmt = stmt.order_by(Internacao.data_hora_entrada.desc())
    return list(db.execute(stmt).scalars())


@router.get("/{id_internacao}", response_model=InternacaoRead)
def buscar_internacao(id_internacao: int, db: Session = Depends(get_orm_db)):
    return _buscar(db, id_internacao)


@router.post("/{id_internacao}/alta", response_model=InternacaoRead)
def dar_alta(
    id_internacao: int,
    dados: InternacaoAlta | None = None,
    db: Session = Depends(get_orm_db),
):
    """Encerra a internação. Sem data no corpo, usa o instante da chamada.

    Depois da alta o paciente sai da vw_pacientes_internados e pode ser internado
    de novo, porque o índice parcial só olha as internações abertas.
    """
    internacao = _buscar(db, id_internacao)
    if internacao.data_hora_saida is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Internação já encerrada em {internacao.data_hora_saida}.",
        )

    saida = (dados.data_hora_saida if dados else None) or datetime.now()
    if saida <= internacao.data_hora_entrada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A saída precisa ser posterior à entrada.",
        )

    internacao.data_hora_saida = saida
    confirmar(db)
    return internacao


@router.put("/{id_internacao}", response_model=InternacaoRead)
def atualizar_internacao(
    id_internacao: int, dados: InternacaoCreate, db: Session = Depends(get_orm_db)
):
    internacao = _buscar(db, id_internacao)
    for campo, valor in dados.model_dump().items():
        setattr(internacao, campo, valor)
    confirmar(db)
    return internacao


@router.delete("/{id_internacao}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_internacao(id_internacao: int, db: Session = Depends(get_orm_db)):
    db.delete(_buscar(db, id_internacao))
    confirmar(db)
    return None

"""Escalas com ORM (Etapa 2).

Inclui reajuste de escala, antes em /etapa2/procedures/reajustar-escala.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from modelos import Escala, Preceptor, Residente, Unidade
from database import get_orm_db
from routers.comum import confirmar, erro_do_banco, nao_encontrado
from schemas.etapa2 import (
    EscalaOrmCreate,
    EscalaOrmRead,
    EscalaReajustada,
    ReajustarEscala,
)

router = APIRouter(prefix="/escalas", tags=["Escalas"])


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


# ---------------------------------------------------------------------------
# Reajuste de escala (antes em /etapa2/procedures/reajustar-escala)
# ---------------------------------------------------------------------------


@router.post("/reajustar", response_model=EscalaReajustada)
def reajustar_escala(dados: ReajustarEscala, db: Session = Depends(get_orm_db)):
    comando = text(
        """
        CALL sp_reajustar_escala(
            :id_residente, :dia_origem, :turno_origem,
            :dia_destino, :turno_destino, NULL
        )
        """
    )
    try:
        resultado = db.execute(comando, dados.model_dump())
        movidas = 0
        if resultado.returns_rows:
            linha = resultado.fetchone()
            if linha is not None and linha[0] is not None:
                movidas = int(linha[0])
        db.commit()
    except DBAPIError as erro:
        db.rollback()
        raise erro_do_banco(erro) from erro

    if movidas == 0:
        mensagem = (
            f"O residente {dados.id_residente} não tem plantão em "
            f"{dados.dia_origem} {dados.turno_origem}. Nada foi alterado."
        )
    else:
        quantos = "1 plantão movido" if movidas == 1 else f"{movidas} plantões movidos"
        mensagem = (
            f"{quantos} de {dados.dia_origem} {dados.turno_origem} "
            f"para {dados.dia_destino} {dados.turno_destino}."
        )
    return {"escalas_movidas": movidas, "mensagem": mensagem}

"""Auditoria de atendimentos (Etapa 2).

O trg_audita_atendimento escreve nesta tabela. A aplicação nunca insere
diretamente: toda linha foi posta pelo trigger.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from modelos import AuditoriaAtendimento
from database import get_orm_db
from schemas.etapa2 import AuditoriaRead

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


@router.get("/atendimentos", response_model=list[AuditoriaRead])
def listar_auditoria(
    id_atendimento: int | None = None,
    operacao: str | None = Query(None, pattern="^(INSERT|UPDATE|DELETE)$"),
    limite: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_orm_db),
):
    stmt = select(AuditoriaAtendimento)
    if id_atendimento is not None:
        stmt = stmt.where(AuditoriaAtendimento.id_atendimento == id_atendimento)
    if operacao:
        stmt = stmt.where(AuditoriaAtendimento.operacao == operacao)
    stmt = stmt.order_by(AuditoriaAtendimento.id_auditoria.desc()).limit(limite)
    return list(db.execute(stmt).scalars())

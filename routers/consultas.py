"""Demonstracoes e consultas sobre o comportamento da ORM."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import consultas as consultas_orm
from database import get_orm_db
from schemas.etapa2 import ComparacaoCarregamento

router = APIRouter(prefix="/consultas", tags=["Consultas ORM"])


@router.get("/lazy-vs-eager", response_model=ComparacaoCarregamento)
def comparar_carregamento(db: Session = Depends(get_orm_db)):
    """Compara o numero de consultas de lazy loading e eager loading."""
    return consultas_orm.comparar_lazy_e_eager(db)

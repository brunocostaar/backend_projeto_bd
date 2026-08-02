"""Consultas analíticas (Etapa 2, item 4)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import analiticas_db
from database import get_orm_db
from schemas.etapa2 import (
    PacienteSemAltoRisco,
    PlantaoPorUnidade,
    PreceptorSupervisao,
    RankingResidente,
)

router = APIRouter(prefix="/analiticas", tags=["Consultas analíticas"])


@router.get("/ranking-residentes", response_model=list[RankingResidente])
def ranking_residentes(db: Session = Depends(get_orm_db)):
    return analiticas_db.ranking_residentes(db)


@router.get("/preceptores-por-mes", response_model=list[PreceptorSupervisao])
def preceptores_por_mes(
    mes: date = Query(
        date(2026, 7, 1),
        description="Qualquer data dentro do mês desejado; só ano e mês contam.",
    ),
    minimo: int = Query(5, ge=0, description="Devolve quem passou deste total."),
    db: Session = Depends(get_orm_db),
):
    return analiticas_db.preceptores_acima_de(db, mes, minimo)


@router.get("/plantoes-por-unidade", response_model=list[PlantaoPorUnidade])
def plantoes_por_unidade(
    projetar_no_mes: bool = Query(
        False,
        description=(
            "Falso conta os slots fixos da grade semanal. Verdadeiro projeta a "
            "grade nos dias do mês atual."
        ),
    ),
    db: Session = Depends(get_orm_db),
):
    if projetar_no_mes:
        linhas = analiticas_db.plantoes_por_unidade_no_mes(db)
        chave = "plantoes_no_mes"
    else:
        linhas = analiticas_db.plantoes_por_unidade_semanal(db)
        chave = "plantoes_semanais"
    return [{**linha, "plantoes": linha.pop(chave)} for linha in linhas]


@router.get("/pacientes-sem-alto-risco", response_model=list[PacienteSemAltoRisco])
def pacientes_sem_alto_risco(db: Session = Depends(get_orm_db)):
    return analiticas_db.pacientes_sem_procedimento_de_alto_risco(db)

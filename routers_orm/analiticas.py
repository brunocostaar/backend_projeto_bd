"""As quatro consultas analíticas da Etapa 1, servidas pela versão em ORM.

Ficam sob /orm porque são a reimplementação pedida no item 4 da Etapa 2. As
versões em SQL puro continuam no 04_analiticas.sql, executadas pelo psql; a
Etapa 1 nunca as expôs pela API.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from orm import analiticas
from orm.sessao import get_orm_db
from schemas.etapa2 import (
    PacienteSemAltoRisco,
    PlantaoPorUnidade,
    PreceptorSupervisao,
    RankingResidente,
)

router = APIRouter(prefix="/orm/analiticas", tags=["ORM - Consultas analíticas"])


@router.get("/ranking-residentes", response_model=list[RankingResidente])
def ranking_residentes(db: Session = Depends(get_orm_db)):
    """Q1. Residentes por número de atendimentos, incluindo quem tem zero."""
    return analiticas.ranking_residentes(db)


@router.get("/preceptores-por-mes", response_model=list[PreceptorSupervisao])
def preceptores_por_mes(
    mes: date = Query(
        date(2026, 7, 1),
        description="Qualquer data dentro do mês desejado; só ano e mês contam.",
    ),
    minimo: int = Query(5, ge=0, description="Devolve quem passou deste total."),
    db: Session = Depends(get_orm_db),
):
    """Q2. Preceptores acima do mínimo de atendimentos supervisionados no mês.

    Com o seed, julho de 2026 devolve Fernando Alves com 6.
    """
    return analiticas.preceptores_acima_de(db, mes, minimo)


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
    """Q3. Plantões por residente em cada unidade, nas duas leituras possíveis.

    A escala não guarda data, só dia da semana e turno, então "no mês corrente"
    é ambíguo. O parâmetro escolhe qual das duas respostas devolver.
    """
    if projetar_no_mes:
        linhas = analiticas.plantoes_por_unidade_no_mes(db)
        chave = "plantoes_no_mes"
    else:
        linhas = analiticas.plantoes_por_unidade_semanal(db)
        chave = "plantoes_semanais"
    return [{**linha, "plantoes": linha.pop(chave)} for linha in linhas]


@router.get("/pacientes-sem-alto-risco", response_model=list[PacienteSemAltoRisco])
def pacientes_sem_alto_risco(db: Session = Depends(get_orm_db)):
    """Q4. Pacientes que nunca passaram por procedimento de risco ALTO."""
    return analiticas.pacientes_sem_procedimento_de_alto_risco(db)

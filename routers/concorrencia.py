"""Simulação de concorrência (Etapa 2, item 6)."""

from __future__ import annotations

from fastapi import APIRouter

import concorrencia
from schemas.etapa2 import ResultadoConcorrencia

router = APIRouter(prefix="/concorrencia", tags=["Concorrência"])


@router.post("/simular", response_model=ResultadoConcorrencia)
def simular_concorrencia():
    return concorrencia.simular()

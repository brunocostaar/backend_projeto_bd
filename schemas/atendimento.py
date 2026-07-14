from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class AtendimentoBase(BaseModel):
    data_hora: datetime = Field(..., examples=["2026-07-10T14:30:00"])
    duracao_minutos: int = Field(..., examples=[45])
    id_paciente: int = Field(..., examples=[1])
    id_residente: int = Field(..., examples=[2])
    id_preceptor: int = Field(..., examples=[3])

class AtendimentoCreate(AtendimentoBase):
    pass

class AtendimentoRead(AtendimentoBase):
    id_atendimento: int = Field(..., examples=[1])

    model_config = ConfigDict(from_attributes=True)

class TempoMedioResidente(BaseModel):
    """Linha do relatório de tempo médio de atendimento por residente."""
    id_residente: int = Field(..., examples=[11])
    nome: str = Field(..., examples=["Karina Duarte"])
    total_atendimentos: int = Field(..., examples=[3])
    tempo_medio_minutos: float | None = Field(None, examples=[41.7])
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field


class InternacaoBase(BaseModel):
    id_paciente: int = Field(..., examples=[3])
    id_unidade: int = Field(..., examples=[2])
    data_hora_entrada: datetime = Field(..., examples=["2026-07-22T10:30:00"])
    motivo: str | None = Field(None, examples=["monitoramento neurologico"])


class InternacaoCreate(InternacaoBase):
    pass


class InternacaoRead(InternacaoBase):
    id_internacao: int = Field(..., examples=[4])
    data_hora_saida: datetime | None = Field(None, examples=[None])

    model_config = ConfigDict(from_attributes=True)


class InternacaoAlta(BaseModel):
    """Corpo do registro de alta. Sem a data, o banco usa o instante atual."""

    data_hora_saida: datetime | None = Field(None, examples=["2026-07-28T09:00:00"])


class PacienteInternado(BaseModel):
    """Linha da vw_pacientes_internados."""

    id_internacao: int = Field(..., examples=[4])
    id_paciente: int = Field(..., examples=[3])
    nome: str = Field(..., examples=["Carla Mendes"])
    cpf: str = Field(..., examples=["33333333333"])
    numero_convenio: str = Field(..., examples=["CONV-0003"])
    grupo_sanguineo: str = Field(..., examples=["AB+"])
    id_unidade: int = Field(..., examples=[2])
    unidade: str = Field(..., examples=["UTI Adulto"])
    data_hora_entrada: datetime = Field(..., examples=["2026-07-22T10:30:00"])
    motivo: str | None = Field(None, examples=["monitoramento neurologico"])
    tempo_internado: timedelta | None = Field(None, examples=["P3DT22H"])

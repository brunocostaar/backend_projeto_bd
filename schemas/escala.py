from pydantic import BaseModel, ConfigDict, Field

class EscalaBase(BaseModel):
    id_unidade: int = Field(..., examples=[1])
    dia_semana: str = Field(..., examples=["Segunda-feira"])
    turno: str = Field(..., examples=["Manhã"])
    id_residente: int = Field(..., examples=[2])
    id_preceptor: int = Field(..., examples=[3])

class EscalaCreate(EscalaBase):
    pass

class EscalaRead(EscalaBase):
    id_escala: int = Field(..., examples=[1])

    model_config = ConfigDict(from_attributes=True)
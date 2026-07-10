from pydantic import BaseModel, ConfigDict, Field

class UnidadeBase(BaseModel):
    nome: str = Field(..., examples=["Ala Leste - UTI Cardiologia"])
    tipo: str = Field(..., examples=["UTI"])
    capacidade_leitos: int = Field(..., examples=[15])

class UnidadeCreate(UnidadeBase):
    pass

class UnidadeRead(UnidadeBase):
    id_unidade: int = Field(..., examples=[1])

    model_config = ConfigDict(from_attributes=True)
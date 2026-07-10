from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# 📋 SCHEMAS PARA PROCEDIMENTO
# ==============================================================================

class ProcedimentoBase(BaseModel):
    codigo: str = Field(..., examples=["PROC-889"])
    nome: str = Field(..., examples=["Eletrocardiograma (ECG)"])
    tempo_medio_minutos: int = Field(..., examples=[20])
    nivel_risco: str = Field(..., examples=["Baixo"])  # Coluna ausente adicionada

class ProcedimentoCreate(ProcedimentoBase):
    pass

class ProcedimentoRead(ProcedimentoBase):
    id_procedimento: int = Field(..., examples=[1])

    model_config = ConfigDict(from_attributes=True)
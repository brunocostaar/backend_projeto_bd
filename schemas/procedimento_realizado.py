from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# 🩺 SCHEMAS PARA PROCEDIMENTO REALIZADO (Relacionamento N:N)
# ==============================================================================

class ProcedimentoRealizadoBase(BaseModel):
    quantidade: int = Field(..., examples=[1])
    tempo_real_minutos: int = Field(..., examples=[25])
    observacao: str | None = Field(None, examples=["Paciente estava um pouco agitado, ritmo cardíaco ligeiramente elevado."])
    faturado: bool = Field(False, examples=[True])  # Coluna ausente adicionada

class ProcedimentoRealizadoCreate(ProcedimentoRealizadoBase):
    id_atendimento: int = Field(..., examples=[1])
    id_procedimento: int = Field(..., examples=[1])

class ProcedimentoRealizadoRead(ProcedimentoRealizadoBase):
    id_atendimento: int = Field(..., examples=[1])
    id_procedimento: int = Field(..., examples=[1])

    model_config = ConfigDict(from_attributes=True)

class ProcedimentoRealizadoDetalhado(ProcedimentoRealizadoRead):
    """Versão da listagem: inclui o nome do procedimento vindo do JOIN."""
    nome_procedimento: str = Field(..., examples=["Sutura simples"])

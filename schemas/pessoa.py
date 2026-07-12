from datetime import date
from pydantic import BaseModel, ConfigDict, Field

# ==========================================
# 1. ESQUEMAS DE PESSOA (Tabela Pai)
# ==========================================

class PessoaBase(BaseModel):
    nome: str = Field(..., examples=["João da Silva"])
    CPF: str = Field(
        ..., 
        max_length=11, 
        min_length=11, 
        description="CPF sem pontos ou traços (apenas 11 dígitos)",
        examples=["12345678901"]
    )
    data_nascimento: date = Field(..., examples=["1990-05-15"])
    is_flamengo: bool = Field(False, examples=[True])
    telefone: str | None = Field(None, examples=["21999999999"])
    endereco: str | None = Field(None, examples=["Rua das Laranjeiras, 123, Rio de Janeiro - RJ"])

class PessoaCreate(PessoaBase):
    pass

class PessoaRead(PessoaBase):
    id_pessoa: int = Field(..., examples=[1])
    
    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. ESQUEMAS DE PACIENTE (Subtipo)
# ==========================================

class PacienteCreate(PessoaCreate):
    num_convenio: str = Field(..., examples=["UNIMED-998877"])
    alergias: str | None = Field(None, examples=["Dipirona, Poeira"])
    grupo_sanguineo: str | None = Field(None, examples=["O+"])

class PacienteRead(PessoaRead):
    num_convenio: str = Field(..., examples=["UNIMED-998877"])
    alergias: str | None = Field(None, examples=["Dipirona, Poeira"])
    grupo_sanguineo: str | None = Field(None, examples=["O+"])


# ==========================================
# 3. ESQUEMAS DE PROFISSIONAL (Subtipo intermediário)
# ==========================================

class ProfissionalCreate(PessoaCreate):
    CRM: str = Field(..., examples=["CRM/RJ 123456"])
    data_admissao: date = Field(..., examples=["2020-02-10"])
    especialidade: str = Field(..., examples=["Cardiologia"])

class ProfissionalRead(PessoaRead):
    CRM: str = Field(..., examples=["CRM/RJ 123456"])
    data_admissao: date = Field(..., examples=["2020-02-10"])
    especialidade: str = Field(..., examples=["Cardiologia"])


# ==========================================
# 4. ESQUEMAS DE PRECEPTOR (Subtipo de Profissional)
# ==========================================

class PreceptorCreate(ProfissionalCreate):
    titulacao: str = Field(..., examples=["Doutorado em Cardiologia"])

class PreceptorRead(ProfissionalRead):
    titulacao: str = Field(..., examples=["Doutorado em Cardiologia"])


# ==========================================
# 5. ESQUEMAS DE RESIDENTE (Subtipo de Profissional)
# ==========================================

class ResidenteCreate(ProfissionalCreate):
    ano_residencia: str = Field(..., examples=["R2"], description="Ano atual da residência (ex: R1, R2, R3)")

class ResidenteRead(ProfissionalRead):
    ano_residencia: str = Field(..., examples=["R2"])


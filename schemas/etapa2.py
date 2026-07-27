"""Schemas das funcionalidades da Etapa 2: views, procedures e consultas ORM."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class ResidenteSemSupervisor(BaseModel):
    """Linha da vw_residentes_sem_supervisor."""

    id_escala: int = Field(..., examples=[3])
    id_residente: int = Field(..., examples=[11])
    residente: str = Field(..., examples=["Karina Duarte"])
    ano_residencia: str = Field(..., examples=["R1"])
    unidade: str = Field(..., examples=["Pronto-Socorro"])
    dia_semana: str = Field(..., examples=["terca"])
    turno: str = Field(..., examples=["tarde"])
    id_preceptor: int | None = Field(None, examples=[7])
    preceptor: str | None = Field(None, examples=["Gabriela Pinto"])
    titulacao: str | None = Field(None, examples=["mestre"])
    motivo: str = Field(..., examples=["preceptor sem titulação de doutor"])

    model_config = ConfigDict(from_attributes=True)


class EstatisticaMensal(BaseModel):
    """Linha da vw_estatisticas_atendimentos_mensal."""

    mes: date = Field(..., examples=["2026-07-01"])
    id_unidade: int = Field(..., examples=[2])
    unidade: str = Field(..., examples=["UTI Adulto"])
    total_atendimentos: int = Field(..., examples=[5])
    media_duracao_minutos: Decimal | None = Field(None, examples=["52.0"])
    menor_duracao: int | None = Field(None, examples=[40])
    maior_duracao: int | None = Field(None, examples=[60])
    procedimentos_mais_comuns: str | None = Field(
        None,
        examples=["Coleta de sangue (2), Intubacao orotraqueal (2), Puncao lombar (2)"],
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Stored procedures
# ---------------------------------------------------------------------------


class TempoMedioEspera(BaseModel):
    """Linha devolvida por sp_calcular_tempo_medio_espera."""

    unidade_id: int = Field(..., examples=[1])
    nome_unidade: str = Field(..., examples=["Enfermaria A"])
    atendimentos_considerados: int = Field(..., examples=[4])
    espera_media_minutos: Decimal | None = Field(None, examples=["33.8"])


class ProcedimentoDoAtendimento(BaseModel):
    """Item da lista aceita por sp_registrar_atendimento_completo."""

    id_procedimento: int = Field(..., examples=[5])
    quantidade: int = Field(1, ge=1, examples=[1])
    tempo_real_minutos: int | None = Field(None, ge=1, examples=[28])
    observacao: str | None = Field(None, examples=["sem intercorrencias"])
    data_hora_inicio: datetime | None = Field(None, examples=["2026-07-26T10:36:00"])
    faturado: bool = Field(False, examples=[False])


class RegistrarAtendimentoCompleto(BaseModel):
    """Entrada da sp_registrar_atendimento_completo.

    A lista precisa de pelo menos um item: o DER exige no mínimo um
    procedimento por atendimento, e a procedure recusa lista vazia.
    """

    data_hora: datetime = Field(..., examples=["2026-07-26T10:30:00"])
    duracao_minutos: int = Field(..., ge=1, examples=[50])
    id_paciente: int = Field(..., examples=[3])
    id_residente: int = Field(..., examples=[13])
    id_preceptor: int = Field(..., examples=[8])
    id_unidade: int | None = Field(None, examples=[2])
    procedimentos: list[ProcedimentoDoAtendimento] = Field(..., min_length=1)


class AtendimentoRegistrado(BaseModel):
    id_atendimento: int = Field(..., examples=[16])
    procedimentos_inseridos: int = Field(..., examples=[2])
    mensagem: str = Field(..., examples=["Atendimento 16 gravado com 2 procedimentos."])


class ReajustarEscala(BaseModel):
    """Entrada da sp_reajustar_escala."""

    id_residente: int = Field(..., examples=[14])
    dia_origem: str = Field(..., examples=["sexta"])
    turno_origem: str = Field(..., examples=["manha"])
    dia_destino: str = Field(..., examples=["quinta"])
    turno_destino: str = Field(..., examples=["manha"])


class EscalaReajustada(BaseModel):
    escalas_movidas: int = Field(..., examples=[1])
    mensagem: str = Field(..., examples=["1 plantão movido de sexta manha para quinta manha."])


# ---------------------------------------------------------------------------
# Auditoria (trigger)
# ---------------------------------------------------------------------------


class AuditoriaRead(BaseModel):
    """Linha de auditoria_atendimento, gravada pelo trg_audita_atendimento."""

    id_auditoria: int = Field(..., examples=[16])
    id_atendimento: int | None = Field(None, examples=[3])
    operacao: str = Field(..., examples=["UPDATE"])
    usuario: str = Field(..., examples=["postgres"])
    data_hora: datetime = Field(..., examples=["2026-07-26T18:04:11"])
    dados_antigos: dict[str, Any] | None = Field(None)
    dados_novos: dict[str, Any] | None = Field(None)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Consultas avançadas com a DSL da ORM
# ---------------------------------------------------------------------------


class PreceptorDeFlamenguista(BaseModel):
    id_preceptor: int = Field(..., examples=[6])
    preceptor: str = Field(..., examples=["Fernando Alves"])
    titulacao: str = Field(..., examples=["doutor"])
    especialidade: str = Field(..., examples=["Clinica Medica"])
    atendimentos_com_flamenguista: int = Field(..., examples=[2])
    residentes_supervisionados: int = Field(..., examples=[2])


class ProcedimentoResumo(BaseModel):
    nome: str = Field(..., examples=["Intubacao orotraqueal"])
    nivel_risco: str | None = Field(None, examples=["ALTO"])
    quantidade: int = Field(..., examples=[1])
    tempo_real_minutos: int | None = Field(None, examples=[30])


class UltimoAtendimento(BaseModel):
    id_paciente: int = Field(..., examples=[1])
    paciente: str = Field(..., examples=["Ana Souza"])
    id_atendimento: int = Field(..., examples=[11])
    data_hora: datetime = Field(..., examples=["2026-07-20T08:15:00"])
    duracao_minutos: int | None = Field(None, examples=[40])
    unidade: str | None = Field(None, examples=["UTI Adulto"])
    residente: str = Field(..., examples=["Karina Duarte"])
    preceptor: str = Field(..., examples=["Gabriela Pinto"])
    procedimentos: list[ProcedimentoResumo] = Field(default_factory=list)


class PercentualAltoRisco(BaseModel):
    id_residente: int = Field(..., examples=[13])
    residente: str = Field(..., examples=["Mariana Teles"])
    ano_residencia: str = Field(..., examples=["R3"])
    total_procedimentos: int = Field(..., examples=[5])
    procedimentos_alto_risco: int = Field(..., examples=[2])
    percentual_alto_risco: Decimal = Field(..., examples=["40.00"])


class ComparacaoCarregamento(BaseModel):
    """Resultado de comparar_lazy_e_eager."""

    atendimentos: int = Field(..., examples=[15])
    consultas_lazy: int = Field(..., examples=[31])
    consultas_eager: int = Field(..., examples=[1])
    resultados_iguais: bool = Field(..., examples=[True])
    observacao: str


# ---------------------------------------------------------------------------
# Concorrência
# ---------------------------------------------------------------------------


class LinhaDeLog(BaseModel):
    instante: str = Field(..., examples=["00.142s"])
    ator: str = Field(..., examples=["sessao A"])
    mensagem: str = Field(..., examples=["SELECT ... FOR UPDATE obteve o bloqueio"])


class CenarioConcorrencia(BaseModel):
    cenario: str = Field(..., examples=["lock pessimista"])
    descricao: str
    desfecho: str = Field(..., examples=["a segunda transação esperou e depois recusou o conflito"])
    conflito_evitado: bool = Field(..., examples=[True])
    log: list[LinhaDeLog]


class ResultadoConcorrencia(BaseModel):
    cenarios: list[CenarioConcorrencia]


# ---------------------------------------------------------------------------
# Consultas analíticas da Etapa 1, reimplementadas com a DSL
# ---------------------------------------------------------------------------


class RankingResidente(BaseModel):
    id_residente: int = Field(..., examples=[11])
    nome: str = Field(..., examples=["Karina Duarte"])
    ano_residencia: str = Field(..., examples=["R1"])
    total_atendimentos: int = Field(..., examples=[4])


class PreceptorSupervisao(BaseModel):
    id_preceptor: int = Field(..., examples=[6])
    nome: str = Field(..., examples=["Fernando Alves"])
    titulacao: str = Field(..., examples=["doutor"])
    total_supervisionados: int = Field(..., examples=[6])


class PlantaoPorUnidade(BaseModel):
    id_unidade: int = Field(..., examples=[1])
    unidade: str = Field(..., examples=["Enfermaria A"])
    id_residente: int = Field(..., examples=[11])
    residente: str = Field(..., examples=["Karina Duarte"])
    plantoes: int = Field(..., examples=[1])


class PacienteSemAltoRisco(BaseModel):
    id_paciente: int = Field(..., examples=[2])
    nome: str = Field(..., examples=["Bruno Lima"])
    grupo_sanguineo: str = Field(..., examples=["A-"])
    numero_convenio: str = Field(..., examples=["CONV-0002"])


# ---------------------------------------------------------------------------
# Variantes usadas pelas rotas com ORM
#
# As colunas acrescentadas em 05_etapa2_estrutura.sql ficam nestes schemas, e
# não nos da Etapa 1. Assim a resposta de /atendimentos/ continua exatamente
# como estava, e /orm/atendimentos/ mostra os campos novos.
# ---------------------------------------------------------------------------


class AtendimentoOrmBase(BaseModel):
    data_hora: datetime = Field(..., examples=["2026-07-20T08:15:00"])
    duracao_minutos: int = Field(..., ge=1, examples=[40])
    id_paciente: int = Field(..., examples=[1])
    id_residente: int = Field(..., examples=[11])
    id_preceptor: int = Field(..., examples=[7])
    id_unidade: int | None = Field(None, examples=[2])


class AtendimentoOrmCreate(AtendimentoOrmBase):
    pass


class AtendimentoOrmRead(AtendimentoOrmBase):
    id_atendimento: int = Field(..., examples=[11])

    model_config = ConfigDict(from_attributes=True)


class ProcedimentoRealizadoOrmBase(BaseModel):
    quantidade: int = Field(1, ge=1, examples=[1])
    tempo_real_minutos: int | None = Field(None, ge=1, examples=[30])
    observacao: str | None = Field(None, examples=["via aerea garantida"])
    faturado: bool = Field(False, examples=[False])
    data_hora_inicio: datetime | None = Field(None, examples=["2026-07-20T08:21:00"])


class ProcedimentoRealizadoOrmCreate(ProcedimentoRealizadoOrmBase):
    id_atendimento: int = Field(..., examples=[11])
    id_procedimento: int = Field(..., examples=[5])


class ProcedimentoRealizadoOrmRead(ProcedimentoRealizadoOrmCreate):
    nome_procedimento: str | None = Field(None, examples=["Intubacao orotraqueal"])
    nivel_risco: str | None = Field(None, examples=["ALTO"])

    model_config = ConfigDict(from_attributes=True)


class ProcedimentoOrmRead(BaseModel):
    id_procedimento: int = Field(..., examples=[5])
    codigo: int = Field(..., examples=[105])
    nome: str = Field(..., examples=["Intubacao orotraqueal"])
    tempo_medio_minutos: int | None = Field(None, examples=[25])
    nivel_risco: str | None = Field(None, examples=["ALTO"])
    # Coluna mantida pelo trigger; a aplicação só lê.
    media_tempo_procedimento: Decimal | None = Field(None, examples=["29.00"])

    model_config = ConfigDict(from_attributes=True)


class EscalaOrmBase(BaseModel):
    id_unidade: int = Field(..., examples=[1])
    dia_semana: str = Field(..., examples=["segunda"])
    turno: str = Field(..., examples=["manha"])
    id_residente: int = Field(..., examples=[11])
    id_preceptor: int = Field(..., examples=[6])


class EscalaOrmCreate(EscalaOrmBase):
    pass


class EscalaOrmRead(EscalaOrmBase):
    id_escala: int = Field(..., examples=[1])
    # Usada no controle de concorrência otimista.
    versao: int = Field(..., examples=[1])

    model_config = ConfigDict(from_attributes=True)

"""Funcionalidades da Etapa 2 expostas na API.

Reúne o que não é CRUD: as três stored procedures, as três views, a tabela de
auditoria alimentada por trigger, as três consultas avançadas em DSL e a
simulação de concorrência. Sem estas rotas, nada disso chegaria à interface.

Views e procedures são objetos do banco, e são chamados como tal, com text().
Mapear uma view como entidade da ORM não traria ganho: ela é somente leitura e
não tem chave primária. A ORM aparece onde há entidade de verdade, como na
auditoria, e nas consultas de orm/consultas.py.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from orm import concorrencia, consultas
from orm.modelos import AuditoriaAtendimento
from orm.sessao import get_orm_db
from routers_orm.comum import erro_do_banco
from schemas.etapa2 import (
    AtendimentoRegistrado,
    AuditoriaRead,
    ComparacaoCarregamento,
    EscalaReajustada,
    EstatisticaMensal,
    PercentualAltoRisco,
    PreceptorDeFlamenguista,
    ReajustarEscala,
    RegistrarAtendimentoCompleto,
    ResidenteSemSupervisor,
    ResultadoConcorrencia,
    TempoMedioEspera,
    UltimoAtendimento,
)
from schemas.internacao import PacienteInternado

router = APIRouter(prefix="/etapa2", tags=["Etapa 2"])


def _linhas(db: Session, sql: str) -> list[dict]:
    return [dict(linha._mapping) for linha in db.execute(text(sql))]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@router.get("/views/pacientes-internados", response_model=list[PacienteInternado])
def pacientes_internados(db: Session = Depends(get_orm_db)):
    """vw_pacientes_internados: quem está internado agora.

    O critério é a internação mais recente estar sem data de saída. Um paciente
    com internação antiga mal encerrada não aparece.
    """
    return _linhas(db, "SELECT * FROM vw_pacientes_internados")


@router.get("/views/residentes-sem-supervisor", response_model=list[ResidenteSemSupervisor])
def residentes_sem_supervisor(db: Session = Depends(get_orm_db)):
    """vw_residentes_sem_supervisor: plantões cujo preceptor não é doutor."""
    return _linhas(db, "SELECT * FROM vw_residentes_sem_supervisor")


@router.get("/views/estatisticas-mensais", response_model=list[EstatisticaMensal])
def estatisticas_mensais(db: Session = Depends(get_orm_db)):
    """vw_estatisticas_atendimentos_mensal: total, média e procedimentos frequentes."""
    return _linhas(db, "SELECT * FROM vw_estatisticas_atendimentos_mensal")


# ---------------------------------------------------------------------------
# Stored procedures
# ---------------------------------------------------------------------------


@router.get("/procedures/tempo-medio-espera", response_model=list[TempoMedioEspera])
def tempo_medio_espera(db: Session = Depends(get_orm_db)):
    """sp_calcular_tempo_medio_espera: espera até o primeiro procedimento.

    É FUNCTION e não PROCEDURE porque devolve um conjunto de linhas, então
    aparece no FROM de um SELECT.
    """
    return _linhas(db, "SELECT * FROM sp_calcular_tempo_medio_espera()")


@router.post("/procedures/registrar-atendimento-completo", response_model=AtendimentoRegistrado)
def registrar_atendimento_completo(
    dados: RegistrarAtendimentoCompleto, db: Session = Depends(get_orm_db)
):
    """sp_registrar_atendimento_completo: atendimento e procedimentos numa transação.

    A lista vai como JSONB. Se qualquer procedimento falhar, o CALL inteiro é
    abortado e o atendimento não fica gravado pela metade.
    """
    procedimentos = [p.model_dump(mode="json") for p in dados.procedimentos]

    comando = text(
        """
        CALL sp_registrar_atendimento_completo(
            CAST(:data_hora AS TIMESTAMP),
            :duracao_minutos,
            :id_paciente,
            :id_residente,
            :id_preceptor,
            :id_unidade,
            CAST(:procedimentos AS JSONB),
            NULL
        )
        """
    )

    try:
        resultado = db.execute(
            comando,
            {
                "data_hora": dados.data_hora.isoformat(),
                "duracao_minutos": dados.duracao_minutos,
                "id_paciente": dados.id_paciente,
                "id_residente": dados.id_residente,
                "id_preceptor": dados.id_preceptor,
                "id_unidade": dados.id_unidade,
                "procedimentos": json.dumps(procedimentos),
            },
        )
        # O parâmetro INOUT volta como uma linha de resultado do CALL.
        id_atendimento = None
        if resultado.returns_rows:
            linha = resultado.fetchone()
            if linha is not None:
                id_atendimento = linha[0]
        if id_atendimento is None:
            id_atendimento = db.execute(
                text(
                    "SELECT id_atendimento FROM atendimento "
                    "WHERE data_hora = CAST(:dh AS TIMESTAMP) "
                    "ORDER BY id_atendimento DESC LIMIT 1"
                ),
                {"dh": dados.data_hora.isoformat()},
            ).scalar()
        db.commit()
    except DBAPIError as erro:
        db.rollback()
        raise erro_do_banco(erro) from erro

    total = len(procedimentos)
    return {
        "id_atendimento": id_atendimento,
        "procedimentos_inseridos": total,
        "mensagem": (
            f"Atendimento {id_atendimento} gravado com {total} "
            f"procedimento{'s' if total > 1 else ''}."
        ),
    }


@router.post("/procedures/reajustar-escala", response_model=EscalaReajustada)
def reajustar_escala(dados: ReajustarEscala, db: Session = Depends(get_orm_db)):
    """sp_reajustar_escala: move os plantões de um dia/turno para outro.

    Recusa tudo se o destino já estiver ocupado pelo mesmo residente. A resposta
    traz quantas escalas foram movidas; zero quando não havia plantão na origem.
    """
    comando = text(
        """
        CALL sp_reajustar_escala(
            :id_residente, :dia_origem, :turno_origem,
            :dia_destino, :turno_destino, NULL
        )
        """
    )
    try:
        resultado = db.execute(comando, dados.model_dump())
        movidas = 0
        if resultado.returns_rows:
            linha = resultado.fetchone()
            if linha is not None and linha[0] is not None:
                movidas = int(linha[0])
        db.commit()
    except DBAPIError as erro:
        db.rollback()
        raise erro_do_banco(erro) from erro

    if movidas == 0:
        mensagem = (
            f"O residente {dados.id_residente} não tem plantão em "
            f"{dados.dia_origem} {dados.turno_origem}. Nada foi alterado."
        )
    else:
        quantos = "1 plantão movido" if movidas == 1 else f"{movidas} plantões movidos"
        mensagem = (
            f"{quantos} de {dados.dia_origem} {dados.turno_origem} "
            f"para {dados.dia_destino} {dados.turno_destino}."
        )
    return {"escalas_movidas": movidas, "mensagem": mensagem}


# ---------------------------------------------------------------------------
# Auditoria (trigger)
# ---------------------------------------------------------------------------


@router.get("/auditoria", response_model=list[AuditoriaRead])
def listar_auditoria(
    id_atendimento: int | None = None,
    operacao: str | None = Query(None, pattern="^(INSERT|UPDATE|DELETE)$"),
    limite: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_orm_db),
):
    """Histórico gravado pelo trg_audita_atendimento.

    A aplicação nunca escreve nesta tabela. Toda linha aqui foi posta pelo
    trigger, inclusive as dos atendimentos que já foram apagados.
    """
    stmt = select(AuditoriaAtendimento)
    if id_atendimento is not None:
        stmt = stmt.where(AuditoriaAtendimento.id_atendimento == id_atendimento)
    if operacao:
        stmt = stmt.where(AuditoriaAtendimento.operacao == operacao)
    stmt = stmt.order_by(AuditoriaAtendimento.id_auditoria.desc()).limit(limite)
    return list(db.execute(stmt).scalars())


# ---------------------------------------------------------------------------
# Consultas avançadas com a DSL da ORM
# ---------------------------------------------------------------------------


@router.get("/consultas/preceptores-flamenguistas", response_model=list[PreceptorDeFlamenguista])
def preceptores_flamenguistas(db: Session = Depends(get_orm_db)):
    """Preceptores que supervisionaram atendimentos a pacientes flamenguistas."""
    return consultas.preceptores_de_pacientes_flamenguistas(db)


@router.get("/consultas/ultimo-atendimento-por-paciente", response_model=list[UltimoAtendimento])
def ultimo_atendimento_por_paciente(db: Session = Depends(get_orm_db)):
    """Último atendimento de cada paciente, com a lista de procedimentos."""
    return consultas.ultimo_atendimento_por_paciente(db)


@router.get("/consultas/percentual-alto-risco", response_model=list[PercentualAltoRisco])
def percentual_alto_risco(db: Session = Depends(get_orm_db)):
    """Proporção de procedimentos de risco ALTO por residente."""
    return consultas.percentual_alto_risco_por_residente(db)


@router.get("/consultas/lazy-vs-eager", response_model=ComparacaoCarregamento)
def lazy_vs_eager(db: Session = Depends(get_orm_db)):
    """Conta as consultas emitidas no carregamento sob demanda e no adiantado."""
    return consultas.comparar_lazy_e_eager(db)


# ---------------------------------------------------------------------------
# Concorrência
# ---------------------------------------------------------------------------


@router.post("/concorrencia/simular", response_model=ResultadoConcorrencia)
def simular_concorrencia():
    """Roda os três cenários de disputa pela mesma escala e devolve os logs.

    Cada cenário abre duas sessões em threads separadas. O que é criado durante
    a simulação é apagado no fim, então o banco volta ao estado anterior.
    """
    return concorrencia.simular()

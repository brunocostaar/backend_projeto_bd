"""Atendimentos com ORM (Etapa 2).

Inclui estatísticas mensais, tempo médio de espera e registro atômico de
atendimento com procedimentos.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased

from modelos import Atendimento, Paciente, Preceptor, Pessoa, Residente, Unidade
from database import get_orm_db
from routers.comum import confirmar, erro_do_banco, nao_encontrado
from schemas.atendimento import TempoMedioResidente
from schemas.etapa2 import (
    AtendimentoOrmCreate,
    AtendimentoOrmRead,
    AtendimentoRegistrado,
    EstatisticaMensal,
    RegistrarAtendimentoCompleto,
    TempoMedioEspera,
)

router = APIRouter(prefix="/atendimentos", tags=["Atendimentos"])


def _validar_referencias(db: Session, dados: AtendimentoOrmCreate) -> None:
    if db.get(Paciente, dados.id_paciente) is None:
        raise nao_encontrado(f"Paciente {dados.id_paciente} não existe.")
    if db.get(Residente, dados.id_residente) is None:
        raise nao_encontrado(f"Residente {dados.id_residente} não existe.")
    if db.get(Preceptor, dados.id_preceptor) is None:
        raise nao_encontrado(f"Preceptor {dados.id_preceptor} não existe.")
    if dados.id_unidade is not None and db.get(Unidade, dados.id_unidade) is None:
        raise nao_encontrado(f"Unidade {dados.id_unidade} não existe.")


def _buscar(db: Session, id_atendimento: int) -> Atendimento:
    atendimento = db.get(Atendimento, id_atendimento)
    if atendimento is None:
        raise nao_encontrado("Atendimento não encontrado.")
    return atendimento


@router.post("/", response_model=AtendimentoOrmRead, status_code=status.HTTP_201_CREATED)
def criar_atendimento(dados: AtendimentoOrmCreate, db: Session = Depends(get_orm_db)):
    _validar_referencias(db, dados)
    atendimento = Atendimento(**dados.model_dump())
    db.add(atendimento)
    confirmar(db)
    return atendimento


@router.get("/", response_model=list[AtendimentoOrmRead])
def listar_atendimentos(
    id_paciente: int | None = None,
    id_residente: int | None = None,
    id_preceptor: int | None = None,
    id_unidade: int | None = None,
    data: str | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = select(Atendimento)
    if id_paciente is not None:
        stmt = stmt.where(Atendimento.id_paciente == id_paciente)
    if id_residente is not None:
        stmt = stmt.where(Atendimento.id_residente == id_residente)
    if id_preceptor is not None:
        stmt = stmt.where(Atendimento.id_preceptor == id_preceptor)
    if id_unidade is not None:
        stmt = stmt.where(Atendimento.id_unidade == id_unidade)
    if data:
        stmt = stmt.where(func.date(Atendimento.data_hora) == data)
    return list(db.execute(stmt.order_by(Atendimento.data_hora.desc())).scalars())


# ---------------------------------------------------------------------------
# Rota fixa antes da rota com parâmetro
# ---------------------------------------------------------------------------


@router.get("/tempo-medio-por-residente", response_model=list[TempoMedioResidente])
def tempo_medio_por_residente(db: Session = Depends(get_orm_db)):
    pessoa = aliased(Pessoa, name="pessoa_residente")
    media = func.round(func.avg(Atendimento.duracao_minutos), 1)

    stmt = (
        select(
            Residente.id_profissional.label("id_residente"),
            pessoa.nome,
            func.count(Atendimento.id_atendimento).label("total_atendimentos"),
            media.label("tempo_medio_minutos"),
        )
        .select_from(Residente)
        .join(pessoa, pessoa.id_pessoa == Residente.id_profissional)
        .outerjoin(Atendimento, Atendimento.id_residente == Residente.id_profissional)
        .group_by(Residente.id_profissional, pessoa.nome)
        .order_by(media.desc().nullslast(), pessoa.nome)
    )
    return [dict(linha._mapping) for linha in db.execute(stmt)]


# ---------------------------------------------------------------------------
# Estatísticas mensais
# ---------------------------------------------------------------------------


@router.get("/estatisticas-mensais", response_model=list[EstatisticaMensal])
def estatisticas_mensais(db: Session = Depends(get_orm_db)):
    return [
        dict(linha._mapping)
        for linha in db.execute(text("SELECT * FROM vw_estatisticas_atendimentos_mensal"))
    ]


# ---------------------------------------------------------------------------
# Tempo médio de espera
# ---------------------------------------------------------------------------


@router.get("/tempo-medio-espera", response_model=list[TempoMedioEspera])
def tempo_medio_espera(db: Session = Depends(get_orm_db)):
    return [
        dict(linha._mapping)
        for linha in db.execute(text("SELECT * FROM sp_calcular_tempo_medio_espera()"))
    ]


# ---------------------------------------------------------------------------
# Atendimento completo
# ---------------------------------------------------------------------------


@router.post("/completo", response_model=AtendimentoRegistrado)
def registrar_atendimento_completo(
    dados: RegistrarAtendimentoCompleto, db: Session = Depends(get_orm_db)
):
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


# As rotas com identificador ficam por ultimo. O Starlette resolve caminhos na
# ordem de registro; desse modo nomes como "estatisticas-mensais" nunca sao
# interpretados como o parametro inteiro id_atendimento.


@router.get("/{id_atendimento}", response_model=AtendimentoOrmRead)
def buscar_atendimento(id_atendimento: int, db: Session = Depends(get_orm_db)):
    return _buscar(db, id_atendimento)


@router.put("/{id_atendimento}", response_model=AtendimentoOrmRead)
def atualizar_atendimento(
    id_atendimento: int,
    dados: AtendimentoOrmCreate,
    db: Session = Depends(get_orm_db),
):
    atendimento = _buscar(db, id_atendimento)
    _validar_referencias(db, dados)
    for campo, valor in dados.model_dump().items():
        setattr(atendimento, campo, valor)
    confirmar(db)
    return atendimento


@router.delete("/{id_atendimento}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_atendimento(id_atendimento: int, db: Session = Depends(get_orm_db)):
    db.delete(_buscar(db, id_atendimento))
    confirmar(db)
    return None

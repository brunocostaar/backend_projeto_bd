"""Atendimentos com ORM (Etapa 2). Espelha routers/atendimento.py.

Diferença de contrato: aqui o atendimento aceita id_unidade, coluna que a
Etapa 2 acrescentou. Sem ela as views mensais e o cálculo de espera não teriam
como agrupar por unidade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from orm.modelos import Atendimento, Paciente, Preceptor, Pessoa, Residente, Unidade
from orm.sessao import get_orm_db
from routers_orm.comum import confirmar, nao_encontrado
from schemas.atendimento import TempoMedioResidente
from schemas.etapa2 import AtendimentoOrmCreate, AtendimentoOrmRead

router = APIRouter(prefix="/orm/atendimentos", tags=["ORM - Atendimentos"])


def _validar_referencias(db: Session, dados: AtendimentoOrmCreate) -> None:
    """Confere as chaves estrangeiras antes de gravar.

    O banco recusaria de qualquer jeito, mas com mensagem do driver. Verificar
    aqui permite dizer qual das quatro referências está errada.
    """
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
    """Grava um atendimento. O trg_audita_atendimento registra a inserção."""
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


# Rota fixa antes da rota com parâmetro, senão "tempo-medio-por-residente"
# seria interpretado como um id.
@router.get("/tempo-medio-por-residente", response_model=list[TempoMedioResidente])
def tempo_medio_por_residente(db: Session = Depends(get_orm_db)):
    """Mesma agregação do endpoint da Etapa 1, escrita com a DSL.

    O JOIN externo mantém no resultado o residente que ainda não atendeu
    ninguém, com total zero e média nula.
    """
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


@router.get("/{id_atendimento}", response_model=AtendimentoOrmRead)
def buscar_atendimento(id_atendimento: int, db: Session = Depends(get_orm_db)):
    return _buscar(db, id_atendimento)


@router.put("/{id_atendimento}", response_model=AtendimentoOrmRead)
def atualizar_atendimento(
    id_atendimento: int,
    dados: AtendimentoOrmCreate,
    db: Session = Depends(get_orm_db),
):
    """Atualiza o atendimento. O trigger de auditoria guarda o antes e o depois."""
    atendimento = _buscar(db, id_atendimento)
    _validar_referencias(db, dados)
    for campo, valor in dados.model_dump().items():
        setattr(atendimento, campo, valor)
    confirmar(db)
    return atendimento


@router.delete("/{id_atendimento}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_atendimento(id_atendimento: int, db: Session = Depends(get_orm_db)):
    """Remove o atendimento e, em cascata, seus procedimentos realizados.

    A linha de auditoria do DELETE permanece: auditoria_atendimento.id_atendimento
    não tem chave estrangeira justamente para sobreviver a esta remoção.
    """
    db.delete(_buscar(db, id_atendimento))
    confirmar(db)
    return None

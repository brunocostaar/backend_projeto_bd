"""Pacientes, preceptores e residentes com ORM (Etapa 2).

Inclui views e consultas avançadas junto dos recursos correspondentes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, contains_eager, selectinload

import consultas
from modelos import Paciente, Pessoa, Preceptor, Profissional, Residente
from database import get_orm_db
from routers.comum import (
    aplicar_alergias,
    confirmar,
    dados_do_paciente,
    dados_do_profissional,
    nao_encontrado,
    remover_pessoa_se_orfa,
)
from schemas.etapa2 import (
    PercentualAltoRisco,
    PreceptorDeFlamenguista,
    ResidenteSemSupervisor,
    UltimoAtendimento,
)
from schemas.internacao import PacienteInternado
from schemas.pessoa import (
    PacienteCreate,
    PacienteRead,
    PreceptorCreate,
    PreceptorRead,
    ResidenteCreate,
    ResidenteRead,
)

router_pacientes = APIRouter(prefix="/pacientes", tags=["Pacientes"])
router_preceptores = APIRouter(prefix="/preceptores", tags=["Preceptores"])
router_residentes = APIRouter(prefix="/residentes", tags=["Residentes"])


# ---------------------------------------------------------------------------
# Pacientes
# ---------------------------------------------------------------------------


def _buscar_paciente(db: Session, id_pessoa: int) -> Paciente:
    paciente = db.get(
        Paciente,
        id_pessoa,
        options=[selectinload(Paciente.pessoa), selectinload(Paciente.alergias)],
    )
    if paciente is None:
        raise nao_encontrado("Paciente não encontrado.")
    return paciente


@router_pacientes.post("/", response_model=PacienteRead, status_code=status.HTTP_201_CREATED)
def criar_paciente(dados: PacienteCreate, db: Session = Depends(get_orm_db)):
    pessoa = Pessoa(
        nome=dados.nome,
        CPF=dados.CPF,
        data_nascimento=dados.data_nascimento,
        is_flamengo=dados.is_flamengo,
        telefone=dados.telefone,
        endereco=dados.endereco,
    )
    pessoa.paciente = Paciente(
        numero_convenio=dados.num_convenio,
        grupo_sanguineo=dados.grupo_sanguineo,
    )
    aplicar_alergias(pessoa.paciente, dados.alergias)

    db.add(pessoa)
    confirmar(db)
    return dados_do_paciente(pessoa.paciente)


@router_pacientes.get("/", response_model=list[PacienteRead])
def listar_pacientes(
    nome: str | None = None,
    cpf: str | None = None,
    grupo_sanguineo: str | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = (
        select(Paciente)
        .join(Paciente.pessoa)
        .options(contains_eager(Paciente.pessoa), selectinload(Paciente.alergias))
    )
    if nome:
        stmt = stmt.where(Pessoa.nome.ilike(f"%{nome}%"))
    if cpf:
        stmt = stmt.where(Pessoa.CPF.like(f"%{cpf}%"))
    if grupo_sanguineo:
        stmt = stmt.where(Paciente.grupo_sanguineo == grupo_sanguineo)
    stmt = stmt.order_by(Pessoa.nome)

    return [dados_do_paciente(p) for p in db.execute(stmt).unique().scalars()]


@router_pacientes.get("/internados", response_model=list[PacienteInternado])
def pacientes_internados(db: Session = Depends(get_orm_db)):
    """vw_pacientes_internados: quem está internado agora."""
    return [dict(linha._mapping) for linha in db.execute(text("SELECT * FROM vw_pacientes_internados"))]


@router_pacientes.get("/ultimo-atendimento", response_model=list[UltimoAtendimento])
def ultimo_atendimento_por_paciente(db: Session = Depends(get_orm_db)):
    """Último atendimento de cada paciente, com a lista de procedimentos."""
    return consultas.ultimo_atendimento_por_paciente(db)


# Caminhos com identificador ficam depois dos caminhos literais acima.


@router_pacientes.get("/{id_pessoa}", response_model=PacienteRead)
def buscar_paciente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    return dados_do_paciente(_buscar_paciente(db, id_pessoa))


@router_pacientes.put("/{id_pessoa}", response_model=PacienteRead)
def atualizar_paciente(
    id_pessoa: int, dados: PacienteCreate, db: Session = Depends(get_orm_db)
):
    paciente = _buscar_paciente(db, id_pessoa)
    pessoa = paciente.pessoa

    pessoa.nome = dados.nome
    pessoa.CPF = dados.CPF
    pessoa.data_nascimento = dados.data_nascimento
    pessoa.is_flamengo = dados.is_flamengo
    pessoa.telefone = dados.telefone
    pessoa.endereco = dados.endereco

    paciente.numero_convenio = dados.num_convenio
    paciente.grupo_sanguineo = dados.grupo_sanguineo
    aplicar_alergias(paciente, dados.alergias)

    confirmar(db)
    return dados_do_paciente(paciente)


@router_pacientes.delete("/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_paciente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    paciente = _buscar_paciente(db, id_pessoa)
    pessoa = paciente.pessoa
    db.delete(paciente)
    remover_pessoa_se_orfa(db, pessoa)
    confirmar(db)
    return None


# ---------------------------------------------------------------------------
# Preceptores
# ---------------------------------------------------------------------------


def _buscar_preceptor(db: Session, id_pessoa: int) -> Preceptor:
    preceptor = db.get(
        Preceptor,
        id_pessoa,
        options=[selectinload(Preceptor.profissional).selectinload(Profissional.pessoa)],
    )
    if preceptor is None:
        raise nao_encontrado("Preceptor não encontrado.")
    return preceptor


def _dados_do_preceptor(preceptor: Preceptor) -> dict:
    return {
        **dados_do_profissional(preceptor.profissional),
        "titulacao": preceptor.titulacao,
    }


@router_preceptores.post("/", response_model=PreceptorRead, status_code=status.HTTP_201_CREATED)
def criar_preceptor(dados: PreceptorCreate, db: Session = Depends(get_orm_db)):
    pessoa = Pessoa(
        nome=dados.nome,
        CPF=dados.CPF,
        data_nascimento=dados.data_nascimento,
        is_flamengo=dados.is_flamengo,
        telefone=dados.telefone,
        endereco=dados.endereco,
    )
    pessoa.profissional = Profissional(
        CRM=dados.CRM,
        data_admissao=dados.data_admissao,
        especialidade=dados.especialidade,
    )
    pessoa.profissional.preceptor = Preceptor(titulacao=dados.titulacao)

    db.add(pessoa)
    confirmar(db)
    return _dados_do_preceptor(pessoa.profissional.preceptor)


@router_preceptores.get("/", response_model=list[PreceptorRead])
def listar_preceptores(
    nome: str | None = None,
    cpf: str | None = None,
    especialidade: str | None = None,
    titulacao: str | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = (
        select(Preceptor)
        .join(Preceptor.profissional)
        .join(Profissional.pessoa)
        .options(
            contains_eager(Preceptor.profissional).contains_eager(Profissional.pessoa)
        )
    )
    if nome:
        stmt = stmt.where(Pessoa.nome.ilike(f"%{nome}%"))
    if cpf:
        stmt = stmt.where(Pessoa.CPF.like(f"%{cpf}%"))
    if especialidade:
        stmt = stmt.where(Profissional.especialidade.ilike(f"%{especialidade}%"))
    if titulacao:
        stmt = stmt.where(Preceptor.titulacao.ilike(f"%{titulacao}%"))
    stmt = stmt.order_by(Pessoa.nome)

    return [_dados_do_preceptor(p) for p in db.execute(stmt).unique().scalars()]


@router_preceptores.get("/supervisionados-flamenguistas", response_model=list[PreceptorDeFlamenguista])
def preceptores_flamenguistas(db: Session = Depends(get_orm_db)):
    """Preceptores que supervisionaram atendimentos a pacientes flamenguistas."""
    return consultas.preceptores_de_pacientes_flamenguistas(db)


@router_preceptores.get("/{id_pessoa}", response_model=PreceptorRead)
def buscar_preceptor(id_pessoa: int, db: Session = Depends(get_orm_db)):
    return _dados_do_preceptor(_buscar_preceptor(db, id_pessoa))


@router_preceptores.put("/{id_pessoa}", response_model=PreceptorRead)
def atualizar_preceptor(
    id_pessoa: int, dados: PreceptorCreate, db: Session = Depends(get_orm_db)
):
    preceptor = _buscar_preceptor(db, id_pessoa)
    profissional = preceptor.profissional
    pessoa = profissional.pessoa

    pessoa.nome = dados.nome
    pessoa.CPF = dados.CPF
    pessoa.data_nascimento = dados.data_nascimento
    pessoa.is_flamengo = dados.is_flamengo
    pessoa.telefone = dados.telefone
    pessoa.endereco = dados.endereco

    profissional.CRM = dados.CRM
    profissional.data_admissao = dados.data_admissao
    profissional.especialidade = dados.especialidade
    preceptor.titulacao = dados.titulacao

    confirmar(db)
    return _dados_do_preceptor(preceptor)


@router_preceptores.delete("/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_preceptor(id_pessoa: int, db: Session = Depends(get_orm_db)):
    preceptor = _buscar_preceptor(db, id_pessoa)
    pessoa = preceptor.profissional.pessoa
    db.delete(preceptor.profissional)
    remover_pessoa_se_orfa(db, pessoa)
    confirmar(db)
    return None


# ---------------------------------------------------------------------------
# Residentes
# ---------------------------------------------------------------------------


def _buscar_residente(db: Session, id_pessoa: int) -> Residente:
    residente = db.get(
        Residente,
        id_pessoa,
        options=[selectinload(Residente.profissional).selectinload(Profissional.pessoa)],
    )
    if residente is None:
        raise nao_encontrado("Residente não encontrado.")
    return residente


def _dados_do_residente(residente: Residente) -> dict:
    return {
        **dados_do_profissional(residente.profissional),
        "ano_residencia": residente.ano_residencia,
    }


@router_residentes.post("/", response_model=ResidenteRead, status_code=status.HTTP_201_CREATED)
def criar_residente(dados: ResidenteCreate, db: Session = Depends(get_orm_db)):
    pessoa = Pessoa(
        nome=dados.nome,
        CPF=dados.CPF,
        data_nascimento=dados.data_nascimento,
        is_flamengo=dados.is_flamengo,
        telefone=dados.telefone,
        endereco=dados.endereco,
    )
    pessoa.profissional = Profissional(
        CRM=dados.CRM,
        data_admissao=dados.data_admissao,
        especialidade=dados.especialidade,
    )
    pessoa.profissional.residente = Residente(ano_residencia=dados.ano_residencia)

    db.add(pessoa)
    confirmar(db)
    return _dados_do_residente(pessoa.profissional.residente)


@router_residentes.get("/", response_model=list[ResidenteRead])
def listar_residentes(
    nome: str | None = None,
    cpf: str | None = None,
    especialidade: str | None = None,
    ano_residencia: str | None = None,
    db: Session = Depends(get_orm_db),
):
    stmt = (
        select(Residente)
        .join(Residente.profissional)
        .join(Profissional.pessoa)
        .options(
            contains_eager(Residente.profissional).contains_eager(Profissional.pessoa)
        )
    )
    if nome:
        stmt = stmt.where(Pessoa.nome.ilike(f"%{nome}%"))
    if cpf:
        stmt = stmt.where(Pessoa.CPF.like(f"%{cpf}%"))
    if especialidade:
        stmt = stmt.where(Profissional.especialidade.ilike(f"%{especialidade}%"))
    if ano_residencia:
        stmt = stmt.where(Residente.ano_residencia == ano_residencia)
    stmt = stmt.order_by(Pessoa.nome)

    return [_dados_do_residente(r) for r in db.execute(stmt).unique().scalars()]


@router_residentes.get("/sem-supervisor-doutor", response_model=list[ResidenteSemSupervisor])
def residentes_sem_supervisor(db: Session = Depends(get_orm_db)):
    """vw_residentes_sem_supervisor: plantões cujo preceptor não é doutor."""
    return [dict(linha._mapping) for linha in db.execute(text("SELECT * FROM vw_residentes_sem_supervisor"))]


@router_residentes.get("/percentual-alto-risco", response_model=list[PercentualAltoRisco])
def percentual_alto_risco(db: Session = Depends(get_orm_db)):
    """Proporção de procedimentos de risco ALTO por residente."""
    return consultas.percentual_alto_risco_por_residente(db)


@router_residentes.get("/{id_pessoa}", response_model=ResidenteRead)
def buscar_residente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    return _dados_do_residente(_buscar_residente(db, id_pessoa))


@router_residentes.put("/{id_pessoa}", response_model=ResidenteRead)
def atualizar_residente(
    id_pessoa: int, dados: ResidenteCreate, db: Session = Depends(get_orm_db)
):
    residente = _buscar_residente(db, id_pessoa)
    profissional = residente.profissional
    pessoa = profissional.pessoa

    pessoa.nome = dados.nome
    pessoa.CPF = dados.CPF
    pessoa.data_nascimento = dados.data_nascimento
    pessoa.is_flamengo = dados.is_flamengo
    pessoa.telefone = dados.telefone
    pessoa.endereco = dados.endereco

    profissional.CRM = dados.CRM
    profissional.data_admissao = dados.data_admissao
    profissional.especialidade = dados.especialidade
    residente.ano_residencia = dados.ano_residencia

    confirmar(db)
    return _dados_do_residente(residente)


@router_residentes.delete("/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_residente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    residente = _buscar_residente(db, id_pessoa)
    pessoa = residente.profissional.pessoa
    db.delete(residente.profissional)
    remover_pessoa_se_orfa(db, pessoa)
    confirmar(db)
    return None

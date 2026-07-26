"""Pacientes, preceptores e residentes com ORM (Etapa 2).

Mesmo contrato de routers/pessoa.py, que faz o mesmo em SQL puro. As duas
versões convivem: /pacientes/ é a da Etapa 1, /orm/pacientes/ é esta.

O que muda na prática:

A herança física deixa de aparecer no código. Em SQL puro, cadastrar um
residente são três INSERT em sequência, cada um repetindo o id da pessoa. Aqui
os objetos são ligados uns aos outros e a sessão descobre sozinha a ordem dos
comandos a partir das chaves estrangeiras.

A transação também some do texto. Não há commit espalhado por rota nem rollback
em cada except: a sessão acumula as mudanças e o commit sai uma vez no fim.

O preceptor ganha edição e exclusão, que a Etapa 1 não tinha.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, selectinload

from orm.modelos import Paciente, Pessoa, Preceptor, Profissional, Residente
from orm.sessao import get_orm_db
from routers_orm.comum import (
    aplicar_alergias,
    confirmar,
    dados_do_paciente,
    dados_do_profissional,
    nao_encontrado,
    remover_pessoa_se_orfa,
)
from schemas.pessoa import (
    PacienteCreate,
    PacienteRead,
    PreceptorCreate,
    PreceptorRead,
    ResidenteCreate,
    ResidenteRead,
)

router = APIRouter(prefix="/orm", tags=["ORM - Pessoas"])


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


@router.post("/pacientes/", response_model=PacienteRead, status_code=status.HTTP_201_CREATED)
def criar_paciente(dados: PacienteCreate, db: Session = Depends(get_orm_db)):
    """Cria pessoa, paciente e alergias como um grafo de objetos.

    db.add() recebe só a pessoa. O cascade save-update leva junto o paciente
    pendurado nela e as alergias penduradas no paciente, e a sessão ordena os
    INSERT conforme as chaves estrangeiras.
    """
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


@router.get("/pacientes/", response_model=list[PacienteRead])
def listar_pacientes(
    nome: str | None = None,
    cpf: str | None = None,
    grupo_sanguineo: str | None = None,
    db: Session = Depends(get_orm_db),
):
    """Lista com os mesmos filtros da Etapa 1, montados com a DSL.

    contains_eager reaproveita o JOIN que os filtros já exigem para preencher
    paciente.pessoa; sem ele o SQLAlchemy repetiria a consulta a cada acesso.
    As alergias vêm num segundo SELECT com IN, o que evita multiplicar as linhas
    do resultado.
    """
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


@router.get("/pacientes/{id_pessoa}", response_model=PacienteRead)
def buscar_paciente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    return dados_do_paciente(_buscar_paciente(db, id_pessoa))


@router.put("/pacientes/{id_pessoa}", response_model=PacienteRead)
def atualizar_paciente(
    id_pessoa: int, dados: PacienteCreate, db: Session = Depends(get_orm_db)
):
    """Atualiza pessoa, paciente e alergias.

    Só os atributos que mudaram entram no UPDATE: a sessão compara o estado
    carregado com o atual antes do flush. Se nada mudou, nenhum comando é
    enviado ao banco.
    """
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


@router.delete("/pacientes/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_paciente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    """Remove o paciente e, se ela não tiver outro papel, também a pessoa."""
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


@router.post("/preceptores/", response_model=PreceptorRead, status_code=status.HTTP_201_CREATED)
def criar_preceptor(dados: PreceptorCreate, db: Session = Depends(get_orm_db)):
    """Três tabelas, um db.add(). O cascade percorre pessoa, profissional e preceptor."""
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


@router.get("/preceptores/", response_model=list[PreceptorRead])
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


@router.get("/preceptores/{id_pessoa}", response_model=PreceptorRead)
def buscar_preceptor(id_pessoa: int, db: Session = Depends(get_orm_db)):
    return _dados_do_preceptor(_buscar_preceptor(db, id_pessoa))


@router.put("/preceptores/{id_pessoa}", response_model=PreceptorRead)
def atualizar_preceptor(
    id_pessoa: int, dados: PreceptorCreate, db: Session = Depends(get_orm_db)
):
    """Edição de preceptor. A Etapa 1 não expunha esta operação."""
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


@router.delete("/preceptores/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_preceptor(id_pessoa: int, db: Session = Depends(get_orm_db)):
    """Exclusão de preceptor, também ausente na Etapa 1.

    Atendimentos supervisionados barram a remoção: a chave estrangeira de
    atendimento não tem ON DELETE, então o banco recusa e a resposta vira 400
    com a mensagem traduzida.
    """
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


@router.post("/residentes/", response_model=ResidenteRead, status_code=status.HTTP_201_CREATED)
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


@router.get("/residentes/", response_model=list[ResidenteRead])
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


@router.get("/residentes/{id_pessoa}", response_model=ResidenteRead)
def buscar_residente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    return _dados_do_residente(_buscar_residente(db, id_pessoa))


@router.put("/residentes/{id_pessoa}", response_model=ResidenteRead)
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


@router.delete("/residentes/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_residente(id_pessoa: int, db: Session = Depends(get_orm_db)):
    residente = _buscar_residente(db, id_pessoa)
    pessoa = residente.profissional.pessoa
    db.delete(residente.profissional)
    remover_pessoa_se_orfa(db, pessoa)
    confirmar(db)
    return None

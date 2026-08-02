"""As quatro consultas analíticas da Etapa 1, reescritas com a DSL da ORM.

O item 4 da Etapa 2 pede todas as operações da Etapa 1 reimplementadas com ORM,
e isso inclui o 04_analiticas.sql, não só o CRUD. As versões em SQL continuam
naquele arquivo e servem de gabarito: o resultado das duas tem que bater.

Nenhuma função usa text(). Onde o SQL original tinha LEFT JOIN, NOT EXISTS ou
generate_series, aqui estão outerjoin(), ~exists() e func.generate_series()
como valor de tabela.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import (
    Date,
    Integer,
    case,
    cast,
    extract,
    func,
    literal_column,
    select,
)
from sqlalchemy.orm import Session, aliased

from modelos import (
    Atendimento,
    Escala,
    Paciente,
    Preceptor,
    Pessoa,
    Procedimento,
    ProcedimentoRealizado,
    Residente,
    Unidade,
)


def ranking_residentes(db: Session) -> list[dict[str, Any]]:
    """Q1. Residentes ordenados por número de atendimentos.

    O JOIN externo é intencional: o residente que ainda não atendeu ninguém
    aparece com total zero em vez de sumir do ranking.
    """
    pessoa = aliased(Pessoa, name="pessoa_residente")
    total = func.count(Atendimento.id_atendimento)

    stmt = (
        select(
            Residente.id_profissional.label("id_residente"),
            pessoa.nome,
            Residente.ano_residencia,
            total.label("total_atendimentos"),
        )
        .select_from(Residente)
        .join(pessoa, pessoa.id_pessoa == Residente.id_profissional)
        .outerjoin(Atendimento, Atendimento.id_residente == Residente.id_profissional)
        .group_by(Residente.id_profissional, pessoa.nome, Residente.ano_residencia)
        .order_by(total.desc(), pessoa.nome)
    )
    return [dict(linha._mapping) for linha in db.execute(stmt)]


def preceptores_acima_de(
    db: Session, mes: date, minimo: int = 5
) -> list[dict[str, Any]]:
    """Q2. Preceptores com mais de N atendimentos supervisionados num mês.

    O filtro do mês vai no WHERE, antes de agrupar; a contagem mínima vai no
    HAVING, depois. Trocar um pelo outro daria resultado errado: o WHERE não
    enxerga o agregado, e o HAVING deixaria entrar atendimento de outro mês na
    conta.

    O mês é recebido como data qualquer dentro dele e truncado aqui.
    """
    pessoa = aliased(Pessoa, name="pessoa_preceptor")
    total = func.count(Atendimento.id_atendimento)
    primeiro_dia = date(mes.year, mes.month, 1)

    stmt = (
        select(
            Preceptor.id_profissional.label("id_preceptor"),
            pessoa.nome,
            Preceptor.titulacao,
            total.label("total_supervisionados"),
        )
        .select_from(Atendimento)
        .join(Preceptor, Preceptor.id_profissional == Atendimento.id_preceptor)
        .join(pessoa, pessoa.id_pessoa == Preceptor.id_profissional)
        .where(
            cast(func.date_trunc("month", Atendimento.data_hora), Date) == primeiro_dia
        )
        .group_by(Preceptor.id_profissional, pessoa.nome, Preceptor.titulacao)
        .having(total > minimo)
        .order_by(total.desc(), pessoa.nome)
    )
    return [dict(linha._mapping) for linha in db.execute(stmt)]


def plantoes_por_unidade_semanal(db: Session) -> list[dict[str, Any]]:
    """Q3, versão A. Slots semanais de cada residente em cada unidade.

    A tabela escala é uma grade semanal, sem data concreta, então "no mês
    corrente" admite duas leituras. Esta conta as posições fixas da grade.
    """
    pessoa = aliased(Pessoa, name="pessoa_residente")
    total = func.count()

    stmt = (
        select(
            Unidade.id_unidade,
            Unidade.nome.label("unidade"),
            pessoa.id_pessoa.label("id_residente"),
            pessoa.nome.label("residente"),
            total.label("plantoes_semanais"),
        )
        .select_from(Escala)
        .join(Unidade, Unidade.id_unidade == Escala.id_unidade)
        .join(pessoa, pessoa.id_pessoa == Escala.id_residente)
        .group_by(Unidade.id_unidade, Unidade.nome, pessoa.id_pessoa, pessoa.nome)
        .order_by(Unidade.nome, total.desc(), pessoa.nome)
    )
    return [dict(linha._mapping) for linha in db.execute(stmt)]


def plantoes_por_unidade_no_mes(db: Session) -> list[dict[str, Any]]:
    """Q3, versão B. A grade semanal projetada sobre os dias do mês atual.

    generate_series produz todas as datas do mês e o CASE traduz o dia da
    semana do PostgreSQL para os valores que a constraint chk_dia_semana usa.
    Uma escala de segunda passa a contar uma vez por segunda existente no mês.

    Uma função geradora de linhas entra no FROM pela DSL com alias(), que
    devolve um TableValuedAlias. O objeto serve de alvo para o join, e
    serie.column é a referência à coluna que ela produz.

    Para função de coluna única, o PostgreSQL usa o apelido da função como nome
    da coluna, e é isso que o alias monta: "generate_series(...) AS dia", com a
    coluna referenciada como dia. table_valued("dia") pareceria mais direto, mas
    gera "AS anon_1" e depois referencia anon_1.dia, coluna que não existe.
    """
    pessoa = aliased(Pessoa, name="pessoa_residente")
    inicio = func.date_trunc("month", func.current_date())
    fim = inicio + literal_column("INTERVAL '1 month - 1 day'")
    serie = func.generate_series(
        inicio, fim, literal_column("INTERVAL '1 day'")
    ).alias("dia")

    nome_do_dia = case(
        {
            0: "domingo",
            1: "segunda",
            2: "terca",
            3: "quarta",
            4: "quinta",
            5: "sexta",
            6: "sabado",
        },
        value=cast(extract("dow", serie.column), Integer),
    )
    total = func.count()

    stmt = (
        select(
            Unidade.id_unidade,
            Unidade.nome.label("unidade"),
            pessoa.id_pessoa.label("id_residente"),
            pessoa.nome.label("residente"),
            total.label("plantoes_no_mes"),
        )
        .select_from(Escala)
        .join(Unidade, Unidade.id_unidade == Escala.id_unidade)
        .join(pessoa, pessoa.id_pessoa == Escala.id_residente)
        .join(serie, Escala.dia_semana == nome_do_dia)
        .group_by(Unidade.id_unidade, Unidade.nome, pessoa.id_pessoa, pessoa.nome)
        .order_by(Unidade.nome, total.desc(), pessoa.nome)
    )
    return [dict(linha._mapping) for linha in db.execute(stmt)]


def pacientes_sem_procedimento_de_alto_risco(db: Session) -> list[dict[str, Any]]:
    """Q4. Pacientes que nunca passaram por procedimento de risco ALTO.

    Usa NOT EXISTS, e não NOT IN. Com NOT IN, um único NULL vindo da
    subconsulta faz a condição inteira deixar de casar, e o resultado vem vazio
    sem erro nenhum. NOT EXISTS não tem esse comportamento.
    """
    pessoa = aliased(Pessoa, name="pessoa_paciente")

    houve_alto_risco = (
        select(1)
        .select_from(Atendimento)
        .join(
            ProcedimentoRealizado,
            ProcedimentoRealizado.id_atendimento == Atendimento.id_atendimento,
        )
        .join(
            Procedimento,
            Procedimento.id_procedimento == ProcedimentoRealizado.id_procedimento,
        )
        .where(
            Atendimento.id_paciente == Paciente.id_pessoa,
            Procedimento.nivel_risco == "ALTO",
        )
        .exists()
    )

    stmt = (
        select(
            Paciente.id_pessoa.label("id_paciente"),
            pessoa.nome,
            Paciente.grupo_sanguineo,
            Paciente.numero_convenio,
        )
        .select_from(Paciente)
        .join(pessoa, pessoa.id_pessoa == Paciente.id_pessoa)
        .where(~houve_alto_risco)
        .order_by(pessoa.nome)
    )
    return [dict(linha._mapping) for linha in db.execute(stmt)]

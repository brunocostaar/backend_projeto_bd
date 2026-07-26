"""Consultas avançadas do item 5 da Etapa 2, escritas com a DSL do SQLAlchemy.

Nenhuma função aqui usa text() ou SQL em string. As três consultas pedidas pelo
enunciado estão em versão SQL no 10_etapa2_verificacao.sql, seção 9, para
comparar os resultados.

Pessoa aparece mais de uma vez em quase toda consulta, porque paciente,
residente e preceptor são todos pessoas. Sem aliased() o SQLAlchemy juntaria a
tabela uma única vez e as condições se misturariam; cada papel recebe um alias
próprio.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Numeric, case, cast, func, select
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from orm.modelos import (
    Atendimento,
    Paciente,
    Preceptor,
    Procedimento,
    ProcedimentoRealizado,
    Profissional,
    Pessoa,
    Residente,
)


def preceptores_de_pacientes_flamenguistas(db: Session) -> list[dict[str, Any]]:
    """Preceptores que supervisionaram residentes no atendimento a flamenguistas.

    O atendimento guarda paciente, residente e preceptor na mesma linha, então
    "o preceptor supervisionou o residente que atendeu aquele paciente" é uma
    única linha de atendimento ligando os três. O JOIN com Residente não filtra
    nada por si, mas deixa esse caminho explícito na consulta.

    Espelha a primeira consulta da seção 9 do 10_etapa2_verificacao.sql.
    """
    pessoa_preceptor = aliased(Pessoa, name="pessoa_preceptor")
    pessoa_paciente = aliased(Pessoa, name="pessoa_paciente")

    stmt = (
        select(
            pessoa_preceptor.id_pessoa.label("id_preceptor"),
            pessoa_preceptor.nome.label("preceptor"),
            Preceptor.titulacao,
            Profissional.especialidade,
            func.count(func.distinct(Atendimento.id_atendimento)).label(
                "atendimentos_com_flamenguista"
            ),
            func.count(func.distinct(Residente.id_profissional)).label(
                "residentes_supervisionados"
            ),
        )
        .select_from(Atendimento)
        .join(Preceptor, Preceptor.id_profissional == Atendimento.id_preceptor)
        .join(Profissional, Profissional.id_pessoa == Preceptor.id_profissional)
        .join(pessoa_preceptor, pessoa_preceptor.id_pessoa == Preceptor.id_profissional)
        .join(Residente, Residente.id_profissional == Atendimento.id_residente)
        .join(Paciente, Paciente.id_pessoa == Atendimento.id_paciente)
        .join(pessoa_paciente, pessoa_paciente.id_pessoa == Paciente.id_pessoa)
        .where(pessoa_paciente.is_flamengo.is_(True))
        .group_by(
            pessoa_preceptor.id_pessoa,
            pessoa_preceptor.nome,
            Preceptor.titulacao,
            Profissional.especialidade,
        )
        .order_by(pessoa_preceptor.nome)
    )

    return [dict(linha._mapping) for linha in db.execute(stmt)]


def ultimo_atendimento_por_paciente(db: Session) -> list[dict[str, Any]]:
    """Último atendimento de cada paciente, com residente, preceptor e procedimentos.

    Duas coisas valem observar na implementação:

    Uma função de janela resolve o "último de cada": row_number() particionado
    por paciente e ordenado por data decrescente marca com 1 o atendimento mais
    recente. O desempate por id cobre dois atendimentos no mesmo instante. O
    resultado vira subconsulta e é reunido com a entidade.

    O carregamento é declarado adiante (eager) em vez de sob demanda. Sem isso,
    percorrer atendimento.paciente.pessoa.nome dentro do laço dispararia uma
    consulta por atendimento, o problema conhecido como N+1. joinedload traz o
    lado "um" no mesmo SELECT; selectinload busca a coleção de procedimentos num
    segundo SELECT com IN, que para listas é melhor do que multiplicar as linhas
    do JOIN.
    """
    ranking = (
        select(
            Atendimento.id_atendimento,
            func.row_number()
            .over(
                partition_by=Atendimento.id_paciente,
                order_by=[
                    Atendimento.data_hora.desc(),
                    Atendimento.id_atendimento.desc(),
                ],
            )
            .label("posicao"),
        )
        .subquery("ranking")
    )

    stmt = (
        select(Atendimento)
        .join(ranking, ranking.c.id_atendimento == Atendimento.id_atendimento)
        .where(ranking.c.posicao == 1)
        .options(
            joinedload(Atendimento.paciente).joinedload(Paciente.pessoa),
            joinedload(Atendimento.residente)
            .joinedload(Residente.profissional)
            .joinedload(Profissional.pessoa),
            joinedload(Atendimento.preceptor)
            .joinedload(Preceptor.profissional)
            .joinedload(Profissional.pessoa),
            joinedload(Atendimento.unidade),
            selectinload(Atendimento.procedimentos_realizados).joinedload(
                ProcedimentoRealizado.procedimento
            ),
        )
        .order_by(Atendimento.data_hora.desc())
    )

    atendimentos = db.execute(stmt).unique().scalars().all()

    return [
        {
            "id_paciente": a.id_paciente,
            "paciente": a.paciente.pessoa.nome,
            "id_atendimento": a.id_atendimento,
            "data_hora": a.data_hora,
            "duracao_minutos": a.duracao_minutos,
            "unidade": a.unidade.nome if a.unidade else None,
            "residente": a.residente.profissional.pessoa.nome,
            "preceptor": a.preceptor.profissional.pessoa.nome,
            "procedimentos": [
                {
                    "nome": pr.procedimento.nome,
                    "nivel_risco": pr.procedimento.nivel_risco,
                    "quantidade": pr.quantidade,
                    "tempo_real_minutos": pr.tempo_real_minutos,
                }
                for pr in sorted(
                    a.procedimentos_realizados, key=lambda pr: pr.procedimento.nome
                )
            ],
        }
        for a in atendimentos
    ]


def percentual_alto_risco_por_residente(db: Session) -> list[dict[str, Any]]:
    """Proporção de procedimentos de risco ALTO realizados por cada residente.

    A conta é por linha de procedimento_realizado, não pela coluna quantidade:
    duas aplicações de medicação no mesmo atendimento contam como um
    procedimento realizado. Contar por quantidade daria outro número, também
    defensável; a escolha está registrada aqui e no PDF do item 5.

    Os JOIN são externos para que "cada residente" inclua quem ainda não
    realizou procedimento nenhum. Nesse caso o total é zero, e o CASE evita a
    divisão por zero devolvendo 0%.
    """
    pessoa_residente = aliased(Pessoa, name="pessoa_residente")

    total = func.count(ProcedimentoRealizado.id_procedimento)
    altos = func.count(ProcedimentoRealizado.id_procedimento).filter(
        Procedimento.nivel_risco == "ALTO"
    )

    percentual = case(
        (total == 0, cast(0, Numeric(5, 2))),
        else_=func.round(cast(100.0 * altos / total, Numeric(10, 4)), 2),
    )

    stmt = (
        select(
            pessoa_residente.id_pessoa.label("id_residente"),
            pessoa_residente.nome.label("residente"),
            Residente.ano_residencia,
            total.label("total_procedimentos"),
            altos.label("procedimentos_alto_risco"),
            percentual.label("percentual_alto_risco"),
        )
        .select_from(Residente)
        .join(pessoa_residente, pessoa_residente.id_pessoa == Residente.id_profissional)
        .outerjoin(Atendimento, Atendimento.id_residente == Residente.id_profissional)
        .outerjoin(
            ProcedimentoRealizado,
            ProcedimentoRealizado.id_atendimento == Atendimento.id_atendimento,
        )
        .outerjoin(
            Procedimento,
            Procedimento.id_procedimento == ProcedimentoRealizado.id_procedimento,
        )
        .group_by(
            pessoa_residente.id_pessoa,
            pessoa_residente.nome,
            Residente.ano_residencia,
        )
        .order_by(percentual.desc(), pessoa_residente.nome)
    )

    return [dict(linha._mapping) for linha in db.execute(stmt)]


def comparar_lazy_e_eager(db: Session) -> dict[str, Any]:
    """Mede o custo do carregamento sob demanda contra o adiantado.

    Percorre os atendimentos lendo o nome do paciente das duas formas e conta
    quantas instruções SQL cada uma provoca. A diferença é o N+1: no modo
    preguiçoso, cada acesso a atendimento.paciente.pessoa que ainda não está na
    sessão vira uma ida ao banco.

    Serve à exigência do enunciado de demonstrar lazy loading contra eager
    loading. A contagem usa um ouvinte de evento do engine.
    """
    from sqlalchemy import event

    contador = {"n": 0}

    def contar(conn, cursor, instrucao, parametros, contexto, muitos):
        contador["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", contar)
    try:
        # Sob demanda: um SELECT nos atendimentos e, depois, dois por
        # atendimento (paciente e pessoa) na primeira vez que cada um é lido.
        db.expunge_all()
        contador["n"] = 0
        nomes_lazy = []
        for a in db.execute(select(Atendimento).order_by(Atendimento.id_atendimento)).scalars():
            nomes_lazy.append(a.paciente.pessoa.nome)
        consultas_lazy = contador["n"]

        # Adiantado: o mesmo resultado em uma instrução.
        db.expunge_all()
        contador["n"] = 0
        stmt = (
            select(Atendimento)
            .options(joinedload(Atendimento.paciente).joinedload(Paciente.pessoa))
            .order_by(Atendimento.id_atendimento)
        )
        nomes_eager = [
            a.paciente.pessoa.nome
            for a in db.execute(stmt).unique().scalars()
        ]
        consultas_eager = contador["n"]
    finally:
        event.remove(engine, "before_cursor_execute", contar)

    return {
        "atendimentos": len(nomes_lazy),
        "consultas_lazy": consultas_lazy,
        "consultas_eager": consultas_eager,
        "resultados_iguais": nomes_lazy == nomes_eager,
        "observacao": (
            "O modo sob demanda emite uma consulta inicial e mais duas por "
            "atendimento ainda não carregado (paciente e pessoa). O adiantado "
            "resolve tudo em uma instrução com JOIN."
        ),
    }

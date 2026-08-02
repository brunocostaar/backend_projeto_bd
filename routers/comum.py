"""Auxiliares compartilhados pelas rotas com ORM."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modelos import Alergia, Paciente, Pessoa

# Erros que o banco devolve e o significado em HTTP. O PostgreSQL entrega o
# SQLSTATE em orig.pgcode; traduzir aqui evita despejar a mensagem crua do
# driver na resposta, que foi o que a Etapa 1 acabou fazendo.
CODIGOS_HTTP = {
    "23505": status.HTTP_409_CONFLICT,          # unique_violation
    "23503": status.HTTP_400_BAD_REQUEST,       # foreign_key_violation
    "23502": status.HTTP_400_BAD_REQUEST,       # not_null_violation
    "23514": status.HTTP_400_BAD_REQUEST,       # check_violation
    "22023": status.HTTP_400_BAD_REQUEST,       # invalid_parameter_value
    "P0001": status.HTTP_409_CONFLICT,          # raise_exception (procedures e triggers)
}


def mensagem_do_banco(erro: Exception) -> str:
    """Extrai a linha útil do erro do PostgreSQL.

    O psycopg2 devolve mensagem, DETAIL, HINT e o texto do comando. Só as
    primeiras linhas interessam a quem chamou a API.
    """
    original = getattr(erro, "orig", None) or erro
    texto = str(original).strip()
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    uteis = [linha for linha in linhas if not linha.startswith(("CONTEXT:", "LINE ", "  "))]
    return " ".join(uteis[:2]) if uteis else texto


def erro_do_banco(erro: Exception) -> HTTPException:
    """Converte erro do banco em HTTPException com código coerente."""
    original = getattr(erro, "orig", None)
    codigo = getattr(original, "pgcode", None)
    return HTTPException(
        status_code=CODIGOS_HTTP.get(codigo, status.HTTP_400_BAD_REQUEST),
        detail=mensagem_do_banco(erro),
    )


def confirmar(db: Session) -> None:
    """Commit com tradução de erro e rollback garantido."""
    try:
        db.commit()
    except IntegrityError as erro:
        db.rollback()
        raise erro_do_banco(erro) from erro
    except Exception as erro:
        db.rollback()
        raise erro_do_banco(erro) from erro


def nao_encontrado(descricao: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=descricao)


# ---------------------------------------------------------------------------
# Conversões entre o modelo mapeado e o formato que a API já usava na Etapa 1
# ---------------------------------------------------------------------------


def texto_para_alergias(texto: str | None) -> list[str]:
    """Quebra "dipirona, latex" na lista de alergias, sem repetição."""
    if not texto:
        return []
    vistas: list[str] = []
    for parte in texto.split(","):
        limpa = parte.strip()
        if limpa and limpa.lower() not in {v.lower() for v in vistas}:
            vistas.append(limpa)
    return vistas


def alergias_para_texto(paciente: Paciente) -> str | None:
    """Junta as alergias numa string, como a Etapa 1 fazia com string_agg."""
    if not paciente.alergias:
        return None
    return ", ".join(sorted(a.alergia for a in paciente.alergias))


def aplicar_alergias(paciente: Paciente, texto: str | None) -> None:
    """Substitui as alergias do paciente pelas do texto.

    A coleção é reatribuída em vez de apagada e recriada linha a linha: com
    delete-orphan, o SQLAlchemy compara a lista nova com a antiga e emite só os
    DELETE e INSERT necessários.
    """
    paciente.alergias = [
        Alergia(alergia=nome) for nome in texto_para_alergias(texto)
    ]


def dados_da_pessoa(pessoa: Pessoa) -> dict:
    return {
        "id_pessoa": pessoa.id_pessoa,
        "nome": pessoa.nome,
        "CPF": pessoa.CPF,
        "data_nascimento": pessoa.data_nascimento,
        "is_flamengo": pessoa.is_flamengo,
        "telefone": pessoa.telefone,
        "endereco": pessoa.endereco,
    }


def dados_do_paciente(paciente: Paciente) -> dict:
    return {
        **dados_da_pessoa(paciente.pessoa),
        "num_convenio": paciente.numero_convenio,
        "alergias": alergias_para_texto(paciente),
        "grupo_sanguineo": paciente.grupo_sanguineo,
    }


def dados_do_profissional(profissional) -> dict:
    return {
        **dados_da_pessoa(profissional.pessoa),
        "CRM": profissional.CRM,
        "data_admissao": profissional.data_admissao,
        "especialidade": profissional.especialidade,
    }


def remover_pessoa_se_orfa(db: Session, pessoa: Pessoa) -> bool:
    """Apaga a pessoa quando ela deixa de ter qualquer papel.

    O DER permite que a mesma pessoa seja paciente e profissional. Apagar o
    paciente e junto a pessoa, como a Etapa 1 faz, levaria embora o vínculo
    profissional dela. Aqui a linha de pessoa só sai quando nenhum papel resta.
    """
    db.flush()
    db.refresh(pessoa)
    if pessoa.paciente is None and pessoa.profissional is None:
        db.delete(pessoa)
        return True
    return False

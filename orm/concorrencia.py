"""Item 6 da Etapa 2: duas transações disputando a mesma escala.

O cenário é o do enunciado. Dois usuários tentam, ao mesmo tempo, escalar o
mesmo residente para o mesmo dia, turno e unidade. Sem cuidado, os dois leem
"não existe escala aí", os dois gravam, e o plantão fica duplicado.

Três estratégias são executadas, cada uma com duas threads e sessões separadas.
Uma barreira sincroniza o início para que a disputa aconteça de fato, em vez de
uma thread terminar antes da outra começar.

  sem protecao       só as restrições do banco decidem. A segunda transação
                     fica bloqueada no índice único e falha quando a primeira
                     confirma. Funciona, mas o erro chega como violação de
                     constraint.

  lock pessimista    cada transação pega SELECT ... FOR UPDATE na linha do
                     residente antes de consultar. A segunda espera a primeira
                     terminar, aí enxerga a escala recém-criada e desiste com
                     uma mensagem de negócio.

  lock otimista      ninguém bloqueia nada. A coluna escala.versao entra no
                     WHERE do UPDATE; quem gravar por último descobre que a
                     versão mudou e recebe StaleDataError.

Nada fica no banco: o que cada cenário cria é removido no fim.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from orm.modelos import Escala, Residente
from orm.sessao import SessionORM

# Combinação livre no seed: o residente 15 tem plantão no sábado à tarde e na
# sexta à tarde, nunca no domingo.
ID_RESIDENTE = 15
ID_PRECEPTOR = 10
ID_UNIDADE = 1
DIA = "domingo"
TURNO = "tarde"

# Impede que uma thread bloqueada trave a requisição inteira.
LOCK_TIMEOUT = "4s"


class Registro:
    """Coleta as linhas de log com o instante relativo ao início do cenário."""

    def __init__(self) -> None:
        self.inicio = time.monotonic()
        self.linhas: list[dict[str, str]] = []
        self.trava = threading.Lock()

    def anotar(self, ator: str, mensagem: str) -> None:
        decorrido = time.monotonic() - self.inicio
        with self.trava:
            self.linhas.append(
                {"instante": f"{decorrido:05.3f}s", "ator": ator, "mensagem": mensagem}
            )

    def ordenadas(self) -> list[dict[str, str]]:
        return sorted(self.linhas, key=lambda linha: linha["instante"])


def _preparar_sessao(db: Session) -> None:
    db.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


def _limpar() -> None:
    """Remove o que os cenários criaram.

    O filtro ignora o turno de propósito. O cenário otimista altera o turno da
    escala antes desta limpeza rodar, então casar por turno deixaria a linha
    para trás. O residente escolhido não tem nenhum plantão de domingo no seed,
    então apagar o dia inteiro só atinge o que a simulação criou.
    """
    with SessionORM() as db:
        db.execute(
            delete(Escala).where(
                Escala.id_residente == ID_RESIDENTE,
                Escala.dia_semana == DIA,
            )
        )
        db.commit()


def _executar_em_paralelo(alvo: Callable[[str, threading.Barrier], None]) -> None:
    barreira = threading.Barrier(2)
    threads = [
        threading.Thread(target=alvo, args=(nome, barreira), daemon=True)
        for nome in ("sessao A", "sessao B")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)


# ---------------------------------------------------------------------------
# Cenário 1: sem proteção explícita
# ---------------------------------------------------------------------------


def cenario_sem_protecao() -> dict[str, Any]:
    _limpar()
    registro = Registro()
    resultados: dict[str, str] = {}

    def trabalhar(nome: str, barreira: threading.Barrier) -> None:
        with SessionORM() as db:
            try:
                _preparar_sessao(db)
                registro.anotar(nome, "transação aberta")

                barreira.wait()

                existe = db.execute(
                    select(Escala).where(
                        Escala.id_residente == ID_RESIDENTE,
                        Escala.dia_semana == DIA,
                        Escala.turno == TURNO,
                    )
                ).first()
                registro.anotar(
                    nome,
                    "consultou antes de gravar: "
                    + ("já existe escala" if existe else "nenhuma escala encontrada"),
                )

                db.add(
                    Escala(
                        dia_semana=DIA,
                        turno=TURNO,
                        id_residente=ID_RESIDENTE,
                        id_preceptor=ID_PRECEPTOR,
                        id_unidade=ID_UNIDADE,
                    )
                )
                registro.anotar(nome, "INSERT enviado, aguardando o banco")
                db.commit()
                registro.anotar(nome, "commit concluído, escala gravada")
                resultados[nome] = "gravou"
            except IntegrityError as erro:
                db.rollback()
                registro.anotar(
                    nome, f"recusado pelo banco: {type(erro.orig).__name__}"
                )
                resultados[nome] = "recusado pela restrição"
            except DBAPIError as erro:
                db.rollback()
                registro.anotar(nome, f"erro de banco: {type(erro.orig).__name__}")
                resultados[nome] = "erro"

    _executar_em_paralelo(trabalhar)
    _limpar()

    gravaram = sum(1 for v in resultados.values() if v == "gravou")
    return {
        "cenario": "sem proteção explícita",
        "descricao": (
            "As duas transações consultam, não encontram nada e tentam gravar. "
            "Só as restrições do banco separam as duas."
        ),
        "desfecho": (
            f"{gravaram} transação gravou; a outra foi recusada pela UNIQUE do "
            "esquema. A consulta prévia das duas não viu conflito nenhum, o que "
            "mostra por que verificar antes de inserir não basta."
        ),
        "conflito_evitado": gravaram == 1,
        "log": registro.ordenadas(),
    }


# ---------------------------------------------------------------------------
# Cenário 2: lock pessimista
# ---------------------------------------------------------------------------


def cenario_lock_pessimista() -> dict[str, Any]:
    _limpar()
    registro = Registro()
    resultados: dict[str, str] = {}

    def trabalhar(nome: str, barreira: threading.Barrier) -> None:
        with SessionORM() as db:
            try:
                _preparar_sessao(db)
                registro.anotar(nome, "transação aberta")

                barreira.wait()

                registro.anotar(nome, "pedindo SELECT ... FOR UPDATE no residente")
                db.execute(
                    select(Residente)
                    .where(Residente.id_profissional == ID_RESIDENTE)
                    .with_for_update()
                ).scalar_one()
                registro.anotar(nome, "bloqueio obtido, ninguém mais mexe neste residente")

                existe = db.execute(
                    select(Escala).where(
                        Escala.id_residente == ID_RESIDENTE,
                        Escala.dia_semana == DIA,
                        Escala.turno == TURNO,
                    )
                ).first()

                if existe:
                    registro.anotar(
                        nome, "escala já existe; desistindo sem tentar gravar"
                    )
                    resultados[nome] = "desistiu com mensagem de negócio"
                    db.rollback()
                    return

                db.add(
                    Escala(
                        dia_semana=DIA,
                        turno=TURNO,
                        id_residente=ID_RESIDENTE,
                        id_preceptor=ID_PRECEPTOR,
                        id_unidade=ID_UNIDADE,
                    )
                )
                db.commit()
                registro.anotar(nome, "commit concluído, bloqueio liberado")
                resultados[nome] = "gravou"
            except DBAPIError as erro:
                db.rollback()
                registro.anotar(nome, f"erro de banco: {type(erro.orig).__name__}")
                resultados[nome] = "erro"

    _executar_em_paralelo(trabalhar)
    _limpar()

    gravaram = sum(1 for v in resultados.values() if v == "gravou")
    desistiram = sum(1 for v in resultados.values() if v.startswith("desistiu"))
    return {
        "cenario": "lock pessimista",
        "descricao": (
            "Cada transação bloqueia a linha do residente com SELECT ... FOR "
            "UPDATE antes de consultar. Uma espera a outra terminar."
        ),
        "desfecho": (
            f"{gravaram} gravou e {desistiram} desistiu depois de ver a escala já "
            "criada. Nenhuma violação de constraint apareceu: a segunda "
            "transação enxergou o estado atualizado e recusou por regra de "
            "negócio, com mensagem legível."
        ),
        "conflito_evitado": gravaram == 1 and desistiram == 1,
        "log": registro.ordenadas(),
    }


# ---------------------------------------------------------------------------
# Cenário 3: lock otimista
# ---------------------------------------------------------------------------


def cenario_lock_otimista() -> dict[str, Any]:
    _limpar()
    registro = Registro()
    resultados: dict[str, str] = {}

    with SessionORM() as db:
        escala = Escala(
            dia_semana=DIA,
            turno=TURNO,
            id_residente=ID_RESIDENTE,
            id_preceptor=ID_PRECEPTOR,
            id_unidade=ID_UNIDADE,
        )
        db.add(escala)
        db.commit()
        id_escala = escala.id_escala
        versao_inicial = escala.versao

    registro.anotar("preparo", f"escala {id_escala} criada na versão {versao_inicial}")

    def trabalhar(nome: str, barreira: threading.Barrier) -> None:
        turno_novo = "manha" if nome == "sessao A" else "noite"
        with SessionORM() as db:
            try:
                _preparar_sessao(db)
                escala = db.get(Escala, id_escala)
                registro.anotar(nome, f"carregou a escala na versão {escala.versao}")

                barreira.wait()

                escala.turno = turno_novo
                registro.anotar(nome, f"tentando gravar turno={turno_novo}")
                db.commit()
                registro.anotar(nome, f"commit aceito, versão agora {escala.versao}")
                resultados[nome] = "gravou"
            except StaleDataError:
                db.rollback()
                registro.anotar(
                    nome,
                    "StaleDataError: a versão mudou entre a leitura e a gravação",
                )
                resultados[nome] = "recusado pela versão"
            except DBAPIError as erro:
                db.rollback()
                registro.anotar(nome, f"erro de banco: {type(erro.orig).__name__}")
                resultados[nome] = "erro"

    _executar_em_paralelo(trabalhar)

    with SessionORM() as db:
        final = db.get(Escala, id_escala)
        if final is not None:
            registro.anotar(
                "verificação",
                f"estado final: turno={final.turno}, versão={final.versao}",
            )
    _limpar()

    gravaram = sum(1 for v in resultados.values() if v == "gravou")
    recusados = sum(1 for v in resultados.values() if v == "recusado pela versão")
    return {
        "cenario": "lock otimista",
        "descricao": (
            "As duas sessões carregam a mesma escala e alteram o turno. Nenhuma "
            "bloqueia nada; a coluna versao entra no WHERE do UPDATE."
        ),
        "desfecho": (
            f"{gravaram} gravou e {recusados} recebeu StaleDataError. A alteração "
            "da primeira não foi sobrescrita, que é o que aconteceria sem o "
            "controle de versão."
        ),
        "conflito_evitado": gravaram == 1 and recusados == 1,
        "log": registro.ordenadas(),
    }


def simular() -> dict[str, Any]:
    """Roda os três cenários em sequência."""
    return {
        "cenarios": [
            cenario_sem_protecao(),
            cenario_lock_pessimista(),
            cenario_lock_otimista(),
        ]
    }

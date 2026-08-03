"""Mapeamento objeto-relacional das tabelas do hospital (Etapa 2).

As classes descrevem as tabelas criadas pelo 01_schema.sql e pelo
05_etapa2_estrutura.sql. Nada aqui cria ou altera tabela: o esquema continua
sendo responsabilidade dos scripts SQL, e o Base.metadata só é usado para
leitura. Rodar create_all() contra este metadata seria um segundo caminho para
definir o banco, com risco de divergir do que os scripts fazem.

Sobre a herança de Pessoa
-------------------------
O DER especifica duas especializações diferentes. Pessoa para Paciente e
Profissional é compartilhada e total: a mesma pessoa pode ser as duas coisas.
Profissional para Preceptor e Residente é exclusiva: em um dado momento o
profissional ocupa um papel só.

A herança mapeada do SQLAlchemy (joined table inheritance) não representa o
primeiro caso. Ela assume que uma linha da tabela pai corresponde a exatamente
uma subclasse, e o mapa de identidade guarda um objeto por chave primária: a
mesma pessoa não pode ser carregada como Paciente e como Profissional ao mesmo
tempo. Além disso o esquema não tem coluna discriminadora.

Por isso as especializações são mapeadas como relacionamentos um-para-um, com
uselist=False. O resultado no banco é idêntico ao da herança física, e a pessoa
que for paciente e profissional ao mesmo tempo continua representável.

Sobre os nomes das colunas
--------------------------
O 01_schema.sql declara CPF e CRM sem aspas, e o PostgreSQL guarda os dois em
minúsculo. Os atributos aqui mantêm a forma maiúscula porque os schemas Pydantic
da Etapa 1 esperam esses nomes na resposta da API; o primeiro argumento de
mapped_column diz qual é a coluna real.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Hierarquia de pessoas
# ---------------------------------------------------------------------------


class Pessoa(Base):
    __tablename__ = "pessoa"

    id_pessoa: Mapped[int] = mapped_column(Integer, primary_key=True)
    CPF: Mapped[str] = mapped_column("cpf", String(11), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    is_flamengo: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    endereco: Mapped[Optional[str]] = mapped_column(String(200))
    telefone: Mapped[Optional[str]] = mapped_column(String(20))
    data_nascimento: Mapped[date] = mapped_column(Date, nullable=False)

    paciente: Mapped[Optional[Paciente]] = relationship(
        back_populates="pessoa", uselist=False, cascade="all, delete-orphan"
    )
    profissional: Mapped[Optional[Profissional]] = relationship(
        back_populates="pessoa", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Pessoa {self.id_pessoa} {self.nome!r}>"


class Paciente(Base):
    __tablename__ = "paciente"

    id_pessoa: Mapped[int] = mapped_column(
        Integer, ForeignKey("pessoa.id_pessoa", ondelete="CASCADE"), primary_key=True
    )
    numero_convenio: Mapped[str] = mapped_column(String(20), nullable=False)
    grupo_sanguineo: Mapped[str] = mapped_column(String(3), nullable=False)

    pessoa: Mapped[Pessoa] = relationship(back_populates="paciente")
    alergias: Mapped[list[Alergia]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan"
    )
    atendimentos: Mapped[list[Atendimento]] = relationship(back_populates="paciente")
    internacoes: Mapped[list[Internacao]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Paciente {self.id_pessoa}>"


class Alergia(Base):
    __tablename__ = "alergia"

    alergia: Mapped[str] = mapped_column(String(30), primary_key=True)
    id_pessoa: Mapped[int] = mapped_column(
        Integer, ForeignKey("paciente.id_pessoa", ondelete="CASCADE"), primary_key=True
    )

    paciente: Mapped[Paciente] = relationship(back_populates="alergias")

    def __repr__(self) -> str:
        return f"<Alergia {self.alergia!r} paciente={self.id_pessoa}>"


class Profissional(Base):
    __tablename__ = "profissional"

    id_pessoa: Mapped[int] = mapped_column(
        Integer, ForeignKey("pessoa.id_pessoa", ondelete="CASCADE"), primary_key=True
    )
    CRM: Mapped[str] = mapped_column("crm", String(30), unique=True, nullable=False)
    data_admissao: Mapped[Optional[date]] = mapped_column(Date)
    especialidade: Mapped[str] = mapped_column(String(50), nullable=False)

    pessoa: Mapped[Pessoa] = relationship(back_populates="profissional")
    preceptor: Mapped[Optional[Preceptor]] = relationship(
        back_populates="profissional", uselist=False, cascade="all, delete-orphan"
    )
    residente: Mapped[Optional[Residente]] = relationship(
        back_populates="profissional", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Profissional {self.id_pessoa} {self.CRM!r}>"


class Preceptor(Base):
    __tablename__ = "preceptor"

    id_profissional: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profissional.id_pessoa", ondelete="CASCADE"),
        primary_key=True,
    )
    titulacao: Mapped[str] = mapped_column(String(30), nullable=False)

    profissional: Mapped[Profissional] = relationship(back_populates="preceptor")
    atendimentos: Mapped[list[Atendimento]] = relationship(back_populates="preceptor")
    escalas: Mapped[list[Escala]] = relationship(back_populates="preceptor")

    def __repr__(self) -> str:
        return f"<Preceptor {self.id_profissional} {self.titulacao!r}>"


class Residente(Base):
    __tablename__ = "residente"

    id_profissional: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profissional.id_pessoa", ondelete="CASCADE"),
        primary_key=True,
    )
    ano_residencia: Mapped[str] = mapped_column(String(2), nullable=False)

    profissional: Mapped[Profissional] = relationship(back_populates="residente")
    atendimentos: Mapped[list[Atendimento]] = relationship(back_populates="residente")
    escalas: Mapped[list[Escala]] = relationship(back_populates="residente")

    def __repr__(self) -> str:
        return f"<Residente {self.id_profissional} {self.ano_residencia}>"


# ---------------------------------------------------------------------------
# Estrutura do hospital e atendimento
# ---------------------------------------------------------------------------


class Unidade(Base):
    __tablename__ = "unidade"

    id_unidade: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo: Mapped[Optional[str]] = mapped_column(String(30))
    capacidade_leitos: Mapped[Optional[int]] = mapped_column(Integer)

    escalas: Mapped[list[Escala]] = relationship(back_populates="unidade")
    atendimentos: Mapped[list[Atendimento]] = relationship(back_populates="unidade")
    internacoes: Mapped[list[Internacao]] = relationship(back_populates="unidade")

    def __repr__(self) -> str:
        return f"<Unidade {self.id_unidade} {self.nome!r}>"


class Atendimento(Base):
    __tablename__ = "atendimento"

    id_atendimento: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duracao_minutos: Mapped[Optional[int]] = mapped_column(Integer)
    id_preceptor: Mapped[int] = mapped_column(
        Integer, ForeignKey("preceptor.id_profissional"), nullable=False
    )
    id_paciente: Mapped[int] = mapped_column(
        Integer, ForeignKey("paciente.id_pessoa"), nullable=False
    )
    id_residente: Mapped[int] = mapped_column(
        Integer, ForeignKey("residente.id_profissional"), nullable=False
    )
    # Acrescentada na Etapa 2 e deixada opcional: os endpoints em SQL puro da
    # Etapa 1 gravam atendimento sem informar unidade.
    id_unidade: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("unidade.id_unidade")
    )

    paciente: Mapped[Paciente] = relationship(back_populates="atendimentos")
    residente: Mapped[Residente] = relationship(back_populates="atendimentos")
    preceptor: Mapped[Preceptor] = relationship(back_populates="atendimentos")
    unidade: Mapped[Optional[Unidade]] = relationship(back_populates="atendimentos")
    procedimentos_realizados: Mapped[list[ProcedimentoRealizado]] = relationship(
        back_populates="atendimento", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Atendimento {self.id_atendimento} {self.data_hora}>"


class Procedimento(Base):
    __tablename__ = "procedimento"

    id_procedimento: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    tempo_medio_minutos: Mapped[Optional[int]] = mapped_column(Integer)
    nivel_risco: Mapped[Optional[str]] = mapped_column(String(15))
    # Mantida pelo trg_atualiza_media_procedimentos. A aplicação lê, não escreve.
    media_tempo_procedimento: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 2))

    realizacoes: Mapped[list[ProcedimentoRealizado]] = relationship(
        back_populates="procedimento"
    )

    def __repr__(self) -> str:
        return f"<Procedimento {self.id_procedimento} {self.nome!r}>"


class ProcedimentoRealizado(Base):
    __tablename__ = "procedimento_realizado"

    id_atendimento: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("atendimento.id_atendimento", ondelete="CASCADE"),
        primary_key=True,
    )
    id_procedimento: Mapped[int] = mapped_column(
        Integer, ForeignKey("procedimento.id_procedimento"), primary_key=True
    )
    quantidade: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    tempo_real_minutos: Mapped[Optional[int]] = mapped_column(Integer)
    observacao: Mapped[Optional[str]] = mapped_column(String(1000))
    faturado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    # Acrescentada na Etapa 2 para o cálculo de tempo médio de espera.
    data_hora_inicio: Mapped[Optional[datetime]] = mapped_column(DateTime)

    atendimento: Mapped[Atendimento] = relationship(
        back_populates="procedimentos_realizados"
    )
    procedimento: Mapped[Procedimento] = relationship(back_populates="realizacoes")

    def __repr__(self) -> str:
        return (
            f"<ProcedimentoRealizado atendimento={self.id_atendimento} "
            f"procedimento={self.id_procedimento}>"
        )


class Escala(Base):
    __tablename__ = "escala"
    __table_args__ = (
        UniqueConstraint(
            "id_residente",
            "dia_semana",
            "turno",
            name="uq_escala_residente_dia_turno",
        ),
    )

    id_escala: Mapped[int] = mapped_column(Integer, primary_key=True)
    dia_semana: Mapped[str] = mapped_column(String(15), nullable=False)
    turno: Mapped[str] = mapped_column(String(15), nullable=False)
    id_preceptor: Mapped[int] = mapped_column(
        Integer, ForeignKey("preceptor.id_profissional", ondelete="CASCADE"),
        nullable=False,
    )
    id_residente: Mapped[int] = mapped_column(
        Integer, ForeignKey("residente.id_profissional", ondelete="CASCADE"),
        nullable=False,
    )
    id_unidade: Mapped[int] = mapped_column(
        Integer, ForeignKey("unidade.id_unidade", ondelete="CASCADE"), nullable=False
    )
    versao: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    unidade: Mapped[Unidade] = relationship(back_populates="escalas")
    residente: Mapped[Residente] = relationship(back_populates="escalas")
    preceptor: Mapped[Preceptor] = relationship(back_populates="escalas")

    # Controle de concorrência otimista. A cada UPDATE o SQLAlchemy acrescenta
    # "AND versao = <valor lido>" ao WHERE e incrementa a coluna. Se outra
    # transação gravou antes, nenhuma linha é afetada e o flush levanta
    # StaleDataError, em vez de sobrescrever a alteração alheia.
    __mapper_args__ = {"version_id_col": versao}

    def __repr__(self) -> str:
        return (
            f"<Escala {self.id_escala} {self.dia_semana}/{self.turno} "
            f"unidade={self.id_unidade} v{self.versao}>"
        )


# ---------------------------------------------------------------------------
# Tabelas da Etapa 2
# ---------------------------------------------------------------------------


class Internacao(Base):
    __tablename__ = "internacao"

    id_internacao: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_paciente: Mapped[int] = mapped_column(
        Integer, ForeignKey("paciente.id_pessoa", ondelete="CASCADE"), nullable=False
    )
    id_unidade: Mapped[int] = mapped_column(
        Integer, ForeignKey("unidade.id_unidade"), nullable=False
    )
    data_hora_entrada: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_hora_saida: Mapped[Optional[datetime]] = mapped_column(DateTime)
    motivo: Mapped[Optional[str]] = mapped_column(String(200))

    paciente: Mapped[Paciente] = relationship(back_populates="internacoes")
    unidade: Mapped[Unidade] = relationship(back_populates="internacoes")

    @property
    def aberta(self) -> bool:
        return self.data_hora_saida is None

    def __repr__(self) -> str:
        estado = "aberta" if self.aberta else "encerrada"
        return f"<Internacao {self.id_internacao} paciente={self.id_paciente} {estado}>"


class AuditoriaAtendimento(Base):
    __tablename__ = "auditoria_atendimento"

    id_auditoria: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Sem ForeignKey de propósito: a linha de auditoria de um DELETE precisa
    # continuar existindo depois que o atendimento sai da tabela.
    id_atendimento: Mapped[Optional[int]] = mapped_column(Integer)
    operacao: Mapped[str] = mapped_column(String(6), nullable=False)
    usuario: Mapped[str] = mapped_column(String(63), nullable=False)
    data_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    dados_antigos: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    dados_novos: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    def __repr__(self) -> str:
        return (
            f"<AuditoriaAtendimento {self.id_auditoria} {self.operacao} "
            f"atendimento={self.id_atendimento}>"
        )

# Plano: CRUD FastAPI com SQL puro

Este plano orientou a construção da API usando consultas SQL escritas à mão,
em vez do ORM do SQLAlchemy. A herança do modelo (Pessoa, Paciente,
Profissional, Preceptor, Residente) é tratada como tabelas relacionais comuns
ligadas por chave estrangeira.

## Instalação

No ambiente virtual do projeto:

```bash
pip install fastapi uvicorn psycopg2-binary sqlalchemy
```

Por que instalar SQLAlchemy se as consultas são SQL puro? Ele é usado apenas
como gerenciador de conexões: abre, fecha e reaproveita conexões com o
PostgreSQL, e permite executar consultas com `db.execute(text("SELECT ..."))`.

## Estrutura de arquivos

```
projeto-bd/
├── database.py              conexão com o banco e gerador de sessões
├── main.py                  aplicação principal, registra as rotas
├── schemas/                 validação de entrada e saída (Pydantic)
│   ├── __init__.py
│   ├── pessoa.py            Pessoa, Paciente, Preceptor, Residente
│   ├── unidade.py
│   ├── procedimento.py      Procedimento e Procedimento Realizado
│   ├── atendimento.py
│   └── escala.py
└── routers/                 endpoints (POST, GET, PUT, DELETE)
    ├── __init__.py
    ├── pessoa.py            Pacientes, Preceptores e Residentes
    ├── unidade.py
    ├── procedimento.py
    ├── procedimento_realizado.py
    ├── atendimento.py
    └── escala.py
```

## Endpoints

### routers/unidade.py

Tabela isolada, boa para testar a primeira consulta.

- `POST /unidades/`: insere uma unidade
- `GET /unidades/`: lista todas
- `GET /unidades/{id}`: busca uma unidade
- `PUT /unidades/{id}`: atualiza
- `DELETE /unidades/{id}`: remove

### routers/procedimento.py e procedimento_realizado.py

- `POST /procedimentos/`, `GET /procedimentos/`, `GET/PUT/DELETE
  /procedimentos/{id}`: CRUD do catálogo de procedimentos, incluindo
  `nivel_risco`
- `POST /procedimentos-realizados/`: registra quantidade, tempo real e
  observação de um procedimento em um atendimento
- `GET/PUT/DELETE /procedimentos-realizados/{id_atendimento}/{id_procedimento}`:
  operações sobre um registro, identificado pela chave composta

### routers/pessoa.py (herança em SQL)

Como o banco tem herança física (a tabela filha aponta para a pai por FK),
os endpoints inserem em mais de uma tabela dentro da mesma transação.

Paciente:

- `POST /pacientes/`: abre transação, insere em `pessoa` com
  `RETURNING id_pessoa`, usa esse id para inserir em `paciente`
  (`numero_convenio`, `grupo_sanguineo`) e grava cada alergia como uma linha
  na tabela `alergia`. Confirma tudo no final; qualquer falha desfaz a
  transação inteira.
- `GET /pacientes/` e `GET /pacientes/{id}`: JOIN de `paciente` com `pessoa`,
  reagrupando as alergias em uma string com `string_agg`
- `PUT /pacientes/{id}`: atualiza `pessoa` e `paciente`, apaga as alergias
  antigas e insere as novas
- `DELETE /pacientes/{id}`: remove de `paciente` e depois de `pessoa`
  (as alergias saem em cascata)

Preceptor e Residente seguem a mesma lógica, com um nível a mais:
`pessoa`, depois `profissional`, depois `preceptor` ou `residente`.
A listagem faz JOIN das três tabelas. Detalhe do PostgreSQL: colunas como
CPF e CRM precisam de alias com aspas (`pe.CPF AS "CPF"`) porque o banco
devolve nomes em minúsculo e o Pydantic diferencia maiúsculas.

### routers/atendimento.py

- `POST /atendimentos/`: antes de inserir, consulta se `id_paciente`,
  `id_residente` e `id_preceptor` existem e devolve 400 se algum não existir
- `GET /atendimentos/`, `GET/PUT/DELETE /atendimentos/{id}`: demais operações

### routers/escala.py

- `POST /escalas/`: valida as FKs e verifica a restrição
  `UNIQUE(id_unidade, dia_semana, turno, id_residente)` antes de inserir,
  devolvendo 409 em caso de conflito
- `GET /escalas/`, `GET/PUT/DELETE /escalas/{id}`: demais operações

## Como executar SQL puro no FastAPI

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter()

@router.get("/unidades/")
def listar_unidades(db: Session = Depends(get_db)):
    query = text("SELECT id_unidade, nome, tipo, capacidade_leitos FROM unidade")
    result = db.execute(query)

    # o SQLAlchemy devolve objetos Row; convertemos para dicionários
    return [dict(row._mapping) for row in result]
```

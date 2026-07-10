# 🛠️ Plano: CRUD FastAPI com SQL Manual (Raw SQL)

Este plano foi adaptado para usar **consultas SQL manuais (Raw SQL)** em vez do ORM do SQLAlchemy. Isso simplifica o entendimento da herança, pois tratamos as tabelas no banco como tabelas relacionais clássicas conectadas por Chave Estrangeira (FK).

---

## 1. Comando de Instalação

Abra o terminal na pasta do seu projeto e execute o comando abaixo para instalar as bibliotecas necessárias no seu ambiente virtual:

```bash
.venv/bin/pip install psycopg2-binary sqlalchemy
```

> **Por que SQLAlchemy se vamos usar SQL manual?**
> Usaremos o SQLAlchemy apenas como um **gerenciador de conexão (Connection Pool)**. Ele cuidará de abrir, fechar e reaproveitar conexões com o PostgreSQL de forma segura e eficiente, permitindo rodar consultas usando a função `db.execute(text("SELECT ..."))`.

---

## 2. Estrutura de Arquivos

Aqui estão os arquivos que você deve criar na raiz do seu projeto:

```
projeto-bd/
├── database.py              ← Configuração da conexão com o banco e gerador de sessões
├── main.py                  ← Arquivo principal (já existe, você vai registrar as rotas aqui)
├── schemas/                 ← Validação dos dados que entram e saem da API (Pydantic)
│   ├── __init__.py
│   ├── pessoa.py            ← Schemas para Pessoa, Paciente, Preceptor, Residente
│   ├── unidade.py           ← Schemas para Unidades de Saúde
│   ├── procedimento.py      ← Schemas para Procedimentos e Realizados
│   ├── atendimento.py       ← Schemas para Atendimentos
│   └── escala.py            ← Schemas para Escalas
└── routers/                 ← Endpoints (Ações HTTP: POST, GET, PUT, DELETE)
    ├── __init__.py
    ├── pessoa.py            ← Endpoints de Pessoas, Pacientes e Profissionais
    ├── unidade.py
    ├── procedimento.py
    ├── atendimento.py
    └── escala.py
```

---

## 3. Endpoints a Serem Gerados

Aqui está a lista exata de endpoints que você deve declarar em cada arquivo da pasta `routers/`.

### 📍 `routers/unidade.py` (Recomendo começar por aqui)
Tabela isolada, ideal para testar a primeira consulta SQL manual.
* **`POST /unidades/`**: Insere uma nova unidade (`INSERT INTO unidade...`).
* **`GET /unidades/`**: Retorna todas as unidades (`SELECT * FROM unidade`).
* **`GET /unidades/{id}`**: Busca uma unidade específica (`SELECT * FROM unidade WHERE id_unidade = :id`).
* **`PUT /unidades/{id}`**: Atualiza dados da unidade (`UPDATE unidade SET...`).
* **`DELETE /unidades/{id}`**: Remove a unidade (`DELETE FROM unidade WHERE...`).

---

### 📍 `routers/procedimento.py`
Gerencia a tabela `procedimento` e a tabela associativa `procedimento_realizado`.
* **`POST /procedimentos/`**: Cria procedimento (`INSERT INTO procedimento...`).
* **`GET /procedimentos/`**: Lista todos.
* **`PUT /procedimentos/{id}`**: Atualiza (`incluindo nivel_risco`).
* **`DELETE /procedimentos/{id}`**: Remove.
* **`POST /procedimentos-realizados/`**: Registra quantidade e tempo real de um procedimento em um atendimento (`INSERT INTO procedimento_realizado...`).
* **`GET /procedimentos-realizados/{id_atendimento}/{id_procedimento}`**: Detalha um registro específico.
* **`DELETE /procedimentos-realizados/{id_atendimento}/{id_procedimento}`**: Remove o registro.

---

### 📍 `routers/pessoa.py` (Lógica da Herança em SQL)
Como o banco de dados tem herança física (FKs para a tabela pai), os endpoints específicos devem lidar com essa lógica manualmente usando transações.

#### Endpoints de Paciente:
* **`POST /pacientes/`**:
  1. Abre transação.
  2. Executa `INSERT INTO pessoa (nome, cpf, data_nascimento, is_flamengo, telefone, endereco) VALUES (...) RETURNING id_pessoa;`.
  3. Pega o `id_pessoa` retornado e executa `INSERT INTO paciente (id_pessoa, num_convenio, alergias, grupo_sanguineo) VALUES (:id_pessoa, ...);`.
  4. Confirma a transação.
* **`GET /pacientes/`**:
  - Consulta: `SELECT * FROM paciente INNER JOIN pessoa ON paciente.id_pessoa = pessoa.id_pessoa;`
* **`GET /pacientes/{id}`**:
  - Consulta com JOIN filtrando por `id_pessoa`.
* **`PUT /pacientes/{id}`**:
  - Atualiza as duas tabelas (`pessoa` e `paciente`) sob o mesmo ID.
* **`DELETE /pacientes/{id}`**:
  - Remove de `paciente`, depois de `pessoa`.

#### Endpoints de Preceptor e Residente:
Siga a mesma lógica acima. No POST, você insere na tabela correspondente.
* **`POST /preceptores/`**: Insere em `pessoa` → pega ID → insere em `profissional` → pega ID → insere em `preceptor`.
* **`GET /preceptores/`**: Faz um `JOIN` de `preceptor` + `profissional` + `pessoa`.
* **`POST /residentes/`**: Insere em `pessoa` → insere em `profissional` → insere em `residente`.
* **`GET /residentes/`**: Faz um `JOIN` de `residente` + `profissional` + `pessoa`.

---

### 📍 `routers/atendimento.py`
Gerencia os atendimentos médicos.
* **`POST /atendimentos/`**: Registra atendimento (`INSERT INTO atendimento...`).
  - *Validação manual*: Antes de inserir, execute consultas para garantir que `id_paciente`, `id_residente` e `id_preceptor` existem.
* **`GET /atendimentos/`**: Lista atendimentos (com opção de trazer os nomes do paciente e médicos via `JOIN`).
* **`DELETE /atendimentos/{id}`**: Remove.

---

### 📍 `routers/escala.py`
Controla a alocação de residentes e preceptores.
* **`POST /escalas/`**: Cria uma escala (`INSERT INTO escala...`).
  - *Validação de Unique*: O banco lançará erro se a constraint `UNIQUE(id_unidade, dia_semana, turno, id_residente)` for violada. Capture essa exceção e retorne uma mensagem amigável (ex: `HTTP 409 Conflict`).
* **`GET /escalas/`**: Lista as escalas configuradas.
* **`DELETE /escalas/{id}`**: Remove a escala.

---

## 4. Dica: Como executar SQL Manual no FastAPI

Para executar SQL manual, você usará a função `text` do SQLAlchemy dentro da rota:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter()

@router.get("/unidades/")
def listar_unidades(db: Session = Depends(get_db)):
    # Usando SQL manual puro
    query = text("SELECT id_unidade, nome, tipo, capacidade_leitos FROM unidade")
    result = db.execute(query)
    
    # O SQLAlchemy retorna linhas (Row objects), convertemos para uma lista de dicionários
    unidades = [dict(row._mapping) for row in result]
    return unidades
```

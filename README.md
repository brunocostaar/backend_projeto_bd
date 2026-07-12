# Backend do Sistema de Gestão Hospitalar

API REST do projeto da disciplina de Banco de Dados (Hospital Universitário
Dra. Yuska Maritan Brito). Feita com FastAPI e PostgreSQL. Todas as consultas
são SQL puro, como pede a Etapa 1 do trabalho: o SQLAlchemy entra apenas como
gerenciador de conexões, sem ORM.

## Requisitos

- Docker (para o banco de dados)
- Python 3.11 ou superior

## Como executar

1. Suba o banco. Na primeira vez, o contêiner cria o banco
   `hospital_universitario`, executa o schema (`01_schema.sql`) e insere os
   dados de teste (`02_seed.sql`):

   ```
   docker compose up -d
   ```

2. Instale as dependências:

   ```
   pip install fastapi uvicorn sqlalchemy psycopg2-binary
   ```

3. Inicie a API:

   ```
   uvicorn main:app --reload
   ```

A API fica em http://localhost:8000 e a documentação interativa em
http://localhost:8000/docs.

Para recriar o banco do zero (apaga tudo e roda os scripts de novo):

```
docker compose down -v
docker compose up -d
```

## Estrutura do projeto

- `01_schema.sql`: criação das tabelas, com PK, FK, CHECK, NOT NULL e UNIQUE
- `02_seed.sql`: massa de dados de teste
- `docker-compose.yml`: PostgreSQL 16 com execução automática dos scripts
- `database.py`: conexão com o banco e injeção de sessão nas rotas
- `main.py`: aplicação FastAPI e registro dos routers
- `schemas/`: validação de entrada e saída (Pydantic)
- `routers/`: endpoints, um arquivo por entidade
- `modelo_relacional.pdf`: modelo relacional gerado a partir do schema

## Endpoints

A lista completa, com os corpos de requisição, está em `/docs`. Resumo:

- `/pacientes/`: criar, listar, buscar, atualizar e excluir
- `/preceptores/`: criar e listar
- `/residentes/`: criar, listar, buscar, atualizar e excluir
- `/unidades/`: CRUD completo
- `/procedimentos/`: CRUD completo
- `/procedimentos-realizados/`: registrar, buscar, atualizar e excluir pela
  chave composta (atendimento e procedimento)
- `/atendimentos/`: CRUD completo, com validação de paciente, residente e
  preceptor antes de inserir
- `/escalas/`: CRUD completo, devolvendo 409 quando a escala viola a
  restrição de unicidade (unidade, dia, turno, residente)

## Observações

As alergias do paciente são gravadas na tabela `alergia`, uma linha por
alergia, conforme a normalização documentada no projeto. A API recebe e
devolve o campo `alergias` como texto separado por vírgulas e faz a conversão
internamente.

O frontend fica em um repositório separado:
https://github.com/hglucena/frontend_projeto_bd

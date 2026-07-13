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

Se a porta 5432 já estiver em uso na máquina (um PostgreSQL local, por
exemplo), altere o mapeamento em `docker-compose.yml` para outra porta, como
`"15432:5432"`, e ajuste a conexão em `database.py`.

## Estrutura do projeto

- `01_schema.sql`: criação das tabelas, com PK, FK, CHECK, NOT NULL e UNIQUE
- `02_seed.sql`: massa de dados de teste
- `04_analiticas.sql`: as 4 consultas analíticas da Etapa 1
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

## Consultas analíticas

O arquivo `04_analiticas.sql` contém as 4 consultas da Etapa 1. Elas não
rodam automaticamente na subida do contêiner (não alteram o banco); execute
com o banco já populado:

```
docker compose exec -T db psql -U postgres -d hospital_universitario < 04_analiticas.sql
```

1. **Ranking de residentes** por número de atendimentos (`LEFT JOIN` para que
   residente sem atendimento apareça com total 0).
2. **Preceptores com mais de 5 atendimentos** em um mês (`GROUP BY` +
   `HAVING`; troque a data no `WHERE` para consultar outro mês — o seed tem o
   caso do preceptor Fernando Alves com 6 atendimentos em julho/2026).
3. **Plantões por residente em cada unidade.** Decisão de projeto: a tabela
   `escala` é uma grade semanal (`dia_semana` + `turno`), sem data concreta,
   então "mês corrente" admite duas leituras e a consulta traz as duas — a
   versão A conta os slots semanais de cada residente por unidade, e a
   versão B projeta a grade nos dias do mês atual (uma escala de segunda
   conta uma vez por segunda-feira existente no mês).
4. **Pacientes que nunca realizaram procedimento de risco ALTO**
   (`NOT EXISTS`, que ao contrário de `NOT IN` não quebra com `NULL`).

## Observações

As alergias do paciente são gravadas na tabela `alergia`, uma linha por
alergia, conforme a normalização documentada no projeto. A API recebe e
devolve o campo `alergias` como texto separado por vírgulas e faz a conversão
internamente.

O frontend fica em um repositório separado:
https://github.com/hglucena/frontend_projeto_bd

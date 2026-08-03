# Backend do Sistema de Gestão Hospitalar

API do projeto de Banco de Dados do Hospital Universitário Dra. Yuska Maritan Brito. O backend usa FastAPI, SQLAlchemy e PostgreSQL 16. O esquema é criado por scripts SQL; a aplicação mapeia essas tabelas e publica uma única API.

O estado atual tem 37 caminhos e 64 operações no OpenAPI. A Etapa 2 acrescentou duas procedures, uma function, 13 triggers, três views, consultas pela DSL do SQLAlchemy e três cenários de concorrência. A última execução completa da suíte terminou com 126 testes aprovados.

## Requisitos

- Docker com o comando `docker compose`
- Python 3.11 ou superior

## Execução local

Na pasta do backend, suba o PostgreSQL:

```powershell
docker compose up -d --wait
```

Instale as dependências da API e dos testes:

```powershell
python -m pip install fastapi uvicorn sqlalchemy psycopg2-binary pytest httpx
```

Inicie a aplicação:

```powershell
uvicorn main:app --reload
```

A API responde em `http://localhost:8000`. O contrato interativo fica em `http://localhost:8000/docs`.

O valor padrão de `DATABASE_URL` aponta para `postgresql://postgres:postgres@localhost:5432/hospital_universitario`. Defina essa variável antes de iniciar a API quando o banco estiver em outro host ou porta.

Para recriar o banco desde o início, remova o volume e suba o serviço novamente. Este comando apaga os dados locais:

```powershell
docker compose down -v
docker compose up -d --wait
```

## Carga do banco

O compose monta sete arquivos na pasta de inicialização do PostgreSQL. Eles rodam, na ordem abaixo, somente quando o volume está vazio.

| Ordem | Arquivo | Conteúdo |
|---:|---|---|
| 1 | `01_schema.sql` | tabelas e constraints da Etapa 1 |
| 2 | `02_seed.sql` | massa inicial |
| 3 | `05_etapa2_estrutura.sql` | migração de estrutura e novas garantias |
| 4 | `06_etapa2_procedures.sql` | duas procedures e uma function |
| 5 | `07_etapa2_triggers.sql` | triggers de integridade, auditoria e média |
| 6 | `08_etapa2_views.sql` | três views |
| 7 | `09_etapa2_seed.sql` | dados da Etapa 2 em uma transação |

`04_analiticas.sql` e `10_etapa2_verificacao.sql` são roteiros manuais. Eles não fazem parte da inicialização automática.

## Organização do código

```text
database.py             engine e fábricas de sessão
main.py                 aplicação FastAPI e registro dos routers
modelos.py              13 entidades SQLAlchemy
consultas.py            consultas do item 5 e medição lazy/eager
analiticas_db.py         quatro consultas analíticas da Etapa 1
concorrencia.py         três cenários com sessões independentes
demo_concorrencia.py    execução dos cenários pelo terminal
routers/                endpoints por recurso
schemas/                modelos de entrada e saída Pydantic
tests/                  SQL, ORM, HTTP, segurança e concorrência
documentacao/etapa2/    oito PDFs desta etapa
```

As tabelas continuam sendo definidas pelos scripts. `modelos.py` não chama `create_all()`. Objetos próprios do PostgreSQL, como views e rotinas armazenadas, são consultados pela mesma sessão usada pela ORM.

## API

A lista completa está em `/docs`. Os recursos principais são:

- `/pacientes/`
- `/preceptores/`
- `/residentes/`
- `/unidades/`
- `/procedimentos/`
- `/procedimentos-realizados/`
- `/atendimentos/`
- `/escalas/`
- `/internacoes/`

As listagens aceitam filtros por query string. Exemplos:

```http
GET /pacientes/?nome=ana&grupo_sanguineo=O%2B
GET /residentes/?especialidade=cardio&ano_residencia=R1
GET /atendimentos/?id_paciente=1&data=2026-07-02
GET /procedimentos-realizados/?id_atendimento=1&faturado=true
```

### Operações específicas

| Método e caminho | Resultado |
|---|---|
| `POST /atendimentos/completo` | cria o atendimento e seus procedimentos na mesma transação |
| `GET /atendimentos/tempo-medio-espera` | calcula a espera até o primeiro procedimento por unidade |
| `GET /atendimentos/estatisticas-mensais` | consulta a view de totais e procedimentos frequentes |
| `POST /escalas/reajustar` | move a escala de um residente com lock pessimista |
| `PUT /escalas/{id_escala}` | atualiza somente com a versão lida pelo cliente |
| `GET /pacientes/internados` | lista a internação mais recente que ainda não tem alta |
| `GET /residentes/sem-supervisor-doutor` | mostra escalas cujo preceptor não é doutor |
| `GET /auditoria/atendimentos` | consulta o histórico gerado pelo trigger |
| `GET /preceptores/supervisionados-flamenguistas` | executa a primeira consulta avançada |
| `GET /pacientes/ultimo-atendimento` | devolve o último atendimento de cada paciente |
| `GET /residentes/percentual-alto-risco` | calcula o percentual de procedimentos ALTO |
| `GET /consultas/lazy-vs-eager` | mede as duas estratégias de carregamento |
| `POST /concorrencia/simular` | executa os três cenários e devolve os logs |

As quatro analíticas da primeira etapa ficam em `/analiticas`: `ranking-residentes`, `preceptores-por-mes`, `plantoes-por-unidade` e `pacientes-sem-alto-risco`.

Para cadastrar um atendimento válido, use `POST /atendimentos/completo`. A transação insere o atendimento primeiro e os procedimentos em seguida. Os constraint triggers são diferidos e conferem a cardinalidade no `COMMIT`; um atendimento isolado é recusado.

## Integridade acrescentada na Etapa 2

`05_etapa2_estrutura.sql` mantém `01_schema.sql` intacto e adiciona:

- `Atendimento.id_unidade`, chave estrangeira opcional usada nos relatórios por unidade;
- `Procedimento_Realizado.data_hora_inicio`, usado no cálculo de espera;
- `Procedimento.media_tempo_procedimento` e os acumuladores de soma e quantidade;
- `Escala.versao`, usada pelo controle otimista;
- `Internacao`, com no máximo uma internação aberta por paciente;
- `Auditoria_Atendimento`, cujo histórico de remoção sobrevive ao atendimento;
- `Papel_Profissional`, que reserva o papel atual de preceptor ou residente;
- `uq_escala_residente_dia_turno`, que fecha conflitos entre unidades.

Titulações são armazenadas como `doutor`, `mestre` ou `especialista`. Entradas descritivas são normalizadas antes do CHECK. O horário do procedimento não pode anteceder o atendimento, nem o atendimento pode ser movido para depois de um procedimento já registrado.

Excluir o último procedimento de um atendimento é recusado no `COMMIT`. Excluir o próprio atendimento continua permitido e remove suas linhas dependentes pela chave estrangeira.

## Rotinas, triggers e views

As rotinas armazenadas são:

```text
sp_registrar_atendimento_completo  PROCEDURE  atendimento e itens em uma transação
sp_calcular_tempo_medio_espera     FUNCTION   uma linha de resultado por unidade
sp_reajustar_escala                PROCEDURE  mudança de dia e turno com FOR UPDATE
```

Os 13 triggers estão agrupados por finalidade: normalização de titulação, reserva e liberação de papel, sobreposição de escala, auditoria, cardinalidade atendimento-procedimento, validação temporal e manutenção da média. A média reage a INSERT, UPDATE e DELETE. Soma e quantidade são atualizadas por deltas sob um advisory lock transacional.

As views são:

```text
vw_pacientes_internados
vw_residentes_sem_supervisor
vw_estatisticas_atendimentos_mensal
```

## Concorrência

`concorrencia.py` executa duas sessões em paralelo em três situações:

1. sem lock explícito, deixando a UNIQUE decidir qual transação confirma;
2. com `SELECT ... FOR UPDATE` na linha do residente;
3. com a versão otimista de uma escala já existente.

O `PUT /escalas/{id_escala}` recebe `versao`. Uma versão desatualizada e um `StaleDataError` durante a gravação resultam em HTTP 409. `sp_reajustar_escala` também bloqueia a linha do residente antes de ler a origem, impedindo que duas chamadas anunciem a mesma mudança.

A simulação guarda os identificadores que criou e remove somente essas linhas no final. Ela nunca limpa por residente, dia ou turno.

Para executar pelo terminal:

```powershell
python demo_concorrencia.py
```

## Testes

Os testes usam um compose próprio, volume descartável e a porta `127.0.0.1:5434`. A guarda em `tests/conftest.py` recusa a porta 5432, hosts remotos e outro SGBD. Se o banco de teste não estiver disponível, a execução falha em vez de ignorar casos.

```powershell
docker compose -f docker-compose.test.yml up -d --wait
pytest -q
docker compose -f docker-compose.test.yml down -v
```

Resultado da última execução completa desta revisão:

```text
126 passed
```

A bateria inclui SQL, ORM, TestClient, resolução de rotas fixas, códigos 404/409/422, versão otimista, lazy/eager, integridade diferida, proteção da configuração e corridas com conexões independentes.

Para executar o roteiro SQL manual no PowerShell, com o banco de desenvolvimento no ar:

```powershell
Get-Content -Raw .\10_etapa2_verificacao.sql |
  docker compose exec -T db psql -U postgres -d hospital_universitario
```

As partes que alteram dados usam `BEGIN` e `ROLLBACK`.

## Documentação da Etapa 2

| Documento | Assunto |
|---|---|
| `etapa2_00_alteracoes_de_esquema.pdf` | colunas, tabelas, constraints e ordem de carga |
| `etapa2_01_stored_procedures.pdf` | duas procedures, uma function e suas transações |
| `etapa2_02_triggers.pdf` | os 13 triggers agrupados por regra |
| `etapa2_03_views.pdf` | critérios das três views e caminhos públicos |
| `etapa2_04_orm.pdf` | mapeamento, sessões, carregamento e contrato HTTP |
| `etapa2_05_consultas_avancadas.pdf` | sete consultas montadas pela DSL |
| `etapa2_06_concorrencia.pdf` | simulação e garantias concorrentes reais |
| `etapa2_07_relatorio_decisoes.pdf` | relatório geral da etapa, em duas páginas |

Os documentos da primeira etapa continuam em `documentacao/` e não foram alterados nesta revisão.

O frontend está no repositório [hglucena/frontend_projeto_bd](https://github.com/hglucena/frontend_projeto_bd).

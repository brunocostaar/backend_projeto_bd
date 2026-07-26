# Backend do Sistema de Gestão Hospitalar

API REST do projeto da disciplina de Banco de Dados (Hospital Universitário
Dra. Yuska Maritan Brito), com FastAPI e PostgreSQL.

O projeto tem duas etapas, e as duas continuam funcionando lado a lado:

- **Etapa 1** — rotas na raiz da API, todas as consultas em SQL puro. O
  SQLAlchemy entra apenas como gerenciador de conexões, sem ORM.
- **Etapa 2** — as mesmas operações reimplementadas com o ORM do SQLAlchemy,
  sob `/orm`, mais stored procedures, triggers, views e controle de
  concorrência, sob `/etapa2`.

Manter as duas permite comparar as implementações na mesma tela: o frontend tem
uma chave no cabeçalho que troca o prefixo das rotas de CRUD.

## Requisitos

- Docker (para o banco de dados)
- Python 3.11 ou superior

## Como executar

1. Suba o banco. Na primeira vez, o contêiner cria o banco
   `hospital_universitario` e executa os sete scripts na ordem:

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

### Scripts SQL

| Arquivo | Conteúdo | Roda no `docker compose up` |
|---|---|---|
| `01_schema.sql` | tabelas da Etapa 1, com PK, FK, CHECK, NOT NULL e UNIQUE | sim |
| `02_seed.sql` | massa de dados de teste da Etapa 1 | sim |
| `04_analiticas.sql` | as 4 consultas analíticas da Etapa 1 | não, só SELECT |
| `05_etapa2_estrutura.sql` | tabelas e colunas que a Etapa 2 exigiu | sim |
| `06_etapa2_procedures.sql` | 3 stored procedures | sim |
| `07_etapa2_triggers.sql` | 3 triggers (mais um de apoio) | sim |
| `08_etapa2_views.sql` | 3 views | sim |
| `09_etapa2_seed.sql` | dados de teste das funcionalidades novas | sim |
| `10_etapa2_verificacao.sql` | roteiro de verificação, com resultados esperados | não, só SELECT |

### Código

```
database.py            conexão com o banco, compartilhada pelas duas camadas
main.py                aplicação FastAPI e registro dos routers
demo_concorrencia.py   simulação de concorrência pela linha de comando
schemas/               validação de entrada e saída (Pydantic)
routers/               Etapa 1: endpoints em SQL puro
orm/
  modelos.py           entidades mapeadas
  sessao.py            sessão do ORM sobre o mesmo engine
  consultas.py         consultas avançadas do item 5
  analiticas.py        as 4 analíticas da Etapa 1, em DSL
  concorrencia.py      os três cenários de disputa por uma escala
routers_orm/           Etapa 2: mesmos endpoints com ORM, mais /etapa2
documentacao/etapa2/   um PDF por parte da Etapa 2
```

## Endpoints

A lista completa está em `/docs`. Resumo:

### Etapa 1 — SQL puro

- `/pacientes/`: CRUD completo
- `/preceptores/`: criar e listar
- `/residentes/`, `/unidades/`, `/procedimentos/`, `/atendimentos/`,
  `/escalas/`: CRUD completo
- `/procedimentos-realizados/`: CRUD pela chave composta (atendimento e
  procedimento)
- `/atendimentos/tempo-medio-por-residente`: AVG com GROUP BY

Todas as listagens aceitam filtros por query string, montados em SQL puro com
`WHERE` dinâmico (`ILIKE` nos campos de texto):

```
GET /pacientes/?nome=ana&grupo_sanguineo=O%2B
GET /residentes/?especialidade=cardio&ano_residencia=R1
GET /atendimentos/?id_paciente=1&data=2026-07-02
GET /procedimentos-realizados/?id_atendimento=1&faturado=true
```

### Etapa 2 — ORM, sob `/orm`

As mesmas operações acima, com a DSL do SQLAlchemy. Diferenças de contrato:

- `/orm/preceptores/` tem CRUD completo; a Etapa 1 só oferece criar e listar
- `/orm/atendimentos/` aceita `id_unidade`
- `/orm/procedimentos-realizados/` aceita `data_hora_inicio`
- `/orm/escalas/` devolve `versao` e usa controle de concorrência otimista
- `/orm/internacoes/`: entidade nova, com registro de alta em
  `POST /orm/internacoes/{id}/alta`
- `/orm/analiticas/`: as 4 consultas analíticas da Etapa 1, que antes só
  rodavam pelo psql

### Etapa 2 — funcionalidades novas, sob `/etapa2`

| Endpoint | O que faz |
|---|---|
| `GET /etapa2/views/pacientes-internados` | quem está internado agora |
| `GET /etapa2/views/residentes-sem-supervisor` | plantões cujo preceptor não é doutor |
| `GET /etapa2/views/estatisticas-mensais` | total, média e procedimentos frequentes por mês e unidade |
| `GET /etapa2/procedures/tempo-medio-espera` | espera até o primeiro procedimento, por unidade |
| `POST /etapa2/procedures/registrar-atendimento-completo` | atendimento e procedimentos numa transação |
| `POST /etapa2/procedures/reajustar-escala` | move plantões de dia/turno, tudo ou nada |
| `GET /etapa2/auditoria` | histórico gravado pelo trigger de atendimento |
| `GET /etapa2/consultas/preceptores-flamenguistas` | preceptores de pacientes com `is_flamengo` |
| `GET /etapa2/consultas/ultimo-atendimento-por-paciente` | último atendimento de cada paciente |
| `GET /etapa2/consultas/percentual-alto-risco` | proporção de procedimentos ALTO por residente |
| `GET /etapa2/consultas/lazy-vs-eager` | mede o custo do carregamento sob demanda |
| `POST /etapa2/concorrencia/simular` | roda os três cenários de disputa e devolve os logs |

## O que a Etapa 2 acrescentou ao banco

Três requisitos pediam informação que o esquema da Etapa 1 não guardava:

- `internacao`, tabela nova, base da `vw_pacientes_internados`
- `atendimento.id_unidade`, sem a qual não há como agrupar por unidade
- `procedimento_realizado.data_hora_inicio`, para medir o tempo de espera

Mais `auditoria_atendimento` (destino do trigger),
`procedimento.media_tempo_procedimento` (mantida por trigger) e `escala.versao`
(controle otimista). Tudo em `05_etapa2_estrutura.sql`; o `01_schema.sql` não
foi tocado, então a Etapa 1 continua reproduzível como foi entregue.

`atendimento.id_unidade` aceita nulo porque os endpoints da Etapa 1 inserem
atendimento sem informar unidade. Um atendimento criado por aquelas rotas não
aparece nas estatísticas mensais.

## Stored procedures, triggers e views

```
sp_registrar_atendimento_completo   atendimento + procedimentos (JSON) numa transação
sp_calcular_tempo_medio_espera      chegada do paciente até o primeiro procedimento
sp_reajustar_escala                 move plantões de um dia/turno para outro

trg_check_sobreposicao_escala       um residente não cobre duas unidades no mesmo turno
trg_audita_atendimento              grava antes e depois em JSONB a cada alteração
trg_atualiza_media_procedimentos    mantém procedimento.media_tempo_procedimento

vw_pacientes_internados             internação mais recente sem data de saída
vw_residentes_sem_supervisor        plantão cujo preceptor não tem titulação de doutor
vw_estatisticas_atendimentos_mensal agregação por mês e unidade
```

Duas observações. `sp_calcular_tempo_medio_espera` é FUNCTION, e não PROCEDURE,
porque devolve um conjunto de linhas e precisa aparecer no `FROM` de um SELECT.
E há um quarto trigger, `trg_atualiza_media_procedimentos_ud`: o enunciado pede
o cálculo da média em `AFTER INSERT`, o que deixaria o valor velho quando
alguém corrigisse ou apagasse um registro, então o par cobre `UPDATE` e
`DELETE`.

## Concorrência

`orm/concorrencia.py` simula duas transações disputando a mesma escala, em três
estratégias: apenas as restrições do banco, bloqueio pessimista com
`SELECT ... FOR UPDATE`, e bloqueio otimista pela coluna `versao`. Pela linha de
comando:

```
python demo_concorrencia.py
```

A mesma simulação está em `POST /etapa2/concorrencia/simular` e na aba
Concorrência do frontend. O que a simulação cria é apagado no fim.

## Consultas analíticas da Etapa 1

`04_analiticas.sql` tem as quatro consultas em SQL. Execute com o banco já
populado:

```
docker compose exec -T db psql -U postgres -d hospital_universitario < 04_analiticas.sql
```

1. **Ranking de residentes** por número de atendimentos (`LEFT JOIN` para que
   residente sem atendimento apareça com total 0).
2. **Preceptores com mais de 5 atendimentos** em um mês (`GROUP BY` +
   `HAVING`). No seed, Fernando Alves tem 6 atendimentos em julho de 2026.
3. **Plantões por residente em cada unidade.** A tabela `escala` é uma grade
   semanal, sem data concreta, então "mês corrente" admite duas leituras e o
   arquivo traz as duas.
4. **Pacientes que nunca realizaram procedimento de risco ALTO** (`NOT EXISTS`,
   que ao contrário de `NOT IN` não quebra com `NULL`).

As quatro foram reimplementadas com a DSL do ORM em `orm/analiticas.py` e
expostas em `/orm/analiticas/`.

## Verificação

`10_etapa2_verificacao.sql` percorre cada funcionalidade da Etapa 2 com os
resultados esperados em comentário. As partes que gravam ficam entre `BEGIN` e
`ROLLBACK`, então pode ser executado quantas vezes for preciso:

```
docker compose exec -T db psql -U postgres -d hospital_universitario < 10_etapa2_verificacao.sql
```

Alguns valores que ele confere, com o banco recém-criado:

| Verificação | Esperado |
|---|---|
| Pacientes internados | 3: Carla Mendes, Ana Souza, Elisa Rocha |
| Residentes sem supervisor doutor | 4 plantões |
| Estatísticas mensais | 6 linhas; UTI em julho com 5 atendimentos e média 52,0 |
| Tempo médio de espera | Enfermaria A 33,8 min; UTI Adulto 5,8 min |
| Auditoria após o seed | 15 linhas: 10 UPDATE e 5 INSERT |
| Percentual de alto risco | Mariana Teles 40%; Nathan Ribeiro 0% |
| Preceptores de flamenguistas | 4 dos 5 |

## Documentação

`documentacao/etapa2/` tem um PDF por parte da Etapa 2:

| Documento | Assunto |
|---|---|
| `etapa2_00_alteracoes_de_esquema` | o que mudou no banco e por quê |
| `etapa2_01_stored_procedures` | as três rotinas, PROCEDURE contra FUNCTION |
| `etapa2_02_triggers` | os três triggers e o que a UNIQUE não cobria |
| `etapa2_03_views` | as três views e os critérios adotados |
| `etapa2_04_orm` | mapeamento, sessão, carregamento adiantado |
| `etapa2_05_consultas_avancadas` | as sete consultas em DSL |
| `etapa2_06_concorrencia` | os três cenários e a comparação entre as estratégias |
| `etapa2_07_relatorio_decisoes` | trigger contra procedure, escolha da ORM |

`documentacao/` guarda os documentos da Etapa 1: modelo conceitual, modelo
relacional, normalização e a documentação técnica geral.

## Observações

As alergias do paciente são gravadas na tabela `alergia`, uma linha por
alergia, conforme a normalização documentada no projeto. A API recebe e devolve
o campo `alergias` como texto separado por vírgulas. A versão em ORM ordena as
alergias alfabeticamente; a da Etapa 1 usa `string_agg` sem `ORDER BY`, e a
ordem depende de como o banco leu as linhas.

O frontend fica em um repositório separado:
https://github.com/hglucena/frontend_projeto_bd

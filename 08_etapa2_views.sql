-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 2 - Views
--
-- Executar depois do 07_etapa2_triggers.sql:
--   psql -U postgres -f 08_etapa2_views.sql
--
-- DROP antes de CREATE em vez de CREATE OR REPLACE VIEW: o REPLACE só aceita
-- manter a mesma lista de colunas, com os mesmos nomes e tipos, então falharia
-- em qualquer ajuste na consulta.

\c hospital_universitario


-- ============================================================
-- vw_pacientes_internados
--
-- Pacientes internados agora. O critério do enunciado é data_hora_saida nula
-- na internação mais recente, o que não é o mesmo que "existe internação sem
-- saída": um paciente com uma internação antiga mal encerrada continuaria
-- aparecendo como internado para sempre.
--
-- DISTINCT ON (id_paciente) é específico do PostgreSQL: com o ORDER BY abaixo,
-- devolve uma linha por paciente, a de entrada mais recente. O desempate por
-- id_internacao cobre duas entradas no mesmo instante.
-- ============================================================

DROP VIEW IF EXISTS vw_pacientes_internados;

CREATE VIEW vw_pacientes_internados AS
WITH ultima_internacao AS (
    SELECT DISTINCT ON (i.id_paciente)
           i.id_internacao,
           i.id_paciente,
           i.id_unidade,
           i.data_hora_entrada,
           i.data_hora_saida,
           i.motivo
      FROM Internacao i
     ORDER BY i.id_paciente, i.data_hora_entrada DESC, i.id_internacao DESC
)
SELECT ui.id_internacao,
       pe.id_pessoa       AS id_paciente,
       pe.nome,
       pe.CPF             AS cpf,
       pa.numero_convenio,
       pa.grupo_sanguineo,
       u.id_unidade,
       u.nome             AS unidade,
       ui.data_hora_entrada,
       ui.motivo,
       (CURRENT_TIMESTAMP - ui.data_hora_entrada) AS tempo_internado
  FROM ultima_internacao ui
  JOIN Paciente pa ON pa.id_pessoa = ui.id_paciente
  JOIN Pessoa   pe ON pe.id_pessoa = pa.id_pessoa
  JOIN Unidade  u  ON u.id_unidade = ui.id_unidade
 WHERE ui.data_hora_saida IS NULL
 ORDER BY ui.data_hora_entrada;


-- ============================================================
-- vw_residentes_sem_supervisor
--
-- Residentes escalados cujo preceptor do plantão não é doutor. O enunciado
-- também menciona quem não tem supervisão ativa; na prática o esquema não
-- permite escala sem preceptor, porque escala.id_preceptor é NOT NULL com
-- chave estrangeira. O LEFT JOIN e o teste de nulo ficam para o caso de a
-- coluna se tornar opcional, e documentam que a situação foi considerada.
--
-- A comparação usa lower() porque titulacao é texto livre: o seed grava
-- "doutor", mas nada impede "Doutor" vindo da API.
-- ============================================================

DROP VIEW IF EXISTS vw_residentes_sem_supervisor;

CREATE VIEW vw_residentes_sem_supervisor AS
SELECT e.id_escala,
       pe_res.id_pessoa   AS id_residente,
       pe_res.nome        AS residente,
       r.ano_residencia,
       u.nome             AS unidade,
       e.dia_semana,
       e.turno,
       pe_pre.id_pessoa   AS id_preceptor,
       pe_pre.nome        AS preceptor,
       pre.titulacao,
       CASE WHEN pre.id_profissional IS NULL THEN 'sem preceptor vinculado'
            ELSE 'preceptor sem titulação de doutor'
       END                AS motivo
  FROM Escala e
  JOIN Residente r      ON r.id_profissional = e.id_residente
  JOIN Pessoa    pe_res ON pe_res.id_pessoa  = r.id_profissional
  JOIN Unidade   u      ON u.id_unidade      = e.id_unidade
  LEFT JOIN Preceptor pre    ON pre.id_profissional = e.id_preceptor
  LEFT JOIN Pessoa    pe_pre ON pe_pre.id_pessoa    = e.id_preceptor
 WHERE pre.id_profissional IS NULL
    OR lower(pre.titulacao) <> 'doutor'
 ORDER BY pe_res.nome, e.dia_semana, e.turno;


-- ============================================================
-- vw_estatisticas_atendimentos_mensal
--
-- Por mês e unidade: quantos atendimentos, duração média e os procedimentos
-- mais frequentes.
--
-- "Procedimentos mais comuns" não cabe numa coluna agregada simples, porque é
-- um ranking dentro de cada grupo. A CTE contagem numera os procedimentos de
-- cada mês/unidade com ROW_NUMBER() e a subconsulta final junta os três
-- primeiros num texto. Vale notar que a função de janela é avaliada depois do
-- GROUP BY, o que permite ordenar por COUNT(*) dentro do OVER.
--
-- total_atendimentos vem da CTE base, não do JOIN com procedimento_realizado:
-- um atendimento sem procedimento registrado ainda conta no total, e nesse
-- caso procedimentos_mais_comuns fica nulo.
--
-- Atendimentos sem unidade (os criados pelos endpoints da Etapa 1, que não
-- informam o campo) ficam de fora.
-- ============================================================

DROP VIEW IF EXISTS vw_estatisticas_atendimentos_mensal;

CREATE VIEW vw_estatisticas_atendimentos_mensal AS
WITH base AS (
    SELECT DATE_TRUNC('month', a.data_hora)::DATE AS mes,
           a.id_unidade,
           a.id_atendimento,
           a.duracao_minutos
      FROM Atendimento a
     WHERE a.id_unidade IS NOT NULL
),
totais AS (
    SELECT b.mes,
           b.id_unidade,
           COUNT(*)                             AS total_atendimentos,
           ROUND(AVG(b.duracao_minutos), 1)     AS media_duracao_minutos,
           MIN(b.duracao_minutos)               AS menor_duracao,
           MAX(b.duracao_minutos)               AS maior_duracao
      FROM base b
     GROUP BY b.mes, b.id_unidade
),
contagem AS (
    SELECT b.mes,
           b.id_unidade,
           pc.nome,
           COUNT(*) AS vezes,
           ROW_NUMBER() OVER (PARTITION BY b.mes, b.id_unidade
                              ORDER BY COUNT(*) DESC, pc.nome) AS posicao
      FROM base b
      JOIN Procedimento_Realizado pr ON pr.id_atendimento  = b.id_atendimento
      JOIN Procedimento           pc ON pc.id_procedimento = pr.id_procedimento
     GROUP BY b.mes, b.id_unidade, pc.nome
)
SELECT t.mes,
       u.id_unidade,
       u.nome AS unidade,
       t.total_atendimentos,
       t.media_duracao_minutos,
       t.menor_duracao,
       t.maior_duracao,
       (SELECT string_agg(c.nome || ' (' || c.vezes || ')', ', ' ORDER BY c.posicao)
          FROM contagem c
         WHERE c.mes = t.mes
           AND c.id_unidade = t.id_unidade
           AND c.posicao <= 3) AS procedimentos_mais_comuns
  FROM totais t
  JOIN Unidade u ON u.id_unidade = t.id_unidade
 ORDER BY t.mes DESC, u.nome;

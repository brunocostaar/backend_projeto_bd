-- ============================================================
-- 04_analiticas.sql
-- Etapa 1 — Consultas analíticas (P4)
-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Requer: 01_schema.sql e 02_seed.sql já executados
-- ============================================================


-- ------------------------------------------------------------
-- Q1. Ranking dos residentes por número de atendimentos
--     (nome e total, do mais ativo para o menos ativo)
--     LEFT JOIN proposital: residente sem atendimento aparece
--     com total 0 e ainda entra no ranking.
-- ------------------------------------------------------------
SELECT
    pe.nome,
    COUNT(a.id_atendimento) AS total_atendimentos
FROM residente r
JOIN pessoa pe        ON pe.id_pessoa = r.id_profissional
LEFT JOIN atendimento a ON a.id_residente = r.id_profissional
GROUP BY pe.id_pessoa, pe.nome
ORDER BY total_atendimentos DESC, pe.nome;


-- ------------------------------------------------------------
-- Q2. Preceptores que supervisionaram mais de 5 atendimentos
--     em um determinado mês.
--     Troque a data abaixo pelo mês desejado (dia 01).
--     No seed, o preceptor Fernando Alves tem 6 atendimentos
--     em julho/2026 — é o caso que a consulta deve capturar.
--     HAVING filtra DEPOIS da agregação (WHERE filtra antes).
-- ------------------------------------------------------------
SELECT
    pe.nome,
    COUNT(*) AS total_supervisionados
FROM atendimento a
JOIN pessoa pe ON pe.id_pessoa = a.id_preceptor
WHERE DATE_TRUNC('month', a.data_hora) = DATE '2026-07-01'
GROUP BY pe.id_pessoa, pe.nome
HAVING COUNT(*) > 5
ORDER BY total_supervisionados DESC;


-- ------------------------------------------------------------
-- Q3. Para cada unidade, quantidade de plantões escalados
--     por residente no mês corrente.
--
--     OBS (decisão de projeto — documentar no README):
--     ESCALA é uma grade SEMANAL (dia_semana + turno), sem
--     data concreta. Interpretação adotada: contar os slots
--     semanais de cada residente por unidade (versão A).
--     A versão B projeta a grade no mês corrente de verdade,
--     multiplicando cada escala pelo nº de ocorrências daquele
--     dia da semana no mês atual.
-- ------------------------------------------------------------

-- Versão A — slots semanais por residente e unidade
SELECT
    u.nome  AS unidade,
    pe.nome AS residente,
    COUNT(*) AS plantoes_semanais
FROM escala e
JOIN unidade u ON u.id_unidade = e.id_unidade
JOIN pessoa pe ON pe.id_pessoa = e.id_residente
GROUP BY u.id_unidade, u.nome, pe.id_pessoa, pe.nome
ORDER BY u.nome, plantoes_semanais DESC, pe.nome;

-- Versão B — ocorrências reais no mês corrente
-- (gera todos os dias do mês atual e casa o dia da semana de
--  cada data com o dia_semana da escala)
-- Os valores do CASE seguem a constraint chk_dia_semana do
-- schema: 'segunda', 'terca', ..., 'domingo'.
SELECT
    u.nome  AS unidade,
    pe.nome AS residente,
    COUNT(*) AS plantoes_no_mes
FROM escala e
JOIN unidade u ON u.id_unidade = e.id_unidade
JOIN pessoa pe ON pe.id_pessoa = e.id_residente
JOIN generate_series(
         DATE_TRUNC('month', CURRENT_DATE),
         (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month - 1 day'),
         INTERVAL '1 day'
     ) AS d(dia)
  ON e.dia_semana = CASE EXTRACT(DOW FROM d.dia)
                        WHEN 0 THEN 'domingo'
                        WHEN 1 THEN 'segunda'
                        WHEN 2 THEN 'terca'
                        WHEN 3 THEN 'quarta'
                        WHEN 4 THEN 'quinta'
                        WHEN 5 THEN 'sexta'
                        WHEN 6 THEN 'sabado'
                    END
GROUP BY u.id_unidade, u.nome, pe.id_pessoa, pe.nome
ORDER BY u.nome, plantoes_no_mes DESC, pe.nome;


-- ------------------------------------------------------------
-- Q4. Pacientes que NUNCA realizaram procedimento de nível
--     de risco 'ALTO'.
--     NOT EXISTS é a forma segura de expressar "nunca"
--     (NOT IN quebra silenciosamente na presença de NULL).
-- ------------------------------------------------------------
SELECT
    pe.nome
FROM paciente pa
JOIN pessoa pe ON pe.id_pessoa = pa.id_pessoa
WHERE NOT EXISTS (
    SELECT 1
    FROM atendimento a
    JOIN procedimento_realizado pr ON pr.id_atendimento  = a.id_atendimento
    JOIN procedimento pc           ON pc.id_procedimento = pr.id_procedimento
    WHERE a.id_paciente  = pa.id_pessoa
      AND pc.nivel_risco = 'ALTO'
)
ORDER BY pe.nome;

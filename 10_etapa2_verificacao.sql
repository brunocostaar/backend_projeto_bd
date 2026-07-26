-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 2 - Roteiro de verificação
--
-- Não altera estrutura nem dados de forma permanente: as partes que gravam
-- ficam dentro de blocos com ROLLBACK. Por isso não entra na lista do
-- docker-compose.yml e é executado à mão, com o banco já povoado:
--
--   docker compose exec -T db psql -U postgres -d hospital_universitario < 10_etapa2_verificacao.sql
--
-- Os resultados esperados abaixo valem para o banco recém-criado, com
-- 01, 02, 05, 06, 07, 08 e 09 aplicados nessa ordem e nada mais. Se a API já
-- tiver gravado dados, os números mudam.

\c hospital_universitario


-- ============================================================
-- 1. Estrutura nova (05)
-- ============================================================

-- Esperado: as quatro colunas acrescentadas, mais internacao e
-- auditoria_atendimento na lista de tabelas.
SELECT table_name, column_name, data_type
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND (table_name, column_name) IN (
        ('atendimento', 'id_unidade'),
        ('procedimento', 'media_tempo_procedimento'),
        ('procedimento_realizado', 'data_hora_inicio'),
        ('escala', 'versao'))
 ORDER BY table_name;

SELECT table_name
  FROM information_schema.tables
 WHERE table_schema = 'public'
   AND table_name IN ('internacao', 'auditoria_atendimento')
 ORDER BY table_name;


-- ============================================================
-- 2. Views (08)
-- ============================================================

-- Esperado: 3 linhas. Carla Mendes na UTI Adulto (entrada 22/07), Ana Souza no
-- Pronto-Socorro (24/07) e Elisa Rocha na Enfermaria A (25/07).
-- Bruno Lima e Diego Ferreira ficam fora: a internação mais recente dos dois
-- já tem alta. Ana aparece apesar de ter uma internação antiga encerrada, o que
-- mostra que a view olha só a mais recente.
SELECT nome, unidade, data_hora_entrada, motivo FROM vw_pacientes_internados;

-- Esperado: 4 linhas. Karina Duarte (terca/tarde), Nathan Ribeiro
-- (sexta/manha) e Olivia Prado duas vezes (sabado/tarde e sexta/tarde).
-- São os plantões cujo preceptor é mestre ou especialista.
SELECT residente, unidade, dia_semana, turno, preceptor, titulacao
  FROM vw_residentes_sem_supervisor;

-- Esperado: 6 linhas. Julho de 2026 com as quatro unidades e junho de 2026 com
-- duas. Conferir a UTI Adulto em julho: 5 atendimentos, média 52.0 minutos e
-- "Coleta de sangue (2), Intubacao orotraqueal (2), Puncao lombar (2)".
SELECT mes, unidade, total_atendimentos, media_duracao_minutos,
       procedimentos_mais_comuns
  FROM vw_estatisticas_atendimentos_mensal;


-- ============================================================
-- 3. sp_calcular_tempo_medio_espera (06)
-- ============================================================

-- Esperado: 4 linhas, da maior espera para a menor.
--   Enfermaria A     4 atendimentos   33.8 min
--   Ambulatorio      2                19.0
--   Pronto-Socorro   4                10.3
--   UTI Adulto       5                 5.8
SELECT * FROM sp_calcular_tempo_medio_espera();


-- ============================================================
-- 4. trg_atualiza_media_procedimentos (07)
-- ============================================================

-- Esperado: a coluna preenchida em 9 dos 10 procedimentos. Lavagem gastrica
-- fica nula porque nunca foi realizada. Coleta de sangue 10.60,
-- Aplicacao de medicacao 21.67, Intubacao orotraqueal 29.00, Puncao lombar
-- 49.00, Acesso venoso central 34.00.
SELECT codigo, nome, media_tempo_procedimento
  FROM Procedimento
 ORDER BY codigo;

-- O trigger reage a INSERT, e o par trg_atualiza_media_procedimentos_ud cobre
-- correção e remoção. Aqui a média de Coleta de sangue (10.60) muda ao corrigir
-- um tempo, e o ROLLBACK devolve tudo ao estado anterior.
BEGIN;
    UPDATE Procedimento_Realizado
       SET tempo_real_minutos = 60
     WHERE id_procedimento = (SELECT id_procedimento FROM Procedimento WHERE codigo = 102)
       AND id_atendimento   = (SELECT id_atendimento FROM Atendimento
                                WHERE data_hora = TIMESTAMP '2026-06-15 08:30');

    -- Esperado: 20.20, ou seja (60+9+11+10+11)/5.
    SELECT nome, media_tempo_procedimento FROM Procedimento WHERE codigo = 102;
ROLLBACK;


-- ============================================================
-- 5. trg_audita_atendimento (07)
-- ============================================================

-- Esperado: 15 linhas no total, sendo 10 UPDATE (o preenchimento da unidade
-- feito pelo 09) e 5 INSERT (os atendimentos novos).
SELECT operacao, COUNT(*) FROM Auditoria_Atendimento GROUP BY operacao ORDER BY operacao;

-- Um ciclo completo de auditoria. Esperado: três linhas novas, INSERT, UPDATE e
-- DELETE, e a linha de DELETE sobrevive ao atendimento porque a coluna
-- id_atendimento da auditoria não tem chave estrangeira.
BEGIN;
    INSERT INTO Atendimento
        (data_hora, duracao_minutos, id_preceptor, id_paciente, id_residente, id_unidade)
    VALUES ('2026-07-26 09:00', 20, 6, 1, 11, 1);

    UPDATE Atendimento SET duracao_minutos = 45
     WHERE data_hora = TIMESTAMP '2026-07-26 09:00';

    DELETE FROM Atendimento WHERE data_hora = TIMESTAMP '2026-07-26 09:00';

    SELECT operacao, usuario,
           dados_antigos->>'duracao_minutos' AS antes,
           dados_novos->>'duracao_minutos'   AS depois
      FROM Auditoria_Atendimento
     ORDER BY id_auditoria DESC
     LIMIT 3;
ROLLBACK;


-- ============================================================
-- 6. trg_check_sobreposicao_escala (07)
-- ============================================================

-- O residente 11 já tem plantão na segunda pela manhã na Enfermaria A. Repetir
-- o dia e o turno em outra unidade passa pela UNIQUE do esquema, porque a
-- unidade é diferente, e é justamente o que o trigger recusa.
--
-- Esperado: ERROR - Residente 11 já está escalado em segunda manha na unidade
-- "Enfermaria A".
BEGIN;
    INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade)
    VALUES ('segunda', 'manha', 7, 11, 3);
ROLLBACK;

-- Mesmo dia e turno, residente diferente: aceito. Esperado: uma linha inserida.
BEGIN;
    INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade)
    VALUES ('segunda', 'manha', 7, 13, 3);
    SELECT COUNT(*) AS escalas_apos_insercao FROM Escala;
ROLLBACK;


-- ============================================================
-- 7. sp_reajustar_escala (06)
-- ============================================================

-- Caso que funciona. O residente 14 só tem o plantão de sexta pela manhã.
-- Esperado: p_escalas_movidas = 1 e versao passando de 1 para 2.
BEGIN;
    CALL sp_reajustar_escala(14, 'sexta', 'manha', 'quinta', 'manha', NULL);
    SELECT id_escala, dia_semana, turno, versao
      FROM Escala WHERE id_residente = 14;
ROLLBACK;

-- Caso recusado. O residente 12 tem plantão na quinta pela manhã e outro na
-- segunda pela manhã; mover o primeiro para a segunda deixaria dois no mesmo
-- turno. Esperado: ERROR - Residente 12 já tem plantão em segunda manha.
BEGIN;
    CALL sp_reajustar_escala(12, 'quinta', 'manha', 'segunda', 'manha', NULL);
ROLLBACK;

-- Origem sem nenhum plantão. Esperado: NOTICE avisando que não há o que fazer,
-- e p_escalas_movidas = 0, sem erro.
BEGIN;
    CALL sp_reajustar_escala(11, 'quarta', 'noite', 'quinta', 'noite', NULL);
ROLLBACK;


-- ============================================================
-- 8. sp_registrar_atendimento_completo (06)
-- ============================================================

-- Caminho normal: um atendimento com dois procedimentos, numa transação só.
-- Esperado: o CALL devolve o id gerado e a consulta mostra 2 procedimentos.
BEGIN;
    CALL sp_registrar_atendimento_completo(
        '2026-07-26 10:30', 50, 3, 13, 8, 2,
        '[{"id_procedimento": 5, "tempo_real_minutos": 26, "data_hora_inicio": "2026-07-26T10:36",
           "observacao": "sem intercorrencias"},
          {"id_procedimento": 2, "quantidade": 2, "tempo_real_minutos": 9}]'::jsonb,
        NULL);

    SELECT a.id_atendimento, COUNT(pr.id_procedimento) AS procedimentos
      FROM Atendimento a
      JOIN Procedimento_Realizado pr ON pr.id_atendimento = a.id_atendimento
     WHERE a.data_hora = TIMESTAMP '2026-07-26 10:30'
     GROUP BY a.id_atendimento;
ROLLBACK;

-- Reversão. O segundo procedimento não existe, então o atendimento inteiro é
-- desfeito. Esperado: ERROR - Procedimento 999 não existe, e a contagem
-- depois do ROLLBACK igual à de antes.
SELECT COUNT(*) AS atendimentos_antes FROM Atendimento;

BEGIN;
    CALL sp_registrar_atendimento_completo(
        '2026-07-26 11:00', 30, 1, 11, 6, 1,
        '[{"id_procedimento": 2, "tempo_real_minutos": 10},
          {"id_procedimento": 999, "tempo_real_minutos": 10}]'::jsonb,
        NULL);
ROLLBACK;

SELECT COUNT(*) AS atendimentos_depois FROM Atendimento;

-- Lista vazia. O DER exige pelo menos um procedimento por atendimento, e essa
-- cardinalidade não cabe em constraint. Esperado: ERROR - Um atendimento
-- precisa de pelo menos um procedimento.
BEGIN;
    CALL sp_registrar_atendimento_completo(
        '2026-07-26 12:00', 30, 1, 11, 6, 1, '[]'::jsonb, NULL);
ROLLBACK;


-- ============================================================
-- 9. Consultas avançadas em SQL, para comparar com a versão ORM
--
-- As três consultas do item 5 da Etapa 2 são implementadas com a DSL do
-- SQLAlchemy em orm/consultas.py. As versões abaixo servem de gabarito: o
-- resultado das duas tem que ser igual.
-- ============================================================

-- Preceptores que supervisionaram residentes no atendimento de pacientes
-- flamenguistas. Esperado: 4 nomes, Fernando Alves, Gabriela Pinto,
-- Henrique Costa e Isabela Martins. Joao Nogueira fica fora.
SELECT DISTINCT pe.nome AS preceptor
  FROM Atendimento a
  JOIN Preceptor pre ON pre.id_profissional = a.id_preceptor
  JOIN Pessoa    pe  ON pe.id_pessoa        = pre.id_profissional
  JOIN Residente r   ON r.id_profissional   = a.id_residente
  JOIN Paciente  pa  ON pa.id_pessoa        = a.id_paciente
  JOIN Pessoa    pep ON pep.id_pessoa       = pa.id_pessoa
 WHERE pep.is_flamengo
 ORDER BY 1;

-- Percentual de procedimentos de risco ALTO por residente. Esperado:
--   Mariana Teles   5 procedimentos, 2 de alto risco, 40.00%
--   Karina Duarte   6, 2, 33.33%
--   Lucas Barbosa   3, 1, 33.33%
--   Olivia Prado    3, 1, 33.33%
--   Nathan Ribeiro  3, 0,  0.00%
-- A conta é por linha de procedimento_realizado, não pela coluna quantidade.
SELECT pe.nome AS residente,
       COUNT(*) AS total_procedimentos,
       COUNT(*) FILTER (WHERE pc.nivel_risco = 'ALTO') AS alto_risco,
       ROUND(100.0 * COUNT(*) FILTER (WHERE pc.nivel_risco = 'ALTO') / COUNT(*), 2) AS percentual
  FROM Atendimento a
  JOIN Residente r  ON r.id_profissional  = a.id_residente
  JOIN Pessoa    pe ON pe.id_pessoa       = r.id_profissional
  JOIN Procedimento_Realizado pr ON pr.id_atendimento  = a.id_atendimento
  JOIN Procedimento           pc ON pc.id_procedimento = pr.id_procedimento
 GROUP BY pe.id_pessoa, pe.nome
 ORDER BY percentual DESC, pe.nome;

-- Último atendimento de cada paciente. Esperado: 5 linhas, uma por paciente,
-- todas da segunda metade de julho de 2026. Ana Souza em 20/07 com Karina
-- Duarte e Gabriela Pinto, Elisa Rocha em 24/07 com Olivia Prado.
SELECT ult.paciente, ult.data_hora, ult.residente, ult.preceptor,
       (SELECT string_agg(pc.nome, ', ' ORDER BY pc.nome)
          FROM Procedimento_Realizado pr
          JOIN Procedimento pc ON pc.id_procedimento = pr.id_procedimento
         WHERE pr.id_atendimento = ult.id_atendimento) AS procedimentos
  FROM (SELECT DISTINCT ON (a.id_paciente)
               a.id_atendimento,
               pep.nome AS paciente,
               a.data_hora,
               per.nome AS residente,
               pec.nome AS preceptor
          FROM Atendimento a
          JOIN Pessoa pep ON pep.id_pessoa = a.id_paciente
          JOIN Pessoa per ON per.id_pessoa = a.id_residente
          JOIN Pessoa pec ON pec.id_pessoa = a.id_preceptor
         ORDER BY a.id_paciente, a.data_hora DESC, a.id_atendimento DESC) ult
 ORDER BY ult.data_hora DESC;

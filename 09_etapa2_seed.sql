-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 2 - Dados de teste das funcionalidades novas
--
-- Executar depois do 08_etapa2_views.sql:
--   psql -U postgres -f 09_etapa2_seed.sql
-- (via docker compose, roda automaticamente na primeira subida)
--
-- Depende do 02_seed.sql. Como lá os ids saem em sequência num banco vazio,
-- este script usa os mesmos números: pessoas 1-5 pacientes, 6-10 preceptores,
-- 11-15 residentes, unidades 1-4, procedimentos 1-10.
--
-- Por que um arquivo novo em vez de mexer no 02_seed.sql: as colunas que estes
-- dados preenchem só existem depois do 05_etapa2_estrutura.sql. Editar o seed
-- da Etapa 1 quebraria a execução isolada daquela etapa.
--
-- O preceptor 6 (Fernando Alves) continua com exatamente 6 atendimentos em
-- julho de 2026. É o caso que a consulta Q2 da Etapa 1 ("preceptores com mais
-- de 5 atendimentos no mês") captura, e nenhum atendimento novo abaixo usa
-- esse preceptor para não estragar essa evidência.
--
-- Este script dispara os triggers da Etapa 2: o UPDATE de unidade gera dez
-- linhas em auditoria_atendimento, os atendimentos novos geram outras cinco, e
-- cada procedimento inserido recalcula media_tempo_procedimento.

\c hospital_universitario


-- ============================================================
-- 1. Unidade dos atendimentos da Etapa 1
--
-- A coluna nasceu vazia. As views e o cálculo de espera agrupam por unidade,
-- então sem isto os dez atendimentos originais ficariam fora de todo relatório.
-- O casamento é por data_hora, que é distinta em cada um dos dez.
-- ============================================================

UPDATE Atendimento a
   SET id_unidade = u.id_unidade
  FROM (VALUES
        (TIMESTAMP '2026-06-15 08:30', 'Pronto-Socorro'),
        (TIMESTAMP '2026-06-20 14:00', 'Enfermaria A'),
        (TIMESTAMP '2026-07-01 09:00', 'UTI Adulto'),
        (TIMESTAMP '2026-07-02 10:15', 'Ambulatorio'),
        (TIMESTAMP '2026-07-03 11:30', 'Pronto-Socorro'),
        (TIMESTAMP '2026-07-05 16:45', 'UTI Adulto'),
        (TIMESTAMP '2026-07-06 08:00', 'Enfermaria A'),
        (TIMESTAMP '2026-07-07 19:20', 'UTI Adulto'),
        (TIMESTAMP '2026-07-08 13:10', 'Pronto-Socorro'),
        (TIMESTAMP '2026-07-09 07:50', 'Enfermaria A')
       ) AS m(data_hora, unidade)
  JOIN Unidade u ON u.nome = m.unidade
 WHERE a.data_hora = m.data_hora
   AND a.id_unidade IS NULL;


-- ============================================================
-- 2. Hora de início dos procedimentos da Etapa 1
--
-- sp_calcular_tempo_medio_espera mede o intervalo entre a chegada do paciente
-- e o começo do primeiro procedimento. Os minutos abaixo foram escolhidos para
-- que as unidades tenham esperas visivelmente diferentes: a UTI atende quase
-- na hora, a Enfermaria demora mais.
--
-- O casamento usa o código do procedimento em vez do id, porque o código é o
-- identificador de negócio e não depende da ordem de inserção.
-- ============================================================

UPDATE Procedimento_Realizado pr
   SET data_hora_inicio = a.data_hora + (m.espera_minutos || ' minutes')::INTERVAL
  FROM (VALUES
        (TIMESTAMP '2026-06-15 08:30', 102, 10),
        (TIMESTAMP '2026-06-15 08:30', 103, 25),
        (TIMESTAMP '2026-06-20 14:00', 101, 35),
        (TIMESTAMP '2026-07-01 09:00', 105,  5),
        (TIMESTAMP '2026-07-01 09:00', 102, 12),
        (TIMESTAMP '2026-07-02 10:15', 104, 20),
        (TIMESTAMP '2026-07-03 11:30', 107, 15),
        (TIMESTAMP '2026-07-05 16:45', 106,  8),
        (TIMESTAMP '2026-07-06 08:00', 103, 40),
        (TIMESTAMP '2026-07-07 19:20', 110,  3),
        (TIMESTAMP '2026-07-08 13:10', 102, 12),
        (TIMESTAMP '2026-07-09 07:50', 109, 30)
       ) AS m(data_hora, codigo, espera_minutos)
  JOIN Atendimento  a ON a.data_hora = m.data_hora
  JOIN Procedimento p ON p.codigo    = m.codigo
 WHERE pr.id_atendimento  = a.id_atendimento
   AND pr.id_procedimento = p.id_procedimento
   AND pr.data_hora_inicio IS NULL;


-- ============================================================
-- 3. Internações
--
-- Cobre os três casos que a vw_pacientes_internados precisa distinguir:
--
--   Ana Souza      internação antiga encerrada e uma aberta agora. Aparece na
--                  view, e prova que ela olha a internação mais recente.
--   Carla Mendes   internada, sem alta. Aparece.
--   Elisa Rocha    internada, sem alta. Aparece.
--   Bruno Lima     internação única, com alta. Não aparece.
--   Diego Ferreira internação mais recente já encerrada. Não aparece.
--
-- O índice parcial uq_internacao_aberta impede uma segunda internação aberta
-- para o mesmo paciente; as linhas abaixo respeitam isso.
-- ============================================================

INSERT INTO Internacao (id_paciente, id_unidade, data_hora_entrada, data_hora_saida, motivo)
SELECT pa.id_pessoa, u.id_unidade, v.entrada, v.saida, v.motivo
  FROM (VALUES
        ('11111111111', 'Enfermaria A',   TIMESTAMP '2026-05-02 07:00', TIMESTAMP '2026-05-06 16:00', 'crise alergica'),
        ('11111111111', 'Pronto-Socorro', TIMESTAMP '2026-07-24 14:00', NULL::TIMESTAMP,              'observacao pos-procedimento'),
        ('22222222222', 'Enfermaria A',   TIMESTAMP '2026-06-18 09:00', TIMESTAMP '2026-06-25 11:00', 'pneumonia'),
        ('33333333333', 'UTI Adulto',     TIMESTAMP '2026-07-22 10:30', NULL::TIMESTAMP,              'monitoramento neurologico'),
        ('44444444444', 'Enfermaria A',   TIMESTAMP '2026-07-10 08:00', TIMESTAMP '2026-07-12 10:00', 'cirurgia eletiva'),
        ('55555555555', 'Enfermaria A',   TIMESTAMP '2026-07-25 08:30', NULL::TIMESTAMP,              'crise hipertensiva')
       ) AS v(cpf, unidade, entrada, saida, motivo)
  JOIN Pessoa   pe ON pe.CPF       = v.cpf
  JOIN Paciente pa ON pa.id_pessoa = pe.id_pessoa
  JOIN Unidade  u  ON u.nome       = v.unidade;


-- ============================================================
-- 4. Atendimentos novos, com unidade e hora de início
--
-- Cinco atendimentos da segunda metade de julho de 2026, escolhidos para dar
-- material às consultas avançadas da Etapa 2:
--
--   percentual de alto risco por residente   os cinco residentes passam a ter
--                                            proporções diferentes, de 0% a 40%
--   preceptores de pacientes flamenguistas   Ana Souza e Diego Ferreira têm
--                                            is_flamengo verdadeiro
--   último atendimento de cada paciente      todos os cinco pacientes ganham um
--                                            atendimento mais recente
--
-- O id do atendimento é gerado pelo banco, então o INSERT devolve os ids com
-- RETURNING e a segunda parte do comando usa data_hora como ponte para saber a
-- qual atendimento cada procedimento pertence.
-- ============================================================

WITH novos_atendimentos AS (
    INSERT INTO Atendimento
        (data_hora, duracao_minutos, id_preceptor, id_paciente, id_residente, id_unidade)
    VALUES
        ('2026-07-20 08:15', 40,  7, 1, 11, 2),
        ('2026-07-21 14:30', 25,  8, 4, 12, 3),
        ('2026-07-22 10:00', 55,  9, 3, 13, 2),
        ('2026-07-23 11:15', 30, 10, 2, 14, 1),
        ('2026-07-24 16:40', 35,  7, 5, 15, 4)
    RETURNING id_atendimento, data_hora
)
INSERT INTO Procedimento_Realizado
    (id_atendimento, id_procedimento, quantidade, tempo_real_minutos,
     observacao, data_hora_inicio, faturado)
SELECT na.id_atendimento,
       p.id_procedimento,
       v.quantidade,
       v.tempo_real,
       v.observacao,
       na.data_hora + (v.espera_minutos || ' minutes')::INTERVAL,
       v.faturado
  FROM (VALUES
        (TIMESTAMP '2026-07-20 08:15', 105, 1, 30, 'via aerea garantida na primeira tentativa',  6, FALSE),
        (TIMESTAMP '2026-07-20 08:15', 102, 1, 10, NULL,                                        20, TRUE),
        (TIMESTAMP '2026-07-21 14:30', 110, 1, 35, 'acesso em subclavia',                        4, FALSE),
        (TIMESTAMP '2026-07-22 10:00', 106, 1, 48, 'liquor limpido',                             7, FALSE),
        (TIMESTAMP '2026-07-22 10:00', 103, 2, 15, NULL,                                        25, FALSE),
        (TIMESTAMP '2026-07-23 11:15', 104, 1, 22, 'troca de curativo sem sinais de infeccao',  30, TRUE),
        (TIMESTAMP '2026-07-24 16:40', 107, 1, 16, NULL,                                        18, FALSE),
        (TIMESTAMP '2026-07-24 16:40', 102, 1, 11, NULL,                                        25, FALSE)
       ) AS v(data_hora, codigo, quantidade, tempo_real, observacao, espera_minutos, faturado)
  JOIN novos_atendimentos na ON na.data_hora = v.data_hora
  JOIN Procedimento        p  ON p.codigo    = v.codigo;


-- ============================================================
-- 5. Escalas novas
--
-- Servem para exercitar sp_reajustar_escala e trg_check_sobreposicao_escala.
-- Nenhuma delas coloca um residente em dois lugares no mesmo dia e turno, o
-- que o trigger recusaria.
--
-- Cenários que este conjunto permite demonstrar:
--
--   CALL sp_reajustar_escala(14, 'sexta', 'manha', 'quinta', 'manha', NULL);
--       funciona: o residente 14 só tem o plantão de sexta pela manhã
--
--   CALL sp_reajustar_escala(12, 'quinta', 'manha', 'segunda', 'manha', NULL);
--       recusado: o residente 12 já tem plantão na segunda pela manhã
--
--   INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade)
--        VALUES ('segunda', 'manha', 7, 11, 3);
--       recusado pelo trigger: o residente 11 já está na segunda pela manhã na
--       Enfermaria A, e a UNIQUE do esquema não pegaria isso porque a unidade
--       é outra
-- ============================================================

INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade) VALUES
('quinta', 'manha', 6,  12, 1),
('quinta', 'tarde', 8,  13, 3),
('sexta',  'tarde', 7,  15, 3);

-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 1 - Massa de dados de teste (PostgreSQL)
--
-- Executar depois do 01_schema.sql:
--   psql -U postgres -f 02_seed.sql
-- (via docker compose, roda automaticamente na primeira subida)
--
-- Os ids são gerados pelo banco (IDENTITY). Como o banco está vazio,
-- eles saem em sequência: pessoas 1-15, unidades 1-4, etc.

\c hospital_universitario

-- ============ PESSOAS ============
-- ids 1-5: pacientes | ids 6-10: preceptores | ids 11-15: residentes
INSERT INTO Pessoa (CPF, nome, is_flamengo, endereco, telefone, data_nascimento) VALUES
('11111111111', 'Ana Souza',        TRUE,  'Rua das Flores, 10',      '83988880001', '1990-03-12'),
('22222222222', 'Bruno Lima',       FALSE, 'Av. Central, 200',        '83988880002', '1985-07-25'),
('33333333333', 'Carla Mendes',     FALSE, 'Rua do Sol, 45',          '83988880003', '2001-11-02'),
('44444444444', 'Diego Ferreira',   TRUE,  'Rua da Praia, 78',        '83988880004', '1978-01-30'),
('55555555555', 'Elisa Rocha',      FALSE, 'Av. Brasil, 1500',        '83988880005', '1995-09-17'),
('66666666666', 'Fernando Alves',   FALSE, 'Rua Acacias, 33',         '83988880006', '1970-05-08'),
('77777777777', 'Gabriela Pinto',   FALSE, 'Av. Norte, 900',          '83988880007', '1975-12-19'),
('88888888888', 'Henrique Costa',   FALSE, 'Rua Ipe, 21',             '83988880008', '1968-04-03'),
('99999999999', 'Isabela Martins',  FALSE, 'Rua Jasmim, 60',          '83988880009', '1980-08-27'),
('10101010101', 'Joao Nogueira',    TRUE,  'Av. Sul, 450',            '83988880010', '1972-02-14'),
('12121212121', 'Karina Duarte',    FALSE, 'Rua Verde, 5',            '83988880011', '1997-06-21'),
('13131313131', 'Lucas Barbosa',    TRUE,  'Rua Azul, 88',            '83988880012', '1996-10-09'),
('14141414141', 'Mariana Teles',    FALSE, 'Av. Leste, 120',          '83988880013', '1994-03-30'),
('15151515151', 'Nathan Ribeiro',   FALSE, 'Rua Rosa, 14',            '83988880014', '1998-12-05'),
('16161616161', 'Olivia Prado',     FALSE, 'Rua Lilas, 72',           '83988880015', '1995-07-11');

-- ============ PACIENTES (pessoas 1-5) ============
INSERT INTO Paciente (id_pessoa, numero_convenio, grupo_sanguineo) VALUES
(1, 'CONV-0001', 'O+'),
(2, 'CONV-0002', 'A-'),
(3, 'CONV-0003', 'AB+'),
(4, 'CONV-0004', 'B+'),
(5, 'CONV-0005', 'O-');

INSERT INTO Alergia (alergia, id_pessoa) VALUES
('dipirona',       1),
('penicilina',     2),
('latex',          2),
('frutos do mar',  4);

-- ============ PROFISSIONAIS (pessoas 6-15) ============
INSERT INTO Profissional (id_pessoa, CRM, data_admissao, especialidade) VALUES
(6,  'CRM-PB-1001', '2010-02-01', 'Clinica Medica'),
(7,  'CRM-PB-1002', '2012-06-15', 'Cardiologia'),
(8,  'CRM-PB-1003', '2008-09-10', 'Cirurgia Geral'),
(9,  'CRM-PB-1004', '2015-03-20', 'Pediatria'),
(10, 'CRM-PB-1005', '2011-11-05', 'Ortopedia'),
(11, 'CRM-PB-2001', '2025-03-01', 'Clinica Medica'),
(12, 'CRM-PB-2002', '2024-03-01', 'Cardiologia'),
(13, 'CRM-PB-2003', '2023-03-01', 'Cirurgia Geral'),
(14, 'CRM-PB-2004', '2025-03-01', 'Pediatria'),
(15, 'CRM-PB-2005', '2024-03-01', 'Ortopedia');

-- ============ PRECEPTORES (profissionais 6-10) ============
INSERT INTO Preceptor (id_profissional, titulacao) VALUES
(6,  'doutor'),
(7,  'mestre'),
(8,  'doutor'),
(9,  'especialista'),
(10, 'mestre');

-- ============ RESIDENTES (profissionais 11-15) ============
INSERT INTO Residente (id_profissional, ano_residencia) VALUES
(11, 'R1'),
(12, 'R2'),
(13, 'R3'),
(14, 'R1'),
(15, 'R2');

-- ============ UNIDADES (ids 1-4) ============
INSERT INTO Unidade (nome, tipo, capacidade_leitos) VALUES
('Enfermaria A',   'Enfermaria',     40),
('UTI Adulto',     'UTI',            12),
('Pronto-Socorro', 'Pronto-Socorro', 20),
('Ambulatorio',    'Ambulatorio',    10);

-- ============ PROCEDIMENTOS (ids 1-10) ============
INSERT INTO Procedimento (codigo, nome, tempo_medio_minutos, nivel_risco) VALUES
(101, 'Sutura simples',          30, 'MEDIO'),
(102, 'Coleta de sangue',        10, 'BAIXO'),
(103, 'Aplicacao de medicacao',  15, 'BAIXO'),
(104, 'Curativo',                20, 'BAIXO'),
(105, 'Intubacao orotraqueal',   25, 'ALTO'),
(106, 'Puncao lombar',           40, 'ALTO'),
(107, 'Eletrocardiograma',       15, 'BAIXO'),
(108, 'Lavagem gastrica',        35, 'MEDIO'),
(109, 'Drenagem de abscesso',    45, 'MEDIO'),
(110, 'Acesso venoso central',   30, 'ALTO');

-- ============ ATENDIMENTOS (ids 1-10) ============
-- O preceptor 6 supervisiona 6 atendimentos em julho/2026
-- (útil para a consulta "preceptores com mais de 5 atendimentos no mês").
INSERT INTO Atendimento (data_hora, duracao_minutos, id_preceptor, id_paciente, id_residente) VALUES
('2026-06-15 08:30', 45, 7,  1, 11),
('2026-06-20 14:00', 30, 8,  2, 12),
('2026-07-01 09:00', 60, 6,  3, 13),
('2026-07-02 10:15', 40, 6,  1, 11),
('2026-07-03 11:30', 25, 6,  4, 14),
('2026-07-05 16:45', 50, 6,  5, 15),
('2026-07-06 08:00', 35, 6,  2, 12),
('2026-07-07 19:20', 55, 6,  3, 11),
('2026-07-08 13:10', 30, 9,  4, 13),
('2026-07-09 07:50', 70, 10, 5, 14);

-- ============ PROCEDIMENTOS REALIZADOS (12 registros) ============
-- Pacientes 1 e 2 nunca fizeram procedimento de risco ALTO
-- (útil para a consulta "pacientes que nunca realizaram procedimento ALTO").
INSERT INTO Procedimento_Realizado
    (id_atendimento, id_procedimento, quantidade, tempo_real_minutos, observacao, faturado) VALUES
(1,  2,  1, 12, 'sem intercorrencias',   TRUE),
(1,  3,  2, 20, NULL,                    TRUE),
(2,  1,  1, 35, 'paciente agitado',      FALSE),
(3,  5,  1, 28, 'intubacao dificil',     FALSE),
(3,  2,  1,  9, NULL,                    FALSE),
(4,  4,  1, 18, NULL,                    TRUE),
(5,  7,  1, 14, NULL,                    FALSE),
(6,  6,  1, 50, 'liquor turvo',          FALSE),
(7,  3,  3, 30, NULL,                    FALSE),
(8, 10,  1, 33, 'acesso em veia jugular', FALSE),
(9,  2,  1, 11, NULL,                    FALSE),
(10, 9,  1, 48, 'drenagem completa',     FALSE);

-- ============ ESCALAS ============
-- Preceptor 6 supervisiona dois residentes no mesmo dia/turno,
-- em unidades diferentes (permitido pela regra do enunciado).
INSERT INTO Escala (dia_semana, turno, id_preceptor, id_residente, id_unidade) VALUES
('segunda', 'manha', 6,  11, 1),
('segunda', 'manha', 6,  12, 2),
('terca',   'tarde', 7,  11, 3),
('quarta',  'noite', 8,  13, 2),
('sexta',   'manha', 9,  14, 4),
('sabado',  'tarde', 10, 15, 1),
('domingo', 'noite', 6,  11, 2);

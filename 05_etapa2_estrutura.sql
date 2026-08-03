-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 2 - Alterações de estrutura
--
-- Executar depois do 01_schema.sql e do 02_seed.sql:
--   psql -U postgres -f 05_etapa2_estrutura.sql
-- (via docker compose, roda automaticamente na primeira subida)
--
-- Os requisitos da Etapa 2 pedem informação que o esquema da Etapa 1 não
-- guarda. Este script acrescenta o que falta, sem tocar no 01_schema.sql,
-- para que a entrega da Etapa 1 continue verificável como estava.
--
-- O que muda e por quê:
--   atendimento.id_unidade            as views e o cálculo de espera agrupam
--                                     por unidade, e não havia ligação entre
--                                     atendimento e unidade
--   procedimento_realizado.data_hora_inicio
--                                     o tempo médio de espera compara a
--                                     chegada do paciente com o início do
--                                     primeiro procedimento
--   procedimento.media_tempo_procedimento
--                                     coluna mantida pelo trigger
--                                     trg_atualiza_media_procedimentos
--   escala.versao                     controle de concorrência otimista
--   internacao                        base da vw_pacientes_internados
--   auditoria_atendimento             destino do trg_audita_atendimento

\c hospital_universitario

-- A migração é atômica: se dados legados impedirem uma nova regra (por
-- exemplo, escalas duplicadas ou titulação fora do domínio), nenhuma alteração
-- parcial fica aplicada. Os locks de DDL também protegem a carga inicial dos
-- acumuladores contra escritas concorrentes durante a migração.
BEGIN;


-- ------------------------------------------------------------
-- Colunas novas em tabelas existentes
-- ------------------------------------------------------------

-- Fica NULL para não quebrar os endpoints da Etapa 1, que inserem atendimento
-- sem informar unidade. A camada ORM exige o campo; as views ignoram as linhas
-- em que ele está vazio.
ALTER TABLE Atendimento
    ADD COLUMN IF NOT EXISTS id_unidade INTEGER
    REFERENCES Unidade(id_unidade) ON UPDATE CASCADE;

ALTER TABLE Procedimento_Realizado
    ADD COLUMN IF NOT EXISTS data_hora_inicio TIMESTAMP;

ALTER TABLE Procedimento
    ADD COLUMN IF NOT EXISTS media_tempo_procedimento NUMERIC(7,2);

-- A média materializada precisa ser atualizada sem reler linhas que outra
-- transação ainda não confirmou. Estes dois acumuladores permitem ao trigger
-- aplicar deltas atômicos (soma/quantidade) na própria linha de Procedimento.
-- BIGINT evita estouro prematuro quando houver muitos registros históricos.
ALTER TABLE Procedimento
    ADD COLUMN IF NOT EXISTS soma_tempo_procedimento BIGINT NOT NULL DEFAULT 0;

ALTER TABLE Procedimento
    ADD COLUMN IF NOT EXISTS quantidade_tempos_procedimento BIGINT NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'chk_acumuladores_procedimento'
           AND conrelid = 'procedimento'::regclass
    ) THEN
        ALTER TABLE Procedimento
            ADD CONSTRAINT chk_acumuladores_procedimento
            CHECK (
                soma_tempo_procedimento >= 0
                AND quantidade_tempos_procedimento >= 0
            );
    END IF;
END;
$$;

-- Incrementada a cada UPDATE de escala. O SQLAlchemy usa esta coluna como
-- version_id_col: se duas sessões carregam a mesma escala e as duas gravam,
-- a segunda encontra a versão trocada e falha em vez de sobrescrever.
ALTER TABLE Escala
    ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;

-- A UNIQUE original inclui id_unidade e, por isso, permite que duas
-- transações escalem o mesmo residente no mesmo turno em unidades distintas.
-- A chave abaixo representa diretamente a regra de negócio e é a barreira
-- concorrente definitiva; o trigger de 07 continua existindo para produzir
-- uma mensagem mais amigável quando o conflito já está visível.
CREATE UNIQUE INDEX IF NOT EXISTS uq_escala_residente_dia_turno
    ON Escala(id_residente, dia_semana, turno);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'uq_escala_residente_dia_turno'
           AND conrelid = 'escala'::regclass
    ) THEN
        ALTER TABLE Escala
            ADD CONSTRAINT uq_escala_residente_dia_turno
            UNIQUE USING INDEX uq_escala_residente_dia_turno;
    END IF;
END;
$$;


-- ------------------------------------------------------------
-- Domínio de titulação
--
-- Valores textuais legados são reduzidos aos três valores canônicos antes
-- de a restrição ser criada. O trigger de 07 faz a mesma normalização nas
-- escritas futuras (por exemplo, "Doutorado em Cardiologia" vira "doutor").
-- ------------------------------------------------------------

UPDATE Preceptor
   SET titulacao = CASE
       WHEN lower(btrim(titulacao)) LIKE 'doutor%'  THEN 'doutor'
       WHEN lower(btrim(titulacao)) LIKE 'mestr%'   THEN 'mestre'
       WHEN lower(btrim(titulacao)) LIKE 'especial%' THEN 'especialista'
       ELSE lower(btrim(titulacao))
   END;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'chk_preceptor_titulacao'
           AND conrelid = 'preceptor'::regclass
    ) THEN
        ALTER TABLE Preceptor
            ADD CONSTRAINT chk_preceptor_titulacao
            CHECK (titulacao IN ('doutor', 'mestre', 'especialista'));
    END IF;
END;
$$;


-- ------------------------------------------------------------
-- Papel exclusivo do profissional
--
-- Consultar Preceptor a partir de um trigger de Residente (e vice-versa) não
-- basta sob concorrência: duas transações podem não enxergar uma à outra.
-- Esta tabela compartilhada transforma a exclusividade numa chave primária.
-- Os triggers de 07 reservam/liberam o papel junto com a tabela especializada.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS Papel_Profissional(
    id_profissional INTEGER PRIMARY KEY,
    papel VARCHAR(10) NOT NULL,
    CONSTRAINT chk_papel_profissional
        CHECK (papel IN ('PRECEPTOR', 'RESIDENTE')),
    CONSTRAINT papelEhProfissional FOREIGN KEY (id_profissional)
        REFERENCES Profissional(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM Preceptor p
          JOIN Residente r ON r.id_profissional = p.id_profissional
    ) THEN
        RAISE EXCEPTION
            'Existem profissionais cadastrados simultaneamente como preceptor e residente; corrija os dados antes da migração.'
            USING ERRCODE = 'check_violation';
    END IF;
END;
$$;

INSERT INTO Papel_Profissional (id_profissional, papel)
SELECT id_profissional, 'PRECEPTOR'
  FROM Preceptor
ON CONFLICT (id_profissional) DO UPDATE
    SET papel = EXCLUDED.papel;

INSERT INTO Papel_Profissional (id_profissional, papel)
SELECT id_profissional, 'RESIDENTE'
  FROM Residente
ON CONFLICT (id_profissional) DO UPDATE
    SET papel = EXCLUDED.papel;

DELETE FROM Papel_Profissional pp
 WHERE NOT EXISTS (
           SELECT 1 FROM Preceptor p
            WHERE p.id_profissional = pp.id_profissional
       )
   AND NOT EXISTS (
           SELECT 1 FROM Residente r
            WHERE r.id_profissional = pp.id_profissional
       );


-- ------------------------------------------------------------
-- Internação
--
-- O enunciado cita internações no contexto do hospital, mas a Etapa 1 não
-- pedia a tabela. A vw_pacientes_internados depende dela.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS Internacao(
    id_internacao INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_paciente INTEGER NOT NULL,
    id_unidade INTEGER NOT NULL,
    data_hora_entrada TIMESTAMP NOT NULL,
    data_hora_saida TIMESTAMP,
    motivo VARCHAR(200),
    CONSTRAINT chk_saida_posterior CHECK
        (data_hora_saida IS NULL OR data_hora_saida > data_hora_entrada),
    CONSTRAINT temPaciente FOREIGN KEY (id_paciente)
        REFERENCES Paciente(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT temUnidade FOREIGN KEY (id_unidade)
        REFERENCES Unidade(id_unidade)
        ON UPDATE CASCADE
);

-- Um paciente não pode ter duas internações abertas ao mesmo tempo. O índice
-- parcial resolve isso no banco: a restrição só vale para as linhas em que
-- data_hora_saida é NULL, então o histórico de altas fica livre.
CREATE UNIQUE INDEX IF NOT EXISTS uq_internacao_aberta
    ON Internacao(id_paciente)
    WHERE data_hora_saida IS NULL;

CREATE INDEX IF NOT EXISTS idx_internacao_paciente_entrada
    ON Internacao(id_paciente, data_hora_entrada DESC);


-- ------------------------------------------------------------
-- Auditoria de atendimento
--
-- id_atendimento não tem chave estrangeira de propósito: a linha de auditoria
-- de um DELETE precisa continuar existindo depois que o atendimento sai da
-- tabela. Uma FK apagaria em cascata justamente o registro que interessa.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS Auditoria_Atendimento(
    id_auditoria INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_atendimento INTEGER,
    operacao VARCHAR(6) NOT NULL,
    usuario VARCHAR(63) NOT NULL,
    data_hora TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dados_antigos JSONB,
    dados_novos JSONB,
    CONSTRAINT chk_operacao CHECK (operacao IN ('INSERT', 'UPDATE', 'DELETE'))
);

CREATE INDEX IF NOT EXISTS idx_auditoria_atendimento
    ON Auditoria_Atendimento(id_atendimento, data_hora DESC);


-- ------------------------------------------------------------
-- Carga inicial da média de tempo
--
-- O trigger da Etapa 2 mantém os acumuladores e a média a partir de agora,
-- mas os procedimentos já gravados pelo seed da Etapa 1 precisam de um estado
-- inicial coerente. O UPDATE cobre também procedimentos sem medição, deixando
-- soma/quantidade em zero e a média nula. Reexecutá-lo é seguro.
-- ------------------------------------------------------------

UPDATE Procedimento p
   SET soma_tempo_procedimento       = m.soma,
       quantidade_tempos_procedimento = m.quantidade,
       media_tempo_procedimento      = m.media
  FROM (
        SELECT p0.id_procedimento,
               COALESCE(SUM(pr.tempo_real_minutos), 0)::BIGINT AS soma,
               COUNT(pr.tempo_real_minutos)::BIGINT            AS quantidade,
               ROUND(AVG(pr.tempo_real_minutos), 2)             AS media
          FROM Procedimento p0
          LEFT JOIN Procedimento_Realizado pr
            ON pr.id_procedimento = p0.id_procedimento
         GROUP BY p0.id_procedimento
       ) m
 WHERE m.id_procedimento = p.id_procedimento;

COMMIT;

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

-- Incrementada a cada UPDATE de escala. O SQLAlchemy usa esta coluna como
-- version_id_col: se duas sessões carregam a mesma escala e as duas gravam,
-- a segunda encontra a versão trocada e falha em vez de sobrescrever.
ALTER TABLE Escala
    ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;


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
-- O trigger da Etapa 2 mantém media_tempo_procedimento a partir de agora, mas
-- os procedimentos já gravados pelo seed da Etapa 1 ficariam com a coluna
-- vazia. Este UPDATE calcula o valor de partida.
-- ------------------------------------------------------------

UPDATE Procedimento p
   SET media_tempo_procedimento = m.media
  FROM (SELECT id_procedimento, ROUND(AVG(tempo_real_minutos), 2) AS media
          FROM Procedimento_Realizado
         WHERE tempo_real_minutos IS NOT NULL
         GROUP BY id_procedimento) m
 WHERE m.id_procedimento = p.id_procedimento;

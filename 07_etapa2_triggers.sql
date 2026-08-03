-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 2 - Triggers
--
-- Executar depois do 06_etapa2_procedures.sql:
--   psql -U postgres -f 07_etapa2_triggers.sql
--
-- No PostgreSQL um trigger não carrega código: ele aponta para uma função
-- declarada com RETURNS TRIGGER. Por isso cada item abaixo tem duas partes,
-- a função fn_* e o trigger trg_* que a dispara.

\c hospital_universitario

-- Funções e triggers são publicados juntos. Se algum dado legado violar
-- uma das novas garantias, a instalação inteira é desfeita em vez de deixar
-- apenas parte dos triggers atualizada.
BEGIN;


-- ============================================================
-- Normalização da titulação do preceptor
--
-- O banco guarda somente os valores canônicos aceitos pelo domínio. Formas
-- usuais mais descritivas são normalizadas antes do CHECK; assim,
-- "Doutorado em Cardiologia" e "Doutora" são armazenados como "doutor".
-- Termos fora do domínio continuam sendo recusados pelo CHECK de 05.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_normaliza_titulacao_preceptor()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_titulacao TEXT := lower(btrim(NEW.titulacao));
BEGIN
    NEW.titulacao := CASE
        WHEN v_titulacao LIKE 'doutor%'   THEN 'doutor'
        WHEN v_titulacao LIKE 'mestr%'    THEN 'mestre'
        WHEN v_titulacao LIKE 'especial%' THEN 'especialista'
        ELSE v_titulacao
    END;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_normaliza_titulacao_preceptor ON Preceptor;

CREATE TRIGGER trg_normaliza_titulacao_preceptor
    BEFORE INSERT OR UPDATE OF titulacao ON Preceptor
    FOR EACH ROW
    EXECUTE FUNCTION fn_normaliza_titulacao_preceptor();


-- ============================================================
-- Exclusividade entre preceptor e residente
--
-- Papel_Profissional tem uma linha por profissional. A tentativa de reservar
-- papéis diferentes disputa a mesma chave primária, inclusive quando as duas
-- inserções ocorrem em transações concorrentes que não se enxergam.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_reserva_papel_profissional()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_papel_desejado VARCHAR(10);
    v_papel_atual    VARCHAR(10);
BEGIN
    v_papel_desejado := CASE lower(TG_TABLE_NAME)
        WHEN 'preceptor' THEN 'PRECEPTOR'
        WHEN 'residente' THEN 'RESIDENTE'
    END;

    IF TG_OP = 'UPDATE'
       AND OLD.id_profissional IS NOT DISTINCT FROM NEW.id_profissional THEN
        RETURN NEW;
    END IF;

    INSERT INTO Papel_Profissional (id_profissional, papel)
    VALUES (NEW.id_profissional, v_papel_desejado)
    ON CONFLICT (id_profissional) DO NOTHING;

    IF NOT FOUND THEN
        SELECT papel
          INTO v_papel_atual
          FROM Papel_Profissional
         WHERE id_profissional = NEW.id_profissional;

        IF v_papel_atual IS DISTINCT FROM v_papel_desejado THEN
            RAISE EXCEPTION
                'Profissional % já está cadastrado como % e não pode ser também %.',
                NEW.id_profissional, lower(v_papel_atual), lower(v_papel_desejado)
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'chk_papel_profissional_exclusivo';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_libera_papel_profissional()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_papel_antigo VARCHAR(10);
BEGIN
    v_papel_antigo := CASE lower(TG_TABLE_NAME)
        WHEN 'preceptor' THEN 'PRECEPTOR'
        WHEN 'residente' THEN 'RESIDENTE'
    END;

    IF TG_OP = 'UPDATE'
       AND OLD.id_profissional IS NOT DISTINCT FROM NEW.id_profissional THEN
        RETURN NEW;
    END IF;

    DELETE FROM Papel_Profissional
     WHERE id_profissional = OLD.id_profissional
       AND papel = v_papel_antigo;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_reserva_papel_preceptor ON Preceptor;
CREATE TRIGGER trg_reserva_papel_preceptor
    BEFORE INSERT OR UPDATE OF id_profissional ON Preceptor
    FOR EACH ROW
    EXECUTE FUNCTION fn_reserva_papel_profissional();

DROP TRIGGER IF EXISTS trg_libera_papel_preceptor ON Preceptor;
CREATE TRIGGER trg_libera_papel_preceptor
    AFTER DELETE OR UPDATE OF id_profissional ON Preceptor
    FOR EACH ROW
    EXECUTE FUNCTION fn_libera_papel_profissional();

DROP TRIGGER IF EXISTS trg_reserva_papel_residente ON Residente;
CREATE TRIGGER trg_reserva_papel_residente
    BEFORE INSERT OR UPDATE OF id_profissional ON Residente
    FOR EACH ROW
    EXECUTE FUNCTION fn_reserva_papel_profissional();

DROP TRIGGER IF EXISTS trg_libera_papel_residente ON Residente;
CREATE TRIGGER trg_libera_papel_residente
    AFTER DELETE OR UPDATE OF id_profissional ON Residente
    FOR EACH ROW
    EXECUTE FUNCTION fn_libera_papel_profissional();


-- ============================================================
-- trg_check_sobreposicao_escala
--
-- Impede que o mesmo residente apareça no mesmo dia e turno em duas unidades
-- diferentes. O trigger oferece uma mensagem amigável quando a outra linha
-- já está visível; a UNIQUE uq_escala_residente_dia_turno, criada em 05, é
-- quem fecha também a corrida entre transações simultâneas.
--
-- A regra vale só para o residente. O preceptor continua podendo supervisionar
-- vários residentes no mesmo dia e turno, em unidades diferentes, como o
-- enunciado permite.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_check_sobreposicao_escala()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_outra_unidade VARCHAR;
BEGIN
    SELECT u.nome
      INTO v_outra_unidade
      FROM Escala e
      JOIN Unidade u ON u.id_unidade = e.id_unidade
     WHERE e.id_residente = NEW.id_residente
       AND e.dia_semana   = NEW.dia_semana
       AND e.turno        = NEW.turno
       AND e.id_unidade  <> NEW.id_unidade
       AND e.id_escala   <> COALESCE(NEW.id_escala, -1)
     LIMIT 1;

    IF v_outra_unidade IS NOT NULL THEN
        RAISE EXCEPTION
            'Residente % já está escalado em % % na unidade "%".',
            NEW.id_residente, NEW.dia_semana, NEW.turno, v_outra_unidade
            USING ERRCODE = 'unique_violation',
                  HINT = 'Um residente não pode cobrir duas unidades no mesmo turno.';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_check_sobreposicao_escala ON Escala;

CREATE TRIGGER trg_check_sobreposicao_escala
    BEFORE INSERT OR UPDATE ON Escala
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_sobreposicao_escala();


-- ============================================================
-- trg_audita_atendimento
--
-- Copia para auditoria_atendimento o estado anterior e o posterior de cada
-- linha alterada. to_jsonb(OLD) e to_jsonb(NEW) transformam a linha inteira em
-- JSON, então a auditoria continua funcionando se a tabela ganhar colunas.
--
-- O trigger é AFTER: só registra o que o banco aceitou, depois das constraints.
-- Em DELETE, id_atendimento vem de OLD, e a linha de auditoria sobrevive ao
-- atendimento porque a coluna não tem chave estrangeira (ver 05).
--
-- usuario recebe session_user, o usuário que abriu a conexão. current_user
-- mudaria com SET ROLE ou dentro de rotina SECURITY DEFINER, o que numa
-- auditoria esconderia justamente quem agiu.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_audita_atendimento()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO Auditoria_Atendimento
            (id_atendimento, operacao, usuario, dados_antigos, dados_novos)
        VALUES (NEW.id_atendimento, 'INSERT', session_user, NULL, to_jsonb(NEW));
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO Auditoria_Atendimento
            (id_atendimento, operacao, usuario, dados_antigos, dados_novos)
        VALUES (NEW.id_atendimento, 'UPDATE', session_user, to_jsonb(OLD), to_jsonb(NEW));
        RETURN NEW;

    ELSE
        INSERT INTO Auditoria_Atendimento
            (id_atendimento, operacao, usuario, dados_antigos, dados_novos)
        VALUES (OLD.id_atendimento, 'DELETE', session_user, to_jsonb(OLD), NULL);
        RETURN OLD;
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS trg_audita_atendimento ON Atendimento;

CREATE TRIGGER trg_audita_atendimento
    AFTER INSERT OR UPDATE OR DELETE ON Atendimento
    FOR EACH ROW
    EXECUTE FUNCTION fn_audita_atendimento();


-- ============================================================
-- Integridade entre atendimento e procedimentos
--
-- O atendimento precisa existir antes de seus procedimentos por causa da FK,
-- portanto a regra "pelo menos um procedimento" não pode ser validada no
-- primeiro INSERT. Os constraint triggers abaixo são INITIALLY DEFERRED: eles
-- observam o estado final no COMMIT e permitem o estado intermediário dentro
-- da transação. Excluir o próprio atendimento continua permitido.
-- ============================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM Atendimento a
         WHERE NOT EXISTS (
                   SELECT 1
                     FROM Procedimento_Realizado pr
                    WHERE pr.id_atendimento = a.id_atendimento
               )
    ) THEN
        RAISE EXCEPTION
            'Existem atendimentos sem procedimento; corrija os dados antes de instalar a restrição diferida.'
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'atendimento_exige_procedimento';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM Procedimento_Realizado pr
          JOIN Atendimento a ON a.id_atendimento = pr.id_atendimento
         WHERE pr.data_hora_inicio < a.data_hora
    ) THEN
        RAISE EXCEPTION
            'Existem procedimentos iniciados antes do atendimento; corrija os dados antes de instalar a validação temporal.'
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'chk_procedimento_inicio_apos_atendimento';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION fn_atendimento_exige_procedimento()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_id_atendimento INTEGER;
BEGIN
    IF lower(TG_TABLE_NAME) = 'atendimento' THEN
        v_id_atendimento := NEW.id_atendimento;

        IF EXISTS (
            SELECT 1 FROM Atendimento a
             WHERE a.id_atendimento = v_id_atendimento
        ) AND NOT EXISTS (
            SELECT 1 FROM Procedimento_Realizado pr
             WHERE pr.id_atendimento = v_id_atendimento
        ) THEN
            RAISE EXCEPTION
                'Atendimento % precisa ter pelo menos um procedimento.',
                v_id_atendimento
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'atendimento_exige_procedimento';
        END IF;

    ELSE
        -- DELETE e a troca de id_atendimento podem deixar o atendimento antigo
        -- vazio. Em UPDATE, o novo destino já contém a própria linha movida.
        v_id_atendimento := OLD.id_atendimento;

        IF EXISTS (
            SELECT 1 FROM Atendimento a
             WHERE a.id_atendimento = v_id_atendimento
        ) AND NOT EXISTS (
            SELECT 1 FROM Procedimento_Realizado pr
             WHERE pr.id_atendimento = v_id_atendimento
        ) THEN
            RAISE EXCEPTION
                'Atendimento % precisa ter pelo menos um procedimento.',
                v_id_atendimento
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'atendimento_exige_procedimento';
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_atendimento_exige_procedimento ON Atendimento;

CREATE CONSTRAINT TRIGGER trg_atendimento_exige_procedimento
    AFTER INSERT ON Atendimento
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION fn_atendimento_exige_procedimento();

DROP TRIGGER IF EXISTS trg_procedimento_preserva_atendimento ON Procedimento_Realizado;

CREATE CONSTRAINT TRIGGER trg_procedimento_preserva_atendimento
    AFTER DELETE OR UPDATE ON Procedimento_Realizado
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION fn_atendimento_exige_procedimento();


-- O início de um procedimento não pode anteceder a chegada registrada no
-- atendimento. O FOR UPDATE no pai serializa esta validação com mudanças de
-- Atendimento.data_hora e fecha a janela de corrida entre as duas tabelas.
CREATE OR REPLACE FUNCTION fn_valida_inicio_procedimento()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_data_hora_atendimento TIMESTAMP;
BEGIN
    SELECT a.data_hora
      INTO v_data_hora_atendimento
      FROM Atendimento a
     WHERE a.id_atendimento = NEW.id_atendimento
       FOR UPDATE;

    -- A inexistência do atendimento fica a cargo da chave estrangeira.
    IF FOUND
       AND NEW.data_hora_inicio IS NOT NULL
       AND NEW.data_hora_inicio < v_data_hora_atendimento THEN
        RAISE EXCEPTION
            'O procedimento não pode começar antes do atendimento % (% < %).',
            NEW.id_atendimento, NEW.data_hora_inicio, v_data_hora_atendimento
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'chk_procedimento_inicio_apos_atendimento';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_valida_inicio_procedimento ON Procedimento_Realizado;

CREATE TRIGGER trg_valida_inicio_procedimento
    BEFORE INSERT OR UPDATE OF id_atendimento, data_hora_inicio
    ON Procedimento_Realizado
    FOR EACH ROW
    EXECUTE FUNCTION fn_valida_inicio_procedimento();


-- A validação inversa impede mover a chegada para depois de um procedimento
-- já registrado. O UPDATE da linha de Atendimento fornece o mesmo lock usado
-- pelo trigger acima, portanto as duas direções ficam serializadas.
CREATE OR REPLACE FUNCTION fn_valida_data_hora_atendimento()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_primeiro_inicio TIMESTAMP;
BEGIN
    IF NEW.data_hora IS NOT DISTINCT FROM OLD.data_hora THEN
        RETURN NEW;
    END IF;

    SELECT MIN(pr.data_hora_inicio)
      INTO v_primeiro_inicio
      FROM Procedimento_Realizado pr
     WHERE pr.id_atendimento = NEW.id_atendimento;

    IF v_primeiro_inicio IS NOT NULL
       AND NEW.data_hora > v_primeiro_inicio THEN
        RAISE EXCEPTION
            'O atendimento % não pode iniciar depois de seu primeiro procedimento (% > %).',
            NEW.id_atendimento, NEW.data_hora, v_primeiro_inicio
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'chk_atendimento_antes_procedimentos';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_valida_data_hora_atendimento ON Atendimento;

CREATE TRIGGER trg_valida_data_hora_atendimento
    BEFORE UPDATE OF data_hora ON Atendimento
    FOR EACH ROW
    EXECUTE FUNCTION fn_valida_data_hora_atendimento();


-- ============================================================
-- trg_atualiza_media_procedimentos
--
-- Mantém procedimento.media_tempo_procedimento com a média de
-- tempo_real_minutos daquele procedimento em todos os atendimentos. É um valor
-- derivado guardado na tabela: leitura barata em troca de recalculá-lo a cada
-- escrita.
--
-- O enunciado pede AFTER INSERT. Só isso deixaria a média velha quando alguém
-- corrigisse o tempo de um registro ou apagasse a linha, e a API da Etapa 1
-- permite as duas coisas (PUT e DELETE em /procedimentos-realizados). Por isso
-- há dois triggers sobre a mesma função: trg_atualiza_media_procedimentos,
-- exatamente como pedido, e trg_atualiza_media_procedimentos_ud, que cobre a
-- correção e a remoção.
--
-- Em UPDATE que troca id_procedimento, os dois procedimentos são recalculados:
-- o que perdeu a linha e o que ganhou.
-- ============================================================

-- Todas as alterações dos acumuladores usam o mesmo advisory lock de
-- transação. O lock é independente de snapshots MVCC e impede que dois
-- triggers apliquem seus deltas em ordens incompatíveis; o UPDATE seguinte,
-- por sua vez, soma o delta atomicamente sobre a versão mais recente da linha.
-- O custo é serializar apenas a pequena etapa de manutenção da estatística.
CREATE OR REPLACE FUNCTION fn_aplica_delta_media_procedimento(
    p_id_procedimento INTEGER,
    p_delta_soma      BIGINT,
    p_delta_quantidade BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE Procedimento p
       SET soma_tempo_procedimento =
               p.soma_tempo_procedimento + p_delta_soma,
           quantidade_tempos_procedimento =
               p.quantidade_tempos_procedimento + p_delta_quantidade,
           media_tempo_procedimento = CASE
               WHEN p.quantidade_tempos_procedimento + p_delta_quantidade = 0
                   THEN NULL
               ELSE ROUND(
                   (p.soma_tempo_procedimento + p_delta_soma)::NUMERIC /
                   (p.quantidade_tempos_procedimento + p_delta_quantidade),
                   2
               )
           END
     WHERE p.id_procedimento = p_id_procedimento
       AND p.quantidade_tempos_procedimento + p_delta_quantidade >= 0
       AND p.soma_tempo_procedimento + p_delta_soma >= 0;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Não foi possível atualizar os acumuladores do procedimento %.',
            p_id_procedimento
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'chk_acumuladores_procedimento';
    END IF;
END;
$$;

-- Mantida como utilitário compatível para reparação administrativa de uma
-- linha. Os triggers normais usam deltas e não dependem desta releitura.
CREATE OR REPLACE FUNCTION fn_recalcula_media_procedimento(p_id_procedimento INTEGER)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(726976170001::BIGINT);

    UPDATE Procedimento p
       SET soma_tempo_procedimento = m.soma,
           quantidade_tempos_procedimento = m.quantidade,
           media_tempo_procedimento = m.media
      FROM (
            SELECT COALESCE(SUM(pr.tempo_real_minutos), 0)::BIGINT AS soma,
                   COUNT(pr.tempo_real_minutos)::BIGINT            AS quantidade,
                   ROUND(AVG(pr.tempo_real_minutos), 2)             AS media
              FROM Procedimento_Realizado pr
             WHERE pr.id_procedimento = p_id_procedimento
           ) m
     WHERE p.id_procedimento = p_id_procedimento;
END;
$$;

CREATE OR REPLACE FUNCTION fn_atualiza_media_procedimentos()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Um único lock global evita deadlocks quando um UPDATE move registros
    -- entre procedimentos diferentes e também serializa transações que
    -- removem os últimos procedimentos de um atendimento.
    PERFORM pg_advisory_xact_lock(726976170001::BIGINT);

    IF TG_OP = 'INSERT' THEN
        PERFORM fn_aplica_delta_media_procedimento(
            NEW.id_procedimento,
            COALESCE(NEW.tempo_real_minutos, 0)::BIGINT,
            CASE WHEN NEW.tempo_real_minutos IS NULL THEN 0 ELSE 1 END
        );
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        PERFORM fn_aplica_delta_media_procedimento(
            OLD.id_procedimento,
            -COALESCE(OLD.tempo_real_minutos, 0)::BIGINT,
            CASE WHEN OLD.tempo_real_minutos IS NULL THEN 0 ELSE -1 END
        );
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.id_procedimento IS DISTINCT FROM NEW.id_procedimento THEN
        PERFORM fn_aplica_delta_media_procedimento(
            OLD.id_procedimento,
            -COALESCE(OLD.tempo_real_minutos, 0)::BIGINT,
            CASE WHEN OLD.tempo_real_minutos IS NULL THEN 0 ELSE -1 END
        );

        PERFORM fn_aplica_delta_media_procedimento(
            NEW.id_procedimento,
            COALESCE(NEW.tempo_real_minutos, 0)::BIGINT,
            CASE WHEN NEW.tempo_real_minutos IS NULL THEN 0 ELSE 1 END
        );

        RETURN NEW;
    END IF;

    -- UPDATE no mesmo procedimento: aplica apenas a diferença entre o estado
    -- antigo e o novo, inclusive nas transições NULL <-> valor.
    PERFORM fn_aplica_delta_media_procedimento(
        NEW.id_procedimento,
        (COALESCE(NEW.tempo_real_minutos, 0) -
         COALESCE(OLD.tempo_real_minutos, 0))::BIGINT,
        (CASE WHEN NEW.tempo_real_minutos IS NULL THEN 0 ELSE 1 END -
         CASE WHEN OLD.tempo_real_minutos IS NULL THEN 0 ELSE 1 END)::BIGINT
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_atualiza_media_procedimentos ON Procedimento_Realizado;

CREATE TRIGGER trg_atualiza_media_procedimentos
    AFTER INSERT ON Procedimento_Realizado
    FOR EACH ROW
    EXECUTE FUNCTION fn_atualiza_media_procedimentos();

DROP TRIGGER IF EXISTS trg_atualiza_media_procedimentos_ud ON Procedimento_Realizado;

CREATE TRIGGER trg_atualiza_media_procedimentos_ud
    AFTER UPDATE OR DELETE ON Procedimento_Realizado
    FOR EACH ROW
    EXECUTE FUNCTION fn_atualiza_media_procedimentos();

COMMIT;

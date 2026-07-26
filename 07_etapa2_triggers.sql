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


-- ============================================================
-- trg_check_sobreposicao_escala
--
-- Impede que o mesmo residente apareça no mesmo dia e turno em duas unidades
-- diferentes. A UNIQUE(id_unidade, dia_semana, turno, id_residente) da Etapa 1
-- não cobre esse caso: para ela, o mesmo residente na segunda de manhã na
-- Enfermaria A e na UTI são duas linhas distintas e válidas. Somando as duas
-- regras, o residente passa a ter no máximo um plantão por dia/turno.
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

CREATE OR REPLACE FUNCTION fn_recalcula_media_procedimento(p_id_procedimento INTEGER)
RETURNS VOID
LANGUAGE sql
AS $$
    UPDATE Procedimento
       SET media_tempo_procedimento = (
               SELECT ROUND(AVG(pr.tempo_real_minutos), 2)
                 FROM Procedimento_Realizado pr
                WHERE pr.id_procedimento = p_id_procedimento
                  AND pr.tempo_real_minutos IS NOT NULL
           )
     WHERE id_procedimento = p_id_procedimento;
$$;

CREATE OR REPLACE FUNCTION fn_atualiza_media_procedimentos()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM fn_recalcula_media_procedimento(OLD.id_procedimento);
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.id_procedimento IS DISTINCT FROM NEW.id_procedimento THEN
        PERFORM fn_recalcula_media_procedimento(OLD.id_procedimento);
    END IF;

    PERFORM fn_recalcula_media_procedimento(NEW.id_procedimento);
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

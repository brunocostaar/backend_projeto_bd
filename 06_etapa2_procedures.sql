-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 2 - Stored procedures
--
-- Executar depois do 05_etapa2_estrutura.sql:
--   psql -U postgres -f 06_etapa2_procedures.sql
--
-- Sobre PROCEDURE e FUNCTION no PostgreSQL: são objetos diferentes. PROCEDURE
-- é chamada com CALL, não devolve valor de retorno (só parâmetros INOUT) e
-- participa da transação de quem chamou. FUNCTION é chamada dentro de um
-- SELECT e devolve valor. As duas rotinas que gravam dados são PROCEDURE; a
-- que só devolve um relatório é FUNCTION, porque precisa aparecer no FROM de
-- uma consulta. O prefixo sp_ foi mantido nos três nomes por causa do
-- enunciado.

\c hospital_universitario


-- ============================================================
-- sp_registrar_atendimento_completo
--
-- Grava o atendimento e todos os seus procedimentos de uma vez. A lista de
-- procedimentos chega como array JSON, cada item no formato:
--
--   {"id_procedimento": 5, "quantidade": 1, "tempo_real_minutos": 28,
--    "observacao": "intubacao dificil", "data_hora_inicio": "2026-08-03T09:06",
--    "faturado": false}
--
-- Só id_procedimento é obrigatório. Quando data_hora_inicio não vem, assume-se
-- que o procedimento começou junto com o atendimento.
--
-- Atomicidade: não há BEGIN/COMMIT no corpo de propósito. Um CALL roda dentro
-- da transação de quem chamou, e qualquer RAISE aqui aborta o comando inteiro,
-- desfazendo o INSERT do atendimento junto com os procedimentos já inseridos
-- no laço. Um COMMIT no meio da rotina destruiria essa garantia.
--
-- Uso:
--   CALL sp_registrar_atendimento_completo(
--       '2026-08-03 09:00', 40, 1, 11, 6, 2,
--       '[{"id_procedimento": 5, "tempo_real_minutos": 28}]'::jsonb, NULL);
--
-- O último argumento é INOUT: o CALL devolve uma linha com o id gerado.
-- ============================================================

DROP PROCEDURE IF EXISTS sp_registrar_atendimento_completo;

CREATE PROCEDURE sp_registrar_atendimento_completo(
    p_data_hora            TIMESTAMP,
    p_duracao_minutos      INTEGER,
    p_id_paciente          INTEGER,
    p_id_residente         INTEGER,
    p_id_preceptor         INTEGER,
    p_id_unidade           INTEGER,
    p_procedimentos        JSONB,
    INOUT p_id_atendimento INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_item     JSONB;
    v_id_proc  INTEGER;
    v_total    INTEGER;
BEGIN
    -- A lista precisa ser um array JSON com pelo menos um item. O constraint
    -- trigger diferido de 07 também garante essa cardinalidade no COMMIT; esta
    -- validação antecipada preserva uma mensagem clara para quem usa a rotina.
    IF p_procedimentos IS NULL OR jsonb_typeof(p_procedimentos) <> 'array' THEN
        RAISE EXCEPTION
            'p_procedimentos deve ser um array JSON, recebido: %',
            COALESCE(jsonb_typeof(p_procedimentos), 'null')
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    v_total := jsonb_array_length(p_procedimentos);
    IF v_total = 0 THEN
        RAISE EXCEPTION 'Um atendimento precisa de pelo menos um procedimento.'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- Checagem das referências antes do INSERT, para devolver mensagem legível
    -- em vez de deixar a violação de chave estrangeira subir crua.
    IF NOT EXISTS (SELECT 1 FROM Paciente WHERE id_pessoa = p_id_paciente) THEN
        RAISE EXCEPTION 'Paciente % não existe.', p_id_paciente
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Residente WHERE id_profissional = p_id_residente) THEN
        RAISE EXCEPTION 'Residente % não existe.', p_id_residente
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Preceptor WHERE id_profissional = p_id_preceptor) THEN
        RAISE EXCEPTION 'Preceptor % não existe.', p_id_preceptor
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF p_id_unidade IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM Unidade WHERE id_unidade = p_id_unidade) THEN
        RAISE EXCEPTION 'Unidade % não existe.', p_id_unidade
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    INSERT INTO Atendimento
        (data_hora, duracao_minutos, id_paciente, id_residente, id_preceptor, id_unidade)
    VALUES
        (p_data_hora, p_duracao_minutos, p_id_paciente, p_id_residente,
         p_id_preceptor, p_id_unidade)
    RETURNING id_atendimento INTO p_id_atendimento;

    FOR v_item IN
        SELECT t.elem FROM jsonb_array_elements(p_procedimentos) AS t(elem)
    LOOP
        v_id_proc := (v_item->>'id_procedimento')::INTEGER;

        IF v_id_proc IS NULL THEN
            RAISE EXCEPTION 'Item sem id_procedimento: %', v_item
                USING ERRCODE = 'invalid_parameter_value';
        END IF;

        IF NOT EXISTS (SELECT 1 FROM Procedimento WHERE id_procedimento = v_id_proc) THEN
            RAISE EXCEPTION 'Procedimento % não existe.', v_id_proc
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        -- Repetir o mesmo id_procedimento na lista viola a chave primária de
        -- procedimento_realizado. A exceção é intencional: a repetição do
        -- procedimento no atendimento é registrada na coluna quantidade.
        INSERT INTO Procedimento_Realizado
            (id_atendimento, id_procedimento, quantidade, tempo_real_minutos,
             observacao, data_hora_inicio, faturado)
        VALUES (
            p_id_atendimento,
            v_id_proc,
            COALESCE((v_item->>'quantidade')::INTEGER, 1),
            (v_item->>'tempo_real_minutos')::INTEGER,
            v_item->>'observacao',
            COALESCE((v_item->>'data_hora_inicio')::TIMESTAMP, p_data_hora),
            COALESCE((v_item->>'faturado')::BOOLEAN, FALSE)
        );
    END LOOP;

    RAISE NOTICE 'Atendimento % gravado com % procedimento(s).',
        p_id_atendimento, v_total;
END;
$$;


-- ============================================================
-- sp_calcular_tempo_medio_espera
--
-- Para cada unidade, média do intervalo entre a chegada do paciente
-- (atendimento.data_hora) e o início do primeiro procedimento daquele
-- atendimento (menor procedimento_realizado.data_hora_inicio).
--
-- É FUNCTION porque devolve um conjunto de linhas. Os nomes das colunas de
-- saída fogem dos nomes usados nas tabelas (unidade_id em vez de id_unidade)
-- porque, dentro do corpo, um parâmetro de saída com o mesmo nome de uma
-- coluna gera erro de referência ambígua.
--
-- Atendimentos sem unidade registrada ou sem nenhum procedimento com hora de
-- início ficam fora da conta, assim como os casos em que o início consta como
-- anterior à chegada, que indicariam dado errado.
--
-- Uso:
--   SELECT * FROM sp_calcular_tempo_medio_espera();
-- ============================================================

DROP FUNCTION IF EXISTS sp_calcular_tempo_medio_espera;

CREATE FUNCTION sp_calcular_tempo_medio_espera()
RETURNS TABLE (
    unidade_id                INTEGER,
    nome_unidade              VARCHAR,
    atendimentos_considerados BIGINT,
    espera_media_minutos      NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    WITH primeiro_procedimento AS (
        SELECT a.id_atendimento,
               a.id_unidade,
               a.data_hora,
               MIN(pr.data_hora_inicio) AS inicio
          FROM Atendimento a
          JOIN Procedimento_Realizado pr ON pr.id_atendimento = a.id_atendimento
         WHERE a.id_unidade IS NOT NULL
           AND pr.data_hora_inicio IS NOT NULL
           AND pr.data_hora_inicio >= a.data_hora
         GROUP BY a.id_atendimento, a.id_unidade, a.data_hora
    )
    SELECT u.id_unidade,
           u.nome,
           COUNT(*),
           ROUND(AVG(EXTRACT(EPOCH FROM (pp.inicio - pp.data_hora)) / 60.0)::NUMERIC, 1)
      FROM primeiro_procedimento pp
      JOIN Unidade u ON u.id_unidade = pp.id_unidade
     GROUP BY u.id_unidade, u.nome
     ORDER BY 4 DESC, u.nome;
END;
$$;


-- ============================================================
-- sp_reajustar_escala
--
-- Move os plantões de um residente de um dia/turno para outro, tudo ou nada.
--
-- A UNIQUE(id_residente, dia_semana, turno) é a barreira definitiva contra
-- sobreposição. A rotina também bloqueia a linha do residente: chamadas
-- concorrentes para a mesma pessoa ficam serializadas, de modo que a segunda
-- relê a origem somente depois de a primeira confirmar sua mudança. Isso evita
-- que duas chamadas anunciem que moveram a mesma escala (lost update).
--
-- Uso:
--   CALL sp_reajustar_escala(14, 'sexta', 'manha', 'quinta', 'manha', NULL);
-- ============================================================

DROP PROCEDURE IF EXISTS sp_reajustar_escala;

CREATE PROCEDURE sp_reajustar_escala(
    p_id_residente          INTEGER,
    p_dia_origem            VARCHAR,
    p_turno_origem          VARCHAR,
    p_dia_destino           VARCHAR,
    p_turno_destino         VARCHAR,
    INOUT p_escalas_movidas INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_dias        CONSTANT VARCHAR[] := ARRAY['segunda', 'terca', 'quarta',
                                              'quinta', 'sexta', 'sabado',
                                              'domingo'];
    v_turnos      CONSTANT VARCHAR[] := ARRAY['manha', 'tarde', 'noite'];
    v_movendo     INTEGER[];
    v_ja_ocupado  INTEGER;
BEGIN
    p_escalas_movidas := 0;

    -- O lock é deliberadamente feito antes da leitura das escalas. Bloquear a
    -- linha de Residente, que sempre existe e é única por pessoa, também cobre
    -- o caso em que ainda não há linha de Escala que pudesse ser bloqueada.
    PERFORM 1
      FROM Residente
     WHERE id_profissional = p_id_residente
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Residente % não existe.', p_id_residente
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- Validar os valores aqui evita descobrir o erro só na violação do CHECK,
    -- com mensagem bem menos clara.
    IF NOT (p_dia_origem = ANY(v_dias)) OR NOT (p_dia_destino = ANY(v_dias)) THEN
        RAISE EXCEPTION 'Dia da semana inválido. Use um de: %',
            array_to_string(v_dias, ', ')
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF NOT (p_turno_origem = ANY(v_turnos)) OR NOT (p_turno_destino = ANY(v_turnos)) THEN
        RAISE EXCEPTION 'Turno inválido. Use um de: %',
            array_to_string(v_turnos, ', ')
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF p_dia_origem = p_dia_destino AND p_turno_origem = p_turno_destino THEN
        RAISE EXCEPTION 'Origem e destino são o mesmo dia/turno (% %).',
            p_dia_origem, p_turno_origem
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT array_agg(id_escala)
      INTO v_movendo
      FROM Escala
     WHERE id_residente = p_id_residente
       AND dia_semana   = p_dia_origem
       AND turno        = p_turno_origem;

    IF v_movendo IS NULL THEN
        RAISE NOTICE 'Residente % não tem plantão em % %; nada a fazer.',
            p_id_residente, p_dia_origem, p_turno_origem;
        RETURN;
    END IF;

    -- Mais de um plantão saindo para o mesmo destino colidiria entre si.
    IF array_length(v_movendo, 1) > 1 THEN
        RAISE EXCEPTION
            'Residente % tem % plantões em % %; movê-los para % % deixaria mais de um plantão no mesmo turno.',
            p_id_residente, array_length(v_movendo, 1),
            p_dia_origem, p_turno_origem, p_dia_destino, p_turno_destino
            USING ERRCODE = 'unique_violation';
    END IF;

    SELECT COUNT(*)
      INTO v_ja_ocupado
      FROM Escala
     WHERE id_residente = p_id_residente
       AND dia_semana   = p_dia_destino
       AND turno        = p_turno_destino
       AND NOT (id_escala = ANY(v_movendo));

    IF v_ja_ocupado > 0 THEN
        RAISE EXCEPTION
            'Residente % já tem plantão em % %.',
            p_id_residente, p_dia_destino, p_turno_destino
            USING ERRCODE = 'unique_violation';
    END IF;

    UPDATE Escala
       SET dia_semana = p_dia_destino,
           turno      = p_turno_destino,
           versao     = versao + 1
     WHERE id_escala = ANY(v_movendo);

    p_escalas_movidas := array_length(v_movendo, 1);

    RAISE NOTICE 'Residente %: % plantão(ões) movido(s) de % % para % %.',
        p_id_residente, p_escalas_movidas,
        p_dia_origem, p_turno_origem, p_dia_destino, p_turno_destino;
END;
$$;

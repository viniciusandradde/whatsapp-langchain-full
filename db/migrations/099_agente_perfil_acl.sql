-- Sprint C — Agent-level ACL (2026-05-22)
--
-- Por padrão, qualquer user com permissão `agente.config` (perfil Admin
-- ou Gestor) vê/edita TODOS os agentes IA da empresa. Pra hospital com
-- N departamentos (financeiro, agendamentos, exames, etc) isso é
-- bloqueador: o "gestor do financeiro" não deveria poder mudar o prompt
-- do agente "agendamentos".
--
-- Esta mig adiciona granularidade por agente:
--   - Tabela agente_perfil(agente_id, perfil_id, can_read, can_write).
--   - Política default: se NENHUM perfil_acesso está em agente_perfil
--     pra um agente, qualquer perfil com `agente.config` continua tendo
--     acesso (compat retroativo). Quando admin adiciona a 1ª linha,
--     vira whitelist estrito.
--   - Helper `user_can_access_agente(user_id, empresa_id, agente_id, mode)`
--     centraliza a lógica.
--
-- Compatibilidade: mig é aditiva. Endpoints existentes continuam usando
-- `require_permission('agente.config')` no nível de empresa. O novo
-- `require_agente_access(slug, 'read'|'write')` se aplica APÓS a perm
-- de empresa.

CREATE TABLE IF NOT EXISTS agente_perfil (
    agente_id  BIGINT  NOT NULL REFERENCES agente_ia(id)     ON DELETE CASCADE,
    perfil_id  BIGINT  NOT NULL REFERENCES perfil_acesso(id) ON DELETE CASCADE,
    can_read   BOOLEAN NOT NULL DEFAULT TRUE,
    can_write  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agente_id, perfil_id)
);

CREATE INDEX IF NOT EXISTS idx_agente_perfil_perfil
    ON agente_perfil (perfil_id);

COMMENT ON TABLE agente_perfil IS
    'Sprint C — ACL por agente. Se vazia pra um agente_id, perm '
    'agente.config dá acesso total (compat). Se >=1 row, vira whitelist.';

COMMENT ON COLUMN agente_perfil.can_read IS
    'Permite GET /api/v1/agentes/{slug} + listar em GET /api/v1/agentes';
COMMENT ON COLUMN agente_perfil.can_write IS
    'Permite PUT /api/v1/agentes/{slug} (mudar prompt, modelo, tools). '
    'POST/DELETE/set-default são write-level no agente.';

-- Helper SQL: checa se user pode acessar um agente.
-- Lógica:
--  1. Superadmin (membership.is_superadmin) → sempre TRUE
--  2. Sem rows em agente_perfil pra esse agente → TRUE (compat retroativo)
--  3. User tem perfil que está em agente_perfil com can_<mode> = TRUE → TRUE
--  4. Caso contrário → FALSE
CREATE OR REPLACE FUNCTION user_can_access_agente(
    p_user_id    TEXT,
    p_empresa_id BIGINT,
    p_agente_id  BIGINT,
    p_mode       TEXT   -- 'read' | 'write'
) RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    is_superadmin BOOLEAN;
    has_acl_row   BOOLEAN;
    has_access    BOOLEAN;
BEGIN
    IF p_mode NOT IN ('read', 'write') THEN
        RAISE EXCEPTION 'modo inválido: %', p_mode;
    END IF;

    -- 1) Superadmin sempre passa (mesmo critério do dependencies.py)
    SELECT COALESCE(u.is_superadmin, false)
      INTO is_superadmin
      FROM auth."user" u
     WHERE u.id = p_user_id;

    IF is_superadmin THEN
        RETURN TRUE;
    END IF;

    -- 2) Se agente não tem nenhuma row em agente_perfil → modo compat
    SELECT EXISTS (
        SELECT 1 FROM agente_perfil WHERE agente_id = p_agente_id
    ) INTO has_acl_row;

    IF NOT has_acl_row THEN
        RETURN TRUE;  -- back-compat: sem ACL configurada, perm de empresa basta
    END IF;

    -- 3) Procura intersection: perfis do user × perfis com can_<mode>
    IF p_mode = 'read' THEN
        SELECT EXISTS (
            SELECT 1
              FROM usuario_perfil up
              JOIN agente_perfil ap ON ap.perfil_id = up.perfil_id
             WHERE up.user_id = p_user_id
               AND up.empresa_id = p_empresa_id
               AND ap.agente_id = p_agente_id
               AND ap.can_read = TRUE
        ) INTO has_access;
    ELSE  -- write
        SELECT EXISTS (
            SELECT 1
              FROM usuario_perfil up
              JOIN agente_perfil ap ON ap.perfil_id = up.perfil_id
             WHERE up.user_id = p_user_id
               AND up.empresa_id = p_empresa_id
               AND ap.agente_id = p_agente_id
               AND ap.can_write = TRUE
        ) INTO has_access;
    END IF;

    RETURN COALESCE(has_access, FALSE);
END;
$$;

COMMENT ON FUNCTION user_can_access_agente(TEXT, BIGINT, BIGINT, TEXT) IS
    'Sprint C — verifica ACL agente_perfil. Retorna TRUE pra superadmin, '
    'TRUE pra agentes sem ACL configurada (compat), FALSE pra demais '
    'casos sem perfil autorizado.';

-- Audit view: lista agentes com ACL ativa (whitelist) vs agentes em compat
CREATE OR REPLACE VIEW agente_acl_status AS
SELECT
    a.empresa_id,
    a.id           AS agente_id,
    a.slug,
    a.nome,
    COUNT(ap.perfil_id) AS perfis_autorizados,
    CASE
        WHEN COUNT(ap.perfil_id) = 0 THEN 'compat (sem ACL — perm empresa basta)'
        ELSE 'whitelist (' || COUNT(ap.perfil_id) || ' perfil/perfis)'
    END AS status
FROM agente_ia a
LEFT JOIN agente_perfil ap ON ap.agente_id = a.id
GROUP BY a.empresa_id, a.id, a.slug, a.nome
ORDER BY a.empresa_id, a.nome;

COMMENT ON VIEW agente_acl_status IS
    'Audit Sprint C: mostra quais agentes têm ACL configurada vs estão '
    'em modo compat. Esperado em prod com hospital: agentes sensíveis '
    '(financeiro, agendamentos, lgpd) em whitelist.';

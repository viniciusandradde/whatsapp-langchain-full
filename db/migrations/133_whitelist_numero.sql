-- Whitelist de números — bypass total da IA por número (escopo: empresa).
--
-- Números cadastrados aqui NÃO recebem nenhuma resposta automática do worker
-- (sem workflow/menu/agente/typing/transcrição) — mesmo comportamento do gate
-- de modo manual (mig 132), porém por número e valendo pra TODAS as conexões
-- da empresa. Caso de uso: contatos pessoais do dono (mãe/pai/esposa) que
-- chamam no número comercial. As mensagens continuam registradas normalmente
-- (atendimento criado no webhook, timeline/fila humana intactas).
--
-- Nota: `telefone` é gravado E.164 normalizado (+5511...). A equivalência do
-- nono dígito BR (+55 DDD 9XXXXXXXX ↔ +55 DDD XXXXXXXX) resolve no LOOKUP
-- (worker gera as variantes), não na gravação — por isso duas grafias do
-- mesmo número podem coexistir como rows distintas (inócuo pro gate).

CREATE TABLE IF NOT EXISTS whitelist_numero (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    telefone TEXT NOT NULL,          -- E.164 normalizado (+5511...)
    nome TEXT,                       -- apelido livre, ex: "Mãe"
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- também materializa o índice btree (empresa_id, telefone) usado pelo gate
    UNIQUE (empresa_id, telefone)
);

-- RLS uniforme (Sprint A.2 — bloco canônico).
ALTER TABLE whitelist_numero ENABLE ROW LEVEL SECURITY;
ALTER TABLE whitelist_numero FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON whitelist_numero;
CREATE POLICY tenant_isolation ON whitelist_numero
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

-- Perm RBAC: CRUD da whitelist (Admin/Gestor only, mesmo racional de tag.manage).
INSERT INTO permissao (codigo, descricao, modulo)
VALUES ('whitelist.manage',
        'CRUD da whitelist de números com IA desativada',
        'whitelist')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, 'whitelist.manage'
  FROM perfil_acesso pa
 WHERE pa.is_system = TRUE AND pa.nome IN ('Admin', 'Gestor')
ON CONFLICT DO NOTHING;

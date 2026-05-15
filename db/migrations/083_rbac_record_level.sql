-- Mig 083 — Record-level access control via permissões `.own` / `.all`
--
-- Sprint Governança RBAC enterprise. Adiciona variantes `.own` / `.all`
-- pra permissões cuja semântica de escopo importa (cliente, atendimento).
--
-- Convenção:
--   <modulo>.<acao>      → legacy, equivale a `.all` (compat)
--   <modulo>.<acao>.all  → toda empresa (admin/gestor)
--   <modulo>.<acao>.own  → escopo do user (depto vinculado em
--                          usuario_departamento). Quando o user não
--                          tem nenhum depto vinculado, `.own` retorna
--                          conjunto vazio (zero records visíveis).
--
-- O catálogo é sincronizado via shared/permissoes.py::sync_catalogo()
-- no boot — esta migration apenas garante que existem mesmo se o sync
-- não rodar (ex: cluster sem hot reload). O backend é a fonte da verdade.

-- Insere as 12 perms record-level. O sync no boot vai garantir descricao
-- atualizada via ON CONFLICT.
INSERT INTO permissao (codigo, descricao, modulo)
VALUES
    ('cliente.read.all',       'Ver TODOS os clientes da empresa',                'cliente'),
    ('cliente.read.own',       'Ver clientes vinculados aos departamentos do user', 'cliente'),
    ('cliente.write.all',      'Criar/editar QUALQUER cliente da empresa',         'cliente'),
    ('cliente.write.own',      'Criar/editar clientes do depto do user',           'cliente'),
    ('atendimento.read.all',   'Ver TODOS os atendimentos da empresa',             'atendimento'),
    ('atendimento.read.own',   'Ver atendimentos do user OU do depto dele',        'atendimento'),
    ('atendimento.write.all',  'Responder em qualquer atendimento',                'atendimento'),
    ('atendimento.write.own',  'Responder só nos atendimentos do depto do user',   'atendimento'),
    ('atendimento.transfer.all','Transferir qualquer atendimento',                 'atendimento'),
    ('atendimento.transfer.own','Transferir só do depto do user',                  'atendimento'),
    ('atendimento.close.all',  'Fechar qualquer atendimento',                      'atendimento'),
    ('atendimento.close.own',  'Fechar só do depto do user',                       'atendimento')
ON CONFLICT (codigo) DO NOTHING;

-- Atualiza perfis system existentes pra ganharem as novas perms.
-- Admin: ganha `.all` em tudo. Gestor: também `.all` (gestão da operação
-- precisa ver tudo). Operador: `.own` (escopo do depto).
--
-- Match flexível: se a empresa NÃO tem perfil "Operador" cadastrado
-- (ex: tenant antigo só com Admin), o UPDATE vira no-op e o seed
-- automático rodará no próximo boot via seed_default_perfis().

DO $$
DECLARE
    perm_id BIGINT;
    perfil_record RECORD;
BEGIN
    -- Para cada perfil_acesso existente, adiciona as perms novas
    -- conforme o nome (system perfis: Admin, Gestor, Operador, Leitura).
    FOR perfil_record IN
        SELECT id, empresa_id, nome FROM perfil_acesso WHERE is_system = TRUE
    LOOP
        IF perfil_record.nome IN ('Admin', 'Gestor') THEN
            -- Admin/Gestor: vê tudo
            FOR perm_id IN
                SELECT id FROM permissao WHERE codigo IN (
                    'cliente.read.all', 'cliente.write.all',
                    'atendimento.read.all', 'atendimento.write.all',
                    'atendimento.transfer.all', 'atendimento.close.all'
                )
            LOOP
                INSERT INTO perfil_permissao (perfil_id, permissao_id)
                VALUES (perfil_record.id, perm_id)
                ON CONFLICT DO NOTHING;
            END LOOP;
        ELSIF perfil_record.nome = 'Operador' THEN
            -- Operador: só do próprio depto
            FOR perm_id IN
                SELECT id FROM permissao WHERE codigo IN (
                    'cliente.read.own', 'cliente.write.own',
                    'atendimento.read.own', 'atendimento.write.own',
                    'atendimento.transfer.own', 'atendimento.close.own'
                )
            LOOP
                INSERT INTO perfil_permissao (perfil_id, permissao_id)
                VALUES (perfil_record.id, perm_id)
                ON CONFLICT DO NOTHING;
            END LOOP;
        ELSIF perfil_record.nome = 'Leitura' THEN
            -- Leitura: read.all (read-only intencional, vê tudo)
            FOR perm_id IN
                SELECT id FROM permissao WHERE codigo IN (
                    'cliente.read.all', 'atendimento.read.all'
                )
            LOOP
                INSERT INTO perfil_permissao (perfil_id, permissao_id)
                VALUES (perfil_record.id, perm_id)
                ON CONFLICT DO NOTHING;
            END LOOP;
        END IF;
    END LOOP;
END $$;

-- Sprint Atendimento UX — Permissões novas pra abas / tags / notas internas.
--
-- 4 perms novas:
--   atendimento.aba.manage     → CRUD nas próprias abas (Operador+)
--   atendimento.tag.aplicar    → aplicar/remover tags em atendimento (Operador+)
--   atendimento.nota_interna.criar → escrever notas internas (Operador+)
--   tag.manage                 → CRUD de tags da empresa (Admin/Gestor only)
--
-- Sem variantes `.own/.all` — abas são sempre do próprio user (RBAC
-- enforced no SQL pelas FKs/WHERE), tags são da empresa (single scope).

INSERT INTO permissao (codigo, descricao, modulo)
VALUES
    ('atendimento.aba.manage',
        'Criar/editar/deletar próprias abas no painel de atendimento',
        'atendimento'),
    ('atendimento.tag.aplicar',
        'Aplicar/remover tags em atendimentos visíveis',
        'atendimento'),
    ('atendimento.nota_interna.criar',
        'Criar notas internas (privadas) na timeline do atendimento',
        'atendimento'),
    ('tag.manage',
        'CRUD de tags da empresa (criar/editar/deletar)',
        'tag')
ON CONFLICT (codigo) DO NOTHING;

-- Admin + Gestor: ganham todas 4 (inclusive tag.manage pra cadastrar).
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, p.codigo
  FROM perfil_acesso pa
 CROSS JOIN permissao p
 WHERE pa.is_system = TRUE
   AND pa.nome IN ('Admin', 'Gestor')
   AND p.codigo IN (
       'atendimento.aba.manage',
       'atendimento.tag.aplicar',
       'atendimento.nota_interna.criar',
       'tag.manage'
   )
ON CONFLICT DO NOTHING;

-- Operador: ganha as 3 operacionais (NÃO tag.manage — só admin cadastra tags).
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, p.codigo
  FROM perfil_acesso pa
 CROSS JOIN permissao p
 WHERE pa.is_system = TRUE
   AND pa.nome = 'Operador'
   AND p.codigo IN (
       'atendimento.aba.manage',
       'atendimento.tag.aplicar',
       'atendimento.nota_interna.criar'
   )
ON CONFLICT DO NOTHING;

-- Leitura: nenhuma (só consome, não modifica).

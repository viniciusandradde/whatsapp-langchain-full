-- Reescreve a descrição dos perfis de sistema em linguagem de produto.
--
-- O seed em `shared/permissoes.py::PERFIS_SYSTEM` foi corrigido, mas ele só
-- roda na criação da empresa (idempotente por UNIQUE) — empresa que já existe
-- fica com o texto antigo gravado. Daí a migration.
--
-- O que estava na tela do cliente, em /settings/perfis:
--   Admin   → "Acesso total — equivalente ao role 'admin' legacy."
--   Leitura → "Read-only — pra auditoria/visualização sem mutação."
--
-- "role legacy" é dívida da migração de RBAC, não descrição de perfil, e
-- "read-only"/"mutação" é vocabulário de banco de dados.
--
-- Só toca em perfil de sistema: perfil personalizado tem descrição escrita
-- pelo cliente e não deve ser sobrescrito.

UPDATE perfil_acesso
   SET descricao = 'Acesso total à empresa, inclusive cobrança e perfis de acesso.'
 WHERE is_system AND nome = 'Admin';

UPDATE perfil_acesso
   SET descricao = 'Gerencia a operação e a equipe. Não mexe em cobrança nem em perfis de acesso.'
 WHERE is_system AND nome = 'Gestor';

UPDATE perfil_acesso
   SET descricao = 'Atende clientes pelo WhatsApp. Sem permissões de gestão.'
 WHERE is_system AND nome = 'Operador';

UPDATE perfil_acesso
   SET descricao = 'Só leitura. Vê tudo da empresa e não altera nada — para auditoria e acompanhamento.'
 WHERE is_system AND nome = 'Leitura';

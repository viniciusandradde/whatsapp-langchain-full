-- ADR-002, Etapa 1 — `conexao.read` deixa de ser órfã, e o Operador ganha.
--
-- Até aqui `GET /api/conexoes` não tinha portão nenhum: bastava ser membro da
-- empresa. A Etapa 1 gateia essas leituras em `conexao.read`, que existe no
-- catálogo desde a mig 083 mas nunca foi exigida por rota alguma (órfã).
--
-- O Operador PRECISA dessa leitura: o modal "Nova conversa" do painel
-- (`frontend/src/app/api/nova-conversa/opcoes/route.ts`) chama
-- `GET /api/conexoes` para descobrir o provider da conexão padrão — é ele que
-- decide se a primeira mensagem é texto livre ou template HSM. Sem o grant, a
-- Etapa 1 TIRARIA acesso de quem hoje usa o sistema, que é exatamente o risco
-- que o ADR manda evitar.
--
-- Isto NÃO alarga o que o operador enxerga: hoje ele já lê a lista inteira sem
-- portão. Restringir de verdade quais conexões cada usuário vê é a Etapa 4
-- (escopo por conexão, allow-list sobre `usuario_conexao`).
--
-- Só concede, nunca remove. `ON CONFLICT DO NOTHING` para ser idempotente e
-- para não mexer em perfil que o cliente já editou à mão.

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, 'conexao.read'
  FROM perfil_acesso pa
 WHERE pa.is_system = TRUE
   AND pa.nome = 'Operador'
ON CONFLICT DO NOTHING;

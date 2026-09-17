-- ADR-002, Etapa 4 — escopo de atendimento por conexão (allow-list, opt-in
-- por empresa). Decisão 6.
--
-- Reusa `usuario_conexao` (mig 111), que hoje é só "conexão padrão de
-- envio", também como allow-list de VISIBILIDADE — a mesma tabela, o mesmo
-- vínculo. Fail-closed por desenho (rejeitamos a deny-list do ZigChat, que é
-- fail-open): sem opt-in, comportamento idêntico a hoje, ninguém filtrado.
--
-- Só afeta escopo `.own` de `atendimento.read` — mesmo padrão do escopo por
-- departamento (`scope_departamento_ids` em shared/atendimento.py e
-- shared/historico.py): Gestor/Admin com `.all` continuam vendo a empresa
-- inteira, sem filtro de conexão nenhum. Decisão tomada com o dono
-- (2026-09-17): eixo dependente do departamento, não independente.
--
-- NÃO cria a permissão `atendimento.scope.conexao` cogitada no texto
-- original da Decisão 6. `atendimento.scope.departamento` já existe no
-- catálogo com essa forma (permissão só documentando o conceito, nunca
-- checada em código — a descrição dela já diz "deprecated, use .own") e o
-- escopo de departamento de fato NÃO checa essa permissão: deriva de
-- `atendimento.read.own` vs `.all`. Repetir o padrão descontinuado aqui
-- readicionaria outra permissão do catálogo que nenhuma rota exige — o
-- oposto do que as Etapas 1-2 vieram consertar.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS conexao_scope_ativo BOOLEAN NOT NULL DEFAULT FALSE;

-- `contexto`: a mesma conexão pode ser invisível na fila e visível no
-- histórico (ou o inverso) — um booleano seria grosseiro demais (lição do
-- ZigChat, docs/zigchat/controle-de-acesso.md). Default cobre os dois
-- contextos: rows criadas ANTES desta feature (só "conexão padrão de
-- envio") não ficam misteriosamente invisíveis quando a empresa liga o
-- opt-in — o admin restringe de propósito depois, não fica restrito por
-- acidente de migração.
ALTER TABLE usuario_conexao
    ADD COLUMN IF NOT EXISTS contexto TEXT[] NOT NULL DEFAULT '{fila,historico}';

-- Auditoria — por que esta atribuição existe. Ideia do ZigChat (`motivo` no
-- registro de restrição); aqui é allow-list, então documenta por que o
-- usuário TEM a conexão, não por que foi negada. Custa uma coluna.
ALTER TABLE usuario_conexao
    ADD COLUMN IF NOT EXISTS motivo TEXT;

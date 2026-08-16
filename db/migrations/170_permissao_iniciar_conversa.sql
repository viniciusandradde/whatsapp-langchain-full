-- 170 — Permissão `atendimento.iniciar` (conversa ativa 1:1).
--
-- Motivo: até aqui o operador só RESPONDE — atendimento nasce exclusivamente
-- de mensagem inbound no webhook. A feature "Nova conversa" deixa o operador
-- iniciar contato com qualquer número pelo painel (paridade ZigChat:
-- criarAlterarAtendimento com cliente+conexão+mensagem/template).
--
-- Política decidida pelo dono (2026-08-15): TODO operador que responde também
-- pode iniciar — grants copiados de `atendimento.write.all` (não de
-- `disparador.disparar`, que restringiria a Admin/Gestor).
--
-- IMPORTANTE — divisão de responsabilidade (mesma da mig 142):
--   * Fonte de verdade do catálogo é `shared/permissoes.py::CATALOGO`
--     (sincroniza no startup) + perfis default para empresa NOVA.
--   * Esta migration existe pros perfis que JÁ EXISTEM em produção.
--
-- O INSERT em `permissao` é redundante com o sync, mas necessário aqui: sem a
-- linha, a FK de `perfil_permissao` recusaria os grants nesta transação.

INSERT INTO permissao (codigo, descricao, modulo)
VALUES (
    'atendimento.iniciar',
    'Iniciar conversa ativa com um número (cria atendimento outbound)',
    'atendimento'
)
ON CONFLICT (codigo) DO NOTHING;

-- Qualquer variante do write conta como "operador que responde": o perfil
-- Operador default usa `.write.own`, e copiar só de `.write.all` deixaria
-- justamente os atendentes de fora.
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT DISTINCT perfil_id, 'atendimento.iniciar'
  FROM perfil_permissao
 WHERE permissao_codigo IN
       ('atendimento.write', 'atendimento.write.all', 'atendimento.write.own')
ON CONFLICT (perfil_id, permissao_codigo) DO NOTHING;

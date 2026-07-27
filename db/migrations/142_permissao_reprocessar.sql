-- 142 — Permissão `atendimento.reprocessar`.
--
-- Motivo: quando a IA pula uma mensagem (conexão em modo manual, número na
-- whitelist) ou o processamento falha, a mensagem fica registrada e ninguém
-- responde ao cliente. Recuperar exigia UPDATE manual no Postgres — reset de
-- status/attempts/response/error/lease_until — o que depende de alguém com
-- acesso ao banco.
--
-- Caso real que motivou (2026-07-27): mensagem 2929 do atendimento 499, uma
-- ex-aluna escrevendo pro agente do Luis Fernando enquanto a conexão estava
-- em manual. Ficou `done` com `[modo manual — IA desligada nesta conexão]`.
--
-- Poder equivalente a `atendimento.reset_thread` (cirurgia na conversa, e
-- reprocessar envia WhatsApp real + gasta token), então os grants são COPIADOS
-- dela em vez de fixados por ID.
--
-- IMPORTANTE — divisão de responsabilidade:
--   * A FONTE DE VERDADE do catálogo é `shared/permissoes.py::CATALOGO`, que o
--     app sincroniza pra tabela `permissao` no startup. A permissão foi
--     adicionada lá, e o perfil Admin a recebe automaticamente (usa "all");
--     Gestor foi incluído explicitamente, espelhando o reset_thread.
--   * `seed_default_perfis` só roda pra empresa NOVA. Esta migration existe
--     pros perfis que JÁ EXISTEM em produção — sem ela, quem hoje tem
--     reset_thread não ganharia a permissão nova e o botão daria 403.
--
-- O INSERT em `permissao` abaixo é redundante com o sync, mas necessário aqui:
-- sem a linha, a FK de `perfil_permissao` recusaria os grants nesta transação.

INSERT INTO permissao (codigo, descricao, modulo)
VALUES (
    'atendimento.reprocessar',
    'Reprocessar mensagem que a IA pulou ou que falhou (reenvia ao cliente)',
    'atendimento'
)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT perfil_id, 'atendimento.reprocessar'
  FROM perfil_permissao
 WHERE permissao_codigo = 'atendimento.reset_thread'
ON CONFLICT (perfil_id, permissao_codigo) DO NOTHING;

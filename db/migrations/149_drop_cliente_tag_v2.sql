-- Remove `cliente_tag_v2`, tabela orfa desde que nasceu.
--
-- Havia DUAS tabelas de tag de cliente convivendo, e isso quase virou bug: o
-- filtro das abas (mig anterior, `shared/aba.py`) foi escrito sobre a v2 e teria
-- dado pasta permanentemente vazia, sem erro nenhum na tela. So apareceu ao
-- validar contra dados de producao.
--
--   cliente_tag     (cliente_id, tag TEXT)  -> 36 linhas, VIVA
--                                              `POST /api/clientes/{id}/tags`
--                                              grava; `Cliente.tags` le
--   cliente_tag_v2  (cliente_id, tag_id)    ->  5 linhas, ninguem escreve
--
-- Verificacoes feitas antes de apagar (2026-07-30, contra producao):
--   1. Codigo: nenhum SQL toca a v2 — so comentarios e docstrings.
--      `delete_tag` menciona CASCADE mas apaga apenas de `tag`.
--   2. Dados: TODOS os 5 pares (cliente, tag) da v2 ja existem em
--      `cliente_tag`. Nada se perde. Eram: cliente 2 com `handoff` e
--      `SEO VSA Tecnologia`; clientes 26, 45 e 46 com `stress-test`.
--   3. Dependencias: nenhuma FK aponta pra ela, nenhuma view a cita, nenhuma
--      policy RLS.
--   4. Atividade: `pg_stat_user_tables` acusa 0 insert, 0 update, 0 delete.
--
-- Apagar em vez de deixar: tabela morta com nome parecido com a viva e uma
-- migration a mais nas costas e um convite a errar de novo. A proxima pessoa
-- que procurar "tag de cliente" vai achar uma so.

DROP TABLE IF EXISTS cliente_tag_v2;

COMMENT ON TABLE cliente_tag IS
    'Tags do CLIENTE (texto livre). Unica tabela de tag de cliente desde a mig '
    '149, que removeu a `cliente_tag_v2` orfa. Alimenta as abas do painel '
    '(aba.filtro->cliente_tags) e a ficha do cliente.';

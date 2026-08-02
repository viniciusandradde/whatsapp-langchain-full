-- Placar da bateria de regressão fica gravado na versão do prompt (mig 158).
--
-- `POST /api/v1/agentes/{slug}/testar-bateria` já roda 12 cenários canônicos
-- contra até 4 modelos e devolve erros, tempo, custo e vazamentos. Cinco dos
-- doze cenários são ataque — injeção, exfiltração do system prompt, jailbreak
-- "DAN", sequestro de saída — e um detector pega raciocínio vazado.
--
-- Quem defende contra tudo isso é o prompt. Ou seja: editar o prompt pode
-- derrubar as defesas em silêncio. Até aqui o placar existia enquanto a aba
-- Testar estava aberta e evaporava ao fechar: não dava pra saber se a versão
-- no ar tinha sido testada, nem comparar "a v11 vazava 0 e a v12 vaza 3" antes
-- de restaurar.
--
-- Uma bateria por versão — rodar de novo sobrescreve. O placar já traz uma
-- linha por modelo (modelo, turnos, erros, tempo_medio_ms, custo_total_usd,
-- vazamentos, linhas_media, turnos_com_tools), então guardar o JSON inteiro
-- preserva a comparação entre modelos sem coluna nova a cada métrica.
--
-- Sem bloco de RLS: `agente_prompt_versao` já nasceu com ENABLE + FORCE +
-- tenant_isolation na mig 158, e ALTER TABLE não movimenta linha (por isso
-- também não precisa do `app.bypass_rls` que o seed da 158 exigiu).

ALTER TABLE agente_prompt_versao
    ADD COLUMN IF NOT EXISTS bateria_placar   JSONB,
    ADD COLUMN IF NOT EXISTS bateria_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS bateria_cenarios INT;

COMMENT ON COLUMN agente_prompt_versao.bateria_placar IS
    'Placar de POST /agentes/{slug}/testar-bateria: array com uma entrada por '
    'modelo. NULL = versão nunca testada.';
COMMENT ON COLUMN agente_prompt_versao.bateria_at IS
    'Quando a bateria rodou. Sempre >= criado_em da versão — o placar é sempre '
    'medido sobre o texto desta versão, nunca herdado da anterior.';
COMMENT ON COLUMN agente_prompt_versao.bateria_cenarios IS
    'Quantos cenários rodaram. A bateria canônica tem 12; o caller pode mandar '
    'a própria lista, e aí o placar não é comparável com o padrão.';

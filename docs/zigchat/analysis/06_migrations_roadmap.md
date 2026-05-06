# 06 — Migrations roadmap pra paridade ZigChat

> Sequência sugerida de migrations a partir de **041** pra reduzir o gap entre nosso modelo e o ZigChat.
> Cada migration é independente (pode ser aplicada isoladamente). Prioridade por valor de produto, não por dificuldade.

## Estratégia geral

- **ALTER TABLE** > nova migration toda — adicionar colunas opcionais é seguro com NULL/DEFAULT.
- **NÃO converter** boolean/string entre formatos — manter nosso `boolean` nativo (ZigChat usa `S/N` por legado).
- **NÃO copiar IDs** — usar nossas BIGSERIAL.
- **Backfill idempotente** quando relevante (UPDATE com WHERE field IS NULL).

## Mig 041 — Expandir menu_chatbot (baixo risco, alto valor UX)

```sql
ALTER TABLE menu_chatbot
  ADD COLUMN atalho TEXT,                              -- "/start" / "menu"
  ADD COLUMN solicitar_nome BOOLEAN DEFAULT FALSE,     -- pergunta nome se cliente novo
  ADD COLUMN menu_moderno BOOLEAN DEFAULT FALSE,       -- usa botões WhatsApp em vez de "1, 2, 3"
  ADD COLUMN auto_navegar_para_item_id BIGINT REFERENCES menu_item(id) ON DELETE SET NULL,
  ADD COLUMN arquivo_url TEXT,                         -- anexo na boas-vindas
  ADD COLUMN qtde_acesso BIGINT DEFAULT 0;             -- counter analytics

-- Wizard de coleta (3 passos sequenciais)
ALTER TABLE menu_chatbot
  ADD COLUMN mensagem_coleta TEXT,                     -- pergunta de coleta
  ADD COLUMN mensagem_confirmar_coleta TEXT,           -- "confirme: ..."
  ADD COLUMN mensagem_final_coleta TEXT;               -- depois de confirmar
```

## Mig 042 — Expandir menu_item com 6 ações novas (alto valor)

```sql
-- Novos campos (compatível: NULL pra MVP)
ALTER TABLE menu_item
  ADD COLUMN comando TEXT,                             -- alias texto da escolha (ex: "vendas")
  ADD COLUMN acao_atendente_id TEXT,                   -- transferir pra usuário específico
  ADD COLUMN acao_modelo_mensagem_id BIGINT REFERENCES modelo_mensagem(id),
  ADD COLUMN webhook_url TEXT,                         -- chamar URL externa
  ADD COLUMN link_url TEXT,                            -- enviar link
  ADD COLUMN nota_min INT,                             -- pesquisa CSAT (escala)
  ADD COLUMN nota_max INT,
  ADD COLUMN nota_pergunta TEXT,
  ADD COLUMN grupo TEXT;                               -- agrupador visual

-- Expandir CHECK acao_tipo
ALTER TABLE menu_item DROP CONSTRAINT menu_item_acao_tipo_check;
ALTER TABLE menu_item ADD CONSTRAINT menu_item_acao_tipo_check CHECK (
  acao_tipo IN (
    -- MVP
    'submenu', 'transferir_dep', 'chamar_agente', 'enviar_msg', 'fechar',
    -- Novos
    'transferir_atendente', 'enviar_template', 'chamar_webhook',
    'enviar_link', 'pesquisa_csat', 'mudar_manual', 'setar_nome'
  )
);
```

## Mig 043 — Expandir agente_ia (governança custo + memória configurável)

```sql
ALTER TABLE agente_ia
  -- Quando estoura limite custo, redireciona pro menu específico
  ADD COLUMN acao_limite_menu_id BIGINT REFERENCES menu_chatbot(id) ON DELETE SET NULL,
  -- Memória configurável (sobrescreve LangGraph store global)
  ADD COLUMN tipo_memoria TEXT DEFAULT 'window'
    CHECK (tipo_memoria IN ('buffer', 'window', 'summary', 'none')),
  ADD COLUMN janela_memoria INT,                       -- N mensagens anteriores
  ADD COLUMN timeout_minutos INT;                      -- TTL conversa idle

-- Separar modelo em provedor + nome (preserva coluna antiga via deprecated)
ALTER TABLE agente_ia
  ADD COLUMN modelo_provedor TEXT,                     -- openai/anthropic/google/openrouter
  ADD COLUMN modelo_nome TEXT;                         -- gpt-4o-mini etc

-- Backfill: split do modelo único
UPDATE agente_ia
   SET modelo_provedor = SPLIT_PART(modelo, '/', 1),
       modelo_nome = SPLIT_PART(modelo, '/', 2)
 WHERE modelo IS NOT NULL AND POSITION('/' IN modelo) > 0;

-- Deprecar modelo único depois de UI/loader migrarem
COMMENT ON COLUMN agente_ia.modelo IS 'DEPRECATED — use modelo_provedor + modelo_nome (mig 043). Removido em mig 050+.';
```

## Mig 044 — Catálogo `modelo_llm` (custos + governança)

```sql
CREATE TABLE modelo_llm (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa(id) ON DELETE CASCADE,  -- NULL = global
  provedor TEXT NOT NULL,                  -- openai/anthropic/google/openrouter/...
  nome TEXT NOT NULL,                      -- gpt-4o-mini
  descricao TEXT,
  tipo TEXT NOT NULL                       -- chat/embedding/midia/audio
    CHECK (tipo IN ('chat','embedding','midia','audio')),
  custo_input_mtok NUMERIC(10,4),         -- USD por 1M tokens input
  custo_output_mtok NUMERIC(10,4),
  janela_contexto INT,                    -- max tokens contexto
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (COALESCE(empresa_id, 0), provedor, nome)
);

-- Seed mínimo (pode ser ampliado por empresa via UI)
INSERT INTO modelo_llm (empresa_id, provedor, nome, tipo, custo_input_mtok, custo_output_mtok, janela_contexto)
VALUES
  (NULL, 'openai', 'gpt-4o-mini', 'chat', 0.15, 0.60, 128000),
  (NULL, 'openai', 'gpt-4o', 'chat', 2.50, 10.00, 128000),
  (NULL, 'google', 'gemini-2.5-flash', 'chat', 0.075, 0.30, 1000000),
  (NULL, 'anthropic', 'claude-haiku-4-5', 'chat', 1.00, 5.00, 200000),
  (NULL, 'anthropic', 'claude-sonnet-4-6', 'chat', 3.00, 15.00, 200000),
  (NULL, 'openai', 'whisper-1', 'audio', 0, 6.00, NULL),
  (NULL, 'openai', 'text-embedding-3-small', 'embedding', 0.02, 0, 8191)
ON CONFLICT DO NOTHING;
```

## Mig 045 — Coluna `nanoid` em histórico (paridade ZigChat)

```sql
-- ZigChat usa nanoid em logs/histórico — facilita anti-enum/anti-guess.
-- Mantemos BIGSERIAL como PK (performance index), só adicionamos nanoid pra exposição externa.
ALTER TABLE atendimento_menu_historico
  ADD COLUMN nanoid TEXT,
  ADD COLUMN resposta TEXT;                            -- texto cru do cliente
CREATE UNIQUE INDEX uq_atendimento_menu_historico_nanoid
  ON atendimento_menu_historico (nanoid)
  WHERE nanoid IS NOT NULL;

-- Backfill: gera nanoid pra rows existentes (manual via app)
```

## Não precisa migrar (ZigChat tem mas é redundante pro nosso)

- `qtde_resposta_invalida` no Atendimento — temos audit_log já.
- `boolean as string "S"/"N"` — herança ZigChat. Manter nosso `BOOLEAN` nativo.
- `descricao` como nome de menu — confuso, manter `nome`.
- `Float` como BIGINT — ZigChat usa por convenção GraphQL. Continuar `BIGINT`/`Int`.

## Sequência ideal

1. **Sub-fase B** (atual MVP) — shippar, validar em prod, capturar UX feedback.
2. **Mig 041 + UI** — atalho + solicitar_nome + auto_navegar (UX wins primeiro).
3. **Mig 042 + worker** — 7 ações novas (transferir_atendente é a mais pedida).
4. **Mig 043 + 044** — governança custo via catalogo modelo_llm + acao_limite_menu_id.
5. **Mig 045** — nanoid em histórico (paridade observabilidade).

Cada uma é ~1 sprint. Total: ~5 sprints pra paridade core.
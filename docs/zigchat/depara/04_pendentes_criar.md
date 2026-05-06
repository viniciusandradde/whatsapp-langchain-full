# 04 — Pendentes (❌) — entidades ZigChat sem equivalente Nexus

[← Voltar ao índice](./README.md)

> Entidades que ZigChat tem e Nexus não. Cada seção tem SQL CREATE pronto + análise de prioridade.
> Total: ~22 entidades.

## Críticas (priorizar)

### 1. McpServer — Integração MCP

**Por quê:** já mapeado no roadmap (Fase 2 do plano enterprise). Permite agente IA chamar tools de servidores MCP externos.

**Mig 042:**

```sql
CREATE TABLE mcp_server (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  descricao TEXT,
  tipo_conexao TEXT NOT NULL CHECK (tipo_conexao IN ('stdio', 'sse', 'http', 'websocket')),
  url TEXT,                         -- pra sse/http/websocket
  comando TEXT,                     -- pra stdio
  args TEXT,                        -- args do comando (JSON serialized)
  headers JSONB DEFAULT '{}',       -- headers HTTP
  status TEXT NOT NULL DEFAULT 'inactive'
    CHECK (status IN ('active', 'inactive', 'error')),
  ultimo_teste TIMESTAMPTZ,
  ultimo_erro TEXT,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_by_user_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (empresa_id, nome)
);

CREATE INDEX idx_mcp_server_empresa ON mcp_server (empresa_id) WHERE ativo;
```

**Já temos:** `agente_ia.mcp_server_ids BIGINT[]` (mig 039) — basta criar a tabela referenciada.

---

### 2. ModeloIA (catálogo de modelos LLM)

**Por quê:** governança custo + UI dropdown sabendo quais modelos existem.

**Mig 044:**

```sql
CREATE TABLE modelo_llm (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa(id) ON DELETE CASCADE,  -- NULL = global
  provedor TEXT NOT NULL,
  nome TEXT NOT NULL,
  descricao TEXT,
  tipo TEXT NOT NULL CHECK (tipo IN ('chat', 'embedding', 'midia', 'audio', 'imagem')),
  custo_input_mtok NUMERIC(10,4),
  custo_output_mtok NUMERIC(10,4),
  janela_contexto INT,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (COALESCE(empresa_id, 0), provedor, nome)
);

INSERT INTO modelo_llm (empresa_id, provedor, nome, tipo, custo_input_mtok, custo_output_mtok, janela_contexto)
VALUES
  (NULL, 'openai', 'gpt-4o-mini', 'chat', 0.15, 0.60, 128000),
  (NULL, 'openai', 'gpt-4o', 'chat', 2.50, 10.00, 128000),
  (NULL, 'google', 'gemini-2.5-flash', 'chat', 0.075, 0.30, 1000000),
  (NULL, 'google', 'gemini-2.5-pro', 'chat', 1.25, 5.00, 2000000),
  (NULL, 'anthropic', 'claude-haiku-4-5', 'chat', 1.00, 5.00, 200000),
  (NULL, 'anthropic', 'claude-sonnet-4-6', 'chat', 3.00, 15.00, 200000),
  (NULL, 'anthropic', 'claude-opus-4-7', 'chat', 15.00, 75.00, 1000000),
  (NULL, 'openai', 'whisper-1', 'audio', 0, 6.00, NULL),
  (NULL, 'openai', 'text-embedding-3-small', 'embedding', 0.02, 0, 8191),
  (NULL, 'openai', 'text-embedding-3-large', 'embedding', 0.13, 0, 8191)
ON CONFLICT DO NOTHING;
```

---

### 3. AtendimentoTransferencia

**Por quê:** auditoria + histórico de transferências (entre departamentos/atendentes/agentes).

**Mig 053:**

```sql
CREATE TABLE atendimento_transferencia (
  id BIGSERIAL PRIMARY KEY,
  atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  -- Origem
  de_user_id TEXT,                  -- atendente origem (ou NULL = bot)
  de_departamento_id BIGINT,        -- depto origem
  de_agente_slug TEXT,              -- agente origem
  -- Destino
  para_user_id TEXT,
  para_departamento_id BIGINT,
  para_agente_slug TEXT,
  -- Metadados
  motivo TEXT,
  iniciado_por_user_id TEXT,        -- quem clicou em "transferir" (ou bot)
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transferencia_atendimento
  ON atendimento_transferencia (atendimento_id, created_at DESC);
```

---

### 4. Tag (entidade própria, atualmente é só string)

**Por quê:** padronizar com cor, descrição, hook próprio. Hoje tag é só string em `cliente_tag(cliente_id, tag)`.

**Mig 052:**

```sql
CREATE TABLE tag (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  cor TEXT,                         -- hex ex: "#FF5733"
  descricao TEXT,
  hook_id BIGINT REFERENCES hook(id) ON DELETE SET NULL,  -- dispara quando tag aplicada
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_by_user_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (empresa_id, nome)
);

-- Migra cliente_tag (cliente_id, tag) → cliente_tag_v2 (cliente_id, tag_id)
CREATE TABLE cliente_tag_v2 (
  cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
  tag_id BIGINT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (cliente_id, tag_id)
);

-- Backfill: cria tag pra cada string distinta
INSERT INTO tag (empresa_id, nome)
SELECT DISTINCT c.empresa_id, ct.tag
  FROM cliente_tag ct JOIN cliente c ON c.id = ct.cliente_id
ON CONFLICT DO NOTHING;

INSERT INTO cliente_tag_v2 (cliente_id, tag_id)
SELECT ct.cliente_id, t.id
  FROM cliente_tag ct
  JOIN cliente c ON c.id = ct.cliente_id
  JOIN tag t ON t.empresa_id = c.empresa_id AND t.nome = ct.tag;

-- Manter cliente_tag legacy temporariamente; deprecar em mig futura
COMMENT ON TABLE cliente_tag IS 'DEPRECATED — usar cliente_tag_v2 + tag (mig 052).';
```

---

### 5. MenuItemArquivo (anexo no item de menu)

**Por quê:** WhatsApp permite mandar PDF/imagem junto da escolha. Hoje menu manda só texto.

**Mig 041:**

```sql
CREATE TABLE menu_item_arquivo (
  id BIGSERIAL PRIMARY KEY,
  menu_id BIGINT REFERENCES menu_chatbot(id) ON DELETE CASCADE,
  item_id BIGINT REFERENCES menu_item(id) ON DELETE CASCADE,
  arquivo_url TEXT NOT NULL,
  arquivo_nome TEXT,
  content_type TEXT,
  descricao TEXT,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (menu_id IS NOT NULL OR item_id IS NOT NULL)  -- pelo menos um
);

CREATE INDEX idx_menu_item_arquivo_menu ON menu_item_arquivo (menu_id) WHERE menu_id IS NOT NULL;
CREATE INDEX idx_menu_item_arquivo_item ON menu_item_arquivo (item_id) WHERE item_id IS NOT NULL;
```

---

### 6. UsuarioAtendimentoTimestamp (read receipts internos)

**Por quê:** mostrar pra equipe quem viu qual atendimento e quando — colaboração.

**Mig 052:**

```sql
CREATE TABLE atendimento_visualizacao (
  atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  ultima_visualizacao_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (atendimento_id, user_id)
);
```

---

### 7. Aviso + AvisoUsuario (notificações da plataforma)

**Por quê:** banner sistema (manutenção, novidades, billing pendente) com tracking de quem leu.

**Mig 055:**

```sql
CREATE TABLE aviso (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa(id) ON DELETE CASCADE,  -- NULL = global
  titulo TEXT NOT NULL,
  conteudo TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'info'
    CHECK (tipo IN ('info', 'warning', 'critical', 'feature')),
  link_url TEXT,                    -- "saiba mais"
  ativo_de TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ativo_ate TIMESTAMPTZ,
  obrigatorio BOOLEAN NOT NULL DEFAULT FALSE,  -- bloqueia uso até ler
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE aviso_usuario_leitura (
  aviso_id BIGINT NOT NULL REFERENCES aviso(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  lido_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (aviso_id, user_id)
);
```

---

## Médias (depende de necessidade comercial)

### 8. PushDevice (notificações mobile)

**Mig 054:**

```sql
CREATE TABLE push_device (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  device_token TEXT NOT NULL,
  device_type TEXT NOT NULL CHECK (device_type IN ('ios', 'android', 'web')),
  device_name TEXT,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (device_token)
);

CREATE INDEX idx_push_device_user ON push_device (user_id, empresa_id) WHERE ativo;
```

### 9. Aba (quadros custom de atendimentos)

**Por quê:** filtro nomeado (ex: "Vendas Q1", "Suporte VIP"). Estilo Trello.

**Mig 050:**

```sql
CREATE TABLE aba (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  filtro JSONB NOT NULL DEFAULT '{}',  -- {departamento_ids: [], tag_ids: [], status: [], ...}
  cor TEXT,
  ordem INT,
  user_id TEXT,                     -- NULL = aba compartilhada
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 10. Turno (escala reutilizável)

**Por quê:** horário compartilhável entre departamentos. Hoje cada depto tem seu próprio.

**Mig 049:**

```sql
CREATE TABLE turno (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,             -- "Comercial 9-18", "24x7", "Plantão noite"
  horarios JSONB NOT NULL DEFAULT '[]',  -- [{dia_semana: 1, inicio: "09:00", fim: "18:00"}, ...]
  fuso_horario TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (empresa_id, nome)
);

ALTER TABLE departamento ADD COLUMN turno_id BIGINT REFERENCES turno(id) ON DELETE SET NULL;
```

### 11. FormPadrao (formulários de coleta)

**Por quê:** lead capture, CSAT, NPS — formulários reutilizáveis.

**Mig 056:**

```sql
CREATE TABLE form_padrao (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  descricao TEXT,
  campos JSONB NOT NULL DEFAULT '[]',  -- [{nome, tipo, obrigatorio, opcoes, validacao}, ...]
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_by_user_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (empresa_id, nome)
);

CREATE TABLE form_resposta (
  id BIGSERIAL PRIMARY KEY,
  form_id BIGINT NOT NULL REFERENCES form_padrao(id) ON DELETE CASCADE,
  cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
  atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
  respostas JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 12. IAExecucaoDetalhe (telemetria LLM)

**Por quê:** hoje audit_log é genérico. Pra cada call LLM queremos: tokens in/out, latência, custo, modelo usado, ferramenta chamada.

**Mig 057:**

```sql
CREATE TABLE ia_execucao (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
  agente_ia_id BIGINT REFERENCES agente_ia(id) ON DELETE SET NULL,
  modelo_provedor TEXT NOT NULL,
  modelo_nome TEXT NOT NULL,
  -- Tokens
  tokens_input INT NOT NULL DEFAULT 0,
  tokens_output INT NOT NULL DEFAULT 0,
  tokens_cached INT NOT NULL DEFAULT 0,
  -- Custo (USD)
  custo_total NUMERIC(10,6),
  -- Latência
  duracao_ms INT,
  -- Tool calls (lista de tools chamadas nessa execução)
  tools_chamadas TEXT[],
  -- Status
  status TEXT NOT NULL CHECK (status IN ('success', 'error', 'timeout', 'rate_limit')),
  erro_msg TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ia_execucao_atendimento
  ON ia_execucao (atendimento_id, created_at DESC);
CREATE INDEX idx_ia_execucao_empresa_data
  ON ia_execucao (empresa_id, created_at DESC);
```

### 13. IABudget (governança custo mensal)

**Por quê:** controle financeiro. Cliente define limite mensal por empresa; sistema bloqueia ou redireciona quando estoura.

**Mig 058:**

```sql
CREATE TABLE ia_budget (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  ano_mes CHAR(7) NOT NULL,         -- "2026-05"
  limite_usd NUMERIC(10,2) NOT NULL,
  consumo_usd NUMERIC(10,2) NOT NULL DEFAULT 0,
  acao_estouro TEXT NOT NULL DEFAULT 'alertar'
    CHECK (acao_estouro IN ('alertar', 'bloquear', 'redirecionar_menu')),
  alerta_pct INT NOT NULL DEFAULT 80,  -- alerta quando >= 80%
  estourado_em TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (empresa_id, ano_mes)
);
```

### 14. Plano + Transacao (billing comercial)

**Por quê:** quando virar SaaS pago. Hoje `empresa.plano` é só TEXT.

**Mig 059:**

```sql
CREATE TABLE plano (
  id BIGSERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE,        -- "Free", "Pro", "Enterprise"
  descricao TEXT,
  preco_mensal_brl NUMERIC(10,2),
  limite_usuarios INT,
  limite_conexoes INT,
  limite_atendimentos_mes INT,
  limite_orcamento_ia_usd NUMERIC(10,2),
  features JSONB NOT NULL DEFAULT '{}',  -- {calendar: true, mcp: false, ...}
  ativo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE transacao (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  plano_id BIGINT REFERENCES plano(id) ON DELETE SET NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('assinatura', 'addon', 'reembolso', 'credito')),
  valor_brl NUMERIC(10,2) NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pendente', 'pago', 'falhou', 'estornado')),
  gateway_id TEXT,                  -- ID externo (Stripe/PagSeguro)
  pago_em TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Baixas (skip por enquanto)

### TelegramChat
Suporte Telegram. Implementar só se cliente pedir explicitamente. Mig depois.

### Produto + CategoriaProduto + OpcaoProduto
Catálogo de produtos. Não somos e-commerce — provavelmente skip permanente, ou nicho.

### IATopAgente
Métrica derivada (top N agentes por uso). Pode ser computado on-the-fly em SQL — não precisa tabela.

### Cidade / Estado
Fixures geográficas. Nosso `cliente.cidade TEXT` + `cliente.uf CHAR(2)` é suficiente.

### Termo
Termos de uso. Resolver com Better Auth metadata em vez de tabela.

### CalendarioEvento
Nosso `agendamento` (mig 027) já cobre + Calendar Agent v2 é diferencial. Skip ZigChat version.

### Contador
Counter genérico legacy. Nosso é por entidade (`campanha.enviados`, etc). Skip.

### ConStateUpdate / DecryptJob / AtendiemntoPayload
Internos ZigChat. Skip permanente.

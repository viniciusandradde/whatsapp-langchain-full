# 03 — Gap grande (🟡) — entidades existentes que precisam ALTER significativo

[← Voltar ao índice](./README.md)

> Entidades onde Nexus tem o core mas faltam campos importantes pra paridade ZigChat.
> SQL pronto pra ALTER incremental + análise de prioridade.

## 1. AgenteIA — `agente_ia` (mig 039)

**Gaps:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `modelo_provedor` + `modelo_nome` | `String!`+`String!` | Temos `modelo` único (ex: `"google/gemini-2.5-flash"`) | 🔥 Alta — necessário pra catálogo modelo_llm |
| `tipo_memoria` | `String!` | Não temos (LangGraph usa store global) | Média — útil pra agentes de FAQ vs vendas |
| `janela_memoria` | `Int` | Não temos | Média |
| `timeout_minutos` | `Int` | Não temos | Baixa — TTL conversa idle |
| `acao_limite_menu_id` | `Int` (FK Menu) | Temos só `limite_custo_acao` (string) | 🔥 Alta — governança custo crítica |

**Mig 043 sugerida:**

```sql
-- Sub-fase B+ — paridade ZigChat (governança custo + memória)
ALTER TABLE agente_ia
  ADD COLUMN modelo_provedor TEXT,
  ADD COLUMN modelo_nome TEXT,
  ADD COLUMN tipo_memoria TEXT NOT NULL DEFAULT 'window'
    CHECK (tipo_memoria IN ('buffer', 'window', 'summary', 'none')),
  ADD COLUMN janela_memoria INT,
  ADD COLUMN timeout_minutos INT,
  ADD COLUMN acao_limite_menu_id BIGINT REFERENCES menu_chatbot(id) ON DELETE SET NULL;

-- Backfill: split modelo único em provedor + nome
UPDATE agente_ia
   SET modelo_provedor = SPLIT_PART(modelo, '/', 1),
       modelo_nome = SPLIT_PART(modelo, '/', 2)
 WHERE modelo IS NOT NULL AND POSITION('/' IN modelo) > 0;

COMMENT ON COLUMN agente_ia.modelo IS
  'DEPRECATED — use modelo_provedor + modelo_nome (mig 043). Removido em mig 060+.';
```

**Impacto código:**
- `shared/agente.py::AgenteIA` adicionar 5 campos
- `shared/llm.py::create_chat_model` aceitar `provedor` separado
- UI editor 5 tabs ganha 2 dropdowns (provedor + modelo)

---

## 2. Menu — `menu_chatbot` (mig 040)

**Gaps:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `atalho` | `String` | Temos `trigger_keywords TEXT[]` (mais geral) | Baixa — UX equivalente |
| `principal` | `String` (S/N) | Temos UNIQUE PARTIAL `WHERE ativo` | ➖ Já coberto |
| `solicitar_nome` | `String` (S/N) | Não temos | Média — UX comum |
| `coleta_informacao` + `confirmar_coleta` + `enviar_msg_final_coleta` | 3× String | Não temos | Média — wizard pré-menu |
| `menu_moderno` | `String` (S/N) | Não temos | 🔥 Alta — botões WhatsApp são killer feature |
| `menu_ia` | `String` (S/N) | Não temos | Baixa — meta-feature |
| `auto_navegar_para_item_id` | `Float` (FK Item) | Não temos | Média — fallback timeout |
| `qtde_acesso` | `Float` | Não temos | Baixa — analytics |
| `arquivo` | `String` | Não temos | Média — anexo nas boas-vindas |
| `resposta_confidencial` | `String` (S/N) | Não temos | Baixa — caso edge |
| `exibir_comando_menu_item` | `String` | Não temos | Baixa |

**Mig 041 sugerida:**

```sql
ALTER TABLE menu_chatbot
  ADD COLUMN atalho TEXT,
  ADD COLUMN solicitar_nome BOOLEAN DEFAULT FALSE,
  ADD COLUMN menu_moderno BOOLEAN DEFAULT FALSE,
  ADD COLUMN auto_navegar_para_item_id BIGINT REFERENCES menu_item(id) ON DELETE SET NULL,
  ADD COLUMN arquivo_url TEXT,
  ADD COLUMN qtde_acesso BIGINT DEFAULT 0,
  -- Wizard de coleta (3 passos sequenciais)
  ADD COLUMN mensagem_coleta TEXT,
  ADD COLUMN mensagem_confirmar_coleta TEXT,
  ADD COLUMN mensagem_final_coleta TEXT,
  ADD COLUMN resposta_confidencial BOOLEAN DEFAULT FALSE;
```

**Impacto código:**
- `shared/menu_chatbot.py::MenuChatbot` adicionar 8 campos
- `worker/processor.py::_try_handle_menu` adicionar lógica de wizard de coleta + auto_navegar timeout
- UI builder ganha tab "Coleta" + toggle "Menu moderno"

---

## 3. Item — `menu_item` (mig 040)

**Gap MAIOR — 7 ações novas + 9 campos:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `comando` | `String` | Não temos | Média — alias texto da escolha |
| `acao_atendente_id` | `Float` (FK Usuario) | Não temos | 🔥 Alta — transferir pra atendente específico |
| `acao_modelo_mensagem_id` | `Float` (FK ModeloMensagem) | Não temos | 🔥 Alta — disparar template |
| `webhook_url` + `hook_id` | `String` + `Int` | Não temos | Média — chamar URL externa |
| `link` | `String` | Não temos | Média — enviar URL/link |
| `nota_min` + `nota_max` + `nota_escolha_msg` | 2× Float + String | Não temos | Média — pesquisa CSAT |
| `mudar_para_manual` | `String` (S/N) | Não temos | 🔥 Alta — handoff humano direto |
| `acao_setar_nome` | `String` (S/N) | Não temos | Baixa — coleta no item |
| `grupo` | `String` | Não temos | Baixa — agrupamento visual |
| `enviar_contato_transf_depto` | `String` | Não temos | Baixa |
| `item_fim_coleta` | `String` | Não temos | Baixa — flag fim wizard |
| `contato_cliente_id` | `Float` (FK Cliente) | Não temos | Baixa — CSV de contato |
| `acao` (numérico) | `Float!` | Temos `acao_tipo` (string CHECK 5) | 🔵 Manter strings — mais legível |

**Mig 042 sugerida:**

```sql
-- Novos campos compatíveis (NULL pra rows existentes)
ALTER TABLE menu_item
  ADD COLUMN comando TEXT,
  ADD COLUMN acao_atendente_id TEXT,    -- TEXT pq Better Auth user IDs são string
  ADD COLUMN acao_modelo_mensagem_id BIGINT REFERENCES modelo_mensagem(id) ON DELETE SET NULL,
  ADD COLUMN webhook_url TEXT,
  ADD COLUMN link_url TEXT,
  ADD COLUMN nota_min INT,
  ADD COLUMN nota_max INT,
  ADD COLUMN nota_pergunta TEXT,
  ADD COLUMN grupo TEXT;

-- Expandir CHECK de acao_tipo de 5 → 12 valores
ALTER TABLE menu_item DROP CONSTRAINT menu_item_acao_tipo_check;
ALTER TABLE menu_item ADD CONSTRAINT menu_item_acao_tipo_check CHECK (
  acao_tipo IN (
    -- MVP (mig 040)
    'submenu', 'transferir_dep', 'chamar_agente', 'enviar_msg', 'fechar',
    -- Sub-fase B+ paridade ZigChat (mig 042)
    'transferir_atendente', 'enviar_template', 'chamar_webhook',
    'enviar_link', 'pesquisa_csat', 'mudar_manual', 'setar_nome'
  )
);
```

**Impacto código:**
- `shared/menu_chatbot.py::ACAO_TIPOS` adicionar 7 valores
- `worker/processor.py::_try_handle_menu` adicionar 7 cases novos
- UI editor item — 7 forms novos (form contextual por acao_tipo)

---

## 4. AtendimentoMenuHistorico — `atendimento_menu_historico` (mig 040)

**Gaps menores:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `nanoid` | `String!` | Temos `id BIGSERIAL` | Baixa — exposição externa anti-guess |
| `resposta` | `String` | Não temos | 🔥 Alta — texto cru cliente pra debug |

**Mig 045 sugerida:**

```sql
ALTER TABLE atendimento_menu_historico
  ADD COLUMN nanoid TEXT,
  ADD COLUMN resposta TEXT;

CREATE UNIQUE INDEX uq_atendimento_menu_historico_nanoid
  ON atendimento_menu_historico (nanoid)
  WHERE nanoid IS NOT NULL;
```

**Impacto código:**
- Worker já passa `text` no `mark_done`. Adicionar gravação no `registrar_historico`.

---

## 5. Atendimento — `atendimento` (mig 010+035)

**Gaps:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `protocolo` | `String` | Não temos | 🔥 Alta — número de protocolo p/ cliente |
| `qtde_resposta_invalida` | `Float` | Não temos | Média — counter inválidas |
| `aba_id` | `Int` (FK Aba) | Não temos | Baixa — depende de criar `Aba` |
| `iniciado_cliente` | `String` (S/N) | Não temos | Média — quem iniciou (cliente vs operador outbound) |
| `finalizacao_usuario` | `String` | Não temos | Média — quem fechou |
| `nome_contato` | `String` | Temos `cliente.nome` | ➖ Redundante |
| `solicitou_encerramento` | `Int` | Não temos | Baixa |
| `tipo` (numérico) | `Float!` | Não temos | Baixa — atendimento type/canal |
| `canal` (numérico) | `Float!` | Temos `conexao_id` | ➖ Coberto |
| `informa_nome` | `String!` (S/N) | Não temos | Baixa |
| `agente_ia_id` (FK numérica) | `Int` | Temos `agente_atual` (slug TEXT) | 🔵 Mantém slug — mais flexível |

**Mig 047 sugerida:**

```sql
ALTER TABLE atendimento
  ADD COLUMN protocolo TEXT,
  ADD COLUMN qtde_resposta_invalida INT NOT NULL DEFAULT 0,
  ADD COLUMN iniciado_cliente BOOLEAN DEFAULT TRUE,  -- true = cliente abriu, false = outbound
  ADD COLUMN finalizado_por_user_id TEXT,            -- quem fechou (operador ou NULL = automático)
  ADD COLUMN solicitou_encerramento BOOLEAN DEFAULT FALSE;

-- Sequence pra protocolo único por empresa
CREATE SEQUENCE IF NOT EXISTS atendimento_protocolo_seq;

-- Trigger pra auto-gerar protocolo no INSERT (formato: empresa_id-NNNNN)
CREATE OR REPLACE FUNCTION gerar_protocolo_atendimento()
RETURNS trigger AS $$
BEGIN
  IF NEW.protocolo IS NULL THEN
    NEW.protocolo := NEW.empresa_id::text || '-' || LPAD(nextval('atendimento_protocolo_seq')::text, 6, '0');
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER atendimento_protocolo_trigger
  BEFORE INSERT ON atendimento
  FOR EACH ROW EXECUTE FUNCTION gerar_protocolo_atendimento();

CREATE INDEX idx_atendimento_protocolo ON atendimento (empresa_id, protocolo) WHERE protocolo IS NOT NULL;
```

**Impacto código:**
- `shared/atendimento.py::Atendimento` adicionar 5 campos
- UI atendimento mostrar protocolo no header do drawer

---

## 6. Cliente — `cliente` (mig 010+038)

Já bem rico (38 campos). **Gaps importantes:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `imagem_perfil` + `imagem_perfil_completa` | `String` | Temos `avatar_url` | 🔵 Equivalente parcial |
| `visto_ultimo` | `Float` | Temos `last_interaction_at` | ✅ Equivalente |
| `state` | `String` | Não temos | Média — estado WhatsApp Web (CONNECTED/QR/etc) |
| `numero_verificado` | `String` (S/N) | Não temos | Média — número validado WhatsApp |
| `desconsiderar_turno_cliente` | `String` (S/N) | Não temos | Baixa — VIP que ignora horário |
| `field_1` ... `field_5` | `String` × 5 | Não temos | 🔥 Alta — campos custom por empresa |
| `tipo_atendimento` | `Int` | Não temos | Média — manual/ia/hibrido pra esse cliente |
| `lid` | `String` | Não temos | Média — Linked Identity WhatsApp |
| `ignora_inatividade` | `String` (S/N) | Não temos | Baixa — bypass timeout |
| `aba_id` | `Int` (FK Aba) | Não temos | Baixa |
| `msg_apos_encerramento` | `String!` | Não temos | Média — msg automática pós-fim |
| `webhook_url` + `hook_id` | `String` + `Int` | Não temos | Baixa — hook por cliente |
| `tags_secundarias` | `String` | Temos `tags` via `cliente_tag` | 🔵 Coberto |
| `remoteid` | `String` | Não temos | Média — ID no sistema externo (CRM legado) |
| `tag_id` | `Int` | Temos via `cliente_tag` | ➖ Many-to-many nosso é melhor |

**Mig 046 sugerida:**

```sql
ALTER TABLE cliente
  ADD COLUMN whatsapp_state TEXT,                 -- CONNECTED/QR/DISCONNECTED
  ADD COLUMN numero_verificado BOOLEAN DEFAULT FALSE,
  ADD COLUMN whatsapp_lid TEXT,                   -- Linked Identity
  ADD COLUMN remote_id TEXT,                      -- ID em CRM externo (Salesforce/RD/etc)
  ADD COLUMN msg_apos_encerramento TEXT,
  -- 5 campos custom por cliente (cada empresa decide o que armazenar)
  ADD COLUMN field_1 TEXT,
  ADD COLUMN field_2 TEXT,
  ADD COLUMN field_3 TEXT,
  ADD COLUMN field_4 TEXT,
  ADD COLUMN field_5 TEXT,
  ADD COLUMN ignora_inatividade BOOLEAN DEFAULT FALSE,
  ADD COLUMN desconsidera_turno BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_cliente_remote_id ON cliente (empresa_id, remote_id) WHERE remote_id IS NOT NULL;
CREATE INDEX idx_cliente_whatsapp_lid ON cliente (whatsapp_lid) WHERE whatsapp_lid IS NOT NULL;
```

---

## 7. Conexao — `conexao` (mig 009+020)

**Gaps:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `engine` | `String!` | Temos `provider` (idêntico) | ✅ |
| `tipo_atendimento` | `String!` | Não temos | 🔥 Alta — manual/ia/hibrido por canal |
| `tipo` | `String` | Não temos | Baixa — canal type adicional |
| `agente_ia_id` (FK Int) | `Int` | Temos `default_agent_id TEXT` | 🔵 Diferente — slug é mais flexível |
| `state` | `String` | Não temos | Média — estado WhatsApp da instância |
| `start_time` | `Float` | Não temos | Baixa — uptime |
| `waba_account_id/description/phone_id/app_id` | 4× String | Não temos | 🔥 Alta — config WABA explícita |
| `padrao` | `String!` (S/N) | Temos `is_default BOOLEAN` | ✅ |
| `session` | `String` | Temos `payload_json` (genérico) | 🔵 Pode armazenar lá |

**Mig 048 sugerida:**

```sql
ALTER TABLE conexao
  ADD COLUMN tipo_atendimento TEXT NOT NULL DEFAULT 'ia'
    CHECK (tipo_atendimento IN ('manual', 'ia', 'hibrido')),
  ADD COLUMN whatsapp_state TEXT,
  -- Config WABA dedicada (em vez de mexer com payload_json genérico)
  ADD COLUMN waba_account_id TEXT,
  ADD COLUMN waba_phone_id TEXT,
  ADD COLUMN waba_app_id TEXT,
  ADD COLUMN waba_account_description TEXT;
```

---

## 8. Departamento — `departamento` (mig 017+032)

**Gaps:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `posicao_fila_transferencia` | `Int` | Não temos | Média — ordem de fallback |
| `notifica_cliente_id` | `Float` (FK Cliente) | Não temos | Baixa — quem é notificado externamente |
| `encerra_atendimento` | `String` (S/N) | Não temos | Média — flag se transfer aciona fechamento |
| `grupo` | `String` | Não temos | Baixa — agrupamento adicional |
| `tolerancia_atend_inativo` | `Int` | Não temos | Média — minutos antes de marcar inativo |
| `enviar_fila_atendimento` | `String` (S/N) | Não temos | Média — se manda mensagem "você é o N na fila" |
| `menu_coleta_id` | `Int` (FK Menu) | Não temos | Média — menu específico para coleta nesse depto |
| `retencao_msg` | `Int` | Não temos | Baixa — dias de retenção |
| `turno_id` | `Float` (FK Turno) | Temos `horario_funcionamento` por dep | 🔵 Equivalente diferente |
| `parent_id` (hierarquia) | — | Temos via mig 032 | ✅ Diferencial nosso |

**Mig 049 sugerida:**

```sql
ALTER TABLE departamento
  ADD COLUMN posicao_fila_transferencia INT,
  ADD COLUMN encerra_atendimento BOOLEAN DEFAULT FALSE,
  ADD COLUMN tolerancia_atend_inativo_min INT,
  ADD COLUMN enviar_fila_atendimento BOOLEAN DEFAULT FALSE,
  ADD COLUMN menu_coleta_id BIGINT REFERENCES menu_chatbot(id) ON DELETE SET NULL,
  ADD COLUMN retencao_msg_dias INT;
```

---

## 9. Empresa — `empresa` (mig 007+008)

**Gaps:**

| ZigChat | Tipo | Status atual | Prioridade |
|---|---|---|---|
| `menu_coleta_id` (FK Menu) | `Int` | Não temos | Média — menu coleta default |
| `hook_id` | `Int` | Não temos | Baixa — hook genérico empresa |
| `criacao_usuario_id` | `Float` | Temos via audit | ➖ Coberto |
| Campos billing (CNPJ tax, endereço fiscal) | — | Temos `doc` mas nada estruturado | Média |

**Mig 050 sugerida:**

```sql
ALTER TABLE empresa
  ADD COLUMN menu_coleta_id BIGINT REFERENCES menu_chatbot(id) ON DELETE SET NULL,
  ADD COLUMN hook_id BIGINT REFERENCES hook(id) ON DELETE SET NULL,
  -- Billing fields
  ADD COLUMN razao_social TEXT,
  ADD COLUMN inscricao_estadual TEXT,
  ADD COLUMN endereco_fiscal_cep TEXT,
  ADD COLUMN endereco_fiscal_logradouro TEXT,
  ADD COLUMN endereco_fiscal_numero TEXT,
  ADD COLUMN endereco_fiscal_bairro TEXT,
  ADD COLUMN endereco_fiscal_cidade TEXT,
  ADD COLUMN endereco_fiscal_uf CHAR(2);
```

---

## 10. Campanha — `campanha` (mig 034)

**Gaps:**

| ZigChat | Status | Prioridade |
|---|---|---|
| Agendamento programado (`scheduled_at`) | Não temos | Média |
| Template (`modelo_mensagem_id`) — em vez de mensagem inline | Não temos | 🔥 Alta — WABA exige HSM |
| Filtros de destinatário (segmento/tag) | Não temos (nosso enfileira lista pronta) | Média |
| Tipo de envio (broadcast/transactional) | Não temos | Média |

**Mig 051 sugerida:**

```sql
ALTER TABLE campanha
  ADD COLUMN modelo_mensagem_id BIGINT REFERENCES modelo_mensagem(id) ON DELETE SET NULL,
  ADD COLUMN scheduled_at TIMESTAMPTZ,
  ADD COLUMN tipo TEXT NOT NULL DEFAULT 'broadcast'
    CHECK (tipo IN ('broadcast', 'transactional', 'reativacao')),
  ADD COLUMN filtro_segmento TEXT,
  ADD COLUMN filtro_tags TEXT[];
```

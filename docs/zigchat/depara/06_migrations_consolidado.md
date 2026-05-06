# 06 — Roadmap consolidado: mig 041-060 pra paridade ZigChat

[← Voltar ao índice](./README.md)

> Sequência otimizada com dependências, ordem ideal e estimativa.
> Cada migration referencia o detalhe completo em `03_gap_grande.md` ou `04_pendentes_criar.md`.

## Princípios de ordenação

1. **Dependências primeiro** — Quem outro depende vem antes (ex: `mcp_server` antes de `agente_ia` referenciar)
2. **Valor entregue** — Features que destravam UX/usuário primeiro
3. **Risco crescente** — ALTERs simples antes de mudanças estruturais (split de coluna, FKs many-to-many)
4. **Reversibilidade** — Migrations idempotentes e ALTER ADD (vs DROP) — fácil rollback via `ALTER TABLE DROP COLUMN`

## Dependency graph

```
041 menu_chatbot expand          (independente)
042 menu_item expand + 7 ações   (depende de 041 pra acao_atendente_id?)
042 mcp_server CREATE            (independente — agente_ia.mcp_server_ids já existe)
043 agente_ia expand             (depende de 041 — acao_limite_menu_id FK)
044 modelo_llm CREATE + seed     (independente)
045 atendimento_menu_historico expand (independente)
046 cliente expand               (independente)
047 atendimento expand           (independente)
048 conexao expand               (independente)
049 turno + departamento expand  (turno antes de FK em departamento)
050 aba CREATE                   (independente)
051 campanha expand              (depende de 044 — modelo_mensagem_id já existe)
052 tag CREATE + cliente_tag_v2 + atendimento_visualizacao + atendimento_transferencia
053 menu_item_arquivo CREATE     (independente)
054 push_device CREATE           (independente)
055 aviso + aviso_usuario_leitura CREATE
056 form_padrao + form_resposta CREATE
057 ia_execucao CREATE           (telemetria LLM)
058 ia_budget CREATE             (governança custo)
059 plano + transacao CREATE     (billing comercial)
060 empresa expand               (FK pra menu_coleta_id + hook_id — depende 041 + 012)
```

## Ordem ideal sugerida (por sprint)

### Sprint 1 — UX wins menu (mig 041-042)

**Objetivo:** menu chatbot com paridade ZigChat MVP.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 041 | Expand `menu_chatbot` (atalho, solicitar_nome, menu_moderno, auto_navegar, qtde_acesso, wizard coleta) + CREATE `menu_item_arquivo` | ~30 | Baixo |
| 042 | Expand `menu_item` (+7 ações novas + 9 campos) + CREATE `mcp_server` | ~40 | Médio (CHECK expand) |

**Código adjacente:**
- `worker/processor.py::_try_handle_menu` — adicionar 7 cases novos + lógica wizard de coleta + lógica auto_navegar (timeout)
- `shared/menu_chatbot.py::ACAO_TIPOS` — adicionar 7 valores
- UI editor menu — tab "Coleta" + 7 forms novos por acao_tipo

---

### Sprint 2 — Catálogo modelo + governança custo (mig 043-044)

**Objetivo:** UI dropdown sabendo quais modelos existem + base pra cobrança.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 044 | CREATE `modelo_llm` + seed inicial | ~40 | Baixo |
| 043 | Expand `agente_ia` (modelo_provedor/nome split, tipo_memoria, janela_memoria, timeout_minutos, acao_limite_menu_id) | ~25 | Médio (backfill SPLIT_PART) |

**Código adjacente:**
- `shared/agente.py::AgenteIA` — 5 campos novos
- `shared/llm.py::create_chat_model` — receber `provedor` separado
- UI editor agente — dropdown 2 níveis (provedor → modelo) puxando de `modelo_llm`

---

### Sprint 3 — CRM enrich (mig 045-046)

**Objetivo:** equipe ganha protocolo + campos custom no cliente.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 045 | Expand `atendimento_menu_historico` (nanoid, resposta) | ~10 | Baixo |
| 046 | Expand `cliente` (whatsapp_state, lid, remote_id, msg_apos_encerramento, field_1..5, ignora_inatividade, desconsidera_turno) | ~25 | Baixo |
| 047 | Expand `atendimento` (protocolo + trigger sequencia, qtde_resposta_invalida, iniciado_cliente, finalizado_por_user_id, solicitou_encerramento) | ~35 | Médio (trigger sql) |

---

### Sprint 4 — Operação (mig 048-049)

**Objetivo:** config canal + escala turno reutilizável.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 048 | Expand `conexao` (tipo_atendimento, whatsapp_state, waba_*) | ~15 | Baixo |
| 049 | Expand `departamento` (posicao_fila_transferencia, etc) + CREATE `turno` + FK | ~40 | Médio |

---

### Sprint 5 — Tagging + transferências auditáveis (mig 050-053)

**Objetivo:** sistema de tag rico + audit completo de transferências.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 050 | CREATE `aba` | ~25 | Baixo |
| 051 | Expand `campanha` (template, scheduled_at, tipo, filtros) | ~15 | Baixo |
| 052 | CREATE `tag` + `cliente_tag_v2` + `atendimento_visualizacao` + `atendimento_transferencia` + backfill | ~80 | 🔥 Alto (migra cliente_tag) |
| 053 | CREATE `menu_item_arquivo` (caso não tenha vindo na 041) | ~20 | Baixo |

---

### Sprint 6 — Notificações + plataforma (mig 054-056)

**Objetivo:** banner sistema, push mobile, formulários.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 054 | CREATE `push_device` | ~20 | Baixo |
| 055 | CREATE `aviso` + `aviso_usuario_leitura` | ~30 | Baixo |
| 056 | CREATE `form_padrao` + `form_resposta` | ~25 | Baixo |

---

### Sprint 7 — Governança IA + Billing (mig 057-059)

**Objetivo:** telemetria LLM + cobrança comercial.

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 057 | CREATE `ia_execucao` | ~30 | Baixo |
| 058 | CREATE `ia_budget` | ~25 | Baixo |
| 059 | CREATE `plano` + `transacao` | ~50 | Médio |

---

### Sprint 8 — Empresa fechamento (mig 060)

| Mig | Escopo | LOC SQL | Risco |
|---|---|---:|---|
| 060 | Expand `empresa` (menu_coleta_id, hook_id, billing fields) | ~25 | Baixo |

---

## Resumo executivo

| Sprint | Migrations | Foco | Dias úteis estimados |
|---|---|---|---:|
| 1 | 041, 042 | Menu paridade + MCP | 4-5 |
| 2 | 043, 044 | Catálogo modelo + custo | 3-4 |
| 3 | 045, 046, 047 | CRM enrich + protocolo | 4-5 |
| 4 | 048, 049 | Conexão + turno | 3-4 |
| 5 | 050-053 | Tag + transferências | 5-6 |
| 6 | 054-056 | Aviso + push + form | 3-4 |
| 7 | 057-059 | IA telemetria + billing | 4-5 |
| 8 | 060 | Empresa fechamento | 1-2 |
| **Total** | **20 migrations** | **Paridade ZigChat** | **~27-35 dias** |

≈ **5-7 sprints** focado, ou **~2 meses** com outras prioridades intercaladas.

---

## Estratégia de rollout

### Não fazer Big Bang
- **Cada migration sobe sozinha** — não precisa esperar todas pra deployar
- **ALTER ADD COLUMN é sempre seguro** — colunas novas com NULL/DEFAULT não quebram código existente
- **Backfill em background** quando volumes grandes (ex: cliente_tag → cliente_tag_v2 com 100k+ rows)

### Feature flag pra novas ações
Cada acao_tipo nova de menu_item entra atrás de feature flag `menu_acao_<tipo>_enabled` (default false) — admin liga via UI quando UI ficar pronta.

### Deprecation graceful
Colunas antigas (`agente_ia.modelo` único após split em provedor+nome) ficam com COMMENT `DEPRECATED — remove em mig XXX` por 2-3 sprints antes de DROP. Permite rollback se algo quebrar.

### Migrations runner já é idempotente
Nosso `_migrations` table + IF NOT EXISTS em todos os CREATE — re-rodar é seguro.

---

## Fora do roadmap (skip permanente)

- `Produto` + `CategoriaProduto` + `OpcaoProduto` — não somos e-commerce
- `TelegramChat` — só se virar prioridade comercial
- `Cidade` / `Estado` — fixures geográficas, nosso TEXT/CHAR(2) basta
- `Termo` — Better Auth metadata cobre
- `Contador` — generic counter legacy ZigChat
- `IATopAgente` — derivado, computa em SQL on-demand

---

## Próximo passo recomendado

Decidir se vamos **iniciar Sprint 1 (mig 041+042)** agora ou **terminar B.5 UI primeiro** (UI builder de menus pra MVP atual).

UI primeiro tem vantagem: valida MVP em produção com cliente real, captura UX feedback que pode mudar prioridades das mig 041-060.

Mig 041 primeiro tem vantagem: paridade ZigChat avança e UI já sai cobrindo features novas.

**Recomendação:** UI primeiro (B.5). Validar antes de ampliar escopo.

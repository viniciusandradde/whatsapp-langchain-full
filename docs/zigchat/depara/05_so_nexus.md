# 05 — Só no Nexus — entidades + features que ZigChat NÃO tem

[← Voltar ao índice](./README.md)

> Diferenciais Nexus que ZigChat não cobre. Não há mapping a fazer aqui — esses são pontos de orgulho a manter.

## Infraestrutura LangGraph (não-relacional)

| Tabela | Mig | Função |
|---|---|---|
| `checkpoints` + `checkpoint_blobs` + `checkpoint_writes` + `checkpoint_migrations` | LangGraph DDL (in-code) | State machine persistence — agente IA continua conversa exatamente do ponto que parou |
| `store` + `store_vectors` + `store_migrations` + `vector_migrations` | LangGraph DDL | Memória semântica cross-thread (`save_memory` / `read_memory` tools) |

**Diferencial:** ZigChat usa armazenamento mais simples (provável JSON em row do Atendimento). Nosso preserva grafo completo de execução, permite resume após crash.

---

## Calendar Agent v2 (mig 027-030)

| Tabela | Função |
|---|---|
| `agendamento` | Mirror local de eventos Google Calendar com governança |
| `agendamento_aprovacao` | Workflow de aprovação humana antes de criar evento |
| `agendamento_historico` | Audit completo de operações (criar/cancelar/reagendar) |
| `agendamento_regras` | Regras de negócio (horário disponível, antecedência mínima, dias bloqueados) |

**Diferencial:** integração nativa Google Calendar com workflow de aprovação 1/2 via WhatsApp. ZigChat tem `CalendarioEvento` simples sem governança.

---

## RBAC granular (mig 031)

| Tabela | Função |
|---|---|
| `permissao` | Catálogo (44+ permissões em `shared/permissoes.py::CATALOGO`) |
| `perfil_acesso` | Roles (Admin, Gestor, Agente, custom) |
| `perfil_permissao` | Many-to-many perfil ↔ permissao |
| `usuario_perfil` | Many-to-many user ↔ perfil |

**Diferencial:** ZigChat tem `Permissao` e `Grupo` mas estrutura desconhecida (sem inputs expostos). Nosso é explícito + auditável + customizável por empresa.

---

## Audit centralizado (mig 036)

| Tabela | Função |
|---|---|
| `audit_log` | Log centralizado de mutations (action, entity_type, entity_id, payload_diff, request metadata) |

**Diferencial:** ZigChat tem `criacao_usuario_id`/`alteracao_usuario_id` por entidade + `GeralLog` desestruturado. Nosso `audit_log` tipa entidade + diff JSON + IP/UA/path.

---

## Hook DLQ + Retry (mig 023)

| Tabela | Função |
|---|---|
| `hook_dead_letter` | Hooks que falharam todas tentativas (retry exponencial 1s/5s/25s) |

**Diferencial:** ZigChat tem `Hook` mas sem indício de DLQ ou retry estruturado. Nosso production-ready com endpoint de re-tentativa manual.

---

## Feature flags (mig 037)

| Tabela | Função |
|---|---|
| `feature_flag` | Flags por empresa (ex: `mcp_enabled`, `calendar_v2`, `menu_moderno_beta`) |

**Diferencial:** ZigChat não tem feature flagging visível. Nosso permite rollout incremental.

---

## Better Auth (schema `auth`)

| Tabela | Função |
|---|---|
| `auth.user` | Identity provider + status (active/disabled) |
| `auth.session` | Sessões + cookies + revoke imediato |
| `auth.account` | Multi-provider (email/password, Google SSO, etc) |
| `auth.password_reset_pending` | Reset sem SMTP — admin compartilha link via WhatsApp |
| `auth_login_event` | Audit IP + UA |

**Diferencial:** ZigChat parece ter auth proprietário. Nosso usa Better Auth com SSO Google opt-in, password reset sem dependência de email server, status user com kill de sessões em <30s.

---

## Cliente CRM enriquecido (mig 038)

`cliente` tem **38 campos** vs ~25 do ZigChat. Extras nossos:

- Documentos: `tipo_pessoa`, `cpf`, `cnpj`, `rg`, `razao_social`, `nome_fantasia`
- Endereço estruturado: `cep`, `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `uf`, `pais`
- Lifecycle: `lifecycle_stage`, `score`, `source`, `responsavel_user_id`, `valor_estimado_brl`
- Social: `instagram`, `linkedin`, `facebook`, `website`
- Contato extra: `email_alternativo`, `telefone_alternativo`
- I18n: `locale`, `timezone`
- `notes` (free-text)

ZigChat tem `field_1..5` genéricos. Nosso é tipado.

---

## Filas via Postgres (mig 001+002)

| Tabela | Função |
|---|---|
| `message_queue` | Fila de mensagens com lease + retry + claim FOR UPDATE SKIP LOCKED |
| `rate_limit_bucket` | Sliding window rate limit (admin endpoints) |
| `rate_limit_buckets` | Per-phone webhook rate limit |

**Diferencial:** ZigChat tem `AtendimentoMensagem` mas sem indícios de fila estruturada. Nosso é at-least-once, observable, com retry exponencial.

---

## RAG (Retrieval Augmented Generation) — mig 015+018

| Tabela | Função |
|---|---|
| `documento_conhecimento` | Documentos do agente (PDF, texto, FAQ) |
| `documento_conhecimento_chunk` | Chunks vetorizados (embedding pgvector) |

**Diferencial:** ZigChat tem `BaseConhecimento` (texto cru). Nosso já tem chunking + embeddings + pgvector pronto pra search.

---

## Outros diferenciais arquiteturais

- **Multi-tenancy estrito** (`empresa_id NOT NULL` em quase tudo) — ZigChat tem mas inconsistente (alguns types `empresa_id` é `Float` opcional)
- **OpenTelemetry tracing** + Prometheus metrics (Fase 0) — ZigChat sem indícios
- **Health granular** (`/health/db`, `/health/queue`, `/health/openrouter`, etc) — ZigChat só `/api/health`
- **Stress testing profile** (Locust) integrado
- **Hooks dispatcher** com retry/DLQ + admin UI (`/integracoes/hooks/dead-letter`)
- **Frontend Next.js 16 + React 19** — ZigChat parece Angular legado

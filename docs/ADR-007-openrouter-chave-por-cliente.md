# ADR-007 — Chave da OpenRouter: uma por cliente ou uma só?

- **Status:** ACEITA E IMPLEMENTADA (25/09/2026) — o dono pediu as Opções A **e** B
  (mig 204, branch `feat/openrouter-chave-por-empresa`).
- **Pergunta do dono:** cada novo cliente deveria ter uma chave de API própria
  na OpenRouter, para separar custos, com cada um como um "pool" lá?

## 1. Como estava

- **Uma chave só** (`settings.openrouter_api_key`), lida em `shared/llm.py`
  e também pelos caminhos de mídia (visão/transcrição), voz e embeddings.
- **O custo já é separado por empresa internamente**:
  `governanca_ia.acrescentar_consumo(pool, empresa_id, custo)` é alimentado a
  cada chamada por `llm_callback`, `midia_processing` e `voz`; `ia_execucao`
  guarda cada chamada com empresa, agente, modelo e finalidade; o `ia_budget`
  aplica o teto do plano (ADR-005). Isso é mais fino do que o painel da
  OpenRouter mostraria por chave.

## 2. O que uma chave por cliente resolve — e o que não resolve

| Objetivo | Chave por cliente ajuda? | Por quê |
|---|---|---|
| Separar custo para **cobrar** | **Não** | Cobra-se preço de plano, não custo bruto. A fonte de verdade do que cada empresa gastou já é `ia_execucao`. |
| Isolar **limite de uso** (rate limit) entre clientes | Sim | Uma chave junta o limite de todos; um cliente que dispara muito atrasa os outros. |
| **Teto de gasto** no lado do provedor | Sim | A OpenRouter permite limite de crédito por chave — teto duro além do `ia_budget`. |
| Reduzir o **raio de um vazamento** | Sim | Chave única vazada afeta todos. |
| Cliente pagar a OpenRouter **direto** | Sim (BYOK) | Cliente traz a própria chave; o gasto aparece no painel dele. |

## 3. Opções

**Opção 0 — manter chave única + contabilidade interna (padrão).**
É o que quase todo SaaS que revende IA faz. Simples, uma rotação só, margem
sob controle. Fraqueza: limite de uso compartilhado e raio de vazamento.

**Opção A — chave própria da empresa (BYOK), opcional.**
Campo cifrado na empresa. Se preenchido, todas as chamadas daquela empresa
usam a chave dela; senão, a da plataforma. Cobre o cliente que quer isolar
de verdade, com pouco esforço.

**Opção B — chave exclusiva provisionada pela plataforma.**
A plataforma cria uma chave por empresa pela API de gestão da OpenRouter,
com limite de crédito, guarda cifrada e rotaciona. Máximo isolamento;
custo operacional de N segredos e reconciliação. Para quem exigir.

## 4. Decisão

Padrão continua a **Opção 0**. As Opções **A e B** existem como recurso por
empresa, ligadas pelo painel (Empresas → "Chave da OpenRouter"). Nenhuma
empresa nasce com chave própria; o superadmin decide caso a caso.

## 5. Como foi implementado (mig 204)

**Dados** — `empresa.openrouter_chave_cifrada` (Fernet, a mesma infra de
`integrations/crypto`), `_prefixo` (o que o painel mostra: `sk-or-v1-abc…`),
`_origem` (`propria` | `provisionada`), `_hash` (identificador na API de
gestão, só provisionada), `_limite_usd`, `_definida_em`. A chave nunca sai
pela API nem entra no `audit_log` (só o prefixo).

**Como a chave chega às chamadas** — `shared/openrouter_chave.py`:
- um `ContextVar` por task; `chave_openrouter()` devolve a da empresa no
  contexto ou a da plataforma; `chave_openrouter_tts()` idem para a voz;
- o worker seta por mensagem (`chave_da_empresa(pool, empresa_id)` dentro
  do `empresa_scope` de `_processar_mensagem`);
- a API seta pelo `openrouter_chave_middleware` (registrado antes do
  `rls_context` para rodar depois dele — LIFO — e ler o `empresa_id` do
  RLS); cache de 60 s por empresa por processo;
- rota que age numa empresa diferente da ativa (`voz/preview`) usa
  `chave_da_empresa` explícito;
- pontos de chamada trocados: `llm.create_chat_model`, `midia_processing`,
  `ocr`, `voz`, embeddings (`shared/embeddings.py::embeddings_openrouter`, um
  cliente por chave — o singleton da base de conhecimento saiu),
  `rag_learner`. `build_graph` não mudou (contrato dos agentes).
- **ficam na chave da plataforma de propósito**: a memória semântica do
  LangGraph (`resolve_store_index_config` — o store embeda numa task de
  fundo, sem contexto de empresa; custo desprezível), a sonda de modelos e
  o catálogo (recursos de plataforma).

**Contabilidade** — segue igual (`acrescentar_consumo` por empresa, teto do
plano no `ia_budget`), com `ia_execucao.metadata.chave_propria = true` em
toda chamada que saiu por chave da empresa, para o relatório separar o que
não é custo da plataforma.

**API** (`server/routes/empresa_admin.py`):
- `GET /api/empresas/{id}/openrouter-chave` — estado, prefixo, e uso/limite
  consultados na OpenRouter (`GET /api/v1/key` com a chave própria;
  `GET /api/v1/keys/{hash}` com a de gestão para a provisionada).
- `PUT …/openrouter-chave` `{chave}` — Opção A; admin da empresa. Formato
  `sk-or-` conferido antes de ir à rede (422); a OpenRouter recusou → 422;
  sem rede → 502. Substituir uma provisionada apaga a antiga na OpenRouter.
- `DELETE …/openrouter-chave` — volta à chave da plataforma; provisionada só
  o superadmin remove (é crédito da plataforma); apaga na OpenRouter
  best-effort e devolve `apagada_na_openrouter`.
- `POST …/openrouter-chave/provisionar` `{limite_usd}` — Opção B, superadmin;
  `POST /api/v1/keys` com `OPENROUTER_PROVISIONING_KEY`. Com chave
  provisionada anterior é rotação sem janela (a nova entra antes de a antiga
  ser apagada). Sem a chave de gestão → 409 explicando.
- `PUT …/openrouter-chave/limite` `{limite_usd}` — superadmin; `PATCH` na
  API de gestão.

**Painel** — bloco "Chave da OpenRouter" em `/companies`
(`openrouter-chave-section.tsx`): estado de hoje, uso na OpenRouter, "Usar
uma chave própria" (campo de senha), e, só para o superadmin, "Criar chave
exclusiva" / "Trocar por uma chave nova" / "Alterar limite". Remoção passa
por confirmação.

**Testes** — `tests/unit/test_openrouter_chave.py` (27: contexto, factory,
embeddings por chave, marca no `ia_execucao`, cache, cliente da OpenRouter
com respx, gravação cifrada sem devolver a chave) e
`tests/integration/test_openrouter_chave_endpoints.py` (E2E: 401/403/422,
semeadura cifrada, remoção e auditoria sem a chave).

## 6. Riscos e o que ficou de fora

- Chave da empresa inválida ou sem crédito: o agente **cala** (a chamada
  falha e cai em `mark_failed`). Não cai para a chave da plataforma de
  propósito — senão a plataforma paga sem saber. O painel mostra o aviso
  ("A OpenRouter não reconhece mais esta chave") ao abrir a empresa. Fica
  para depois: a sonda de modelos em uso testar também por chave própria e
  avisar a empresa pelo canal de alertas.
- Cifra ilegível (chave de cifra da plataforma trocada): cai para a chave
  da plataforma com log `openrouter_chave_ilegivel` — é erro de
  configuração da plataforma, não da empresa.
- Cache de 60 s: trocar a chave pelo painel vale na API na hora (o cache do
  processo é limpo) e no worker em até um minuto.
- Cache de prompt da OpenRouter é por chave: empresa com chave própria não
  perde nada (o cache já é por empresa na prática, os prompts diferem).
- Provisionar automaticamente ao criar a empresa ficou de fora: o padrão
  é a chave da plataforma e a decisão é do superadmin, caso a caso.

# ADR-007 — Chave da OpenRouter: uma por cliente ou uma só?

- **Status:** PROPOSTA (25/09/2026), aguardando decisão do dono.
- **Pergunta do dono:** cada novo cliente deveria ter uma chave de API própria
  na OpenRouter, para separar custos, com cada um como um "pool" lá?

## 1. Como está hoje

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

**Opção A — BYOK opcional por empresa (recomendada).**
Campo cifrado `empresa.openrouter_key_encrypted`. Se preenchido, todas as
chamadas daquela empresa usam a chave dela; senão, a da plataforma. Cobre o
cliente que quer isolar de verdade, com pouco esforço.

**Opção B — provisionamento automático via API da OpenRouter.**
No cadastro, criar uma chave por empresa com limite de crédito, guardar
cifrada, rotacionar. Máximo isolamento; custo operacional de N segredos e
reconciliação. Só para enterprise que exija.

## 4. Decisão proposta

Padrão continua a **Opção 0**. Implementar a **Opção A** como recurso opcional.
Deixar a **Opção B** para quando um cliente enterprise pedir.

## 5. Plano de implementação da Opção A (para a próxima sessão)

1. **Mig 204** — `empresa.openrouter_key_encrypted TEXT` (cifrada com a mesma
   infra de `integrations/crypto`, chave `INTEGRACOES_ENCRYPTION_KEY`).
2. **`shared/llm.py`** — helper `chave_openrouter()` que devolve a chave da
   empresa ativa (contextvar) ou a da plataforma. O worker e o loader setam a
   contextvar por empresa, sem mudar a assinatura de `build_graph` (contrato
   dos agentes). Trocar as leituras diretas de `settings.openrouter_api_key`
   em `llm.py`, `midia_processing.py`, `voz.py`, `transcricao.py` e
   embeddings/RAG.
3. **Rota** `PUT /api/empresas/{id}/openrouter-key` (admin da empresa ou
   superadmin): grava cifrada; **nunca devolve a chave**, só "definida/não
   definida" e os 6 primeiros caracteres. Validar com uma chamada mínima à
   OpenRouter (`/api/v1/auth/key`) antes de gravar.
4. **UI** — bloco "Chave própria da OpenRouter" no form de `/companies`
   (mesmo padrão dos links de gateway da leva F): definir, trocar, remover.
5. **Contabilidade** segue igual (`acrescentar_consumo` por empresa), com uma
   marca `chave_propria=true` em `ia_execucao.metadata` para o relatório saber
   que aquele gasto não é da plataforma.
6. **Testes** — unit (contextvar cai na plataforma sem chave; empresa com chave
   usa a dela; chave nunca sai na resposta) + E2E (rota 401/403/200, a chamada
   de validação com chave falsa dá 422) + fumaça no dev.

## 6. Riscos

- Chave da empresa inválida ou sem crédito: o agente cala. Mitigação: a sonda
  de modelos em uso (`ia_alertas`) passa a testar também por chave própria e
  avisa a empresa; opcional "cair para a chave da plataforma" **desligado**
  por padrão (senão a plataforma paga sem saber).
- Cache de prompt é por chave: empresa com chave própria não perde nada (o
  cache já é por empresa na prática, os prompts diferem).

# Billing Asaas — Configuração e Teste (Dokploy)

Integração de cobrança da plataforma. O Asaas é uma **conta única da plataforma**
que fatura as empresas-clientes (cada empresa = um customer + subscription no
Asaas). **Não é por-empresa.**

Há **duas formas** de configurar a credencial (a partir do PR de config-pela-UI):

| Forma | Quem | Onde | Precedência |
|---|---|---|---|
| **Env vars** (Dokploy) | DevOps | painel Dokploy → env | fallback |
| **UI** (superadmin) | Superadmin | `/settings/integracoes` → card Asaas | **vence** o env (lê DB primeiro) |

> Enquanto o PR de config-pela-UI **não estiver deployado + migration 117 aplicada**,
> só a forma **env var** funciona. Este guia foca no caminho env (Dokploy), que
> funciona com o código atual.

---

## 1. Pré-requisitos no Asaas

1. Conta Asaas (sandbox para testes: `https://sandbox.asaas.com`).
2. **API Key:** Asaas → Configurações → Integrações → API. Formato `$aact_...`.
3. Base URLs (informativo — o app resolve sozinho por `ASAAS_ENVIRONMENT`):
   - Sandbox: `https://api-sandbox.asaas.com/v3`
   - Produção: `https://api.asaas.com/v3`

---

## 2. Variáveis no Dokploy

No painel Dokploy → seu Compose service → **Environment**, adicione:

```bash
ASAAS_ENVIRONMENT=sandbox            # ou "production"
ASAAS_API_KEY=$aact_xxxxxxxx         # OUTBOUND (checkout/subscription/teste)
ASAAS_WEBHOOK_TOKEN=<token-livre>    # INBOUND (valida o webhook recebido)
# Opcionais:
# ASAAS_SUCCESS_URL=https://chat.vsanexus.com/billing?ok=1
# ASAAS_CANCEL_URL=https://chat.vsanexus.com/billing?cancel=1
```

Depois **Redeploy** (env nova só vale após rebuild/restart do serviço).

| Var | Pra quê | Sem ela |
|---|---|---|
| `ASAAS_API_KEY` | criar customer/subscription, checkout, `POST /testar` | `/api/billing/*` → 503 |
| `ASAAS_WEBHOOK_TOKEN` | validar o `asaas-access-token` dos webhooks | webhook → 503/401 |
| `ASAAS_ENVIRONMENT` | escolher base URL (sandbox/prod) | default `sandbox` |

> ⚠️ `ASAAS_API_KEY` e `ASAAS_WEBHOOK_TOKEN` são **segredos** — só no painel Dokploy,
> nunca no repo. Rotacione se vazarem (mesmo sandbox).

---

## 3. Webhook no painel Asaas

Asaas → Integrações → **Webhooks** → novo:

- **URL:** `https://api.vsanexus.com/webhook/asaas`
- **Token de autenticação:** o **mesmo** valor de `ASAAS_WEBHOOK_TOKEN`.
  (Asaas envia esse valor no header `asaas-access-token`; o app compara —
  sem HMAC/assinatura.)
- **Eventos:** pelo menos `PAYMENT_CONFIRMED`, `PAYMENT_RECEIVED`,
  `PAYMENT_OVERDUE`, `PAYMENT_REFUNDED`, `SUBSCRIPTION_DELETED`.

---

## 4. Testar

1. **Webhook (inbound):** dispare um evento de teste pelo painel Asaas (ou faça um
   pagamento sandbox). Esperado: `200` no endpoint. Confira nos logs do worker/API
   `asaas_webhook_processed` (ou `asaas_webhook_duplicate_skipped` em reentrega —
   idempotência por `event.id`). Token errado → `401`; token ausente no servidor → `503`.
2. **Checkout (outbound):** no painel, empresa admin → `/billing` → Upgrade. Esperado:
   redireciona pro `invoiceUrl` do Asaas. Requer `ASAAS_API_KEY` válida.
3. **Validação rápida da API key:** (após o PR de UI) superadmin em
   `/settings/integracoes` → card Asaas → **Testar conexão** (chama `GET /myAccount`).

---

## 5. Caminho pela UI (após PR de config-pela-UI + mig 117)

Superadmin → `/settings/integracoes` → card **"Asaas — Cobrança (plataforma)"**:
ambiente, API key, webhook token, URLs + **Testar**. O que for salvo aqui **vence**
as env vars (precedência DB > env). Útil pra trocar credencial sem redeploy.

---

## Notas

- Falha transitória no webhook → o app retorna **5xx** pra o Asaas **retentar**
  (a confirmação de pagamento não é perdida); a idempotência (`dedup_key`) torna o
  retry seguro.
- `PAYMENT_OVERDUE` hoje é **logado** (dunning visível) mas **não** faz downgrade
  automático — política de carência é decisão de negócio (follow-up).
- Cobrança de cliente final pela própria empresa (Asaas por-empresa) **não** é
  suportado — billing aqui é só da plataforma.

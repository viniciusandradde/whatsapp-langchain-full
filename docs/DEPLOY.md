# Deploy

Este guia resume o deploy do projeto e aponta para os documentos detalhados
de operação.

## Estado atual

Hoje o projeto cobre:
- API FastAPI pública para `POST /webhook/twilio`
- Worker assíncrono com envio outbound via Twilio
- Frontend/admin panel em Next.js com Better Auth
- PostgreSQL com pgvector
- deploy de referência em Railway
- stress testing e leitura de gargalos
- documentação final com separação clara entre sandbox e produção
- branding mínimo aplicado no frontend

## Topologia alvo

```text
Internet -> Frontend (público)
Internet -> API (pública para /health e /webhook/twilio)
Twilio -> API (webhook inbound)
Frontend -> API (server-side via INTERNAL_API_URL + INTERNAL_SERVICE_TOKEN)
API -> PostgreSQL
Worker -> PostgreSQL
Frontend -> PostgreSQL (schema auth)
Worker -> Twilio (outbound)
```

## Guias detalhados

- [Railway](RAILWAY.md): provisionamento de serviços, rede interna, variáveis e watch paths
- [Twilio](TWILIO.md): credenciais, webhook, assinatura, sandbox e cloudflared
- [Stress Testing](STRESS_TESTING.md): preparo do ambiente e leitura de throughput/latência

## Variáveis essenciais por serviço

### API

- `DATABASE_URL`
- `ENVIRONMENT=production`
- `LOG_JSON=true`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `VALIDATE_TWILIO_SIGNATURE=true`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WEBHOOK_URL`
- `INTERNAL_SERVICE_TOKEN`
- `MEMORY_ENABLED`, `EMBEDDING_MODEL`, `EMBEDDING_DIMS` quando memória semântica estiver ativa

### Worker

- `DATABASE_URL`
- `ENVIRONMENT=production`
- `LOG_JSON=true`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_MODEL`
- `OPENROUTER_MIDIA_MODEL`
- `TWILIO_OUTBOUND_MODE=real`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_API_KEY_SID`
- `TWILIO_API_KEY_SECRET`
- `TWILIO_FROM_NUMBER`

> Em `TWILIO_OUTBOUND_MODE=real`, o worker encerra no boot se as credenciais
> outbound do Twilio estiverem ausentes.

### Frontend

- `ENVIRONMENT=production`
- `DATABASE_URL`
- `INTERNAL_API_URL`
- `INTERNAL_SERVICE_TOKEN`
- `BETTER_AUTH_SECRET`
- `BETTER_AUTH_URL`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

## Fluxo recomendado de publicacao

1. Provisionar `db`, `api`, `worker` e `frontend`.
2. Configurar as variáveis de ambiente por serviço.
3. Publicar domínio da API e do Frontend.
4. Configurar o webhook do Twilio apontando para `https://<api>/webhook/twilio?agent=rhawk_assistant`.
5. Definir `ADMIN_EMAIL` e `ADMIN_PASSWORD` no Frontend, acessar `/login`, validar o bootstrap automático do primeiro admin e trocar a senha em `/settings`.
6. Executar smoke tests de API, painel e mensagem real no WhatsApp.

## Checklist de verificação

- `GET /health` responde `200`
- `/login` renderiza corretamente no Frontend
- request com assinatura inválida retorna `403` quando a validação está habilitada
- `message_queue` recebe mensagens e o worker faz `queued -> processing -> done|failed`
- a resposta chega ao WhatsApp antes de `mark_done`
- o Frontend acessa `/api/*` apenas via `INTERNAL_SERVICE_TOKEN`
- não existe endpoint público de signup habilitado em production

### Cutover: sandbox → produção

Referência detalhada em [TWILIO.md — Parte B](TWILIO.md#parte-b--número-real--produção).

Resumo dos passos críticos:

1. Adquirir número WhatsApp Business no Twilio
2. Atualizar `TWILIO_FROM_NUMBER` com o número real
3. Atualizar `TWILIO_WEBHOOK_URL` com o domínio Railway da API
4. Habilitar `VALIDATE_TWILIO_SIGNATURE=true`
5. Configurar webhook no Twilio Console (Messaging → WhatsApp Senders)
6. Testar envio e recebimento com número real
7. Validar assinatura em produção

### Rollback

Três níveis de rollback disponíveis:

**Nível 1 — Rollback de deploy (Railway)**
- Railway mantém histórico de deploys por serviço
- No dashboard: Service → Deployments → selecionar deploy anterior → Redeploy
- Útil quando um deploy quebrou a API ou o Worker

**Nível 2 — Rollback Twilio (produção → sandbox)**
- Reconfigurar webhook no Twilio Console para apontar de volta ao túnel local
- Reverter `TWILIO_FROM_NUMBER` para o número do sandbox
- Reverter `VALIDATE_TWILIO_SIGNATURE=false` se necessário
- Detalhes em [TWILIO.md — Troubleshooting](TWILIO.md#rollback-produção--sandbox)

**Nível 3 — Rollback completo**
- Combina nível 1 + nível 2
- Usar quando tanto o deploy quanto a configuração Twilio precisam reverter

## Notas operacionais

- Em `ENVIRONMENT=production`, o endpoint `/webhook/sync` fica desabilitado.
- `TWILIO_OUTBOUND_MODE=mock` e útil para desenvolvimento local e stress test sem custo real.
- Em qualquer ambiente, o painel falha cedo se `INTERNAL_SERVICE_TOKEN` ou `BETTER_AUTH_SECRET` estiverem ausentes; em production, também exige valores fortes.
- Se `auth."user"` estiver vazio, o primeiro acesso ao `/login` cria o admin automaticamente a partir de `ADMIN_EMAIL` e `ADMIN_PASSWORD`.
- O guia detalhado de Railway fica em [RAILWAY.md](RAILWAY.md); este arquivo é a visão geral.

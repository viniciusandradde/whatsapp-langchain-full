# Deploy

Este guia resume o deploy do projeto e aponta para os documentos detalhados
de operação.

## Estado atual

Hoje o projeto cobre:
- API FastAPI pública para `POST /webhook/evolution` e `POST /webhook/waba`
- Worker assíncrono com envio outbound multi-provider (WABA / Evolution)
- Frontend/admin panel em Next.js 16 com Better Auth
- PostgreSQL com pgvector
- **deploy primário em Dokploy (Docker Compose) em Oracle Cloud** (`chat.vsanexus.com`); Railway é alternativa de referência
- stress testing e leitura de gargalos
- documentação final com separação clara entre sandbox e produção
- white-label por empresa no frontend (logo + nome + cores)

## Topologia alvo

```text
Internet -> Frontend (público)
Internet -> API (pública para /health e /webhook/*)
Provider (Evolution/Meta) -> API (webhook inbound)
Frontend -> API (server-side via INTERNAL_API_URL + INTERNAL_SERVICE_TOKEN)
API -> PostgreSQL
Worker -> PostgreSQL
Frontend -> PostgreSQL (schema auth)
Worker -> Provider da conexão (outbound)
```

## Guias detalhados

- [Dokploy](DOKPLOY.md): deploy primário (Compose único no Oracle Cloud + Traefik + Let's Encrypt)
- [Railway](RAILWAY.md): alternativa — provisionamento de serviços, rede interna, variáveis e watch paths
- [Evolution](EVOLUTION.md): provider Evolution API (webhook + outbound)
- [WABA / Meta](WABA_SETUP.md): Embedded Signup, config_id, webhook e troubleshooting
- [Stress Testing](STRESS_TESTING.md): preparo do ambiente e leitura de throughput/latência

## Variáveis essenciais por serviço

### API

- `DATABASE_URL`
- `ENVIRONMENT=production`
- `LOG_JSON=true`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `DATABASE_URL_APP` (role `chat_nexus_app` — sem ele o RLS fica inerte)
- `FRONTEND_ORIGINS`
- `META_APP_SECRET` e `WABA_WEBHOOK_VERIFY_TOKEN` (quando houver conexão WABA)
- `EVOLUTION_VALIDATE_APIKEY=true` (quando o envio for real)
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
- `EVOLUTION_OUTBOUND_MODE=real`
- `EVOLUTION_API_URL` e `EVOLUTION_GLOBAL_API_KEY`

> As credenciais por-conexão (instância, token WABA) ficam cifradas no banco e
> são cadastradas pela UI em **Conexões** — não vão no env.

### Frontend

- `ENVIRONMENT=production`
- `DATABASE_URL`
- `INTERNAL_API_URL`
- `INTERNAL_SERVICE_TOKEN`
- `BETTER_AUTH_SECRET`
- `BETTER_AUTH_URL`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

> **⚠️ `INTERNAL_API_URL` é build arg, não só env de runtime.** O frontend serve
> `/uploads/avatars/*` e `/uploads/logos/*` via `next.config.ts::rewrites()`, que
> proxia pra `INTERNAL_API_URL`. Como o build é `output: "standalone"`, a destination
> do rewrite **é congelada no route-manifest em BUILD time** — então `INTERNAL_API_URL`
> precisa existir no `npm run build`. Por isso é passado como `ARG` no
> `Dockerfile.frontend` (+ `build.args` no compose), não apenas como env de runtime.
> Sem o ARG, cai no fallback `http://localhost:8000` e o proxy de uploads (avatares +
> logos white-label) quebra com `ECONNREFUSED` (500) em produção.

## Fluxo recomendado de publicacao

1. Provisionar `db`, `api`, `worker` e `frontend`.
2. Configurar as variáveis de ambiente por serviço.
3. Publicar domínio da API e do Frontend.
4. Cadastrar a conexão pela UI (**Conexões**) e apontar o webhook do provider para `https://<api>/webhook/evolution` (ou `/webhook/waba`).
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

### Cutover para número real

Referência detalhada em [WABA_SETUP.md](WABA_SETUP.md) (Meta) ou
[EVOLUTION.md](EVOLUTION.md) (Baileys).

Resumo dos passos críticos:

1. Cadastrar a conexão pela UI — o número vive na tabela `conexao`, não no env
2. Apontar o webhook do provider para o domínio público da API
3. Habilitar a validação de assinatura (`META_APP_SECRET` no WABA,
   `EVOLUTION_VALIDATE_APIKEY=true` na Evolution)
4. Testar envio e recebimento com número real
5. Conferir nos logs que a assinatura está sendo validada

### Rollback

Três níveis de rollback disponíveis:

**Nível 1 — Rollback de deploy (Railway)**
- Railway mantém histórico de deploys por serviço
- No dashboard: Service → Deployments → selecionar deploy anterior → Redeploy
- Útil quando um deploy quebrou a API ou o Worker

**Nível 2 — Rollback de conexão**
- Desativar a conexão problemática pela UI (**Conexões** → status `disabled`)
- Reapontar o webhook do provider para o ambiente anterior
- O histórico de atendimento sobrevive: desde a migration `129` a FK é
  `ON DELETE SET NULL` com snapshot do canal

**Nível 3 — Rollback completo**
- Combina nível 1 + nível 2
- Usar quando tanto o deploy quanto a configuração do provider precisam reverter

## Hardening de produção

Em `ENVIRONMENT=production` o startup faz fail-fast nestes casos:

- `INTERNAL_SERVICE_TOKEN` vazio ou com menos de 32 caracteres
- `FRONTEND_ORIGINS` vazio (precisa ter pelo menos uma origem permitida)
- `DATABASE_URL_APP` vazio (sem ele o runtime conecta com bypass de RLS)
- `EVOLUTION_OUTBOUND_MODE=real` sem `EVOLUTION_VALIDATE_APIKEY=true`

Variáveis adicionais a configurar:

- `FRONTEND_ORIGINS` — lista CSV de origens permitidas (ex: `https://chat.nexus.com`)
- `META_APP_SECRET` — valida o HMAC-SHA256 do webhook WABA
- `EVOLUTION_VALIDATE_APIKEY` — exige o header `apikey` no webhook Evolution

Cabeçalhos de segurança aplicados automaticamente:

| Header | Dev | Prod |
|--------|-----|------|
| X-Content-Type-Options: nosniff | ✓ | ✓ |
| X-Frame-Options: DENY | ✓ | ✓ |
| Referrer-Policy: no-referrer | ✓ | ✓ |
| Strict-Transport-Security | — | ✓ (max-age=1y) |

## Notas operacionais

- Em `ENVIRONMENT=production`, o endpoint `/webhook/sync` fica desabilitado.
- `EVOLUTION_OUTBOUND_MODE=mock` é útil para desenvolvimento local e stress test sem mandar mensagem de verdade.
- Em qualquer ambiente, o painel falha cedo se `INTERNAL_SERVICE_TOKEN` ou `BETTER_AUTH_SECRET` estiverem ausentes; em production, também exige valores fortes.
- Se `auth."user"` estiver vazio, o primeiro acesso ao `/login` cria o admin automaticamente a partir de `ADMIN_EMAIL` e `ADMIN_PASSWORD`.
- O guia detalhado do deploy primário fica em [DOKPLOY.md](DOKPLOY.md); a alternativa Railway em [RAILWAY.md](RAILWAY.md). Este arquivo é a visão geral.

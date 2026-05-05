# Webscap — ZigChat inventory scraper

Inventário automatizado de **ZigChat** (Angular + GraphQL) que serve de
referência pro **Nexus Chat AI**. Captura schema GraphQL completo,
operações em runtime, rotas, screenshots e gera **coverage report**
cruzando com as migrations do Nexus pra mostrar o gap real.

## O que mudou da v0.1 (legacy/playwright)

Antiga `webscap/playwright/` continua em `webscap/legacy/` pra rollback.
Esta v0.2 entrega:

- **TypeScript end-to-end** com tipos pros artefatos (schema, ops, coverage).
- **SDL formatter**: `schema.json` vira `schema.graphql` canônico (diff line-by-line, ferramentas GraphQL consomem direto).
- **Operation collector**: dedupe + categorização por entidade (50 chamadas de `getCliente` viram 1 com 50 occurrences).
- **Payload sampler**: 1 exemplo real de `variables` + `responseKeys` por operation, em arquivos JSON separados.
- **Coverage report**: cruza ops categorizadas com `db/migrations/*.sql` do Nexus → markdown com `covered / partial / missing`.
- **Output timestamped**: cada run em `output/runs/<YYYY-MM-DD_HHMMSS>/` + symlink `output/latest`.
- **Rate limiter** (token bucket) + **retry exponencial** (com jitter) + **session guard** (detecta storageState expirado antes de gastar tempo).
- **Auto route discovery** via DOM walk (`<a href>` + `[routerLink]`); fallback estático se discovery vazio.
- **HAR export** opcional (`ENABLE_HAR=true`).
- **Tests** (vitest) cobrindo SDL, dedupe/categorize, coverage builder e retry.

## Setup

Node 20+. Playwright `1.49+`.

```bash
nvm use 20
npm install
npx playwright install chromium
```

Ou via container Microsoft (sem precisar instalar nada local):

```bash
docker run --rm -it --network=host \
  -v "$PWD":/work -w /work \
  mcr.microsoft.com/playwright:v1.49.1-jammy bash
npm install
```

## Uso típico

```bash
# 1. Login manual (1× por máquina, headed) — gera auth.json
npm run login

# 2. Schema completo via introspection (rápido, ~30s)
npm run introspect

# 3. Captura de operações em runtime (varre rotas, intercepta GraphQL,
#    screenshots, dedupe). ~5min com 10-20 rotas.
npm run capture

# 4. Coverage report contra Nexus migrations (lê output/latest)
npm run coverage

# Tudo de uma vez (passos 2-4)
npm run all
```

Saída fica em:

```
output/
├── runs/
│   └── 2026-05-05_180000/
│       ├── schema.graphql           # SDL canônico
│       ├── schema.json              # raw introspection
│       ├── operations.json          # dedupe + categorias
│       ├── payloads/<op>.json       # 1 exemplo de cada op
│       ├── routes.json              # rotas visitadas + status
│       ├── screenshots/<rota>.png
│       └── har/session.har          # se ENABLE_HAR=true
├── latest -> runs/2026-05-05_180000  # symlink
└── coverage.md                       # gap analysis Nexus
```

## Variáveis de ambiente (override do default)

| Var | Default | Descrição |
|---|---|---|
| `BASE_URL` | `https://dev.zigchat.com.br` | Alvo |
| `AUTH_FILE` | `auth.json` | Storage state file |
| `OUTPUT_DIR` | `output` | Onde salvar runs |
| `GQL_PATH` | `/api/graphql` | Endpoint GraphQL (path relativo) |
| `LOG_LEVEL` | `info` | `debug \| info \| warn \| error` |
| `ENABLE_HAR` | `false` | Exporta HAR (pesa ~10MB por sessão) |
| `DISCOVER_ROUTES` | `true` | Auto-descobre via DOM (`false` usa estático) |
| `NEXUS_MIGRATIONS_DIR` | `../db/migrations` | Pra coverage report |

## Arquitetura

```
src/
├── auth/               # login interativo + session guard
├── crawler/            # route discovery + visitor (com retry+limiter)
├── graphql/            # introspect + SDL formatter + op collector + sampler
├── network/            # interceptor + rate limiter + HAR export
├── reporting/          # coverage report + inventory MD
├── lib/                # logger, output paths timestamped, retry helper
├── cli/                # entry points (npm run *)
└── types.ts            # tipos compartilhados
```

### Rate limiting

Token bucket (default 2 RPS). Configura via `DEFAULT_CONFIG.rateLimitRps`
em `types.ts`. Crawler chama `limiter.acquire()` antes de cada `goto`.
Pra rodar mais rápido em alvo próprio (sem 429), suba pra 5-10 RPS.

### Retry exponencial

`lib/retry.ts::withRetry()`. Backoff exponencial com jitter ±20%, cap
em 30s. Por padrão retenta apenas em flake de rede (timeout/ECONNRESET)
ou status 408/425/429/5xx — erros 4xx não-retryable propagam imediato.

### Session guard

Antes de qualquer crawl, `auth/session-guard.ts::checkSession()` faz:
1. Ping HTTP via `fetch` na rota GraphQL — se 401/403, sessão morta.
2. Navegação rápida pra `/dashboard` — se redireciona pra `/login`,
   sessão morta.

Falha sai com exit code 2 e instrução pra rodar `npm run login`.

### Coverage report

`reporting/coverage-report.ts` lê `db/migrations/*.sql` (regex `CREATE TABLE`),
extrai entidades + heurística de count de colunas. Cruza com categorias
das ops ZigChat (mapeamento em `CATEGORY_TO_TABLE`). Status:

- **covered**: tabela existe e ops fazem sentido
- **partial**: tabela existe mas muitas ops vs poucas colunas (gap de campos)
- **missing**: sem tabela equivalente

O markdown final em `output/coverage.md` ordena missing primeiro pra
priorizar backlog.

## Tests

```bash
npm test
```

Cobre SDL formatter, operation collector (categorize/dedupe/groupByCategory),
coverage builder e retry helper. Sem dependência de Playwright nos tests
(unit puro).

## Ética e limites

- Sessão usada é **a sua**, autenticada manualmente. Não automatize
  login/captcha bypass — viola Terms of Use.
- Use só pra mapeamento próprio (gap analysis, schema reference).
- **Não** publique `auth.json` ou outputs em repositórios públicos —
  contêm IDs/cookies/dados de tenant.
- Schema de dados não é protegido por copyright; código fonte e
  texto literal de UI são. Use o coverage como **referência arquitetural**,
  não como template pra copiar.

## Roadmap futuro

- **F3** (próximo): schema-diff entre runs + changelog markdown + GitHub
  Action nightly + alerta quando schema do alvo muda.
- **F4**: flow runner declarativo (YAML) pra reproduzir cenários
  completos (criar cliente → enviar msg → fechar) capturando payloads
  por step. Visual diff (pixelmatch) pra detectar redesign.

Detalhes no plano `/home/opc/.claude/plans/`.

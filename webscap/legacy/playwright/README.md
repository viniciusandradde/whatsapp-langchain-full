# ZigChat Scrap — Playwright + GraphQL

Inventário automatizado do ZigChat (Angular + GraphQL) pra servir de
referência ao **Nexus Chat AI**. Captura rotas, componentes PrimeNG,
operações GraphQL em runtime e o schema completo via introspection.

## Pré-requisito

Node 20+ (Playwright `1.49+` exige). Tem 3 caminhos:

### A) Local (recomendado)

```bash
nvm use 20
npm install
npx playwright install chromium
```

### B) Container Playwright

```bash
docker run --rm -it --network=host \
  -v "$PWD":/work -w /work \
  mcr.microsoft.com/playwright:v1.49.1-jammy bash
# dentro do container:
npm install
```

### C) Servidor sem display (só capture/introspect, sem login)

`login.js` precisa de display X11. Use o caminho A no seu PC, copie o
`auth.json` resultante pro servidor, rode `capture.js` ou
`graphql-introspect.js` headless.

## Uso

```bash
# 1) Logar manualmente (1x por máquina) — abre browser, espera Enter
npm run login

# 2) Varrer rotas + interceptar GraphQL → output/inventory.json + shots
npm run capture

# 3) Introspecção do schema → output/schema.json + schema-summary.txt
npm run graphql:introspect
```

## Saída

```
output/
├── inventory.json           # rotas, componentes, gqlOps, flows
├── shot__dashboard_panel.png
├── shot__dashboard_atendimento.png
├── ...
├── schema.json              # schema GraphQL bruto
└── schema-summary.txt       # queries + mutations resumidos
```

## Ética / Termos

A sessão pertence ao usuário autenticado. Use só pra mapeamento próprio
(análise de stack pra construir alternativa) e respeite os Termos de
Uso da plataforma. Não publique o `auth.json` nem os outputs em
público.

## Próximos passos depois do capture

1. Diff do schema vs nosso modelo (`/main/db/migrations/`).
2. Cross-ref de operações GraphQL com endpoints REST equivalentes que
   queremos no Nexus Chat AI.
3. Identificar entidades-chave (Empresa, Usuario, Cliente, Atendimento,
   Conexao, Campanha) e desenhar schema Postgres.

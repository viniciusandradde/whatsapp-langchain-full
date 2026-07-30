# Chatvolt — fontes

**Data de acesso de todas as fontes: 2026-07-28.**

## Método de coleta

`docs.chatvolt.ai` roda **Mintlify sobre Next.js**. O conteúdo é renderizado no
cliente, então `curl` na URL devolve o shell da SPA — foi o que aconteceu na
primeira tentativa, e é a razão de o site institucional (`www.chatvolt.ai`, Vite
+ react-router) não ter rendido nada útil por HTTP direto.

Caminho que funcionou:

1. **Árvore de navegação** — `__NEXT_DATA__` de qualquer página contém
   `props.pageProps.pageData.mintConfig.navigation`, com a lista completa de
   páginas. Rendeu **168 páginas**.
2. **Conteúdo** — rota de dados do Next: `/_next/data/<buildId>/<page>.json`.
   O `buildId` sai do mesmo `__NEXT_DATA__` (na coleta: `rteXURCv5KFNJ8Q6lEEmq`).
   Cada resposta traz:
   - `pageProps.pageData.apiReferenceData.endpoint` — **operação OpenAPI completa**
     (path, método, parâmetros, body, respostas, security)
   - `pageProps.mdxSource.compiledSource` — MDX compilado; a prosa é extraída dos
     literais em posição `children:`
3. **Limpeza** — deduplicação de blocos repetidos (o Mintlify emite o conteúdo
   mais de uma vez por causa de componentes tipo Card/Accordion) e remoção do
   ruído de syntax highlight. Reduziu 1,58 MB → 782 KB.

Resultado: **168/168 páginas coletadas, zero erros.**

### O que não funcionou

- `llms.txt`, `sitemap.xml` e `openapi/*.yaml` (os 11 specs referenciados no
  `mintConfig`) retornam **o shell da SPA com status 200** — o Mintlify serve a
  página de introdução como fallback para rota desconhecida. Sinal de alerta
  geral: **HTTP 200 não significa que veio o recurso pedido**; sempre conferir
  o tamanho e o primeiro byte.
- `WebFetch` na home institucional retornou só o `<title>`.

### Introspecção autenticada

Chamadas `GET` contra `https://api.chatvolt.ai` com chave de API de conta de
teste, fornecida pelo dono da conta. **Somente leitura** — nenhuma escrita.

| Endpoint | Status | Retorno |
|---|---|---|
| `/datastores/list` | 200 | 1 datastore — **única resposta com dados reais** |
| `/contacts` | 200 | vazio |
| `/conversation` | 200 | vazio |
| `/crm/scenario` | 200 | vazio |
| `/dispatches` | 200 | vazio |
| `/dispatches/contacts/lists` | 200 | vazio |
| `/artifacts` | 200 | vazio |
| `/whatsapp/templates` | 400 | exige parâmetro |
| `/agent-blacklist` | 404 | — |

A conta foi criada no mesmo dia da coleta e está praticamente vazia, então a
introspecção confirmou **formato** (campos, tipos, IDs, paginação), não volume
nem comportamento sob uso.

Credenciais não constam destes documentos.

### Tabela de planos

Extraída do bundle JavaScript da landing (`/assets/index-*.js`), onde o objeto de
planos está literal no código. Preços, limites e features por degrau são valores
de produção, não estimativa.

### Rotas do painel — `_buildManifest.js`

O painel (`app.chatvolt.ai`) é Next.js e publica a lista completa de rotas no
manifesto de build, **sem exigir autenticação**:

```bash
curl -s https://app.chatvolt.ai/auth/signin | grep -oE '"buildId":"[^"]+"'
curl -s https://app.chatvolt.ai/_next/static/<buildId>/_buildManifest.js
```

Na coleta: `buildId=fclnaS2B_QQynYrcJqYl0`, 77 entradas, 51 rotas de página.

Foi a fonte mais produtiva depois da API, porque revelou **módulos que a
documentação não menciona**: `/analytics` (com `CreditsAuditTab` e
`FiltersAnalytics`), `/custom-dashboard`, `/forms`, `/apps`, `/partner-set`,
`/integrations/crisp/*`, `/onboarding`. Detalhes em
[`01-mapa-funcional.md`](01-mapa-funcional.md#13-módulos-não-documentados).

Lição geral: **em SPA, o manifesto de build é inventário de funcionalidade.**
Vale rodar antes de qualquer captura de tela — dá o mapa e evita chutar URL.

### Capturas de tela

Scripts em `scripts/capture_benchmark_screens.py` (VPS, páginas públicas) e
`scripts/capture_chatvolt_local.py` (PC do operador, painel autenticado).

O Chatvolt **não tem login por senha** — só magic link, código ou Google
(NextAuth). Por isso a captura autenticada não pode rodar sozinha na VPS: o
login acontece uma vez numa janela real e a sessão é reaproveitada via
`storage_state.json`.

Gotcha do host: em ARM/OEL8 o `headless_shell` do Playwright dá **SIGSEGV**; os
scripts passam `channel="chromium"` para usar o build completo, que funciona.

## Documentação — 168 páginas

Todas sob `https://docs.chatvolt.ai/`.

### Visão geral (3)

`introduction` · `platform` · `voltapi/introduction`

### Agente (26)

`agent/get-started` · `agent/tools/quick-start` · `agent/tools/datastore-tool` ·
`agent/tools/http-tool` · `agent/tools/request-human-tool` ·
`agent/tools/mark-as-resolved-tool` · `agent/tools/delayed-responses-tool` ·
`agent/tools/follow-up-messages-tool` · `agent/human-handoff` ·
`agent/fine-tuning` · `agent/conversation-file-upload` · `agent/answer-sources` ·
`agent/message-suggestions` · `agent/optimize-ai-answers` · `agent/rate-limit` ·
`agent/debug` · `agent/prompt-variables` · `agent/whitelist` ·
`agent/elevenLabs-audios` · `agent/transcriptions-with-groq` · `agent/webhooks` ·
`agent/conversation-variables` · `agent/raw-mode` · `agent/fluxvolt-integration` ·
`agent/dispatch` · `agent/zapper-integration`

### Base de conhecimento (1)

`datastore/get-started`

### Flux CRM (2)

`fluxvolt/introduction` · `fluxvolt/step-configuration`

### Artifacts (1)

`artifacts/structure-guide`

### Integrações (10)

`integrations/whatsapp` · `integrations/telegram` · `integrations/instagram` ·
`integrations/twilio` · `integrations/make` · `integrations/google-drive` ·
`integrations/mercadolivre` · `integrations/slack` · `integrations/youtube` ·
`integrations/zapper`

### Widgets (3)

`widgets/chatbot/bubble` · `widgets/chatbot/standard` · `widgets/chatbot/reference`

### Permissões (1)

`others/user-permissions`

### API — referência (113)

`api-reference/authentication` mais 112 páginas de endpoint sob
`api-reference/endpoint/`, agrupadas em: agents (6), agent tools (4),
whitelist (4), blacklist (4), conversation (19), contacts (6), dispatches (13),
artifacts (17), datastores/datasources (10), whatsapp (9), crm (15),
zapi/zapper/twilio/mercadolivre (4).

Lista completa em `cv_api_surface.txt` no material de coleta; superfície
organizada em [`02-api-e-integracoes.md`](02-api-e-integracoes.md).

### Termos e privacidade (8)

`privacy/lgpd` · `privacy/br-lgpd` · `privacy/cookie-policy` ·
`privacy/br-cookie-policy` · `privacy/privacy-policy` ·
`privacy/br-privacy-policy` · `privacy/terms` · `privacy/br-terms`

## Site institucional

| URL | Uso |
|---|---|
| `https://www.chatvolt.ai/` | Posicionamento, meta description |
| `https://www.chatvolt.ai/pricing` | Planos (via bundle JS) |
| `https://www.chatvolt.ai/en-US` | Versão em inglês |
| `https://app.chatvolt.ai/` | Painel — URLs de navegação citadas na doc |

## Fontes secundárias — não usadas como evidência

Localizadas em busca, **não** utilizadas para afirmar funcionalidade (ver regra
de evidência no [README](../../README.md)):

- Canal no YouTube com curso gratuito ("CURSO GRATUITO CHATVOLT", aulas #1 e #4)
- Entrevista: "Ele criou um dos maiores SaaS de Agentes IA do Brasil (Chatvolt)"
- Instagram `@chatvolt`, LinkedIn `br.linkedin.com/company/chatvolt`
- `https://apps.make.com/chatvolt-ai` — listagem do app no Make

São úteis para captura de UX (fluxo 04) e leitura de go-to-market, não para
mapa funcional.

## Reprodutibilidade

O `buildId` do Mintlify **muda a cada deploy** da documentação. Para recoletar:

1. `curl -sL https://docs.chatvolt.ai/introduction` e extrair `buildId` +
   `mintConfig.navigation` do `__NEXT_DATA__`
2. Iterar as páginas em `/_next/data/<buildId>/<page>.json`
3. Diffar contra a coleta anterior para achar o que mudou

Vale versionar apenas o índice de páginas (`cv_pages.txt`) — o diff dele já
mostra funcionalidade nova antes de qualquer anúncio.

## Limitações desta coleta

Registradas para que ninguém leia a análise como mais completa do que é:

1. **Sem captura do painel autenticado.** A leitura de UX é reconstrução a
   partir da doc e das rotas. As telas pendentes estão listadas em
   [`04-ux-flows.md`](04-ux-flows.md#pendentes-), com script pronto para
   capturá-las.
2. **Analytics: existe, profundidade desconhecida.** O manifesto confirma
   `/analytics` com filtros e auditoria de créditos, mas sem a tela não dá para
   dizer quais métricas nem se exporta. *(Antes desta coleta, eu havia marcado
   como "não avaliável" — o manifesto corrigiu pela metade.)*
3. **Módulos identificados mas não explorados.** `/forms`, `/apps`,
   `/partner-set`, `/custom-dashboard` e a integração Crisp existem como rota;
   o que fazem é inferência.
4. **Conta de teste vazia.** Confirmou schema, não comportamento.
5. **Lista de modelos LLM não verificada.** A alegação de "50+" e os nomes
   citados na doc estão desatualizados; o endpoint que os lista não é público.
6. **Sem teste de carga, latência ou confiabilidade.** Análise puramente
   funcional.

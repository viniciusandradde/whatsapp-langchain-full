# ADR-003 — Data fetching no painel: TanStack Query sobre Server Actions

- **Status:** aceita — 2026-09-16 (piloto no dev: fila `/atendimento`)
- **Decisores:** Vinicius (dono) + incidente de produção 16/09
- **Código:** `components/query-provider.tsx`, `app/atendimento/{page,atendimento-list,fila-live,actions}.tsx`
- **Referência:** blueprint `docs/one-for-all-main/` (tríade types → service → queries),
  `docs/ANALISE_BLUEPRINT_ONE_FOR_ALL.md`

## Contexto

O painel atualizava a fila viva com `router.refresh()`: cada evento SSE re-executava os **quatro fetches**
da página inteira (`getAtendimentos`, `getDepartamentos`, `getMyAbas`, `getContadores`), sem cache, sem
dedupe entre abas e sem backoff.

Em **16/09/2026** isso produziu **1.073 requisições/minuto de um único operador**, estourando o rate limit
(600/min) e travando o painel em "Muitas ações em pouco tempo". Como a janela do limite é fixa por minuto,
o próprio cliente impedia a recuperação — só destravava fechando as abas. O paliativo (PR #131) foi um
**circuit breaker escrito à mão**: teto de refresh por janela, backoff e pausa ao carregar em erro.

O blueprint `one-for-all` resolve isso por arquitetura: TanStack Query com invalidação por chave.

## Decisões

1. **TanStack Query é a camada de leitura do painel.** O evento SSE passa a chamar
   `invalidateQueries({ queryKey: ["atendimentos"] })` — revalida **uma lista**, não a página. Custo por
   evento: de 4 requests para 1.

2. **A `queryFn` chama Server Action ou `/api/proxy/*` — nunca a API direto.** Esta é a adaptação
   obrigatória e o ponto mais importante do ADR: o blueprint usa `axios` no browser, o que no Nexus
   **vazaria o `INTERNAL_SERVICE_TOKEN`** (server-only, e que autentica qualquer chamada em `/api/*`).
   Copiar o `api.ts` do blueprint é proibido.

3. **SSR preservado.** O Server Component continua renderizando o primeiro estado e o passa como
   `initialData` — sem flash, sem refetch no mount. A `queryKey` inclui os filtros, então trocar de filtro
   é outra chave com outro `initialData`.

4. **Defaults conservadores.** `refetchOnWindowFocus: false` (ligá-lo recriaria a tempestade: o operador
   alterna abas o dia inteiro), `staleTime` 10s, e `retry` que **recua no 429** com backoff exponencial
   em vez de insistir. Erro de permissão/sessão não é retentado.

5. **O circuit breaker permanece.** Redundante com o backoff do Query, mas é defesa em profundidade e já
   provou valor em produção.

6. **SSE continua sendo o transporte.** Query substitui o *refresh*, não o canal de eventos. Trocar por
   socket.io foi **rejeitado**: não resolve o gargalo real, que é **1 conexão Postgres dedicada por
   operador** no `LISTEN` (`max_connections=100` → teto de ~80-90 operadores). Isso se resolve
   multiplexando o LISTEN (um por processo + fan-out em memória) e com PgBouncer — vale para SSE ou
   WebSocket. É trabalho de infra, fora deste ADR.

7. **Adoção incremental, por tela.** São 106 componentes client e 46 arquivos de Server Actions. Query e
   Server Actions **convivem** (a action vira a `queryFn`). Piloto: a fila `/atendimento`, onde a dor foi
   medida. Métrica de sucesso: requisições/minuto por operador e ausência de 429 com várias abas abertas.

## Consequências

- **Positivas:** menos carga por evento; dedupe entre componentes e abas; backoff nativo; navegação entre
  filtros mais rápida (cache); o padrão do blueprint (tríade + invalidação) passa a estar disponível.
- **Negativas:** uma dependência a mais no bundle; duas formas de buscar dados convivendo durante a
  migração; risco de alguém "simplificar" chamando a API direto do cliente — daí a decisão 2 ser explícita.
- **Não adotado do blueprint:** `axios` no cliente (segurança), PocketBase, socket.io, PDF/XLSX no cliente
  (o backend já gera, com cap de linhas e envio por WhatsApp).

## Resultado do piloto (medido no dev, 2026-09-17)

Medição pelo `rate_limit_bucket` (requisições/min por usuário na API) e pelo access log do uvicorn
(ligado só no container do dev). Um único usuário, `/atendimento`.

| Cenário | Antes | Depois |
|---|---|---|
| 1 aba parada, sem evento | 32 req/min | **4 req/min** |
| 4 abas + 6 mensagens chegando em 1 min (teste do dono) | 401 / 224 req/min | **56 req/min**, 0 × 429 |
| Custo de 1 evento SSE, por aba | 4 fetches (página inteira) | 1 (`GET /api/atendimentos`) |

O piloto (`invalidateQueries` no lugar de `router.refresh()`) funcionava desde o primeiro dia, mas
**dois problemas fora dele escondiam o ganho** — e são o achado de verdade desta medição:

1. **`nextCookies()` do Better Auth 1.5.4 re-renderizava a rota em toda Server Action.** O plugin
   sondava se podia escrever cookie com `cookies().set(...); cookies().delete(...)` no `before` de
   `/get-session`. Dentro de uma Server Action a sonda funciona — e deixa `mutableCookies` marcado como
   modificado. O Next 16 então trata a action como revalidada (`x-action-revalidated: 1`) e devolve
   layout + página re-renderizados na resposta: **7 fetches de API** (`empresas`, `perfis/me`,
   `departamentos`, `auth/me/admin`, `abas/me`, `contadores`, `atendimentos`) por action, inclusive
   nas periódicas (`loadContadoresAction` a cada 30 s). Todo `apiFetch` passa por `getSession()`, então
   **toda** action pagava isso. Corrigido upstream na 1.6.2 (detecção de RSC por header, sem sonda);
   o Nexus foi para a 1.6.33 — sem migração (tabelas core idênticas), única breaking (`freshAge`) em
   endpoints que o painel não usa.
2. **Re-prefetch de todos os `<Link>` visíveis depois de cada action.** Com o cache do router
   invalidado, o Next refazia o prefetch das 5 abas da fila e das 6 rotas do menu = 11 renders de
   página no servidor, cada um com seus fetches. `prefetch={false}` nesses links (prefetch só ao
   passar o mouse) cortou o lado do browser de 63 para 6 req/min.

Lições para as próximas telas:

- **Medir na API, não no browser.** O DevTools do browser mostrava 6 req/min enquanto a API recebia
  32: o custo estava no render server-side que a action carregava de carona.
- Qualquer coisa que mute cookie dentro de uma Server Action (inclusive biblioteca) custa um re-render
  da rota inteira. Vale para `setActiveEmpresa` (esperado) e valia, sem querer, para o Better Auth.
- Custo por evento agora é **1 request por aba**: N abas do mesmo operador = N requests. Se virar
  problema, o próximo passo é sincronizar o cache entre abas (`broadcastQueryClient`), não voltar
  ao refresh.
- A conexão SSE continua 1 por aba (e 1 `LISTEN` no Postgres por aba) — é o gargalo de capacidade
  da decisão 6, fora deste ADR.

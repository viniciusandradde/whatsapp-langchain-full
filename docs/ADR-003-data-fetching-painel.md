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

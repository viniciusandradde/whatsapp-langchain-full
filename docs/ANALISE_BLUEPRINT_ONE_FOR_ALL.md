# Análise do blueprint `one-for-all` → melhorias para o Nexus

Documento de análise (2026-09-16). Fonte: `docs/one-for-all-main/` — projeto **one-for-all**, monolito Next.js 16 / React 19 do Mackenzie que agrega vários módulos num só app (`intranet`, `badge-maker`, `conversor-icontrol-totvs`, `wareaudit`). 606 arquivos, 11 MB.

Objetivo: usar esse projeto como **blueprint** e extrair o que vale adotar no Chat Nexus — com honestidade sobre o que **não** se aplica.

---

## 1. O que o blueprint faz bem (o padrão canônico)

O núcleo reaproveitável não é a stack em si, é a **tríade padronizada por domínio**, gerada automaticamente:

```
src/types/<feature>/<nome>.ts          →  <Nome>PayloadType / <Nome>ResType
src/lib/shared/services/<nome>Service  →  CRUD: all / byId / create / patch / remove
src/lib/shared/queries/<nome>Queries   →  hooks TanStack Query + invalidação + toast de erro
```

- **Service** concentra o acesso HTTP, com `endpoints` centralizados (`lib/constants/*/endpoints`) — nada de URL solta no componente.
- **Queries** expõe `use<Nome>s`, `use<Nome>ById`, `use<Nome>Create`, `use<Nome>Patch`, `use<Nome>Remove`; toda mutação faz `queryClient.invalidateQueries({ queryKey: [...] })` no `onSuccess` e trata erro por um `mutationErrorHandler` único (toast padronizado).
- **`npm run generate` (Plop)** scaffolda os três arquivos de uma vez — o padrão não depende de disciplina, é gerado.
- Detalhe fino: busca com `useDebounce(params.search, 500)` embutido no próprio hook de query, então a tela não reimplementa debounce.

Organização por **domínio** (`types/<feature>`, `hooks/<feature>`, `components/<feature>`, `lib/db/<feature>`), não por rota.

## 2. Stack: blueprint × Nexus

| Área | one-for-all | Chat Nexus hoje | Vale adotar? |
|---|---|---|---|
| Data fetching | **TanStack Query** (cache, dedupe, invalidação seletiva, retry/backoff) | `router.refresh()` full-page + Server Actions + `apiFetch` | **Sim — P1** |
| Listas longas | **TanStack Virtual** + Table | render direto | **Sim — P2** |
| Lint/format | **Biome** (uma ferramenta) | ESLint (+ gotcha do Prettier) | **Sim — P3** |
| Validação/forms | **Zod 4** + react-hook-form + `@hookform/resolvers` | manual no front; Pydantic no backend | **Sim — P4** |
| Scaffolding | **Plop** (gerador de módulo) | manual | **Sim — P5** |
| Estado client | Zustand | useState/context | Talvez |
| Gráficos | recharts | — | Talvez |
| Editor rico | TipTap (tabelas, cores, links) | — | Nicho (templates) |
| PDF / XLSX | `@react-pdf/renderer`, `xlsx` (client) | gerados no backend | **Não** (manter backend) |
| Realtime | socket.io-client | SSE próprio | **Não** (ver §4) |
| Backend de dados | PocketBase + pg | Postgres + RLS + FastAPI | **Não** |
| React Compiler | `babel-plugin-react-compiler` explícito | já em uso | — |

## 3. Melhorias priorizadas para o Nexus

### P1 — TanStack Query no painel (maior impacto; resolve dor medida)
**Problema real:** em 16/09 a fila viva gerou **1073 req/min de um único usuário** e travou o painel ("Muitas ações em pouco tempo"). A raiz: cada evento SSE dispara `router.refresh()`, que **re-executa os 4 fetches da página inteira** (`/atendimento/page.tsx`), sem cache, sem dedupe e sem backoff — tivemos de escrever um circuit breaker à mão (PR #131).

**Com Query:** o evento SSE passa a chamar `queryClient.invalidateQueries({ queryKey: ["atendimentos"] })` — só a lista revalida; `staleTime` evita refetch redundante; dedupe junta chamadas simultâneas (várias abas/componentes); `retry` com backoff exponencial trata 429 nativamente. É o "refresh incremental" que ficou pendente como fase 2.

**Adaptação obrigatória (não copiar o blueprint ao pé da letra):** o blueprint chama a API direto do browser com `axios`. No Nexus isso **vazaria o `INTERNAL_SERVICE_TOKEN`**, que é `server-only`. A `queryFn` deve chamar **Server Action** (já são 46) ou os **route handlers `/api/proxy/*`** (já existem para mídia, atendentes, tour, RAG). O token nunca sai do servidor.

### P2 — Virtualização das listas longas
`@tanstack/react-virtual` na fila de atendimentos e na timeline de mensagens. Hoje a timeline pagina por cursor, mas renderiza tudo que carrega. Casa diretamente com a meta de escalar operadores/volume.

### P3 — Biome no lugar de ESLint
Uma ferramenta para lint + format, ordens de grandeza mais rápida no CI. Também elimina o risco registrado do **Prettier reformatar o repo inteiro** (o projeto não tem `.prettierrc`): o Biome traz config explícita (`biome.json`) e `biome check` no lugar de duas ferramentas.

### P4 — Zod + react-hook-form nos formulários
Validação declarativa no cliente, espelhando o contrato Pydantic do backend. Hoje os forms do painel validam à mão (ou não validam, e o erro só aparece no 422). Ganho direto em UX de erro — que já é uma diretriz do projeto (mensagem em pt-BR, sem detalhe técnico).

### P5 — Plop (scaffolding) com a suíte E2E embutida
O contrato do projeto exige **Smoke + E2E por feature** (modelo `test_aba_endpoints.py`). Um gerador que crie, além de types/service/queries, o **arquivo de teste no modelo canônico**, transforma uma regra que hoje depende de disciplina em algo gerado por padrão.

### P6 — TanStack Table
Padroniza sort/filtro/paginação em Histórico, Usuários, Campanhas e Relatórios — hoje cada tela reimplementa.

## 4. O que NÃO adotar (e por quê)

- **axios no cliente / services chamando a API direto** — quebra o modelo de segurança do Nexus (token server-only + `verify_service_token`). Manter `apiFetch` server-only + proxies.
- **socket.io** — trocar o transporte **não** resolve o gargalo real de escala: cada operador abre **1 conexão Postgres dedicada** no SSE (`atendimento.py`, `LISTEN`), e o teto é `max_connections`. A solução é **multiplexar o LISTEN** (um por processo + fan-out em memória) e PgBouncer — independente de SSE ou WebSocket.
- **PocketBase** — o Nexus tem Postgres com RLS FORCE, roles e auditoria; não há ganho.
- **Monolito multi-módulo** — o blueprint agrega produtos distintos por conveniência do Mackenzie; o Nexus é um produto só.
- **PDF/XLSX no cliente** — o Nexus já gera no backend (com cap de linhas e envio por WhatsApp); mover para o cliente perderia isso.

## 5. Roadmap sugerido (ondas)

| Onda | Escopo | Por que nessa ordem |
|---|---|---|
| **1** | Biome (P3) + Plop com E2E (P5) + **TanStack Query numa tela piloto: a fila `/atendimento`** (P1) | Ferramentas de base são baratas e sem risco de runtime; a fila é onde a dor foi medida — dá para comparar req/min antes × depois |
| **2** | Query no resto do painel + virtualização (P2) | Depois que o padrão provar na tela mais crítica |
| **3** | Zod + RHF (P4) + TanStack Table (P6) | Refino de formulários e listas |

**Métrica de sucesso da Onda 1:** requisições por minuto por operador na fila (hoje: 4 por evento, com picos que estouraram 600/min) e ausência de 429 com várias abas abertas.

## 6. Riscos e cuidados

- **Migração grande:** são 106 componentes client e 46 arquivos de Server Actions. Não migrar tudo de uma vez — por tela, começando pela fila. Query e Server Actions **convivem** (a action vira a `queryFn`).
- **Não trocar o modelo de auth** no caminho: a tentação de copiar o `api.ts` com axios do blueprint é o maior risco de segurança desta adoção.
- **SSE continua**: Query substitui o *refresh*, não o transporte de eventos. O evento SSE passa a invalidar chaves em vez de recarregar a página.
- **Biome ≠ ESLint** em regras: rodar uma vez em modo check e revisar o diff antes de adotar no CI (evitar reformatação em massa, o mesmo cuidado do Prettier).

---

Ver também: `docs/SEGURANCA.md`, `docs/CUSTO_E_CAPACIDADE.md`, `docs/PRD-FRONTEND.md`.

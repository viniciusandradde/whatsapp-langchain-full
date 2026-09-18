# Inbox agrupado (Claude Design "Inbox Agrupado v2") — agrupamento e funções, mesmo design system

## Context

O dono desenhou no Claude Design a tela `/atendimento` em três colunas (handoff em `Design system VSA Nexus-handoff.zip`, arquivo `project/Inbox Agrupado v2.dc.html`; `support.js` é só o runtime do protótipo e `assets/vsa-logo.png` já existe no front). Decisão dele: **o design system atual se mantém** (tokens, Inter/JetBrains Mono, shadcn sobre Base UI, light default + `.dark`, portão `scripts/ui_metrics.sh --check`) — entram o **agrupamento** e as **funções** do mock, não a paleta escura/Geist.

O que o mock pede e o que já existe:
- **Rail** "Sistema" (Não Resolvidas · Resolvidas · Todas conversas) + "Minhas abas": é a `AtendimentoSidebar` de hoje com 3 itens em vez de 5 (decidido: seguir o mock; `?tipo=nao_lidas` e `?tipo=humano_solicitado` continuam como deep link).
- **Lista agrupada**: busca "Nome, telefone ou protocolo", "Expandir/Recolher tudo", segmentado **Agrupar por Status | Departamento | Responsável**, grupos com cabeçalho sticky (caret, ponto, nome, contagem, não-lidas), card com nome/tempo, telefone · espera · depto, prévia, chips de automação / espera / não-lidas. **Não existe** — hoje é uma `<ul>` plana de 300 px.
- **Conversa inline**: já é `AtendimentoDrawer modo="painel"` (cabeçalho com protocolo/tags/"ver ficha", Painel do cliente, Conversa|Arquivos, Reprocessar com IA, composer com Nota interna/Template, Atender/Devolver à IA/Transferir/Resolver/Abandonar). Faltam duas funções: a conversa selecionada não está na URL (troca de aba a perde) e toda ação de estado fecha o painel.
- **Colunas redimensionáveis** com persistência e duplo-clique: não existe.
- **Chip "SLA"**: não há SLA no backend. Decidido: chip **"Sem resposta há X"** (tempo desde a última mensagem do cliente sem resposta), com faixa de cor — precisa do campo novo `aguardando_desde`.

Dados (levantamento no `master 8e36f8a`): `situacao` (`resposta_perdida|com_ia|aguardando_humano|em_atendimento|sem_automacao|resolvida|abandonada`) já é a regra canônica de automação (`shared/atendimento.py::derivar_situacao`); `nao_lidas`, `ultima_mensagem_preview`, `last_message_at`, `protocolo`, `departamento_id`, `assigned_to_user_id` existem. Faltam `aguardando_desde` e busca por telefone em `q` (só nome/protocolo). Nomes de departamento/atendente resolvem no front (`getDepartamentos` já na page; `loadAtendentesAction` já existe).

Contrato do repo: PRs isoladas a partir de `origin/master`, dev primeiro (rebuild), captura de tela para UI, `prefetch={false}` em todo `<Link>`, só tokens do tema (portão `ui_metrics.sh --check` não pode subir), nunca `git add -A`.

---

## PR A — backend: `aguardando_desde` + busca por telefone (branch `feat/atendimento-aguardando-desde`)

**`src/whatsapp_langchain/shared/atendimento.py`**
- `_preencher_derivados`: a query `DISTINCT ON (atendimento_id)` que já alimenta o preview (última row não-interna, `ORDER BY id DESC`) ganha `created_at`. Nova função pura `derivar_aguardando_desde(incoming_message, response, created_at) -> datetime | None`: última row tem `incoming_message` e o `response` é NULL ou começa com `MARKERS_INTERNOS` (mesma regra do `derivar_preview`) → o cliente falou por último sem resposta → devolve `created_at`; senão `None`. Preenche `atd.aguardando_desde`.
- `list_atendimentos`: `q` com ≥ 4 dígitos também casa `regexp_replace(c.telefone, '\D', '', 'g') ILIKE '%<dígitos>%'` (além de nome/protocolo).
- **`shared/models.py::Atendimento`**: `aguardando_desde: datetime | None = None`.
- Testes: unit da função pura (respondida → None; não respondida → created_at; marker interno conta como não respondida; nota interna já fica fora pela query); E2E `docker_demo` no molde de `tests/integration/test_aba_endpoints.py` (2 rows na `message_queue`: uma respondida, uma não → lista devolve `aguardando_desde` só na segunda; `q=9979` acha pelo telefone).
- Docs: parágrafo "Leva fila de atendimento" do `CLAUDE.md` (campo novo + busca por telefone).

Sem migration. Frontend: `frontend/src/lib/api.ts::Atendimento` ganha `aguardando_desde?: string | null` (na PR B).

---

## PR B — frontend: inbox agrupado (branch `feat/inbox-agrupado`)

### Arquivos novos (`frontend/src/app/atendimento/`)
- **`agrupar.ts`** (puro, sem React): `type ModoAgrupamento = "status" | "departamento" | "responsavel"`; `interface Grupo { id; nome; ponto: string (classe token); itens: Atendimento[]; naoLidas: number }`; `agruparAtendimentos(itens, modo, ctx: { userId; departamentos; atendentes }) : Grupo[]`.
  - **Status** (primeira regra que casar; ordem fixa dos grupos): `meus` = `assigned_to_user_id === userId` e status ativo → "Meus atendimentos" (`bg-brand-primary`); `humano` = `situacao === "aguardando_humano"` → "Humano solicitado" (`bg-destructive`); `fila` = `status === "aguardando"` (situacao `sem_automacao`/`resposta_perdida`) → "Aguardando (fila)" (`bg-warning`); `andamento` = `situacao === "em_atendimento"` → "Em atendimento" (`bg-brand-secondary`); `ia` = `situacao === "com_ia"` → "Com a IA" (`bg-success`); `resolvida`/`abandonada` → "Resolvidas"/"Abandonadas" (só aparecem em `tipo=resolvidas|todas`); resto → "Outros" (defensivo). Grupos vazios não renderizam.
  - **Departamento**: por `departamento_id` → nome via `ctx.departamentos`; "Sem departamento" por último. **Responsável**: por `assigned_to_user_id` → nome via `ctx.atendentes`; "Sem responsável" por último. Ordem alfabética; `naoLidas` = soma de `nao_lidas`.
- **`lista-toolbar.tsx`**: busca (`InputGroup` + ícone, placeholder "Nome, telefone ou protocolo", debounce 300 ms → `router.push("/atendimento?...q=")` preservando os outros params); botão "Expandir tudo"/"Recolher tudo"; segmentado "Agrupar por" (3 `Button size="sm"` num `bg-muted p-0.5 rounded-lg`, ativo `bg-background shadow-sm`). Modo persistido em `localStorage["atd-agrupar-por"]`.
- **`grupo-fila.tsx`**: cabeçalho `sticky top-0 z-10 bg-background/95 backdrop-blur border-b` (botão com caret `ChevronDown` rotacionando `-90deg` fechado, ponto `size-2 rounded-full` com a classe token do grupo, nome `font-mono text-[10px] uppercase tracking-[.14em]`, contagem `text-muted-foreground`, badge não-lidas `bg-destructive text-destructive-foreground` à direita) + filhos quando aberto. Estado aberto/fechado por grupo em `localStorage["atd-grupos-abertos"]` (default: meus/humano/fila abertos, andamento/ia fechados; por departamento/responsável tudo aberto).
- **`card-atendimento.tsx`**: card extraído da `<ul>` atual e reorganizado como no mock — linha 1: ícone do canal (`MessageCircle`), nome `font-medium truncate`, tempo `formatRelative(last_message_at)` mono à direita; linha 2 mono `text-[10px] text-muted-foreground`: telefone · (espera) · departamento; prévia `text-xs truncate`; linha de chips: automação (`SITUACAO_LABEL[situacao]` com classes token novas `SITUACAO_CHIP`), **"Sem resposta há X"** (só quando `aguardando_desde`; faixa: < 1 h `text-muted-foreground bg-muted`, 1–4 h `text-warning bg-warning/10`, > 4 h `text-destructive bg-destructive/10`), não-lidas (`formatarNaoLidas`), ponto de prioridade e `Frown` de sentimento (mantidos), até 3 `cliente_tags` (mantido); selecionado = `border-l-2 border-primary bg-accent`, `aria-current`. Botão "marcar não lida" no hover continua irmão do botão do card (button aninhado é inválido).
- **`src/hooks/use-local-storage.ts`**: `useLocalStorage<T>(chave, inicial)` — `useState(inicial)` + leitura em `useEffect` (sem mismatch de hidratação) + escrita em `try/catch`; substitui os três `localStorage` à mão que a tela tem hoje só onde for tocado.
- **`src/hooks/use-colunas-redimensionaveis.ts`**: larguras `{ lista: 560 }` (rail continua com o colapso próprio da `AtendimentoShell`), alça `onPointerDown` → `pointermove/pointerup` na `window`, `min/max` em px (lista 320–860), `cursor: col-resize` + `user-select: none` no `body` durante o arrasto, persistência `localStorage["atd-larguras"]`, duplo-clique redefine. Sem dependência nova (o `react-resizable-panels` trabalha em % e não casa com os limites em px do mock).

### Arquivos alterados
- **`atendimento-list.tsx`**: passa a orquestrar: `useQuery(["atendimentos", filtros])` (igual), `useQuery(["atendentes"], loadAtendentesAction, staleTime 60 s, enabled só no modo responsável), `agruparAtendimentos(...)`, toolbar + grupos + cards; **conversa na URL**: `ativoId` vem de `useSearchParams().get("id")`, selecionar faz `router.replace` com `?id=` (mantendo os outros params; `scroll:false`); `ativo = atendimentos.find(a => a.id === ativoId) ?? últimoSnapshot` (assim status/dono no cabeçalho acompanham o refetch); alça de redimensionar entre lista e conversa; painel desktop com `key={ativo.id}` e `onAcaoConcluida={() => invalidate(["atendimentos"], ["contadores"])}`; mobile (< 1024) mantém o overlay e a regra "só UM drawer montado" (`isDesktop === false`). Estado vazio por grupo/lista.
- **`atendimento-drawer.tsx`**: prop nova `onAcaoConcluida?: () => void`; `runAction` chama `onAcaoConcluida ?? onClose` em sucesso (painel fica aberto e reflete o novo estado; o `X` do cabeçalho continua `onClose` → limpa `?id`). Nada mais muda no drawer.
- **`atendimento-sidebar.tsx`**: `SYSTEM_TABS` → `nao_resolvidas` (badge = `contadores.sistema.nao_lidas`, `bg-destructive`), `resolvidas`, `todas`; remove as entradas `nao_lidas`/`humano_solicitado`. Trocar as classes cruas dos badges (`bg-red-600`, `bg-amber-500/20`) por tokens no que for tocado.
- **`page.tsx`**: `const session = await requireSession()` → passa `userId={session.user.id}` e `departamentos` ao `AtendimentoList`; títulos por `tipo` inalterados (deep links).
- **`list-filters.tsx`**: remove o campo de busca (foi para a toolbar da lista); mantém departamento/prioridade/responsável/tags.
- **`situacao.ts`**: `SITUACAO_CHIP: Record<SituacaoAtendimento, string>` só com tokens (`bg-muted text-muted-foreground`, `bg-success/10 text-success`, `bg-brand-primary/10 text-brand-primary`, `bg-warning/10 text-warning`, `bg-destructive/10 text-destructive`); `faixaEspera(iso) → "normal"|"aviso"|"critico"`; `formatarEspera(iso) → "12min" | "3h 05min" | "2d"`.
- **`src/lib/api.ts`**: `Atendimento.aguardando_desde?: string | null`.
- **`CLAUDE.md`** (parágrafo "Leva fila de atendimento"): agrupamento client-side sobre a página carregada, chaves de `localStorage` (`atd-agrupar-por`, `atd-grupos-abertos`, `atd-larguras`), `?id=` na URL, `onAcaoConcluida`.

### Regras que não podem quebrar
- `prefetch={false}` em todo `<Link>` (rail); `router.replace` para `?id=` (não `push` — não empilha histórico a cada clique).
- Só UM `AtendimentoDrawer` montado; `useMediaQuery` devolve `undefined` no 1º render.
- Sem `fixed inset-0`, sem `confirm()`, sem paleta crua nova, sem `<input>` cru — `scripts/ui_metrics.sh --check` compara com `scripts/ui_metrics.baseline` e reprova se subir.
- Contagens dos grupos são da página carregada (limite 50); o rail continua usando `/contadores` (global).
- Circuit breaker do `fila-live.tsx` intocado; `revalidatePath` das actions intocado.

### Ordem de execução
1. PR A (backend) → unit + E2E → dev rebuild api → PR → CI → merge → conferir container.
2. PR B: `situacao.ts` + `agrupar.ts` → hooks → `card-atendimento.tsx` → `grupo-fila.tsx` → `lista-toolbar.tsx` → `atendimento-list.tsx` → drawer/sidebar/page/list-filters → `api.ts` → docs.
3. `npm run lint` + `npm run typecheck` + `bash scripts/ui_metrics.sh --check`.
4. Dev: `docker compose -p chatnexus-dev -f docker-compose.yml -f docker-compose.override.yml up -d --build frontend`; validar pela tela (Playwright MCP headless, login `admin@dev.local`, fechar o banner PWA "Agora não"): capturas em **light e dark**, desktop 1440 e mobile 390; roteiro: 3 modos de agrupamento, abrir/fechar grupo e "Recolher tudo" (persistem no reload), busca por telefone, selecionar conversa → `?id=` na URL → trocar de aba do rail e voltar mantém a conversa → **Atender** não fecha o painel e o cabeçalho passa a "Em atendimento" → arrastar a alça (limites 320/860) e duplo-clique redefine → mobile abre overlay.
5. Mostrar ao dono no dev (capturas) → PR → CI verde → merge → conferir container novo (`grep agrupar` no bundle ou pela tela).

## Fora do escopo (próximas levas)
Toggle "mostrar prévia" (`showPreview` do mock); SLA real por departamento (`departamento.tolerancia_atend_inativo_min`, sem uso hoje); `departamento_nome`/`assigned_to_nome` vindos do backend; contadores por `situacao` no rail; migrar `fixed` do drawer (menu ⋮, popover de transferir, dropdown de modelos) para `Popover`/`DropdownMenu` do kit; abas mortas (`meus/aguardando/grupos/outros`).

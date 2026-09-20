# Seletor de modelos do agente — estilo "Modelos Disponíveis" (Chatvolt)

**Pedido do dono (20/09/2026, com 5 capturas do Chatvolt):** "Vamos melhorar o menu do agente na configuração dos LLM, ele deve ter esse layout e todos elementos, deve trazer todos os llms com essas configurações. Copie e fazer 100% funcionando."

Capturas de referência (fora do repo): `~/.claude/uploads/15ae8448-1576-44ed-90c9-aa875ea3474b/{245b39a5,1cf206ae,0fc57d99,c452f1c5,b62f40b9}-image.jpg`.

Status: **planejado, não iniciado** (nenhum código alterado). Decisões abaixo já tomadas pelo dono. **A especificação completa para codar (assinaturas, SQL, componentes, testes, portões) está em `docs/ADR-004-seletor-modelos-agente.md` — este arquivo é o resumo/ordem de execução.**

---

## 1. Decisões (dono, 20/09)

| Tema | Decisão |
|---|---|
| Fonte dos modelos | **Catálogo completo do OpenRouter** (`openrouter_modelo`, 470 rows no dev, mig 178). Os curados (`modelo_llm`) ganham selo **Recomendado** e vêm primeiro em "Relevância". |
| Custo | **Créditos estimados por mensagem**: `1 crédito = US$ 0,001`. `custo = (chars_do_tier/4) × preco_prompt + 300 × preco_completion` (US$/token do `pricing` jsonb). `créditos = ceil(custo / 0,001)`, mínimo 1. US$ real no tooltip. Conferido: Gemini 2.5 Flash em Lite ≈ 0,0012 → 2 C (igual ao Chatvolt). |
| Premium / BLOQUEADO | **Só visual nesta leva** — selo "Premium" em Medium/Large/Extended e nos modelos caros; nada trava. Gate real por plano fica para depois (não travar a 1018). |
| Tamanho do Contexto | **Substitui a "Janela de memória (msgs)"**: Lite 6.000 · Regular 15.000 · Medium 25.000 · Large 35.000 · Extended 300.000 caracteres. Vira coluna `agente_ia.contexto_tamanho` (NULL = legado, comportamento atual). |

## 2. O que existe hoje (levantado)

- Editor: `frontend/src/app/agents/db/[slug]/agente-editor.tsx` → `TabModelo` (linhas ~704-1000): `FieldSelect` Provedor + Modelo do curado (`modelosChat: ModeloLLM[]`), `PickerCatalogoCompleto` (superadmin; busca nos 470 e injeta `escolhaLivre` como hidden inputs `modelo_provedor`/`modelo_nome`), depois estilo/temperatura/top-p/max_tokens/tipo_memoria/janela_memoria/timeout/retenção/limite→menu e o bloco "Valores efetivos" com custo /Mtok.
- Save: o form já aceita qualquer slug via `modelo_provedor` + `modelo_nome` (caminho do `escolhaLivre`) — **não precisa mudar a API de salvar o modelo**.
- Catálogo completo: tabela `openrouter_modelo` — `slug, canonical_slug, nome, descricao, context_length, input_modalities[] (visão), output_modalities[], supported_parameters[] (reasoning = Pensamento; tools = HTTP Tools), pricing jsonb (prompt/completion/… em US$ por token, string), benchmarks jsonb, criado_no_or (NEW), atualizado_em, ativo`. Rankings diários mig 179 (`openrouter_ranking_*`) → tendência ↗. Rotas `/api/openrouter/*` são **superadmin-only** (recurso de plataforma) — o seletor precisa de um endpoint próprio, com a permissão de editar agente.
- Plano: `plano.features` jsonb (ex.: `voz`) — base para o gate futuro.
- **Achado importante:** `tipo_memoria` e `janela_memoria` são salvos (mig 043) mas **não chegam ao worker** — `agents/loader.py` passa `chat_model/temperatura/top_p/max_tokens/tools_enabled/aceita_*` ao `build_graph`, e `agents/catalog/agente/agent.py` chama `get_context_middleware()` só com os defaults globais (`CONTEXT_STRATEGY=trim`, `TRIM_KEEP_TURNS`). Ou seja, hoje a UI promete memória que o backend ignora (gotcha conhecido). O tamanho do contexto tem que ser ligado de verdade (§3.3).
- `AgenteRuntime` (`shared/agente.py` ~L860-925) já carrega `tipo_memoria`/`janela_memoria`; `_COLS` (L60-75) e `_row_to_agente` posicional (L186) — coluna nova entra no fim da lista e no fim do dataclass (`AgenteIA`, L112-125). `update_agente` (L715) atualiza qualquer subset por nome. Pydantic da rota: `server/routes/agente.py` L140 (`janela_memoria: int | None = Field(ge=1, le=200)`). Tipo web: `frontend/src/lib/api.ts` L3651-3652 (`AgenteIA`).

## 3. Backend

### 3.1 Migration `187_agente_contexto_tamanho.sql`
```sql
ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS contexto_tamanho TEXT
    CHECK (contexto_tamanho IN ('lite','regular','medium','large','extended'));
COMMENT ON COLUMN agente_ia.contexto_tamanho IS
  'Tamanho do contexto (Lite 6k … Extended 300k chars) que limita a memória Window. NULL = legado (janela_memoria / TRIM_KEEP_TURNS).';
```
Fonte única dos tiers em `shared/contexto.py`:
```python
TIERS = {"lite": 6_000, "regular": 15_000, "medium": 25_000, "large": 35_000, "extended": 300_000}  # chars
PREMIUM = {"medium", "large", "extended"}
def chars_para_tokens(chars): return chars // 4
```

### 3.2 Modelo / CRUD
- `_COLS` += `contexto_tamanho` (último); `AgenteIA.contexto_tamanho: str | None = None`; `to_dict`; `AgenteRuntime.contexto_tamanho` + `from_agente`.
- Rota `agente.py`: `contexto_tamanho: Literal[...] | None`. Ao salvar com tier, **zerar `janela_memoria`** (ou ignorar) — um só manda.
- `frontend/src/lib/api.ts::AgenteIA` += `contexto_tamanho: string | null`.

### 3.3 Worker — ligar o contexto de verdade
- `agents/loader.py`: passar `contexto_chars=TIERS[rt.contexto_tamanho]` (None se legado) e, de brinde, `trim_keep_turns=rt.janela_memoria` quando houver, ao `build_graph`.
- `agents/catalog/agente/agent.py::build_graph(..., contexto_chars: int | None = None, trim_keep_turns: int | None = None)` → `get_context_middleware(trim_keep_turns=…, trim_max_chars=contexto_chars)`.
- `agents/middleware/context.py::get_context_middleware(trim_max_chars=None)` → `create_trim_middleware(keep_turns, max_chars)`.
- `agents/middleware/trim.py`: além do corte por turnos, quando `max_chars` está setado, remove turnos do início enquanto `sum(len(conteúdo))` dos que sobram > `max_chars`, **sempre mantendo o último turno inteiro** (a pergunta atual nunca sai). `RemoveMessage` como hoje. Testes unitários: (a) sem `max_chars` = comportamento atual; (b) 3 turnos de 3k chars com `max_chars=6000` → fica só os 2 últimos; (c) um turno maior que o teto fica inteiro.
- Log `agent_loaded` ganha `contexto_tamanho`.
- Não confundir com o cache do prompt (CLAUDE.md "variável volátil"): o tier limita o HISTÓRICO, o system prompt fixo continua igual.

### 3.4 Endpoint do catálogo para o seletor
`GET /api/modelos-llm/catalogo` (router de `modelos-llm`, mesma permissão do editor de agente — **não** superadmin). Sem paginação (470 rows × ~300 B). Resposta:
```json
{"itens":[{"slug":"google/gemini-2.5-flash","provedor":"google","provedor_nome":"Google","nome":"Gemini 2.5 Flash","descricao":"…","context_length":1048576,
  "visao":true,"pensamento":false,"tools":true,"preco_prompt":3e-7,"preco_completion":2.5e-6,
  "novo":false,"tendencia":true,"promo":false,"curado":true,"criado_em":"…"}],"gerado_em":"…"}
```
- `provedor` = prefixo do slug; `provedor_nome` = mapa fixo (google→Google, openai→OpenAI, anthropic→Anthropic, qwen→Qwen, deepseek→Deepseek, moonshotai→Moonshot AI, amazon→Amazon, meta-llama→Meta, mistralai→Mistral, x-ai→xAI, z-ai→Z.ai, …; fallback = capitalizar).
- `visao` = `'image' = ANY(input_modalities)`; `pensamento` = `'reasoning' = ANY(supported_parameters)` (ou `include_reasoning`); `tools` = `'tools' = ANY(supported_parameters)`.
- `novo` = `criado_no_or > now() - 30 dias`; `tendencia` = está no ranking diário mais recente (mig 179) no top N; `promo` = `preco_prompt = 0` ou slug termina em `:free`; `curado` = existe em `modelo_llm` (`provedor/nome`), `ativo`.
- Cache 10 min em memória no processo (o sync do catálogo roda a cada 10 min no worker).
- Smoke test (TestClient, 401 sem token) + E2E `docker_demo` no molde `test_aba_endpoints.py`: lista ≥ 1, campos presentes, um curado marcado.

## 4. Frontend — `frontend/src/app/agents/db/[slug]/seletor-modelo.tsx`

Substitui, dentro de `TabModelo`, os dois `FieldSelect` (Provedor/Modelo), o `PickerCatalogoCompleto` e o `Field` "Janela de memória". Mantém (abaixo): Estilo, Temperatura, Top-p, Max tokens, Tipo de memória, Timeout, Retenção, Limite→menu, "Valores efetivos". Hidden inputs: `modelo_provedor`, `modelo_nome`, `contexto_tamanho`. O botão Salvar do editor continua — e vira **flutuante** (`sticky bottom-4 right-4`) como no Chatvolt.

Dados: `useQuery(["catalogo-modelos"], carregarCatalogoAction, staleTime 10 min)` (Server Action → proxy; nunca axios no cliente). Cálculo de créditos no cliente (`creditos(modelo, tier)` puro, testável).

Layout (mesmos tokens/kit; tema claro e escuro; mobile-first — o dono testa no celular):
1. **Card-resumo** (fundo `bg-brand-primary/5`): logo do provedor · "MODELO SELECIONADO" nome · "TAMANHO DO CONTEXTO" ● tier · "CRÉDITOS" `$` N.
2. **Busca** (`InputGroup` + lupa): "Buscar por modelo, fabricante ou provedor…" — filtra por nome, slug e provedor (client-side).
3. **Chips de filtro** (toggle): `$ Promoção`, `👁 Visão`, `🧠 Pensamento`, `<> HTTP Tools` (ícones lucide: `BadgeDollarSign`, `Eye`, `Brain`, `Code`).
4. **"N modelos encontrados"** + botão limpar filtros (`FilterX`).
5. **Ordenação**: `Select` Relevância | Nome | Preço | Contexto | Mais novos, + botão direção ↓/↑. Relevância = curado primeiro, depois tendência, depois novo, depois preço.
6. **Abas de provedor** (linha rolável horizontal, `ScrollArea`): `Todos · N`, `Google · 11`, … contagem já com os filtros aplicados; ativa = `bg-brand-primary text-white`.
7. **Cards** (grid 1 col mobile / 2 col ≥ lg): logo (SVG simples por provedor em `logos-provedor.tsx`; fallback = inicial), nome (truncate) + provedor, badges `NEW`, `↗` tendência, `$` promo, `Recomendado` (curado), `🔒 BLOQUEADO →` só visual quando premium (preço > limiar OU tier premium) — clicável leva à seção de planos; ícones de capacidade (visão/pensamento/tools, esmaecidos quando ausentes); grade `LITE · REGULAR · MEDIUM · LARGE · EXTENDED` com créditos, o tier atual em destaque (`bg-brand-primary/10`); tier maior que `context_length` do modelo fica "—"; selecionado = `border-l-4 border-success bg-success/5`.
8. **Tamanho do Contexto**: 5 cards empilhados (`Lite · 6.000 caracteres · [2 C]`…), selecionado com borda `brand-primary`; Medium+ com selo `Premium` (só visual); texto de ajuda ("Define quantos caracteres o agente consegue lembrar…"). Créditos do badge = do modelo selecionado naquele tier.
9. **Aviso** (banner `destructive/10`): quando `len(prompt_override)` > chars do tier → "O prompt excede o número de caracteres suportado neste tamanho de contexto, reduza o prompt ou aumente o Tamanho do Contexto."
10. Estado vazio/erro do catálogo → volta ao select curado (fallback, nunca tela morta). Agente com modelo fora do catálogo (legado) aparece como card "atual" no topo.

Métricas de UI (`scripts/ui_metrics.sh --check`): sem `<input>/<select>` crus, sem paleta crua, sem `fixed inset-0`.

## 5. Ordem de execução (dev-first, PRs isoladas de `origin/master`)

1. **PR A — backend** `feat/contexto-tamanho-backend`: mig 187 + `shared/contexto.py` + CRUD/rota/runtime + trim por chars ligado no worker + endpoint `/catalogo` + testes (unit trim, smoke, E2E). `make check`, `make test -m "not docker_demo"` dirigido, E2E no dev, rebuild api+worker no dev, conferir por conteúdo.
2. **PR B — frontend** `feat/seletor-modelos-chatvolt`: `seletor-modelo.tsx` + `logos-provedor.tsx` + `creditos.ts` (puro) + ajustes em `agente-editor.tsx`/`api.ts`/actions + docs (CLAUDE.md parágrafo do módulo). Lint/typecheck/métricas; rebuild dev (**lembrar: `up --build frontend` reconstrói a api do checkout atual** — buildar a api da PR A primeiro ou rebased); validar 390×844 e 1440×900, claro/escuro; capturas ao dono ANTES do merge.
3. Merge sequencial (A, esperar deploy; B), conferir containers por conteúdo, migration aplicada em prod.

## 6. Fora desta leva (anotado)
- Gate real por plano (Premium bloqueando) — precisa mapear o que cada empresa usa (1018 hoje) antes de ligar.
- `tipo_memoria` buffer/summary/none de verdade no worker (só Window/trim é honrado; summary existe no middleware mas não é escolhido pelo agente).
- Créditos como moeda de cobrança (billing) — aqui é só estimativa exibida.
- App Android: campo aditivo, não quebra; tela nova fica só no web.

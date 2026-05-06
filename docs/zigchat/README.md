# ZigChat — API GraphQL (referência completa)

> Schema baixado via introspection em **2026-05-06** de `https://dev.zigchat.com.br/api/graphql`.
> Não é doc oficial do ZigChat — é engenharia reversa do schema GraphQL pra referência interna.

**Endpoint:** `POST https://dev.zigchat.com.br/api/graphql`
**Totais:** 282 types, 151 queries, 74 mutations.

## Convenções da API ZigChat

- **Mutations:** `criarAlterarX(data)` — UPSERT (cria se `data.id` é null, edita se preenchido).
- **Queries de listagem:** `listarX()` (sem filtro), `listarXAtivos()` (apenas ativos), `filtrarX(filter: XListInput)` (paginado), `buscarXPorId(id)`.
- **Booleans em string:** ZigChat usa `"S"` / `"N"` em vez de boolean nativo (provável herança de DB legacy).
- **IDs:** campos numéricos `Float`/`Int` (BIGINT). Exceções: `nanoid` (string) em algumas tabelas como `AtendimentoMenuHistorico`.
- **Operações em lote:** `criarAlterarItemLote(data)` (items do menu), `duplicarMenu(id)`, `criarAlterarMcpServer + testarMcpServer`, etc.
- **DataTable types:** quase todo `X` tem um `XDataTable` com `{ rows: [X], total: Int, ... }` retornado por `filtrarX`.
- **ListInput / FilterInput:** entradas de paginação + filtro pra `filtrarX`.

## Módulos

- [`agente_ia.md`](./agente_ia.md) — **agente_ia** — 26 types, 9 queries, 4 mutations
- [`menu_chatbot.md`](./menu_chatbot.md) — **menu_chatbot** — 20 types, 6 queries, 3 mutations
- [`atendimento_mensagem.md`](./atendimento_mensagem.md) — **atendimento_mensagem** — 41 types, 18 queries, 10 mutations
- [`cliente_crm.md`](./cliente_crm.md) — **cliente_crm** — 45 types, 26 queries, 13 mutations
- [`conexao_canal.md`](./conexao_canal.md) — **conexao_canal** — 11 types, 5 queries, 3 mutations
- [`departamento_horario.md`](./departamento_horario.md) — **departamento_horario** — 16 types, 10 queries, 3 mutations
- [`campanha_disparo.md`](./campanha_disparo.md) — **campanha_disparo** — 5 types, 3 queries, 2 mutations
- [`hook_webhook.md`](./hook_webhook.md) — **hook_webhook** — 15 types, 8 queries, 3 mutations
- [`produto.md`](./produto.md) — **produto** — 14 types, 6 queries, 2 mutations
- [`autenticacao_rbac.md`](./autenticacao_rbac.md) — **autenticacao_rbac** — 19 types, 13 queries, 10 mutations
- [`empresa_billing.md`](./empresa_billing.md) — **empresa_billing** — 10 types, 9 queries, 3 mutations
- [`variavel_ambiente.md`](./variavel_ambiente.md) — **variavel_ambiente** — 5 types, 3 queries, 1 mutations
- [`calendario.md`](./calendario.md) — **calendario** — 5 types, 2 queries, 1 mutations
- [`arquivo_pasta.md`](./arquivo_pasta.md) — **arquivo_pasta** — 12 types, 7 queries, 4 mutations
- [`aviso_termo.md`](./aviso_termo.md) — **aviso_termo** — 8 types, 5 queries, 4 mutations
- [`formulario.md`](./formulario.md) — **formulario** — 5 types, 3 queries, 1 mutations
- [`analytics.md`](./analytics.md) — **analytics** — 3 types, 2 queries, 0 mutations
- [`extras.md`](./extras.md) — **extras (não classificados)** — 22 types, 16 queries, 7 mutations

## Notas de paridade vs whatsapp-langchain

Ver `~/.claude/projects/-home-dev-projetos-whatsapp-langchain/memory/reference_zigchat_api.md` (memória local) — diffs entre o data model do ZigChat e nossas migrations 039 + 040, com plano de paridade futura (mig 041+).

Pontos altos:
- ZigChat tem **~10 ações de menu** (vs nossos 5 MVP): `transferir_atendente`, `enviar_template`, `chamar_webhook`, `enviar_link`, `pesquisa_csat`, `mudar_manual`, `setar_nome`
- ZigChat separa modelo LLM em `modelo_provedor` + `modelo_nome` (nosso é só `modelo` string)
- ZigChat tem `acao_limite_menu_id` no agente — quando estoura limite custo, redireciona pro menu (governança)
- ZigChat tem catálogo `ModeloIA` com `custo_input_mtok` + `custo_output_mtok`
- ZigChat tem wizard de coleta pré-menu (`solicitar_nome`, `coleta_informacao`, `confirmar_coleta`)
- ZigChat tem `menu_moderno` (botões nativos WhatsApp) e `menu_ia` (IA decide próxima opção)
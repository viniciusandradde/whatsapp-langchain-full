# 07 — Convenções e patterns adotados pelo ZigChat

> O que faz sentido **adotar**, **adaptar** ou **ignorar** no nosso lado.

## ✅ Adotar (já estamos fazendo, ou deveríamos)

### Multi-tenancy via `empresa_id`
ZigChat: `empresa_id` em quase todo OBJECT principal. **Nosso:** idem (Etapa 1 garantiu).

### Soft delete via flag (`ativo`)
ZigChat: `ativo: String` ("S"/"N"). **Nosso:** `ativo: BOOLEAN` (mais idiomático). Mesma semântica.

### Audit fields (`criacao_usuario_id` / `alteracao_usuario_id`)
ZigChat: tem nos types principais. **Nosso:** temos `created_by_user_id` em algumas tabelas + `audit_log` global. **Gap:** padronizar par created+updated_by.

### UPSERT mutations padrão
ZigChat: `criarAlterarX(data: XInput)` — single endpoint pra POST e PUT. **Nosso:** separamos em `POST` + `PUT`. **Decisão:** manter REST tradicional (mais explícito, melhor pra audit por verb).

## 🟡 Adaptar (boa ideia, mas implementar do nosso jeito)

### `XDataTable` wrapper de paginação
ZigChat: `{ rows: [X], total: Int, ... }`. **Nosso:** alguns endpoints retornam `{items: []}`, outros `{rows, total, page}`. **Recomendação:** padronizar `{rows: [], total: int, page: int, page_size: int}` em todos `GET /list`.

### `XInput` separado de `X` (input distinct from output)
ZigChat: tem `MenuInput` separado de `Menu` (write-only fields, não retorna FKs). **Nosso:** Pydantic `CreateXInput` + `UpdateXInput`. **Mantém.**

### `XListInput` + `XFilterInput` pra paginação tipada
ZigChat: separa filtro + paginação. **Nosso:** query params soltos. **Recomendação:** Pydantic `XListQuery` quando endpoint cresce (ex: `cliente?segmento=...&tag=...&page=...`).

### Operações em lote
ZigChat: `criarAlterarItemLote(data: [ItemInput])`. **Nosso:** temos `reorder_items` mas não bulk upsert. **Recomendação:** adicionar `POST /api/v1/menus/{id}/itens/bulk` pra UI editor (drag-drop salva tudo de uma vez).

## ❌ Não adotar

### `boolean` em string `"S"`/`"N"`
Herança Oracle/legacy. Postgres tem boolean nativo, idiomático e tipado.

### `Float` pra IDs
Convenção GraphQL ZigChat (Float comporta BIGINT). Em REST `integer` é mais correto. Mantém `int`.

### `id` como `Float!`
Idem. Nosso Pydantic + asyncpg → `int`.

### `nome` vs `descricao` ambiguidade
ZigChat usa `descricao` ora pra "label/nome", ora pra "descrição complementar". Inconsistente. Nosso modelo tem `nome` + `descricao` separados.

## 📌 Padrões nossos que ZigChat NÃO tem

- **JSONB tipado** (`tools_config`, `acao_payload`) — ZigChat usa colunas separadas (`acao_*_id`, `acao_setar_nome`, `nota_min`, `nota_max`...). **Trade-off:** colunas separadas são tipadas + indexáveis; JSONB é flexível pra evolução. Nosso JSONB é melhor pra ações compostas.
- **Array Postgres** (`trigger_keywords TEXT[]`, `tools_enabled TEXT[]`) — ZigChat tem `atalho` singular + `tool_configs` lista de rows. Array é mais simples pra leitura.
- **Audit log global** (`audit_log` table) — ZigChat tem `GeralLog` mas espalhado. Nosso é centralizado.
- **Better Auth + RBAC granular** — ZigChat parece ter `Permissao + Grupo` mas estrutura desconhecida. Nosso `permissoes.CATALOGO` + `perfil` é explícito.
- **Hooks com retry + DLQ** (`hook_dispatcher`) — ZigChat tem `Hook` mas sem indício de retry/DLQ. Nosso é production-ready.
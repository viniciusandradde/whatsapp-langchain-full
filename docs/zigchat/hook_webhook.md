# ZigChat — `hook_webhook`

_15 types, 8 queries, 3 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarHookPorId`
**Args:** `id: Int!`
**Retorna:** `Hook`

##### `buscarHookTaskPorId`
**Args:** `nanoid: String!`
**Retorna:** `HookTask`

##### `buscarHookUrlPorId`
**Args:** `id: Int!`
**Retorna:** `HookUrl`

##### `filtrarHook`
**Args:** `filter: HookListInput!`
**Retorna:** `HookDataTable`

##### `filtrarHookTask`
**Args:** `filter: HookTaskListInput!`
**Retorna:** `HookTaskDataTable`

##### `filtrarHookUrl`
**Args:** `filter: HookUrlListInput!`
**Retorna:** `HookUrlDataTable`

##### `listarHookUrls`
**Args:** _(nenhum)_
**Retorna:** `[HookUrl!]`

##### `listarHooks`
**Args:** _(nenhum)_
**Retorna:** `[Hook!]`

## Mutations

##### `criarAlterarHook`
**Args:** `data: HookInput!`
**Retorna:** `Hook`

##### `criarAlterarHookTask`
**Args:** `data: HookTaskInput!`
**Retorna:** `HookTask`

##### `criarAlterarHookUrl`
**Args:** `data: HookUrlInput!`
**Retorna:** `HookUrl`

## Types

### `Hook`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String` |  |
| `code` | `String` |  |
| `tipo` | `String` |  |
| `ativo` | `String` |  |
| `empresa_id` | `Int` |  |
| `criacao_usuario` | `String` |  |
| `msg_cliente` | `String` |  |
| `msg_usuario` | `String` |  |
| `headers` | `String` |  |
| `acao` | `Int` |  |

### `HookDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Hook!]` |  |
| `count` | `Int` |  |

### `HookFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `HookInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `code` | `String` |  |
| `tipo` | `String` |  |
| `ativo` | `String` |  |
| `msg_cliente` | `String` |  |
| `msg_usuario` | `String` |  |
| `headers` | `String` |  |
| `acao` | `Int` |  |

### `HookListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `HookFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `HookTask`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `target` | `String` |  |
| `body` | `String` |  |
| `queue` | `String` |  |
| `status` | `Int` |  |
| `empresa_id` | `Int!` |  |
| `log` | `String` |  |
| `http_status_code` | `Int` |  |
| `data_hora_criacao` | `DateTime` |  |
| `data_hora_finalizacao` | `DateTime` |  |
| `hook_id` | `Int!` |  |
| `hook` | `Hook` |  |

### `HookTaskDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[HookTask!]` |  |
| `count` | `Int` |  |

### `HookTaskFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `hook_id` | `PrimeFilterItemInt` |  |
| `queue` | `PrimeFilterItemString` |  |
| `status` | `PrimeFilterItemInt` |  |

### `HookTaskInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String` |  |
| `status` | `Int` |  |

### `HookTaskListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `HookTaskFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `HookUrl`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `hook_id` | `Int` |  |
| `url` | `String` |  |
| `empresa_id` | `Int` |  |
| `data_hora_criacao` | `DateTime` |  |
| `criacao_usuario` | `String` |  |
| `hook` | `Hook` |  |

### `HookUrlDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[HookUrl!]` |  |
| `count` | `Int` |  |

### `HookUrlFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `HookUrlInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `hook_id` | `Int` |  |
| `url` | `String` |  |
| `ativo` | `String` |  |

### `HookUrlListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `HookUrlFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

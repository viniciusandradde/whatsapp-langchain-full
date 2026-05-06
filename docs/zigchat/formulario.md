# ZigChat — `formulario`

_5 types, 3 queries, 1 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarFormPadraoPorId`
**Args:** `id: Int!`
**Retorna:** `FormPadrao`

##### `filtrarFormPadrao`
**Args:** `filter: FormPadraoListInput!`
**Retorna:** `FormPadraoDataTable`

##### `listarFormPadrao`
**Args:** _(nenhum)_
**Retorna:** `[FormPadrao!]`

## Mutations

##### `criarAlterarFormPadrao`
**Args:** `data: FormPadraoInput!`
**Retorna:** `FormPadrao`

## Types

### `FormPadrao`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `form` | `String` |  |
| `template` | `String` |  |
| `ativo` | `String!` |  |
| `empresa_id` | `Int!` |  |

### `FormPadraoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[FormPadrao!]` |  |
| `count` | `Int` |  |

### `FormPadraoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `FormPadraoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `form` | `String` |  |
| `template` | `String` |  |
| `ativo` | `String` |  |

### `FormPadraoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `FormPadraoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

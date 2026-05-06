# ZigChat — `variavel_ambiente`

_5 types, 3 queries, 1 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarVariavelAmbientePorId`
**Args:** `id: Int!`
**Retorna:** `VariavelAmbiente`

##### `filtrarVariavelAmbiente`
**Args:** `filter: VariavelAmbienteListInput!`
**Retorna:** `VariavelAmbienteDataTable`

##### `listarVariaveisAmbiente`
**Args:** _(nenhum)_
**Retorna:** `[VariavelAmbiente!]`

## Mutations

##### `criarAlterarVariavelAmbiente`
**Args:** `data: VariavelAmbienteInput!`
**Retorna:** `VariavelAmbiente`

## Types

### `VariavelAmbiente`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String!` |  |
| `descricao` | `String` |  |
| `empresa_id` | `Int` |  |
| `ativo` | `String` |  |
| `criado_por` | `String` |  |
| `alterado_por` | `String` |  |
| `data_criacao` | `String` |  |
| `data_atualizacao` | `String` |  |

### `VariavelAmbienteDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[VariavelAmbiente!]` |  |
| `count` | `Int` |  |

### `VariavelAmbienteFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `VariavelAmbienteInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `valor` | `String` |  |
| `descricao` | `String` |  |
| `ativo` | `String` |  |

### `VariavelAmbienteListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `VariavelAmbienteFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

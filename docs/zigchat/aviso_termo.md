# ZigChat — `aviso_termo`

_8 types, 5 queries, 4 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarAvisoPorId`
**Args:** `id: Int!`
**Retorna:** `Aviso`

##### `buscarUltimoTermo`
**Args:** _(nenhum)_
**Retorna:** `Termo`

##### `filtrarAviso`
**Args:** `filter: AvisoListInput!`
**Retorna:** `AvisoDataTable`

##### `listarAvisosAtivos`
**Args:** _(nenhum)_
**Retorna:** `[Aviso!]`

##### `listarLeitoresAviso`
**Args:** `aviso_id: Int!`
**Retorna:** `[AvisoUsuario!]!`

## Mutations

##### `criarAlterarAviso`
**Args:** `data: AvisoInput!`
**Retorna:** `Aviso`

##### `criarAlterarTermo`
**Args:** `data: TermoInput!`
**Retorna:** `Termo`

##### `marcarAvisoLido`
**Args:** `aviso_id: Int!`
**Retorna:** `Boolean!`

##### `marcarTodosAvisosLidos`
**Args:** _(nenhum)_
**Retorna:** `Boolean!`

## Types

### `Aviso`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `titulo` | `String!` |  |
| `descricao` | `String!` |  |
| `data_inicio` | `String` |  |
| `data_fim` | `String` |  |
| `ativo` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `criacao_usuario` | `String` |  |
| `empresas` | `String` |  |
| `lido` | `String` |  |

### `AvisoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Aviso!]` |  |
| `count` | `Int` |  |

### `AvisoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `titulo` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |
| `empresas` | `PrimeFilterItemInt` |  |

### `AvisoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `titulo` | `String` |  |
| `descricao` | `String` |  |
| `data_inicio` | `String` |  |
| `data_fim` | `String` |  |
| `ativo` | `String` |  |
| `empresas` | `[Int!]` |  |

### `AvisoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AvisoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `Termo`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `descricao` | `String!` |  |
| `ativo` | `String` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `usuarios` | `[Usuario!]` |  |
| `aceitou` | `String` |  |

### `TermoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `aceitar` | `String` |  |

### `UserWebNotification`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `header` | `String` |  |
| `content` | `String` |  |
| `severity` | `String` |  |
| `type` | `String` |  |
| `usuario_id` | `Int` |  |

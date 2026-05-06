# ZigChat — `calendario`

_5 types, 2 queries, 1 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarCalendarioEventoPorId`
**Args:** `id: Int!`
**Retorna:** `CalendarioEvento`

##### `filtrarCalendarioEvento`
**Args:** `filter: CalendarioEventoListInput!`
**Retorna:** `CalendarioEventoDataTable`

## Mutations

##### `criarAlterarCalendarioEvento`
**Args:** `data: CalendarioEventoInput!`
**Retorna:** `CalendarioEvento`

## Types

### `CalendarioEvento`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `data_inicial` | `String!` |  |
| `data_final` | `String` |  |
| `acao_novos_atend` | `String!` |  |
| `msg_atendimento_em_andamento` | `String` |  |
| `msg_encerramento` | `String` |  |
| `ativo` | `String` |  |
| `empresa_id` | `Int!` |  |
| `horarios` | `[CalendarioEventoHorario!]` |  |
| `conexoes` | `[Conexao!]` |  |

### `CalendarioEventoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[CalendarioEvento!]` |  |
| `count` | `Int` |  |

### `CalendarioEventoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `CalendarioEventoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `data_inicial` | `String` |  |
| `data_final` | `String` |  |
| `acao_novos_atend` | `String` |  |
| `msg_atendimento_em_andamento` | `String` |  |
| `msg_encerramento` | `String` |  |
| `ativo` | `String` |  |
| `horarios` | `[CalendarioEventoHorarioInput!]` |  |
| `conexoes` | `[Int!]` |  |

### `CalendarioEventoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `CalendarioEventoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

# ZigChat — `campanha_disparo`

_5 types, 3 queries, 2 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarCampanhaPorId`
**Args:** `id: Int!`
**Retorna:** `Campanha`

##### `filtrarCampanha`
**Args:** `filter: CampanhaListInput!`
**Retorna:** `CampanhaDataTable`

##### `listarCampanhas`
**Args:** _(nenhum)_
**Retorna:** `[Campanha!]`

## Mutations

##### `criarAlterarCampanha`
**Args:** `data: CampanhaInput!`
**Retorna:** `Campanha`

##### `criarAlterarItemLote`
**Args:** `data: [ItemInput!]!`
**Retorna:** `[Item!]`

## Types

### `Campanha`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `status` | `Int!` |  |
| `data_hora_inicio` | `DateTime` |  |
| `data_hora_fim` | `DateTime` |  |
| `ativo` | `String!` |  |
| `menu_id` | `Int` |  |
| `conexao_id` | `Int!` |  |
| `waba_template_id` | `String!` |  |
| `metadata` | `String` |  |
| `filtro_publico_alvo` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `criacao_usuario` | `String` |  |
| `empresa_id` | `Int!` |  |
| `body_params` | `String` |  |
| `header_params` | `String` |  |
| `erro_descricao` | `String` |  |
| `num_disparo` | `Int` |  |
| `num_recebido` | `Int` |  |

### `CampanhaDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Campanha!]` |  |
| `count` | `Int` |  |

### `CampanhaFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |
| `filtro_publico_alvo` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `CampanhaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `status` | `Int` |  |
| `data_hora_inicio` | `String` |  |
| `data_hora_fim` | `String` |  |
| `ativo` | `String` |  |
| `menu_id` | `Int` |  |
| `conexao_id` | `Int` |  |
| `filtro_publico_alvo` | `String` |  |
| `waba_template_id` | `String` |  |
| `header_parameters` | `[WabaTemplateParameterCampanha!]` |  |
| `body_parameters` | `[WabaTemplateParameterCampanha!]` |  |
| `replaced_header` | `String` |  |
| `replaced_body` | `String` |  |

### `CampanhaListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `CampanhaFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

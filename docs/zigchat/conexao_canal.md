# ZigChat — `conexao_canal`

_11 types, 5 queries, 3 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarCanalExternoPorId`
**Args:** `id: Int!`
**Retorna:** `CanalExterno`

##### `buscarConexaoPorId`
**Args:** `id: Int!`
**Retorna:** `Conexao`

##### `filtrarCanalExterno`
**Args:** `filter: CanalExternoListInput!`
**Retorna:** `CanalExternoDataTable`

##### `filtrarConexao`
**Args:** `filter: ConexaoListInput!`
**Retorna:** `ConexaoDataTable`

##### `listarCanalExterno`
**Args:** _(nenhum)_
**Retorna:** `[CanalExterno!]`

## Mutations

##### `atualizarStatusConexao`
**Args:** _(nenhum)_
**Retorna:** `Boolean`

##### `criarAlterarCanalExterno`
**Args:** `data: CanalExternoInput!`
**Retorna:** `CanalExterno`

##### `criarAlterarConexao`
**Args:** `data: ConexaoInput!`
**Retorna:** `Conexao`

## Types

### `CanalExterno`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `tipo` | `Int!` |  |
| `descricao` | `String!` |  |
| `canal` | `String!` |  |
| `empresa_id` | `Int!` |  |

### `CanalExternoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[CanalExterno!]` |  |
| `count` | `Int` |  |

### `CanalExternoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `CanalExternoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `tipo` | `Int` |  |
| `descricao` | `String` |  |
| `canal` | `String` |  |
| `ativo` | `String` |  |

### `CanalExternoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `CanalExternoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `Conexao`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `nome` | `String` |  |
| `identificador` | `String` |  |
| `tipo_atendimento` | `String!` |  |
| `session` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `state` | `String` |  |
| `tipo` | `String` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa` |  |
| `ativo` | `String!` |  |
| `padrao` | `String!` |  |
| `start_time` | `Float` |  |
| `engine` | `String!` |  |
| `waba_account_id` | `String` |  |
| `waba_account_description` | `String` |  |
| `waba_phone_id` | `String` |  |
| `waba_app_id` | `String` |  |
| `agente_ia_id` | `Int` |  |
| `agenteIA` | `AgenteIA` |  |

### `ConexaoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Conexao!]` |  |
| `count` | `Int` |  |

### `ConexaoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `identificador` | `PrimeFilterItemString` |  |
| `empresa_id` | `PrimeFilterItemInt` |  |
| `state` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |
| `engine` | `PrimeFilterItemString` |  |

### `ConexaoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `tipo` | `String` |  |
| `nome` | `String` |  |
| `tipo_atendimento` | `String` |  |
| `padrao` | `String` |  |
| `ativo` | `String` |  |
| `session` | `String` |  |
| `engine` | `String` |  |
| `waba_account_id` | `String` |  |
| `waba_account_description` | `String` |  |
| `waba_phone_id` | `String` |  |
| `waba_app_id` | `String` |  |
| `agente_ia_id` | `Int` |  |

### `ConexaoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ConexaoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `TelegramChat`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `descricao` | `String` |  |

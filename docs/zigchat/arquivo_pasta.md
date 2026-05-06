# ZigChat — `arquivo_pasta`

_12 types, 7 queries, 4 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarArquivoPorId`
**Args:** `uuid: String!`
**Retorna:** `Arquivo`

##### `buscarPastaPorId`
**Args:** `uuid: String!`
**Retorna:** `Pasta`

##### `decryptFile`
**Args:** `id: String!`, `w_id: String!`
**Retorna:** `DecryptJob`

##### `filtrarArquivo`
**Args:** `filter: ArquivoListInput!`
**Retorna:** `ArquivoDataTable`

##### `filtrarPasta`
**Args:** `filter: PastaListInput!`
**Retorna:** `PastaDataTable`

##### `listarPastas`
**Args:** _(nenhum)_
**Retorna:** `[Pasta!]`

##### `regenerarKeywordsArquivo`
**Args:** `uuid: String!`
**Retorna:** `String`

## Mutations

##### `criarAlterarArquivo`
**Args:** `data: ArquivoInput!`, `thumbnail: Upload`, `file: Upload`
**Retorna:** `Arquivo`

##### `criarAlterarPasta`
**Args:** `data: PastaInput!`
**Retorna:** `Pasta`

##### `enviarArquivosChat`
**Args:** `contentType: String!`, `resposta_mensagem_nanoid: String`, `atendimentoId: Int!`, `caption: String!`, `thumbnail: String`, `dir: String!`, `file: Upload!`
**Retorna:** `LocalFile`

##### `uploadFile`
**Args:** `dir: String!`, `file: Upload!`
**Retorna:** `LocalFile`

## Types

### `Arquivo`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String!` |  |
| `pasta_uuid` | `String` |  |
| `empresa_id` | `Int!` |  |
| `criacao_usuario_id` | `Int` |  |
| `dono_usuario_id` | `Int` |  |
| `original_name` | `String!` |  |
| `stored_name` | `String!` |  |
| `description` | `String` |  |
| `keywords` | `String` |  |
| `extension` | `String` |  |
| `mime_type` | `String` |  |
| `type` | `String` |  |
| `size_bytes` | `Float` |  |
| `file_key` | `String!` |  |
| `file_path` | `String!` |  |
| `thumbnail_key` | `String!` |  |
| `thumbnail_path` | `String` |  |
| `metadata` | `String` |  |
| `source` | `String!` |  |
| `disk` | `String!` |  |
| `delete_file` | `String!` |  |
| `data_hora_criacao` | `DateTime` |  |
| `pasta` | `Pasta` |  |
| `empresa` | `Empresa` |  |
| `criacaoUsuario` | `Usuario` |  |
| `donoUsuario` | `Usuario` |  |

### `ArquivoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Arquivo!]` |  |
| `count` | `Int` |  |

### `ArquivoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `original_name` | `PrimeFilterItemString` |  |
| `type` | `PrimeFilterItemString` |  |
| `category` | `PrimeFilterItemString` |  |
| `source` | `PrimeFilterItemString` |  |
| `pasta_uuid` | `PrimeFilterItemString` |  |
| `description` | `PrimeFilterItemString` |  |
| `keywords` | `PrimeFilterItemString` |  |
| `dono_usuario_id` | `PrimeFilterItemInt` |  |
| `search` | `PrimeFilterItemString` |  |
| `mime_type` | `PrimeFilterItemString` |  |

### `ArquivoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String` |  |
| `original_name` | `String` |  |
| `pasta_uuid` | `String` |  |
| `description` | `String` |  |
| `keywords` | `String` |  |
| `size_bytes` | `String` |  |
| `source` | `String` |  |
| `metadata` | `String` |  |
| `ativo` | `String` |  |
| `privado` | `Boolean` |  |

### `ArquivoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ArquivoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `ArquivoMetadado`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `aspectRatioWidth` | `Float` |  |
| `aspectRatioHeight` | `Float` |  |
| `height` | `Float` |  |
| `width` | `Float` |  |
| `orientation` | `Float` |  |

### `LocalFile`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `path` | `String!` |  |
| `atendimentoMensagem` | `AtendimentoMensagem` |  |

### `Pasta`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String!` |  |
| `empresa_id` | `Int!` |  |
| `criacao_usuario_id` | `Int` |  |
| `dono_usuario_id` | `Int` |  |
| `nome` | `String!` |  |
| `cor` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `empresa` | `Empresa` |  |
| `criacaoUsuario` | `Usuario` |  |
| `donoUsuario` | `Usuario` |  |
| `arquivos` | `[Arquivo!]` |  |

### `PastaDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Pasta!]` |  |
| `count` | `Int` |  |

### `PastaFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |

### `PastaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String` |  |
| `nome` | `String` |  |
| `ativo` | `String` |  |
| `cor` | `String` |  |
| `privado` | `Boolean` |  |

### `PastaListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `PastaFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

# ZigChat — `extras`

_22 types, 16 queries, 7 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `adminFiltrarConexoes`
**Args:** `filter: ConexaoListInput!`
**Retorna:** `ConexaoDataTable`

##### `buscarGeralLogPorId`
**Args:** `nanoid: String!`
**Retorna:** `GeralLog`

##### `buscarItemPorId`
**Args:** `id: Int!`
**Retorna:** `Item`

##### `carregarMensagens`
**Args:** `data: BuscarMensagemInput!`
**Retorna:** `[AtendimentoMensagem!]`

##### `filtrarGeralLog`
**Args:** `filter: GeralLogListInput!`
**Retorna:** `GeralLogDataTable`

##### `filtrarItem`
**Args:** `filter: ItemListInput!`
**Retorna:** `ItemDataTable`

##### `getUserLogged`
**Args:** _(nenhum)_
**Retorna:** `Usuario`

##### `limiteAtendentesValido`
**Args:** _(nenhum)_
**Retorna:** `Boolean`

##### `listarAgentesIA`
**Args:** _(nenhum)_
**Retorna:** `[AgenteIA!]`

##### `listarBasesConhecimento`
**Args:** _(nenhum)_
**Retorna:** `[BaseConhecimento!]`

##### `listarChatIds`
**Args:** _(nenhum)_
**Retorna:** `[TelegramChat!]`

##### `listarConexoes`
**Args:** _(nenhum)_
**Retorna:** `[Conexao!]`

##### `listarConexoesVinculadas`
**Args:** _(nenhum)_
**Retorna:** `[Conexao!]`

##### `listarModelosIA`
**Args:** _(nenhum)_
**Retorna:** `[ModeloIA!]`

##### `listarPermissoes`
**Args:** _(nenhum)_
**Retorna:** `[Permissao!]!`

##### `listarTransacoes`
**Args:** _(nenhum)_
**Retorna:** `[Transacao!]`

## Mutations

##### `criarAlterarItem`
**Args:** `data: ItemInput!`
**Retorna:** `Item`

##### `fecharPedido`
**Args:** `data: [PedidoProdutoInput!]!`
**Retorna:** `Pedido`

##### `inicializaSessao`
**Args:** `conexao_id: Int!`
**Retorna:** `String`

##### `reenviarMsg`
**Args:** `data: ReenviarAtendimentoMensagemInput!`
**Retorna:** `AtendimentoMensagem`

##### `salvarAppTraces`
**Args:** `data: [TraceEventInput!]!`
**Retorna:** `[TraceEvent!]!`

##### `salvarTema`
**Args:** `tema: String!`
**Retorna:** `Boolean`

##### `updateUserActivity`
**Args:** _(nenhum)_
**Retorna:** `String`

## Types

### `ConStateUpdate`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `state` | `String` |  |
| `msg` | `String` |  |
| `conexaoId` | `Float` |  |
| `empresaId` | `Float` |  |
| `battery` | `InfoBatteryState` |  |
| `queue` | `QueueUpdate` |  |

### `DecryptJob`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `String!` |  |
| `state` | `String` |  |
| `started_at` | `String` |  |
| `completed_at` | `String` |  |
| `error_message` | `String` |  |
| `empresa_id` | `Float` |  |

### `GeralLog`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `empresa_id` | `Int!` |  |
| `usuario_id` | `Int` |  |
| `descricao` | `String!` |  |
| `valores_antigos` | `String!` |  |
| `valores_novos` | `String!` |  |
| `tipo` | `Int!` |  |
| `usuario` | `Usuario` |  |

### `GeralLogDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[GeralLog!]` |  |
| `count` | `Int` |  |

### `GeralLogFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `tipo` | `PrimeFilterItemInt` |  |
| `descricao` | `PrimeFilterItemString` |  |
| `data_hora_criacao` | `PrimeFilterItemStringArray` |  |

### `GeralLogListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `GeralLogFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `IAUsoAnualItem`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `mes` | `Int!` |  |
| `custo_total` | `Float!` |  |
| `execucoes` | `Int!` |  |
| `tokens_total` | `Int!` |  |

### `IAUsoDiario`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `dia` | `String!` |  |
| `execucoes` | `Int!` |  |
| `custo_chat` | `Float!` |  |
| `custo_whisper` | `Float!` |  |
| `custo_embedding` | `Float!` |  |
| `custo_total` | `Float!` |  |
| `duration_ms_total` | `Float!` |  |
| `tool_calls_total` | `Int!` |  |
| `tool_errors_total` | `Int!` |  |
| `tokens_input` | `Int!` |  |
| `tokens_output` | `Int!` |  |

### `IAUsoMensal`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `execucoes` | `Int!` |  |
| `tokens_input` | `Int!` |  |
| `tokens_output` | `Int!` |  |
| `tokens_total` | `Int!` |  |
| `custo_chat` | `Float!` |  |
| `custo_whisper` | `Float!` |  |
| `custo_embedding` | `Float!` |  |
| `custo_total` | `Float!` |  |
| `duration_ms_total` | `Float!` |  |
| `tool_calls_total` | `Int!` |  |
| `tool_errors_total` | `Int!` |  |

### `InfoBatteryState`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `powersave` | `Boolean` |  |
| `plugged` | `Boolean` |  |
| `percentage` | `Float` |  |

### `McpToolResult`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `String!` |  |
| `descricao` | `String` |  |

### `MessageVCard`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `String` |  |
| `waid` | `String` |  |
| `telefone` | `String` |  |
| `cliente` | `Cliente` |  |

### `Pedido`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `atendimento_id` | `Int!` |  |
| `cliente_id` | `Int!` |  |
| `data_hora_criacao` | `String!` |  |
| `status` | `Int!` |  |
| `obs` | `String` |  |
| `valor_total` | `Float!` |  |

### `PedidoItemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `qtde` | `Int` |  |
| `descricao` | `String` |  |
| `nome` | `String` |  |
| `preco` | `Float` |  |

### `PrimeFilterItemInt`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `value` | `Int` |  |
| `matchMode` | `String` |  |

### `PrimeFilterItemString`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `value` | `String` |  |
| `matchMode` | `String` |  |

### `PrimeFilterItemStringArray`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `value` | `[String!]` |  |
| `matchMode` | `String` |  |

### `QrCodeObject`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `data` | `String` |  |

### `QueueUpdate`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `pendingMenssages` | `Float` |  |
| `msgPerMinute` | `Float` |  |

### `TraceEvent`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String!` |  |

### `TraceEventInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String!` |  |
| `ts` | `String` |  |
| `session_uuid` | `String` |  |
| `usuario_id` | `Int` |  |
| `empresa_id` | `Int` |  |
| `device_uuid` | `String` |  |
| `app_version` | `String` |  |
| `env` | `String` |  |
| `type` | `String` |  |
| `name` | `String` |  |
| `status` | `String` |  |
| `duration_ms` | `Int` |  |
| `data` | `String` |  |

### `UserFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `usuario` | `PrimeFilterItemString` |  |
| `email` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |
| `online` | `PrimeFilterItemString` |  |
| `disponivel` | `PrimeFilterItemString` |  |
| `data_hora_criacao` | `PrimeFilterItemStringArray` |  |
| `empresa_id` | `PrimeFilterItemInt` |  |
| `tipo` | `PrimeFilterItemInt` |  |

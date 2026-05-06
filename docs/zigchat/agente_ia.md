# ZigChat — `agente_ia`

_26 types, 9 queries, 4 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarAgenteIAPorId`
**Args:** `id: Int!`
**Retorna:** `AgenteIA`

##### `buscarBaseConhecimentoPorId`
**Args:** `id: Int!`
**Retorna:** `BaseConhecimento`

##### `buscarMcpServerPorId`
**Args:** `id: Int!`
**Retorna:** `McpServer`

##### `filtrarAgenteIA`
**Args:** `filter: AgenteIAListInput!`
**Retorna:** `AgenteIADataTable`

##### `filtrarBaseConhecimento`
**Args:** `filter: BaseConhecimentoListInput!`
**Retorna:** `BaseConhecimentoDataTable`

##### `filtrarMcpServer`
**Args:** `filter: McpServerListInput!`
**Retorna:** `McpServerDataTable`

##### `iaExecucaoDetalhe`
**Args:** `id: String!`
**Retorna:** `IAExecucaoDetalhe`

##### `iaExecucoes`
**Args:** `filtro: IAExecucaoFiltro!`
**Retorna:** `IAExecucaoLista!`

##### `listarMcpServers`
**Args:** _(nenhum)_
**Retorna:** `[McpServer!]`

## Mutations

##### `criarAlterarAgenteIA`
**Args:** `data: AgenteIAInput!`
**Retorna:** `AgenteIA`

##### `criarAlterarBaseConhecimento`
**Args:** `data: BaseConhecimentoInput!`
**Retorna:** `BaseConhecimento`

##### `criarAlterarMcpServer`
**Args:** `data: McpServerInput!`
**Retorna:** `McpServer`

##### `testarMcpServer`
**Args:** `data: TestarMcpServerInput!`
**Retorna:** `TestarMcpServerResult`

## Types

### `AgenteIA`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String!` |  |
| `descricao` | `String` |  |
| `modelo_provedor` | `String!` |  |
| `modelo_nome` | `String!` |  |
| `temperatura` | `Float` |  |
| `max_tokens` | `Int` |  |
| `prompt_sistema` | `String!` |  |
| `tipo_memoria` | `String!` |  |
| `janela_memoria` | `Int` |  |
| `timeout_minutos` | `Int` |  |
| `empresa_id` | `Int` |  |
| `ativo` | `String` |  |
| `data_criacao` | `String` |  |
| `data_hora_atualizacao` | `String` |  |
| `criacao_usuario` | `String` |  |
| `alteracao_usuario` | `String` |  |
| `acao_limite_custo` | `String!` |  |
| `acao_limite_menu_id` | `Int` |  |
| `base_conhecimentos` | `[BaseConhecimento!]` |  |
| `mcp_servers` | `[McpServer!]` |  |
| `tool_configs` | `[AgenteIAToolConfig!]` |  |

### `AgenteIADataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[AgenteIA!]` |  |
| `count` | `Int` |  |

### `AgenteIAFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `AgenteIAInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `descricao` | `String` |  |
| `modelo_provedor` | `String` |  |
| `modelo_nome` | `String` |  |
| `temperatura` | `Float` |  |
| `max_tokens` | `Int` |  |
| `prompt_sistema` | `String` |  |
| `tipo_memoria` | `String` |  |
| `janela_memoria` | `Int` |  |
| `timeout_minutos` | `Int` |  |
| `ativo` | `String` |  |
| `acao_limite_custo` | `String` |  |
| `acao_limite_menu_id` | `Int` |  |
| `base_conhecimento_ids` | `[Int!]` |  |
| `mcp_server_ids` | `[Int!]` |  |
| `tool_configs` | `[AgenteIAToolConfigInput!]` |  |

### `AgenteIAListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AgenteIAFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `AgenteIAToolConfig`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `agente_ia_id` | `Int!` |  |
| `tool_name` | `String!` |  |
| `modo` | `String` |  |
| `ids_permitidos` | `String` |  |
| `empresa_id` | `Int!` |  |

### `AgenteIAToolConfigInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `tool_name` | `String!` |  |
| `modo` | `String` |  |
| `ids_permitidos` | `[String!]` |  |

### `BaseConhecimento`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String!` |  |
| `conteudo` | `String!` |  |
| `fonte` | `String!` |  |
| `empresa_id` | `Int` |  |
| `ativo` | `String` |  |
| `data_criacao` | `String` |  |
| `agentes_ia` | `[AgenteIA!]` |  |

### `BaseConhecimentoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[BaseConhecimento!]` |  |
| `count` | `Int` |  |

### `BaseConhecimentoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `BaseConhecimentoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `conteudo` | `String` |  |
| `fonte` | `String` |  |
| `ativo` | `String` |  |

### `BaseConhecimentoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `BaseConhecimentoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `IABudget`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `limite_usd` | `Float` |  |
| `usado_usd` | `Float!` |  |
| `restante_usd` | `Float` |  |

### `IAExecucaoDetalhe`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `String!` |  |
| `agente_ia_id` | `Int!` |  |
| `atendimento_id` | `Int!` |  |
| `mensagem_nanoids` | `String` |  |
| `tokens_input` | `Int!` |  |
| `tokens_output` | `Int!` |  |
| `tokens_total` | `Int!` |  |
| `custo_estimado` | `Float` |  |
| `data_hora` | `String!` |  |
| `trace` | `String` | JSON string do trace completo |

### `IAExecucaoFiltro`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `agente_ia_id` | `Int` |  |
| `atendimento_id` | `Int` |  |
| `nanoid` | `String` |  |
| `limit` | `Int` |  |
| `offset` | `Int` |  |

### `IAExecucaoItem`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `String!` |  |
| `agente_ia_id` | `Int!` |  |
| `agente_nome` | `String` |  |
| `atendimento_id` | `Int!` |  |
| `mensagem_nanoids` | `String` |  |
| `tokens_input` | `Int!` |  |
| `tokens_output` | `Int!` |  |
| `tokens_total` | `Int!` |  |
| `custo_estimado` | `Float` |  |
| `data_hora` | `String!` |  |
| `duration_ms` | `Int` |  |
| `input_type` | `String` |  |

### `IAExecucaoLista`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[IAExecucaoItem!]!` |  |
| `has_more` | `Boolean!` |  |

### `IATopAgente`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `agente_ia_id` | `Int!` |  |
| `nome` | `String!` |  |
| `custo_total` | `Float!` |  |
| `execucoes` | `Int!` |  |

### `McpServer`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String!` |  |
| `descricao` | `String` |  |
| `tipo` | `String` |  |
| `tipo_conexao` | `String` |  |
| `url` | `String` |  |
| `comando` | `String` |  |
| `args` | `String` |  |
| `headers` | `String` |  |
| `status` | `String` |  |
| `ultimo_teste` | `String` |  |
| `empresa_id` | `Int` |  |
| `ativo` | `String` |  |
| `criado_por` | `String` |  |
| `alterado_por` | `String` |  |
| `data_criacao` | `String` |  |
| `data_atualizacao` | `String` |  |
| `agentes_ia` | `[AgenteIA!]` |  |

### `McpServerDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[McpServer!]` |  |
| `count` | `Int` |  |

### `McpServerFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `tipo` | `PrimeFilterItemString` |  |
| `status` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `McpServerInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `descricao` | `String` |  |
| `tipo_conexao` | `String` |  |
| `url` | `String` |  |
| `comando` | `String` |  |
| `args` | `String` |  |
| `headers` | `String` |  |
| `ativo` | `String` |  |

### `McpServerListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `McpServerFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `ModeloIA`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `provedor` | `String!` |  |
| `nome` | `String!` |  |
| `descricao` | `String` |  |
| `ativo` | `String` |  |
| `tipo` | `String!` |  |
| `custo_input_mtok` | `Float` |  |
| `custo_output_mtok` | `Float` |  |

### `TestarMcpServerInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `url` | `String!` |  |
| `headers` | `String` |  |

### `TestarMcpServerResult`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | `String!` |  |
| `tools` | `[McpToolResult!]!` |  |

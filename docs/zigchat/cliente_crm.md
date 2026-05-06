# ZigChat — `cliente_crm`

_45 types, 26 queries, 13 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarAbaPorId`
**Args:** `id: Int!`
**Retorna:** `Aba`

##### `buscarCliente`
**Args:** `filtro: ClienteInput!`
**Retorna:** `[Cliente!]`

##### `buscarClienteAnotacaoPorId`
**Args:** `id: Int!`
**Retorna:** `ClienteAnotacao`

##### `buscarClienteMencaoPorId`
**Args:** `cliente_id: Int!`
**Retorna:** `[ClienteMencao!]`

##### `buscarClientePorId`
**Args:** `id: Int!`
**Retorna:** `Cliente`

##### `buscarClientePorNomeOuTel`
**Args:** `query: String!`
**Retorna:** `[Cliente!]`

##### `buscarClientePorTelefoneFinal`
**Args:** `telefone: String!`
**Retorna:** `[Cliente!]`

##### `buscarClientesPorId`
**Args:** `ids: [Int!]!`
**Retorna:** `[Cliente!]`

##### `buscarTagPorId`
**Args:** `id: Int!`
**Retorna:** `Tag`

##### `buscarWabaSaldoLimite`
**Args:** _(nenhum)_
**Retorna:** `WabaSaldoLimite`

##### `buscarWabaTelefones`
**Args:** `waba_account_id: String!`, `token: String!`
**Retorna:** `String`

##### `buscarWabaTemplatePorId`
**Args:** `nanoid: String!`
**Retorna:** `WabaTemplate`

##### `filtrarAba`
**Args:** `filter: AbaListInput!`
**Retorna:** `AbaDataTable`

##### `filtrarCampanhaCliente`
**Args:** `filter: CampanhaClienteListInput!`
**Retorna:** `CampanhaClienteDataTable`

##### `filtrarCliente`
**Args:** `filter: ClienteListInput!`
**Retorna:** `ClienteDataTable`

##### `filtrarClienteAnotacao`
**Args:** `filter: ClienteAnotacaoListInput!`
**Retorna:** `ClienteAnotacaoDataTable`

##### `filtrarClientesCampanha`
**Args:** `filter: CampanhaListInput!`
**Retorna:** `ClienteDataTable`

##### `filtrarTag`
**Args:** `filter: TagListInput!`
**Retorna:** `TagDataTable`

##### `filtrarWabaTemplate`
**Args:** `filter: WabaTemplateListInput!`
**Retorna:** `WabaTemplateDataTable`

##### `listarAba`
**Args:** _(nenhum)_
**Retorna:** `[Aba!]`

##### `listarCategoriaProdutoPorCliente`
**Args:** `filter: ListarCategoriaProdutoFilterInput!`
**Retorna:** `[CategoriaProduto!]`

##### `listarTags`
**Args:** _(nenhum)_
**Retorna:** `[Tag!]`

##### `listarVinculoUsuarioCliente`
**Args:** `cliente_id: Int!`
**Retorna:** `[UsuarioCliente!]`

##### `listarWabaSaldoPorMesAno`
**Args:** `ano: Int!`, `mes: Int!`
**Retorna:** `[WabaSaldo!]`

##### `listarWabaTemplatesPorAccountId`
**Args:** `waba_account_id: String!`
**Retorna:** `[WabaTemplate!]`

##### `listarWabaTemplatesPorConexaoId`
**Args:** `conexao_id: Int!`
**Retorna:** `[WabaTemplate!]`

## Mutations

##### `criarAlterarAba`
**Args:** `data: AbaInput!`
**Retorna:** `Aba`

##### `criarAlterarCliente`
**Args:** `data: ClienteInput!`
**Retorna:** `Cliente`

##### `criarAlterarClienteAnotacao`
**Args:** `data: ClienteAnotacaoInput!`
**Retorna:** `ClienteAnotacao`

##### `criarAlterarTag`
**Args:** `data: TagInput!`
**Retorna:** `Tag`

##### `criarAlterarWabaTemplate`
**Args:** `data: WabaTemplateInput!`
**Retorna:** `WabaTemplate`

##### `criarClienteMencao`
**Args:** `data: ClienteMencaoInput!`
**Retorna:** `Boolean`

##### `criarVinculoUsuarioCliente`
**Args:** `data: UsuarioClienteInput!`
**Retorna:** `UsuarioCliente`

##### `excluirClienteMencao`
**Args:** `nanoid: String!`
**Retorna:** `Boolean`

##### `importarClientes`
**Args:** `data: ClienteImportacaoInput!`
**Retorna:** `[Cliente!]`

##### `importarWabaTemplates`
**Args:** `waba_account_id: String!`
**Retorna:** `[WabaTemplate!]`

##### `sincronizarWabaTemplate`
**Args:** `template_id: String!`
**Retorna:** `WabaTemplate`

##### `uploadWabaFile`
**Args:** `waba_account_id: String!`, `file_length: Int!`, `file: Upload!`
**Retorna:** `WabaTemplateFileUpload`

##### `wabaEmbeddedSignup`
**Args:** `data: WabaEmbeddedSignupInput!`
**Retorna:** `Conexao`

## Types

### `Aba`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `empresa_id` | `Int!` |  |
| `usuario_id` | `Int` |  |

### `AbaDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Aba!]` |  |
| `count` | `Int` |  |

### `AbaFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `AbaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `atendimento_id` | `Int` |  |
| `usuario_id` | `Int` |  |
| `ativo` | `String` |  |

### `AbaListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AbaFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `CampanhaCliente`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `campanha_id` | `Int!` |  |
| `cliente_id` | `Int!` |  |
| `status` | `Int!` |  |
| `erro_descricao` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `empresa_id` | `Int!` |  |
| `cliente` | `Cliente` |  |

### `CampanhaClienteDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[CampanhaCliente!]` |  |
| `count` | `Int` |  |

### `CampanhaClienteFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | `PrimeFilterItemInt` |  |
| `campanha_id` | `PrimeFilterItemInt` |  |

### `CampanhaClienteListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `CampanhaClienteFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `Cliente`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `nome` | `String` |  |
| `telefone` | `String` |  |
| `email` | `String` |  |
| `remoteid` | `String` |  |
| `observacoes` | `String` |  |
| `bairro` | `String` |  |
| `endereco` | `String` |  |
| `complemento` | `String` |  |
| `cep` | `String` |  |
| `numero` | `String` |  |
| `imagem_perfil` | `String` |  |
| `imagem_perfil_completa` | `String` |  |
| `visto_ultimo` | `Float` |  |
| `state` | `String` |  |
| `ativo` | `String!` |  |
| `numero_verificado` | `String` |  |
| `grupo` | `String` |  |
| `faixa_salarial_inicial` | `Float` |  |
| `faixa_salarial_final` | `Float` |  |
| `tag_id` | `Int` |  |
| `empresa_id` | `Float` |  |
| `cidade_id` | `Float` |  |
| `cidade` | `Cidade` |  |
| `empresa` | `Empresa!` |  |
| `data_cadastro` | `String!` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `data_nascimento` | `String` |  |
| `aba_id` | `Int` |  |
| `msg_apos_encerramento` | `String!` |  |
| `atendente_usuario_id` | `Int` |  |
| `alteracaoUsuario` | `Usuario!` |  |
| `criacaoUsuario` | `Usuario` |  |
| `tipo_atendimento` | `Int` |  |
| `desconsiderar_turno_cliente` | `String` |  |
| `field_1` | `String` |  |
| `field_2` | `String` |  |
| `field_3` | `String` |  |
| `field_4` | `String` |  |
| `field_5` | `String` |  |
| `webhook_url` | `String` |  |
| `hook_id` | `Int` |  |
| `tag` | `Tag` |  |
| `tags` | `[Tag!]` |  |
| `tags_secundarias` | `String` |  |
| `lid` | `String` |  |
| `ignora_inatividade` | `String` |  |

### `ClienteAnotacao`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `descricao` | `String!` |  |
| `mensagem` | `String!` |  |
| `ativo` | `String` |  |
| `criacao_usuario` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `cliente_id` | `Int!` |  |
| `cliente` | `Cliente!` |  |

### `ClienteAnotacaoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[ClienteAnotacao!]` |  |
| `count` | `Int` |  |

### `ClienteAnotacaoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `descricao` | `PrimeFilterItemString` |  |
| `mensagem` | `PrimeFilterItemString` |  |
| `cliente_id` | `PrimeFilterItemInt` |  |

### `ClienteAnotacaoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `descricao` | `String!` |  |
| `mensagem` | `String!` |  |
| `ativo` | `String` |  |
| `cliente_id` | `Int!` |  |

### `ClienteAnotacaoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ClienteAnotacaoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `ClienteDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Cliente!]` |  |
| `count` | `Int` |  |

### `ClienteFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |
| `telefone` | `PrimeFilterItemString` |  |
| `email` | `PrimeFilterItemString` |  |
| `id` | `PrimeFilterItemInt` |  |
| `tag_id` | `PrimeFilterItemInt` |  |
| `grupo` | `PrimeFilterItemString` |  |
| `bairro` | `PrimeFilterItemString` |  |
| `field_1` | `PrimeFilterItemString` |  |
| `field_2` | `PrimeFilterItemString` |  |
| `field_3` | `PrimeFilterItemString` |  |
| `field_4` | `PrimeFilterItemString` |  |
| `field_5` | `PrimeFilterItemString` |  |

### `ClienteImportacao`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `String` |  |
| `telefone` | `String!` |  |
| `email` | `String` |  |

### `ClienteImportacaoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `tag_id` | `Int` |  |
| `tag_descricao` | `String` |  |
| `clientes` | `[ClienteImportacao!]!` |  |

### `ClienteInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `telefone` | `String` |  |
| `email` | `String` |  |
| `observacoes` | `String` |  |
| `ativo` | `String` |  |
| `empresa_id` | `Int` |  |
| `endereco` | `String` |  |
| `numero` | `String` |  |
| `bairro` | `String` |  |
| `complemento` | `String` |  |
| `cep` | `String` |  |
| `cidade_id` | `Int` |  |
| `faixa_salarial_inicial` | `Float` |  |
| `faixa_salarial_final` | `Float` |  |
| `tag_id` | `Int` |  |
| `data_nascimento` | `String` |  |
| `aba_id` | `Int` |  |
| `tipo_atendimento` | `Int` |  |
| `msg_apos_encerramento` | `String` |  |
| `imagem_perfil` | `String` |  |
| `imagem_perfil_completa` | `String` |  |
| `desconsiderar_turno_cliente` | `String` |  |
| `atendente_usuario_id` | `Int` |  |
| `field_1` | `String` |  |
| `field_2` | `String` |  |
| `field_3` | `String` |  |
| `field_4` | `String` |  |
| `field_5` | `String` |  |
| `webhook_url` | `String` |  |
| `hook_id` | `Int` |  |
| `tags` | `[Int!]` |  |
| `ignora_inatividade` | `String` |  |

### `ClienteListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ClienteFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `ClienteMencao`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `cliente_id` | `Int!` |  |
| `cliente_mencao_id` | `Int!` |  |
| `cliente` | `Cliente` |  |
| `clienteMencionado` | `Cliente` |  |
| `canais` | `[CanalExterno!]` |  |

### `ClienteMencaoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String` |  |
| `cliente_id` | `Float` |  |
| `cliente_mencao_id` | `Float` |  |
| `canais` | `[Int!]` |  |

### `Tag`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `descricao` | `String!` |  |
| `cor` | `String` |  |
| `ativo` | `String!` |  |
| `empresa_id` | `Int!` |  |
| `webhook_url` | `String` |  |
| `hook_id` | `Int` |  |

### `TagDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Tag!]` |  |
| `count` | `Int` |  |

### `TagFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `TagInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `cor` | `String` |  |
| `ativo` | `String` |  |
| `webhook_url` | `String` |  |
| `hook_id` | `Int` |  |

### `TagListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `TagFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `UsuarioCliente`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `usuario_id` | `Float!` |  |
| `usuario` | `Usuario` |  |
| `cliente_id` | `Float!` |  |
| `cliente` | `Cliente!` |  |

### `UsuarioClienteInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `usuario_id` | `Int` |  |
| `cliente_id` | `Int` |  |
| `ativo` | `String` |  |

### `WabaEmbeddedSignupInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `waba_phone_id` | `String` |  |
| `waba_account_id` | `String!` |  |
| `conexao_id` | `Int` |  |
| `register_phone` | `Boolean!` |  |

### `WabaSaldo`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `waba_category` | `String!` |  |
| `mes` | `Int!` |  |
| `ano` | `Int!` |  |
| `saldo` | `Int!` |  |
| `empresa_id` | `Int!` |  |
| `conexao_id` | `Int!` |  |
| `conexao` | `Conexao` |  |

### `WabaSaldoLimite`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `saldo_utility` | `Int` |  |
| `saldo_authentication` | `Int` |  |
| `saldo_marketing` | `Int` |  |

### `WabaTemplate`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `id` | `String` |  |
| `name` | `String` |  |
| `category` | `String` |  |
| `correct_category` | `String` |  |
| `previous_category` | `String` |  |
| `parameter_format` | `String` |  |
| `language` | `String` |  |
| `status` | `String` |  |
| `components` | `String` |  |
| `waba_account_id` | `String` |  |
| `ativo` | `String` |  |
| `empresa_id` | `Int` |  |
| `header_handle` | `String` |  |
| `header_asset_url` | `String` |  |
| `header_file` | `String` |  |
| `header_file_mimetype` | `String` |  |
| `description` | `String` |  |
| `conexao` | `Conexao` |  |

### `WabaTemplateButton`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | `String` |  |
| `text` | `String` |  |
| `url` | `String` |  |
| `phone_number` | `String` |  |
| `example` | `String` |  |

### `WabaTemplateComponent`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | `String` |  |
| `format` | `String` |  |
| `text` | `String` |  |
| `example` | `WabaTemplateExample` |  |
| `buttons` | `[WabaTemplateButton!]` |  |

### `WabaTemplateDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[WabaTemplate!]` |  |
| `count` | `Int` |  |

### `WabaTemplateExample`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `body_text` | `[String!]` |  |
| `body_text_named_params` | `[WabaTemplateNamedParam!]` |  |
| `header_text` | `[String!]` |  |
| `header_text_named_params` | `[WabaTemplateNamedParam!]` |  |
| `header_handle` | `[String!]` |  |

### `WabaTemplateFileUpload`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `header_handle` | `String!` |  |
| `upload_path` | `String!` |  |
| `mimetype` | `String` |  |

### `WabaTemplateFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | `PrimeFilterItemString` |  |
| `category` | `PrimeFilterItemString` |  |
| `status` | `PrimeFilterItemString` |  |
| `waba_account_id` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `WabaTemplateImageParameterCampanha`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `link` | `String!` |  |

### `WabaTemplateInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String` |  |
| `id` | `String` |  |
| `name` | `String` |  |
| `category` | `String` |  |
| `parameter_format` | `String` |  |
| `language` | `String` |  |
| `allow_category_change` | `String` |  |
| `message_send_ttl_seconds` | `Int` |  |
| `components` | `[WabaTemplateComponent!]` |  |
| `ativo` | `String` |  |
| `waba_account_id` | `String` |  |
| `header_handle` | `String` |  |
| `header_asset_url` | `String` |  |
| `header_file` | `String` |  |
| `header_file_mimetype` | `String` |  |
| `description` | `String` |  |

### `WabaTemplateListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `WabaTemplateFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `WabaTemplateNamedParam`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `param_name` | `String` |  |
| `example` | `String` |  |

### `WabaTemplateParameterCampanha`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | `String` |  |
| `parameter_name` | `String` |  |
| `text` | `String` |  |
| `image` | `WabaTemplateImageParameterCampanha` |  |

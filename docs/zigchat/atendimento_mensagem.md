# ZigChat — `atendimento_mensagem`

_41 types, 18 queries, 10 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarAtendimentoHistoricoPorId`
**Args:** `next: Int`, `id: Int!`
**Retorna:** `Atendimento`

##### `buscarAtendimentoPorId`
**Args:** `id: Int!`
**Retorna:** `Atendimento`

##### `buscarAtendimentoTransferenciaPorId`
**Args:** `id: Int!`
**Retorna:** `AtendimentoTransferencia`

##### `buscarFormPadraoAtendimentoPorNanoid`
**Args:** `nanoid: String!`
**Retorna:** `FormPadraoAtendimento`

##### `buscarModeloMensagemPorId`
**Args:** `id: Int!`
**Retorna:** `ModeloMensagem`

##### `buscarSistemaMensagemPorId`
**Args:** `id: Int!`
**Retorna:** `SistemaMensagem`

##### `buscarUltimaMensagemCliente`
**Args:** `conexaoId: Int!`, `clienteId: Int!`
**Retorna:** `ClienteConexaoUltimaMensagem`

##### `contarAtendimentosAbertosUsuario`
**Args:** `usuario_id: Int!`
**Retorna:** `Int`

##### `filtrarAtendimentoHistorico`
**Args:** `filter: AtendimentoListInput!`
**Retorna:** `AtendimentoDataTable`

##### `filtrarAtendimentoMensagem`
**Args:** `filter: AtendimentoMensagemListInput!`
**Retorna:** `[AtendimentoMensagem!]`

##### `filtrarAtendimentoTransferencia`
**Args:** `filter: AtendimentoTransferenciaListInput!`
**Retorna:** `AtendimentoTransferenciaDataTable`

##### `filtrarAtendimentosCount`
**Args:** `filter: AtendimentoLazyFilterInput!`
**Retorna:** `AtendimentoLazyResponse`

##### `filtrarAtendimentosLazy`
**Args:** `filter: AtendimentoLazyFilterInput!`
**Retorna:** `AtendimentoLazyResponse`

##### `filtrarFormPadraoAtendimento`
**Args:** `filter: FormPadraoAtendimentoListInput!`
**Retorna:** `FormPadraoAtendimentoDataTable`

##### `filtrarModeloMensagem`
**Args:** `filter: ModeloMensagemListInput!`
**Retorna:** `ModeloMensagemDataTable`

##### `filtrarSistemaMensagem`
**Args:** `filter: SistemaMensagemListInput!`
**Retorna:** `SistemaMensagemDataTable`

##### `listarAtendimentoTransferencia`
**Args:** `atendimento_id: Int!`
**Retorna:** `[AtendimentoTransferencia!]`

##### `listarModeloMensagem`
**Args:** _(nenhum)_
**Retorna:** `[ModeloMensagem!]`

## Mutations

##### `copiarArquivoDeMensagem`
**Args:** `original_name: String`, `pasta_uuid: String`, `nanoid: String!`
**Retorna:** `Arquivo`

##### `criarAlterarAtendimento`
**Args:** `data: AtendimentoInput!`
**Retorna:** `Atendimento`

##### `criarAlterarAtendimentoMensagem`
**Args:** `data: AtendimentoMensagemInput!`
**Retorna:** `AtendimentoMensagem`

##### `criarAlterarAtendimentoTransferencia`
**Args:** `data: AtendimentoTransferenciaInput!`
**Retorna:** `AtendimentoTransferencia`

##### `criarAlterarFormPadraoAtendimento`
**Args:** `data: FormPadraoAtendimentoInput!`
**Retorna:** `FormPadraoAtendimento`

##### `criarAlterarModeloMensagem`
**Args:** `data: ModeloMensagemInput!`
**Retorna:** `ModeloMensagem`

##### `criarAlterarSistemaMensagem`
**Args:** `data: SistemaMensagemInput!`
**Retorna:** `SistemaMensagem`

##### `encaminharAtendimentoMensagem`
**Args:** `data: EncaminharMensagemInput!`
**Retorna:** `[AtendimentoMensagem!]`

##### `lerAtendimentoMensagemPorId`
**Args:** `nanoid: String!`
**Retorna:** `[AtendimentoMensagem!]`

##### `limparFila`
**Args:** `conexao_id: Int`
**Retorna:** `Boolean`

## Types

### `Atendimento`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `protocolo` | `String` |  |
| `cliente_id` | `Float` |  |
| `ultima_msg_enviada_nanoid` | `String` |  |
| `usuario_id` | `Float` |  |
| `canal` | `Float!` |  |
| `qtde_resposta_invalida` | `Float` |  |
| `grupo` | `String` |  |
| `cliente` | `Cliente` |  |
| `usuario` | `Usuario` |  |
| `usuarioAtendente` | `Usuario` |  |
| `ultimaMensagemEnviada` | `AtendimentoMensagem` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `tipo` | `Float!` |  |
| `lida` | `Float` |  |
| `nao_lida` | `Float` |  |
| `atendente_usuario_id` | `Float` |  |
| `menu_id` | `Float` |  |
| `ativo` | `String!` |  |
| `informa_nome` | `String!` |  |
| `departamento_id` | `Float` |  |
| `departamento` | `Departamento` |  |
| `data_hora_finalizacao` | `DateTime` |  |
| `data_hora_ultima_atividade` | `DateTime` |  |
| `data_hora_inicio` | `DateTime` |  |
| `empresa_id` | `Float` |  |
| `item_id` | `Float` |  |
| `solicitou_encerramento` | `Int` |  |
| `aba_id` | `Int` |  |
| `empresa` | `Empresa!` |  |
| `conexao_id` | `Float` |  |
| `nome_contato` | `String` |  |
| `iniciado_cliente` | `String` |  |
| `finalizacao_usuario` | `String` |  |
| `campanha_id` | `Int` |  |
| `tags` | `String` |  |
| `atendimentoTags` | `[Tag!]` |  |
| `data_hora_ultima_recebida` | `DateTime` |  |
| `agente_ia_id` | `Int` |  |
| `agenteIA` | `AgenteIA` |  |
| `conexao` | `Conexao` |  |
| `item` | `Item!` |  |
| `mensagens` | `[AtendimentoMensagem!]` |  |
| `usuarioTimestamp` | `[UsuarioAtendimentoTimestamp!]` |  |
| `notificacoes` | `Int` |  |
| `cliente_em_atendimento` | `Boolean` |  |
| `atendimento_automatico` | `String` |  |

### `AtendimentoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Atendimento!]` |  |
| `count` | `Int` |  |

### `AtendimentoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `PrimeFilterItemInt` |  |
| `protocolo` | `PrimeFilterItemString` |  |
| `cliente_nome` | `PrimeFilterItemString` |  |
| `cliente_id` | `PrimeFilterItemInt` |  |
| `conexao_id` | `PrimeFilterItemInt` |  |
| `cliente_tag_id` | `PrimeFilterItemInt` |  |
| `atendente_usuario_id` | `PrimeFilterItemInt` |  |
| `departamento_id` | `PrimeFilterItemInt` |  |
| `ativo` | `PrimeFilterItemString` |  |
| `data_hora_criacao` | `PrimeFilterItemStringArray` |  |
| `canal` | `PrimeFilterItemInt` |  |
| `grupo` | `PrimeFilterItemString` |  |
| `iniciado_cliente` | `PrimeFilterItemString` |  |
| `validate_date` | `PrimeFilterItemString` |  |
| `data_hora_finalizacao` | `PrimeFilterItemStringArray` |  |
| `tipo` | `PrimeFilterItemInt` |  |

### `AtendimentoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `protocolo` | `String` |  |
| `conexao_id` | `Float` |  |
| `mensagem` | `String` |  |
| `cliente_id` | `Float` |  |
| `usuario_id` | `Float` |  |
| `canal` | `Float` |  |
| `data_hora_criacao` | `DateTime` |  |
| `tipo` | `Float` |  |
| `atendente_usuario_id` | `Int` |  |
| `ativo` | `String` |  |
| `departamento_id` | `Int` |  |
| `data_hora_finalizacao` | `DateTime` |  |
| `empresa_id` | `Float` |  |
| `continuar_atendimento` | `String` |  |
| `transferir_atendimento` | `String` |  |
| `agente_ia_id` | `Int` |  |
| `instrucao_ia` | `String` |  |
| `aba_id` | `Int` |  |
| `grupo` | `String` |  |
| `nome_grupo` | `String` |  |
| `template_id` | `String` |  |
| `header_parameters` | `[WabaTemplateParameterAtendimento!]` |  |
| `body_parameters` | `[WabaTemplateParameterAtendimento!]` |  |
| `replaced_header` | `String` |  |
| `replaced_body` | `String` |  |
| `tags` | `[Int!]` |  |

### `AtendimentoLazyFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `tipo_visualizacao` | `Int!` |  |
| `ordem_atividade` | `Boolean` |  |
| `aba_id` | `Int` |  |
| `departamentos` | `[Int!]` |  |
| `nome_contato` | `String` |  |
| `cliente_nome` | `String` |  |
| `cliente_telefone` | `String` |  |
| `tipo` | `Int` |  |
| `protocolo` | `String` |  |
| `conexao_id` | `Int` |  |
| `limit` | `Int!` |  |
| `offset` | `Int!` |  |

### `AtendimentoLazyResponse`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `num_atendimentos` | `Int!` |  |
| `num_nao_lidas` | `Int!` |  |
| `atendimentos` | `[Atendimento!]!` |  |

### `AtendimentoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AtendimentoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `AtendimentoMensagem`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `atendimento_id` | `Float!` |  |
| `conexao_id` | `Float` |  |
| `conexao` | `Conexao` |  |
| `empresa_id` | `Float` |  |
| `canal` | `Float` |  |
| `cliente_id` | `Float` |  |
| `ultima_mensagem_nanoid` | `String` |  |
| `mencaoCliente` | `[Cliente!]` |  |
| `cliente` | `Cliente` |  |
| `grupo` | `String` |  |
| `timestamp` | `Float!` |  |
| `atendimento` | `Atendimento` |  |
| `mensagem` | `String` |  |
| `metadado` | `String` |  |
| `vcard` | `MessageVCard` |  |
| `content_type` | `String` |  |
| `thumbnail` | `String` |  |
| `status` | `String!` |  |
| `marcar_como_lida` | `String!` |  |
| `automatica` | `String!` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `arquivo` | `String` |  |
| `legenda` | `String` |  |
| `erro_descricao` | `String` |  |
| `w_id` | `String` |  |
| `link_externo` | `String` |  |
| `qtde_erros` | `Float!` |  |
| `tipo` | `Int!` |  |
| `ordem` | `Int!` |  |
| `interna` | `String!` |  |
| `atendente_usuario_id` | `Float` |  |
| `contact_cliente_id` | `Float` |  |
| `contactCliente` | `Int` |  |
| `usuario` | `Usuario` |  |
| `ativo` | `String` |  |
| `enviada_dispositivo` | `String` |  |
| `verificada` | `String` |  |
| `encrypted` | `String` |  |
| `file_type` | `String` |  |
| `encaminhada` | `String` |  |
| `resposta_mensagem_nanoid` | `String` |  |
| `waba_billable` | `String` |  |
| `waba_pricing_model` | `String` |  |
| `waba_category` | `String` |  |
| `resposta_coleta` | `String` |  |
| `campanha_id` | `Int` |  |
| `agente_ia_id` | `Int` |  |
| `agenteIA` | `AgenteIA` |  |
| `aguardando_msg` | `String` |  |
| `arquivo_nome` | `String` |  |
| `respostaMensagem` | `AtendimentoMensagem` |  |
| `menuModernoMetadado` | `MenuModernoMetadado` |  |
| `arquivoMetadados` | `ArquivoMetadado` |  |
| `signedThumbnail` | `String` |  |
| `signedFile` | `String` |  |

### `AtendimentoMensagemFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `mensagem` | `PrimeFilterItemString` |  |
| `data_hora_criacao` | `PrimeFilterItemStringArray` |  |
| `atendente_usuario_id` | `PrimeFilterItemInt` |  |
| `conexao_id` | `PrimeFilterItemInt` |  |
| `cliente_id` | `PrimeFilterItemInt` |  |
| `departamento_id` | `PrimeFilterItemInt` |  |

### `AtendimentoMensagemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String` |  |
| `atendimento_id` | `Float` |  |
| `mensagem` | `String` |  |
| `status` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `arquivo` | `String` |  |
| `legenda` | `String` |  |
| `interna` | `String` |  |
| `atendente_usuario_id` | `Float` |  |
| `ativo` | `String` |  |
| `contact_cliente_id` | `Float` |  |
| `resposta_mensagem_nanoid` | `String` |  |
| `template_id` | `String` |  |
| `header_parameters` | `[WabaTemplateParameterMensagem!]` |  |
| `body_parameters` | `[WabaTemplateParameterMensagem!]` |  |
| `replaced_body` | `String` |  |
| `replaced_header` | `String` |  |
| `tipo` | `Int` |  |
| `content_type` | `String` |  |
| `arquivo_nome` | `String` |  |
| `arquivo_uuid` | `String` |  |

### `AtendimentoMensagemListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AtendimentoMensagemFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `AtendimentoTransferencia`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `atendimento_id` | `Float!` |  |
| `atendimento` | `Atendimento!` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `atendente_usuario_id` | `Float` |  |
| `criacao_usuario_id` | `Float` |  |
| `atendente` | `Usuario` |  |
| `departamento_id` | `Float` |  |
| `departamento` | `Departamento` |  |
| `criacaoUsuario` | `Usuario` |  |

### `AtendimentoTransferenciaDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[AtendimentoTransferencia!]` |  |
| `count` | `Int` |  |

### `AtendimentoTransferenciaFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |

### `AtendimentoTransferenciaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `atendimento_id` | `Float!` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `atendente_usuario_id` | `Float` |  |
| `departamento_id` | `Float` |  |

### `AtendimentoTransferenciaListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AtendimentoTransferenciaFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `BuscarMensagemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `timestamp` | `Float` |  |
| `atendimentoId` | `Float` |  |
| `tipo` | `String` |  |

### `ClienteConexaoUltimaMensagem`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `cliente_id` | `Int!` |  |
| `conexao_id` | `Int!` |  |
| `data_hora_ultima_recebida` | `DateTime!` |  |

### `EncaminharMensagemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `mensagens` | `[String!]!` |  |
| `atendimentos` | `[Int!]!` |  |

### `FormPadraoAtendimento`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `descricao` | `String!` |  |
| `form` | `String` |  |
| `template` | `String` |  |
| `criacao_usuario_id` | `Int!` |  |
| `atendimento_id` | `Int` |  |
| `cliente_id` | `Int` |  |
| `form_padrao_id` | `Int!` |  |
| `data_hora_criacao` | `String!` |  |
| `empresa_id` | `Int!` |  |
| `atendimento` | `Atendimento` |  |
| `cliente` | `Cliente` |  |
| `criacaoUsuario` | `Usuario` |  |

### `FormPadraoAtendimentoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[FormPadraoAtendimento!]` |  |
| `count` | `Int` |  |

### `FormPadraoAtendimentoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |
| `atendimento_id` | `PrimeFilterItemInt` |  |
| `cliente_id` | `PrimeFilterItemInt` |  |

### `FormPadraoAtendimentoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String` |  |
| `descricao` | `String` |  |
| `form` | `String` |  |
| `template` | `String` |  |
| `atendimento_id` | `Int` |  |
| `cliente_id` | `Int` |  |
| `form_padrao_id` | `Int` |  |
| `ativo` | `String` |  |

### `FormPadraoAtendimentoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `FormPadraoAtendimentoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `MensagemStatusUpdate`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `state` | `String` |  |
| `msgIds` | `[String!]` |  |
| `msgErro` | `String` |  |
| `atendimentoId` | `Int` |  |
| `empresaId` | `Int` |  |

### `ModeloMensagem`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `descricao` | `String` |  |
| `atalho` | `String` |  |
| `mensagem` | `String` |  |
| `tornar_manual` | `String!` |  |
| `encerrar_atendimento` | `String` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa!` |  |
| `data_cadastro` | `DateTime!` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `usuario_id` | `Int` |  |
| `arquivo` | `String` |  |
| `mimetype` | `String` |  |
| `arquivo_nome` | `String` |  |
| `usuario` | `Usuario` |  |

### `ModeloMensagemDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[ModeloMensagem!]` |  |
| `count` | `Int` |  |

### `ModeloMensagemFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |

### `ModeloMensagemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `atalho` | `String` |  |
| `mensagem` | `String` |  |
| `tornar_manual` | `String` |  |
| `encerrar_atendimento` | `String` |  |
| `ativo` | `String` |  |
| `usuario_id` | `Int` |  |
| `arquivo` | `String` |  |
| `mimetype` | `String` |  |
| `arquivo_nome` | `String` |  |

### `ModeloMensagemListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ModeloMensagemFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `ReenviarAtendimentoMensagemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String` |  |

### `SistemaMensagem`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `mensagem` | `String` |  |
| `tipo` | `Float!` |  |
| `ativo` | `String!` |  |
| `arquivo` | `String` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa!` |  |
| `data_cadastro` | `DateTime!` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `alteracaoUsuario` | `Usuario` |  |
| `criacaoUsuario` | `Usuario` |  |

### `SistemaMensagemDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[SistemaMensagem!]` |  |
| `count` | `Int` |  |

### `SistemaMensagemFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `mensagem` | `PrimeFilterItemString` |  |
| `tipo` | `PrimeFilterItemInt` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `SistemaMensagemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `mensagem` | `String` |  |
| `tipo` | `Float` |  |
| `ativo` | `String` |  |
| `arquivo` | `String` |  |

### `SistemaMensagemListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `SistemaMensagemFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `UsuarioAtendimentoTimestamp`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `usuario_id` | `Float` |  |
| `atendimento_id` | `Float` |  |
| `timestamp` | `Float!` |  |
| `lida` | `Float` |  |
| `nao_lida` | `Float` |  |

### `WabaTemplateImageParameterAtendimento`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `link` | `String!` |  |

### `WabaTemplateImageParameterMensagem`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `link` | `String!` |  |

### `WabaTemplateParameterAtendimento`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | `String` |  |
| `parameter_name` | `String` |  |
| `text` | `String` |  |
| `image` | `WabaTemplateImageParameterAtendimento` |  |

### `WabaTemplateParameterMensagem`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | `String` |  |
| `parameter_name` | `String` |  |
| `text` | `String` |  |
| `image` | `WabaTemplateImageParameterMensagem` |  |

# ZigChat — `menu_chatbot`

_20 types, 6 queries, 3 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarMenuPorId`
**Args:** `id: Int!`
**Retorna:** `Menu`

##### `filtrarAtendimentoMenuHistorico`
**Args:** `filter: AtendimentoMenuHistoricoListInput!`
**Retorna:** `AtendimentoMenuHistoricoDataTable`

##### `filtrarMenu`
**Args:** `filter: MenuListInput!`
**Retorna:** `MenuDataTable`

##### `listarMenuItemArquivo`
**Args:** `filtro: MenuItemArquivoListarInput!`
**Retorna:** `[MenuItemArquivo!]`

##### `listarMenus`
**Args:** _(nenhum)_
**Retorna:** `[Menu!]`

##### `listarMenusAtivos`
**Args:** _(nenhum)_
**Retorna:** `[Menu!]`

## Mutations

##### `criarAlterarMenu`
**Args:** `data: MenuInput!`
**Retorna:** `Menu`

##### `criarAlterarMenuItemArquivo`
**Args:** `data: MenuItemArquivoInput!`
**Retorna:** `MenuItemArquivo`

##### `duplicarMenu`
**Args:** `id: Int!`
**Retorna:** `Menu`

## Types

### `AtendimentoMenuHistorico`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nanoid` | `String!` |  |
| `resposta` | `String` |  |
| `data_hora` | `String` |  |
| `atendimento_id` | `Float` |  |
| `cliente_id` | `Float` |  |
| `menu_id` | `Float` |  |
| `item_id` | `Float` |  |
| `item` | `Item` |  |
| `menu` | `Menu!` |  |
| `cliente` | `Cliente!` |  |
| `atendimento` | `Atendimento!` |  |

### `AtendimentoMenuHistoricoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[AtendimentoMenuHistorico!]` |  |
| `count` | `Int` |  |

### `AtendimentoMenuHistoricoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `menu_id` | `PrimeFilterItemInt` |  |
| `data_hora` | `PrimeFilterItemStringArray` |  |

### `AtendimentoMenuHistoricoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `AtendimentoMenuHistoricoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `Item`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `comando` | `String` |  |
| `enviar_contato_transf_depto` | `String` |  |
| `descricao` | `String!` |  |
| `mensagem` | `String` |  |
| `nota_escolha_msg` | `String` |  |
| `webhook_url` | `String` |  |
| `item_fim_coleta` | `String` |  |
| `link` | `String` |  |
| `acao` | `Float!` |  |
| `menu_id` | `Float` |  |
| `menu` | `Menu!` |  |
| `empresa_id` | `Float` |  |
| `nota_max` | `Float` |  |
| `nota_min` | `Float` |  |
| `acao_setar_nome` | `String!` |  |
| `contato_cliente_id` | `Float` |  |
| `empresa` | `Empresa!` |  |
| `data_cadastro` | `DateTime!` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `acao_modelo_mensagem_id` | `Float` |  |
| `acao_menu_id` | `Float` |  |
| `acao_departamento_id` | `Float` |  |
| `acao_atendente_id` | `Float` |  |
| `grupo` | `String` |  |
| `ordem` | `Int` |  |
| `hook_id` | `Int` |  |
| `mudar_para_manual` | `String` |  |
| `acao_agente_ia_id` | `Int` |  |
| `acao_agente_ia` | `AgenteIA` |  |
| `acao_menu` | `Menu` |  |
| `acao_departamento` | `Departamento` |  |
| `acao_atendente` | `Usuario` |  |
| `acao_modelo_mensagem` | `ModeloMensagem` |  |
| `alteracaoUsuario` | `Usuario` |  |
| `criacaoUsuario` | `Usuario` |  |
| `contatoCliente` | `Cliente` |  |

### `ItemDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Item!]` |  |
| `count` | `Int` |  |

### `ItemFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |
| `menu_id` | `PrimeFilterItemInt` |  |

### `ItemInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `comando` | `String` |  |
| `descricao` | `String` |  |
| `acao_setar_nome` | `String` |  |
| `nota_escolha_msg` | `String` |  |
| `item_fim_coleta` | `String` |  |
| `acao` | `Float` |  |
| `nota_max` | `Float` |  |
| `nota_min` | `Float` |  |
| `menu_id` | `Int` |  |
| `contato_cliente_id` | `Int` |  |
| `acao_modelo_mensagem_id` | `Int` |  |
| `acao_menu_id` | `Int` |  |
| `acao_departamento_id` | `Int` |  |
| `acao_atendente_id` | `Int` |  |
| `ativo` | `String` |  |
| `mensagem` | `String` |  |
| `link` | `String` |  |
| `grupo` | `String` |  |
| `ordem` | `Int` |  |
| `webhook_url` | `String` |  |
| `hook_id` | `Int` |  |
| `mudar_para_manual` | `String` |  |
| `acao_agente_ia_id` | `Int` |  |

### `ItemListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ItemFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `Menu`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `descricao` | `String!` |  |
| `atalho` | `String` |  |
| `conexao_id` | `Float` |  |
| `conexao` | `Conexao` |  |
| `mensagem` | `String` |  |
| `arquivo` | `String` |  |
| `principal` | `String!` |  |
| `solicitar_nome` | `String!` |  |
| `coleta_informacao` | `String!` |  |
| `enviar_msg_final_coleta` | `String!` |  |
| `menu_moderno` | `String!` |  |
| `confirmar_coleta` | `String!` |  |
| `ativo` | `String!` |  |
| `exibir_comando_menu_item` | `String` |  |
| `qtde_acesso` | `Float!` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa!` |  |
| `data_cadastro` | `DateTime!` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `menu_ia` | `String` |  |
| `alteracaoUsuario` | `Usuario` |  |
| `criacaoUsuario` | `Usuario` |  |
| `items` | `[Item!]` |  |
| `auto_navegar_para_item_id` | `Float` |  |
| `resposta_confidencial` | `String` |  |

### `MenuDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Menu!]` |  |
| `count` | `Int` |  |

### `MenuFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |
| `principal` | `PrimeFilterItemString` |  |
| `conexao_id` | `PrimeFilterItemInt` |  |

### `MenuInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `conexao_id` | `Float` |  |
| `descricao` | `String` |  |
| `atalho` | `String` |  |
| `mensagem` | `String` |  |
| `arquivo` | `String` |  |
| `principal` | `String` |  |
| `solicitar_nome` | `String` |  |
| `coleta_informacao` | `String` |  |
| `menu_moderno` | `String` |  |
| `confirmar_coleta` | `String` |  |
| `enviar_msg_final_coleta` | `String` |  |
| `ativo` | `String` |  |
| `auto_navegar_para_item_id` | `Float` |  |
| `exibir_comando_menu_item` | `String` |  |
| `resposta_confidencial` | `String` |  |
| `menu_ia` | `String` |  |

### `MenuItemArquivo`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `arquivo` | `String!` |  |
| `descricao` | `String!` |  |
| `content_type` | `String` |  |
| `menu_id` | `Float` |  |
| `item_id` | `Float` |  |
| `arquivo_nome` | `String` |  |

### `MenuItemArquivoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `arquivo` | `String` |  |
| `ativo` | `String` |  |
| `content_type` | `String` |  |
| `menu_id` | `Int` |  |
| `item_id` | `Int` |  |
| `arquivo_nome` | `String` |  |

### `MenuItemArquivoListarInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `menu_id` | `Int` |  |
| `item_id` | `Int` |  |

### `MenuListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `MenuFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `MenuModernoBtn`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `buttonId` | `Int` |  |
| `buttonText` | `MenuModernoBtnText` |  |
| `type` | `Int` |  |

### `MenuModernoBtnText`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `displayText` | `String` |  |

### `MenuModernoMetadado`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `text` | `String` |  |
| `footer` | `String` |  |
| `buttons` | `[MenuModernoBtn!]` |  |

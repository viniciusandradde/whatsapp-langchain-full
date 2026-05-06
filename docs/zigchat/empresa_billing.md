# ZigChat — `empresa_billing`

_10 types, 9 queries, 3 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `admBuscarEmpresaPorId`
**Args:** `id: Int!`
**Retorna:** `Empresa`

##### `admFiltrarEmpresas`
**Args:** `filter: EmpresaListInput!`
**Retorna:** `EmpresaDataTable`

##### `adminListarEmpresas`
**Args:** _(nenhum)_
**Retorna:** `[Empresa!]`

##### `buscarCidade`
**Args:** `data: CidadeFilterInput!`
**Retorna:** `[Cidade!]`

##### `buscarCidadePorIbge`
**Args:** `ibge: String!`
**Retorna:** `Cidade`

##### `buscarEmpresaPorId`
**Args:** `id: Int!`
**Retorna:** `Empresa`

##### `filtrarEmpresa`
**Args:** `filter: EmpresaListInput!`
**Retorna:** `EmpresaDataTable`

##### `listarPastasEmpresa`
**Args:** _(nenhum)_
**Retorna:** `[Pasta!]`

##### `listarTransacoesEmpresa`
**Args:** _(nenhum)_
**Retorna:** `[Transacao!]`

## Mutations

##### `admCriarAlterarEmpresa`
**Args:** `data: EmpresaInput!`
**Retorna:** `Empresa`

##### `criarAlterarEmpresa`
**Args:** `data: EmpresaInput!`
**Retorna:** `Empresa`

##### `criarAlterarPushDevice`
**Args:** `data: PushDeviceInput!`
**Retorna:** `PushDevice`

## Types

### `Cidade`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `ibge` | `String!` |  |
| `descricao` | `String!` |  |
| `uf` | `String!` |  |

### `CidadeFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |

### `Empresa`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `razao_social` | `String` |  |
| `cpf_cnpj` | `String` |  |
| `nome_fantasia` | `String` |  |
| `logo` | `String` |  |
| `tema` | `String` |  |
| `session` | `String` |  |
| `ativo` | `String!` |  |
| `sincronizar_contatos` | `String` |  |
| `multidevice` | `String!` |  |
| `habilitar_msg_grupo` | `String` |  |
| `battery_plugged` | `String` |  |
| `battery_powersave` | `String` |  |
| `fuso_horario` | `String` |  |
| `whats_ativo` | `String!` |  |
| `tipo_atendimento` | `String!` |  |
| `w_online` | `String!` |  |
| `tempo_atendimento` | `String` |  |
| `api_verifica_numero` | `String` |  |
| `apenas_grupos` | `String` |  |
| `max_usuario` | `Float!` |  |
| `start_time` | `Float` |  |
| `data_cadastro` | `String!` |  |
| `enviar_prococolo_cliente` | `String!` |  |
| `enviar_msg_encerramento_atend` | `String!` |  |
| `exibir_tempo_atendimento` | `String` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `cluster` | `String` |  |
| `enviar_msg_nome_atend` | `String` |  |
| `enviar_fila_atendimento` | `String` |  |
| `api_key` | `String` |  |
| `webhook_url` | `String` |  |
| `repetir_msg_boas_vindas` | `String` |  |
| `tolerancia_atend_inativo` | `Float!` |  |
| `battery_percentage` | `Float` |  |
| `horario_funcionamento` | `Float!` |  |
| `canal_padrao` | `Float!` |  |
| `telegram_token` | `String` |  |
| `telegram_chatid` | `String` |  |
| `cliente_faixa_salarial` | `String` |  |
| `retencao_msg` | `Int` |  |
| `campos_cliente` | `String` |  |
| `menu_coleta_id` | `Int` |  |
| `min_finaliza_pesquisa` | `Int` |  |
| `atendente_indisponivel` | `String` |  |
| `logo_dark` | `String` |  |
| `direcionar_atendente_principal` | `String` |  |
| `transacoes` | `[Transacao!]` |  |
| `alteracaoUsuario` | `Usuario!` |  |
| `criacaoUsuario` | `Usuario` |  |
| `programacao_atendimento` | `String` |  |
| `programacao_menu_coleta` | `String` |  |
| `finalizacao_atendimento_inativo` | `String` |  |
| `encerrar_apenas_atend_automatico` | `String` |  |
| `beta_tester` | `String` |  |
| `conexao_usuario` | `String` |  |
| `conexoes` | `[Conexao!]` |  |
| `cliente_field_metadata` | `String` |  |
| `enviar_msg_inicio` | `String` |  |
| `waba_verify_token` | `String` |  |
| `enviar_msg_indisponivel` | `String` |  |
| `saldo_utility` | `Int` |  |
| `saldo_authentication` | `Int` |  |
| `saldo_marketing` | `Int` |  |
| `max_conexao` | `Int` |  |
| `hook_id` | `Int` |  |
| `departamento_obrigatorio` | `String` |  |
| `status_bloqueio` | `String` |  |
| `limite_custo_ia_mensal` | `Float` |  |
| `habilitar_ia` | `String` |  |

### `EmpresaDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Empresa!]` |  |
| `count` | `Int` |  |

### `EmpresaFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `PrimeFilterItemInt` |  |
| `razao_social` | `PrimeFilterItemString` |  |
| `nome_fantasia` | `PrimeFilterItemString` |  |
| `cpf_cnpj` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `EmpresaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `razao_social` | `String` |  |
| `cpf_cnpj` | `String` |  |
| `nome_fantasia` | `String` |  |
| `min_finaliza_pesquisa` | `Float` |  |
| `logo` | `String` |  |
| `ativo` | `String` |  |
| `sincronizar_contatos` | `String` |  |
| `enviar_fila_atendimento` | `String` |  |
| `cluster` | `String` |  |
| `fuso_horario` | `String` |  |
| `whats_ativo` | `String` |  |
| `tipo_atendimento` | `String` |  |
| `tempo_atendimento` | `Float` |  |
| `max_usuario` | `Float` |  |
| `exibir_tempo_atendimento` | `String` |  |
| `w_online` | `String` |  |
| `enviar_prococolo_cliente` | `String` |  |
| `enviar_msg_encerramento_atend` | `String` |  |
| `enviar_msg_nome_atend` | `String` |  |
| `repetir_msg_boas_vindas` | `String` |  |
| `api_key` | `String` |  |
| `webhook_url` | `String` |  |
| `habilitar_msg_grupo` | `String` |  |
| `tolerancia_atend_inativo` | `Int` |  |
| `horario_funcionamento` | `Int` |  |
| `transacoes` | `[Int!]` |  |
| `canal_padrao` | `Int` |  |
| `telegram_token` | `String` |  |
| `telegram_chatid` | `String` |  |
| `cliente_faixa_salarial` | `String` |  |
| `retencao_msg` | `Int` |  |
| `campos_cliente` | `String` |  |
| `menu_coleta_id` | `Int` |  |
| `atendente_indisponivel` | `String` |  |
| `programacao_atendimento` | `String` |  |
| `programacao_menu_coleta` | `String` |  |
| `finalizacao_atendimento_inativo` | `String` |  |
| `encerrar_apenas_atend_automatico` | `String` |  |
| `beta_tester` | `String` |  |
| `conexao_usuario` | `String` |  |
| `enviar_msg_indisponivel` | `String` |  |
| `logo_dark` | `String` |  |
| `direcionar_atendente_principal` | `String` |  |
| `cliente_field_metadata` | `String` |  |
| `enviar_msg_inicio` | `String` |  |
| `waba_verify_token` | `String` |  |
| `saldo_utility` | `Int` |  |
| `saldo_authentication` | `Int` |  |
| `saldo_marketing` | `Int` |  |
| `max_conexao` | `Int` |  |
| `hook_id` | `Int` |  |
| `departamento_obrigatorio` | `String` |  |
| `status_bloqueio` | `String` |  |
| `habilitar_ia` | `String` |  |
| `limite_custo_ia_mensal` | `Float` |  |

### `EmpresaListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `EmpresaFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `PushDevice`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String` |  |
| `push_token` | `String!` |  |
| `usuario_id` | `Int!` |  |
| `empresa_id` | `Int!` |  |
| `platform` | `String!` |  |
| `app_version` | `String` |  |
| `data_hora_criacao` | `DateTime!` |  |
| `data_hora_alteracao` | `DateTime!` |  |
| `push_token_expiracao` | `DateTime!` |  |

### `PushDeviceInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `uuid` | `String` |  |
| `push_token` | `String` |  |
| `platform` | `String` |  |
| `app_version` | `String` |  |
| `opt_out` | `String` |  |

### `Transacao`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `descricao` | `String!` |  |
| `empresa` | `[Empresa!]` |  |

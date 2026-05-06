# ZigChat — `autenticacao_rbac`

_19 types, 13 queries, 10 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `Login`
**Args:** `login: LoginInput!`
**Retorna:** `Usuario`

##### `admTotalUsuariosEmpresa`
**Args:** `empresa_id: [Int!]!`
**Retorna:** `[TotalUsuarioEmpresa!]`

##### `adminFiltrarUsuarios`
**Args:** `filter: UsuarioListInput!`
**Retorna:** `UsuarioDataTable`

##### `adminListarUsuariosCriacaoStatus`
**Args:** `data_final: String!`, `data_inicial: String!`
**Retorna:** `[Usuario!]`

##### `buscarGrupoSistemaPorId`
**Args:** `id: Int!`
**Retorna:** `GrupoSistema`

##### `buscarUsuario`
**Args:** `filtro: UsuarioInput!`
**Retorna:** `[Usuario!]`

##### `criarEmpresaVerifyToken`
**Args:** _(nenhum)_
**Retorna:** `String`

##### `filtrarGrupoSistema`
**Args:** `filter: GrupoSistemaListInput!`
**Retorna:** `GrupoSistemaDataTable`

##### `filtrarUsuario`
**Args:** `filter: UsuarioListInput!`
**Retorna:** `UsuarioDataTable`

##### `listarGruposPermissoes`
**Args:** _(nenhum)_
**Retorna:** `[GrupoSistema!]`

##### `listarUsuarios`
**Args:** _(nenhum)_
**Retorna:** `[Usuario!]`

##### `pushDeviceUsuarioPorUuid`
**Args:** `push_device_uuid: String!`
**Retorna:** `PushDeviceUsuario`

##### `usuarioPorId`
**Args:** `id: Int!`
**Retorna:** `Usuario`

## Mutations

##### `admSessionUpdate`
**Args:** `data: SessionUpdateInput!`
**Retorna:** `String`

##### `alteraStatusUsuario`
**Args:** `data: UsuarioInput!`
**Retorna:** `Usuario`

##### `alterarSenha`
**Args:** `data: AlterarSenhaInput!`
**Retorna:** `Usuario`

##### `alterarUsuarioDisponivel`
**Args:** `disponivel: String!`, `id: Int!`
**Retorna:** `Usuario`

##### `criaAlteraUsuario`
**Args:** `data: UsuarioInput!`
**Retorna:** `Usuario`

##### `criarAlterarGrupoSistema`
**Args:** `data: GrupoSistemaInput!`
**Retorna:** `GrupoSistema`

##### `criarAlterarPushDeviceUsuario`
**Args:** `data: PushDeviceUsuarioInput!`
**Retorna:** `PushDeviceUsuario`

##### `criarUsuarioAvaliacao`
**Args:** `data: UsuarioAvaliacaoInput!`
**Retorna:** `Usuario`

##### `replicarUsuario`
**Args:** `data: ReplicarUsuarioInput!`
**Retorna:** `Boolean`

##### `sessionUpdate`
**Args:** `conexao_id: Int`, `type: String!`
**Retorna:** `String`

## Types

### `AlterarSenhaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `senha` | `String` |  |
| `nova_senha` | `String!` |  |
| `confirmar_senha` | `String!` |  |

### `AvisoUsuario`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `aviso_id` | `Float!` |  |
| `usuario_id` | `Float!` |  |
| `leitor` | `Usuario` |  |

### `GrupoSistema`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String!` |  |
| `descricao` | `String!` |  |
| `permissoes` | `[Permissao!]` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa!` |  |

### `GrupoSistemaDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[GrupoSistema!]` |  |
| `count` | `Int` |  |

### `GrupoSistemaFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `PrimeFilterItemString` |  |

### `GrupoSistemaInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `descricao` | `String` |  |
| `permissoes` | `[Int!]` |  |
| `ativo` | `String` |  |

### `GrupoSistemaListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `GrupoSistemaFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `LoginInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `usuario` | `String!` |  |
| `senha` | `String!` |  |

### `Permissao`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `categoria` | `String!` |  |

### `PushDeviceUsuario`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `usuario_id` | `Int!` |  |
| `push_device_uuid` | `String!` |  |
| `notificacao_usuario` | `String!` |  |
| `notificacao_empresa` | `String!` |  |
| `notificacao_interna` | `String!` |  |

### `PushDeviceUsuarioInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `push_device_uuid` | `String!` |  |
| `notificacao_usuario` | `String` |  |
| `notificacao_empresa` | `String` |  |
| `notificacao_interna` | `String` |  |

### `ReplicarUsuarioInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `usuario_replica_id` | `Int!` |  |
| `nome` | `String!` |  |
| `email` | `String!` |  |
| `usuario` | `String!` |  |
| `senha` | `String!` |  |
| `confirmar_senha` | `String!` |  |

### `SessionUpdateInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `conexao_id` | `Int!` |  |
| `type` | `String!` |  |

### `TotalUsuarioEmpresa`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `total` | `Int` |  |
| `tipo` | `Int` |  |
| `empresa_id` | `Int` |  |

### `Usuario`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `usuario` | `String!` |  |
| `email` | `String` |  |
| `token` | `String` |  |
| `ativo` | `String` |  |
| `nome` | `String` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa!` |  |
| `foto` | `String` |  |
| `online` | `String` |  |
| `disponivel` | `String` |  |
| `departamentos` | `[Departamento!]` |  |
| `permissoes` | `[Permissao!]` |  |
| `canais` | `[CanalExterno!]` |  |
| `padrao_conexao_id` | `Float` |  |
| `conexao` | `Conexao!` |  |
| `conexoes` | `[Conexao!]` |  |
| `turno_id` | `Float` |  |
| `tipo` | `Int` |  |
| `admin` | `String` |  |
| `data_hora_criacao` | `DateTime` |  |
| `criacao_usuario` | `String` |  |
| `data_alteracao_ativo` | `DateTime` |  |
| `alteracao_ativo_usuario` | `String` |  |
| `data_hora_login` | `DateTime` |  |
| `turno` | `Turno` |  |

### `UsuarioAvaliacaoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | `String` |  |
| `razao_social` | `String` |  |
| `cpf_cnpj` | `String` |  |
| `email` | `String` |  |
| `usuario` | `String` |  |
| `senha` | `String` |  |
| `confirmar_senha` | `String` |  |

### `UsuarioDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Usuario!]` |  |
| `count` | `Int` |  |

### `UsuarioInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `nome` | `String` |  |
| `email` | `String` |  |
| `usuario` | `String` |  |
| `senha` | `String` |  |
| `confirmar_senha` | `String` |  |
| `permissoes` | `[Int!]` |  |
| `departamentos` | `[Int!]` |  |
| `conexoes` | `[Int!]` |  |
| `padrao_conexao_id` | `Int` |  |
| `canais` | `[Int!]` |  |
| `ativo` | `String` |  |
| `foto` | `String` |  |
| `online` | `String` |  |
| `turno_id` | `Float` |  |
| `transferencia_usuario_id` | `Int` |  |
| `acao_desativacao` | `Int` |  |
| `tipo` | `Int` |  |

### `UsuarioListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `UserFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

# ZigChat — `departamento_horario`

_16 types, 10 queries, 3 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarDepartamentoPorId`
**Args:** `id: Int!`
**Retorna:** `Departamento`

##### `buscarTurnoPorId`
**Args:** `id: Int!`
**Retorna:** `Turno`

##### `filtrarDepartamento`
**Args:** `filter: DepartamentoListInput!`
**Retorna:** `DepartamentoDataTable`

##### `filtrarTurno`
**Args:** `filter: TurnoListInput!`
**Retorna:** `TurnoDataTable`

##### `listarDepartamentos`
**Args:** _(nenhum)_
**Retorna:** `[Departamento!]`

##### `listarDepartamentosHistorico`
**Args:** _(nenhum)_
**Retorna:** `[Departamento!]`

##### `listarDepartamentosPorUsuarioId`
**Args:** `id: Int!`
**Retorna:** `[Departamento!]`

##### `listarHorarioFuncionamento`
**Args:** _(nenhum)_
**Retorna:** `[HorarioFuncionamento!]`

##### `listarTurno`
**Args:** _(nenhum)_
**Retorna:** `[Turno!]`

##### `listarTurnoAtivo`
**Args:** _(nenhum)_
**Retorna:** `[Turno!]`

## Mutations

##### `criarAlterarDepartamento`
**Args:** `data: DepartamentoInput!`
**Retorna:** `Departamento`

##### `criarAlterarHorarioFuncionamento`
**Args:** `data: HorarioFuncionamentoInput!`
**Retorna:** `HorarioFuncionamento`

##### `criarAlterarTurno`
**Args:** `data: TurnoInput!`
**Retorna:** `Turno`

## Types

### `CalendarioEventoHorario`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `calendario_evento_id` | `Int!` |  |
| `horario_inicial` | `String!` |  |
| `horario_final` | `String!` |  |

### `CalendarioEventoHorarioInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `horario_inicial` | `String` |  |
| `horario_final` | `String` |  |

### `Departamento`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `descricao` | `String!` |  |
| `ativo` | `String` |  |
| `empresa_id` | `Float` |  |
| `empresa` | `Empresa!` |  |
| `data_cadastro` | `DateTime!` |  |
| `criacao_usuario_id` | `Float` |  |
| `alteracao_usuario_id` | `Float` |  |
| `posicao_fila_transferencia` | `Int` |  |
| `notifica_cliente_id` | `Float` |  |
| `encerra_atendimento` | `String` |  |
| `grupo` | `String` |  |
| `tolerancia_atend_inativo` | `Int` |  |
| `enviar_fila_atendimento` | `String` |  |
| `menu_coleta_id` | `Int` |  |
| `retencao_msg` | `Int` |  |
| `notificaCliente` | `Int` |  |
| `alteracaoUsuario` | `Usuario` |  |
| `criacaoUsuario` | `Int` |  |
| `usuarios` | `[Usuario!]` |  |
| `canais` | `[CanalExterno!]` |  |
| `turno_id` | `Float` |  |
| `turno` | `Turno` |  |

### `DepartamentoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Departamento!]` |  |
| `count` | `Int` |  |

### `DepartamentoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `DepartamentoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float` |  |
| `descricao` | `String` |  |
| `ativo` | `String` |  |
| `encerra_atendimento` | `String` |  |
| `enviar_fila_atendimento` | `String` |  |
| `notifica_cliente_id` | `Float` |  |
| `canais` | `[Int!]` |  |
| `grupo` | `String` |  |
| `tolerancia_atend_inativo` | `Int` |  |
| `menu_coleta_id` | `Int` |  |
| `retencao_msg` | `Int` |  |
| `turno_id` | `Float` |  |

### `DepartamentoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `DepartamentoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `HorarioFuncionamento`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Float!` |  |
| `horario_inicio` | `String!` |  |
| `horario_fim` | `String!` |  |
| `empresa_id` | `Float!` |  |
| `semana` | `Float!` |  |

### `HorarioFuncionamentoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `horario_inicio` | `String` |  |
| `horario_fim` | `String` |  |
| `semana` | `Int` |  |
| `empresa_id` | `Int` |  |
| `ativo` | `String` |  |

### `Turno`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `msg_atendimento_em_andamento` | `String` |  |
| `acao_novos_atend` | `String` |  |
| `msg_encerramento` | `String` |  |
| `data_hora_criacao` | `String` |  |
| `criacao_usuario_id` | `Float` |  |
| `empresa_id` | `Float` |  |
| `usuario` | `Usuario` |  |
| `horarios` | `[TurnoHorario!]` |  |
| `ativo` | `String!` |  |

### `TurnoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Turno!]` |  |
| `count` | `Int` |  |

### `TurnoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `descricao` | `PrimeFilterItemString` |  |
| `ativo` | `PrimeFilterItemString` |  |

### `TurnoHorario`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `turno_id` | `Int!` |  |
| `turno` | `Turno!` |  |
| `dia_semana` | `Int!` |  |
| `horario_inicial` | `String!` |  |
| `horario_final` | `String!` |  |

### `TurnoHorarioInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `turno_id` | `Int` |  |
| `dia_semana` | `Int` |  |
| `horario_inicial` | `String` |  |
| `horario_final` | `String` |  |

### `TurnoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `criacao_usuario_nanoid` | `String` |  |
| `atualizacao_usuario_nanoid` | `String` |  |
| `msg_atendimento_em_andamento` | `String` |  |
| `msg_encerramento` | `String` |  |
| `acao_novos_atend` | `String` |  |
| `data_hora_criacao` | `String` |  |
| `horarios` | `[TurnoHorarioInput!]` |  |
| `ativo` | `String` |  |

### `TurnoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `TurnoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

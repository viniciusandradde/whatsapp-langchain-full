# ZigChat — `analytics`

_3 types, 2 queries, 0 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarContadorPorNome`
**Args:** `nome: String!`
**Retorna:** `Contador`

##### `iaDashboard`
**Args:** _(nenhum)_
**Retorna:** `IADashboard!`

## Types

### `AtendiemntoPayload`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `ctxUserEmpresaId` | `Int` |  |
| `atendente_usuario_id` | `Int` |  |
| `usuario_id` | `Int` |  |
| `departamento_id` | `Int` |  |
| `tipo` | `Int` |  |
| `grupo` | `String` |  |
| `encerrou` | `String` |  |
| `conexao_id` | `String` |  |
| `old_atendente_usuario_id` | `Int` |  |
| `old_departamento_id` | `Int` |  |
| `old_tipo` | `Int` |  |
| `atendimento_id` | `Int` |  |

### `Contador`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String` |  |
| `qtde` | `Int` |  |
| `empresa_id` | `Int` |  |

### `IADashboard`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `budget` | `IABudget!` |  |
| `mensal` | `IAUsoMensal!` |  |
| `diario` | `[IAUsoDiario!]!` |  |
| `anual` | `[IAUsoAnualItem!]!` |  |
| `top_agentes` | `[IATopAgente!]!` |  |

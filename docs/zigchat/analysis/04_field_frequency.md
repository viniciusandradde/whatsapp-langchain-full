# 04 — Frequência de campos (todos os OBJECT + INPUT)

> Quais nomes de campo aparecem com mais frequência. Identifica padrões e convenções.

## Top 50 campos por frequência

| Campo | Freq | Tipo dominante |
|---|---:|---|
| `id` | 94 | `Int` |
| `rows` | 76 | `Int` |
| `ativo` | 75 | `String` |
| `descricao` | 72 | `String` |
| `empresa_id` | 49 | `Int!` |
| `nome` | 41 | `String` |
| `filters` | 38 | `CategoriaProdutoFilterInput` |
| `first` | 38 | `Int` |
| `sortField` | 38 | `String` |
| `sortOrder` | 38 | `Int` |
| `globalFilter` | 38 | `String` |
| `count` | 37 | `Int` |
| `tipo` | 29 | `Int` |
| `data_hora_criacao` | 27 | `DateTime` |
| `cliente_id` | 20 | `Int!` |
| `status` | 16 | `String` |
| `conexao_id` | 16 | `Float` |
| `mensagem` | 16 | `String` |
| `usuario_id` | 16 | `Int` |
| `nanoid` | 15 | `String!` |
| `atendimento_id` | 15 | `Int` |
| `empresa` | 13 | `Empresa!` |
| `criacao_usuario_id` | 12 | `Float` |
| `hook_id` | 12 | `Int` |
| `usuario` | 12 | `Usuario` |
| `grupo` | 11 | `String` |
| `atendente_usuario_id` | 11 | `Float` |
| `menu_id` | 11 | `Int` |
| `type` | 11 | `String` |
| `criacaoUsuario` | 10 | `Usuario` |
| `agente_ia_id` | 10 | `Int` |
| `arquivo` | 10 | `String` |
| `email` | 9 | `String` |
| `cliente` | 9 | `Cliente` |
| `webhook_url` | 8 | `String` |
| `uuid` | 8 | `String!` |
| `data_cadastro` | 7 | `DateTime!` |
| `alteracao_usuario_id` | 7 | `Float` |
| `criacao_usuario` | 7 | `String` |
| `departamento_id` | 7 | `Float` |
| `state` | 6 | `String` |
| `alteracaoUsuario` | 6 | `Usuario` |
| `tipo_atendimento` | 6 | `Int` |
| `canais` | 6 | `[CanalExterno!]` |
| `conexao` | 6 | `Conexao` |
| `turno_id` | 6 | `Float` |
| `canal` | 6 | `Float` |
| `waba_account_id` | 6 | `String` |
| `url` | 6 | `String` |
| `arquivo_nome` | 6 | `String` |

## Convenções universais detectadas

- **`id`** — sempre `Float!` (BIGINT) ou `Int!` em types mais novos. Algumas tabelas usam `nanoid: String!` (ex: `AtendimentoMenuHistorico`).
- **`empresa_id`** — multi-tenancy: presente em quase todo type principal. Tipo `Float` (NULL permitido em alguns? — verificar).
- **`ativo`** — soft delete via string `"S"`/`"N"`. NÃO é boolean nativo.
- **`data_cadastro` / `data_criacao` / `data_hora_criacao`** — timestamps DDL inconsistentes no naming.
- **`criacao_usuario_id` + `alteracao_usuario_id`** — auditoria de quem criou/alterou (Usuario FK).
- **`descricao`** — campo "label/nome" em muitos types onde nosso modelo usa `nome`. Em outros é descrição extra.
- **`nanoid`** — chave alternativa string (NanoID) em tabelas de log/histórico (mensagens, histórico menu).

## Campos triviais / derivados (alta frequência mas pouco semântico)

_Ignorar nesses no comparativo de paridade — são bookkeeping comum._

- `id`, `ativo`, `empresa_id`, `data_cadastro`, `data_criacao`, `data_hora_criacao`
- `criacao_usuario_id`, `alteracao_usuario_id`, `criacaoUsuario`, `alteracaoUsuario`
- `data_atualizacao`, `data_hora_atualizacao`, `updated_at`
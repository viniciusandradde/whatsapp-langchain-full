# 01 — Overview do schema GraphQL ZigChat

> Métricas brutas extraídas via introspection em **2026-05-06** de `https://dev.zigchat.com.br/api/graphql`.

## Totais

- **Types totais (excluindo built-ins, Query, Mutation):** 282
- **Queries:** 151
- **Mutations:** 74
- **Subscriptions:** 1

## Distribuição por kind

| Kind | Quantidade | % |
|---|---:|---:|
| `INPUT_OBJECT` | 155 | 55.0% |
| `OBJECT` | 127 | 45.0% |

## Naming patterns nas Queries (top prefixos)

| Prefixo | Qtde | Semântica esperada |
|---|---:|---|
| `buscar` | 48 | Single record por ID/chave |
| `listar` | 42 | Lista completa sem filtro/paginação |
| `filtrar` | 41 | Lista paginada + filtro (retorna `XDataTable`) |
| `admin` | 4 | Operação cross-tenant (super admin) |
| `adm` | 3 | — |
| `ia` | 3 | — |
| `carregar` | 1 | Load custom (ex: histórico de mensagens) |
| `criar` | 1 | — |
| `limite` | 1 | Verificações de quota/limite |
| `get` | 1 | — |
| `usuario` | 1 | — |
| `contar` | 1 | — |
| `decrypt` | 1 | Decrypt de arquivo encriptado |
| `regenerar` | 1 | — |
| `push` | 1 | — |

## Naming patterns nas Mutations (top prefixos)

| Prefixo | Qtde | Semântica esperada |
|---|---:|---|
| `criar` | 43 | INSERT puro (em geral combinado com `criarAlterar`) |
| `importar` | 2 | — |
| `salvar` | 2 | — |
| `upload` | 2 | — |
| `alterar` | 2 | UPDATE puro |
| `adm` | 2 | — |
| `marcar` | 2 | — |
| `fechar` | 1 | — |
| `reenviar` | 1 | — |
| `ler` | 1 | — |
| `encaminhar` | 1 | — |
| `excluir` | 1 | — |
| `enviar` | 1 | Outbound (ex: `enviarMensagem`) |
| `duplicar` | 1 | Clone (ex: `duplicarMenu`) |
| `cria` | 1 | — |
| `replicar` | 1 | — |
| `altera` | 1 | — |
| `update` | 1 | — |
| `atualizar` | 1 | — |
| `limpar` | 1 | — |
| `inicializa` | 1 | — |
| `session` | 1 | — |
| `sincronizar` | 1 | — |
| `waba` | 1 | — |
| `testar` | 1 | Health check (ex: `testarMcpServer`) |
| `copiar` | 1 | — |

## Top 25 types por número de campos

| Type | Kind | Campos |
|---|---|---:|
| `Empresa` | OBJECT | 71 |
| `AtendimentoMensagem` | OBJECT | 56 |
| `EmpresaInput` | INPUT_OBJECT | 56 |
| `Cliente` | OBJECT | 48 |
| `Atendimento` | OBJECT | 47 |
| `Item` | OBJECT | 38 |
| `ClienteInput` | INPUT_OBJECT | 33 |
| `Menu` | OBJECT | 27 |
| `AtendimentoInput` | INPUT_OBJECT | 27 |
| `Usuario` | OBJECT | 26 |
| `Arquivo` | OBJECT | 26 |
| `ItemInput` | INPUT_OBJECT | 24 |
| `Departamento` | OBJECT | 23 |
| `AgenteIA` | OBJECT | 22 |
| `AtendimentoMensagemInput` | INPUT_OBJECT | 21 |
| `Conexao` | OBJECT | 20 |
| `WabaTemplate` | OBJECT | 19 |
| `Campanha` | OBJECT | 19 |
| `McpServer` | OBJECT | 18 |
| `UsuarioInput` | INPUT_OBJECT | 18 |
| `ProdutoInput` | INPUT_OBJECT | 18 |
| `MenuInput` | INPUT_OBJECT | 17 |
| `AgenteIAInput` | INPUT_OBJECT | 17 |
| `ModeloMensagem` | OBJECT | 16 |
| `AtendimentoFilterInput` | INPUT_OBJECT | 16 |

## Padrões estruturais detectados

- **`XDataTable`:** 37 tipos. Wrapper de paginação `{ rows: [X], total, ... }`.
- **`XInput`:** 61 tipos. Payload de mutation.
- **`XListInput`:** 38 tipos. Filtro + paginação pra `filtrarX`.
- **`XFilterInput`:** 41 tipos. Sub-objeto de filtro.
- **Enums:** 0 tipos.
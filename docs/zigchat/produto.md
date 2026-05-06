# ZigChat — `produto`

_14 types, 6 queries, 2 mutations_

[← Voltar ao índice](./README.md)

## Queries

##### `buscarCategoriaProdutoPorId`
**Args:** `id: Int!`
**Retorna:** `CategoriaProduto`

##### `buscarProdutoPorId`
**Args:** `id: Int!`
**Retorna:** `Produto`

##### `filtrarCategoriaProduto`
**Args:** `filter: CategoriaProdutoListInput!`
**Retorna:** `CategoriaProdutoDataTable`

##### `filtrarProduto`
**Args:** `filter: ProdutoListInput!`
**Retorna:** `ProdutoDataTable`

##### `listarCategoriaProduto`
**Args:** _(nenhum)_
**Retorna:** `[CategoriaProduto!]`

##### `listarProdutos`
**Args:** `tipo: Int`
**Retorna:** `[Produto!]`

## Mutations

##### `criarAlterarCategoriaProduto`
**Args:** `data: CategoriaProdutoInput!`
**Retorna:** `CategoriaProduto`

##### `criarAlterarProduto`
**Args:** `data: ProdutoInput!`
**Retorna:** `Produto`

## Types

### `CategoriaProduto`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `empresa_id` | `Int!` |  |
| `descricao` | `String!` |  |
| `ativo` | `String!` |  |
| `produtos` | `[Produto!]` |  |
| `clientes` | `[Cliente!]` |  |

### `CategoriaProdutoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[CategoriaProduto!]` |  |
| `count` | `Int` |  |

### `CategoriaProdutoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `PrimeFilterItemInt` |  |

### `CategoriaProdutoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `ativo` | `String` |  |
| `clientes` | `[Int!]` |  |

### `CategoriaProdutoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `CategoriaProdutoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

### `ListarCategoriaProdutoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `cliente_id` | `Int` |  |
| `empresa_id` | `Int` |  |

### `OpcaoProduto`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `nome` | `String!` |  |
| `obrigatorio` | `String!` |  |
| `maximo` | `Int!` |  |
| `minimo` | `Int!` |  |
| `empresa_id` | `Int!` |  |
| `produto_id` | `Int!` |  |
| `itens` | `[Produto!]` |  |

### `OpcaoProdutoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `itens` | `[Int!]` |  |
| `nome` | `String` |  |
| `obrigatorio` | `String` |  |
| `maximo` | `Int` |  |
| `minimo` | `Int` |  |

### `PedidoProdutoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `qtde` | `Int` |  |
| `valor_total` | `Float` |  |
| `valor_unit` | `Float` |  |
| `descricao` | `String` |  |
| `nome` | `String` |  |
| `obs` | `String` |  |
| `itens` | `[PedidoItemInput!]` |  |

### `Produto`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int!` |  |
| `descricao` | `String!` |  |
| `preco` | `Float!` |  |
| `desconto_percentual` | `Int!` |  |
| `desconto_reais` | `Float!` |  |
| `qtde_estoque` | `Int!` |  |
| `controla_estoque` | `String!` |  |
| `divisivel` | `String!` |  |
| `imagem` | `String` |  |
| `nome` | `String` |  |
| `cod_exp` | `String` |  |
| `empresa_id` | `Int!` |  |
| `categoria_id` | `Int!` |  |
| `tipo` | `Int!` |  |
| `opcoes` | `[OpcaoProduto!]` |  |

### `ProdutoDataTable`
_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `rows` | `[Produto!]` |  |
| `count` | `Int` |  |

### `ProdutoFilterInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `PrimeFilterItemInt` |  |
| `tipo` | `PrimeFilterItemInt` |  |
| `categoria_id` | `PrimeFilterItemInt` |  |

### `ProdutoInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `Int` |  |
| `descricao` | `String` |  |
| `preco` | `Int` |  |
| `desconto_percentual` | `Int` |  |
| `desconto_reais` | `Int` |  |
| `qtde_estoque` | `Int` |  |
| `controla_estoque` | `String` |  |
| `divisivel` | `String` |  |
| `imagem` | `String` |  |
| `nome` | `String` |  |
| `cod_exp` | `String` |  |
| `empresa_id` | `Int` |  |
| `tipo` | `Int` |  |
| `categoria_id` | `Int` |  |
| `opcoes` | `[OpcaoProdutoInput!]` |  |
| `itens` | `[ProdutoInput!]` |  |
| `qtde` | `Int` |  |
| `valor_total` | `Float` |  |

### `ProdutoListInput`
_INPUT_OBJECT_

| Campo | Tipo | Descrição |
|---|---|---|
| `filters` | `ProdutoFilterInput` |  |
| `first` | `Int` |  |
| `rows` | `Int` |  |
| `sortField` | `String` |  |
| `sortOrder` | `Int` |  |
| `globalFilter` | `String` |  |

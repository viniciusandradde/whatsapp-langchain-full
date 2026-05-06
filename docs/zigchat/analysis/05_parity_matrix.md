# 05 — Matriz de paridade ZigChat × whatsapp-langchain

> Comparação field-by-field das 4 entidades core que tem equivalente direto.
> Marcadores: ✅ presente nos dois | 🟡 presente nos dois mas semântica/tipo diferente | ❌ só em um lado.

## `AgenteIA` — ZigChat `AgenteIA`

| ZigChat campo | Tipo | → Nosso campo | Status |
|---|---|---|---|
| `id` | `Int!` | `id` | ✅ |
| `nome` | `String!` | `nome` | ✅ |
| `descricao` | `String` | `descricao` | ✅ |
| `modelo_provedor` | `String!` | `modelo (parte)` | 🟡 semântica diferente |
| `modelo_nome` | `String!` | `modelo (parte)` | 🟡 semântica diferente |
| `temperatura` | `Float` | `temperatura_override` | ✅ |
| `max_tokens` | `Int` | `max_tokens` | ✅ |
| `prompt_sistema` | `String!` | `prompt_override` | ✅ |
| `tipo_memoria` | `String!` | — | ❌ só ZigChat |
| `janela_memoria` | `Int` | — | ❌ só ZigChat |
| `timeout_minutos` | `Int` | — | ❌ só ZigChat |
| `empresa_id` | `Int` | `empresa_id` | ✅ |
| `ativo` | `String` | `ativo` | ✅ |
| `data_criacao` | `String` | `created_at` | ✅ |
| `data_hora_atualizacao` | `String` | `updated_at` | ✅ |
| `criacao_usuario` | `String` | `created_by_user_id` | ✅ |
| `alteracao_usuario` | `String` | — | ❌ só ZigChat |
| `acao_limite_custo` | `String!` | `limite_custo_acao` | ✅ |
| `acao_limite_menu_id` | `Int` | — | ❌ só ZigChat |
| `base_conhecimentos` | `[BaseConhecimento!]` | `base_conhecimento_ids` | ✅ |
| `mcp_servers` | `[McpServer!]` | `mcp_server_ids` | ✅ |
| `tool_configs` | `[AgenteIAToolConfig!]` | `tools_config` | ✅ |

**Campos extras só nossos:**

- `slug` (TEXT NOT NULL)
- `template_catalog` (TEXT NOT NULL DEFAULT vsa_tech)
- `modelo` (TEXT)
- `estilo_resposta` (TEXT NOT NULL DEFAULT equilibrado (CHECK 4 valores))
- `top_p_override` (NUMERIC(3,2))
- `tools_enabled` (TEXT[] DEFAULT [])
- `aceita_imagem` (BOOLEAN DEFAULT TRUE)
- `aceita_audio` (BOOLEAN DEFAULT TRUE)
- `aceita_documento` (BOOLEAN DEFAULT TRUE)
- `variavel_ids` (BIGINT[] DEFAULT [])
- `is_default` (BOOLEAN DEFAULT FALSE)

## `Menu (menu_chatbot)` — ZigChat `Menu`

| ZigChat campo | Tipo | → Nosso campo | Status |
|---|---|---|---|
| `id` | `Float!` | `id` | ✅ |
| `descricao` | `String!` | `nome (ZigChat usa "descricao" como label)` | ✅ |
| `atalho` | `String` | — | ❌ só ZigChat |
| `conexao_id` | `Float` | `conexao_id` | ✅ |
| `conexao` | `Conexao` | `conexao_id (nested)` | ✅ |
| `mensagem` | `String` | `mensagem_boas_vindas` | ✅ |
| `arquivo` | `String` | — | ❌ só ZigChat |
| `principal` | `String!` | `is_default (parcial — uq partial nosso)` | 🟡 semântica diferente |
| `solicitar_nome` | `String!` | — | ❌ só ZigChat |
| `coleta_informacao` | `String!` | — | ❌ só ZigChat |
| `enviar_msg_final_coleta` | `String!` | — | ❌ só ZigChat |
| `menu_moderno` | `String!` | — | ❌ só ZigChat |
| `confirmar_coleta` | `String!` | — | ❌ só ZigChat |
| `ativo` | `String!` | `ativo` | ✅ |
| `exibir_comando_menu_item` | `String` | — | ❌ só ZigChat |
| `qtde_acesso` | `Float!` | — | ❌ só ZigChat |
| `empresa_id` | `Float` | `empresa_id` | ✅ |
| `empresa` | `Empresa!` | `empresa_id (nested)` | ✅ |
| `data_cadastro` | `DateTime!` | `created_at` | ✅ |
| `criacao_usuario_id` | `Float` | `created_by_user_id` | ✅ |
| `alteracao_usuario_id` | `Float` | _(bookkeeping comum, ignorar)_ | ✅ |
| `menu_ia` | `String` | — | ❌ só ZigChat |
| `alteracaoUsuario` | `Usuario` | _(bookkeeping comum, ignorar)_ | ✅ |
| `criacaoUsuario` | `Usuario` | `created_by_user_id (nested)` | ✅ |
| `items` | `[Item!]` | `items (via menu_item)` | ✅ |
| `auto_navegar_para_item_id` | `Float` | — | ❌ só ZigChat |
| `resposta_confidencial` | `String` | — | ❌ só ZigChat |

**Campos extras só nossos:**

- `nome` (TEXT NOT NULL)
- `trigger_keywords` (TEXT[] DEFAULT [menu, opcoes, inicio])
- `mensagem_opcao_invalida` (TEXT DEFAULT "Opção inválida...")
- `updated_at` (TIMESTAMPTZ)

## `Item (menu_item)` — ZigChat `Item`

| ZigChat campo | Tipo | → Nosso campo | Status |
|---|---|---|---|
| `id` | `Float!` | `id` | ✅ |
| `comando` | `String` | — | ❌ só ZigChat |
| `enviar_contato_transf_depto` | `String` | — | ❌ só ZigChat |
| `descricao` | `String!` | `label` | ✅ |
| `mensagem` | `String` | — | ❌ só ZigChat |
| `nota_escolha_msg` | `String` | — | ❌ só ZigChat |
| `webhook_url` | `String` | — | ❌ só ZigChat |
| `item_fim_coleta` | `String` | — | ❌ só ZigChat |
| `link` | `String` | — | ❌ só ZigChat |
| `acao` | `Float!` | `acao_tipo` | ✅ |
| `menu_id` | `Float` | `menu_id` | ✅ |
| `menu` | `Menu!` | `menu_id (nested)` | ✅ |
| `empresa_id` | `Float` | _(bookkeeping comum, ignorar)_ | ✅ |
| `nota_max` | `Float` | — | ❌ só ZigChat |
| `nota_min` | `Float` | — | ❌ só ZigChat |
| `acao_setar_nome` | `String!` | — | ❌ só ZigChat |
| `contato_cliente_id` | `Float` | — | ❌ só ZigChat |
| `empresa` | `Empresa!` | _(bookkeeping comum, ignorar)_ | ✅ |
| `data_cadastro` | `DateTime!` | `created_at` | ✅ |
| `criacao_usuario_id` | `Float` | _(bookkeeping comum, ignorar)_ | ✅ |
| `alteracao_usuario_id` | `Float` | _(bookkeeping comum, ignorar)_ | ✅ |
| `acao_modelo_mensagem_id` | `Float` | — | ❌ só ZigChat |
| `acao_menu_id` | `Float` | `parent_id (parcial — só submenu)` | 🟡 semântica diferente |
| `acao_departamento_id` | `Float` | `acao_payload.departamento_id (JSONB)` | ✅ |
| `acao_atendente_id` | `Float` | — | ❌ só ZigChat |
| `grupo` | `String` | — | ❌ só ZigChat |
| `ordem` | `Int` | `ordem` | ✅ |
| `hook_id` | `Int` | — | ❌ só ZigChat |
| `mudar_para_manual` | `String` | — | ❌ só ZigChat |
| `acao_agente_ia_id` | `Int` | `acao_payload.agente_slug (JSONB)` | ✅ |
| `acao_agente_ia` | `AgenteIA` | `acao_payload (nested)` | ✅ |
| `acao_menu` | `Menu` | `parent (nested)` | ✅ |
| `acao_departamento` | `Departamento` | `acao_payload (nested)` | ✅ |
| `acao_atendente` | `Usuario` | — | ❌ só ZigChat |
| `acao_modelo_mensagem` | `ModeloMensagem` | — | ❌ só ZigChat |
| `alteracaoUsuario` | `Usuario` | _(bookkeeping comum, ignorar)_ | ✅ |
| `criacaoUsuario` | `Usuario` | _(bookkeeping comum, ignorar)_ | ✅ |
| `contatoCliente` | `Cliente` | — | ❌ só ZigChat |

**Campos extras só nossos:**

- `parent_id` (BIGINT FK self (NULL=raiz))
- `acao_payload` (JSONB DEFAULT {})
- `ativo` (BOOLEAN DEFAULT TRUE)
- `updated_at` (TIMESTAMPTZ)

## `AtendimentoMenuHistorico` — ZigChat `AtendimentoMenuHistorico`

| ZigChat campo | Tipo | → Nosso campo | Status |
|---|---|---|---|
| `nanoid` | `String!` | `id (🟡 nanoid string vs nosso bigserial)` | ✅ |
| `resposta` | `String` | — | ❌ só ZigChat |
| `data_hora` | `String` | `escolhido_at` | ✅ |
| `atendimento_id` | `Float` | `atendimento_id` | ✅ |
| `cliente_id` | `Float` | — | ❌ só ZigChat |
| `menu_id` | `Float` | `menu_id` | ✅ |
| `item_id` | `Float` | `item_id` | ✅ |
| `item` | `Item` | `item_id (nested)` | ✅ |
| `menu` | `Menu!` | `menu_id (nested)` | ✅ |
| `cliente` | `Cliente!` | — | ❌ só ZigChat |
| `atendimento` | `Atendimento!` | `atendimento_id (nested)` | ✅ |

**Campos extras só nossos:**

- `id` (BIGSERIAL)
- `posicao_atual_item_id` (BIGINT FK SET NULL)

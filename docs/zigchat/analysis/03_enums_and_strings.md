# 03 — Enums + booleans-em-string

> ZigChat tem POUCOS enums GraphQL — quase tudo é string com convenção.
> O padrão dominante é boolean-em-string `"S"`/`"N"` (ativo, principal, etc).

## Enums GraphQL formais

_Nenhum enum formal no schema._

## Boolean-em-string (campos `"S"`/`"N"`)

Identificados por nome (`ativo`, `principal`, `padrao`, etc) com `String` ou `String!`.
Lista de campos detectados em todos os OBJECT types:

| Campo | Em N types | Tipo predominante | Sample types (3) |
|---|---:|---|---|
| `ativo` | 25 | `String` | `CategoriaProduto`, `Cliente`, `Empresa` |
| `enviar_fila_atendimento` | 2 | `String` | `Empresa`, `Departamento` |
| `lida` | 2 | `Float` | `Atendimento`, `UsuarioAtendimentoTimestamp` |
| `numero_verificado` | 1 | `String` | `Cliente` |
| `desconsiderar_turno_cliente` | 1 | `String` | `Cliente` |
| `ignora_inatividade` | 1 | `String` | `Cliente` |
| `encerra_atendimento` | 1 | `String` | `Departamento` |
| `padrao` | 1 | `String!` | `Conexao` |
| `informa_nome` | 1 | `String!` | `Atendimento` |
| `iniciado_cliente` | 1 | `String` | `Atendimento` |
| `finalizacao_usuario` | 1 | `String` | `Atendimento` |
| `cliente_em_atendimento` | 1 | `Boolean` | `Atendimento` |
| `atendimento_automatico` | 1 | `String` | `Atendimento` |
| `mudar_para_manual` | 1 | `String` | `Item` |
| `principal` | 1 | `String!` | `Menu` |
| `solicitar_nome` | 1 | `String!` | `Menu` |
| `coleta_informacao` | 1 | `String!` | `Menu` |
| `enviar_msg_final_coleta` | 1 | `String!` | `Menu` |
| `menu_moderno` | 1 | `String!` | `Menu` |
| `confirmar_coleta` | 1 | `String!` | `Menu` |
| `exibir_comando_menu_item` | 1 | `String` | `Menu` |
| `menu_ia` | 1 | `String` | `Menu` |
| `resposta_confidencial` | 1 | `String` | `Menu` |

## "Enums" semânticos descobertos por análise de naming

Campos numéricos com semântica de enum (ex: `acao` em Item, `tipo` em vários):

| Campo | Semântica provável |
|---|---|
| `acao` | Ação do menu_item — provável enum numérico (1=submenu, 2=transferir_dep, 3=chamar_agente, ...). Comparar com nosso CHECK acao_tipo string. |
| `tipo` | Múltiplas semânticas. Em `Conexao` provavelmente engine (twilio/evolution/waba); em `Atendimento` é canal_id; em `ModeloIA` é "chat"/"embedding"/"midia". |
| `tipo_atendimento` | Em Conexao + Cliente. Provável: 1=manual, 2=ia, 3=hibrido. |
| `tipo_memoria` | Em AgenteIA. Provável: "buffer"/"summary"/"window". |
| `acao_limite_custo` | Em AgenteIA. Provável: "menu"/"encerrar"/"continuar"/"bloquear" (alinhado com nosso `limite_custo_acao`). |
| `engine` | Em Conexao. Twilio/Evolution/WABA/etc. |
| `tipo_conexao` | Em McpServer. stdio/sse/http. |
| `modelo_provedor` | Em AgenteIA + ModeloIA. openai/anthropic/google/openrouter. |
| `state` | Em Cliente + Conexao. Estado WhatsApp Web (CONNECTED/DISCONNECTED/QR). |
| `status` | Genérico — significado varia por contexto (open/closed/pending/etc). |
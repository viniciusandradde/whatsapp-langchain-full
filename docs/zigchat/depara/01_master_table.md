# 01 — Master table: todas as entidades ZigChat → Nexus

[← Voltar ao índice](./README.md)

> Visão geral de TODOS os types ZigChat OBJECT relevantes (sem Inputs / DataTables / FilterInputs) mapeados ao equivalente Nexus.

## Legenda de status

- ✅ **Existe** — entidade Nexus cobre todos os campos ZigChat relevantes
- 🟡 **Parcial** — entidade Nexus existe mas faltam campos importantes
- 🔵 **Existe diferente** — semântica equivalente mas estrutura distinta (não dá pra comparar field-by-field)
- ❌ **Pendente** — entidade ZigChat não existe no Nexus
- ➖ **Não aplica** — ZigChat tem mas é redundante / específico do legado deles

## Categoria: Agente IA

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `AgenteIA` | `agente_ia` | 🟡 | 039 | Falta: `tipo_memoria`, `janela_memoria`, `timeout_minutos`, `acao_limite_menu_id`, `modelo_provedor`/`modelo_nome` separados |
| `AgenteIAToolConfig` | `agente_ia.tools_config` (JSONB) | 🔵 | 039 | Nosso é JSONB único; ZigChat tem tabela própria. Decisão: manter JSONB (mais flexível). |
| `BaseConhecimento` | `documento_conhecimento` | 🟡 | 015 | Nome diferente. Falta many-to-many explícita com `agente_ia` (nosso usa array IDs). |
| `McpServer` | ❌ | ❌ | nova 042 | Roadmap nosso (Fase 2). MCP integration. |
| `ModeloIA` | ❌ | ❌ | nova 044 | Catálogo de modelos LLM com custo. |
| `IATopAgente` | ❌ | ❌ | nova 056 | Métrica/ranking de agentes. |
| `IABudget` | ❌ | ❌ | nova 057 | Orçamento mensal por empresa. |
| `IAExecucaoDetalhe` / `IAExecucaoFiltro` / `IAExecucaoLista` | `audit_log` (parcial) | 🟡 | 036 | Nosso audit cobre eventos genéricos. Falta detalhe LLM (tokens in/out, latência, custo). |

## Categoria: Menu chatbot

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Menu` | `menu_chatbot` | 🟡 | 040 | Falta: `atalho`, `solicitar_nome`, `coleta_*`, `menu_moderno`, `menu_ia`, `auto_navegar_para_item_id`, `qtde_acesso`, `arquivo` |
| `Item` | `menu_item` | 🟡 | 040 | Falta 7 ações (transferir_atendente, enviar_template, chamar_webhook, enviar_link, pesquisa_csat, mudar_manual, setar_nome) + `comando`, `nota_min/max`, `grupo`, `webhook_url`, `link` |
| `MenuItemArquivo` | ❌ | ❌ | nova 041 | Anexo (PDF/imagem) atrelado a item de menu. |
| `MenuModernoMetadado` / `MenuModernoBtn` / `MenuModernoBtnText` | ❌ | ❌ | nova 041 | Suporte a botões interativos do WhatsApp. |
| `AtendimentoMenuHistorico` | `atendimento_menu_historico` | 🟡 | 040 | Falta: `nanoid` + `resposta` (texto cru cliente). |

## Categoria: Atendimento + mensagem

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Atendimento` | `atendimento` | 🟡 | 010+035 | Falta: `protocolo`, `qtde_resposta_invalida`, `aba_id`, `iniciado_cliente`, `finalizacao_usuario`, `nome_contato`, `solicitou_encerramento`, `tipo`, `canal` (numérico — nosso conexao_id basta) |
| `AtendimentoMensagem` | `message_queue` | 🔵 | 001+002 | Estrutura diferente (fila vs histórico). Nosso preserva incoming + response na mesma row; ZigChat usa rows separadas (mensagem + resposta). |
| `UsuarioAtendimentoTimestamp` | ❌ | ❌ | nova 052 | Quem viu cada atendimento e quando (read receipts internos). |
| `AtendimentoTransferencia` | ❌ | ❌ | nova 053 | Histórico de transferências entre depto/atendente. |
| `AtendimentoMenuHistorico` | (já em menu) | — | 040 | — |
| `AtendiemntoPayload` (sic) | ❌ | ➖ | n/a | Typo do schema deles, parece DTO interno. |

## Categoria: Cliente CRM

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Cliente` | `cliente` | ✅ | 010+038 | Já bem completo. Faltam: `imagem_perfil`, `imagem_perfil_completa`, `visto_ultimo`, `state` (estado WhatsApp), `numero_verificado`, `desconsiderar_turno_cliente`, `field_1..5` (campos custom), `tipo_atendimento`, `lid` (linked identity), `ignora_inatividade`, `aba_id`, `msg_apos_encerramento`, `webhook_url`, `hook_id`, `tags_secundarias`, `remoteid`, `bairro/endereco/cep` (parcial — temos cep+logradouro+bairro mas não inteiramente), `faixa_salarial_inicial/final`, `tag_id` |
| `Tag` | `cliente_tag` | 🔵 | 010 | Nosso é só (cliente_id, tag_string). ZigChat tem `Tag` como entidade própria com `id`, `nome`, `cor`, `descricao`, `hook_id`. Migrar pra entidade própria seria útil. |
| `Aba` | ❌ | ❌ | nova 050 | Painel/quadro custom de organização de atendimentos (estilo Trello). |
| `AbaInput` | ❌ | ❌ | (input) | — |
| `Cidade` / `Estado` | ❌ | ➖ | n/a | Fixures geográficas. Nosso `cliente.cidade` (text) + `cliente.uf` (char(2)) é mais simples. |

## Categoria: Conexão / Canal

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Conexao` | `conexao` | 🟡 | 009+020 | Falta: `tipo_atendimento` (manual/ia/hibrido), `tipo` (canal), `agente_ia_id` (nosso é texto `default_agent_id`), `engine` (similar ao nosso `provider`), `waba_*` (temos via `waba_template`?), `state`. |
| `CanalExterno` | `conexao` (parcial) | 🔵 | 009 | ZigChat parece separar "canal" (WhatsApp/Telegram) de "conexao" (instância). Nosso unifica. |
| `TelegramChat` | ❌ | ❌ | nova 059 | Suporte Telegram (não temos). Roadmap futuro. |

## Categoria: Departamento / Horário

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Departamento` | `departamento` | 🟡 | 017+032 | Falta: `posicao_fila_transferencia`, `notifica_cliente_id`, `encerra_atendimento`, `grupo`, `tolerancia_atend_inativo`, `enviar_fila_atendimento`, `menu_coleta_id`, `retencao_msg`, `turno_id` (FK pra `Turno`). Nosso tem hierarquia (`parent_id`) que ZigChat não tem. |
| `Turno` | `horario_funcionamento` | 🔵 | 017 | Nosso é por departamento. ZigChat tem `Turno` como entidade reutilizável (departamentos podem compartilhar turno). |
| `Feriado` | `feriado` | ✅ | 017 | Equivalente direto. |

## Categoria: Campanha / Disparo

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Campanha` | `campanha` | 🟡 | 034 | Falta: agendamento programado (`scheduled_at`), template (`modelo_mensagem_id`), filtros de destinatário (segmento/tag), tipo de envio (broadcast/transactional). |
| `CampanhaDestinatario` (implícito) | `campanha_destinatario` | ✅ | 034 | Equivalente direto. |

## Categoria: Modelo de mensagem (templates)

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `ModeloMensagem` | `modelo_mensagem` | ✅ | 011 | Equivalente direto. ZigChat pode ter `tipo` adicional (HSM vs free). |

## Categoria: Hook / Webhook

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Hook` | `hook` | 🟡 | 012 | Falta: `headers` customizáveis, `metodo` (GET/POST), `timeout_ms`. |
| `HookLog` (implícito) | `hook_log` | ✅ | 012 | Equivalente. |
| `HookDeadLetter` (implícito) | `hook_dead_letter` | ✅ | 023 | **Diferencial nosso** — DLQ + retry com backoff exponencial. ZigChat parece ter só log. |

## Categoria: Produto (catálogo)

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Produto` | ❌ | ❌ | nova 060 | Catálogo. Decidir se precisamos. |
| `CategoriaProduto` | ❌ | ❌ | nova 060 | — |
| `OpcaoProduto` | ❌ | ❌ | nova 060 | Variações (tamanho, cor, etc). |

## Categoria: Autenticação / RBAC

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Usuario` | `auth.user` (Better Auth) | 🔵 | 003+004 | Schema diferente. Better Auth gerencia identity; nosso `empresa_membro` faz vínculo com empresa. |
| `Permissao` | `permissao` | ✅ | 031 | Equivalente. |
| `Grupo` | `perfil_acesso` | ✅ | 031 | Nosso "perfil" = ZigChat "grupo". |
| `LoginEvent` (implícito) | `auth_login_event` | ✅ | 026 | Equivalente. |
| `PasswordReset` | `auth.password_reset_pending` | ✅ | 025 | — |

## Categoria: Empresa / Billing

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Empresa` | `empresa` | 🟡 | 007+008 | Faltam: campos billing (CNPJ tax info, endereço fiscal), `menu_coleta_id`, `hook_id`. |
| `Plano` | ❌ | ❌ | nova 058 | Catálogo de planos comerciais (free/pro/enterprise). Nosso `empresa.plano` é só TEXT. |
| `Transacao` | ❌ | ❌ | nova 058 | Histórico financeiro. |
| `PushDevice` | ❌ | ❌ | nova 054 | Notificações push pra atendentes mobile. |
| `EmpresaMembro` (implícito) | `empresa_membro` | ✅ | 003 | Equivalente. |

## Categoria: Variável de ambiente

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `VariavelAmbiente` | `variavel_ambiente` | ✅ | 016 | Equivalente direto. |

## Categoria: Calendário / Agendamento

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `CalendarioEvento` | `agendamento` (parcial) | 🟡 | 027 | Nosso é Calendar Agent v2 (mais avançado, integração Google). ZigChat parece ter só armazenamento simples. **Diferencial nosso.** |

## Categoria: Arquivo / Pasta

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Pasta` | `pasta` | ✅ | 033 | Equivalente. |
| `Arquivo` | (sem tabela única) | 🔵 | n/a | Nosso usa `documento_conhecimento` (RAG) ou storage externo. ZigChat tem entidade dedicada — útil pra anexos genéricos. |

## Categoria: Aviso / Termo

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `Aviso` | ❌ | ❌ | nova 055 | Notificações da plataforma pra usuários (banner sistema). |
| `AvisoUsuario` | ❌ | ❌ | nova 055 | Quem leu qual aviso. |
| `Termo` | ❌ | ❌ | nova 058 | Termos de uso aceitos. |

## Categoria: Formulário

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `FormPadrao` | ❌ | ❌ | nova 049 | Formulários de coleta (CSAT, lead capture, etc). Acima de menu chatbot wizard. |

## Categoria: Analytics / Logs

| ZigChat | Nexus | Status | Mig | Notas |
|---|---|---|---|---|
| `GeralLog` | `audit_log` | 🔵 | 036 | Estrutura diferente. Nosso é tipado por entidade; ZigChat parece ser log genérico. |
| `Contador` | ❌ | ➖ | n/a | Counter genérico (provavelmente analytics legacy). Não recomendado migrar. |

## Categoria: Específico ZigChat (skip)

Não migrar — ou são legacy ZigChat ou redundante com nossa stack:

- `ConStateUpdate` — sub-tipo de Conexao update (interno deles)
- `DecryptJob` — workflow de decrypt de arquivo (provavelmente caso específico WABA media)
- `Termo` — termos de uso aceitos (resolver com Better Auth metadata)
- `IABudget` — pode ser implementado depois se governança custo virar prioridade
- `AtendiemntoPayload` (sic) — typo, é DTO interno

## Resumo numérico

| Status | Quantidade |
|---|---:|
| ✅ Existe direto | ~12 entidades |
| 🟡 Parcial (precisa ALTER) | ~10 entidades |
| 🔵 Existe diferente | ~6 entidades |
| ❌ Pendente CREATE | ~22 entidades |
| ➖ Não migrar | ~6 entidades |

Total mapped: ~56 entidades ZigChat principais. Restante (~70 types) são `XInput`, `XListInput`, `XFilterInput`, `XDataTable` (wrappers) que não precisam mapping direto.

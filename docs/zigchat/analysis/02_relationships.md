# 02 — Relacionamentos entre types

> FKs detectadas pela convenção `xxx_id` (Int/Float) + listas `[Y!]` em campos.
> Não enxerga FKs com nome custom (ex: `usuario_atendente_id` → Usuario).

## Top 30 types mais referenciados (entrando)

| Type | Refs entrando | Origem (sample 5) |
|---|---:|---|
| `Empresa` | 43 | `CategoriaProduto.empresa_id`, `Produto.empresa_id`, `OpcaoProduto.empresa_id`, `Cliente.empresa_id`, `Transacao.empresa` (+38 mais) |
| `Usuario` | 38 | `Cliente.criacao_usuario_id`, `Cliente.alteracao_usuario_id`, `Cliente.atendente_usuario_id`, `Empresa.criacao_usuario_id`, `Empresa.alteracao_usuario_id` (+33 mais) |
| `Cliente` | 15 | `CategoriaProduto.clientes`, `Departamento.notifica_cliente_id`, `AtendimentoMensagem.cliente_id`, `AtendimentoMensagem.mencaoCliente`, `Atendimento.cliente_id` (+10 mais) |
| `Atendimento` | 11 | `AtendimentoMensagem.atendimento_id`, `UsuarioAtendimentoTimestamp.atendimento_id`, `AtendimentoDataTable.rows`, `AtendimentoTransferencia.atendimento_id`, `AtendimentoMenuHistorico.atendimento_id` (+6 mais) |
| `Conexao` | 10 | `Empresa.conexoes`, `Usuario.conexoes`, `AtendimentoMensagem.conexao_id`, `Atendimento.conexao_id`, `Menu.conexao_id` (+5 mais) |
| `AgenteIA` | 10 | `Conexao.agente_ia_id`, `BaseConhecimento.agentes_ia`, `McpServer.agentes_ia`, `AgenteIAToolConfig.agente_ia_id`, `AtendimentoMensagem.agente_ia_id` (+5 mais) |
| `Menu` | 8 | `Empresa.menu_coleta_id`, `Departamento.menu_coleta_id`, `Atendimento.menu_id`, `Item.menu_id`, `MenuItemArquivo.menu_id` (+3 mais) |
| `Hook` | 7 | `Cliente.hook_id`, `Empresa.hook_id`, `Tag.hook_id`, `Item.hook_id`, `HookDataTable.rows` (+2 mais) |
| `Item` | 6 | `Atendimento.item_id`, `Menu.items`, `Menu.auto_navegar_para_item_id`, `ItemDataTable.rows`, `MenuItemArquivo.item_id` (+1 mais) |
| `Departamento` | 5 | `Usuario.departamentos`, `Atendimento.departamento_id`, `AtendimentoTransferencia.departamento_id`, `DepartamentoDataTable.rows`, `AtendiemntoPayload.departamento_id` |
| `Produto` | 4 | `CategoriaProduto.produtos`, `OpcaoProduto.produto_id`, `OpcaoProduto.itens`, `ProdutoDataTable.rows` |
| `Tag` | 4 | `Cliente.tag_id`, `Cliente.tags`, `Atendimento.atendimentoTags`, `TagDataTable.rows` |
| `CanalExterno` | 4 | `Usuario.canais`, `Departamento.canais`, `CanalExternoDataTable.rows`, `ClienteMencao.canais` |
| `Turno` | 4 | `Usuario.turno_id`, `Departamento.turno_id`, `TurnoHorario.turno_id`, `TurnoDataTable.rows` |
| `Campanha` | 4 | `AtendimentoMensagem.campanha_id`, `Atendimento.campanha_id`, `CampanhaDataTable.rows`, `CampanhaCliente.campanha_id` |
| `Aba` | 3 | `Cliente.aba_id`, `Atendimento.aba_id`, `AbaDataTable.rows` |
| `Permissao` | 2 | `Usuario.permissoes`, `GrupoSistema.permissoes` |
| `BaseConhecimento` | 2 | `AgenteIA.base_conhecimentos`, `BaseConhecimentoDataTable.rows` |
| `McpServer` | 2 | `AgenteIA.mcp_servers`, `McpServerDataTable.rows` |
| `FormPadrao` | 2 | `FormPadraoDataTable.rows`, `FormPadraoAtendimento.form_padrao_id` |
| `CalendarioEvento` | 2 | `CalendarioEventoDataTable.rows`, `CalendarioEventoHorario.calendario_evento_id` |
| `Aviso` | 2 | `AvisoDataTable.rows`, `AvisoUsuario.aviso_id` |
| `Arquivo` | 2 | `Pasta.arquivos`, `ArquivoDataTable.rows` |
| `CategoriaProduto` | 1 | `CategoriaProdutoDataTable.rows` |
| `OpcaoProduto` | 1 | `Produto.opcoes` |
| `Cidade` | 1 | `Cliente.cidade_id` |
| `Transacao` | 1 | `Empresa.transacoes` |
| `TurnoHorario` | 1 | `Turno.horarios` |
| `AgenteIAToolConfig` | 1 | `AgenteIA.tool_configs` |
| `AtendimentoMensagem` | 1 | `Atendimento.mensagens` |

## Detalhe completo (saindo)

Para cada `OBJECT`, lista FKs detectadas + LIST<X>.

### `Aba`

**FKs:**
- `empresa_id` → `Empresa`
- `usuario_id` → `Usuario`

### `AbaDataTable`

**Listas:**
- `rows: [Aba]`

### `AgenteIA`

**FKs:**
- `empresa_id` → `Empresa`
- `acao_limite_menu_id` → `?`

**Listas:**
- `base_conhecimentos: [BaseConhecimento]`
- `mcp_servers: [McpServer]`
- `tool_configs: [AgenteIAToolConfig]`

### `AgenteIADataTable`

**Listas:**
- `rows: [AgenteIA]`

### `AgenteIAToolConfig`

**FKs:**
- `agente_ia_id` → `AgenteIA`
- `empresa_id` → `Empresa`

### `Arquivo`

**FKs:**
- `empresa_id` → `Empresa`
- `criacao_usuario_id` → `Usuario`
- `dono_usuario_id` → `?`

### `ArquivoDataTable`

**Listas:**
- `rows: [Arquivo]`

### `AtendiemntoPayload`

**FKs:**
- `atendente_usuario_id` → `Usuario`
- `usuario_id` → `Usuario`
- `departamento_id` → `Departamento`
- `old_atendente_usuario_id` → `?`
- `old_departamento_id` → `?`
- `atendimento_id` → `Atendimento`

### `Atendimento`

**FKs:**
- `cliente_id` → `Cliente`
- `usuario_id` → `Usuario`
- `atendente_usuario_id` → `Usuario`
- `menu_id` → `Menu`
- `departamento_id` → `Departamento`
- `empresa_id` → `Empresa`
- `item_id` → `Item`
- `aba_id` → `Aba`
- `conexao_id` → `Conexao`
- `campanha_id` → `Campanha`
- `agente_ia_id` → `AgenteIA`

**Listas:**
- `atendimentoTags: [Tag]`
- `mensagens: [AtendimentoMensagem]`
- `usuarioTimestamp: [UsuarioAtendimentoTimestamp]`

### `AtendimentoDataTable`

**Listas:**
- `rows: [Atendimento]`

### `AtendimentoLazyResponse`

**Listas:**
- `atendimentos: [Atendimento]`

### `AtendimentoMensagem`

**FKs:**
- `atendimento_id` → `Atendimento`
- `conexao_id` → `Conexao`
- `empresa_id` → `Empresa`
- `cliente_id` → `Cliente`
- `atendente_usuario_id` → `Usuario`
- `contact_cliente_id` → `?`
- `campanha_id` → `Campanha`
- `agente_ia_id` → `AgenteIA`

**Listas:**
- `mencaoCliente: [Cliente]`

### `AtendimentoMenuHistorico`

**FKs:**
- `atendimento_id` → `Atendimento`
- `cliente_id` → `Cliente`
- `menu_id` → `Menu`
- `item_id` → `Item`

### `AtendimentoMenuHistoricoDataTable`

**Listas:**
- `rows: [AtendimentoMenuHistorico]`

### `AtendimentoTransferencia`

**FKs:**
- `atendimento_id` → `Atendimento`
- `atendente_usuario_id` → `Usuario`
- `criacao_usuario_id` → `Usuario`
- `departamento_id` → `Departamento`

### `AtendimentoTransferenciaDataTable`

**Listas:**
- `rows: [AtendimentoTransferencia]`

### `AvisoDataTable`

**Listas:**
- `rows: [Aviso]`

### `AvisoUsuario`

**FKs:**
- `aviso_id` → `Aviso`
- `usuario_id` → `Usuario`

### `BaseConhecimento`

**FKs:**
- `empresa_id` → `Empresa`

**Listas:**
- `agentes_ia: [AgenteIA]`

### `BaseConhecimentoDataTable`

**Listas:**
- `rows: [BaseConhecimento]`

### `CalendarioEvento`

**FKs:**
- `empresa_id` → `Empresa`

**Listas:**
- `horarios: [CalendarioEventoHorario]`
- `conexoes: [Conexao]`

### `CalendarioEventoDataTable`

**Listas:**
- `rows: [CalendarioEvento]`

### `CalendarioEventoHorario`

**FKs:**
- `calendario_evento_id` → `CalendarioEvento`

### `Campanha`

**FKs:**
- `menu_id` → `Menu`
- `conexao_id` → `Conexao`
- `empresa_id` → `Empresa`

### `CampanhaCliente`

**FKs:**
- `campanha_id` → `Campanha`
- `cliente_id` → `Cliente`
- `empresa_id` → `Empresa`

### `CampanhaClienteDataTable`

**Listas:**
- `rows: [CampanhaCliente]`

### `CampanhaDataTable`

**Listas:**
- `rows: [Campanha]`

### `CanalExterno`

**FKs:**
- `empresa_id` → `Empresa`

### `CanalExternoDataTable`

**Listas:**
- `rows: [CanalExterno]`

### `CategoriaProduto`

**FKs:**
- `empresa_id` → `Empresa`

**Listas:**
- `produtos: [Produto]`
- `clientes: [Cliente]`

### `CategoriaProdutoDataTable`

**Listas:**
- `rows: [CategoriaProduto]`

### `Cliente`

**FKs:**
- `tag_id` → `Tag`
- `empresa_id` → `Empresa`
- `cidade_id` → `Cidade`
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`
- `aba_id` → `Aba`
- `atendente_usuario_id` → `Usuario`
- `hook_id` → `Hook`

**Listas:**
- `tags: [Tag]`

### `ClienteAnotacao`

**FKs:**
- `cliente_id` → `Cliente`

### `ClienteAnotacaoDataTable`

**Listas:**
- `rows: [ClienteAnotacao]`

### `ClienteConexaoUltimaMensagem`

**FKs:**
- `cliente_id` → `Cliente`
- `conexao_id` → `Conexao`

### `ClienteDataTable`

**Listas:**
- `rows: [Cliente]`

### `ClienteMencao`

**FKs:**
- `cliente_id` → `Cliente`
- `cliente_mencao_id` → `ClienteMencao`

**Listas:**
- `canais: [CanalExterno]`

### `Conexao`

**FKs:**
- `empresa_id` → `Empresa`
- `agente_ia_id` → `AgenteIA`

### `ConexaoDataTable`

**Listas:**
- `rows: [Conexao]`

### `Contador`

**FKs:**
- `empresa_id` → `Empresa`

### `DecryptJob`

**FKs:**
- `empresa_id` → `Empresa`

### `Departamento`

**FKs:**
- `empresa_id` → `Empresa`
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`
- `notifica_cliente_id` → `Cliente`
- `menu_coleta_id` → `Menu`
- `turno_id` → `Turno`

**Listas:**
- `usuarios: [Usuario]`
- `canais: [CanalExterno]`

### `DepartamentoDataTable`

**Listas:**
- `rows: [Departamento]`

### `Empresa`

**FKs:**
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`
- `menu_coleta_id` → `Menu`
- `hook_id` → `Hook`

**Listas:**
- `transacoes: [Transacao]`
- `conexoes: [Conexao]`

### `EmpresaDataTable`

**Listas:**
- `rows: [Empresa]`

### `FormPadrao`

**FKs:**
- `empresa_id` → `Empresa`

### `FormPadraoAtendimento`

**FKs:**
- `criacao_usuario_id` → `Usuario`
- `atendimento_id` → `Atendimento`
- `cliente_id` → `Cliente`
- `form_padrao_id` → `FormPadrao`
- `empresa_id` → `Empresa`

### `FormPadraoAtendimentoDataTable`

**Listas:**
- `rows: [FormPadraoAtendimento]`

### `FormPadraoDataTable`

**Listas:**
- `rows: [FormPadrao]`

### `GeralLog`

**FKs:**
- `empresa_id` → `Empresa`
- `usuario_id` → `Usuario`

### `GeralLogDataTable`

**Listas:**
- `rows: [GeralLog]`

### `GrupoSistema`

**FKs:**
- `empresa_id` → `Empresa`

**Listas:**
- `permissoes: [Permissao]`

### `GrupoSistemaDataTable`

**Listas:**
- `rows: [GrupoSistema]`

### `Hook`

**FKs:**
- `empresa_id` → `Empresa`

### `HookDataTable`

**Listas:**
- `rows: [Hook]`

### `HookTask`

**FKs:**
- `empresa_id` → `Empresa`
- `hook_id` → `Hook`

### `HookTaskDataTable`

**Listas:**
- `rows: [HookTask]`

### `HookUrl`

**FKs:**
- `hook_id` → `Hook`
- `empresa_id` → `Empresa`

### `HookUrlDataTable`

**Listas:**
- `rows: [HookUrl]`

### `HorarioFuncionamento`

**FKs:**
- `empresa_id` → `Empresa`

### `IADashboard`

**Listas:**
- `diario: [IAUsoDiario]`
- `anual: [IAUsoAnualItem]`
- `top_agentes: [IATopAgente]`

### `IAExecucaoDetalhe`

**FKs:**
- `agente_ia_id` → `AgenteIA`
- `atendimento_id` → `Atendimento`

### `IAExecucaoItem`

**FKs:**
- `agente_ia_id` → `AgenteIA`
- `atendimento_id` → `Atendimento`

### `IAExecucaoLista`

**Listas:**
- `rows: [IAExecucaoItem]`

### `IATopAgente`

**FKs:**
- `agente_ia_id` → `AgenteIA`

### `Item`

**FKs:**
- `menu_id` → `Menu`
- `empresa_id` → `Empresa`
- `contato_cliente_id` → `Cliente`
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`
- `acao_modelo_mensagem_id` → `?`
- `acao_menu_id` → `?`
- `acao_departamento_id` → `?`
- `acao_atendente_id` → `?`
- `hook_id` → `Hook`
- `acao_agente_ia_id` → `?`

### `ItemDataTable`

**Listas:**
- `rows: [Item]`

### `McpServer`

**FKs:**
- `empresa_id` → `Empresa`

**Listas:**
- `agentes_ia: [AgenteIA]`

### `McpServerDataTable`

**Listas:**
- `rows: [McpServer]`

### `Menu`

**FKs:**
- `conexao_id` → `Conexao`
- `empresa_id` → `Empresa`
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`
- `auto_navegar_para_item_id` → `Item`

**Listas:**
- `items: [Item]`

### `MenuDataTable`

**Listas:**
- `rows: [Menu]`

### `MenuItemArquivo`

**FKs:**
- `menu_id` → `Menu`
- `item_id` → `Item`

### `MenuModernoMetadado`

**Listas:**
- `buttons: [MenuModernoBtn]`

### `ModeloMensagem`

**FKs:**
- `empresa_id` → `Empresa`
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`
- `usuario_id` → `Usuario`

### `ModeloMensagemDataTable`

**Listas:**
- `rows: [ModeloMensagem]`

### `OpcaoProduto`

**FKs:**
- `empresa_id` → `Empresa`
- `produto_id` → `Produto`

**Listas:**
- `itens: [Produto]`

### `Pasta`

**FKs:**
- `empresa_id` → `Empresa`
- `criacao_usuario_id` → `Usuario`
- `dono_usuario_id` → `?`

**Listas:**
- `arquivos: [Arquivo]`

### `PastaDataTable`

**Listas:**
- `rows: [Pasta]`

### `Pedido`

**FKs:**
- `atendimento_id` → `Atendimento`
- `cliente_id` → `Cliente`

### `Produto`

**FKs:**
- `empresa_id` → `Empresa`
- `categoria_id` → `?`

**Listas:**
- `opcoes: [OpcaoProduto]`

### `ProdutoDataTable`

**Listas:**
- `rows: [Produto]`

### `PushDevice`

**FKs:**
- `usuario_id` → `Usuario`
- `empresa_id` → `Empresa`

### `PushDeviceUsuario`

**FKs:**
- `usuario_id` → `Usuario`

### `SistemaMensagem`

**FKs:**
- `empresa_id` → `Empresa`
- `criacao_usuario_id` → `Usuario`
- `alteracao_usuario_id` → `Usuario`

### `SistemaMensagemDataTable`

**Listas:**
- `rows: [SistemaMensagem]`

### `Tag`

**FKs:**
- `empresa_id` → `Empresa`
- `hook_id` → `Hook`

### `TagDataTable`

**Listas:**
- `rows: [Tag]`

### `Termo`

**Listas:**
- `usuarios: [Usuario]`

### `TestarMcpServerResult`

**Listas:**
- `tools: [McpToolResult]`

### `TotalUsuarioEmpresa`

**FKs:**
- `empresa_id` → `Empresa`

### `Transacao`

**Listas:**
- `empresa: [Empresa]`

### `Turno`

**FKs:**
- `criacao_usuario_id` → `Usuario`
- `empresa_id` → `Empresa`

**Listas:**
- `horarios: [TurnoHorario]`

### `TurnoDataTable`

**Listas:**
- `rows: [Turno]`

### `TurnoHorario`

**FKs:**
- `turno_id` → `Turno`

### `UserWebNotification`

**FKs:**
- `usuario_id` → `Usuario`

### `Usuario`

**FKs:**
- `empresa_id` → `Empresa`
- `padrao_conexao_id` → `?`
- `turno_id` → `Turno`

**Listas:**
- `departamentos: [Departamento]`
- `permissoes: [Permissao]`
- `canais: [CanalExterno]`
- `conexoes: [Conexao]`

### `UsuarioAtendimentoTimestamp`

**FKs:**
- `usuario_id` → `Usuario`
- `atendimento_id` → `Atendimento`

### `UsuarioCliente`

**FKs:**
- `usuario_id` → `Usuario`
- `cliente_id` → `Cliente`

### `UsuarioDataTable`

**Listas:**
- `rows: [Usuario]`

### `VariavelAmbiente`

**FKs:**
- `empresa_id` → `Empresa`

### `VariavelAmbienteDataTable`

**Listas:**
- `rows: [VariavelAmbiente]`

### `WabaSaldo`

**FKs:**
- `empresa_id` → `Empresa`
- `conexao_id` → `Conexao`

### `WabaTemplate`

**FKs:**
- `empresa_id` → `Empresa`

### `WabaTemplateDataTable`

**Listas:**
- `rows: [WabaTemplate]`

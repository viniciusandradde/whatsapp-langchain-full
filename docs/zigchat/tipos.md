# ZigChat — tipos

> Extraído por introspecção de `https://dev.zigchat.com.br/api/graphql` em 2026-09-16.
> Referência de PRODUTO (paridade de features). A integração runtime está arquivada — ver decisão de 2026-09-16.

**334** tipos (inclui internos do GraphQL).

### Aba (OBJECT)

- `id`: Int!
- `descricao`: String!
- `empresa_id`: Int!
- `usuario_id`: Int

### AbaDataTable (OBJECT)

- `rows`: [Aba!]
- `count`: Int

### AbaFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString

### AbaInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `atendimento_id`: Int
- `usuario_id`: Int
- `ativo`: String

### AbaListInput (INPUT_OBJECT)

- `filters`: AbaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AgenteIA (OBJECT)

- `id`: Int!
- `nome`: String!
- `descricao`: String
- `modelo_provedor`: String!
- `modelo_nome`: String!
- `temperatura`: Float
- `max_tokens`: Int
- `prompt_sistema`: String!
- `tipo_memoria`: String!
- `janela_memoria`: Int
- `resumo_percentual`: Int
- `limite_custo_ia_por_atendimento`: Float
- `timeout_minutos`: Int
- `empresa_id`: Int
- `ativo`: String
- `data_criacao`: String
- `data_hora_atualizacao`: String
- `criacao_usuario`: String
- `alteracao_usuario`: String
- `acao_limite_custo`: String!
- `acao_limite_menu_id`: Int
- `base_conhecimentos`: [BaseConhecimento!]
- `mcp_servers`: [McpServer!]
- `tool_configs`: [AgenteIAToolConfig!]

### AgenteIADataTable (OBJECT)

- `rows`: [AgenteIA!]
- `count`: Int

### AgenteIAFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### AgenteIAInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `descricao`: String
- `modelo_provedor`: String
- `modelo_nome`: String
- `temperatura`: Float
- `max_tokens`: Int
- `prompt_sistema`: String
- `tipo_memoria`: String
- `janela_memoria`: Int
- `resumo_percentual`: Int
- `limite_custo_ia_por_atendimento`: Float
- `timeout_minutos`: Int
- `ativo`: String
- `acao_limite_custo`: String
- `acao_limite_menu_id`: Int
- `base_conhecimento_ids`: [Int!]
- `mcp_server_ids`: [Int!]
- `tool_configs`: [AgenteIAToolConfigInput!]

### AgenteIAListInput (INPUT_OBJECT)

- `filters`: AgenteIAFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AgenteIAToolConfig (OBJECT)

- `id`: Int!
- `agente_ia_id`: Int!
- `tool_name`: String!
- `modo`: String
- `ids_permitidos`: String
- `empresa_id`: Int!

### AgenteIAToolConfigInput (INPUT_OBJECT)

- `tool_name`: String!
- `modo`: String
- `ids_permitidos`: [String!]

### Alerta (OBJECT)

- `uuid`: String!
- `empresa_id`: Float!
- `empresa`: Empresa
- `conexao_id`: Float!
- `conexao`: Conexao
- `tipo`: String!
- `nivel`: String!
- `situacao`: String!
- `descricao`: String
- `data_hora_referencia`: DateTime!
- `data_hora_criacao`: DateTime
- `data_hora_resolucao`: DateTime
- `resolucao_usuario`: String

### AlertaDataTable (OBJECT)

- `rows`: [Alerta!]
- `count`: Int

### AlertaFilterInput (INPUT_OBJECT)

- `situacao`: PrimeFilterItemString
- `nivel`: PrimeFilterItemString
- `tipo`: PrimeFilterItemString

### AlertaInput (INPUT_OBJECT)

- `uuid`: String
- `situacao`: String

### AlertaListInput (INPUT_OBJECT)

- `filters`: AlertaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AlterarSenhaInput (INPUT_OBJECT)

- `id`: Int!
- `senha`: String
- `nova_senha`: String!
- `confirmar_senha`: String!

### Arquivo (OBJECT)

- `uuid`: String!
- `pasta_uuid`: String
- `empresa_id`: Int!
- `criacao_usuario_id`: Int
- `dono_usuario_id`: Int
- `original_name`: String!
- `stored_name`: String!
- `description`: String
- `keywords`: String
- `extension`: String
- `mime_type`: String
- `type`: String
- `size_bytes`: Float
- `file_key`: String!
- `file_path`: String!
- `thumbnail_key`: String!
- `thumbnail_path`: String
- `metadata`: String
- `source`: String!
- `disk`: String!
- `delete_file`: String!
- `data_hora_criacao`: DateTime
- `pasta`: Pasta
- `empresa`: Empresa
- `criacaoUsuario`: Usuario
- `donoUsuario`: Usuario

### ArquivoDataTable (OBJECT)

- `rows`: [Arquivo!]
- `count`: Int

### ArquivoFilterInput (INPUT_OBJECT)

- `original_name`: PrimeFilterItemString
- `type`: PrimeFilterItemString
- `category`: PrimeFilterItemString
- `source`: PrimeFilterItemString
- `pasta_uuid`: PrimeFilterItemString
- `description`: PrimeFilterItemString
- `keywords`: PrimeFilterItemString
- `dono_usuario_id`: PrimeFilterItemInt
- `search`: PrimeFilterItemString
- `mime_type`: PrimeFilterItemString

### ArquivoInput (INPUT_OBJECT)

- `uuid`: String
- `original_name`: String
- `pasta_uuid`: String
- `description`: String
- `keywords`: String
- `size_bytes`: String
- `source`: String
- `metadata`: String
- `ativo`: String
- `privado`: Boolean

### ArquivoListInput (INPUT_OBJECT)

- `filters`: ArquivoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### ArquivoMetadado (OBJECT)

- `aspectRatioWidth`: Float
- `aspectRatioHeight`: Float
- `height`: Float
- `width`: Float
- `orientation`: Float

### AtendiemntoPayload (OBJECT)

- `ctxUserEmpresaId`: Int
- `atendente_usuario_id`: Int
- `usuario_id`: Int
- `departamento_id`: Int
- `tipo`: Int
- `grupo`: String
- `encerrou`: String
- `conexao_id`: String
- `old_atendente_usuario_id`: Int
- `old_departamento_id`: Int
- `old_tipo`: Int
- `atendimento_id`: Int

### Atendimento (OBJECT)

- `id`: Float!
- `protocolo`: String
- `cliente_id`: Float
- `ultima_msg_enviada_nanoid`: String
- `usuario_id`: Float
- `canal`: Float!
- `qtde_resposta_invalida`: Float
- `grupo`: String
- `cliente`: Cliente
- `usuario`: Usuario
- `usuarioAtendente`: Usuario
- `ultimaMensagemEnviada`: AtendimentoMensagem
- `data_hora_criacao`: DateTime!
- `tipo`: Float!
- `lida`: Float
- `nao_lida`: Float
- `atendente_usuario_id`: Float
- `menu_id`: Float
- `ativo`: String!
- `informa_nome`: String!
- `departamento_id`: Float
- `departamento`: Departamento
- `data_hora_finalizacao`: DateTime
- `data_hora_ultima_atividade`: DateTime
- `data_hora_inicio`: DateTime
- `empresa_id`: Float
- `item_id`: Float
- `solicitou_encerramento`: Int
- `aba_id`: Int
- `empresa`: Empresa!
- `conexao_id`: Float
- `nome_contato`: String
- `iniciado_cliente`: String
- `finalizacao_usuario`: String
- `campanha_id`: Int
- `tags`: String
- `atendimentoTags`: [Tag!]
- `data_hora_ultima_recebida`: DateTime
- `agente_ia_id`: Int
- `agenteIA`: AgenteIA
- `conexao`: Conexao
- `item`: Item!
- `mensagens`: [AtendimentoMensagem!]
- `usuarioTimestamp`: [UsuarioAtendimentoTimestamp!]
- `notificacoes`: Int
- `cliente_em_atendimento`: Boolean
- `atendimento_automatico`: String

### AtendimentoDataTable (OBJECT)

- `rows`: [Atendimento!]
- `count`: Int

### AtendimentoFilterInput (INPUT_OBJECT)

- `id`: PrimeFilterItemInt
- `protocolo`: PrimeFilterItemString
- `cliente_nome`: PrimeFilterItemString
- `cliente_id`: PrimeFilterItemInt
- `conexao_id`: PrimeFilterItemInt
- `tags`: PrimeFilterItemIntArray
- `atendente_usuario_id`: PrimeFilterItemInt
- `departamento_id`: PrimeFilterItemInt
- `ativo`: PrimeFilterItemString
- `data_hora_criacao`: PrimeFilterItemStringArray
- `canal`: PrimeFilterItemInt
- `grupo`: PrimeFilterItemString
- `iniciado_cliente`: PrimeFilterItemString
- `validate_date`: PrimeFilterItemString
- `data_hora_finalizacao`: PrimeFilterItemStringArray
- `tipo`: PrimeFilterItemInt

### AtendimentoInput (INPUT_OBJECT)

- `id`: Float
- `protocolo`: String
- `conexao_id`: Float
- `mensagem`: String
- `cliente_id`: Float
- `usuario_id`: Float
- `canal`: Float
- `data_hora_criacao`: DateTime
- `tipo`: Float
- `atendente_usuario_id`: Int
- `ativo`: String
- `departamento_id`: Int
- `data_hora_finalizacao`: DateTime
- `empresa_id`: Float
- `continuar_atendimento`: String
- `transferir_atendimento`: String
- `agente_ia_id`: Int
- `instrucao_ia`: String
- `aba_id`: Int
- `grupo`: String
- `nome_grupo`: String
- `template_id`: String
- `header_parameters`: [WabaTemplateParameterAtendimento!]
- `body_parameters`: [WabaTemplateParameterAtendimento!]
- `replaced_header`: String
- `replaced_body`: String
- `tags`: [Int!]

### AtendimentoLazyFilterInput (INPUT_OBJECT)

- `tipo_visualizacao`: Int!
- `ordem_atividade`: Boolean
- `aba_id`: Int
- `departamentos`: [Int!]
- `nome_contato`: String
- `cliente_nome`: String
- `cliente_telefone`: String
- `tipo`: Int
- `protocolo`: String
- `conexao_id`: Int
- `limit`: Int!
- `offset`: Int!

### AtendimentoLazyResponse (OBJECT)

- `num_atendimentos`: Int!
- `num_nao_lidas`: Int!
- `atendimentos`: [Atendimento!]!

### AtendimentoListInput (INPUT_OBJECT)

- `filters`: AtendimentoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AtendimentoMensagem (OBJECT)

- `nanoid`: String!
- `atendimento_id`: Float!
- `conexao_id`: Float
- `conexao`: Conexao
- `empresa_id`: Float
- `canal`: Float
- `cliente_id`: Float
- `ultima_mensagem_nanoid`: String
- `mencaoCliente`: [Cliente!]
- `cliente`: Cliente
- `grupo`: String
- `timestamp`: Float!
- `atendimento`: Atendimento
- `mensagem`: String
- `metadado`: String
- `vcard`: MessageVCard
- `content_type`: String
- `thumbnail`: String
- `status`: String!
- `marcar_como_lida`: String!
- `automatica`: String!
- `data_hora_criacao`: DateTime!
- `arquivo`: String
- `legenda`: String
- `erro_descricao`: String
- `w_id`: String
- `link_externo`: String
- `qtde_erros`: Float!
- `tipo`: Int!
- `ordem`: Int!
- `interna`: String!
- `atendente_usuario_id`: Float
- `contact_cliente_id`: Float
- `contactCliente`: Int
- `usuario`: Usuario
- `ativo`: String
- `enviada_dispositivo`: String
- `verificada`: String
- `encrypted`: String
- `file_type`: String
- `encaminhada`: String
- `resposta_mensagem_nanoid`: String
- `waba_billable`: String
- `waba_pricing_model`: String
- `waba_category`: String
- `resposta_coleta`: String
- `campanha_id`: Int
- `agente_ia_id`: Int
- `agenteIA`: AgenteIA
- `aguardando_msg`: String
- `arquivo_nome`: String
- `respostaMensagem`: AtendimentoMensagem
- `menuModernoMetadado`: MenuModernoMetadado
- `arquivoMetadados`: ArquivoMetadado
- `signedThumbnail`: String
- `signedFile`: String

### AtendimentoMensagemFilterInput (INPUT_OBJECT)

- `mensagem`: PrimeFilterItemString
- `data_hora_criacao`: PrimeFilterItemStringArray
- `atendente_usuario_id`: PrimeFilterItemInt
- `conexao_id`: PrimeFilterItemInt
- `cliente_id`: PrimeFilterItemInt
- `departamento_id`: PrimeFilterItemInt

### AtendimentoMensagemInput (INPUT_OBJECT)

- `nanoid`: String
- `atendimento_id`: Float
- `mensagem`: String
- `status`: String
- `data_hora_criacao`: DateTime
- `arquivo`: String
- `legenda`: String
- `interna`: String
- `atendente_usuario_id`: Float
- `ativo`: String
- `contact_cliente_id`: Float
- `resposta_mensagem_nanoid`: String
- `template_id`: String
- `header_parameters`: [WabaTemplateParameterMensagem!]
- `body_parameters`: [WabaTemplateParameterMensagem!]
- `replaced_body`: String
- `replaced_header`: String
- `tipo`: Int
- `content_type`: String
- `arquivo_nome`: String
- `arquivo_uuid`: String
- `interactive`: InteractiveMensagemInput

### AtendimentoMensagemListInput (INPUT_OBJECT)

- `filters`: AtendimentoMensagemFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AtendimentoMenuHistorico (OBJECT)

- `nanoid`: String!
- `resposta`: String
- `data_hora`: String
- `atendimento_id`: Float
- `cliente_id`: Float
- `menu_id`: Float
- `item_id`: Float
- `item`: Item
- `menu`: Menu!
- `cliente`: Cliente!
- `atendimento`: Atendimento!

### AtendimentoMenuHistoricoDataTable (OBJECT)

- `rows`: [AtendimentoMenuHistorico!]
- `count`: Int

### AtendimentoMenuHistoricoFilterInput (INPUT_OBJECT)

- `menu_id`: PrimeFilterItemInt
- `data_hora`: PrimeFilterItemStringArray

### AtendimentoMenuHistoricoListInput (INPUT_OBJECT)

- `filters`: AtendimentoMenuHistoricoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AtendimentoTransferencia (OBJECT)

- `id`: Float!
- `atendimento_id`: Float!
- `atendimento`: Atendimento!
- `data_hora_criacao`: DateTime!
- `atendente_usuario_id`: Float
- `criacao_usuario_id`: Float
- `atendente`: Usuario
- `departamento_id`: Float
- `departamento`: Departamento
- `criacaoUsuario`: Usuario

### AtendimentoTransferenciaDataTable (OBJECT)

- `rows`: [AtendimentoTransferencia!]
- `count`: Int

### AtendimentoTransferenciaFilterInput (INPUT_OBJECT)

- `id`: Float!

### AtendimentoTransferenciaInput (INPUT_OBJECT)

- `id`: Float!
- `atendimento_id`: Float!
- `data_hora_criacao`: DateTime!
- `atendente_usuario_id`: Float
- `departamento_id`: Float

### AtendimentoTransferenciaListInput (INPUT_OBJECT)

- `filters`: AtendimentoTransferenciaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AtendimentosAbertosUsuarioResult (OBJECT)

- `total`: Int!
- `menus`: [Menu!]!

### Aviso (OBJECT)

- `id`: Float!
- `titulo`: String!
- `descricao`: String!
- `data_inicio`: String
- `data_fim`: String
- `ativo`: String
- `data_hora_criacao`: DateTime
- `criacao_usuario`: String
- `empresas`: String
- `lido`: String

### AvisoDataTable (OBJECT)

- `rows`: [Aviso!]
- `count`: Int

### AvisoFilterInput (INPUT_OBJECT)

- `titulo`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString
- `empresas`: PrimeFilterItemInt

### AvisoInput (INPUT_OBJECT)

- `id`: Int
- `titulo`: String
- `descricao`: String
- `data_inicio`: String
- `data_fim`: String
- `ativo`: String
- `empresas`: [Int!]

### AvisoListInput (INPUT_OBJECT)

- `filters`: AvisoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### AvisoUsuario (OBJECT)

- `aviso_id`: Float!
- `usuario_id`: Float!
- `leitor`: Usuario

### BaseConhecimento (OBJECT)

- `id`: Int!
- `nome`: String!
- `conteudo`: String!
- `fonte`: String!
- `empresa_id`: Int
- `ativo`: String
- `data_criacao`: String
- `agentes_ia`: [AgenteIA!]

### BaseConhecimentoDataTable (OBJECT)

- `rows`: [BaseConhecimento!]
- `count`: Int

### BaseConhecimentoFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### BaseConhecimentoInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `conteudo`: String
- `fonte`: String
- `ativo`: String

### BaseConhecimentoListInput (INPUT_OBJECT)

- `filters`: BaseConhecimentoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### BuscarMensagemInput (INPUT_OBJECT)

- `timestamp`: Float
- `atendimentoId`: Float
- `tipo`: String

### CalendarioEvento (OBJECT)

- `id`: Int!
- `descricao`: String!
- `data_inicial`: String!
- `data_final`: String
- `acao_novos_atend`: String!
- `msg_atendimento_em_andamento`: String
- `msg_encerramento`: String
- `ativo`: String
- `empresa_id`: Int!
- `horarios`: [CalendarioEventoHorario!]
- `conexoes`: [Conexao!]

### CalendarioEventoDataTable (OBJECT)

- `rows`: [CalendarioEvento!]
- `count`: Int

### CalendarioEventoFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString

### CalendarioEventoHorario (OBJECT)

- `id`: Int!
- `calendario_evento_id`: Int!
- `horario_inicial`: String!
- `horario_final`: String!

### CalendarioEventoHorarioInput (INPUT_OBJECT)

- `horario_inicial`: String
- `horario_final`: String

### CalendarioEventoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `data_inicial`: String
- `data_final`: String
- `acao_novos_atend`: String
- `msg_atendimento_em_andamento`: String
- `msg_encerramento`: String
- `ativo`: String
- `horarios`: [CalendarioEventoHorarioInput!]
- `conexoes`: [Int!]

### CalendarioEventoListInput (INPUT_OBJECT)

- `filters`: CalendarioEventoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Campanha (OBJECT)

- `id`: Int!
- `descricao`: String!
- `status`: Int!
- `data_hora_inicio`: DateTime
- `data_hora_fim`: DateTime
- `ativo`: String!
- `menu_id`: Int
- `agente_ia_id`: Int
- `conexao_id`: Int!
- `waba_template_id`: String!
- `metadata`: String
- `filtro_publico_alvo`: String
- `data_hora_criacao`: DateTime
- `criacao_usuario`: String
- `empresa_id`: Int!
- `body_params`: String
- `header_params`: String
- `erro_descricao`: String
- `num_disparo`: Int
- `num_recebido`: Int

### CampanhaCliente (OBJECT)

- `nanoid`: String!
- `campanha_id`: Int!
- `cliente_id`: Int!
- `status`: Int!
- `erro_descricao`: String
- `data_hora_criacao`: DateTime
- `empresa_id`: Int!
- `cliente`: Cliente

### CampanhaClienteDataTable (OBJECT)

- `rows`: [CampanhaCliente!]
- `count`: Int

### CampanhaClienteFilterInput (INPUT_OBJECT)

- `status`: PrimeFilterItemInt
- `campanha_id`: PrimeFilterItemInt

### CampanhaClienteListInput (INPUT_OBJECT)

- `filters`: CampanhaClienteFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### CampanhaDataTable (OBJECT)

- `rows`: [Campanha!]
- `count`: Int

### CampanhaFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `filtro_publico_alvo`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### CampanhaInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `status`: Int
- `data_hora_inicio`: String
- `data_hora_fim`: String
- `ativo`: String
- `menu_id`: Int
- `agente_ia_id`: Int
- `conexao_id`: Int
- `filtro_publico_alvo`: String
- `waba_template_id`: String
- `header_parameters`: [WabaTemplateParameterCampanha!]
- `body_parameters`: [WabaTemplateParameterCampanha!]
- `replaced_header`: String
- `replaced_body`: String

### CampanhaListInput (INPUT_OBJECT)

- `filters`: CampanhaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### CanalExterno (OBJECT)

- `id`: Int!
- `tipo`: Int!
- `descricao`: String!
- `canal`: String!
- `empresa_id`: Int!

### CanalExternoDataTable (OBJECT)

- `rows`: [CanalExterno!]
- `count`: Int

### CanalExternoFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString

### CanalExternoInput (INPUT_OBJECT)

- `id`: Float
- `tipo`: Int
- `descricao`: String
- `canal`: String
- `ativo`: String

### CanalExternoListInput (INPUT_OBJECT)

- `filters`: CanalExternoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Cargo (OBJECT)

- `id`: Float!
- `descricao`: String!
- `ativo`: String
- `funcionario`: [Funcionario!]

### CategoriaProduto (OBJECT)

- `id`: Int!
- `empresa_id`: Int!
- `descricao`: String!
- `ativo`: String!
- `produtos`: [Produto!]
- `clientes`: [Cliente!]

### CategoriaProdutoDataTable (OBJECT)

- `rows`: [CategoriaProduto!]
- `count`: Int

### CategoriaProdutoFilterInput (INPUT_OBJECT)

- `id`: PrimeFilterItemInt

### CategoriaProdutoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `ativo`: String
- `clientes`: [Int!]

### CategoriaProdutoListInput (INPUT_OBJECT)

- `filters`: CategoriaProdutoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Cidade (OBJECT)

- `id`: Int!
- `ibge`: String!
- `descricao`: String!
- `uf`: String!

### CidadeFilterInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String

### Cliente (OBJECT)

- `id`: Float
- `nome`: String
- `telefone`: String
- `email`: String
- `remoteid`: String
- `observacoes`: String
- `bairro`: String
- `endereco`: String
- `complemento`: String
- `cep`: String
- `numero`: String
- `imagem_perfil`: String
- `imagem_perfil_completa`: String
- `visto_ultimo`: Float
- `state`: String
- `ativo`: String!
- `numero_verificado`: String
- `grupo`: String
- `faixa_salarial_inicial`: Float
- `faixa_salarial_final`: Float
- `tag_id`: Int
- `empresa_id`: Float
- `cidade_id`: Float
- `cidade`: Cidade
- `empresa`: Empresa!
- `data_cadastro`: String!
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `data_nascimento`: String
- `aba_id`: Int
- `msg_apos_encerramento`: String!
- `atendente_usuario_id`: Int
- `alteracaoUsuario`: Usuario!
- `criacaoUsuario`: Usuario
- `tipo_atendimento`: Int
- `desconsiderar_turno_cliente`: String
- `field_1`: String
- `field_2`: String
- `field_3`: String
- `field_4`: String
- `field_5`: String
- `webhook_url`: String
- `hook_id`: Int
- `tag`: Tag
- `tags`: [Tag!]
- `tags_secundarias`: String
- `lid`: String
- `wa_username`: String
- `ignora_inatividade`: String

### ClienteAnotacao (OBJECT)

- `id`: Float
- `descricao`: String!
- `mensagem`: String!
- `ativo`: String
- `criacao_usuario`: String
- `data_hora_criacao`: DateTime
- `cliente_id`: Int!
- `cliente`: Cliente!

### ClienteAnotacaoDataTable (OBJECT)

- `rows`: [ClienteAnotacao!]
- `count`: Int

### ClienteAnotacaoFilterInput (INPUT_OBJECT)

- `id`: Float
- `descricao`: PrimeFilterItemString
- `mensagem`: PrimeFilterItemString
- `cliente_id`: PrimeFilterItemInt

### ClienteAnotacaoInput (INPUT_OBJECT)

- `id`: Float
- `descricao`: String!
- `mensagem`: String!
- `ativo`: String
- `cliente_id`: Int!

### ClienteAnotacaoListInput (INPUT_OBJECT)

- `filters`: ClienteAnotacaoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### ClienteConexaoUltimaMensagem (OBJECT)

- `cliente_id`: Int!
- `conexao_id`: Int!
- `data_hora_ultima_recebida`: DateTime!

### ClienteDataTable (OBJECT)

- `rows`: [Cliente!]
- `count`: Int

### ClienteFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `telefone`: PrimeFilterItemString
- `email`: PrimeFilterItemString
- `id`: PrimeFilterItemInt
- `tag_id`: PrimeFilterItemInt
- `grupo`: PrimeFilterItemString
- `bairro`: PrimeFilterItemString
- `field_1`: PrimeFilterItemString
- `field_2`: PrimeFilterItemString
- `field_3`: PrimeFilterItemString
- `field_4`: PrimeFilterItemString
- `field_5`: PrimeFilterItemString
- `aniversario_mes`: PrimeFilterItemInt
- `aniversario_dia`: PrimeFilterItemInt

### ClienteImportacao (INPUT_OBJECT)

- `nome`: String
- `telefone`: String!
- `email`: String

### ClienteImportacaoInput (INPUT_OBJECT)

- `tag_id`: Int
- `tag_descricao`: String
- `clientes`: [ClienteImportacao!]!

### ClienteInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `telefone`: String
- `email`: String
- `observacoes`: String
- `ativo`: String
- `empresa_id`: Int
- `endereco`: String
- `numero`: String
- `bairro`: String
- `complemento`: String
- `cep`: String
- `cidade_id`: Int
- `faixa_salarial_inicial`: Float
- `faixa_salarial_final`: Float
- `tag_id`: Int
- `data_nascimento`: String
- `aba_id`: Int
- `tipo_atendimento`: Int
- `msg_apos_encerramento`: String
- `imagem_perfil`: String
- `imagem_perfil_completa`: String
- `desconsiderar_turno_cliente`: String
- `atendente_usuario_id`: Int
- `field_1`: String
- `field_2`: String
- `field_3`: String
- `field_4`: String
- `field_5`: String
- `webhook_url`: String
- `hook_id`: Int
- `tags`: [Int!]
- `ignora_inatividade`: String

### ClienteListInput (INPUT_OBJECT)

- `filters`: ClienteFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### ClienteMencao (OBJECT)

- `nanoid`: String!
- `cliente_id`: Int!
- `cliente_mencao_id`: Int!
- `cliente`: Cliente
- `clienteMencionado`: Cliente
- `canais`: [CanalExterno!]

### ClienteMencaoInput (INPUT_OBJECT)

- `nanoid`: String
- `cliente_id`: Float
- `cliente_mencao_id`: Float
- `canais`: [Int!]

### ClienteTagLoteInput (INPUT_OBJECT)

- `cliente_ids`: [Int!]!
- `tag_ids`: [Int!]!
- `acao`: String!

### ConStateUpdate (OBJECT)

- `state`: String
- `msg`: String
- `conexaoId`: Float
- `empresaId`: Float
- `battery`: InfoBatteryState
- `queue`: QueueUpdate

### Conexao (OBJECT)

- `id`: Float!
- `nome`: String
- `identificador`: String
- `tipo_atendimento`: String!
- `session`: String
- `data_hora_criacao`: DateTime
- `data_hora_desativacao`: DateTime
- `state`: String
- `tipo`: String
- `empresa_id`: Float
- `empresa`: Empresa
- `ativo`: String!
- `padrao`: String!
- `start_time`: Float
- `engine`: String!
- `waba_account_id`: String
- `waba_account_description`: String
- `waba_phone_id`: String
- `waba_app_id`: String
- `agente_ia_id`: Int
- `agenteIA`: AgenteIA

### ConexaoDataTable (OBJECT)

- `rows`: [Conexao!]
- `count`: Int

### ConexaoFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `identificador`: PrimeFilterItemString
- `empresa_id`: PrimeFilterItemInt
- `state`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString
- `engine`: PrimeFilterItemString

### ConexaoInput (INPUT_OBJECT)

- `id`: Int
- `tipo`: String
- `nome`: String
- `tipo_atendimento`: String
- `padrao`: String
- `ativo`: String
- `session`: String
- `engine`: String
- `waba_account_id`: String
- `waba_account_description`: String
- `waba_phone_id`: String
- `waba_app_id`: String
- `agente_ia_id`: Int

### ConexaoListInput (INPUT_OBJECT)

- `filters`: ConexaoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### ConexaoOculta (OBJECT)

- `uuid`: String!
- `conexao_id`: Int!
- `usuario_id`: Int!
- `contexto`: String!
- `motivo`: String!
- `data_hora_criacao`: DateTime
- `conexao`: Conexao
- `usuario`: Usuario

### ConexaoOcultaInput (INPUT_OBJECT)

- `uuid`: String
- `conexao_id`: Int
- `contexto`: String
- `motivo`: String
- `ativo`: String

### Contador (OBJECT)

- `id`: Int!
- `nome`: String
- `qtde`: Int
- `empresa_id`: Int

### DecryptJob (OBJECT)

- `id`: String!
- `state`: String
- `started_at`: String
- `completed_at`: String
- `error_message`: String
- `empresa_id`: Float

### Departamento (OBJECT)

- `id`: Float!
- `descricao`: String!
- `ativo`: String
- `empresa_id`: Float
- `empresa`: Empresa!
- `data_cadastro`: DateTime!
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `posicao_fila_transferencia`: Int
- `notifica_cliente_id`: Float
- `encerra_atendimento`: String
- `grupo`: String
- `tolerancia_atend_inativo`: Int
- `enviar_fila_atendimento`: String
- `menu_coleta_id`: Int
- `retencao_msg`: Int
- `notificaCliente`: Int
- `alteracaoUsuario`: Usuario
- `criacaoUsuario`: Int
- `usuarios`: [Usuario!]
- `canais`: [CanalExterno!]
- `turno_id`: Float
- `turno`: Turno

### DepartamentoDataTable (OBJECT)

- `rows`: [Departamento!]
- `count`: Int

### DepartamentoFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### DepartamentoInput (INPUT_OBJECT)

- `id`: Float
- `descricao`: String
- `ativo`: String
- `encerra_atendimento`: String
- `enviar_fila_atendimento`: String
- `notifica_cliente_id`: Float
- `canais`: [Int!]
- `grupo`: String
- `tolerancia_atend_inativo`: Int
- `menu_coleta_id`: Int
- `retencao_msg`: Int
- `turno_id`: Float

### DepartamentoListInput (INPUT_OBJECT)

- `filters`: DepartamentoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Empresa (OBJECT)

- `id`: Float!
- `razao_social`: String
- `cpf_cnpj`: String
- `nome_fantasia`: String
- `logo`: String
- `tema`: String
- `session`: String
- `ativo`: String!
- `sincronizar_contatos`: String
- `multidevice`: String!
- `habilitar_msg_grupo`: String
- `battery_plugged`: String
- `battery_powersave`: String
- `fuso_horario`: String
- `whats_ativo`: String!
- `tipo_atendimento`: String!
- `w_online`: String!
- `tempo_atendimento`: String
- `api_verifica_numero`: String
- `apenas_grupos`: String
- `max_usuario`: Float!
- `start_time`: Float
- `data_cadastro`: String!
- `enviar_prococolo_cliente`: String!
- `enviar_msg_encerramento_atend`: String!
- `exibir_tempo_atendimento`: String
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `cluster`: String
- `enviar_msg_nome_atend`: String
- `enviar_fila_atendimento`: String
- `api_key`: String
- `webhook_url`: String
- `repetir_msg_boas_vindas`: String
- `tolerancia_atend_inativo`: Float!
- `battery_percentage`: Float
- `horario_funcionamento`: Float!
- `canal_padrao`: Float!
- `telegram_token`: String
- `telegram_chatid`: String
- `cliente_faixa_salarial`: String
- `retencao_msg`: Int
- `campos_cliente`: String
- `menu_coleta_id`: Int
- `min_finaliza_pesquisa`: Int
- `atendente_indisponivel`: String
- `logo_dark`: String
- `direcionar_atendente_principal`: String
- `transacoes`: [Transacao!]
- `alteracaoUsuario`: Usuario!
- `criacaoUsuario`: Usuario
- `programacao_atendimento`: String
- `programacao_menu_coleta`: String
- `finalizacao_atendimento_inativo`: String
- `encerrar_apenas_atend_automatico`: String
- `beta_tester`: String
- `conexao_usuario`: String
- `conexoes`: [Conexao!]
- `cliente_field_metadata`: String
- `enviar_msg_inicio`: String
- `waba_verify_token`: String
- `enviar_msg_indisponivel`: String
- `saldo_utility`: Int
- `saldo_authentication`: Int
- `saldo_marketing`: Int
- `max_conexao`: Int
- `hook_id`: Int
- `departamento_obrigatorio`: String
- `status_bloqueio`: String
- `limite_custo_ia_mensal`: Float
- `limite_custo_ia_por_atendimento`: Float
- `habilitar_ia`: String
- `enviar_msg_departamento`: String

### EmpresaDataTable (OBJECT)

- `rows`: [Empresa!]
- `count`: Int

### EmpresaFilterInput (INPUT_OBJECT)

- `id`: PrimeFilterItemInt
- `razao_social`: PrimeFilterItemString
- `nome_fantasia`: PrimeFilterItemString
- `cpf_cnpj`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### EmpresaInput (INPUT_OBJECT)

- `id`: Float
- `razao_social`: String
- `cpf_cnpj`: String
- `nome_fantasia`: String
- `min_finaliza_pesquisa`: Float
- `logo`: String
- `ativo`: String
- `sincronizar_contatos`: String
- `enviar_fila_atendimento`: String
- `cluster`: String
- `fuso_horario`: String
- `whats_ativo`: String
- `tipo_atendimento`: String
- `tempo_atendimento`: Float
- `max_usuario`: Float
- `exibir_tempo_atendimento`: String
- `w_online`: String
- `enviar_prococolo_cliente`: String
- `enviar_msg_encerramento_atend`: String
- `enviar_msg_nome_atend`: String
- `repetir_msg_boas_vindas`: String
- `api_key`: String
- `webhook_url`: String
- `habilitar_msg_grupo`: String
- `tolerancia_atend_inativo`: Int
- `horario_funcionamento`: Int
- `transacoes`: [Int!]
- `canal_padrao`: Int
- `telegram_token`: String
- `telegram_chatid`: String
- `cliente_faixa_salarial`: String
- `retencao_msg`: Int
- `campos_cliente`: String
- `menu_coleta_id`: Int
- `atendente_indisponivel`: String
- `programacao_atendimento`: String
- `programacao_menu_coleta`: String
- `finalizacao_atendimento_inativo`: String
- `encerrar_apenas_atend_automatico`: String
- `beta_tester`: String
- `conexao_usuario`: String
- `enviar_msg_indisponivel`: String
- `logo_dark`: String
- `direcionar_atendente_principal`: String
- `cliente_field_metadata`: String
- `enviar_msg_inicio`: String
- `waba_verify_token`: String
- `saldo_utility`: Int
- `saldo_authentication`: Int
- `saldo_marketing`: Int
- `max_conexao`: Int
- `hook_id`: Int
- `departamento_obrigatorio`: String
- `status_bloqueio`: String
- `habilitar_ia`: String
- `limite_custo_ia_mensal`: Float
- `limite_custo_ia_por_atendimento`: Float
- `enviar_msg_departamento`: String

### EmpresaListInput (INPUT_OBJECT)

- `filters`: EmpresaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### EncaminharMensagemInput (INPUT_OBJECT)

- `mensagens`: [String!]!
- `atendimentos`: [Int!]!

### Fatura (OBJECT)

- `uuid`: String!
- `empresa_id`: Int!
- `empresa`: Empresa
- `cod_exp`: String
- `mes`: Int!
- `ano`: Int!
- `valor`: Float!
- `descricao`: String
- `url_pagamento`: String
- `negociado`: String!
- `obs_negociado`: String
- `data_vencimento`: String!
- `data_pagamento`: String
- `data_hora_criacao`: DateTime
- `data_hora_atualizacao`: DateTime
- `arquivos`: [FaturaArquivo!]

### FaturaArquivo (OBJECT)

- `uuid`: String!
- `empresa_id`: Int!
- `empresa`: Empresa
- `cod_exp`: String
- `fatura_uuid`: String!
- `fatura`: Fatura
- `descricao`: String
- `tipo`: String
- `arquivo`: String!
- `nome`: String
- `mime_type`: String
- `tamanho`: Float
- `ext`: String
- `data_hora_criacao`: DateTime

### FaturaArquivoInput (INPUT_OBJECT)

- `uuid`: String
- `fatura_uuid`: String
- `nome`: String
- `descricao`: String
- `tipo`: String
- `tamanho`: String
- `ativo`: String

### FaturaDataTable (OBJECT)

- `rows`: [Fatura!]
- `count`: Int

### FaturaFilterInput (INPUT_OBJECT)

- `empresa_id`: PrimeFilterItemInt
- `mes`: PrimeFilterItemInt
- `ano`: PrimeFilterItemInt

### FaturaInput (INPUT_OBJECT)

- `uuid`: String
- `empresa_id`: Int
- `cod_exp`: String
- `mes`: Int
- `ano`: Int
- `valor`: Float
- `descricao`: String
- `url_pagamento`: String
- `negociado`: String
- `obs_negociado`: String
- `data_vencimento`: String
- `data_pagamento`: String
- `ativo`: String

### FaturaListInput (INPUT_OBJECT)

- `filters`: FaturaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### FormPadrao (OBJECT)

- `id`: Int!
- `descricao`: String!
- `form`: String
- `template`: String
- `ativo`: String!
- `empresa_id`: Int!

### FormPadraoAtendimento (OBJECT)

- `nanoid`: String!
- `descricao`: String!
- `form`: String
- `template`: String
- `criacao_usuario_id`: Int!
- `atendimento_id`: Int
- `cliente_id`: Int
- `form_padrao_id`: Int!
- `data_hora_criacao`: String!
- `empresa_id`: Int!
- `atendimento`: Atendimento
- `cliente`: Cliente
- `criacaoUsuario`: Usuario

### FormPadraoAtendimentoDataTable (OBJECT)

- `rows`: [FormPadraoAtendimento!]
- `count`: Int

### FormPadraoAtendimentoFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `atendimento_id`: PrimeFilterItemInt
- `cliente_id`: PrimeFilterItemInt

### FormPadraoAtendimentoInput (INPUT_OBJECT)

- `nanoid`: String
- `descricao`: String
- `form`: String
- `template`: String
- `atendimento_id`: Int
- `cliente_id`: Int
- `form_padrao_id`: Int
- `ativo`: String

### FormPadraoAtendimentoListInput (INPUT_OBJECT)

- `filters`: FormPadraoAtendimentoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### FormPadraoDataTable (OBJECT)

- `rows`: [FormPadrao!]
- `count`: Int

### FormPadraoFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString

### FormPadraoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `form`: String
- `template`: String
- `ativo`: String

### FormPadraoListInput (INPUT_OBJECT)

- `filters`: FormPadraoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Funcionario (OBJECT)

- `id`: Int!
- `empresa_id`: Int!
- `empresa`: Empresa
- `usuario_id`: Int
- `usuario`: Usuario
- `nome`: String!
- `telefone`: String
- `email`: String
- `ativo`: String
- `data_hora_criacao`: DateTime
- `criacao_usuario`: String
- `cargos`: [Cargo!]

### FuncionarioDataTable (OBJECT)

- `rows`: [Funcionario!]
- `count`: Int

### FuncionarioFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `email`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString
- `empresa_id`: PrimeFilterItemInt

### FuncionarioInput (INPUT_OBJECT)

- `id`: Int
- `empresa_id`: Int
- `nome`: String
- `telefone`: String
- `email`: String
- `ativo`: String
- `usuario_id`: Int
- `cargo_ids`: [Int!]

### FuncionarioListInput (INPUT_OBJECT)

- `filters`: FuncionarioFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### GeralLog (OBJECT)

- `nanoid`: String!
- `data_hora_criacao`: DateTime!
- `empresa_id`: Int!
- `usuario_id`: Int
- `descricao`: String!
- `valores_antigos`: String!
- `valores_novos`: String!
- `tipo`: Int!
- `usuario`: Usuario

### GeralLogDataTable (OBJECT)

- `rows`: [GeralLog!]
- `count`: Int

### GeralLogFilterInput (INPUT_OBJECT)

- `tipo`: PrimeFilterItemInt
- `descricao`: PrimeFilterItemString
- `data_hora_criacao`: PrimeFilterItemStringArray

### GeralLogListInput (INPUT_OBJECT)

- `filters`: GeralLogFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### GrupoSistema (OBJECT)

- `id`: Int!
- `nome`: String!
- `descricao`: String!
- `permissoes`: [Permissao!]
- `empresa_id`: Float
- `empresa`: Empresa!

### GrupoSistemaDataTable (OBJECT)

- `rows`: [GrupoSistema!]
- `count`: Int

### GrupoSistemaFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString

### GrupoSistemaInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `descricao`: String
- `permissoes`: [Int!]
- `ativo`: String

### GrupoSistemaListInput (INPUT_OBJECT)

- `filters`: GrupoSistemaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Hook (OBJECT)

- `id`: Int!
- `descricao`: String
- `code`: String
- `tipo`: String
- `ativo`: String
- `empresa_id`: Int
- `criacao_usuario`: String
- `msg_cliente`: String
- `msg_usuario`: String
- `headers`: String
- `acao`: Int

### HookDataTable (OBJECT)

- `rows`: [Hook!]
- `count`: Int

### HookFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString

### HookInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `code`: String
- `tipo`: String
- `ativo`: String
- `msg_cliente`: String
- `msg_usuario`: String
- `headers`: String
- `acao`: Int

### HookListInput (INPUT_OBJECT)

- `filters`: HookFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### HookTask (OBJECT)

- `nanoid`: String!
- `target`: String
- `body`: String
- `queue`: String
- `status`: Int
- `empresa_id`: Int!
- `log`: String
- `http_status_code`: Int
- `data_hora_criacao`: DateTime
- `data_hora_finalizacao`: DateTime
- `hook_id`: Int!
- `hook`: Hook

### HookTaskDataTable (OBJECT)

- `rows`: [HookTask!]
- `count`: Int

### HookTaskFilterInput (INPUT_OBJECT)

- `hook_id`: PrimeFilterItemInt
- `queue`: PrimeFilterItemString
- `status`: PrimeFilterItemInt

### HookTaskInput (INPUT_OBJECT)

- `nanoid`: String
- `status`: Int

### HookTaskListInput (INPUT_OBJECT)

- `filters`: HookTaskFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### HookUrl (OBJECT)

- `id`: Int!
- `hook_id`: Int
- `url`: String
- `empresa_id`: Int
- `data_hora_criacao`: DateTime
- `criacao_usuario`: String
- `hook`: Hook

### HookUrlDataTable (OBJECT)

- `rows`: [HookUrl!]
- `count`: Int

### HookUrlFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString

### HookUrlInput (INPUT_OBJECT)

- `id`: Int
- `hook_id`: Int
- `url`: String
- `ativo`: String

### HookUrlListInput (INPUT_OBJECT)

- `filters`: HookUrlFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### HorarioFuncionamento (OBJECT)

- `id`: Float!
- `horario_inicio`: String!
- `horario_fim`: String!
- `empresa_id`: Float!
- `semana`: Float!

### HorarioFuncionamentoInput (INPUT_OBJECT)

- `id`: Int
- `horario_inicio`: String
- `horario_fim`: String
- `semana`: Int
- `empresa_id`: Int
- `ativo`: String

### IAAtendimentoResumo (OBJECT)

- `atendimento_id`: Int!
- `execucoes`: Int!
- `tokens_input`: Int!
- `tokens_output`: Int!
- `tokens_total`: Int!
- `custo_total`: Float
- `duration_ms_total`: Float
- `primeira_data`: String
- `ultima_data`: String
- `agentes`: String — Nomes dos agentes que atenderam (separados por virgula)

### IABudget (OBJECT)

- `limite_usd`: Float
- `usado_usd`: Float!
- `restante_usd`: Float

### IACustoMedioAgente (OBJECT)

- `agente_ia_id`: Int!
- `nome`: String
- `custo_medio`: Float!
- `atendimentos`: Int!

### IADashboard (OBJECT)

- `budget`: IABudget!
- `mensal`: IAUsoMensal!
- `diario`: [IAUsoDiario!]!
- `anual`: [IAUsoAnualItem!]!
- `top_agentes`: [IATopAgente!]!
- `custo_medio_atendimento_agente`: [IACustoMedioAgente!]!
- `ultimos_atendimentos`: [IAUltimoAtendimento!]!

### IAExecucaoDetalhe (OBJECT)

- `id`: String!
- `agente_ia_id`: Int!
- `atendimento_id`: Int!
- `mensagem_nanoids`: String
- `tokens_input`: Int!
- `tokens_output`: Int!
- `tokens_total`: Int!
- `custo_estimado`: Float
- `data_hora`: String!
- `trace`: String — JSON string do trace completo

### IAExecucaoFiltro (INPUT_OBJECT)

- `agente_ia_id`: Int
- `atendimento_id`: Int
- `nanoid`: String
- `ordem`: String — 'asc' (cronologico) ou 'desc' (recente primeiro, default)
- `limit`: Int
- `offset`: Int

### IAExecucaoItem (OBJECT)

- `id`: String!
- `agente_ia_id`: Int!
- `agente_nome`: String
- `atendimento_id`: Int!
- `mensagem_nanoids`: String
- `tokens_input`: Int!
- `tokens_output`: Int!
- `tokens_total`: Int!
- `custo_estimado`: Float
- `data_hora`: String!
- `duration_ms`: Int
- `input_type`: String

### IAExecucaoLista (OBJECT)

- `rows`: [IAExecucaoItem!]!
- `has_more`: Boolean!

### IATopAgente (OBJECT)

- `agente_ia_id`: Int!
- `nome`: String!
- `custo_total`: Float!
- `execucoes`: Int!

### IAUltimoAtendimento (OBJECT)

- `atendimento_id`: Int!
- `agente_ia_id`: Int
- `agente_nome`: String
- `custo_total`: Float!
- `execucoes`: Int!
- `ultima_data`: String

### IAUsoAnualItem (OBJECT)

- `mes`: Int!
- `custo_total`: Float!
- `execucoes`: Int!
- `tokens_total`: Int!

### IAUsoDiario (OBJECT)

- `dia`: String!
- `execucoes`: Int!
- `custo_chat`: Float!
- `custo_whisper`: Float!
- `custo_embedding`: Float!
- `custo_total`: Float!
- `duration_ms_total`: Float!
- `tool_calls_total`: Int!
- `tool_errors_total`: Int!
- `tokens_input`: Int!
- `tokens_output`: Int!

### IAUsoMensal (OBJECT)

- `execucoes`: Int!
- `tokens_input`: Int!
- `tokens_output`: Int!
- `tokens_total`: Int!
- `custo_chat`: Float!
- `custo_whisper`: Float!
- `custo_embedding`: Float!
- `custo_total`: Float!
- `duration_ms_total`: Float!
- `tool_calls_total`: Int!
- `tool_errors_total`: Int!

### InfoBatteryState (OBJECT)

- `powersave`: Boolean
- `plugged`: Boolean
- `percentage`: Float

### InteractiveMensagemInput (INPUT_OBJECT)

- `type`: String!
- `header_text`: String
- `body_text`: String!
- `footer_text`: String
- `opcoes`: [InteractiveOpcaoInput!]

### InteractiveOpcaoInput (INPUT_OBJECT)

- `id`: String!
- `title`: String!
- `description`: String

### Item (OBJECT)

- `id`: Float!
- `comando`: String
- `enviar_contato_transf_depto`: String
- `descricao`: String!
- `mensagem`: String
- `nota_escolha_msg`: String
- `webhook_url`: String
- `item_fim_coleta`: String
- `link`: String
- `acao`: Float!
- `menu_id`: Float
- `menu`: Menu!
- `empresa_id`: Float
- `nota_max`: Float
- `nota_min`: Float
- `acao_setar_nome`: String!
- `contato_cliente_id`: Float
- `empresa`: Empresa!
- `data_cadastro`: DateTime!
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `acao_modelo_mensagem_id`: Float
- `acao_menu_id`: Float
- `acao_departamento_id`: Float
- `acao_atendente_id`: Float
- `grupo`: String
- `ordem`: Int
- `hook_id`: Int
- `mudar_para_manual`: String
- `acao_agente_ia_id`: Int
- `acao_agente_ia`: AgenteIA
- `acao_menu`: Menu
- `acao_departamento`: Departamento
- `acao_atendente`: Usuario
- `acao_modelo_mensagem`: ModeloMensagem
- `alteracaoUsuario`: Usuario
- `criacaoUsuario`: Usuario
- `contatoCliente`: Cliente

### ItemDataTable (OBJECT)

- `rows`: [Item!]
- `count`: Int

### ItemFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `menu_id`: PrimeFilterItemInt

### ItemInput (INPUT_OBJECT)

- `id`: Int
- `comando`: String
- `descricao`: String
- `acao_setar_nome`: String
- `nota_escolha_msg`: String
- `item_fim_coleta`: String
- `acao`: Float
- `nota_max`: Float
- `nota_min`: Float
- `menu_id`: Int
- `contato_cliente_id`: Int
- `acao_modelo_mensagem_id`: Int
- `acao_menu_id`: Int
- `acao_departamento_id`: Int
- `acao_atendente_id`: Int
- `ativo`: String
- `mensagem`: String
- `link`: String
- `grupo`: String
- `ordem`: Int
- `webhook_url`: String
- `hook_id`: Int
- `mudar_para_manual`: String
- `acao_agente_ia_id`: Int

### ItemListInput (INPUT_OBJECT)

- `filters`: ItemFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### ListarCategoriaProdutoFilterInput (INPUT_OBJECT)

- `cliente_id`: Int
- `empresa_id`: Int

### LocalFile (OBJECT)

- `path`: String!
- `atendimentoMensagem`: AtendimentoMensagem

### LoginInput (INPUT_OBJECT)

- `usuario`: String!
- `senha`: String!

### McpServer (OBJECT)

- `id`: Int!
- `nome`: String!
- `descricao`: String
- `tipo`: String
- `tipo_conexao`: String
- `url`: String
- `comando`: String
- `args`: String
- `headers`: String
- `status`: String
- `ultimo_teste`: String
- `empresa_id`: Int
- `ativo`: String
- `criado_por`: String
- `alterado_por`: String
- `data_criacao`: String
- `data_atualizacao`: String
- `agentes_ia`: [AgenteIA!]

### McpServerDataTable (OBJECT)

- `rows`: [McpServer!]
- `count`: Int

### McpServerFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `tipo`: PrimeFilterItemString
- `status`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### McpServerInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `descricao`: String
- `tipo_conexao`: String
- `url`: String
- `comando`: String
- `args`: String
- `headers`: String
- `ativo`: String

### McpServerListInput (INPUT_OBJECT)

- `filters`: McpServerFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### McpToolResult (OBJECT)

- `nome`: String!
- `descricao`: String

### MensagemStatusUpdate (OBJECT)

- `state`: String
- `msgIds`: [String!]
- `msgErro`: String
- `atendimentoId`: Int
- `empresaId`: Int

### Menu (OBJECT)

- `id`: Float!
- `descricao`: String!
- `atalho`: String
- `conexao_id`: Float
- `conexao`: Conexao
- `mensagem`: String
- `arquivo`: String
- `principal`: String!
- `solicitar_nome`: String!
- `coleta_informacao`: String!
- `enviar_msg_final_coleta`: String!
- `menu_moderno`: String!
- `confirmar_coleta`: String!
- `ativo`: String!
- `exibir_comando_menu_item`: String
- `qtde_acesso`: Float!
- `empresa_id`: Float
- `empresa`: Empresa!
- `data_cadastro`: DateTime!
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `menu_ia`: String
- `alteracaoUsuario`: Usuario
- `criacaoUsuario`: Usuario
- `items`: [Item!]
- `auto_navegar_para_item_id`: Float
- `resposta_confidencial`: String
- `menu_interativo`: String

### MenuDataTable (OBJECT)

- `rows`: [Menu!]
- `count`: Int

### MenuFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString
- `principal`: PrimeFilterItemString
- `conexao_id`: PrimeFilterItemInt

### MenuInput (INPUT_OBJECT)

- `id`: Float
- `conexao_id`: Float
- `descricao`: String
- `atalho`: String
- `mensagem`: String
- `arquivo`: String
- `principal`: String
- `solicitar_nome`: String
- `coleta_informacao`: String
- `menu_moderno`: String
- `confirmar_coleta`: String
- `enviar_msg_final_coleta`: String
- `ativo`: String
- `auto_navegar_para_item_id`: Float
- `exibir_comando_menu_item`: String
- `resposta_confidencial`: String
- `menu_ia`: String
- `menu_interativo`: String

### MenuItemArquivo (OBJECT)

- `id`: Float!
- `arquivo`: String!
- `descricao`: String
- `content_type`: String
- `menu_id`: Float
- `item_id`: Float
- `arquivo_nome`: String

### MenuItemArquivoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `arquivo`: String
- `ativo`: String
- `content_type`: String
- `menu_id`: Int
- `item_id`: Int
- `arquivo_nome`: String

### MenuItemArquivoListarInput (INPUT_OBJECT)

- `menu_id`: Int
- `item_id`: Int

### MenuListInput (INPUT_OBJECT)

- `filters`: MenuFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### MenuModernoBtn (OBJECT)

- `buttonId`: Int
- `buttonText`: MenuModernoBtnText
- `type`: Int

### MenuModernoBtnText (OBJECT)

- `displayText`: String

### MenuModernoMetadado (OBJECT)

- `text`: String
- `footer`: String
- `buttons`: [MenuModernoBtn!]

### MessageVCard (OBJECT)

- `nome`: String
- `waid`: String
- `telefone`: String
- `cliente`: Cliente

### MetricaConexaoFiltro (INPUT_OBJECT)

- `conexao_id`: Int
- `data_inicial`: String!
- `data_final`: String!
- `granularidade`: String

### MetricaConexaoPonto (OBJECT)

- `periodo`: String!
- `recebidas`: Int!
- `enviadas`: Int!

### ModeloIA (OBJECT)

- `id`: Int!
- `provedor`: String!
- `nome`: String!
- `descricao`: String
- `ativo`: String
- `tipo`: String!
- `custo_input_mtok`: Float
- `custo_output_mtok`: Float
- `janela_contexto`: Int

### ModeloMensagem (OBJECT)

- `id`: Float!
- `descricao`: String
- `atalho`: String
- `mensagem`: String
- `tornar_manual`: String!
- `encerrar_atendimento`: String
- `empresa_id`: Float
- `empresa`: Empresa!
- `data_cadastro`: DateTime!
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `usuario_id`: Int
- `arquivo`: String
- `mimetype`: String
- `arquivo_nome`: String
- `usuario`: Usuario
- `tipo`: String!
- `cabecalho_tipo`: String
- `mensagem_cabecalho`: String
- `mensagem_rodape`: String
- `mensagem_opcoes`: String

### ModeloMensagemDataTable (OBJECT)

- `rows`: [ModeloMensagem!]
- `count`: Int

### ModeloMensagemFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `tipo`: PrimeFilterItemString

### ModeloMensagemInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `atalho`: String
- `mensagem`: String
- `tornar_manual`: String
- `encerrar_atendimento`: String
- `ativo`: String
- `usuario_id`: Int
- `arquivo`: String
- `mimetype`: String
- `arquivo_nome`: String
- `tipo`: String
- `cabecalho_tipo`: String
- `mensagem_cabecalho`: String
- `mensagem_rodape`: String
- `opcoes`: [InteractiveOpcaoInput!]

### ModeloMensagemListInput (INPUT_OBJECT)

- `filters`: ModeloMensagemFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Mutation (OBJECT)

- `testeAgenteMensagem`: Boolean!
- `criarAlterarCategoriaProduto`: CategoriaProduto
- `fecharPedido`: Pedido
- `criarAlterarProduto`: Produto
- `criarAlterarAtendimentoMensagem`: AtendimentoMensagem
- `reenviarMsg`: AtendimentoMensagem
- `lerAtendimentoMensagemPorId`: [AtendimentoMensagem!]
- `encaminharAtendimentoMensagem`: [AtendimentoMensagem!]
- `criarAlterarAtendimento`: Atendimento
- `criarAlterarAtendimentoTransferencia`: AtendimentoTransferencia
- `criarAlterarCanalExterno`: CanalExterno
- `criarAlterarClienteAnotacao`: ClienteAnotacao
- `criarClienteMencao`: Boolean
- `excluirClienteMencao`: Boolean
- `criarAlterarCliente`: Cliente
- `vincularTagsClientesEmLote`: Float!
- `importarClientes`: [Cliente!]
- `criarAlterarDepartamento`: Departamento
- `criarAlterarEmpresa`: Empresa
- `salvarTema`: Boolean
- `criarAlterarFuncionario`: Funcionario
- `criarAlterarFatura`: Fatura
- `criarAlterarFaturaArquivo`: FaturaArquivo
- `uploadFile`: LocalFile
- `enviarArquivosChat`: LocalFile
- `criarAlterarGrupoSistema`: GrupoSistema
- `criarAlterarHorarioFuncionamento`: HorarioFuncionamento
- `criarAlterarItem`: Item
- `criarAlterarItemLote`: [Item!]
- `criarAlterarMenuItemArquivo`: MenuItemArquivo
- `criarAlterarMenu`: Menu
- `duplicarMenu`: Menu
- `criarAlterarModeloMensagem`: ModeloMensagem
- `criarAlterarSistemaMensagem`: SistemaMensagem
- `criarAlterarTag`: Tag
- `criarAlterarTermo`: Termo
- `criarVinculoUsuarioCliente`: UsuarioCliente
- `alterarSenha`: Usuario
- `criaAlteraUsuario`: Usuario
- `criarUsuarioAvaliacao`: Usuario
- `replicarUsuario`: Boolean
- `alteraStatusUsuario`: Usuario
- `alterarUsuarioDisponivel`: Usuario
- `updateUserActivity`: String
- `criarAlterarFormPadrao`: FormPadrao
- `criarAlterarFormPadraoAtendimento`: FormPadraoAtendimento
- `criarAlterarAba`: Aba
- `criarAlterarConexao`: Conexao
- `atualizarStatusConexao`: Boolean
- `limparFila`: Boolean
- `inicializaSessao`: String
- `sessionUpdate`: String
- `criarAlterarTurno`: Turno
- `criarAlterarCalendarioEvento`: CalendarioEvento
- `criarAlterarWabaTemplate`: WabaTemplate
- `importarWabaTemplates`: [WabaTemplate!]
- `sincronizarWabaTemplate`: WabaTemplate
- `uploadWabaFile`: WabaTemplateFileUpload
- `wabaEmbeddedSignup`: Conexao
- `admCriarAlterarEmpresa`: Empresa
- `admSessionUpdate`: String
- `admLimparFila`: Boolean
- `criarAlterarHook`: Hook
- `criarAlterarHookTask`: HookTask
- `criarAlterarHookUrl`: HookUrl
- `criarAlterarCampanha`: Campanha
- `criarAlterarAviso`: Aviso
- `marcarAvisoLido`: Boolean!
- `marcarTodosAvisosLidos`: Boolean!
- `criarAlterarAgenteIA`: AgenteIA
- `criarAlterarBaseConhecimento`: BaseConhecimento
- `criarAlterarVariavelAmbiente`: VariavelAmbiente
- `criarAlterarMcpServer`: McpServer
- `testarMcpServer`: TestarMcpServerResult
- `criarAlterarAlerta`: Alerta
- `alterarSituacaoAlertas`: Float!
- `criarAlterarPasta`: Pasta
- `criarAlterarArquivo`: Arquivo
- `copiarArquivoDeMensagem`: Arquivo
- `criarAlterarPushDevice`: PushDevice
- `criarAlterarPushDeviceUsuario`: PushDeviceUsuario
- `salvarAppTraces`: [TraceEvent!]!
- `criarAlterarConexaoOculta`: Boolean

### OpcaoProduto (OBJECT)

- `id`: Int!
- `nome`: String!
- `obrigatorio`: String!
- `maximo`: Int!
- `minimo`: Int!
- `empresa_id`: Int!
- `produto_id`: Int!
- `itens`: [Produto!]

### OpcaoProdutoInput (INPUT_OBJECT)

- `id`: Int
- `itens`: [Int!]
- `nome`: String
- `obrigatorio`: String
- `maximo`: Int
- `minimo`: Int

### Pasta (OBJECT)

- `uuid`: String!
- `empresa_id`: Int!
- `criacao_usuario_id`: Int
- `dono_usuario_id`: Int
- `nome`: String!
- `cor`: String
- `data_hora_criacao`: DateTime
- `empresa`: Empresa
- `criacaoUsuario`: Usuario
- `donoUsuario`: Usuario
- `arquivos`: [Arquivo!]

### PastaDataTable (OBJECT)

- `rows`: [Pasta!]
- `count`: Int

### PastaFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString

### PastaInput (INPUT_OBJECT)

- `uuid`: String
- `nome`: String
- `ativo`: String
- `cor`: String
- `privado`: Boolean

### PastaListInput (INPUT_OBJECT)

- `filters`: PastaFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Pedido (OBJECT)

- `id`: Int!
- `atendimento_id`: Int!
- `cliente_id`: Int!
- `data_hora_criacao`: String!
- `status`: Int!
- `obs`: String
- `valor_total`: Float!

### PedidoItemInput (INPUT_OBJECT)

- `id`: Int
- `qtde`: Int
- `descricao`: String
- `nome`: String
- `preco`: Float

### PedidoProdutoInput (INPUT_OBJECT)

- `id`: Int
- `qtde`: Int
- `valor_total`: Float
- `valor_unit`: Float
- `descricao`: String
- `nome`: String
- `obs`: String
- `itens`: [PedidoItemInput!]

### Permissao (OBJECT)

- `id`: Int!
- `descricao`: String!
- `categoria`: String!

### PrimeFilterItemInt (INPUT_OBJECT)

- `value`: Int
- `matchMode`: String

### PrimeFilterItemIntArray (INPUT_OBJECT)

- `value`: [Int!]
- `matchMode`: String

### PrimeFilterItemString (INPUT_OBJECT)

- `value`: String
- `matchMode`: String

### PrimeFilterItemStringArray (INPUT_OBJECT)

- `value`: [String!]
- `matchMode`: String

### Produto (OBJECT)

- `id`: Int!
- `descricao`: String!
- `preco`: Float!
- `desconto_percentual`: Int!
- `desconto_reais`: Float!
- `qtde_estoque`: Int!
- `controla_estoque`: String!
- `divisivel`: String!
- `imagem`: String
- `nome`: String
- `cod_exp`: String
- `empresa_id`: Int!
- `categoria_id`: Int!
- `tipo`: Int!
- `opcoes`: [OpcaoProduto!]

### ProdutoDataTable (OBJECT)

- `rows`: [Produto!]
- `count`: Int

### ProdutoFilterInput (INPUT_OBJECT)

- `id`: PrimeFilterItemInt
- `tipo`: PrimeFilterItemInt
- `categoria_id`: PrimeFilterItemInt

### ProdutoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `preco`: Int
- `desconto_percentual`: Int
- `desconto_reais`: Int
- `qtde_estoque`: Int
- `controla_estoque`: String
- `divisivel`: String
- `imagem`: String
- `nome`: String
- `cod_exp`: String
- `empresa_id`: Int
- `tipo`: Int
- `categoria_id`: Int
- `opcoes`: [OpcaoProdutoInput!]
- `itens`: [ProdutoInput!]
- `qtde`: Int
- `valor_total`: Float

### ProdutoListInput (INPUT_OBJECT)

- `filters`: ProdutoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### PushDevice (OBJECT)

- `uuid`: String
- `push_token`: String!
- `usuario_id`: Int!
- `empresa_id`: Int!
- `platform`: String!
- `app_version`: String
- `data_hora_criacao`: DateTime!
- `data_hora_alteracao`: DateTime!
- `push_token_expiracao`: DateTime!

### PushDeviceInput (INPUT_OBJECT)

- `uuid`: String
- `push_token`: String
- `platform`: String
- `app_version`: String
- `opt_out`: String

### PushDeviceUsuario (OBJECT)

- `usuario_id`: Int!
- `push_device_uuid`: String!
- `notificacao_usuario`: String!
- `notificacao_empresa`: String!
- `notificacao_interna`: String!
- `notificacao_grupo`: String!

### PushDeviceUsuarioInput (INPUT_OBJECT)

- `push_device_uuid`: String!
- `notificacao_usuario`: String
- `notificacao_empresa`: String
- `notificacao_interna`: String
- `notificacao_grupo`: String

### QrCodeObject (OBJECT)

- `data`: String

### Query (OBJECT)

- `filtrarCategoriaProduto`: CategoriaProdutoDataTable
- `buscarCategoriaProdutoPorId`: CategoriaProduto
- `listarCategoriaProduto`: [CategoriaProduto!]
- `listarCategoriaProdutoPorCliente`: [CategoriaProduto!]
- `filtrarProduto`: ProdutoDataTable
- `buscarProdutoPorId`: Produto
- `listarProdutos`: [Produto!]
- `listarTransacoes`: [Transacao!]
- `listarTransacoesEmpresa`: [Transacao!]
- `filtrarAtendimentoMensagem`: [AtendimentoMensagem!]
- `carregarMensagens`: [AtendimentoMensagem!]
- `filtrarAtendimentoHistorico`: AtendimentoDataTable
- `buscarAtendimentoHistoricoPorId`: Atendimento
- `buscarAtendimentoPorId`: Atendimento
- `filtrarAtendimentoTransferencia`: AtendimentoTransferenciaDataTable
- `buscarAtendimentoTransferenciaPorId`: AtendimentoTransferencia
- `listarAtendimentoTransferencia`: [AtendimentoTransferencia!]
- `filtrarCanalExterno`: CanalExternoDataTable
- `buscarCanalExternoPorId`: CanalExterno
- `listarCanalExterno`: [CanalExterno!]
- `listarChatIds`: [TelegramChat!]
- `buscarCidadePorIbge`: Cidade
- `buscarCidade`: [Cidade!]
- `filtrarClienteAnotacao`: ClienteAnotacaoDataTable
- `buscarClienteAnotacaoPorId`: ClienteAnotacao
- `buscarClienteMencaoPorId`: [ClienteMencao!]
- `filtrarCliente`: ClienteDataTable
- `buscarClientePorId`: Cliente
- `buscarClientesPorId`: [Cliente!]
- `buscarClientePorNomeOuTel`: [Cliente!]
- `buscarCliente`: [Cliente!]
- `buscarClientePorTelefoneFinal`: [Cliente!]
- `filtrarDepartamento`: DepartamentoDataTable
- `buscarDepartamentoPorId`: Departamento
- `listarDepartamentos`: [Departamento!]
- `listarDepartamentosPorUsuarioId`: [Departamento!]
- `listarDepartamentosHistorico`: [Departamento!]
- `filtrarEmpresa`: EmpresaDataTable
- `buscarEmpresaPorId`: Empresa
- `criarEmpresaVerifyToken`: String
- `limiteAtendentesValido`: Boolean
- `filtrarFuncionario`: FuncionarioDataTable
- `buscarFuncionarioPorId`: Funcionario
- `listarFuncionarios`: [Funcionario!]
- `listarCargos`: [Cargo!]
- `filtrarFaturas`: FaturaDataTable
- `buscarFaturaPorUuid`: Fatura
- `listarFaturasEmpresa`: [Fatura!]
- `listarFaturasVencidas`: [Fatura!]
- `listarFaturaArquivos`: [FaturaArquivo!]
- `filtrarGeralLog`: GeralLogDataTable
- `buscarGeralLogPorId`: GeralLog
- `filtrarGrupoSistema`: GrupoSistemaDataTable
- `buscarGrupoSistemaPorId`: GrupoSistema
- `listarGruposPermissoes`: [GrupoSistema!]
- `listarHorarioFuncionamento`: [HorarioFuncionamento!]
- `filtrarItem`: ItemDataTable
- `buscarItemPorId`: Item
- `listarMenuItemArquivo`: [MenuItemArquivo!]
- `filtrarMenu`: MenuDataTable
- `buscarMenuPorId`: Menu
- `listarMenus`: [Menu!]
- `listarMenusAtivos`: [Menu!]
- `filtrarModeloMensagem`: ModeloMensagemDataTable
- `buscarModeloMensagemPorId`: ModeloMensagem
- `listarModeloMensagem`: [ModeloMensagem!]
- `listarPermissoes`: [Permissao!]!
- `filtrarSistemaMensagem`: SistemaMensagemDataTable
- `buscarSistemaMensagemPorId`: SistemaMensagem
- `filtrarTag`: TagDataTable
- `buscarTagPorId`: Tag
- `listarTags`: [Tag!]
- `buscarUltimoTermo`: Termo
- `listarVinculoUsuarioCliente`: [UsuarioCliente!]
- `filtrarUsuario`: UsuarioDataTable
- `getUserLogged`: Usuario
- `usuarioPorId`: Usuario
- `listarUsuarios`: [Usuario!]
- `Login`: Usuario
- `buscarUsuario`: [Usuario!]
- `contarAtendimentosAbertosUsuario`: AtendimentosAbertosUsuarioResult
- `filtrarAtendimentoMenuHistorico`: AtendimentoMenuHistoricoDataTable
- `filtrarFormPadrao`: FormPadraoDataTable
- `buscarFormPadraoPorId`: FormPadrao
- `listarFormPadrao`: [FormPadrao!]
- `filtrarFormPadraoAtendimento`: FormPadraoAtendimentoDataTable
- `buscarFormPadraoAtendimentoPorNanoid`: FormPadraoAtendimento
- `filtrarAba`: AbaDataTable
- `buscarAbaPorId`: Aba
- `listarAba`: [Aba!]
- `decryptFile`: DecryptJob
- `filtrarConexao`: ConexaoDataTable
- `buscarConexaoPorId`: Conexao
- `listarConexoes`: [Conexao!]
- `listarConexoesVinculadas`: [Conexao!]
- `filtrarTurno`: TurnoDataTable
- `listarTurno`: [Turno!]
- `listarTurnoAtivo`: [Turno!]
- `buscarTurnoPorId`: Turno
- `filtrarAtendimentosLazy`: AtendimentoLazyResponse
- `filtrarAtendimentosCount`: AtendimentoLazyResponse
- `filtrarCalendarioEvento`: CalendarioEventoDataTable
- `buscarCalendarioEventoPorId`: CalendarioEvento
- `filtrarWabaTemplate`: WabaTemplateDataTable
- `buscarWabaTemplatePorId`: WabaTemplate
- `listarWabaTemplatesPorAccountId`: [WabaTemplate!]
- `listarWabaTemplatesPorConexaoId`: [WabaTemplate!]
- `buscarWabaTelefones`: String
- `listarWabaSaldoPorMesAno`: [WabaSaldo!]
- `buscarWabaSaldoLimite`: WabaSaldoLimite
- `insightMensagemWaba`: [WabaInsightMensagem!]!
- `listarWabaServicoMensal`: [WabaContadorMsgMensal!]!
- `listarWabaServicoDiario`: [WabaContadorMsgDiario!]!
- `buscarContadorPorNome`: Contador
- `admFiltrarEmpresas`: EmpresaDataTable
- `adminListarEmpresas`: [Empresa!]
- `admBuscarEmpresaPorId`: Empresa
- `adminFiltrarUsuarios`: UsuarioDataTable
- `adminListarUsuariosCriacaoStatus`: [Usuario!]
- `adminListarUsuariosPorEmpresa`: [Usuario!]
- `adminFiltrarConexoes`: ConexaoDataTable
- `admTotalUsuariosEmpresa`: [TotalUsuarioEmpresa!]
- `filtrarHook`: HookDataTable
- `buscarHookPorId`: Hook
- `listarHooks`: [Hook!]
- `filtrarHookTask`: HookTaskDataTable
- `buscarHookTaskPorId`: HookTask
- `filtrarHookUrl`: HookUrlDataTable
- `buscarHookUrlPorId`: HookUrl
- `listarHookUrls`: [HookUrl!]
- `filtrarCampanha`: CampanhaDataTable
- `buscarCampanhaPorId`: Campanha
- `listarCampanhas`: [Campanha!]
- `filtrarClientesCampanha`: ClienteDataTable
- `filtrarCampanhaCliente`: CampanhaClienteDataTable
- `filtrarAviso`: AvisoDataTable
- `buscarAvisoPorId`: Aviso
- `listarLeitoresAviso`: [AvisoUsuario!]!
- `listarAvisosAtivos`: [Aviso!]
- `filtrarAgenteIA`: AgenteIADataTable
- `buscarAgenteIAPorId`: AgenteIA
- `listarAgentesIA`: [AgenteIA!]
- `filtrarBaseConhecimento`: BaseConhecimentoDataTable
- `buscarBaseConhecimentoPorId`: BaseConhecimento
- `listarBasesConhecimento`: [BaseConhecimento!]
- `listarModelosIA`: [ModeloIA!]
- `filtrarVariavelAmbiente`: VariavelAmbienteDataTable
- `buscarVariavelAmbientePorId`: VariavelAmbiente
- `listarVariaveisAmbiente`: [VariavelAmbiente!]
- `filtrarMcpServer`: McpServerDataTable
- `buscarMcpServerPorId`: McpServer
- `listarMcpServers`: [McpServer!]
- `buscarUltimaMensagemCliente`: ClienteConexaoUltimaMensagem
- `iaDashboard`: IADashboard!
- `iaExecucoes`: IAExecucaoLista!
- `iaExecucaoDetalhe`: IAExecucaoDetalhe
- `iaAtendimentoResumo`: IAAtendimentoResumo!
- `metricaConexao`: [MetricaConexaoPonto!]!
- `filtrarAlertas`: AlertaDataTable
- `buscarAlertaPorUuid`: Alerta
- `listarAlertasPorSituacao`: [Alerta!]
- `filtrarPasta`: PastaDataTable
- `buscarPastaPorId`: Pasta
- `listarPastas`: [Pasta!]
- `listarPastasEmpresa`: [Pasta!]
- `filtrarArquivo`: ArquivoDataTable
- `buscarArquivoPorId`: Arquivo
- `regenerarKeywordsArquivo`: String
- `pushDeviceUsuarioPorUuid`: PushDeviceUsuario
- `listarConexoesOcultasUsuario`: [ConexaoOculta!]
- `admListarConexoesOcultas`: [ConexaoOculta!]

### QueueUpdate (OBJECT)

- `pendingMenssages`: Float
- `msgPerMinute`: Float
- `msgSentPerMinute`: Float
- `lastReceivedMessageAt`: String
- `lastSentMessageAt`: String

### ReenviarAtendimentoMensagemInput (INPUT_OBJECT)

- `nanoid`: String

### ReplicarUsuarioInput (INPUT_OBJECT)

- `usuario_replica_id`: Int!
- `nome`: String!
- `email`: String!
- `usuario`: String!
- `senha`: String!
- `confirmar_senha`: String!

### SessionUpdateInput (INPUT_OBJECT)

- `conexao_id`: Int!
- `type`: String!

### SistemaMensagem (OBJECT)

- `id`: Float!
- `mensagem`: String
- `tipo`: Float!
- `ativo`: String!
- `arquivo`: String
- `empresa_id`: Float
- `empresa`: Empresa!
- `data_cadastro`: DateTime!
- `criacao_usuario_id`: Float
- `alteracao_usuario_id`: Float
- `alteracaoUsuario`: Usuario
- `criacaoUsuario`: Usuario

### SistemaMensagemDataTable (OBJECT)

- `rows`: [SistemaMensagem!]
- `count`: Int

### SistemaMensagemFilterInput (INPUT_OBJECT)

- `mensagem`: PrimeFilterItemString
- `tipo`: PrimeFilterItemInt
- `ativo`: PrimeFilterItemString

### SistemaMensagemInput (INPUT_OBJECT)

- `id`: Float
- `mensagem`: String
- `tipo`: Float
- `ativo`: String
- `arquivo`: String

### SistemaMensagemListInput (INPUT_OBJECT)

- `filters`: SistemaMensagemFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### Subscription (OBJECT)

- `testeAgenteResposta`: TesteAgenteResposta!
- `atualizaAtendimentoMensagemSub`: AtendimentoMensagem!
- `mensagemStatusUpdate`: MensagemStatusUpdate!
- `atualizaAtendimentoListaSub`: AtendiemntoPayload!
- `userStatusUpdate`: Usuario!
- `userListStatusUpdate`: [Usuario!]!
- `atualizaSessaoEmpresaSub`: Conexao!
- `atualizaQrCodeSub`: QrCodeObject!
- `conStateUpdate`: ConStateUpdate!
- `userWebNotification`: [UserWebNotification!]!

### Tag (OBJECT)

- `id`: Float!
- `descricao`: String!
- `cor`: String
- `ativo`: String!
- `empresa_id`: Int!
- `webhook_url`: String
- `hook_id`: Int

### TagDataTable (OBJECT)

- `rows`: [Tag!]
- `count`: Int

### TagFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### TagInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `cor`: String
- `ativo`: String
- `webhook_url`: String
- `hook_id`: Int

### TagListInput (INPUT_OBJECT)

- `filters`: TagFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### TelegramChat (OBJECT)

- `id`: Float
- `descricao`: String

### Termo (OBJECT)

- `id`: Float!
- `descricao`: String!
- `ativo`: String
- `data_hora_criacao`: DateTime!
- `usuarios`: [Usuario!]
- `aceitou`: String

### TermoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `aceitar`: String

### TestarMcpServerInput (INPUT_OBJECT)

- `url`: String!
- `headers`: String

### TestarMcpServerResult (OBJECT)

- `status`: String!
- `tools`: [McpToolResult!]!

### TesteAgenteResposta (OBJECT)

- `session_id`: String!
- `resposta`: String
- `steps`: String
- `encerrado`: Boolean!
- `motivo`: String

### TotalUsuarioEmpresa (OBJECT)

- `total`: Int
- `tipo`: Int
- `empresa_id`: Int

### TraceEvent (OBJECT)

- `uuid`: String!

### TraceEventInput (INPUT_OBJECT)

- `uuid`: String!
- `ts`: String
- `created_at`: String
- `session_uuid`: String
- `usuario_id`: Int
- `empresa_id`: Int
- `device_uuid`: String
- `app_version`: String
- `env`: String
- `type`: String
- `name`: String
- `status`: String
- `duration_ms`: Int
- `data`: String

### Transacao (OBJECT)

- `id`: Float!
- `descricao`: String!
- `empresa`: [Empresa!]

### Turno (OBJECT)

- `id`: Int!
- `descricao`: String!
- `msg_atendimento_em_andamento`: String
- `acao_novos_atend`: String
- `msg_encerramento`: String
- `data_hora_criacao`: String
- `criacao_usuario_id`: Float
- `empresa_id`: Float
- `usuario`: Usuario
- `horarios`: [TurnoHorario!]
- `ativo`: String!

### TurnoDataTable (OBJECT)

- `rows`: [Turno!]
- `count`: Int

### TurnoFilterInput (INPUT_OBJECT)

- `descricao`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### TurnoHorario (OBJECT)

- `id`: Int!
- `turno_id`: Int!
- `turno`: Turno!
- `dia_semana`: Int!
- `horario_inicial`: String!
- `horario_final`: String!

### TurnoHorarioInput (INPUT_OBJECT)

- `id`: Int
- `turno_id`: Int
- `dia_semana`: Int
- `horario_inicial`: String
- `horario_final`: String

### TurnoInput (INPUT_OBJECT)

- `id`: Int
- `descricao`: String
- `criacao_usuario_nanoid`: String
- `atualizacao_usuario_nanoid`: String
- `msg_atendimento_em_andamento`: String
- `msg_encerramento`: String
- `acao_novos_atend`: String
- `data_hora_criacao`: String
- `horarios`: [TurnoHorarioInput!]
- `ativo`: String

### TurnoListInput (INPUT_OBJECT)

- `filters`: TurnoFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### UserFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `usuario`: PrimeFilterItemString
- `email`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString
- `online`: PrimeFilterItemString
- `disponivel`: PrimeFilterItemString
- `data_hora_criacao`: PrimeFilterItemStringArray
- `empresa_id`: PrimeFilterItemInt
- `tipo`: PrimeFilterItemInt

### UserWebNotification (OBJECT)

- `header`: String
- `content`: String
- `severity`: String
- `type`: String
- `usuario_id`: Int

### Usuario (OBJECT)

- `id`: Int!
- `usuario`: String!
- `email`: String
- `token`: String
- `ativo`: String
- `nome`: String
- `empresa_id`: Float
- `empresa`: Empresa!
- `foto`: String
- `online`: String
- `disponivel`: String
- `departamentos`: [Departamento!]
- `permissoes`: [Permissao!]
- `canais`: [CanalExterno!]
- `padrao_conexao_id`: Float
- `conexao`: Conexao!
- `conexoes`: [Conexao!]
- `turno_id`: Float
- `tipo`: Int
- `admin`: String
- `data_hora_criacao`: DateTime
- `criacao_usuario`: String
- `data_alteracao_ativo`: DateTime
- `alteracao_ativo_usuario`: String
- `data_hora_login`: DateTime
- `turno`: Turno
- `cargos`: [Int!]

### UsuarioAtendimentoTimestamp (OBJECT)

- `usuario_id`: Float
- `atendimento_id`: Float
- `timestamp`: Float!
- `lida`: Float
- `nao_lida`: Float

### UsuarioAvaliacaoInput (INPUT_OBJECT)

- `nome`: String
- `razao_social`: String
- `cpf_cnpj`: String
- `email`: String
- `usuario`: String
- `senha`: String
- `confirmar_senha`: String

### UsuarioCliente (OBJECT)

- `usuario_id`: Float!
- `usuario`: Usuario
- `cliente_id`: Float!
- `cliente`: Cliente!

### UsuarioClienteInput (INPUT_OBJECT)

- `usuario_id`: Int
- `cliente_id`: Int
- `ativo`: String

### UsuarioDataTable (OBJECT)

- `rows`: [Usuario!]
- `count`: Int

### UsuarioInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `email`: String
- `usuario`: String
- `senha`: String
- `confirmar_senha`: String
- `permissoes`: [Int!]
- `departamentos`: [Int!]
- `conexoes`: [Int!]
- `padrao_conexao_id`: Int
- `canais`: [Int!]
- `ativo`: String
- `foto`: String
- `online`: String
- `turno_id`: Float
- `transferencia_usuario_id`: Int
- `acao_desativacao`: Int
- `tipo`: Int

### UsuarioListInput (INPUT_OBJECT)

- `filters`: UserFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### VariavelAmbiente (OBJECT)

- `id`: Int!
- `nome`: String!
- `descricao`: String
- `empresa_id`: Int
- `ativo`: String
- `criado_por`: String
- `alterado_por`: String
- `data_criacao`: String
- `data_atualizacao`: String

### VariavelAmbienteDataTable (OBJECT)

- `rows`: [VariavelAmbiente!]
- `count`: Int

### VariavelAmbienteFilterInput (INPUT_OBJECT)

- `nome`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### VariavelAmbienteInput (INPUT_OBJECT)

- `id`: Int
- `nome`: String
- `valor`: String
- `descricao`: String
- `ativo`: String

### VariavelAmbienteListInput (INPUT_OBJECT)

- `filters`: VariavelAmbienteFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### WabaContadorMsgDiario (OBJECT)

- `id`: Int!
- `waba_category`: String!
- `dia`: Int!
- `mes`: Int!
- `ano`: Int!
- `qtde`: Int!
- `empresa_id`: Int!
- `conexao_id`: Int!
- `conexao`: Conexao

### WabaContadorMsgMensal (OBJECT)

- `id`: Int!
- `waba_category`: String!
- `mes`: Int!
- `ano`: Int!
- `qtde`: Int!
- `empresa_id`: Int!
- `conexao_id`: Int!
- `conexao`: Conexao

### WabaEmbeddedSignupInput (INPUT_OBJECT)

- `waba_phone_id`: String
- `waba_account_id`: String!
- `conexao_id`: Int
- `register_phone`: Boolean!

### WabaInsightMensagem (OBJECT)

- `conexao_id`: Int!
- `conexao_nome`: String!
- `total`: Int!

### WabaSaldo (OBJECT)

- `id`: Int!
- `waba_category`: String!
- `mes`: Int!
- `ano`: Int!
- `saldo`: Int!
- `empresa_id`: Int!
- `conexao_id`: Int!
- `conexao`: Conexao

### WabaSaldoLimite (OBJECT)

- `saldo_utility`: Int
- `saldo_authentication`: Int
- `saldo_marketing`: Int

### WabaTemplate (OBJECT)

- `nanoid`: String!
- `id`: String
- `name`: String
- `category`: String
- `correct_category`: String
- `previous_category`: String
- `parameter_format`: String
- `language`: String
- `status`: String
- `components`: String
- `waba_account_id`: String
- `ativo`: String
- `empresa_id`: Int
- `header_handle`: String
- `header_asset_url`: String
- `header_file`: String
- `header_file_mimetype`: String
- `description`: String
- `conexao`: Conexao

### WabaTemplateButton (INPUT_OBJECT)

- `type`: String
- `text`: String
- `url`: String
- `phone_number`: String
- `example`: String
- `otp_type`: String
- `autofill_text`: String
- `zero_tap_terms_accepted`: Boolean
- `supported_apps`: [WabaTemplateSupportedApp!]

### WabaTemplateComponent (INPUT_OBJECT)

- `type`: String
- `format`: String
- `text`: String
- `example`: WabaTemplateExample
- `buttons`: [WabaTemplateButton!]
- `add_security_recommendation`: Boolean
- `code_expiration_minutes`: Int

### WabaTemplateDataTable (OBJECT)

- `rows`: [WabaTemplate!]
- `count`: Int

### WabaTemplateExample (INPUT_OBJECT)

- `body_text`: [String!]
- `body_text_named_params`: [WabaTemplateNamedParam!]
- `header_text`: [String!]
- `header_text_named_params`: [WabaTemplateNamedParam!]
- `header_handle`: [String!]

### WabaTemplateFileUpload (OBJECT)

- `header_handle`: String!
- `upload_path`: String!
- `mimetype`: String

### WabaTemplateFilterInput (INPUT_OBJECT)

- `name`: PrimeFilterItemString
- `category`: PrimeFilterItemString
- `status`: PrimeFilterItemString
- `waba_account_id`: PrimeFilterItemString
- `ativo`: PrimeFilterItemString

### WabaTemplateImageParameterAtendimento (INPUT_OBJECT)

- `link`: String!

### WabaTemplateImageParameterCampanha (INPUT_OBJECT)

- `link`: String!

### WabaTemplateImageParameterMensagem (INPUT_OBJECT)

- `link`: String!

### WabaTemplateInput (INPUT_OBJECT)

- `nanoid`: String
- `id`: String
- `name`: String
- `category`: String
- `parameter_format`: String
- `language`: String
- `allow_category_change`: String
- `message_send_ttl_seconds`: Int
- `components`: [WabaTemplateComponent!]
- `ativo`: String
- `waba_account_id`: String
- `header_handle`: String
- `header_asset_url`: String
- `header_file`: String
- `header_file_mimetype`: String
- `description`: String

### WabaTemplateListInput (INPUT_OBJECT)

- `filters`: WabaTemplateFilterInput
- `first`: Int
- `rows`: Int
- `sortField`: String
- `sortOrder`: Int
- `globalFilter`: String

### WabaTemplateNamedParam (INPUT_OBJECT)

- `param_name`: String
- `example`: String

### WabaTemplateParameterAtendimento (INPUT_OBJECT)

- `type`: String
- `parameter_name`: String
- `text`: String
- `image`: WabaTemplateImageParameterAtendimento

### WabaTemplateParameterCampanha (INPUT_OBJECT)

- `type`: String
- `parameter_name`: String
- `text`: String
- `image`: WabaTemplateImageParameterCampanha

### WabaTemplateParameterMensagem (INPUT_OBJECT)

- `type`: String
- `parameter_name`: String
- `text`: String
- `image`: WabaTemplateImageParameterMensagem

### WabaTemplateSupportedApp (INPUT_OBJECT)

- `package_name`: String
- `signature_hash`: String


# ZigChat — catálogo de permissões

> Extraído por introspecção de `https://dev.zigchat.com.br/api/graphql` em 2026-09-16.
> Referência de PRODUTO (paridade de features). A integração runtime está arquivada — ver decisão de 2026-09-16.

**142 permissões** em **34 categorias**. Modelo: `Permissao(id, descricao, categoria)` — plano, agrupado por `categoria` (o módulo). Sem escopo `.own/.all` (o Nexus tem).

| Categoria (módulo) | Qtd | Ações |
|---|--:|---|
| Aba Atendimento | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Agente IA | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Anotacao | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Atendimento | 18 | Transferir Atendimento, Atualizar Cliente, Cadastrar Anotação, Cadastrar Atendimento, Ver Histórico Transferência, Visualizar Atendimentos, Visualizar Atendimentos de Outros Usuários, Visualizar Todos os Grupos, Vincular Usuário ao Grupo, Remover usuário do Grupo, Visualizar Participantes do Grupo, Visualizar Acompanhamento de Menções, Excluir Acompanhamento de Menções, Cadastrar Acompanhamento de Menções, Visualizar Todas as Conexões, Ver Resultado de Pesquisas, Encerrar Grupo, Transferir para Agente IA |
| Base de Conhecimento | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Calendário de Eventos | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Campanha | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Canal | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Cliente | 7 | Visualizar, Editar, Excluir, Cadastrar, Exportar para Planilha, Importar de Planilha, Vincular Tags |
| Conexão | 6 | Criar Nova Conexão, Desativar Conexão, Tornar Padrão, Limpar Fila, Reconectar/Desconectar, Atualizar |
| Dashboard | 1 | Visualizar |
| Departamento | 5 | Visualizar, Editar, Excluir, Cadastrar, Alterar Período de Retenção |
| Empresa | 6 | Visualizar, Editar, Excluir, Cadastrar, Alterar tema, Alterar Período de Retenção |
| Formulário | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Formulário Modelo | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Galeria de Arquivos | 4 | Enviar arquivos pessoais, Gerenciar arquivos pessoais (editar/excluir), Enviar arquivos da empresa, Gerenciar arquivos da empresa (editar/excluir) |
| Grupo | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Histórico | 3 | Visualizar, Visualizar Todos os Históricos, Visualizar Histórico do Departamento |
| Hook | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Item | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Log | 1 | Visualizar |
| MCP Server | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Menu | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Modelo Mensagem | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Relatório | 2 | Visualizar Pesquisa de Satisfação, Auditoria de Arquivos Enviados e Recebidos |
| Restrição | 1 | Ocultar Telefone dos Contatos |
| Sistema Mensagem | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Tag | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Turno | 4 | Visualizar, Editar, Excluir, Cadastrar |
| Usuario | 6 | Cadastrar, Ativar/Desativar, Editar, Visualizar, Editar Regras e Permissões, Excluir |
| Variavel de Ambiente | 4 | Visualizar, Editar, Excluir, Cadastrar |
| WABA Saldo | 1 | Visualizar |
| WABA Template | 4 | Visualizar, Editar, Excluir, Cadastrar |
| WhatsApp | 1 | Gerenciar Sessão |

## Detalhe (id → descrição)

### Aba Atendimento

- `80` — Visualizar
- `81` — Editar
- `82` — Excluir
- `83` — Cadastrar

### Agente IA

- `119` — Visualizar
- `120` — Editar
- `121` — Excluir
- `122` — Cadastrar

### Anotacao

- `37` — Visualizar
- `38` — Editar
- `39` — Excluir
- `40` — Cadastrar

### Atendimento

- `41` — Transferir Atendimento
- `42` — Atualizar Cliente
- `43` — Cadastrar Anotação
- `44` — Cadastrar Atendimento
- `45` — Ver Histórico Transferência
- `46` — Visualizar Atendimentos
- `47` — Visualizar Atendimentos de Outros Usuários
- `48` — Visualizar Todos os Grupos
- `49` — Vincular Usuário ao Grupo
- `50` — Remover usuário do Grupo
- `51` — Visualizar Participantes do Grupo
- `56` — Visualizar Acompanhamento de Menções
- `57` — Excluir Acompanhamento de Menções
- `58` — Cadastrar Acompanhamento de Menções
- `84` — Visualizar Todas as Conexões
- `96` — Ver Resultado de Pesquisas
- `97` — Encerrar Grupo
- `136` — Transferir para Agente IA

### Base de Conhecimento

- `123` — Visualizar
- `124` — Editar
- `125` — Excluir
- `126` — Cadastrar

### Calendário de Eventos

- `99` — Visualizar
- `100` — Editar
- `101` — Excluir
- `102` — Cadastrar

### Campanha

- `114` — Visualizar
- `115` — Editar
- `116` — Excluir
- `117` — Cadastrar

### Canal

- `61` — Visualizar
- `62` — Editar
- `63` — Excluir
- `64` — Cadastrar

### Cliente

- `13` — Visualizar
- `14` — Editar
- `15` — Excluir
- `16` — Cadastrar
- `108` — Exportar para Planilha
- `118` — Importar de Planilha
- `141` — Vincular Tags

### Conexão

- `90` — Criar Nova Conexão
- `91` — Desativar Conexão
- `92` — Tornar Padrão
- `93` — Limpar Fila
- `94` — Reconectar/Desconectar
- `95` — Atualizar

### Dashboard

- `135` — Visualizar

### Departamento

- `9` — Visualizar
- `10` — Editar
- `11` — Excluir
- `12` — Cadastrar
- `71` — Alterar Período de Retenção

### Empresa

- `17` — Visualizar
- `18` — Editar
- `19` — Excluir
- `20` — Cadastrar
- `52` — Alterar tema
- `70` — Alterar Período de Retenção

### Formulário

- `72` — Visualizar
- `73` — Editar
- `74` — Excluir
- `75` — Cadastrar

### Formulário Modelo

- `76` — Visualizar
- `77` — Editar
- `78` — Excluir
- `79` — Cadastrar

### Galeria de Arquivos

- `137` — Enviar arquivos pessoais
- `138` — Gerenciar arquivos pessoais (editar/excluir)
- `139` — Enviar arquivos da empresa
- `140` — Gerenciar arquivos da empresa (editar/excluir)

### Grupo

- `5` — Visualizar
- `6` — Editar
- `7` — Excluir
- `8` — Cadastrar

### Histórico

- `53` — Visualizar
- `54` — Visualizar Todos os Históricos
- `55` — Visualizar Histórico do Departamento

### Hook

- `110` — Visualizar
- `111` — Editar
- `112` — Excluir
- `113` — Cadastrar

### Item

- `25` — Visualizar
- `26` — Editar
- `27` — Excluir
- `28` — Cadastrar

### Log

- `60` — Visualizar

### MCP Server

- `127` — Visualizar
- `128` — Editar
- `129` — Excluir
- `130` — Cadastrar

### Menu

- `21` — Visualizar
- `22` — Editar
- `23` — Excluir
- `24` — Cadastrar

### Modelo Mensagem

- `33` — Visualizar
- `34` — Editar
- `35` — Excluir
- `36` — Cadastrar

### Relatório

- `69` — Visualizar Pesquisa de Satisfação
- `89` — Auditoria de Arquivos Enviados e Recebidos

### Restrição

- `98` — Ocultar Telefone dos Contatos

### Sistema Mensagem

- `29` — Visualizar
- `30` — Editar
- `31` — Excluir
- `32` — Cadastrar

### Tag

- `65` — Visualizar
- `66` — Editar
- `67` — Excluir
- `68` — Cadastrar

### Turno

- `85` — Visualizar
- `86` — Editar
- `87` — Excluir
- `88` — Cadastrar

### Usuario

- `1` — Cadastrar
- `2` — Ativar/Desativar
- `3` — Editar
- `4` — Visualizar
- `109` — Editar Regras e Permissões
- `142` — Excluir

### Variavel de Ambiente

- `131` — Visualizar
- `132` — Editar
- `133` — Excluir
- `134` — Cadastrar

### WABA Saldo

- `107` — Visualizar

### WABA Template

- `103` — Visualizar
- `104` — Editar
- `105` — Excluir
- `106` — Cadastrar

### WhatsApp

- `59` — Gerenciar Sessão


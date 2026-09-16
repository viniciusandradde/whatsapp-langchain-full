# ZigChat — extração completa do schema (referência de produto)

Extraído por introspecção de `https://dev.zigchat.com.br/api/graphql` em **2026-09-16** (introspection e `listarPermissoes` respondem sem autenticação).

> A **integração runtime** com o ZigChat está **arquivada** (decisão de 2026-09-16: não há token machine-to-machine; o JWT é de sessão de 5 dias). Estes arquivos servem como **referência de paridade de produto** — em especial o modelo de permissões.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `schema-introspection.json` | Schema completo (474 KB) — 334 tipos |
| `permissoes.json` / `permissoes.md` | **142 permissões em 34 categorias** |
| `queries.md` | 171 queries |
| `mutations.md` | 83 mutations |
| `tipos.md` | Tipos com todos os campos |
| **`controle-de-acesso.md`** | **2ª introspecção — o *mecanismo* de atribuição**, não o catálogo. Leia este para decidir modelo. |

## Modelo de permissões do ZigChat

```
Permissao      { id, descricao, categoria }          # plano, agrupado por categoria
GrupoSistema   { id, nome, descricao, permissoes[], empresa_id }   # PRESET, não perfil
Usuario        { ..., permissoes[], departamentos[], conexoes[], canais[], admin, turno_id }
```

Três características que explicam a sensação de "sistema completo":

1. **Cobertura total** — 34 categorias cobrem *todo* módulo do sistema (inclusive Dashboard, Log, Histórico, Galeria de Arquivos, WABA Saldo, Turno).
2. **Matriz uniforme** — a maioria das categorias tem as mesmas 4 ações (`Visualizar`, `Editar`, `Excluir`, `Cadastrar`), então a tela de perfil é previsível e nada fica de fora.
3. **A permissão vive no usuário** — `Usuario.permissoes[]` é a lista efetiva.

> ⚠️ **Correção (2ª introspecção, 2026-09-16):** o `GrupoSistema` **não é um perfil** — não existe
> vínculo usuário↔grupo em lugar nenhum do schema (sem `grupo_id` no `Usuario`/`UsuarioInput`, sem
> mutation de vínculo). O grupo é um *preset* que a tela copia para a linha do usuário. Portanto a
> permissão direta no usuário não é uma *exceção* ao perfil: é o **único** mecanismo. Detalhes,
> evidência e consequências em [`controle-de-acesso.md`](controle-de-acesso.md).

E a **segmentação de acesso** não é só permissão: o usuário tem `departamentos[]`, `conexoes[]` e `canais[]` — ele só enxerga o que está vinculado a ele (e há ainda uma deny-list `ConexaoOculta` por usuário e contexto).

## Comparação com o Nexus

| | ZigChat | Chat Nexus |
|---|---|---|
| Permissões | **142** | 68 |
| Módulos/categorias | **34** | 20 |
| Granularidade | all-or-nothing por categoria | **escopo `.own` / `.all`** (mais fino) |
| Escopo por departamento | "Visualizar Histórico do Departamento" | `atendimento.scope.departamento` |
| **Escopo por conexão/canal** | **"Visualizar Todas as Conexões" + `Usuario.conexoes[]` + deny-list `ConexaoOculta`** | **não existe** |
| Vínculo usuário → perfil | **não existe** (grupo é preset copiado) | `usuario_perfil` |
| Permissão direta no usuário | **é o único mecanismo** | não (só via perfil) |
| Desativar usuário | transfere a fila (`acao_desativacao`) | **deixa atendimentos órfãos** |
| Aplicação nas rotas | uniforme | **44% das rotas** (ver `docs/ANALISE_PERMISSOES.md`) |

### Permissões do ZigChat que o Nexus não tem equivalente

- **Dashboard · Visualizar** — qualquer membro vê o dashboard hoje.
- **Histórico · Visualizar / Todos / do Departamento** — o Nexus não gateia o módulo Histórico.
- **Relatório · Ver Pesquisa de Satisfação · Auditoria de Arquivos Enviados/Recebidos**.
- **Cliente · Exportar para Planilha / Importar de Planilha** — exportar base de clientes é ação sensível (LGPD) e hoje não tem permissão própria.
- **Restrição · Ocultar Telefone dos Contatos** — mascaramento de PII por permissão.
- **Conexão · Limpar Fila · Reconectar/Desconectar · Tornar Padrão · Desativar** — ações operacionais separadas de "editar".
- **Usuário · Editar Regras e Permissões** separado de **Editar** — impede que quem edita usuário se autoconceda permissão (controle de escalação). O Nexus separa parcialmente (`empresa.member.role`).
- **Empresa/Departamento · Alterar Período de Retenção** — o Nexus tem retenção (Fase D) sem permissão própria.
- **Atendimento · Transferir para Agente IA** — devolver a conversa à IA não é gateado no Nexus.
- **Turno**, **Galeria de Arquivos**, **Grupo (WhatsApp)**, **WABA Saldo**, **Formulário**.

### O que o Nexus tem e o ZigChat não

- Escopo `.own`/`.all` por função (o Zig é all-or-nothing).
- RLS no banco (`FORCE`, roles sem bypass) — defesa além da aplicação.
- Auditoria granular (`audit_log`, login events) e DLQ de hooks.
- Multi-empresa por usuário.

## Como reproduzir a extração

```bash
curl -s https://dev.zigchat.com.br/api/graphql -H "Content-Type: application/json" \
  -d '{"query":"query{listarPermissoes{id descricao categoria}}"}'
```

Introspecção completa: ver o corpo usado em `schema-introspection.json` (query padrão `IntrospectionQuery`).

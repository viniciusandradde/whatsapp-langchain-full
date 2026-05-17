---
title: ZigChat GraphQL — referência rápida
type: resource
status: ativo
priority: baixa
created: 2026-05-06
updated: 2026-05-17
tags: [zigchat, graphql, referencia, integracao]
empresa: ZigChat-Vendor
responsavel: Vinicius-Andrade
categoria: referencia-externa
area:
projeto_pai: Integracao-ZigChat
relacionados: [Integracao-ZigChat]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ZigChat GraphQL — referência rápida

## Resumo

Plataforma concorrente do Nexus (paridade-base com a qual nos comparamos). Possui API GraphQL pública mas **sem M2M API key** — autenticação só via JWT de sessão (5 dias de TTL), capturado no login web do admin.

Doc detalhada em `docs/zigchat/` no repo (schema introspection completo, queries/mutations/types, mapping pra modelo Nexus).

## Endpoint

```
https://dev.zigchat.com.br/api/graphql
```

## Auth

```http
Authorization: JWT <token>
Content-Type: application/json
```

Token tem 5 dias de validade. Renova só com novo login web — **não há refresh nem M2M**. Por isso integração runtime é inviável; doc serve só pra paridade.

## Convenções idiomáticas (chatas)

- **IDs**: tipo Float (não Int nem ID GraphQL)
- **Booleanos**: "S" / "N" (string, não bool)
- **Datas**: ISO 8601 string
- **Upsert**: mutations `criarAlterarX` — se ID presente atualiza, se ausente cria
- **Empresa scoping**: implícito pelo JWT (não passa `empresa_id` nos args)

## Entidades principais e mapping pra Nexus

| ZigChat | Nexus | Notas |
|---|---|---|
| `Empresa` | `empresa` | direto |
| `Departamento` | `departamento` | Nexus tem hier (parent_id), Zig é flat |
| `Atendente` (User) | `auth.user` + `empresa_membro` | Nexus separa user de membership |
| `Perfil` | `perfil` + `perfil_permissao` | parecido após mig 031 |
| `Permissao` | `permissao` | Nexus tem `.own/.all` (mig 083), Zig não |
| `Cliente` | `cliente` | direto |
| `Atendimento` | `atendimento` | direto |
| `Tag` | `cliente_tag` | direto |
| `Conversa`/`Mensagem` | `mensagem_atendimento` | direto |
| `MenuChatbot` | `menu_chatbot` + `menu_item` | Nexus desnormaliza |
| `Conexao` (WhatsApp) | `conexao` | Nexus suporta Twilio + Evolution |
| `IA Agente` | `agente_ia` | similar |
| `Webhook` | `hook` + `hook_log` + `hook_dead_letter` | Nexus tem DLQ |
| `Hora atendimento` | `empresa_horario_atendimento` | similar |
| `Modelo mensagem` (Quick Reply) | `modelo_mensagem` | direto |
| `Base Conhecimento` | `base_conhecimento` | similar |
| `Campanha` | `campanha` | similar |

## Queries úteis

### Introspection
```bash
curl -sS https://dev.zigchat.com.br/api/graphql \
  -H "Authorization: JWT $JWT" \
  -H "Content-Type: application/json" \
  -d '{"query":"query{__schema{types{name}}}"}'
```

### Listar atendimentos
```graphql
query {
  atendimentos(skip: 0, take: 20, status: "Aberto") {
    id nome status iniciadoEm
    cliente { id nome telefone }
    atendente { id nome }
  }
}
```

### Criar/atualizar agente IA
```graphql
mutation {
  criarAlterarAgenteIa(input: {
    id: null
    nome: "Atendente Cardiologia"
    promptSistema: "..."
    ativo: "S"
  }) {
    id nome
  }
}
```

## Diffs significativos vs Nexus

1. **Sem `.own/.all`** — permissões zig são all-or-nothing por módulo
2. **Sem workflow** — Zig tem só menu chatbot (estilo nosso `menu_chatbot` legacy)
3. **Sem multi-LLM** — Zig usa um único provider hardcoded
4. **Sem checkpointer LangGraph** — agente IA é stateless (sem memória de conversa)
5. **Sem hook DLQ** — webhooks fire-and-forget puro
6. **Sem audit trail granular** — só log básico
7. **Sem multi-tenant em sentido estrito** — empresa = workspace mas user não pode ter múltiplas empresas

## Arquivos relacionados

- `docs/zigchat/schema-introspection.json` (430KB)
- `docs/zigchat/queries.md`, `mutations.md`, `tipos.md`, `inputs.md`
- `docs/zigchat/mapping-nexus-zigchat.md`

## Relacionados

- [[01-Projects/Integracao-ZigChat]]
- [[Empresas/ZigChat-Vendor]]

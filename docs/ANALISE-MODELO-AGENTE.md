# Análise — agente de catálogo × agente montado na UI

> Pedido: *"não quero agente tipo catálogo, quero poder fazer os agentes com
> build como no Chatvolt"*. Este documento mede a distância entre os dois
> modelos e propõe o caminho.
>
> Levantado em 2026-07-31 sobre `feat/shadcn-onda-0`.

## 1. O que o nosso modelo é hoje

Um agente é **duas coisas**: uma linha em `agente_ia` (configuração no banco,
editável pela UI) e um `template_catalog` que aponta para um **diretório Python**
em `agents/catalog/<slug>/`.

A configuração cobre prompt, modelo, temperatura, estilo, tools marcadas, bases
de conhecimento, variáveis e servidores MCP. O diretório Python decide a
**topologia do grafo**.

### Os quatro templates, medidos

| template | linhas | como monta as tools | topologia |
|---|---:|---|---|
| `vsa_tech` | 117 | `resolve_tools()` — **lê o banco** | `create_agent()` |
| `atendimento_completo` | 141 | lista **cravada em Python** | `create_agent()` |
| `agendamentos` | 119 | lista **cravada em Python** | `create_agent()` |
| `atendimento_router` | 100 | — | `StateGraph` próprio |

**Três dos quatro chamam `create_agent()` com argumentos idênticos** — verificado
linha a linha:

```python
return create_agent(
    model=model, tools=tools, system_prompt=effective_prompt,
    middleware=middleware, checkpointer=checkpointer, store=store,
)
```

O `atendimento_completo` diz na própria docstring que "espelha vsa_tech". A única
diferença real entre eles é **de onde vêm as tools**: um obedece à configuração,
o outro tem a lista fixa no código.

Só o `atendimento_router` é arquitetura de verdade — router + até 3
especialistas em paralelo + síntese.

### A consequência

Criar um comportamento novo de agente exige **arquivo Python + deploy**. O
cliente não constrói nada; escolhe entre quatro caixas, e três delas são a mesma
caixa.

## 2. O que o modelo do Chatvolt é

`POST /agents` tem **13 campos** e nenhum template: nome, descrição, modelo,
temperatura, `systemPrompt`, visibilidade, handle, config de widget, horário de
inatividade **por canal**, e `tools`.

As tools são **6 tipos**, e o desenho é deliberado:

| tipo | o que faz |
|---|---|
| `http` | **chama qualquer API HTTP** durante a conversa, via function calling |
| `datastore` | busca semântica na base |
| `request_human` | transfere para humano |
| `mark_as_resolved` | encerra |
| `delayed_responses` | resposta com atraso |
| `follow_up_messages` | follow-up automático |

O conjunto é pequeno **por desenho**: `http` é a escotilha universal. Em vez de
catalogar dezenas de ações, deixam o cliente construir a sua.

## 3. As três lacunas que importam

### L1 — A camada de template é quase toda redundante

Três templates são o mesmo `create_agent()`. O que os distingue — prompt e lista
de tools — já é configuração no banco para um deles (`vsa_tech`). Manter os
outros dois como código é dívida, não recurso.

### L2 — Não existe tool HTTP genérica

O registry cataloga ~19 tools nomeadas (calendário, CRM, memória, RAG,
transferência). Nenhuma delas é "chame esta URL". Toda integração nova é
**mudança de código nossa**, com deploy — enquanto no Chatvolt é um formulário.

Esta é a lacuna que mais separa "plataforma" de "produto sob medida".

### L3 — MCP é fiação morta

`agente_ia.mcp_server_ids` existe no banco, aparece na API, tem tela no painel
(`/catalog/mcp`) — e **nada em `agents/` ou `worker/` o consome**. Verificado:

```bash
grep -rln "mcp" src/whatsapp_langchain/agents/ src/whatsapp_langchain/worker/
# (nenhum arquivo)
```

É o terceiro caso do padrão *a UI promete o que o backend ignora* encontrado
neste módulo. Os outros dois:

- **`tools_enabled` em 3 dos 4 templates** — o admin marca as ferramentas, e
  `atendimento_completo`, `agendamentos` e `atendimento_router` descartam a
  seleção. Atinge **7 dos 9 agentes da empresa 1** no banco de dev.
- O card de `/agents` exibia `N tools` para agentes onde a seleção não vale.

MCP dói mais porque **era a escotilha**: um servidor MCP configurável resolveria
L2 de forma mais moderna que o `http` do Chatvolt.

## 4. Proposta — "agente montado na UI"

Ordem por dependência, não por tamanho.

### Etapa 1 — Fazer a configuração valer (corrige L1 e o defeito das tools)

Os três templates `create_agent()` colapsam em **um**, que lê tudo do banco.
O que hoje é `atendimento_completo` vira um agente com aquele prompt e aquele
conjunto de tools **marcado na UI** — não um arquivo.

`template_catalog` deixa de ser "qual agente" e passa a ser **"qual topologia"**,
com dois valores: `simples` (o `create_agent`) e `router` (o paralelo). Isso é
uma escolha de arquitetura, e essa sim merece existir no código.

Migration converte os agentes existentes: quem é `atendimento_completo` vira
`simples` com `tools_enabled` preenchido com a lista que estava cravada em
Python — assim ninguém perde comportamento.

### Etapa 2 — Ligar o MCP (corrige L3)

`mcp_server_ids` passa a ser lido no `loader` e as tools do servidor entram no
agente. É a escotilha, e o painel já tem a tela.

Alternativa honesta se isso não for prioridade: **tirar o campo da UI**. Prometer
e ignorar é pior que não oferecer.

### Etapa 3 — Tool HTTP genérica (corrige L2)

Uma tool `chamar_api` configurada por agente: URL, método, cabeçalhos, esquema
de parâmetros. É o `http` do Chatvolt.

Aproveita o que já existe: `api_connection` (o conector REST genérico, com
credenciais cifradas) já guarda base_url e autenticação. Falta expor como tool.

### Etapa 4 — A tela de construir

Com 1–3 feitas, `/agents/new` deixa de ser "escolha um template" e vira
"descreva o agente": nome, o que ele faz (prompt), qual modelo, o que pode
consultar (bases), o que pode fazer (tools + MCP + APIs).

## 5. O que NÃO copiar do Chatvolt

- **Prompt sem versionamento.** Eles têm `systemPrompt` e nada mais. O nosso já
  guarda histórico de override, e prompt é o ativo do cliente.
- **Agente sem departamento.** Lá o roteamento é do Flux CRM. Nosso modelo de
  departamento + fila + turnos é vantagem real; o agente conhecer o
  departamento é o que permite transferir com contexto.
- **`temperature` limitada a 1.0.** Sem motivo; a nossa vai onde o modelo vai.

## 6. Risco da mudança

O maior é **regressão silenciosa de comportamento**: um agente que hoje tem 23
tools por código e passa a ter as marcadas na UI pode ficar sem alguma. Por isso
a Etapa 1 leva migration que **materializa a lista atual** em vez de assumir
padrão.

O segundo é o `atendimento_router`, que não colapsa. Ele fica, e é o argumento a
favor de `template_catalog` continuar existindo como **topologia**.

## Relacionados

- `docs/benchmark/matriz-telas.md` — linhas `agents-lista` e `agent-editor`
- `docs/benchmark/plataformas/chatvolt/capture-chatvolt/01-mapa-funcional.md` §1
- `docs/PRD-FRONTEND.md` — Onda 3

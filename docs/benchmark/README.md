# Benchmarking funcional — metodologia

Teardown de produto de plataformas concorrentes, com o objetivo de produzir uma
**matriz de paridade** contra o Chat Nexus e um **backlog de gaps priorizado**.

Não é análise de mercado nem comparativo comercial. O recorte é funcional: o que
o produto **faz**, como resolve cada problema, e o que isso implica pro nosso
roadmap.

## Plataformas analisadas

| Plataforma | Status | Data | Pasta |
|---|---|---|---|
| Chatvolt | ✅ concluído | 2026-07-28 | [`plataformas/chatvolt/`](plataformas/chatvolt/) |

## Auditoria do nosso próprio painel

O benchmark do concorrente é funcional — o que o produto **faz**. A contraparte,
com a mesma régua de evidência aplicada ao Chat Nexus, é a auditoria de UI/UX em
[`nosso-painel/analise-ui-ux.md`](nosso-painel/analise-ui-ux.md): o que a tela
comunica, quanto custa operá-la, e um backlog priorizado por impacto ÷ esforço.
Capturada por `scripts/capture_painel_screens.py`, que é a contraparte de
`capture_chatvolt_local.py`.

## Como a análise é feita

Três fontes, em ordem decrescente de confiabilidade:

1. **API pública documentada** — specs OpenAPI, referência de endpoints. É a
   fonte mais confiável porque descreve o contrato real, não o marketing.
   Enums, campos obrigatórios e códigos de erro revelam o modelo de dados.
2. **Documentação de produto** — guias de configuração, tutoriais. Descreve
   intenção e fluxo de UX; costuma atrasar em relação ao produto.
3. **Introspecção da API em conta real** — chamadas `GET` autenticadas contra
   uma conta de teste, para confirmar formato de resposta, IDs e defaults.

**Landing page e material de vendas não são fonte de funcionalidade.** Entram
só em `00-visao-geral.md`, para posicionamento e ICP, sempre marcados como
alegação de marketing.

### Regras de evidência

- Toda linha da matriz de paridade cita evidência: arquivo colhido, URL de doc,
  ou caminho de código nosso (`arquivo.py:linha`).
- O **estado atual do Chat Nexus** vem exclusivamente de código, migrations e
  docs deste repositório. Nada de memória ou suposição — se não achei no
  código, o status é "Não temos".
- Quando a doc do concorrente e a API divergem, **a API vence** e a divergência
  é registrada.
- Funcionalidade que só aparece em vídeo/rede social e não tem lastro em doc ou
  API é marcada como **não confirmada** e não entra na matriz.

### Introspecção autenticada

Feita apenas com **chamadas de leitura** (`GET`), em conta de teste fornecida
pelo dono do produto sob análise. Nenhuma escrita, nenhum dado de terceiro.
Credenciais nunca são gravadas nestes documentos.

## Critérios de classificação

### Status no Chat Nexus

| Status | Significado |
|---|---|
| **Temos** | Funcionalidade equivalente em produção, com contrato comparável |
| **Parcial** | Existe, mas com cobertura, alcance ou ergonomia menor |
| **Não temos** | Ausente do código |
| **Não queremos** | Ausente por decisão consciente — justificada em `backlog-gaps.md` |

"Parcial" é o status mais informativo e o mais fácil de errar. A régua: se um
cliente que usa a funcionalidade no concorrente **migraria sem perceber falta**,
é "Temos". Se perceberia, é "Parcial".

### Esforço

Estimativa de implementação no **nosso** stack, considerando migration, backend,
frontend e testes.

| | Significado |
|---|---|
| **P** | Até ~2 dias. Cabe no que já existe; sem migration nova ou com uma trivial |
| **M** | ~1 semana. Migration + endpoints + tela; sem mudança arquitetural |
| **G** | Semanas. Mexe em contrato central (canal, worker, modelo de dados) ou exige integração externa nova |

### Impacto (1–5)

Quanto a ausência custa **hoje**, em venda perdida ou operação manual:

| | Significado |
|---|---|
| **5** | Bloqueia venda ou causa incidente recorrente |
| **4** | Objeção frequente; existe contorno manual caro |
| **3** | Pedido recorrente, sem bloquear |
| **2** | Diferencial marginal |
| **1** | Nice-to-have; ninguém pediu |

Impacto é sobre **o nosso ICP**, não sobre o do concorrente. Funcionalidade
central lá pode ser irrelevante aqui — e isso é resultado válido, não omissão.

### Priorização do backlog

Ordenação por **Impacto ÷ Esforço** (P=1, M=2, G=3). É um ponto de partida
mecânico, não veredito: dependência técnica e sequenciamento podem sobrepor a
ordem, e quando sobrepõem, o item diz por quê.

## Glossário

Vocabulário do concorrente ↔ nosso, para leitura cruzada da matriz.

| Chatvolt | Chat Nexus | Observação |
|---|---|---|
| Organization | `empresa` | Unidade de multi-tenancy e billing |
| Agent | `agente_ia` | Lá o agente carrega também o canal (Deploy); aqui canal é `conexao`, separada |
| Datastore | — | Container de fontes. Aqui a base é direta por empresa, sem container |
| Datasource | `documento_conhecimento` | Unidade de conteúdo indexado |
| Conversation | `atendimento` | Lá 1 conversa por contato/canal; aqui atendimento tem ciclo aberto/fechado |
| Contact | `cliente` | |
| Inbox | `/atendimento` | Tela do operador |
| Flux CRM (Scenario/Step) | `workflow` + `menu_chatbot` | Ver ressalva abaixo |
| Dispatch | `campanha` | Envio em massa |
| Artifact | — | Conteúdo estruturado consultável pelo agente |
| VoltAPI | — | Sandbox JavaScript interno |
| Tool (`http`) | — | Chamada HTTP genérica pelo agente |
| Whitelist | `whitelist_numero` | **Semântica invertida** — ver abaixo |
| Handle | `agente_ia.slug` | |
| Frustration | — | Score 0–100 de insatisfação |

### Duas armadilhas de vocabulário

**`whitelist` significa o oposto nos dois produtos.** No Chatvolt é uma
*allow-list*: o agente só fala com números da lista. No Chat Nexus,
`whitelist_numero` é uma *lista de bloqueio*: número cadastrado **não** recebe
resposta automática (`shared/whitelist.py`, migration 133). Comparar as duas
como equivalentes é erro grosseiro — são funcionalidades diferentes com o mesmo
nome.

**"Flux CRM" não mapeia limpo em nada nosso.** Ele é kanban de conversas +
máquina de estados + automação de atribuição, tudo junto. Partes correspondem
aos nossos `workflow` (LangGraph) e `menu_chatbot`, partes ao `departamento` e
`aba`, e partes não existem aqui. A matriz decompõe em linhas separadas em vez
de forçar uma equivalência única.

## Entregáveis

```
docs/benchmark/
├── README.md                        ← este arquivo
├── matriz-paridade.md               ← funcionalidade × concorrente × nós
├── backlog-gaps.md                  ← gaps priorizados + "Não replicar"
├── nosso-painel/
│   ├── analise-ui-ux.md             ← auditoria de UI/UX do NOSSO painel
│   └── img/                         ← 123 capturas (gitignored: dado de cliente)
└── plataformas/chatvolt/
    ├── 00-visao-geral.md            ← posicionamento, ICP, modelo de negócio
    ├── 01-mapa-funcional.md         ← árvore de funcionalidades por domínio
    ├── 02-api-e-integracoes.md      ← superfície de API, webhooks, integrações
    ├── 03-modelo-de-dados-inferido.md
    ├── 04-ux-flows.md               ← fluxos principais
    └── 05-fontes.md                 ← URLs consultadas, com data
```

## Domínios da análise

Toda funcionalidade é classificada em um destes onze domínios:

1. **Agentes** — criação, persona/prompt, modelos LLM, ferramentas, handoff, horários, regras
2. **Base de conhecimento (RAG)** — fontes, ingestão, reindexação, chunking, citação, limites
3. **Canais** — WhatsApp oficial e não-oficial, Instagram, Telegram, widget, API
4. **CRM / funil** — contatos, conversas, cenários, etapas, logs, tags, atribuição
5. **Disparos / campanhas** — massa, agendamento, templates, opt-out
6. **Integrações** — nativas, webhooks, Make/n8n/Zapier, e-commerce
7. **Widget/embed** — modos, customização, eventos, autenticação
8. **API e extensibilidade** — autenticação, escopo, rate limits, webhooks de saída
9. **Analytics** — métricas, relatórios, exportação
10. **Multi-tenant, permissões e billing** — organizações, papéis, limites por plano
11. **Compliance** — LGPD, retenção, residência, auditoria

## Como manter

Rodar de novo quando o concorrente anunciar release relevante, ou a cada
trimestre. O corpus de documentação é colhido por script, então a re-coleta é
barata: ver `05-fontes.md` para o método.

Ao atualizar, **preservar o histórico de decisão**. Item movido de "Não temos"
para "Temos" mantém a linha; item que sai de "Não replicar" precisa dizer o que
mudou no mundo para a decisão anterior deixar de valer.

# Matriz tela-a-tela — Chatvolt × Chat Nexus

> Capturas: Chatvolt 2026-07-28 (98 imagens, painel v4.3.19, plano Free);
> Chat Nexus 2026-07-30 (123 imagens, produção). Ambas fora do git — ver
> `.gitignore` de cada pasta.

A [matriz de paridade](matriz-paridade.md) compara **funcionalidade**: o que cada
produto faz. Esta compara **tela**: o que o desenho comunica e quanto custa
operar. São perguntas diferentes — em vários pontos temos a funcionalidade e
perdemos na tela, que é exatamente o padrão que a
[auditoria de UI/UX](nosso-painel/analise-ui-ux.md) mediu.

## Como ler o veredito

| veredito | significado |
|---|---|
| **empatar** | eles resolveram melhor; a onda copia a solução |
| **superar** | temos vantagem real; a onda preserva e explicita |
| **ignorar** | a solução deles não se aplica ao nosso ICP ou ao nosso modelo |
| **sem régua** | não existe tela equivalente lá; critério é nosso |

Onda = quando entra na [migração para shadcn](../../../.claude/plans/) (Onda 1
shell, 2 atendimento, 3 IA, 4 conectividade/disparo, 5 dashboards, 6 governança).

---

## Placar

| veredito | telas |
|---|---:|
| empatar | 6 |
| superar | 5 |
| ignorar | 4 |
| sem régua | 17 |
| **total mapeado** | **32** |

Dezessete telas sem contraparte é o dado mais importante desta matriz: **na
maior parte do painel não existe régua externa**. Copiar o Chatvolt resolve seis
telas; as outras vinte e seis dependem de critério próprio — e é por isso que os
contratos de UI (C1–C7 do plano) existem.

---

# 1. Operação

## `logs` (Inbox) × `/atendimento` — **empatar** — Onda 2

| | Chatvolt | Chat Nexus |
|---|---|---|
| Layout | duas colunas fixas: fila à esquerda, conversa à direita | drawer `max-w-3xl` sobre backdrop escuro (`atendimento-drawer.tsx:321`) |
| Abas | 5 (Não Resolvidas · Não Lidas · Humano Solicitado · Resolvidas · Todas) | **as mesmas 5** — espelhadas no ciclo anterior |
| Badge de contador | em "Não Lidas" e "Humano Solicitado" | contadores existem, badge só na sidebar |
| Prévia da última mensagem | sim, no item da lista | **não** — o card mostra 3 linhas de metadado e zero conteúdo |
| Densidade | linha de lista | card de ~250px por conversa |
| Autoscroll / paginação | sim | **nenhum dos dois** (`limit=200` fixo, cursor ignorado) |

**O que copiar:** o layout de duas colunas e a prévia no item. Não é preferência
estética — hoje o operador escolhe entre ver a fila **ou** ler a conversa.

**O que não copiar:** a taxonomia de abas já é nossa e está congelada pelo APK
instalado (`meus|aguardando|grupos|outros` seguem aceitos).

## `contacts` × `/clientes` + `/disparador/contatos` — **empatar** — Onda 4

Lá o cabeçalho põe "Exportar Contatos" e "Disparar p/ Filtrados" lado a lado: a
lista foi desenhada como origem de campanha. Aqui `/disparador/contatos` tem
**19.647 contatos, mil renderizados, sem busca e sem paginação** — o caminho
para achar um contato é clicar "Carregar mais" dezenove vezes.

**O que copiar:** o atalho lista→campanha e o filtro salvo.
**O que resolver antes:** busca server-side e paginação (item U18 do backlog).

## `dispatches` × `/campanhas` — **superar** — Onda 4

No Chatvolt a tela é inacessível no plano Free — modal de upgrade sobre página
desfocada. Do produto pago vimos o paywall, não a tela. Nós temos campanha com
template HSM, mídia, agendamento, pool de conexões, teto diário e aquecimento.

**Régua:** nenhuma. É registrar que a comparação não é possível e medir por
critério próprio.

---

# 2. Agentes e conteúdo

## `agents-lista` × `/agents` — **empatar** — Onda 3

O card deles carrega **diagnóstico**: modelo em uso, "Sem base de conhecimento",
e `Prompt: 8594 / 6k` em vermelho. O nosso carrega **configuração**:
`temp 0.50 · top_p 0.85 · 3 tools · 1 KBs` — e esconde num contorno cinza que
**8 dos 9 agentes estão inativos** e que um está sem modelo (`Modelo: —`).

**O que copiar:** a inversão de prioridade — problema na cara, hiperparâmetro no
editor. É o item U2 do backlog.

## `agent-editor` × `/agents/[slug]/edit` — **superar** — Onda 3

Lá criar agente é **modal sobre a lista** — não existe rota de criação, e o
editor de prompt nasce dentro de uma caixa. Aqui é página inteira, com base de
conhecimento, tools, MCP e playground.

**Onde perdemos mesmo assim:** a página tem 3.000px porque lista os 24
documentos da base sem paginação, e o campo que define o produto — o system
prompt — é uma textarea de 200px no topo.

## `datastores` × `/settings/pastas` + base do agente — **empatar** — Onda 3

O card deles mostra "Privado" e "0 agentes" **antes** do conteúdo: a pergunta
que anteciparam é "quem está usando isto", não "o que tem aqui". Nossa lista de
documentos não diz qual agente consome qual base.

---

# 3. Análise e configuração

## `analytics` (8 abas) × `/dashboard/*` + `/chats/relatorios` — **empatar** — Onda 5

Oito abas, entre elas **Créditos** e **Anúncios**, com aviso de retenção de 90
dias no topo. É analytics de quem cobra por uso e vende para quem compra
tráfego. Nosso equivalente está espalhado em quatro rotas
(`/dashboard/atendimento`, `/dashboard/ia`, `/dashboard/qualidade`,
`/chats/relatorios`) sem índice comum.

**O que copiar:** o agrupamento numa tela com abas.
**O que ignorar:** as abas de Créditos e Anúncios — não é o nosso modelo.

## `settings-organization` × `/companies/[id]` — **empatar** — Onda 6

Quatro abas de topo e cinco sub-abas, com "Resumo da Empresa — usado como
contexto pelos agentes" no mesmo formulário da URL do dashboard do cliente: a
organização é objeto de primeira classe, desenhado para quem opera várias
contas. Nosso form de empresa tem 981 linhas e 21 inputs numa coluna só.

## `settings-billing` × `/billing` — **superar** — Onda 6

A tela deles é tabela de preços; o consumo real (2/200) vive fixo na barra
lateral, visível em toda tela. Nós temos consumo detalhado por recurso — mas só
no dashboard, e com **barra cheia significando "ilimitado"** (item U4).

**O que copiar:** o medidor persistente no shell. **Onda 1.**

## `settings-api-keys` × `/disparador/api-keys` — **superar** — Onda 6

Lá: criar, revelar, excluir — **sem escopo, sem nome, sem validade, sem rotação,
sem último uso**. Já registrado em "não copiar" no
[backlog](backlog-gaps.md).

## `settings-llm-keys` × `/catalog/models` — **superar** — Onda 6

A tela deles mostra dois provedores travados no Premium, enquanto o objeto da
organização carrega seis campos de chave: a régua de plano está na interface,
não no backend. Nosso catálogo de modelos é editável e global/por empresa.

## `permissoes-membros` × `/settings/perfis` + `/usuarios` — **superar** — Onda 6

Eles têm permissão por agente e por base. Nós temos RBAC granular com perfis,
departamentos, turnos e auditoria — muito além.

**Onde perdemos na tela:** "4 perfil(s) — 4 system, 0 customizado(s)" e
*"equivalente ao role 'admin' legacy"* — dívida de migração virou copy de
produto (item U17).

## `onboarding` × `/onboarding` — **empatar** — Onda 1

Lá **não existe** onboarding: jogam o usuário na lista de agentes e apostam no
tutorial embutido. Aqui a tela existe, tem 4 passos com progresso e estado — e é
**inalcançável**: `app/page.tsx:15` manda todo login para o dashboard.

**O veredito é "empatar" por ironia:** os dois produtos entregam zero onboarding
ao usuário. A diferença é que o nosso já está construído e só falta um
`redirect`. É o item U0, o de melhor razão impacto/esforço do backlog.

## `apps` × `/settings/integracoes` — **ignorar** — Onda 4

Dois cards, um vazio e quebrado, outro um "Slack Bot" descrito em inglês no meio
de um painel em português — herança de base de código anterior. Nada a aprender.

---

# 4. Fora de escopo (decisão anterior, mantida)

| tela | por quê |
|---|---|
| `crm` (Flux CRM) | kanban + máquina de estados + automação num objeto só; não é o nosso modelo |
| `voltapi` | sandbox JavaScript interno |
| `partner-set` | programa de parceiro |
| `artifacts`, `artifact-categories` | racham RAG e registro consultável em dois produtos e cobram pelo segundo por unidade |
| `forms` | módulo completo, **ausente da barra lateral** deles — funcionalidade entregue a um cliente e nunca promovida |
| `custom-dashboard` | moldura de iframe, escrita para quem *recebe* o painel de uma agência |

---

# 5. Sem régua — 17 áreas onde não existe contraparte

`/connections` · `/queue` · `/traces` · `/whitelist` · `/tags` ·
`/agendamentos` · `/atendentes` · `/settings/turnos` · `/settings/horarios` ·
`/governanca/ia-budget` · `/relatorios/allure` · `/settings/security/*` ·
`/catalog/mcp` · `/workflows` · `/menus` · `/hooks` · `/dashboard/rag*`

Aqui o Chatvolt não ajuda nem atrapalha. O risco é o oposto do de copiar: **são
as telas onde a inconsistência nasce**, porque não há referência nenhuma
puxando o desenho para um padrão. Os contratos C1–C7 do plano de migração valem
principalmente para elas.

Duas dessas merecem nota, porque são vantagem competitiva com tela ruim:

- **`/connections`** — o Chatvolt não separa canal de agente (o Deploy é do
  agente). Nós temos conexão como objeto próprio, multi-provider, com anti-ban e
  aquecimento. E a ação mais consequente do produto — ligar/desligar a IA — é um
  `<select>` dentro da linha da tabela, sem confirmação e sem feedback.
- **`/settings/security/*`** — auditoria, histórico de acesso e governança não
  têm equivalente lá. São telas de venda para cliente grande, hoje renderizadas
  como tabelas cruas.

---

## Manutenção

Regra do [ADR-015](../../../.claude/plans/): **nenhuma onda fecha sem as linhas
dela preenchidas aqui**, e veredito "superar" exige print lado a lado. Quando o
Chatvolt lançar release relevante, recolher com
`scripts/capture_chatvolt_local.py` e revisar os vereditos — preservando o
histórico, como manda o [README](README.md).

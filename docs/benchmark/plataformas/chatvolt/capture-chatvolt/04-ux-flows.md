# Chatvolt — fluxos de UX

> Reconstruídos a partir da documentação passo a passo (que é ilustrada com
> screenshots do painel). Coleta: 2026-07-28.
>
> **Fluxos marcados 🎥 precisam de captura manual** — a doc não cobre, ou cobre
> de forma insuficiente para avaliar ergonomia. Ver seção final.

## Navegação principal

Menu lateral inferido dos caminhos citados na doc e nas URLs de `app.chatvolt.ai`:

```
Agents          → app.chatvolt.ai/agents
Datastores      → app.chatvolt.ai/datastores
Inbox           → conversas
CRM (Flux)      → cenários e steps
Dispatches      → app.chatvolt.ai/dispatches
Artifacts       → catálogo
VoltAPI         → funções JS
Contacts        → contatos
Analytics       → (não documentado)
Settings        → app.chatvolt.ai/settings
                  ├── api-keys
                  ├── billing
                  ├── llm-keys
                  └── organization → Team → permissões
```

Estrutura do agente, por abas: **Settings** (global, tools, webhooks) e
**Deploy** (canais).

---

## Fluxo 1 — Criar agente e colocar no ar

Caminho feliz declarado pela doc (`agent/get-started`), em três passos:

```
1. Agents → novo agente → configurar (nome, modelo, prompt, temperatura)
2. Datastores → criar datastore → conectar ao agente via Datastore Tool
3. Deploy → escolher canal
```

**Observação de design:** o agente nasce **sem** base de conhecimento. Conectar
conhecimento é ato explícito, via *ferramenta* — não é campo do agente. A
consequência é conceitualmente elegante (RAG é uma tool como outra qualquer) mas
custa um passo a mais no onboarding.

No Chat Nexus a base é da empresa e o agente enxerga por gate
(`knowledge_enabled`), sem passo de ligação. Menos flexível, mais direto.

---

## Fluxo 2 — Conectar WhatsApp Oficial

`integrations/whatsapp`:

```
Agents → [agente] → Deploy → WhatsApp → Settings → Add WhatsApp Account
   → popup Facebook (Embedded Signup)
   → escolher: número de teste Meta | novo número | número existente do WhatsApp Business App
   → autorizar
```

**O ponto de venda mais forte da integração**, destacado na própria doc: conectar
um número existente **mantém o app WhatsApp Business funcionando no celular**,
com sincronização em tempo real entre app e plataforma.

Isso remove a maior objeção de PME na adoção de plataforma de atendimento — o
medo de "perder o WhatsApp do celular". Nós usamos o mesmo Embedded Signup
(`docs/WABA_SETUP.md`), mas **não comunicamos essa garantia em lugar nenhum**.
É ganho de conversão sem escrever código.

---

## Fluxo 3 — Handoff humano na Inbox

```
Inbox → conversa → [Reply]        → IA desligada, operador assume
                 → [Enable AI]    → IA religada
```

Dois botões, um estado (`isAiEnabled`). O operador vê e controla exatamente uma
coisa.

Comparação: no nosso `/atendimento`, o estado equivalente é derivado de status +
atribuição, e o operador manipula indiretamente (assumir, transferir, fechar).
Mais poderoso e mais difícil de prever — ver
[`03-modelo-de-dados-inferido.md`](03-modelo-de-dados-inferido.md#a-nota-sobre-handoff).

---

## Fluxo 4 — Corrigir resposta errada (fine-tuning)

O fluxo mais bem desenhado do produto:

```
Inbox → identifica resposta ruim → [improve]
      → operador escreve a resposta correta
      → sistema cria datasource Q&A no datastore ligado
      → agente acerta perguntas similares daí em diante
```

Quem corrige é **quem atende**, não quem programa. O ciclo de melhoria fecha em
segundos, dentro da tela onde o erro foi visto.

Temos as peças (`fewshot_example`, `rag_learner`, sugestões em `/dashboard/rag`)
mas o gatilho vive em **outra tela**, operada por outro perfil. É diferença de
ergonomia, não de capacidade — e ergonomia é o que determina se a ferramenta é
usada.

---

## Fluxo 5 — Montar funil no Flux CRM

```
CRM → criar cenário → [New Step] → modal de configuração abre automaticamente
    → Básico:   nome, agente responsável, condição de entrada (linguagem natural),
                prompt extra, mensagem de entrada
    → Avançado: obrigatório, remoção, solicitar contato, auto next step,
                padrões (status/prioridade/IA/tags/atribuição),
                notificação Z-API, webhook
    → board kanban: arrastar steps para reordenar, arrastar conversas entre steps
```

Detalhe de UX que vale copiar: **o modal de configuração abre sozinho ao criar o
step.** Não existe step vazio esperando configuração — o sistema força a decisão
no momento certo.

---

## Fluxo 6 — Disparo em massa

```
Dispatches → [Create List] → upload CSV + mapear colunas (name, phone)
                           → revisar e editar antes de salvar
           → [New Dispatch] → nome, listas, agente, cenário CRM, step inicial,
                              status padrão, agendamento
           → [Start Dispatch]
           → abas: Active | Scheduled | Completed | Saved Lists
```

O passo que muda tudo: **escolher cenário + step inicial**. Quem responde ao
disparo cai dentro de um funil configurado, não numa conversa solta.

Nossas campanhas (`shared/campanha.py`) enviam e devolvem a resposta ao fluxo
normal de atendimento. Tecnicamente entregamos a mensagem; funcionalmente não
entregamos a **operação de vendas** que vem depois.

---

## Fluxo 7 — Permissões por agente

```
Settings → Organization → card Team → [ícone de engrenagem] no membro
   → modal:  Admin (sim/não)
             permissões por módulo
             lista de agentes com View / Update / Delete por linha
             ações em massa: "set all to View/Update/Delete" | "disable all"
   → salva automaticamente
```

A ação em massa existe porque a lista cresce com o número de agentes — decisão
de UX que antecipa o problema de escala da própria tela.

---

## Fluxo 8 — Configurar webhook com validação

```
Agents → [agente] → Settings → Webhooks
   → URL + header opcional
   → [salvar] → sistema faz POST de teste ANTES de gravar
        resposta > 5s  → "Slow", pede endpoint melhor
        > 6s / inalcançável → "Unreachable"
   → em uso: falhas consecutivas bloqueiam automaticamente
             desbloqueio = re-salvar a URL
```

Valida o consumidor **na configuração**, não na produção. Nossa DLQ
(`shared/hook_dispatcher.py` + migration 023) trata o problema depois que
aconteceu; eles evitam que aconteça. As duas abordagens são complementares.

---

## Fluxo 9 — Escrever função VoltAPI

```
VoltAPI → [+] → função criada com nome gerado
        → editor JS (async (input) => {...})
        → [AI Assistant] gera / explica / depura o código
        → console de execução mostra logs
        → menu ⋮ → renomear | deletar | habilitar/desabilitar
```

Assistente de IA embutido no editor de código do próprio produto — reduz a
barreira de "precisa de dev" que normalmente mata funcionalidades de
extensibilidade em ferramenta no-code.

---

---

# Capturas

Screenshots em [`img/`](img/). Cada subseção traz **o que a escolha de design
revela sobre a prioridade deles** — não descrição do que está na tela.

## Como capturar

Dois scripts, porque o Chatvolt **não tem login por senha** (NextAuth: magic
link, código ou Google). A VPS não consegue se autenticar sozinha.

| Script | Onde roda | Para quê |
|---|---|---|
| `scripts/capture_benchmark_screens.py` | VPS | Páginas públicas; painel se houver `storage_state.json` |
| `scripts/capture_chatvolt_local.py` | PC do operador | Painel autenticado — login manual uma vez, captura automática depois |

```bash
# VPS — páginas públicas
uv run python scripts/capture_benchmark_screens.py --set publico

# PC do operador — painel (copiar só o arquivo, é autocontido)
pip install playwright && playwright install chromium
python capture_chatvolt_local.py            # login uma vez, captura tudo
python capture_chatvolt_local.py --reusar   # rodadas seguintes
```

As rotas do painel **não são chute**: saem do `_buildManifest.js` do app.

```bash
curl -s https://app.chatvolt.ai/auth/signin | grep -oE '"buildId":"[^"]+"'
curl -s https://app.chatvolt.ai/_next/static/<buildId>/_buildManifest.js
```

Gotcha do host: na VPS ARM/OEL8 o `headless_shell` do Playwright dá **SIGSEGV**.
Os scripts passam `channel="chromium"` para usar o build completo, que roda
normal. Não trocar sem testar em `aarch64`.

⚠️ Telas de Inbox e Contatos contêm dados de cliente real. Revisar antes de
commitar.

---

## C1 — Login

![Tela de login do Chatvolt](img/chatvolt-login.png)

**Não existe senha.** Magic link por e-mail, código de verificação ou Google —
NextAuth puro, mais uma confirmação da linhagem Chaindesk
([`00-visao-geral.md`](00-visao-geral.md#linhagem-técnica--a-leitura-mais-importante-deste-documento)).

O que a escolha revela: eles **abriram mão de gerenciar credencial** —
sem hash de senha, sem fluxo de recuperação, sem política de complexidade, sem
a superfície de ataque que vem junto. É decisão de time pequeno que prefere não
manter o que não é o produto.

O card diz "acessar **ou criar** sua conta": mesmo campo para login e cadastro,
sem tela de registro separada. Fricção zero na aquisição — o custo é não coletar
nada no cadastro (nome, empresa, telefone), o que empurra a qualificação para
depois, no `/onboarding`.

Contraste conosco: usamos Better Auth com senha, reset sem SMTP (admin
compartilha o link manualmente, migration 025), rate limit próprio no login e
histórico de acesso. É mais trabalho de manutenção, mas atende cliente
corporativo que exige controle de credencial — e magic link em e-mail
corporativo com filtro agressivo é fonte conhecida de chamado de suporte.

## C2 — Landing

![Landing do Chatvolt](img/chatvolt-landing.png)

## C3 — Página de preços

![Preços do Chatvolt](img/chatvolt-pricing.png)

Valores e limites já extraídos em
[`00-visao-geral.md`](00-visao-geral.md#planos) — vieram do bundle JS, não da
leitura da imagem.

---

## Pendentes 🎥

Precisam de sessão autenticada. Rodar `capture_chatvolt_local.py` no PC e
transferir as imagens; depois cada uma vira subseção aqui.

**Descobertas no `_buildManifest.js` que a documentação não menciona** — estas
são as mais valiosas, porque são pontos cegos da análise atual:

| Slug | Rota | Por que importa |
|---|---|---|
| `analytics` | `/analytics` | **Existe** — com `CreditsAuditTab` e `FiltersAnalytics`. A doc não cita; eu havia marcado "não avaliável" |
| `custom-dashboard` | `/custom-dashboard` | Dashboard montável pelo cliente? Não documentado |
| `forms` | `/forms`, `/forms/[id]/admin` | Resolve o mistério do módulo "Forms" que só aparecia nas permissões |
| `apps` | `/apps` | Catálogo/marketplace de integrações? |
| `partner-set` | `/partner-set` | **Programa de parceiro/revenda** — encaixa no ICP de agência |
| — | `/integrations/crisp/*` | Integração **Crisp**, ausente da lista de canais documentada |

Fluxos de produto:

| Slug | Rota | O que observar |
|---|---|---|
| `inbox` | `/logs` | Filtros, densidade, ações em massa, painel do contato, exibição de tags/frustration/summary. `/logs/ActiveUsers` sugere presença em tempo real |
| `agent-editor` | `/agents/create` | Organização das abas, ergonomia do prompt, editor de HTTP Tool e o toggle "Provided By User" |
| `crm` | `/crm` | Board kanban, densidade com muitos cenários |
| `dispatches` | `/dispatches` | As quatro abas; onde ficam (se ficam) os controles anti-ban |
| `artifacts` | `/artifacts` | Cadastro de produto, mídia, e **como o agente apresenta isso no WhatsApp** |
| `contacts` | `/contacts` | `CTWAAttributionCard` e `ContactExport` aparecem no manifest — exportação existe |
| `voltapi` | `/voltapi` | Editor JS e o assistente de IA embutido |
| `settings-billing` | `/settings/billing` | Consumo de crédito em tempo real, alerta de limite, upgrade |
| `settings-llm-keys` | `/settings/llm-keys` | Quais provedores o BYOK aceita |
| `settings-organization` | `/settings/organization` | Modal de permissão por agente, com as ações em massa |
| `onboarding` | `/onboarding` | Quantos passos até o primeiro agente respondendo |

Faltam ainda, e exigem interação além de navegar:

- **Mobile** — `--mobile` captura em 390×844; avaliar se o operador atende pelo celular
- **Widget no site** — aparência padrão e customização real
- **Fluxo NPS** — só aparece como evento de webhook; onde se configura?

# Loop bot↔bot no WhatsApp — diagnóstico e plano

Análise de 2026-09-17. Pergunta do dono: como impedir que o agente do Nexus entre
em ida-e-volta infinita com **outro** autômato (bot de outra empresa, auto-resposta
"recebemos sua mensagem", outro número do próprio Nexus com IA ligada), gastando
tokens e — a partir de 1º/10/2026 — tarifa da Meta por mensagem.

Conclusão curta: **o Nexus já tem o teto de custo (rate limit por telefone) e o
eco do próprio número filtrado, mas não tem nenhum detector nem nenhum freio por
conversa.** O loop hoje é limitado a 120 voltas/hora por número — o suficiente
para custar ~R$100/dia por número em loop, sem ninguém ser avisado.

A recomendação é a mesma que o e-mail resolveu em 2004 (RFC 3834): **marcar o que
é automático, nunca responder ao que é automático, e limitar a uma resposta
automática por remetente por período.** No WhatsApp não existe cabeçalho
`Auto-Submitted`, então os três passos viram sinais que nós mesmos criamos e
medimos — sempre em código determinístico, nunca no LLM.

---

## 1. Por que o exemplo com `loop_count` no State não se aplica aqui

No Nexus há **um grafo por `(telefone, agente)`**, e cada volta do loop é uma
execução separada do worker: o webhook enfileira, `worker/processor.py::process_message`
faz UM `graph.ainvoke`, envia a resposta e termina. Não existem dois agentes
dentro do mesmo grafo trocando mensagens; o "outro agente" está em outro servidor,
do outro lado do WhatsApp. Logo:

| Sugestão original | Equivalente no Nexus |
|---|---|
| `loop_count` no `AgentState` + `conditional_edges` | contador **por thread no banco** (`message_queue` já tem tudo: `created_at`, `processed_at`, `origem_resposta`), checado no worker **antes** do `ainvoke` |
| `recursion_limit` no `invoke` | vale, mas protege de OUTRA coisa: agente que fica chamando tool em círculo dentro de um turno. Hoje não é definido (default 25 do LangGraph) |
| `interrupt` do LangGraph | o Nexus já tem o equivalente fora do grafo: fila humana (`status='aguardando'`), HITL (`atendimento.hitl.approve`), handoff. A pausa é uma coluna no atendimento, não um checkpoint parado |
| marcador `[BOT_MSG]` no system prompt | marcador **invisível** e aplicado **pelo código** no cliente outbound, nunca pelo prompt (o modelo esquece, e o cliente real veria) |

---

## 2. O que já existe (medido no código)

| Defesa | Onde | O que cobre | Limite |
|---|---|---|---|
| Descarta `fromMe=true` | `evolution_webhook.py:197` | eco do próprio número | só o próprio número; não cobre outro número do Nexus |
| Descarta grupo/broadcast/newsletter | `evolution_webhook.py:~205` | loops em grupo | — |
| Rate limit **120/h por telefone** | `server/dependencies.py::check_rate_limit`, chamado em `evolution_webhook.py:389` | teto absoluto de voltas | é teto, não detector: 120 voltas/h × (US$0,0013 LLM + R$0,035 Meta) ≈ **R$4,4/h ≈ R$105/dia por número**, em silêncio |
| Debounce/agrupamento | `shared/queue.py::enqueue_or_buffer` | junta rajadas de texto do mesmo número | bot que responde na hora gera 1 row por resposta — o agrupamento não segura loop |
| Modo manual por conexão | `processor.py:~2489` | conexão sem IA nunca responde | é tudo-ou-nada por conexão |
| `whitelist_numero` (bloqueio por número) | `processor.py:~2510` | kill switch manual por número | alguém precisa perceber e cadastrar |
| `ia_budget` por empresa | `governanca_ia.py:~210` | teto de gasto | default `acao_estouro='alertar'` — **não bloqueia** (achado M1 do red team) |
| Handoff / fila humana / HITL | `processor.py`, `atendimento.hitl.approve` | pausa a IA quando um humano assume | não é acionado por comportamento, só por decisão |

Sinais do provedor que **não** existem: nem a Cloud API da Meta nem o Baileys
(Evolution) expõem um "isto é um bot". O Baileys não sabe sequer dizer se a conta
conectada é Business ([issue #2219](https://github.com/WhiskeySockets/Baileys/issues/2219));
o payload do Evolution traz `pushName`, `source` (android/ios/web/desktop) e
`messageTimestamp` ([webhooks](https://evolutionapi-evolution-api-90.mintlify.app/events/webhooks)),
e `verifiedBizName` só quando a outra ponta é uma conta Business verificada. Nada
disso separa humano de autômato: o próprio Nexus roda em número pessoal.
**Os sinais úteis são comportamentais** — e estão todos em `message_queue`.

---

## 3. Lacunas

1. **Nenhum detector.** Um número que responde em 1 segundo, 40 vezes seguidas,
   com o mesmo texto, é tratado igual a um cliente conversando.
2. **Nenhum freio por conversa.** As únicas pausas são por conexão inteira (modo
   manual) ou por número cadastrado à mão (whitelist).
3. **Nada marca a saída do Nexus como automática.** Dois números do próprio Nexus
   com IA ligada, um falando com o outro (cliente que também usa Nexus; teste do
   dono entre a instância pessoal e a de produção), entram em loop sem que nenhum
   dos lados consiga reconhecer o outro.
4. **Ninguém é avisado.** O loop só aparece no custo do OpenRouter e, a partir de
   outubro, na fatura da Meta.
5. `recursion_limit` implícito (25) e sem tratamento: `GraphRecursionError` cai
   no `except` genérico e a mensagem volta pra fila com retry — paga de novo.

---

## 4. Proposta em camadas

Ordem de custo crescente e valor decrescente: a camada 1 resolve o caso
Nexus↔Nexus de graça; a camada 2 é o detector de verdade; a 3 é o humano; a 4 é
o teto que segura se tudo o mais falhar.

### Camada 1 — Origem (webhook): marcar o automático, descartar o automático

**1a. Marcador invisível em toda saída automática.** Anexar ao fim de cada texto
enviado por agente/menu/workflow/CSAT uma sequência de zero-width (por exemplo
`U+200B U+200D U+200B` — `​‍​`). O WhatsApp preserva esses
caracteres no corpo da mensagem; o cliente real não vê nada.

- **Onde entra (uma vez só):** no cliente outbound que o worker usa —
  `worker/outbound_client.py` (Protocol) / `processor.py::_resolve_outbound_client`
  devolve o cliente já embrulhado num `_MarcadorAutomatico` que acrescenta a
  sequência em `send_message`. Há 20+ `outbound.send_message(...)` espalhados no
  worker; tocar em cada um é convite a esquecer um. O envio **humano** pelo
  composer vai por `shared/outbound.py::send_outbound_manual`, caminho separado —
  e **não** leva marcador: é o `Auto-Submitted: no` do RFC 3834.
- **Descartar na entrada:** em `evolution_webhook.py`, logo após o filtro de
  grupo (~linha 215) e antes do prefetch de mídia (que custa download), se o texto
  contém a sequência → `Response(200)` + log `webhook_descartado_marcador_automatico`
  + contador. Mesmo ponto em `webhook_waba.py`. Isso mata Nexus↔Nexus na primeira
  volta, com custo zero (nem entra na fila).
- **Higiene obrigatória:** remover a sequência do texto **antes** de qualquer
  coisa que o modelo leia (histórico do checkpointer, `normalized_input`,
  transcrição, timeline). Um marcador que vaza pro prompt vira ruído e pode ser
  copiado pelo modelo — e caracteres invisíveis são vetor conhecido de
  injeção ([Originality.AI](https://originality.ai/blog/invisible-text-detector-remover)).
  Regra: a sequência existe só no fio; nasce no cliente outbound e morre no webhook.
- **Limite honesto:** bot de terceiros não carrega o nosso marcador. A camada 1
  resolve o loop interno e o eco; o externo é a camada 2.

**1b. Supressão de duplicata exata.** O caso mais comum de bot externo é
auto-resposta fixa ("Obrigado pelo contato, em breve retornaremos"). Regra no
webhook, antes de enfileirar: mesmo `(empresa_id, phone_number)` + mesmo
`md5(texto normalizado)` **≥ 3 vezes em 10 minutos** → descarta a 3ª em diante,
com log. Consulta indexada em `message_queue` (`idx_queue_phone_agent` +
`created_at`) — sem tabela nova. Humano que manda "ok" três vezes em 10 min é
raro e, se acontecer, perde só a repetição, não a conversa.

**1c. Guardar os sinais, não decidir por eles.** `pushName`, `source` e
`verifiedBizName` (quando vier) entram no log estruturado do webhook. Servem
para o operador e para o detector da camada 2 ponderar; sozinhos não descartam
nada.

### Camada 2 — Worker: detector determinístico de ping-pong, antes do `ainvoke`

Novo módulo `shared/loop_guard.py` com **funções puras** (testáveis sem banco)
+ uma consulta. Chamado em `processor.py::process_message` **depois** do gate de
whitelist (~linha 2530) e **antes** de qualquer coisa que custe (transcrição,
preprocess de mídia, agente). Lê as últimas N rows da thread em `message_queue`
e avalia três sinais; **qualquer um** dispara:

| Sinal | Critério sugerido | Por que esse número |
|---|---|---|
| **Latência sub-humana** | `created_at` do inbound − `processed_at` da row anterior (momento em que NÓS respondemos) **< 3 s**, em **≥ 3 voltas consecutivas** | humano lê e digita; "ok" rápido existe, três seguidos não. `processed_at` já é gravado em `mark_done` |
| **Cadência sem humano** | **≥ 8 voltas em 5 min** todas com `origem_resposta='agente'` (nenhuma resposta de operador, nenhuma nota interna no meio) | cliente em rajada manda fotos/áudios, não 8 turnos respondidos pelo agente em 5 min |
| **Repetição** | **≥ 3** inbounds com mesmo hash **ou** ≥ 4 respostas NOSSAS iguais em 15 min | cobre o bot externo fixo E o nosso agente preso numa resposta padrão |

Mais um **teto por thread**, independente dos sinais: **≥ 30 respostas do
agente para o mesmo número em 1 h** → dispara. É um quarto do rate limit
(120/h) e ainda é mais conversa do que qualquer atendimento real.

**O que acontece ao disparar** (tudo determinístico, nada de LLM):

1. `UPDATE atendimento SET ia_pausada_ate = NOW() + INTERVAL '6 hours',
   ia_pausa_motivo = 'loop_suspeito'` (mig nova, `189_atendimento_ia_pausada.sql`).
   Seis horas casa com o cooldown que `shared/ia_alertas.py` já usa.
2. A mensagem fica na timeline com marcador interno
   `[IA pausada — possível loop com outro bot]` (entra em `MARKERS_INTERNOS`,
   `shared/atendimento.py:1377`, para o preview da fila não mostrar).
3. **Nada é enviado ao número.** Nem "vou encaminhar a um atendente": qualquer
   saída alimenta o outro bot. É o "at most one auto-response per sender per
   period" do RFC 3834 levado ao limite — zero durante a pausa.
4. Atendimento vai/fica na fila humana (`status='aguardando'`, mesmo contrato
   do modo manual) com `ia_pausa_motivo` visível no card.
5. Hook `atendimento.loop_detectado` (novo em `EVENTOS_VALIDOS`,
   `shared/hook_dispatcher.py`) + notificação ao dono pelo caminho que
   `ia_alertas._notificar` já usa (WhatsApp da empresa 1 + Telegram).
6. Enquanto `ia_pausada_ate > NOW()`, o gate no worker devolve antes do agente
   (mesmo lugar do detector). Expirou → IA volta sozinha; se o operador
   bloqueou o número (`whitelist_numero`), não volta.

**`recursion_limit` explícito.** Em `processor.py:~3085` (`invoke_config`),
`"recursion_limit": settings.agent_recursion_limit` (default 30; hoje é o 25
implícito). Capturar `langgraph.errors.GraphRecursionError` **antes** do `except`
genérico: `mark_failed` sem retry (o loop interno de tools é determinístico —
repetir paga de novo e falha de novo), nota interna na timeline, contador. Não
é anti-ping-pong; é anti-agente-girando-em-tool, e custa uma linha.

### Camada 3 — Humano

- Card na fila com selo "possível loop" e dois botões: **Retomar IA** (zera
  `ia_pausada_ate`) e **Bloquear número** (insere em `whitelist_numero`, que já
  existe). Ambos são endpoints de 1 UPDATE cada; permissão `atendimento.write`.
- Contador "IA pausada por loop (24h)" no relatório de produção
  (`scripts/producao_checks.py`) e no Dashboard — é o indicador que a Ligo
  recomenda acompanhar ("volume de mensagens de serviço", ver §6).

### Camada 4 — Teto de custo (segura se tudo acima falhar)

- `ia_budget.acao_estouro` default **`bloquear`** (fecha o M1 do red team). Hoje
  um loop atravessa o teto de gasto e só gera alerta.
- Teto **diário** por número: 60 respostas automáticas/dia/telefone
  (`rate_limit_bucket`, mesma infra do middleware admin, chave
  `wa:<empresa>:<phone>:dia`). O rate limit atual é por hora e por telefone —
  sem teto diário um loop "lento" (1 volta a cada 40 s) passa o dia inteiro dentro
  dos 120/h.

---

## 5. Custo de cada camada

| Camada | Código | Banco | Custo por mensagem | O que resolve |
|---|---|---|---|---|
| 1a marcador | ~40 linhas (wrapper + strip + 2 webhooks) + testes | — | zero (string) | **Nexus↔Nexus, eco, encaminhamento** — de graça |
| 1b duplicata | ~30 linhas | 1 SELECT indexado | ~1 ms | auto-resposta fixa de terceiros |
| 2 detector | ~150 linhas puras + 1 consulta + gate | mig 189 (2 colunas) | 1 SELECT (últimas 10 rows da thread) | bot externo "inteligente", agente preso |
| 2 recursion_limit | 5 linhas | — | zero | tool em círculo dentro de um turno |
| 3 humano | 2 endpoints + selo + 2 botões | — | — | decisão e desbloqueio |
| 4 teto | config + 1 bucket | reusa `rate_limit_bucket` | ~1 ms | última linha de defesa |

Tudo junto cabe em uma sprint curta; a camada 1a sozinha cabe em uma tarde e já
elimina o cenário mais provável hoje (o dono testando de um número Nexus para
outro).

---

## 6. O que NÃO fazer, e por quê

- **Marcador visível (`[BOT_MSG]`).** Todo cliente real leria a etiqueta; o
  modelo tenderia a copiá-la (ou a omiti-la, o que é pior: a defesa some sem
  aviso). O marcador é responsabilidade do código no cliente outbound, invisível,
  e nunca aparece no prompt.
- **LLM decidindo se é loop.** É não-determinístico, custa uma chamada por
  mensagem — e essa chamada é exatamente o que o loop explora. Toda decisão
  desta análise é uma comparação de timestamps e hashes.
- **Confiar em `pushName`/conta Business/`source`.** Bots rodam em número
  pessoal (o Nexus, inclusive); humanos usam Business. São dicas para o
  operador, não critério.
- **Responder ao bot pedindo para parar.** Cada saída é uma entrada para o outro
  lado. Durante a pausa a resposta é o silêncio.
- **Baixar o rate limit global.** 120/h por telefone é o que segura um cliente
  mandando 15 fotos de uma vez sem ser barrado; o freio certo é por
  comportamento (camada 2), não por volume bruto.
- **`recursion_limit` alto "para não quebrar".** Ele existe para quebrar. O
  agente do Nexus resolve um turno em poucos passos; 30 é folga, 1000 é
  cheque em branco.

---

## 7. Aberto para o dono decidir

1. **Tempo de pausa:** 6 h (proposto) ou até um operador retomar? Seis horas
   corrige sozinho o falso positivo raro; "até retomar" é mais seguro e mais
   trabalho.
2. **Avisar quem:** só o dono (como `ia_alertas`) ou também o resumo diário da
   empresa dona da conexão?
3. **Marcador em envio de menu/workflow/CSAT** também, ou só no agente IA? A
   proposta é em tudo que é automático — é o que o RFC 3834 chama de
   `auto-replied`.
4. **Teto diário de 60/número:** confortável para os clientes atuais (medir na
   1018: o cliente mais falante do mês)?

---

## 8. Fontes

- RFC 3834, *Recommendations for Automatic Responses to Electronic Mail* —
  marcar o automático, não responder ao automático, uma resposta por remetente
  por período: <https://www.mailertogo.com/rfc/3834>
- Ligo, *Evite loops entre bots no WhatsApp* — definição, causas, e o custo com
  a cobrança por mensagem de serviço a partir de 1º/10/2026:
  <https://ligo.cloud/blog/atendimento/loops-entre-bots-no-whatsapp/>
- Circuit breaker de auto-resposta em bot de WhatsApp (8 respostas por par
  conta/remetente em 10 min, eco ignorado antes de contar, falha do Redis pausa
  em vez de liberar): <https://github.com/max1029384756/wa-chatbot/pull/1>
- LangGraph, `GRAPH_RECURSION_LIMIT`:
  <https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT>
- Baileys não distingue conta Business de pessoal:
  <https://github.com/WhiskeySockets/Baileys/issues/2219>
- Campos do `messages.upsert` do Evolution (`pushName`, `source`,
  `messageTimestamp`):
  <https://evolutionapi-evolution-api-90.mintlify.app/events/webhooks>
- Meta, limites de mensagens e qualidade:
  <https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits>
- Caracteres invisíveis como vetor de injeção (por que o marcador nunca chega
  ao prompt): <https://originality.ai/blog/invisible-text-detector-remover>
- Custo interno já medido: `docs/CUSTO_E_CAPACIDADE.md` (R$0,035/msg Meta a
  partir de 1º/10/2026; ~US$0,0013 por turno de IA).

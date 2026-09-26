# ADR-008 — Resposta do dono pelo celular pausa a IA (Evolution, Z-API e Meta)

- **Status:** ACEITA (26/09/2026) — o dono aprovou as quatro decisões da §6 como propostas. PR A implementada (mig 205, PR #194); PR B (retorno por tempo) implementada.
- **Origem:** relatório `.planning/reports/20260926-agente-luis-analise-e-mercado-llm.md`
  (agente do Luís "entra por cima" das conversas que ele conduz pelo celular;
  pontuação competitiva 8,4/10).
- **Relacionados:** mig 200 (Coexistência da Meta, que já faz isto na API
  oficial), mig 198 (eco de saúde, único `fromMe` tratado hoje na Evolution),
  decisão "IA co-piloto, não handoff".

## 1. Contexto

O ChatNexus só pausa a IA quando o humano age **pelo painel** (Atender) ou,
na API oficial em modo Coexistência, quando a Meta manda o eco do aplicativo
(`smb_message_echoes`). Na conexão **Evolution**, que é a de todos os
clientes de hoje, a mensagem que o dono digita no celular chega ao webhook
com `key.fromMe = true` e é **descartada** (`evolution_webhook.py`, ramo
`evolution_webhook_skipped_fromMe`). Consequências medidas no Luís
(20/08–16/09/2026):

- o agente não sabe o que o dono já respondeu e recomeça a conversa
  ("Olá, tudo bem? Como posso ajudar?" no meio de um assunto em andamento);
- o agente responde em conversas que o dono está conduzindo, e quem está do
  outro lado lê as duas vozes como se fossem o Luís.

O mercado trata o caso: o agente de IA da Meta pausa a conversa quando o dono
responde manualmente; a Evolution tem `stopBotFromMe` nos robôs nativos; um
fork do Chatwoot registrou em 23/09/2026 a falha oposta (robô seguindo
respondendo junto com o atendente, 1.338 mensagens em 141 conversas em duas
semanas). Chatwoot e Chatvolt só documentam a pausa pelo painel.

## 2. Decisão

**Uma regra para todos os canais:** mensagem enviada pelo número da conexão
fora do ChatNexus (celular, WhatsApp Web ou Desktop do dono) é tratada como
**resposta humana**: entra na conversa, entra na memória do agente e **pausa
a IA naquela conversa**. A IA volta por "Devolver à IA" ou, opcionalmente,
depois de um tempo sem resposta do humano, configurável por conexão.

A implementação **espelha a Coexistência** (`shared/waba_coexistence.py::registrar_eco`),
que já tem o modelo pronto: dono sentinela do atendimento, linha de saída
com `origem_resposta` própria, rótulo "WhatsApp Business (celular)" na
timeline e o gate de handoff do worker que cala o agente.

Não é opção por empresa desligável no primeiro momento: **liga por padrão**
em toda conexão Evolution, como é na Coexistência. Um interruptor por conexão
existe apenas para o retorno automático por tempo.

## 3. Desenho

### 3.1 Sinal por canal

| Canal | Sinal | Como separar "celular" de "API" | Situação |
|---|---|---|---|
| Evolution | `messages.upsert` com `key.fromMe = true` | A Evolution v2 não reemite o que ela mesma enviou (conferido no dev em 21/09). O eco de saúde é reconhecido antes, pelo prefixo `ECO_PREFIXO` e pelo destinatário = próprio número. O campo `source` (android, ios, web, desktop) fica registrado no log para auditoria; **não** decide nada | Agora |
| Z-API | webhook "Ao receber" com a opção "notificar enviadas por mim" ligada na instância | `fromMe = true` e `fromApi = false` é o celular; `fromApi = true` é o que saiu pela API (inclusive o nosso envio) | Junto com o provedor Z-API (projeto próprio; o recurso é um dia dentro dele) |
| Meta Cloud API, número dedicado | não existe: o número sai do aplicativo | — | Nada a fazer; o painel já pausa |
| Meta Coexistência | `smb_message_echoes` | a Meta separa por desenho | Feito (mig 200) |

### 3.2 Fluxo na Evolution

No `evolution_webhook.py`, o ramo `fromMe` passa a ter três saídas, nesta ordem:

1. **Eco de saúde** (mig 198): como hoje, `registrar_eco_voltou`, sem enfileirar.
2. **Descartes**: destinatário em `@g.us`, `@broadcast`, `@newsletter`,
   `status@broadcast`; mensagem sem texto nem mídia reconhecível (reação,
   enquete, protocolo); conexão que não está `active`; número na lista de
   bloqueio (`whitelist_numero`) segue sem IA de qualquer jeito, mas a
   mensagem **entra** na timeline (é histórico do dono com aquele contato).
3. **Resposta humana pelo celular** → `shared/resposta_celular.py::registrar_resposta_celular(pool, conexao, evento)`:
   - `upsert_cliente(empresa, telefone_do_destinatario)` (respeita o nono dígito);
   - `open_or_attach_atendimento(..., iniciado_cliente=False, assigned_to_user_id=HUMANO_CELULAR)`;
     atendimento aberto **sem dono** → `claim_atendimento(HUMANO_CELULAR)`;
     com operador do painel → fica com o operador (não rouba);
   - `_persist_outbound_row(response=texto, user_id=USUARIO_CELULAR, origem_resposta=ORIGEM_CELULAR, provider_message_id=key.id, media_*)`,
     com `normalized_input = "manual:app:whatsapp"` (mesmo prefixo que a
     timeline já rotula como "WhatsApp Business (celular)"; o rótulo ganha a
     forma genérica "WhatsApp (celular)");
   - **memória do agente** (corrigido na implementação): a resposta do
     operador do painel **não** entrava no contexto do agente (o worker só
     monta a mensagem do cliente). O mecanismo adotado, para celular E painel:
     antes de chamar o modelo, o worker anexa ao texto do cliente o bloco
     `[A EQUIPE JÁ RESPONDEU ESTE CLIENTE desde a sua última mensagem …]` com
     até 5 respostas humanas (500 caracteres cada) dadas depois da última
     resposta da IA (`shared/resposta_celular.py::respostas_humanas_recentes`),
     depois dos guardrails, como o prefixo `[JÁ ENCAMINHADO AO SETOR]`;
   - `entrega_status`/ack: a Evolution manda `messages.update` para as
     mensagens do celular também; `registrar_ack` continua contando só como
     "saída funcionando" (não muda);
   - log `evolution_resposta_celular_registrada` com `conexao_id`,
     `atendimento_id`, `ia_pausada`, `source`.
4. Mídia do celular (simplificado na implementação): entra como texto
   indicativo com a legenda, por exemplo `[foto enviada pelo celular] segue`
   ou `[documento enviado pelo celular: proposta.pdf]`. O arquivo não é
   baixado: a IA não responde a essa mensagem, e baixar custaria banda e
   armazenamento sem uso.

**Idempotência:** o `key.id` da Evolution vai em `message_id` da linha de
saída; repetição do webhook (reentrega) faz `INSERT … ON CONFLICT DO NOTHING`
por `(conexao_id, message_id)` onde a linha for de origem celular. Hoje não há
índice único em `message_queue.message_id` (multi-mídia e debounce); o ADR
propõe um índice **parcial** `WHERE origem_resposta = 'celular'`.

### 3.3 Pausa e retorno da IA

- **Pausa**: é o estado que já existe: `atendimento.status = em_andamento` +
  `assigned_to_user_id = HUMANO_CELULAR` (mesmo mecanismo do `HUMANO_APP` da
  Coexistência). O gate de handoff do worker (`processor.py`, "Operador humano
  → pula a invocação") cala o agente sem código novo; o worker grava
  `[handoff humano — operador respondendo]` na linha do cliente, que o painel
  já esconde.
- **Volta manual**: "Devolver à IA" (`POST /api/atendimentos/{id}/devolver-ia`)
  limpa o dono e volta a `aguardando` — já funciona para o `HUMANO_APP`.
- **Volta por tempo (opcional, por conexão)**: `conexao.celular_retorno_ia_minutos`
  (NULL = só manual). Um laço no worker, `_retorno_ia_celular_loop`, a cada
  60 s: atendimentos com dono `HUMANO_CELULAR` cuja **última mensagem do
  celular** é mais antiga que o prazo **e** que receberam mensagem do cliente
  depois dela → devolve à IA + reprocessa a última mensagem do cliente. Sem
  mensagem nova do cliente, nada a fazer: o atendimento espera. Log
  `resposta_celular_ia_retornou`. Padrão decidido pelo dono: NULL (só manual).
  *Implementado (PR B):* a devolução não usa `devolver_atendimento_para_ia`
  (que devolve qualquer dono) e sim um UPDATE condicional a o dono AINDA ser
  `HUMANO_CELULAR`, na mesma transação do reenfileiramento: só uma réplica do
  worker ganha a linha, e o operador que assumiu pelo painel entre a leitura e
  a devolução fica com a conversa. O reenfileiramento é o mesmo reset do
  "Reprocessar com IA", restrito à linha com marcador de handoff.
- **Cliente escreve enquanto pausado**: a mensagem entra na fila e recebe o
  marcador de handoff, como hoje quando um operador está atendendo. O chip
  "Em atendimento · WhatsApp (celular)" no cabeçalho da conversa avisa o
  operador do painel.

### 3.4 Dados (mig 205)

```sql
ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS celular_retorno_ia_minutos INTEGER
        CHECK (celular_retorno_ia_minutos IS NULL OR celular_retorno_ia_minutos BETWEEN 5 AND 10080);
-- origem_resposta ganha o valor 'celular' (CHECK, se houver; hoje é texto livre)
CREATE UNIQUE INDEX IF NOT EXISTS uq_message_queue_celular
    ON message_queue (conexao_id, message_id)
    WHERE origem_resposta = 'celular';
```

Sem coluna nova para ligar/desligar: liga por padrão. Se um cliente pedir para
desligar, entra como coluna booleana em PR própria.

`HUMANO_CELULAR = "whatsapp_celular"` e `USUARIO_CELULAR` seguem o padrão dos
sentinelas da Coexistência (`shared/waba_coexistence.py`). O `HUMANO_APP` da
Coexistência **permanece**: são canais diferentes com o mesmo comportamento;
a timeline e o chip tratam os dois com o rótulo "WhatsApp (celular)".

### 3.5 Painel

- Timeline: bolha de saída com rótulo "WhatsApp (celular)" (`timeline.ts`,
  `ROTULO_CELULAR` passa a cobrir `manual:app:whatsapp` além de
  `manual:app:whatsapp_business`).
- Cabeçalho da conversa: chip de situação "Em atendimento · celular" quando o
  dono é `HUMANO_CELULAR` ou `HUMANO_APP`; botão "Devolver à IA" já existe.
- Página da conexão Evolution (`/connections/[id]`): bloco "Resposta pelo
  celular" com o texto "Quando você responder pelo celular, a IA para naquela
  conversa" e o campo "A IA volta sozinha depois de: [nunca | 30 min | 1 h |
  2 h | 4 h | 24 h]".
- App Android: `Bolha.kt::MARCADORES_INTERNOS` já trata `manual:app:`; conferir
  o rótulo.

### 3.6 Z-API (quando o provedor existir)

- Provedor `zapi` (novo `conexao.provider`; CHECK da mig 153 precisa ampliar):
  cliente de envio, webhook `/webhook/zapi`, QR, saúde. Projeto próprio, ADR
  separada.
- Neste ADR só fica o contrato: o webhook de recebimento com `fromMe = true`
  e `fromApi = false` chama a mesma `registrar_resposta_celular`. O envio pela
  API volta com `fromApi = true` e é ignorado (o ChatNexus já gravou a linha
  ao enviar). A instância precisa de "notificar enviadas por mim" ligado; o
  onboarding da conexão liga isso pela API da Z-API e o monitor de saúde
  confere.

### 3.7 O que NÃO muda

- Mensagem enviada **pelo painel** não volta pelo webhook (Evolution não
  reemite) e já pausa a IA pelo claim do operador.
- Lista de bloqueio (`whitelist_numero`): contato bloqueado continua sem IA;
  a resposta do dono para ele entra na timeline como histórico.
- Coexistência da Meta: intacta.
- Guarda robô × robô (branch `feat/guarda-conversa-automatica`): independente.

## 4. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Eco de saúde ou mensagem enviada pelo próprio ChatNexus contada como "celular" e pausando a IA | Ordem do ramo `fromMe`: eco primeiro (prefixo + destinatário); Evolution não reemite envios da API (conferido no dev em 21/09; **reconferir na fumaça** com `source`) |
| WhatsApp Web do dono | É o dono: conta como celular (é o desejado) |
| Dono responde num grupo | Descarte por `@g.us` |
| Dono manda mensagem para um número que nunca escreveu (conversa nova) | `open_or_attach` cria o atendimento `em_andamento` com dono celular; a IA não entra até "Devolver" ou até o tempo. Igual à Coexistência |
| Volume: conexões pessoais como a da VSA (2.973 contatos) geram muitas linhas de saída | Linha de saída é barata; mídia vai ao bucket com a retenção da empresa; sem chamada de IA |
| Retorno por tempo reprocessa mensagem antiga e o agente responde tarde | Reprocessa só a **última** mensagem do cliente e só se ela for posterior à última do celular; teto de idade de 24 h para reprocessar |
| Cliente com muitos operadores no painel: dono responde pelo celular numa conversa que um operador já assumiu | Não rouba: fica com o operador; a mensagem entra na timeline |
| Z-API sem "notificar enviadas por mim" | O onboarding liga; o monitor de saúde alerta se a opção estiver desligada |

## 5. Plano de entrega

1. **PR A — Evolution (backend + timeline)**: `shared/resposta_celular.py`,
   ramo `fromMe` do webhook, mig 205, `HUMANO_CELULAR` no gate e nos rótulos,
   `ROTULO_CELULAR`, chip do cabeçalho. Testes: unit (`tests/unit/test_resposta_celular.py`:
   descartes, eco não vira resposta, texto e mídia, não rouba operador,
   idempotência) e E2E (`tests/integration/test_resposta_celular_endpoints.py`:
   webhook Evolution com `fromMe` no dev → linha de saída, atendimento com
   dono celular, mensagem do cliente recebe marcador de handoff, "Devolver à
   IA" reativa). Fumaça no dev: enviar do celular de teste pela instância do
   dev e conferir timeline + `worker_skipped_agent_handoff`. Foto claro/escuro.
   Esforço: 2 a 3 dias.
2. **PR B — retorno por tempo**: coluna `celular_retorno_ia_minutos`, laço no
   worker, bloco na página da conexão. Testes unit (regra pura do prazo) +
   E2E (job em processo). Esforço: 1 dia.
3. **PR C — Z-API**: dentro do projeto do provedor (ADR própria).
4. **Docs**: `CLAUDE.md` (highlight mig 205), `docs/EVOLUTION.md` (seção
   "Resposta pelo celular"), `docs/WHATSAPP_COEXISTENCE.md` (nota de que a
   regra vale nos dois canais).

Ordem de merge: A → B. Cada uma validada no dev e mostrada ao dono antes do
merge (contrato de entrega).

## 6. Decisões do dono (aprovadas em 26/09/2026, todas como propostas)

1. Padrão do retorno automático: **nunca** (proposta, igual à Meta) ou um
   tempo (ex.: 2 h)?
2. A mensagem do celular entra na memória do agente como fala do assistente
   (proposta: sim, como na Coexistência)?
3. Ligar por padrão em toda conexão Evolution (proposta: sim) ou exigir que
   cada cliente ligue?
4. Para o Luís especificamente: com o recurso ligado, família e amigos que
   ele responde pelo celular deixam de receber a IA naquela conversa. A lista
   de bloqueio continua recomendada para quem nunca deve ter IA.

## 7. Como medir o sucesso (30 dias após o deploy no Luís)

- Zero respostas do agente em conversas com mensagem do celular nos 60 min
  anteriores (hoje: acontece; medir com `message_queue` por atendimento).
- Queda dos "recomeços" (abertura repetida com < 30 min de conversa: 19 no
  período analisado).
- Nenhum falso positivo de pausa por eco ou por mensagem da API (log
  `evolution_resposta_celular_registrada` com `source` para auditar).

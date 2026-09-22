# WhatsApp Coexistence no ChatNexus

> Mig `200_waba_coexistence.sql` · branch `feat/waba-coexistence` · 22/09/2026.
> Requisitos da Meta conferidos na documentação oficial em 22/09/2026 (Graph
> API **v25.0**): [Onboard WhatsApp Business app users][onboarding],
> [Embedded Signup — implementation][impl], [smb_message_echoes][echoes].
> O que não está confirmado lá está marcado como **a validar no teste real**.

[onboarding]: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users
[impl]: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/implementation
[echoes]: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/reference/smb_message_echoes

## 1. O que é Coexistence

O cliente do ChatNexus continua usando o **WhatsApp Business no celular** e, ao
mesmo tempo, o ChatNexus recebe e responde pela **Cloud API** oficial, no mesmo
número. O que o operador manda do celular chega ao ChatNexus como **eco** e vai
para o histórico da conversa, e a IA **não responde** por cima.

No ChatNexus, Coexistence **não é um provider novo**: é um modo da conexão
`provider = 'waba'`.

| `conexao.waba_mode` | O que é |
|---|---|
| `cloud_api` (padrão) | Número dedicado à API oficial. O fluxo de sempre. |
| `coexistence` | WhatsApp Business no celular + ChatNexus no mesmo número. |

Evolution é sempre `cloud_api`: um CHECK no banco impede outro valor
(`conexao_waba_mode_provider_check`).

```
WhatsApp Business (celular) ──► Meta ──► Cloud API ──► POST /webhook/waba (HMAC)
                                                          │
                          ┌───────────────────────────────┼──────────────────────────────┐
                    field=messages              field=smb_message_echoes         history / smb_app_state_sync
                    (cliente escreveu)          (empresa respondeu no celular)   / account_update
                          │                               │                              │
              cliente + atendimento + fila      linha de SAÍDA `done` na timeline   histórico, contatos,
                          │                     + IA pausada naquela conversa       desconexão
                    worker → IA/menu/workflow
                          │
                ChatNexus ──► Cloud API ──► Cliente
```

## 2. Pré-requisitos

Confirmados na documentação da Meta:

- O ChatNexus precisa ser **Tech Provider** (ou Solution Partner) e usar o
  **Embedded Signup**.
- O número precisa estar no **WhatsApp Business app versão 2.24.17 ou mais
  nova**.
- Depois do onboarding, o ChatNexus tem **24 horas** para pedir a
  sincronização de contatos e de histórico (`smb_app_data`). Depois disso é
  preciso desconectar e conectar de novo.
- O histórico cobre as mensagens dos **180 dias** antes do onboarding. Mídia do
  histórico só vem para mensagens de até **14 dias**, e em webhooks separados.

Do lado do ChatNexus:

- Plano com o recurso `waba` (Pro ou Enterprise; mig 191).
- Variáveis `META_APP_ID`, `META_APP_SECRET`, `META_CONFIG_ID` e
  `WABA_WEBHOOK_VERIFY_TOKEN` preenchidas. Sem as três primeiras,
  `waba_enabled` é falso e as rotas de conexão respondem 503. Sem o secret, o
  webhook rejeita tudo.

## 3. Configuração Meta

Parte comum com a Cloud API: siga `docs/WABA_SETUP.md` (app, domínios,
Embedded Signup, webhook). O que muda para Coexistence:

1. Na **configuração do Embedded Signup**, habilitar o onboarding de números do
   WhatsApp Business app. O botão do ChatNexus manda
   `extras.featureType = "whatsapp_business_app_onboarding"` e
   `sessionInfoVersion = "3"` **só** no modo Coexistence. **A validar no teste
   real**: a página atual da Meta não traz o trecho literal do `featureType` no
   texto extraído.
2. No **webhook** do app, assinar os campos:
   - `messages` e `message_template_status_update` (já usados pela Cloud API);
   - `smb_message_echoes`: o que a empresa enviou pelo celular;
   - `history`: o histórico de conversas;
   - `smb_app_state_sync`: contatos do celular;
   - `account_update`: desconexão (`PARTNER_REMOVED`).
3. A URL do webhook continua `https://<api>/webhook/waba`, com HMAC
   `X-Hub-Signature-256` obrigatório.

## 4. Configuração ChatNexus

Nenhuma variável nova. As mesmas da Cloud API:

```bash
META_APP_ID=********
META_APP_SECRET=********
META_CONFIG_ID=********
WABA_WEBHOOK_VERIFY_TOKEN=********
WABA_GRAPH_API_VERSION=v25.0
```

O banco precisa da mig 200 (a api aplica ao subir). Ela acrescenta
`conexao.waba_mode` e a tabela `waba_wamid_processado`, o livro de
idempotência do webhook.

## 5. Como conectar

1. **Conexões → Nova conexão → WhatsApp Oficial**.
2. Escolher **WhatsApp Business + ChatNexus**: "Continue usando o WhatsApp
   Business no celular enquanto o ChatNexus processa as conversas".
3. **Conectar com Meta**. No popup da Meta, escolher o número do WhatsApp
   Business e confirmar no celular.
4. Ao voltar, o ChatNexus faz o seguinte:
   - troca o código pelo token, que fica cifrado em `credentials_encrypted`;
   - descobre o número por `GET /{waba}/phone_numbers`, porque o evento
     `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` traz só o `waba_id`. Mais de um
     número na WABA gera 409 com o pedido de conectar de novo escolhendo um;
   - **não** chama `/register` (a Meta manda pular);
   - assina o webhook com `POST /{waba}/subscribed_apps`;
   - pede `POST /{phone}/smb_app_data` com `sync_type=smb_app_state_sync` e
     depois `sync_type=history`.
5. Se a sincronização falhar, a conexão fica **Conectada** com o aviso
   "Sincronização de contatos e histórico pendente". Na página da conexão, o
   botão **Sincronizar contatos e histórico** repete o pedido
   (`POST /api/conexoes/{id}/waba/sincronizar`) dentro das 24 horas.

Código: `integrations/waba/oauth.py` (`list_phone_numbers`,
`sincronizar_smb`), `server/routes/conexao.py` (`_create_waba_conexao`,
`waba_embedded_signup`, `waba_sincronizar`) e
`frontend/src/app/connections/waba-oauth-button.tsx`.

## 6. Como testar

**Automático**:

```bash
# unit (parsers com os payloads literais da Meta, eco, rota, onboarding)
uv run pytest tests/unit/test_waba_coexistence.py tests/unit/test_waba_embedded_signup_smoke.py tests/unit/test_waba_webhook.py -q

# E2E no dev: webhook assinado → banco → worker
DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
uv run pytest tests/integration/test_waba_coexistence_endpoints.py -v
```

A E2E assina com o `META_APP_SECRET` do dev (ambiente ou `.env.local`) e cobre
schema, abertura de atendimento, eco sem IA, IA pausada até "Devolver à IA",
eco repetido, HMAC inválido, tenant, histórico e `PARTNER_REMOVED`.

**Teste real** (dev primeiro, com um número de teste, não o pessoal):

1. Conectar o número em modo Coexistence.
2. Do celular de um cliente, mandar "Olá". A IA responde pela Cloud API.
3. O operador responde **pelo WhatsApp Business do celular**.
4. Conferir no Inbox que a resposta aparece como **WhatsApp Business
   (celular)** e que a conversa ficou "Em atendimento".
5. O cliente manda outra mensagem. A IA não responde (marcador de handoff na
   linha).
6. Clicar **Devolver à IA**. A próxima mensagem do cliente volta a ser
   respondida pela IA.
7. Guardar prints e logs **sem token** (`docs/META_APP_REVIEW.md`).

## 7. Webhooks

Mesmo endpoint e mesma regra de HMAC da Cloud API
(`server/routes/webhook_waba.py`). Os parsers são puros, em
`integrations/waba/webhook.py`, e o tratamento está em
`shared/waba_coexistence.py`.

| Campo | O que o ChatNexus faz | Log |
|---|---|---|
| `messages` | `upsert_cliente` (com o nome do perfil) + `open_or_attach_atendimento` + fila do worker. Antes da mig 200 a mensagem WABA entrava sem atendimento e não aparecia no Inbox | `webhook_waba_received` |
| `smb_message_echoes` | Linha de saída `done` + IA pausada (seção 8) | `waba_coexistence_echo_received` |
| `history` | Só texto, num atendimento **resolvido** por cliente, com a data original. Não abre conversa na fila, não gera push nem "não lida" e não entra na régua de atividade da conexão. Erro `2593109` (histórico recusado no app) vira aviso na conexão | `waba_coexistence_history_received` |
| `smb_app_state_sync` | Contato `add` → `upsert_cliente(nome)`. Não sobrescreve um nome já preenchido | `waba_coexistence_state_sync` |
| `account_update` | `PARTNER_REMOVED` → conexão `disconnected` + health-check falho. O monitor e o banner de conexão já avisam | `waba_coexistence_account_update` |

Regras que valem para todos os campos:

- **Tenant** sempre pelo `phone_number_id` do payload (ou `entry.id` da WABA no
  `account_update`) → conexão → empresa → `set_request_context`. Nenhum
  `empresa_id` vem da Meta. `phone_number_id` desconhecido é ignorado com 200.
- **Idempotência** pelo `wamid` em `waba_wamid_processado`. A entrega reivindica
  o wamid antes de processar e libera se falhar. Falha interna devolve **503**
  para a Meta reentregar, e o que já entrou é pulado. No histórico, a
  reivindicação acontece na mesma transação que grava as linhas.
- **Nunca** vão para log: `access_token`, `app_secret`, `authorization_code`.
  Conteúdo das mensagens também não.

## 8. Echo do operador

Quando o operador responde pelo celular:

1. A linha entra em `message_queue` com `status='done'`, `incoming_message=''`,
   `response=<texto>`, `normalized_input='manual:app:whatsapp_business'`,
   `origem_resposta='whatsapp_business_app'` e `message_id=<wamid>`. Usa o
   mesmo `_persist_outbound_row` do envio pelo painel.
2. **Não passa por `enqueue_or_buffer`.** O `claim_next` do worker só pega
   `queued`, então é o backend que garante que a IA não roda sobre a mensagem
   do operador, não o prompt nem a tela.
3. **A IA pausa naquela conversa** (decisão do dono, 22/09). O atendimento
   fica `em_andamento` com o dono sentinela `whatsapp_business_app`, pelo mesmo
   `claim_atendimento` do botão "Atender". O gate de handoff do worker
   (`worker/processor.py`, "atendimento em andamento com dono") cala o agente.
   Não existe regra nova de retomada: **"Devolver à IA"** (já existente)
   devolve a conversa.
   - Se a conversa já está com um operador do painel, o eco **não** tira dele.
   - Se não há conversa aberta, ela nasce já com o dono "celular".
4. Na timeline, o prefixo `manual:app:` aparece como **WhatsApp Business
   (celular)**, e no agrupamento por responsável o dono sentinela tem o mesmo
   nome.
5. Mídia enviada pelo celular (v1): grava a legenda e
   `[imagem/vídeo/documento enviado pelo celular]`. Os bytes ficam para depois.
   `revoke` e `edit` só geram log.

As mensagens do app **não abrem nem estendem** a janela de 24 horas da Cloud
API (Meta).

## 9. Limitações

Da Meta (documentação de 22/09/2026):

- Vazão de **20 mensagens por segundo** por número em Coexistence.
- Sem suporte a grupos, listas de transmissão, mensagens temporárias,
  visualização única, localização ao vivo e chamadas.
- Sincronização de contatos e histórico só em até 24 horas do onboarding.

Do ChatNexus (v1):

- Histórico importado só como **texto**: mídia e mensagens sem texto ficam de
  fora. O histórico não entra na memória do agente (checkpointer).
- A timeline ordena por `id`. Lotes do histórico que chegam em fases diferentes
  (a Meta manda primeiro os mais recentes) podem aparecer fora de ordem dentro
  do atendimento importado.
- Eco de mídia sem o arquivo. `revoke` e `edit` não alteram a bolha.
- Coexistence com mais de um número na mesma WABA: o onboarding pede para
  conectar de novo escolhendo um número (409).
- O app Android mostra a resposta do celular como as outras respostas manuais
  (ele não rotula por prefixo).
- Não há WhatsApp Coexistence para Evolution: é recurso da API oficial.

## 10. Troubleshooting

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Webhook responde `rejected_no_secret` | `META_APP_SECRET` vazio | Preencher e reiniciar a api |
| `rejected` | Assinatura não bate (secret de outro app) | Conferir o App Secret do app que manda o webhook |
| Resposta do celular não aparece | Campo `smb_message_echoes` não assinado, ou `phone_number_id` sem conexão ativa | Assinar o campo; procurar `waba_webhook_no_conexao` no log |
| Popup termina e nada acontece | Listener não recebeu `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` | Conferir no console do navegador o evento `WA_EMBEDDED_SIGNUP`; conferir se a configuração do Embedded Signup tem o onboarding do Business app habilitado |
| 409 "Não foi possível identificar o número" | A WABA tem mais de um número | Conectar de novo escolhendo um único número |
| Aviso "Sincronização … pendente" | `smb_app_data` recusado | Botão **Sincronizar contatos e histórico** (em até 24 horas); log `waba_coexistence_sync_failed` traz o status da Meta |
| "O histórico de conversas não foi compartilhado" | Erro `2593109`: a empresa recusou no app | Nada a fazer no ChatNexus; o histórico não vem |
| Conexão ficou **Desconectado no WhatsApp Business** | `account_update PARTNER_REMOVED` (ex.: celular muito tempo sem uso) | Conectar de novo pelo Embedded Signup |
| IA não volta a responder | O atendimento continua com o dono "celular" | **Devolver à IA** na conversa |
| Mensagem duplicada | Não deveria ocorrer: o wamid é deduplicado | Procurar `waba_webhook_duplicado`; conferir `waba_wamid_processado` |

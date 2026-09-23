# Meta App Review — checklist e evidências do ChatNexus

> Preparação para a aprovação do App da Meta (Cloud API + Coexistence).
> Técnica: documentação oficial da Meta (Graph API **v25.0**, conferida em
> 22/09/2026). Prática de aprovação: material da comunidade ZDG
> (<https://comunidade.zdg.com.br/geral/meta-whatsapp-meta/>), que **não**
> substitui a Meta.
>
> **Funcionar tecnicamente não é o mesmo que ter o App aprovado.** São duas
> etapas. Este documento cobre a segunda e aponta o que da primeira ela exige.

## ⚠️ Regra de segredos

Nunca colocar em GitHub, README, prints, screencasts, logs ou documentação:

```text
META_APP_SECRET
ACCESS_TOKEN (token de negócio / System User)
SYSTEM_USER_TOKEN
CLIENT_SECRET
WEBHOOK_SECRET / WABA_WEBHOOK_VERIFY_TOKEN
```

Em vídeo ou print, mostrar como `********` ou borrar. Os campos abaixo são
preenchidos no **painel da Meta**. Aqui ficam só os identificadores que não
são segredo, e só quando existirem.

## App

| Item | Valor | Onde conferir |
|---|---|---|
| App ID | `1370880258203802` ("Chat Nexus") | Meta for Developers → App → Configurações básicas |
| Business ID | _preencher_ | Business Manager → Informações da empresa |
| WABA ID | _preencher_ (a de teste) | WhatsApp Manager |
| Configuration ID (Embedded Signup) | `1063505079636299` ("ChatNexus": token do usuário do sistema, nunca expira) | Login do Facebook para Empresas → Configurações |
| App Secret | `********` (só no env) | nunca no documento |
| Tipo do App | Business, com o produto WhatsApp | Painel do App |
| Tech Provider | _confirmar_ | exigido para Coexistence (Meta) |

## Domínios

| Item | Valor |
|---|---|
| App Domain | _preencher_ (domínio do painel, ex.: `vsanexus.com`) |
| Privacy Policy | _URL pública_ |
| Terms of Service | _URL pública_ |
| Allowed domains do JS SDK | domínio do painel (o FB SDK recusa outros: "tela branca", ver `docs/WABA_SETUP.md`) |

## Permissões

Princípio: **menor quantidade + justificativa clara + uso comprovável**.

| Permissão | Pedir? | Chamadas reais do ChatNexus que a usam |
|---|---|---|
| `whatsapp_business_messaging` | **Sim** | `POST /{phone-number-id}/messages`: resposta da IA e do operador (`integrations/waba/client.py::WabaClient.send_message`), indicador de digitação (`send_typing`), modelo de mensagem aprovado (`templates.py::send_template_message`). `GET /{media-id}`: mídia recebida do cliente (`client.py::download_media`) |
| `whatsapp_business_management` | **Sim** | `POST /{waba-id}/subscribed_apps`: assina o webhook no onboarding (`oauth.py::subscribe_webhook`). `GET /{phone-number-id}`: dados do número no onboarding (`fetch_phone_details`) e sonda de saúde da conexão, 1 vez por hora (`saude_conexoes.py::_sondar_waba`). `GET /{waba-id}/phone_numbers`: número do onboarding Coexistence (`list_phone_numbers`). `POST /{phone-number-id}/register`: só Cloud API (`register_phone`). `POST /{phone-number-id}/smb_app_data`: contatos e histórico no Coexistence (`sincronizar_smb`). `GET/POST/DELETE /{waba-id}/message_templates` e `GET /{template-id}`: modelos de mensagem (`templates.py`) |
| `business_management` | **Proposta: não pedir** (a configuração "ChatNexus" de 23/09 veio com ela listada — conferir se dá para tirar sem quebrar o cadastro) | Usada só pelo fluxo OAuth **legado** (`GET /me/businesses` em `oauth.py::list_waba_accounts`, rotas `/waba/oauth/*`), que não é o caminho oficial (Embedded Signup). Confirmar no painel da configuração do Embedded Signup se ela aparece como exigida. Se não aparecer, tirar do pedido de revisão |

Pendências para conferir no painel (não dá para ver pelo código):

- quais estão em **Standard Access** × **Advanced Access**;
- quais pedem App Review para uso com empresas de terceiros (os clientes do
  ChatNexus);
- requisitos específicos por permissão exibidos na tela de revisão.

### Justificativas (texto para o formulário)

Cada justificativa corresponde às chamadas da tabela acima. Ajustar ao que o
painel pedir, sem generalizar.

**whatsapp_business_messaging**: "O ChatNexus é uma plataforma de atendimento
pelo WhatsApp. Quando o cliente final escreve para o número da empresa
conectada, o ChatNexus recebe a mensagem pelo webhook e responde, pelo agente
de IA ou pelo operador humano no painel, com `POST /{phone-number-id}/messages`.
Também baixa a mídia que o cliente envia (`GET /{media-id}`) para que o
operador e o agente possam lê-la, e envia modelos de mensagem aprovados quando
a janela de 24 horas está fechada."

**whatsapp_business_management**: "Durante a conexão do número pelo Embedded
Signup, o ChatNexus assina o app nos webhooks da WABA
(`POST /{waba-id}/subscribed_apps`), lê os dados do número
(`GET /{phone-number-id}`, `GET /{waba-id}/phone_numbers`) e, no modo
Coexistence, pede a sincronização de contatos e histórico do WhatsApp Business
app (`POST /{phone-number-id}/smb_app_data`). Depois, gerencia os modelos de
mensagem da WABA (criar, consultar status, excluir em
`/{waba-id}/message_templates`) e verifica periodicamente se o número continua
respondendo (`GET /{phone-number-id}`)."

## Embedded Signup

| Modo | Como o ChatNexus chama | Status |
|---|---|---|
| Cloud API | `FB.login({config_id, response_type:'code', override_default_response_type:true, extras:{setup:{}, sessionInfoVersion:'3'}})` → evento `FINISH` com `waba_id` + `phone_number_id` → `POST /api/conexoes/waba/embedded-signup` → troca do código (30 s) → `register` → `subscribed_apps` | Código pronto; **teste real pendente** |
| Coexistence | Igual, com `extras.featureType:'whatsapp_business_app_onboarding'` → evento `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` só com `waba_id` → `phone_numbers` → **sem** `register` → `subscribed_apps` → `smb_app_data` (contatos e histórico) | Código pronto; **teste real pendente**; `featureType` a validar |

## Webhook

| Item | Valor |
|---|---|
| URL | `https://<api>/webhook/waba` (a API, não o painel) |
| Verify Token | `********` (env `WABA_WEBHOOK_VERIFY_TOKEN`) |
| Assinatura | `X-Hub-Signature-256` obrigatória; sem o secret o endpoint rejeita tudo |
| Campos assinados | `messages`, `message_template_status_update`, `smb_message_echoes`, `history`, `smb_app_state_sync`, `account_update` |

## Evidências

Evidência = funcionalidade real do ChatNexus usada num ambiente de teste. **Não
criar chamadas artificiais só para a revisão.** Se a Meta pedir uma operação que
o ChatNexus não faz, implementar a funcionalidade ou registrar a limitação aqui.
Nunca simular.

| Permissão | Como gerar (uso real) | Status |
|---|---|---|
| Messaging | Cliente de teste escreve → IA responde (`POST /messages`); operador responde pelo painel; enviar um modelo aprovado | NOK: App ainda não configurado |
| Management | Conectar o número de teste pelo Embedded Signup (`subscribed_apps`, `phone_numbers`, `smb_app_data`); criar e sincronizar um modelo de mensagem; a sonda de saúde roda sozinha a cada hora | NOK: App ainda não configurado |

"Ligações de APIs exigidas" no painel da Meta precisa virar **Concluído** antes
de enviar a revisão (ZDG).

O painel auxiliar de geração de evidências da ZDG **não** é incorporado ao
ChatNexus. Se for usado, é só como ferramenta externa.

### Ambiente de teste

```
Meta App ─► Business de teste ─► WABA de teste ─► número de teste ─► ChatNexus (dev)
```

O número pessoal não deve ser o primeiro nem o único ambiente de teste. Ordem de
validação: Cloud API → Embedded Signup → Coexistence → Webhook → Echo →
Workflow/IA.

## Screencast

Gravar no dev, com um número de teste. **Tokens e secrets nunca aparecem na
tela**: o painel não os mostra, e o terminal não deve estar em cena.

**Vídeo 1: Embedded Signup (Coexistence)**
ChatNexus → Conexões → Nova conexão → WhatsApp Oficial → "WhatsApp Business +
ChatNexus" → Conectar com Meta → popup oficial da Meta (seleção da empresa e do
número, confirmação no app) → volta ao ChatNexus → conexão **Conectada** com
"WhatsApp Oficial · Coexistência" → página da conexão com o modo.

**Vídeo 2: Messaging**
Celular do cliente manda mensagem → aparece no Inbox do ChatNexus → IA/fluxo
responde → a resposta chega no celular do cliente. Deixar claro que o canal é a
WhatsApp Cloud API (página da conexão: "WhatsApp Oficial (Meta)").

**Vídeo 3: Coexistence**
Operador responde pelo **WhatsApp Business no celular** → a mensagem aparece no
Inbox como **WhatsApp Business (celular)** e a conversa fica "Em atendimento" →
o cliente manda outra → **a IA não responde** → "Devolver à IA" → a IA volta.
Esse vídeo mostra a principal característica do Coexistence.

## Checklist de prontidão

```text
[ ] App publicado
[ ] Business verificado
[ ] Privacy Policy configurada
[ ] Terms configurado
[ ] App Domain configurado
[ ] Webhook funcionando (verificado + campos assinados)
[ ] WABA funcionando
[ ] Cloud API funcionando
[ ] Embedded Signup funcionando
[ ] Coexistence funcionando
[ ] Messaging funcionando
[ ] Management funcionando
[ ] chamadas reais registradas ("Ligações de APIs exigidas" = Concluído)
[ ] screencast preparado (3 vídeos, sem segredos)
```

## Meta App Review Readiness

Estado em 22/09/2026, depois da implementação (branch `feat/waba-coexistence`):

```text
App:              NOK: recriar/configurar no Meta for Developers (as variáveis
                  META_APP_ID/SECRET/CONFIG_ID estão vazias no dev e em produção)
Business:         a confirmar: verificação do Business Manager
WABA:             NOK: WABA e número de teste a criar
Embedded Signup:  código pronto (Cloud API e Coexistence); teste real pendente
Coexistence:      código pronto e coberto por testes automáticos (unit + E2E no
                  dev com webhook assinado); teste real com a Meta pendente

Permissões:
- whatsapp_business_messaging:  pedir; uso real mapeado
- whatsapp_business_management: pedir; uso real mapeado
- business_management:          proposta de NÃO pedir (só OAuth legado)

Evidências:
- Messaging:  NOK (depende do App + número de teste)
- Management: NOK (depende do App + número de teste)

Screencast:
- Onboarding:  NOK
- Messaging:   NOK
- Coexistence: NOK

Pendências:
1. Dono configura o App da Meta (Tech Provider, domínio, privacidade, termos,
   Embedded Signup com Coexistence, webhook apontando para a API do dev).
2. Teste real no dev (roteiro em docs/WHATSAPP_COEXISTENCE.md, seção 6);
   validar o `featureType` e a troca do código com `redirect_uri`.
3. Gerar as chamadas reais e conferir "Ligações de APIs exigidas".
4. Gravar os 3 vídeos.
5. Decidir sobre `business_management` com o painel aberto.
6. Publicar o App e enviar a revisão.
```

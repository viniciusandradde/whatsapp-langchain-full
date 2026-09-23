# WABA — Setup do App Meta + Conexão WhatsApp Oficial

Guia passo-a-passo pra criar o app Meta, configurar o **Embedded Signup** e
conectar um número WhatsApp oficial ao Nexus via o botão "Conectar com Meta".

Método usado: **Embedded Signup via Facebook JS SDK** (igual ZigChat) — o popup
oficial da Meta retorna `waba_id` + `phone_number_id` e o backend cria a conexão.

> **WABA é o provider PRIMARY** desde 2026 — é o caminho recomendado para
> qualquer número WhatsApp oficial. Para o provider não-oficial (Baileys) veja
> [docs/EVOLUTION.md](EVOLUTION.md).

> Pré-requisito de negócio: o número WhatsApp que você vai conectar **não pode**
> estar registrado em outro app/WABA ao mesmo tempo. Se já estiver (ex: no app
> do ZigChat), migre o número pro novo app OU use um número novo.

---

## Visão geral do fluxo

```
1. Meta for Developers → criar App (tipo Business)
2. Adicionar produto "WhatsApp" + configurar Embedded Signup → gera config_id
3. Pegar App ID + App Secret (Settings → Basic)
4. Cadastrar domínios (chat/api.vsanexus.com) no app + FB Login
5. Configurar webhook (api.vsanexus.com/webhook/waba) + verify token
6. Setar envs no Dokploy + redeploy
7. UI → Conectar com Meta → popup → seleciona número → conexão "Conectada"
8. Validar: mandar msg do número → chega no /atendimento
```

---

## Parte 1 — Criar o App no Meta for Developers

1. Acesse <https://developers.facebook.com/apps> (logado no Facebook que tem
   acesso ao Business Manager certo).
2. **Criar app** → tipo **Business** → vincular ao **Business Portfolio** (BM)
   correto.
3. Nome do app: ex. `Nexus Chat AI` (interno, não aparece pro cliente final).

> **Múltiplos apps**: você pode ter vários apps no mesmo BM. Criar um novo NÃO
> afeta o app existente (ex: o que já conecta outro número). Cada app tem seu
> próprio `app_id`/`secret`/`config_id`.

---

## Parte 2 — Produto WhatsApp + Embedded Signup

1. No painel do app → **Adicionar produto** → **WhatsApp** → Configurar.
2. Isso cria automaticamente uma WABA de teste + um número de teste (útil pra
   validar antes de conectar o número real).
3. **Embedded Signup**: App → WhatsApp → **Embedded Signup** (ou "Configurações").
   - Criar/abrir uma **configuration** → copiar o **Configuration ID**
     (`config_id`). É um número longo (ex: `1356011062653699`).
   - Permissões da config: `whatsapp_business_management` +
     `whatsapp_business_messaging`.
   - **Coexistence** (WhatsApp Business no celular + ChatNexus, mig 200):
     habilitar na configuração o onboarding de números do WhatsApp Business
     app. Detalhes em `docs/WHATSAPP_COEXISTENCE.md`.

---

## Parte 3 — Credenciais (App ID + Secret)

1. App → **Configurações → Básico**:
   - **ID do app** (`app_id`) — número.
   - **Chave Secreta do app** (`app_secret`) — clicar em **Mostrar**, copiar
     (hex 32 chars). **Nunca commitar / nunca expor no frontend.**

---

## Parte 4 — Domínios (CRÍTICO pro FB SDK funcionar)

O FB JS SDK **bloqueia** `FB.login` se o domínio não estiver autorizado — é a
causa #1 de "clico em Conectar e nada acontece / tela em branco".

1. App → **Configurações → Básico → Domínios do app**: adicionar
   - `chat.vsanexus.com`
2. App → **Login do Facebook → Configurações**:
   - **Domínios permitidos para o JavaScript SDK**: `https://chat.vsanexus.com`
   - **URIs de redirecionamento OAuth válidos**: `https://chat.vsanexus.com/`
     (o Embedded Signup não usa redirect, mas o FB Login exige ≥1 URI válida)
3. **Modo do app** (topo do dashboard):
   - **Live** pra produção (exige Business verification), OU
   - **Development** + seu usuário Meta como **Admin/Testador** do app (funciona
     com número de teste, sem verificação).

---

## Parte 5 — Webhook (recebimento de mensagens)

1. App → **WhatsApp → Configuration → Webhook**:
   - **Callback URL**: `https://api.vsanexus.com/webhook/waba`
   - **Verify Token**: o mesmo valor que você vai pôr em
     `WABA_WEBHOOK_VERIFY_TOKEN` (gere com `python -c "import uuid; print(uuid.uuid4())"`)
   - Clicar **Verify and Save** (a Meta faz um GET de challenge no endpoint —
     o backend já responde isso em `webhook_waba.py`).
2. **Subscrever campos**: marcar `messages` + `message_template_status_update`.
   Para Coexistence, também `smb_message_echoes`, `history`,
   `smb_app_state_sync` e `account_update` (`docs/WHATSAPP_COEXISTENCE.md`).

> O webhook fica em `api.vsanexus.com` (backend FastAPI), **NÃO** em
> `chat.vsanexus.com` (frontend Next.js) — esse último redireciona pra /login.

---

## Parte 6 — Envs no Dokploy

No service `chat.vsanexus.com` → **Environment**, com os valores REAIS (não os
placeholders):

```bash
META_APP_ID=<app_id numérico do passo 3>
META_APP_SECRET=<app_secret hex do passo 3>
META_CONFIG_ID=<config_id do passo 2>
WABA_WEBHOOK_VERIFY_TOKEN=<uuid gerado no passo 5>
WABA_GRAPH_API_VERSION=v25.0
PUBLIC_BASE_URL=https://api.vsanexus.com
```

**Redeploy** (rebuild — o frontend carrega o FB SDK com o app_id do
`/waba/config`). Confirmar no log da API que `waba_enabled` virou true:

```bash
docker exec $(docker ps -qf "name=chatvsanexus.*api") sh -c \
  'echo "APP_ID=[$META_APP_ID]"; echo "CONFIG_ID=[$META_CONFIG_ID]"; echo "SECRET=$([ -n \"$META_APP_SECRET\" ] && echo set || echo VAZIO)"'
```

Os 3 devem aparecer preenchidos. Se algum vier `[]`/`VAZIO`, o env não pegou.

---

## Parte 7 — Conectar pela UI

1. `chat.vsanexus.com` → **Conexões** → **Nova conexão** → **WhatsApp Oficial**.
   Escolher o modo: **WhatsApp Cloud API** (número dedicado à API) ou
   **WhatsApp Business + ChatNexus** (Coexistence: o número continua no app do
   celular; não é registrado e os contatos e o histórico são sincronizados).
2. Botão **"Conectar com Meta"** (espera o SDK carregar — fica "Carregando
   SDK..." por ~1s).
3. Popup oficial da Meta abre → logar / selecionar o **Business** + **número**
   (ou criar número novo). Confirmar.
4. Popup fecha → conexão `waba` aparece como **Conectada** na lista.

---

## Parte 8 — Validar E2E

1. Do WhatsApp de um celular, mandar msg pro número conectado.
2. Conferir que chega na fila:
   ```bash
   docker exec $(docker ps -qf "name=chatvsanexus.*db") \
     psql -U postgres -d whatsapp_langchain -P pager=off -c \
     "SELECT id, phone_number, to_number, status FROM message_queue
       WHERE conexao_id = (SELECT id FROM conexao WHERE provider='waba'
                            ORDER BY id DESC LIMIT 1)
       ORDER BY id DESC LIMIT 3;"
   ```
3. Aparece linha + agente responde → cliente recebe no WhatsApp.

---

## Troubleshooting

| Sintoma | Causa provável | Fix |
|---|---|---|
| "Clico em Conectar e nada acontece / tela branca" | Domínio não autorizado no FB Login OU `META_APP_ID` vazio | Parte 4 + conferir envs (Parte 6) |
| Botão fica "Carregando SDK..." pra sempre | `/waba/config` retornou 503 (waba_enabled=false) | Setar META_APP_ID/SECRET/CONFIG_ID + redeploy |
| Popup abre mas erro "URL blocked / domain not included" | Falta domínio em "Allowed Domains for JS SDK" | Parte 4 |
| Webhook "Verify and Save" falha | URL errada (usou chat. em vez de api.) ou verify token diferente | Parte 5 |
| Conecta mas msg não chega | Campos `messages` não subscritos OU webhook não verificado | Parte 5 (subscrever campos) |
| Erro no console `confirm-ad-redirect.js` | AdBlocker bloqueando popup FB | Testar em aba anônima sem extensões |
| "Número já registrado" | Número está em outro app/WABA | Migrar número pro novo app ou usar número novo |

### Como pegar o erro exato

F12 → aba **Console** (não Network) → procurar linha **vermelha**. O FB SDK
costuma dizer `Can't Load URL: The domain of this URL isn't included...` —
isso aponta direto pra Parte 4 (domínios).

---

## Estado em 2026-08-21 (leia antes de tentar ligar)

**A integração está DESLIGADA em produção.** `waba_enabled` é `False`: o app
Meta que existia foi criado num painel cujas credenciais moravam no env do
Dokploy, e esse env morreu com o servidor no incidente de 2026-08-19. Não
sobreviveram nem no `.env` de desenvolvimento. Ligar de novo exige **recriar o
app na Meta** e refazer as Partes 1 a 6 deste guia; o código não precisa mudar.

Hoje não existe nenhuma conexão `waba` — a operação roda em **Evolution
(Baileys)**, que é o padrão por decisão do dono. WABA fica disponível para quem
pedir número oficial.

### O que mudou na Meta e afeta a decisão

- **1º/10/2026** — mensagens de **serviço** (resposta livre dentro da janela de
  24h) e **utility dentro da janela** passam a ser **cobradas por mensagem**.
  Hoje são gratuitas. É exatamente o padrão de uso do Nexus: o agente
  respondendo cliente dentro da janela. Rates por país saem até 1º/09/2026.
  Traduzindo: no número oficial, **cada resposta do agente passa a ter preço**.
- **Desde abr/2026** o Embedded Signup é o caminho padrão de onboarding
  (mandato de Tech Provider da Meta) — que é justamente o fluxo deste guia.
- O cliente onboardado precisa cadastrar **método de pagamento** na conta
  WhatsApp Business dele, senão o envio falha.
- Versão da Graph API: usamos **v25.0** (`WABA_GRAPH_API_VERSION`), suportada
  até **29/07/2028**. A checagem `graph_api_version` do relatório diário avisa
  90 dias antes do sunset — ninguém precisa lembrar disso sozinho.

### O que o código NÃO faz (para não descobrir no dia)

- **Não envia mídia** por conexão WABA: falta o upload
  (`POST /{phone_id}/media`). Anexo pelo composer é bloqueado com aviso.
- **Não trata `statuses`** (enviado / entregue / lido) — sem tracking de entrega
  em conexão oficial.
- **Não guarda validade do token** (`expires_in` é descartado) nem faz refresh.
- **Templates sem parâmetro de HEADER** (texto ou mídia) e sem named params.
- **Sem retry/backoff em 429** no cliente WABA.
- **Um app Meta para toda a plataforma**: o HMAC do webhook usa sempre o
  `META_APP_SECRET` global; não há app por empresa.

### Fluxo OAuth legado (depreciado)

`/waba/oauth/start`, `/callback`, `/result` e `/finalize` são do fluxo antigo,
por redirect. Continuam registrados, mas o caminho oficial é o Embedded Signup
(`/waba/embedded-signup`). Não construa nada novo em cima do legado.

---

## Endpoints envolvidos (referência técnica)

| Endpoint | Função |
|---|---|
| `GET /api/conexoes/waba/config` | Frontend pega `app_id`+`config_id` pro FB.init (sem secret) |
| `POST /api/conexoes/waba/embedded-signup` | Recebe `{code, waba_account_id, phone_number_id?, waba_mode}` → cria conexão (`phone_number_id` é opcional só em Coexistence) |
| `POST /api/conexoes/waba/manual` | Conexão manual (como o Chatwoot): `{phone_number_id, waba_account_id, access_token, display_name?}` — valida na Meta (`GET /{phone}` + `GET /{waba}/phone_numbers`), **não registra** o número (já está ativo na API), assina o webhook da conta. Token de usuário do sistema com acesso ao App do ChatNexus (App próprio por empresa: ADR-006) |
| `POST /api/conexoes/{id}/waba/sincronizar` | Coexistence: repete o pedido de contatos + histórico (`smb_app_data`) em até 24 h |
| `GET/POST /webhook/waba` | Handshake (verify token) + mensagens, status de templates e, em Coexistence, eco do celular, histórico, contatos e desconexão |
| `/api/conexoes/{id}/templates` | Templates HSM (após conexão criada). Desde a mig `113`, templates HSM aprovados são **enviáveis** via campanha (selector no form) e via composer do `/atendimento` |

Código: `integrations/waba/oauth.py` (exchange/phone/register/subscribe),
`server/routes/conexao.py` (`_create_waba_conexao`, endpoints),
`frontend/src/app/connections/waba-oauth-button.tsx` (FB SDK).

---

## Múltiplos números / múltiplos apps (seu caso)

- **Mesmo app, vários números**: uma WABA pode ter vários números; o Embedded
  Signup deixa escolher qual conectar. Cada número vira uma `conexao` separada
  no Nexus (resolvida por `waba_phone_id` no webhook).
- **Apps diferentes pra ferramentas diferentes**: ok ter o app do ZigChat +
  app do Nexus no mesmo BM. Mas um **número** só vive em um app por vez.
- **Trocar número entre apps**: WhatsApp Manager → Phone Numbers → mover o
  número pro novo app (pode exigir re-verificação do número).

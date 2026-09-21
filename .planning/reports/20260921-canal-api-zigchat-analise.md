# Canal por API — sistemas externos usam os agentes de IA do Nexus por webhook (ZigChat = 1º sistema)

> Análise de 21/09/2026, guardada para execução posterior (decisão do dono: primeiro o monitoramento das conexões, depois esta integração). OpenAPI oficial do ZigChat REST v1 em `20260921-zigchat-openapi-v1.json`.

## Contexto e decisões do dono (21/09)

- Pedido: mensagens do ZigChat vêm ao Nexus, os agentes de IA processam, a resposta volta ao ZigChat — **via webhook**.
- **Não mudar a estrutura do Nexus**: o Nexus continua atendendo as conversas próprias (Evolution/WABA) e passa a **receber webhooks de outros sistemas**, que usam os agentes e recebem a resposta. O ZigChat é o primeiro sistema, não um caso especial.
- Objetivo de negócio: usar o fluxo do **Hospital Mackenzie (HPM)** — o dono é responsável — para **validar o Nexus em volume, com vários agentes rodando** (≈ 35 mil msgs/mês, 17 departamentos, 9.822 atendimentos em 3 meses).
- Cliente = Mackenzie (HPM), validar **direto em produção** (`app.zigchat.com.br`, empresa 43, conexão 548 "67 3416-7800 - Oficial") com departamento e número de teste; escopo = **todas as mensagens de departamentos escolhidos**; **humano continua no ZigChat** (Nexus = IA + espelho somente-leitura); **Fase 0 (spike) antes do MVP**.

## Por que a decisão de 16/09 (won't-do) está superada

A premissa "ZigChat não tem token máquina-a-máquina nem webhook; auth é JWT de sessão de 5 dias" olhava só o **GraphQL interno do painel** (`dev.zigchat.com.br/api/graphql`). Fatos levantados em 21/09 (agentes de varredura + introspecção + OpenAPI oficial):

| Capacidade | Evidência |
|---|---|
| **REST v1 com chave permanente** `https://app.zigchat.com.br/api/v1`, `Authorization: Bearer <Empresa.api_key>` | `/home/projects/tools/relatorios-hpm/zigchat.py:8,21-22`; coletor a cada 30 min desde 23/06/2026, última coleta 21/09 21:07Z (mesma chave); OpenAPI em `/api/v1/docs/` (embutido em `swagger-ui-init.js`); servers `app.` e `teste.zigchat.com.br` |
| `POST /mensagem/enviar` **por telefone** | `{mensagens*:[{mensagem, arquivo}], telefone\|lid\|cliente_id, conexao (nome), nome*, transferir, interna, verifica_numero, finalizarAtendimento}` → `{codigo 1\|2, erro, dados}` |
| `POST /atendimento/transferir {atendimento_id*, departamento_id, atendente_usuario_id}`, `POST /atendimento/encerrar {atendimento_id*, mensagem*}`, **context** `criarAlteraContext {atendimento_id, context_key, value}` / `deletarContext` / `GET /atendimento/context/{id}/{key}`, `GET /atendimento/listar?id&departamento_id&cliente_id&conexao_id&ativo&limit≤50&order`, `GET /mensagem/listar/{id}`, `/mensagem/menuEnviar`, `/mensagem/template` (HSM) | OpenAPI (escrita ainda **não exercitada** por nós — só leitura) |
| **Webhooks de saída** (painel `/dashboard/hk/hook`, abas Formatação / URLs / Entregas): `acao=1` **"Hook Padrão" por mensagem** (flags `msg_cliente`/`msg_usuario`), `2` início de atendimento, `3` fim, `4` tag, `5` entrou na fila; `HookUrl` (várias por hook), `Hook.headers` (headers customizados = segredo), `HookTask{target, body, queue, status, http_status_code, log}` | `webscap/output/runs/2026-05-05_180535/payloads/flow_hook-explorar__filtrarHook.json` (branch `feat/webscap`); screenshot `_dashboard_hk_hook.png`; schema GraphQL `Hook/HookUrl/HookTask` |
| Template (Mustache, **editável**) do Hook Padrão: `{nanoid, mensagem, conexao, atendimentoId, empresaId, empresaNome, tipo, arquivo, isGroupMessage, cliente{id,nome,telefone,email}, context}` | idem; idêntico ao "payload esperado" em `nexus-ai/.ai/skills/whatsapp-integration/SKILL.md:67-88` |
| Formato real das mensagens (dump REST): sem `fromMe`; cliente = `automatica=false AND usuario=null`; humano = `usuario != null`; bot = `automatica=true`; `content_type`, `url` (S3), `interna`, `atendente_usuario_id` | `scripts/import_zigchat_dump.py:119-143`; `tools/relatorios-hpm/data/zigchat-mensagens/…` |
| GraphQL do painel: `Login(login:{usuario,senha}){token}` (JWT 5 dias, header literal `JWT`), subscriptions `atualizaAtendimentoMensagemSub(empresa_id)` em `wss://<host>/subscriptions` (protocolo `graphql-ws` legado, `connection_init{headers:{authorization:"JWT …"}}`) — **plano B de push sem hook** | introspecção 21/09 + bundle `main-es2015.*.js` (`websocket:"wss://dev.zigchat.com.br/subscriptions"`; handshake aceito, fecha sem token) |
| ZigChat tem **IA nativa** (`AgenteIA`, `McpServer` HTTP, `Item.acao_agente_ia_id`, `Atendimento.agente_ia_id`) e menus por departamento — concorre na mesma conversa | schema + `/dashboard/ia` |
| Nexus: provedor de canal = valor em `conexao.provider` (CHECK mig 153) + ramo em `shared/outbound.py::_build_client` (linha 130 = "Provider desconhecido") + cliente `OutboundClient` (`delivery_mode`, `send_message(to, body) -> str`, `send_typing(to, message_id) -> bool`, `worker/outbound_client.py:61-100`). Webhook de entrada no molde de `evolution_webhook.py:247-587`. **Não existe dedup por `message_id`** (mig 001 sem UNIQUE; comentário em `webhook_waba.py:225` está errado). `POST /api/conexoes` não cifra credenciais (só `/evolution/provision` chama `save_credentials`). Hooks do Nexus são só notificação (sem evento "resposta enviada"). | relatório do agente "contrato de provedor" |

Quem usa ZigChat: HPM (empresa 43, conexão 548; 17 deptos: 83 Agendamento Ambulatorial 14.926 atend., 88 Atendimento ao Cliente 3.717, 82 Ouvidoria 1.118 em jul/25→set/26); ZigChat cobra R$ 0,0385/msg (R$ 1.302/mês). Chave da empresa 43 **vazou** em `tools/relatorios-hpm/dados.txt` — rotacionar após a Fase 0.

## Desenho

```
Sistema externo (ZigChat, ERP, outro chat…)
   │ POST https://api.vsanexus.com/webhook/api/{canal_id}   header X-Nexus-Canal-Token
   │ corpo = CONTRATO DO NEXUS (JSON fixo) — no ZigChat, o template Mustache do Hook Padrão gera esse JSON
   ▼
Nexus API  server/routes/webhook_api.py
   conexão provider='api' por canal_id (bypass RLS) → compare_digest(token) → set_request_context(empresa)
   filtros do canal (ex.: extra.departamento_id ∈ [83, 88]) · roteamento regra → agente + modo · remetente=atendente ⇒ handoff · dedup "api:<id>"
   upsert_cliente + open_or_attach_atendimento (externo_id = conversa_id) + enqueue_or_buffer + dispatch_event → 200 em <100 ms
   ▼
Worker — fluxo de hoje, sem mudança
   outbound = ApiOutboundClient(conexao) ← _build_client ramo 'api'
   send_message(to, body) → ENTREGA CONFIGURÁVEL: url + método + headers + modelo de corpo (Jinja2 |tojson) + regra de sucesso
       preset "ZigChat": POST /api/v1/mensagem/enviar {mensagens:[{mensagem}], telefone, nome, conexao}, sucesso codigo==1
       preset "Webhook genérico": POST url do sistema {conversa_id, telefone, nome, texto, arquivo, mensagem_id} + X-Webhook-Signature (HMAC)
   delivery_mode="sombra": agente roda, resposta gravada com marcador, NADA sai (validação em volume)
   on_handoff (duck-typing) → entrega "transferir" (preset ZigChat: POST /atendimento/transferir)
Painel /atendimento: espelho somente-leitura para provider='api'
```

**Contrato de entrada** (`docs/CANAL_API.md`, público):
```json
{"id": "id único na origem (dedup)", "conversa_id": "id do atendimento na origem",
 "contato": {"telefone": "+5567999999999", "nome": "Fulano", "id_externo": "123"},
 "remetente": "cliente | atendente | sistema", "texto": "…",
 "arquivo": {"url": "https://…", "tipo": "image/jpeg", "nome": "foto.jpg"},
 "data": "2026-09-21T18:00:00Z", "extra": {"departamento_id": 83}}
```
`remetente=atendente` marca assumido por humano (gate do handoff cala o agente); `sistema` só espelha; `extra` alimenta filtros e roteamento; telefone via `shared/telefone.py::normalizar_br`; `arquivo.url` http(s) vira `media_url`; `id` → `message_id="api:<id>"` (índice parcial único, duplicata = 200).

**Modelo**: `conexao.provider='api'`; `payload_json = {canal_id, sistema, filtros, roteamento: [{quando:{departamento_id:[83]}, agente:"agendamentos", modo:"sombra"|"ao_vivo"}, …, {padrao:…}], entrega, transferencia, rotulo_origem}`; `credentials_encrypted = {token_entrada, segredos}`; `atendimento.externo_id`; `message_queue.entrega_modo` (sombra por mensagem). Presets em `integrations/canal_api/presets.py`.

**Validação em volume (HPM)**: roteamento por departamento → agente (prompts em `docs/agentes/prompts-saude/`: agendamentos, atendimento-cliente, exames, financeiro, ouvidoria, suporte-exames, nps-feedback; sandbox empresa 999 Mackenzie já tem o material do dump); **modo sombra** por regra (`SOMBRA_MARKER = "[modo sombra — resposta não enviada]"`, chip "Modo sombra"); capacidade OK (89 msg/min/réplica, 2 réplicas); custo ≈ US$ 36/mês em sombra total. Escada: Fase 0 → sombra total nos departamentos → ao vivo em 1 departamento (Agendamento) → demais.

## Fase 0 — spike em produção (HPM), 1–2 dias, sem merge
Pré-requisitos: chave da empresa 43, acesso ao painel HPM (Hooks), departamento "Teste IA", número de teste do dono.
1. Rota mínima de captura no dev `POST /webhook/api/{canal_id}` (log `canal_api_webhook_raw`); cadastrar Hook Padrão → URL do dev, `headers` com o token; **editar o template Mustache para emitir o contrato do Nexus** (validar aninhados, `departamento_id`, `atendente_usuario_id`, `usuario`, `automatica`, `interna`, `timestamp`, `content_type`).
2. Cenários: texto/áudio/imagem no departamento de teste; atendente humano responde; IA nativa; grupo; interna; outro departamento; URL devolve 500 → retentativa (`HookTask`).
3. Escrita (`scripts/zigchat_spike.py`, chave em `~/.secrets`): `/mensagem/enviar` (como aparece no painel; **volta pelo hook como eco?**), `criarAlteraContext` (aparece no hook seguinte?), `transferir`, `encerrar`, `GET /atendimento/listar?id=`, latência.
4. Entrega: `docs/ZIGCHAT_INTEGRACAO.md` + memória `reference_zigchat_api` + `decisoes_arquiteturais_2026-09-16` (decisão 3 superada) + vault `Integracao-ZigChat.md`.
5. Go/no-go: departamento identificável no hook, envio por telefone sem loop (ou eco reconhecível), `transferir` OK.

## Fase 1 — MVP Canal por API (texto + mídia por URL), preset ZigChat
- **Mig 197**: `conexao_provider_check` += `'api'`; `atendimento.externo_id` + índice; `message_queue.entrega_modo`; `uq_message_queue_api (conexao_id, message_id) WHERE starts_with(message_id,'api:')`; `plano.features.canal_api` (Pro/Ent + flag para o HPM — confirmar).
- Backend: `PROVIDERS_SUPORTADOS += "api"`; `get_conexao_by_canal_id` (bypass); `integrations/canal_api/{contrato,presets,entrega,client}.py`; ramo em `_build_client`; `CANAL_API_OUTBOUND_MODE`; rota `POST /api/conexoes/canal-api` (molde `/evolution/provision`, `save_credentials`, devolve URL/token/contrato/template Mustache); `server/routes/webhook_api.py`; handoff nos dois sentidos; modo sombra no processor (`processor.py:~3453`, `_resolve_outbound_client` lê `entrega_modo`); espelho somente-leitura; sonda de saúde = entrega `teste` do preset.
- Frontend: `ConexaoProvider += "api"`; card "Sistema externo (API)" → `canal-api-form-modal.tsx` (preset, campos, roteamento) → tela "Como conectar"; `connections-list`, `[id]/page`, aviso no composer.
- Testes: unit webhook/entrega/roteamento/sombra; E2E `test_canal_api_endpoints.py`; fumaça no dev com o hook real do HPM.
- Fase 2: endpoint síncrono, templates HSM, `HookTask` no monitor, IA nativa por atendimento, rotação da chave, plano B (subscription).

## Riscos
Eco/loop (resposta volta pelo hook como "atendente" — `remetente` no contrato + guarda robô×robô); hook entrega tudo da empresa (filtro por `extra` antes de escrever; fallback `GET /atendimento/listar?id=`); segredos só em `credentials_encrypted`; retentativa do hook (índice parcial); template configurável (Jinja2 sandbox, `|tojson`, anti-SSRF, presets em código).

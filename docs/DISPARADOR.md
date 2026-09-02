# Disparador — captura de contatos/grupos + disparo em massa

Módulo que incorpora ao ChatNexus um disparador de mensagens em massa pelo
WhatsApp, integrado ao módulo **Campanhas**. Captura contatos/grupos (via
extensão Chrome ou server-side pela Evolution API), permite segmentar e
disparar com salvaguardas anti-ban, e suporta o canal oficial (WABA).

> Origem: análise multi-agente cruzando o produto comercial "Disparador" e o
> ecossistema Baileys (`docs/Baileys`). Proposta final em
> `docs/DISPARADOR_PROPOSTA_FINAL.md`; PRD em `.taskmaster/docs/prd-disparador.txt`.

## Arquitetura

```
Extensão Chrome ──(API key)──▶ POST /api/captura/*        ┐
                                                           ├─▶ contato_capturado
Painel ──(service-token)──▶ POST /api/conexoes/{id}/captura/*  (staging)
                               └─ Evolution fetch_contacts/groups/participants
                                                           ▼
                              promover ──▶ cliente (CRM)
                                                           ▼
Painel ─▶ POST /api/disparador/preview (resolve+dedup+opt-out+validação)
       ─▶ cria Campanha ─▶ _dispatch_loop (jitter anti-ban, kill-switch)
                               └─ OutboundClient (Evolution / WABA)
```

Decisões-chave (do veredito):

- **`wa_jid` é a identidade primária**, não o telefone. Membros multi-device
  aparecem como `<lid>@lid` sem telefone derivável; chavear por telefone os
  perderia. `telefone` é NULLABLE (extraído só de `@s.whatsapp.net`).
- **Staging, não CRM direto**: dados raspados são sujos (sem consentimento);
  caem em `contato_capturado` e o usuário **promove** os escolhidos pra `cliente`.
- **Captura é assíncrona** (background task + `captura_lote.status`): puxar
  membros de grupo é pesado/rate-limited na Evolution.
- **Anti-ban estrutural**: jitter aleatório, validação `onWhatsApp`, opt-out,
  kill-switch. O canal sustentável pra volume é o **WABA** (oficial).

## Schema (migrations 118–121)

| Tabela | Migration | Papel |
|--------|-----------|-------|
| `empresa_api_key` | 118 | Chave por empresa (hash sha256, escopos, expiração, revogação) |
| `captura_lote` | 119 | Auditoria de cada captura (contadores + status) |
| `contato_capturado` | 119 | Staging único por `(empresa_id, wa_jid)` |
| `grupo` / `grupo_membro` | 119 | Grupos/comunidades + membros (`empresa_id` denormalizado p/ RLS) |
| `campanha.intervalo_min_ms/max_ms` | 120 | Faixa de jitter anti-ban |
| `campanha_destinatario.variaveis` | 120 | Personalização por destinatário (CSV) |
| `disparador_opt_out` | 121 | Lista de supressão |
| `campanha.kill_switch_pct/aborted_reason` | 121 | Aborto automático por taxa de falha |

Toda tabela com `empresa_id` se auto-enrola em RLS (`ENABLE`+`FORCE`+policy
`tenant_isolation` via `_rls_tenant_match`).

## Autenticação

Dois caminhos coexistem:

- **Painel** → `verify_service_token` + `get_empresa_context` (header
  `X-Empresa-Id` / default do user). Usado por captura server-side, preview,
  CRUD de keys, opt-out.
- **Extensão Chrome** → `verify_api_key` (`Authorization: Bearer nxs_<eid>_<hex>`).
  A empresa é **descoberta pela chave** e o contexto RLS é ativado
  (`set_request_context`). Rate-limit por chave (`apikey:<id>:disparador`).
  Escopos: `capture`/`dispatch`/`templates` (via `require_scope`).

Formato da chave: `nxs_<empresa_id>_<32hex>`. Guardamos só `sha256(chave)`; o
segredo é exibido **uma única vez** na criação. Comparação timing-safe.

## API reference

### API keys (painel)
- `GET  /api/disparador/api-keys` — lista (sem segredo).
- `POST /api/disparador/api-keys` — `{label, scopes?}` → cria e retorna `key` 1x.
- `POST /api/disparador/api-keys/{id}/revoke` — revoga (soft).

### Captura
- `GET  /api/disparador/status` — *(extensão, API key)* health + empresa + escopos.
- `POST /api/conexoes/{id}/captura/contatos` — *(painel)* 202 + background.
- `POST /api/conexoes/{id}/captura/grupos?com_membros=true` — *(painel)* 202.
- `GET  /api/captura/lotes/{lote_id}` — status/contadores (polling).
- `GET  /api/captura/contatos` · `GET /api/captura/grupos` — browser.
- `POST /api/captura/promover` — `{contato_ids:[…]}` → vira `cliente` (só os com telefone).

### Disparo
- `POST /api/disparador/preview` — `{conexao_id?, origem:{tipo,…}, validar_numeros?}`
  → `{total_bruto, count_duplicado, count_opt_out, count_invalido,
  total_disponivel, amostra, amostra_truncada, limite_plano, excede_plano}`.
  Origens: `manual` | `grupos` | `contatos` | `janela_24h`.
- `GET/POST/DELETE /api/disparador/opt-out` — gestão da supressão.
- Envio: cria `Campanha` com os telefones resolvidos e usa o dispatch existente
  (`POST /api/campanhas/{id}/dispatch`).

## Anti-ban (load-bearing)

- **Jitter aleatório**: `_dispatch_loop` dorme `random.uniform(min,max)` por
  destinatário (default **3000–8000ms** p/ Evolution), não intervalo fixo —
  cadência regular é assinatura de bot.
- **Validação `onWhatsApp`**: `preview(validar_numeros=true)` chama
  `EvolutionClient.check_numbers` e descarta números sem WhatsApp antes de
  enviar (disparar pra números mortos acelera ban).
- **Kill-switch**: aborta a campanha se `falhas/(enviados+falhas) > kill_switch_pct`
  (default 30%) após amostra mínima de 20 — sinal de lista ruim/número marcado.
- **Empurrar volume pro WABA**: o canal não-oficial (Evolution/Baileys) é melhor
  esforço; volume sustentável vai pelo oficial com templates HSM.

## Compliance / LGPD

- **Opt-out**: o worker (`_try_handle_opt_out`) detecta STOP/PARAR/SAIR/… e
  registra em `disparador_opt_out` antes de qualquer roteamento; o resolver de
  disparo filtra esses telefones (`count_opt_out` no preview).
- **Consentimento**: contatos capturados ficam em staging; promover ao CRM é
  ação explícita do operador. Avisar o usuário do produto sobre responsabilidade
  LGPD/consentimento e risco de ToS (a UI deve ter aceite na 1ª campanha
  Evolution).

## Limitações conhecidas

- **Dispatcher in-process**: `_dispatch_loop` roda via `asyncio.create_task` +
  `_BG_TASKS`; um restart da API no meio perde o loop (recipients ficam
  `pendente`). Reenviar pendentes é manual; fix durável (mover pro worker via
  `message_queue`) é dívida técnica registrada.
- **Membros só-LID** não são enviáveis por telefone (sem telefone derivável) —
  ficam no staging mas o disparo por telefone os ignora.

## Testes

- Unit (CI): `tests/unit/test_api_key.py`, `test_evolution_capture.py`,
  `test_campanha_jitter.py`, `test_opt_out.py`.
- Smoke (CI, TestClient): cada endpoint exige auth (401 sem token).
- E2E (`@pytest.mark.docker_demo`): `test_disparador_endpoints.py`,
  `test_captura.py`, `test_disparo.py` — precisam da stack + migrações 118–121.

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
INTERNAL_SERVICE_TOKEN=dev-token-change-in-production EVOLUTION_OUTBOUND_MODE=mock \
uv run pytest tests/integration/test_disparador_endpoints.py tests/integration/test_captura.py tests/integration/test_disparo.py -v
```

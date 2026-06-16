# Disparador Nexus — Proposta Final (análise multi-agente cruzada com docs/Baileys)

> Gerada por workflow dinâmico: 10 especialistas analisaram `docs/Baileys` (226 arquivos: whatsapp-api-nodejs REST, frontend de disparo ZDGText/ZDGFile, screenshots da extensão comercial, planilhas de export de grupo) + juiz sintetizador. PRD task-master em `.taskmaster/docs/prd-disparador.txt`; veredito bruto em `.taskmaster/docs/disparador-veredito.json`.

## Sumário executivo

O plano aprovado está arquiteturalmente correto na PLATAFORMA (staging contato_capturado, RLS self-enroll por migration, verify_api_key + set_request_context, reuso de campanha/_dispatch_loop, API key hasheada por empresa superior ao ?key= dos tutoriais), mas foi escrito sob premissa FALSA — declara nas linhas 17-19 que "docs/Baileys não existe". A pasta existe e contém o produto-fonte real: whatsapp-api-nodejs (tutorial 20/4918a, salman0ansari) com ~25 rotas REST (/instance,/message,/group,/misc), o frontend de disparo (ZDGText.js/ZDGFile.js), screenshots da extensão comercial "Disparador PRO" (docs/Baileys/fotos/) e planilhas que provam o produto-promessa (extrair telefones de membros de grupo → disparar). Cruzar com a fonte revela 7 lacunas que mudam o plano: (1) ANTI-BAN — o produto usa JITTER ALEATÓRIO min/max por destinatário (randomIntFromInterval) + validação onWhatsApp antes de cada envio + presença composing; nosso _dispatch_loop usa intervalo FIXO (linha 359/473-474) sem validação — pior que o tutorial, é assinatura de bot; o plano herda isso ("_dispatch_loop NÃO muda"), o gap mais material. (2) IDENTIDADE = JID, NÃO TELEFONE — membros modernos vêm como @lid sem telefone; o UNIQUE (grupo_id, telefone) os PERDE; nosso cliente.whatsapp_lid (mig 046) já reconhece isso. (3) MEMBROS NÃO SÃO GRÁTIS — getAllGroups() só lista chats @g.us sem participantes; membros exigem fetch separado pesado → captura assíncrona, não síncrona. (4) VARIÁVEIS POR DESTINATÁRIO — placeholders [field1..N] do CSV; nosso _resolve_template_vars (linha 304) só faz {{nome}}; falta JSONB variaveis em campanha_destinatario. (5) PREPARAR→ENVIAR — a UI real valida/conta (e mostra total disponível para upsell "100 de 1210") antes de comprometer; o plano vai direto draft→running. (6) MÍDIA POR URL — nativa no tutorial (sendUrlMediaFile), mais barata que upload local + gotcha rewrite /uploads. (7) COMPLIANCE — falta opt-out, warmup, quiet hours, kill-switch. Recomendo inverter ordem (Evolution antes do scraping, testável em CI), migs de jitter+variáveis+validação, e fixar a verdade técnica de mensagens ricas (botões clicáveis só WABA; "pagamento" do tutorial = WhatsApp Pay e NÃO PIX). A extensão deve reusar o modal de QR (connections/evolution-qr-modal.tsx) e o Embedded Signup WABA já entregue. Verifiquei no repo: evolution_client.py só tem send_message+send_typing (falta todo o resto); _dispatch_loop usa intervalo_s fixo; _resolve_template_vars só troca {{nome}}; migration mais recente confirmada = 117.

## Deltas de arquitetura vs plano aprovado

### 1. Substituir o intervalo FIXO do _dispatch_loop por JITTER aleatorio: colunas intervalo_min_ms/intervalo_max_ms em campanha e delay = random.uniform(min,max)/1000 por destinatario (fallback intervalo_ms quando min==max). Default Evolution 3000-8000ms.
- **Por quê:** O produto-fonte (ZDGText.js:82-87 randomIntFromInterval + ZDGFile.js:61-65) usa jitter como anti-ban PRIMARIO; cadencia regular e assinatura de bot. O plano afirma _dispatch_loop NAO muda (linhas 77/197) e 500ms fixo (linha 228) = 7200 msg/h num numero novo = ban quase certo. Confirmado no repo: campanha.py:359 usa intervalo_s fixo, :473-474 asyncio.sleep(intervalo_s).
- **Afeta:** `src/whatsapp_langchain/shared/campanha.py (_dispatch_loop linha 359/473-474) + db/migrations/120`

### 2. wa_jid como IDENTIDADE PRIMARIA: UNIQUE de contato_capturado vira (empresa_id, wa_jid), telefone NULLABLE; +wa_lid; grupo_membro ganha wa_jid NOT NULL + telefone NULLABLE, UNIQUE (grupo_id, wa_jid).
- **Por quê:** Membros multi-device aparecem como @lid sem telefone derivavel; store da Baileys keyeia por JID (botzdg_chat_upsert.js:63). O UNIQUE (grupo_id, telefone) do plano (mig 119) perde membros so-LID. cliente.whatsapp_lid (mig 046) ja reconhece o modelo.
- **Afeta:** `db/migrations/119 (contato_capturado, grupo_membro) + shared/captura.py`

### 3. Captura de MEMBROS de grupo como lote ASSINCRONO dedicado (captura_lote tipo=grupo_membros, status processando->concluido/parcial), separado de grupos; fetch separado por grupo (groupMetadata) com cap+paginacao+background task.
- **Por quê:** getAllGroups()=chats.filter(@g.us) NAO traz participantes (instance.js:427); o repo admite no group.route.js que sem store might not work. Membros = 2o round-trip pesado; store hidrata em minutos (chats.set). O plano (slice 4 sincrono no MVP) subestima.
- **Afeta:** `worker/evolution_client.py (fetch_group_participants) + server/routes/captura_evolution.py + db/migrations/119`

### 4. Validacao onWhatsApp/exists ANTES do disparo: EvolutionClient.check_numbers (POST /chat/whatsappNumbers) no RESOLVER do create (batch), marca invalidos falhou sem gastar envio; coluna wa_existe+validado_at. Skip WABA.
- **Por quê:** TODO envio Baileys chama verifyId->onWhatsApp antes (instance.js:232-246); numeros raspados sao sujos; disparar para inexistentes acelera ban. normalize_phone (campanha.py:41) so faz regex, nunca valida existencia. Anti-ban n1 ausente no plano.
- **Afeta:** `worker/evolution_client.py + shared/campanha.py (resolver) + db/migrations/121`

### 5. Coluna variaveis JSONB em campanha_destinatario + _resolve_template_vars estendido (mescla variaveis por-destinatario do CSV sobre template_variaveis, [field1..N]/{{var}}, {{nome}} retrocompat).
- **Por quê:** A UI real usa placeholders posicionais por coluna do CSV (chrome_DvZZ3ZnirH.png). _resolve_template_vars (campanha.py:304-316) so troca {{nome}} pelo primeiro nome. Sem JSONB por destinatario, campanhas personalizadas por CSV - funcao central do produto - sao impossiveis.
- **Afeta:** `shared/campanha.py (_resolve_template_vars linha 304) + db/migrations/120`

### 6. Endpoint PREVIEW (POST /api/disparador/preview): resolve origem, retorna {count_valido, count_invalido, sample, total_disponivel}; so entao front habilita ENVIAR.
- **Por quê:** A UI real (chrome_DvZZ3ZnirH.png) tem Preparar (verde) + ENVIAR (cinza, so habilita apos Preparar); modais expoem total mesmo truncado (100 de 1210) como upsell. O plano vai direto draft->running sem preview nem total_disponivel.
- **Afeta:** `server/routes/disparador.py + server/routes/captura.py + frontend create`

### 7. Inverter ordem: captura via Evolution (slice 4 do plano) ANTES do scraping (slice 3); Evolution reusa EvolutionClient, roda em CI com mock e valida staging+promote+membros; scraping e o artefato mais fragil (ToS, QA manual).
- **Por quê:** Captura Evolution e mais barata, testavel e prova o cano de dados antes do scraper fragil. Derisca o build conforme foco em 1 modulo por vez.
- **Afeta:** `sequencia de build do plano + tests/integration/test_disparador_*.py`

### 8. MIDIA POR URL para Evolution (send_media_url) em vez de carregar bytes; upload local + DISPARADOR_MEDIA_DIR + mount /uploads/disparador como secundario/WABA.
- **Por quê:** O tutorial envia midia por URL nativamente (instance.js:263-277 sendUrlMediaFile; ZDGFile.js). Evolution aceita URL. O plano escolheu upload local que arrasta o gotcha rewrite /uploads (INTERNAL_API_URL congelado em build) - citado pelo proprio plano como risco.
- **Afeta:** `worker/evolution_client.py + server/routes/disparador.py + compose`

### 9. Camada COMPLIANCE/anti-ban estrutural: disparador_opt_out (filtro no resolver + captura STOP no worker); caps por provider; warmup escalonado; quiet hours (08h-20h default); kill-switch (auto-abort se falhas/enviados>30%).
- **Por quê:** ToS/ban e P0 estrutural e o plano so mitiga com intervalo 500ms + avisos. Denuncias sao o gatilho n1 de ban. WABA e a rota sustentavel para volume - gating empurra volume para WABA.
- **Afeta:** `shared/campanha.py + shared/plano_limits.py + worker (process_message) + db/migrations`

### 10. Fixar VERDADE TECNICA de mensagens ricas e gatear por provider: botao/lista clicavel so WABA (NAO Evolution/pessoal, deprecado ~2022); pagamento tutorial = requestPaymentMessage (WhatsApp Pay) != PIX (PIX real = BR Code+QR); cartao = imagem+caption+botoes != vCard. Implementar send_reaction (unico recurso rico em conta pessoal).
- **Por quê:** Aulas 4910/4925/4927/4914 pinam @adiwajshing/baileys 4.0-4.4 (descontinuado); botoes interativos bloqueados em conta pessoal. Replicar literal entrega feature que nao renderiza. Header promete PIX, listas com botoes, 21 midias - Premium so viavel em WABA. Reacao (POST /message/sendReaction) e o unico portavel.
- **Afeta:** `docs/plano + shared/outbound.py + worker/evolution_client.py`

## Inventário de features (prioridade × status no plano)

| Prioridade | Feature | Fonte | Status |
|---|---|---|---|
| P0 | wa_jid identidade primaria + wa_lid + telefone NULLABLE (membros so-LID) | captura-grupos + cliente.whatsapp_lid mig 046 | modificar |
| P0 | JITTER aleatorio intervalo_min_ms/max_ms por destinatario | disparo-massa + screenshots + sessao-antiban | modificar |
| P0 | empresa_api_key (nxs_<eid>_<32hex> + key_hash sha256 + scopes + revoked_at) | PRD + auth-token (contra-exemplo keyCheck.js) | coberto |
| P0 | verify_api_key (HTTPBearer auto_error=False, 401/403) + set_request_context | PRD + dependencies.py verify_service_token L113-155 | coberto |
| P0 | contato_capturado (staging) dedup idempotente | PRD | coberto |
| P0 | grupo + grupo_membro (wa_jid, is_admin) | PRD + app-grupo.js | coberto |
| P0 | Captura via extensao Chrome (POST /api/captura/*) | PRD | coberto |
| P0 | Captura server-side Evolution (findContacts/fetchAllGroups) | PRD + rest-api + nodeback | coberto |
| P0 | Promover contato_capturado -> cliente (bulk) | PRD | coberto |
| P0 | Resolver de destinatarios no create (manual|grupos|contatos|janela_24h|segmento) | PRD | coberto |
| P0 | Disparo em massa reusando _dispatch_loop | PRD + disparo-massa | coberto |
| P1 | check_numbers (POST /chat/whatsappNumbers) onWhatsApp/exists | rest-api + disparo-massa + sessao-antiban | novo |
| P1 | getWhatsAppId/normalizador unico de JID (@s.whatsapp.net vs @g.us) | rest-api + backend-arch (instance.js:227-246) | novo |
| P1 | total_disponivel mesmo truncado (upsell 100 de 1210) | screenshots (chrome_KUc91Q1e5o) | novo |
| P1 | contatos-unicos (dedup cross-grupo DISTINCT wa_jid) = LEADS UNICOS | captura-grupos (HISTORICO_GRUPOx.xlsx) | novo |
| P1 | Preparar->ENVIAR (POST /preview: count/invalidos/total) | screenshots | novo |
| P1 | Opt-out/supressao (disparador_opt_out + STOP no worker) | sessao-antiban | novo |
| P1 | Caps por provider (Evolution baixo vs WABA tier) | sessao-antiban + plano_limits | novo |
| P1 | Status auth 401/403 NUNCA 500 + compare timing-safe sobre o HASH + lookup por key_prefix | auth-token (anti-padrao botzdgpost.js 500) | modificar |
| P1 | is_business derivado de verifiedName!=null + push_name opcional | captura-grupos (shape store) | modificar |
| P1 | fetch_group_participants como lote ASSINCRONO separado, NAO inline | backend-arch + plano-cross (getAllGroups sem participantes) | modificar |
| P1 | captura_lote (auditoria) + contador pulados por invalido | PRD + screenshots | modificar |
| P1 | Variaveis por-destinatario (variaveis JSONB) + [field1..N] | screenshots + disparo-massa | modificar |
| P1 | Midia por URL (send_media_url) caminho nativo Evolution | disparo-massa + plano-cross | modificar |
| P1 | Reuso modal QR existente (connections/evolution-qr-modal.tsx), polling NAO Socket.IO | frontend | modificar |
| P1 | Aviso ToS/ban BLOQUEANTE (checkbox de aceite) na 1a campanha pessoal | sessao-antiban + PRD | modificar |
| P1 | API Oficial WABA: criar/listar/sync templates HSM (reusa waba_templates) | PRD + screenshots | coberto |
| P1 | Embedded Signup WABA (reusa fluxo existente) | screenshots + docs/WABA_SETUP.md | coberto |
| P1 | Janela 24h (DISTINCT message_queue 24h) | PRD | coberto |
| P1 | Plan gating: disparador/disparador_media/disparador_max_contatos(Free=25) | PRD | coberto |
| P1 | Permissoes disparador.{capturar,disparar,api_key.manage,template.manage} | PRD | coberto |
| P1 | Extensao Chrome MV3 (background+content+popup+options+lib/api Bearer) | PRD + screenshots | coberto |
| P1 | Scraping via hook window.Store (moduleRaid), isolado+versionado | PRD + captura-grupos | coberto |
| P1 | Painel /disparador (api-keys segredo 1x + contatos browser + bulk promover) | PRD + frontend | coberto |
| P2 | expires_at + rotacao de API key + rate-limit por key | auth-token | novo |
| P2 | grupo.invite_link + grupo.tipo (grupo|comunidade) | captura-grupos (folder 171) + screenshots | novo |
| P2 | Health da conexao (/instance/info + /misc/getStatus) p/ Testar conexao | rest-api + screenshots | novo |
| P2 | Presenca composing antes do envio | disparo-massa + rich-messages | novo |
| P2 | Warmup escalonado de numero novo | sessao-antiban | novo |
| P2 | Quiet hours + kill-switch (auto-abort falhas>30%) | sessao-antiban | novo |
| P2 | send_reaction (POST /message/sendReaction) unico rico em conta pessoal | rich-messages (botzdgreactions.js) | novo |
| P2 | Botoes/listas via WABA (interactive/template), NAO Evolution | rich-messages (deprecado conta pessoal) | novo |
| P2 | Extensao aguarda Store.Chat hidratar antes do 1o envio | captura-grupos + backend-arch | novo |
| P2 | UI de progresso por destinatario (polling campanha_destinatario) | frontend | novo |
| P2 | ADR: NAO hospedar nodeback Baileys (RAM+arquivo+key=identidade) incompativel com SaaS/RLS | backend-arch | novo |
| P2 | Aba de canal data-driven por Conexao.provider (+WaVoIP futuro) | screenshots (3 pilulas) | modificar |
| P2 | Midia por upload local (secundario) | PRD | coberto |
| P3 | PIX real (BR Code EMV+QR) via send_media, NAO requestPaymentMessage | rich-messages (aula 4927 = WhatsApp Pay) | novo |
| P3 | Inbound trata templateButtonReplyMessage.selectedId E buttonsResponseMessage.selectedButtonId | rich-messages | novo |
| P3 | Restore-on-boot + distincao logout(novo QR) vs disconnect(reconectavel) | sessao-antiban + backend-arch | novo |

## Roadmap (vertical slices entregáveis — ordem de derisco)

### S0 — Fundacao API keys + RLS via API-key (maior risco)
**Meta:** Provar que a auth da extensao por API key hasheada isola tenants pelo RLS em ambas as direcoes ANTES de qualquer captura. Ponto unico de falha.
**Depende de:** —
**Entregáveis:**
- mig 118 empresa_api_key (key_prefix 8ch, key_hash sha256, scopes TEXT[], expires_at NULLABLE, last_used_at/ip, revoked_at; UNIQUE (empresa_id,label); unique key_hash WHERE revoked_at IS NULL) + bloco RLS self-enroll
- shared/api_key.py::resolve_api_key (parse nxs_<eid>_<32hex>, sha256, SELECT por key_prefix sob empresa_scope(None,bypass=True), hmac.compare_digest no HASH, bump last_used_at)
- server/dependencies.py::verify_api_key (HTTPBearer auto_error=False; 401/403 NUNCA 500; chama set_request_context) + require_scope
- CRUD /api/disparador/api-keys (criar retorna segredo 1x, listar, revogar) sob verify_service_token
- frontend disparador/api-keys/ (segredo 1x + copy/toast) + Sidebar
**Riscos:**
- Esquecer set_request_context -> INSERT quebra InsufficientPrivilege
- Esquecer bloco RLS na migration -> vazamento cross-tenant
- Comparar token cru em vez do hash -> timing leak
**Testes:**
- TestSmoke: /api/disparador/api-keys -> 401 sem service token
- TestE2E: criar key -> listar -> revogar; segredo so na criacao
- TestE2EIsolamento (PRIMEIRO): key empresa A NAO le/escreve B; contexto ausente bloqueia; comparar com tabela sem RLS-enroll que vaza

### S1 — Captura server-side via Evolution -> staging (FUNCAO PRINCIPAL, em CI)
**Meta:** Provar o cano completo de captura+staging+dedup+membros via Evolution (mock em CI) ANTES do scraper fragil. Inverte a ordem do plano.
**Depende de:** S0
**Entregáveis:**
- mig 119 captura: captura_lote (tipo contatos|grupos|grupo_membros, contadores incl. pulados_invalido, status); contato_capturado (wa_jid IDENTIDADE, wa_lid, telefone NULLABLE, push_name, verified_name, is_business, wa_existe, validado_at, visto_ultima_vez_at; UNIQUE (empresa_id,wa_jid)); grupo (wa_group_id, invite_link, tipo; UNIQUE (empresa_id,wa_group_id)); grupo_membro (wa_jid NOT NULL, telefone NULLABLE, is_admin; UNIQUE (grupo_id,wa_jid)) + RLS em cada
- worker/evolution_client.py: fetch_contacts (POST /chat/findContacts), fetch_groups (GET /group/fetchAllGroups?getParticipants=true), fetch_group_participants, check_numbers (POST /chat/whatsappNumbers), health (/instance/info)
- shared/captura.py: normalize_capturado (telefone so de @s.whatsapp.net, is_business=verifiedName!=null), getWhatsAppId, upserts ON CONFLICT visto_ultima_vez_at=NOW(), promover_contatos->upsert_cliente, membros async via asyncio.create_task+_BG_TASKS+captura_lote.status
- server/routes/captura_evolution.py: POST /api/conexoes/{id}/captura/{contatos|grupos} (service-token+get_empresa_context); membros background task; GET leitura (total_disponivel mesmo truncado) + GET /api/disparador/contatos-unicos (DISTINCT wa_jid cross-grupo)
- frontend disparador/contatos/ read-only (browser, Capturar via Evolution, Promover p/ CRM bulk, push_name vazio->fallback telefone)
**Riscos:**
- Rate limit Evolution em contas grandes -> paginar+cap+background
- Membros so-LID perdidos se chave fosse telefone (resolvido por wa_jid)
- Store nao hidratado -> captura parcial (status=parcial, re-captura idempotente)
**Testes:**
- TestSmoke: /api/conexoes/{id}/captura/* + /contatos-unicos -> 401 sem auth
- TestE2E (docker_demo, EVOLUTION_OUTBOUND_MODE=mock): capturar contatos -> listar -> capturar grupos -> capturar membros (async, poll status) -> promover -> assert cliente; assert membro so-LID com wa_jid e telefone NULL
- TestE2EIsolamento: contatos/grupos da empresa A invisiveis p/ B

### S2 — Targeting do disparo + JITTER anti-ban + variaveis por destinatario
**Meta:** Conectar captura ao disparo: resolver origens, jitter aleatorio, validacao onWhatsApp e variaveis por destinatario. Reusa _dispatch_loop com mudanca minima de sleep.
**Depende de:** S1
**Entregáveis:**
- mig 120: campanha += origem_destinatarios CHECK, grupo_ids BIGINT[], captura_filtro JSONB, intervalo_min_ms, intervalo_max_ms; campanha_destinatario += variaveis JSONB
- shared/campanha.py: resolver no create (grupos->grupo_membro telefone NOT NULL; contatos_capturados filtrado; janela_24h->DISTINCT message_queue 24h; valida check_numbers batch p/ Evolution, marca invalidos falhou); _dispatch_loop troca asyncio.sleep fixo por random.uniform(min,max) por destinatario; _resolve_template_vars estendido
- server/routes/disparador.py: POST /api/disparador/preview (count_valido/invalido/sample/total_disponivel); create chama create_campanha; gating count Free<=25 (402)
- frontend create: selector origem, Intervalo min/max (s), Preparar->ENVIAR, progresso por destinatario (polling campanha_destinatario)
**Riscos:**
- check_numbers caro em lote grande -> cap + best-effort
- Resolver/gating rodam no create (fora do loop)
- Jitter mal calibrado ainda banir (default 3-8s Evolution)
**Testes:**
- TestSmoke: /api/disparador/preview + create -> 401 sem auth
- TestE2E (docker_demo, mock): origem=grupos -> preview retorna count+invalidos -> criar -> _dispatch_loop expande campanha_destinatario -> assert variaveis JSONB resolvidas + status por destinatario + jitter (mock conta sleeps)
- TestE2E gating: Free >25 -> 402

### S3 — Compliance & anti-ban estrutural
**Meta:** Tornar o disparo de sessao pessoal o mais seguro possivel - controles do produto-fonte + os que faltam no ecossistema.
**Depende de:** S2
**Entregáveis:**
- mig: disparador_opt_out (empresa_id, telefone; UNIQUE) + RLS; campanha += janela_inicio/janela_fim (quiet hours), kill_switch_pct
- shared/campanha.py: resolver exclui suprimidos; _dispatch_loop respeita quiet hours + auto-abort se falhas/enviados>kill_switch_pct (status aborted+reason)
- shared/plano_limits.py: caps por conexao.provider (Evolution cap diario baixo+intervalo grande; WABA por tier) lidos no resolver
- worker (process_message): STOP/descadastro -> INSERT disparador_opt_out
- frontend: aviso ToS/ban BLOQUEANTE (checkbox de aceite) na 1a campanha Evolution; UI opt-out
**Riscos:**
- Opt-out tem que rodar no resolver E em re-disparo de pendentes
- Quiet hours mal modelado bloqueia campanha legitima
- Kill-switch falso-positivo aborta campanha boa
**Testes:**
- TestSmoke: endpoints opt-out -> 401
- TestE2E (docker_demo): telefone no opt-out -> criar campanha com ele -> assert excluido; simular >30% falhas -> assert auto-abort
- TestE2E: worker recebe STOP -> assert INSERT opt-out

### S4 — API Oficial (WABA templates) + plan gating completo
**Meta:** Wire da aba API Oficial (reusa waba_templates + Embedded Signup) e gating Free/Premium. Aba data-driven por provider.
**Depende de:** S2
**Entregáveis:**
- mig 121: permissao rows disparador.*; plano.features disparador/disparador_media/disparador_max_contatos(Free=25)
- Reuso waba_templates.py (create/submit/list/sync) gated Premium; GET /api/disparador/janela-24h (DISTINCT message_queue)
- shared/plano_limits.py: tem_feature(disparador) libera modulo; resolver le features[disparador_max_contatos]; disparador_media gateia midia
- frontend: aba de canal data-driven por Conexao.provider; aba API Oficial reusa Embedded Signup + templates; midia via URL ou upload secundario
**Riscos:**
- plano.limite_* NULL=ilimitado -> cap Free via features
- Gating no loop em vez do resolver
**Testes:**
- TestSmoke: /api/disparador/janela-24h + template create -> 401
- TestE2E (docker_demo): Free template create -> 402; Premium cria; origem=janela_24h DISTINCT correto
- TestE2EIsolamento: templates/janela-24h escopados

### S5 — Extensao Chrome MV3 (scraping real) - quarentena
**Meta:** Construir a extensao depois do backend de captura validado. Scraping via hook window.Store, isolado/versionado. QA manual (sem CI).
**Depende de:** S0, S1
**Entregáveis:**
- extension/ MV3: manifest (host web.whatsapp.com/* + backend/*); background.ts (chrome.storage API key+URL, POSTs chunked+retry); content/scrape.ts+store-hook.ts (moduleRaid->Store.Contact/Chat/GroupMetadata; seletores/keys isolados + constante de versao + self-test scrape-health; aguarda Store.Chat>0 antes do 1o envio); popup/ (layout vertical unico, abas data-driven; NUMEROS+Validar+Contatos+Grupos+Modelo+Anexar+Intervalo min/max+Preparar->ENVIAR); options/ (Testar conexao via /health); lib/api.ts (Bearer, NUNCA ?key=)
- README.md pt-BR: AVISO ToS/ban + load-unpacked; quarentena (so /api/captura/* scope capture, fora do make ci, zip standalone NAO proxiado /uploads)
- ADR no vault: NAO hospedar nodeback Baileys (RAM+arquivo+key=identidade incompativel SaaS/RLS); conexao nao-oficial via Evolution
**Riscos:**
- Meta ofusca/rotaciona CSS -> preferir Store, isolar 1 arquivo
- Store eventualmente-consistente -> 1a captura incompleta
- ToS: extensao e o artefato mais exposto
**Testes:**
- QA manual: load unpacked -> web.whatsapp.com logado -> capturar -> ver no painel; scrape-health passa
- Backend coberto por S0/S1 (extensao POSTa contatos sample em CI via curl/httpx)

### S6 — Mensagens ricas viaveis (reacao + botoes WABA) + verdade tecnica
**Meta:** Entregar so o que renderiza: reacao (Evolution) e botoes via WABA. Fixar a verdade tecnica no plano. PIX real fica P3.
**Depende de:** S4
**Entregáveis:**
- worker/evolution_client.py: send_reaction (POST /message/sendReaction body {key, reaction}) - unico rico em conta pessoal
- shared/outbound.py: protocol send_buttons/send_reaction opcional por provider (Evolution->reacao; WABA->interactive/template; NotImplemented fallback)
- webhook inbound: trata templateButtonReplyMessage.selectedId E buttonsResponseMessage.selectedButtonId (clique p/ segmentacao)
- docs/plano: secao Mensagens ricas o que da e o que NAO da (botao clicavel so WABA; pagamento=WhatsApp Pay!=PIX; cartao=imagem+caption!=vCard); backlog P3 PIX BR Code (EMV+QR via send_media)
**Riscos:**
- Botoes Baileys deprecados em conta pessoal -> via Evolution = feature quebrada (gatear por provider)
- requestPaymentMessage instavel BR (nao prometer como PIX)
**Testes:**
- TestE2E (docker_demo, mock): send_reaction Evolution -> assert chamada; botoes so WABA
- Smoke: handler inbound parseia ambos shapes de resposta de botao

## Riscos & mitigações

| Sev | Risco | Mitigação |
|---|---|---|
| P0 | ToS/ban do WhatsApp (P0 PRODUTO): scraping + disparo de sessao pessoal (Baileys/Evolution = WhatsApp Web nao-oficial) viola os Termos e bane o NUMERO do cliente. Cadencia regular (intervalo fixo do plano) e assinatura de bot; numeros raspados sao sujos; denuncias sao o gatilho n1 de ban. | Jitter aleatorio min/max (S2); validacao onWhatsApp/check_numbers antes do disparo (S2); opt-out + quiet hours + kill-switch + warmup (S3); caps muito menores p/ Evolution vs WABA (S3); aviso ToS BLOQUEANTE com checkbox (S3); empurrar volume para WABA via gating (S4). |
| P0 | RLS no caminho API-key (P0): esquecer set_request_context em verify_api_key -> todo INSERT de captura quebra com InsufficientPrivilege; esquecer o bloco RLS self-enroll na migration -> vazamento cross-tenant (mig 101 nao pega tabelas novas). | verify_api_key chama set_request_context apos resolver a empresa (igual evolution_webhook.py:317); cada tabela self-enrola RLS na propria migration (template mig 111/112); TestE2EIsolamento PRIMEIRO no S0 (ambas direcoes). |
| P0 | Identidade por telefone perde membros so-LID (P0 dados): UNIQUE (grupo_id, telefone) e (empresa_id, telefone) do plano quebram p/ membros que so expoem @lid (multi-device, sem telefone), que somem silenciosamente. | wa_jid como identidade primaria (UNIQUE por wa_jid), telefone NULLABLE so de @s.whatsapp.net, wa_lid armazenado. Espelha cliente.whatsapp_lid (mig 046). TestE2E assertando membro so-LID com telefone NULL (S1). |
| P1 | Dispatcher in-process (P1): _dispatch_loop + _BG_TASKS perde a campanha em restart da API (recipients ficam pendente). Captura aumenta o tamanho das campanhas -> janela de perda maior. | Path reenviar pendentes (re-claim de campanha_destinatario status=pendente); fix duravel (dispatch via message_queue no worker) = divida tecnica fora de escopo, registrada. |
| P1 | Rate limit/latencia Evolution (P1): findContacts/fetchAllGroups e fetch_group_participants (groupMetadata por grupo) pesados em contas grandes; store hidrata em minutos (chats.set) -> 1a captura incompleta. | Captura assincrona por padrao (asyncio.create_task+_BG_TASKS+captura_lote.status); paginacao + cap por chamada; membros como lote dedicado separado; re-captura idempotente (ON CONFLICT). |
| P1 | Extensao Chrome fragil (P1): Meta ofusca/rotaciona classes CSS e pode quebrar moduleRaid/window.Store; e o artefato mais exposto a ToS. | Hook window.Store > DOM; isolar TODOS seletores/keys num scrape.ts com constante de versao + self-test scrape-health; quarentena (so /api/captura/* scope capture, sem service token, fora do make ci, zip standalone). ADR: nao hospedar nodeback Baileys. |
| P2 | plano.limite_* NULL=ilimitado (P2): usar colunas de limite p/ cap Free daria ilimitado por engano. | Cap Free de 25 via features[disparador_max_contatos] no resolver (HTTPException 402), nunca pelas colunas limite_*. get_plano_info() cache 30s. |
| P2 | Gotcha rewrite /uploads/* do Next (P2): midia via upload local exige mount /uploads/disparador + INTERNAL_API_URL no build (ARG), senao ECONNREFUSED em prod. | Preferir midia por URL (send_media_url) para Evolution - dispensa o mount; upload local so secundario/WABA com ARG correto e volume no compose. |
| P2 | Mensagens ricas que nao renderizam (P2): copiar literalmente payloads de botao/pagamento dos tutoriais (Baileys 4.0-4.4 descontinuado) entrega feature quebrada - botoes interativos bloqueados em conta pessoal; pagamento e WhatsApp Pay (instavel BR), nao PIX. | Gatear por provider (botao/list clicavel so WABA; Evolution so texto+midia+reacao); so send_reaction e portavel; PIX real = BR Code EMV+QR (backlog P3), nunca requestPaymentMessage; secao o que da e o que NAO da no plano. |

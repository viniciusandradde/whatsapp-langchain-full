# Análise — enviar áudio (nota de voz) e anexos pelo atendimento web, como no ZigChat

Data: 2026-09-18 (noite). Pedido do dono: "análise para enviar áudio e anexo pelo atendimento
chatnexus, igual do ZigChat". Levantado contra `master d52a451` e produção (`chat.vsanexus.com`).

## 1. Resumo em cinco linhas

- **O backend já faz tudo**: `POST /api/atendimentos/{id}/responder-midia` (multipart `arquivo` +
  `legenda`) manda **nota de voz** por `sendWhatsAppAudio` (bolha com player e forma de onda) e
  **imagem/vídeo/documento** por `sendMedia`, grava a bolha de saída e a timeline web já a
  renderiza. Quem usa hoje é **só o app Android** (grava OGG/Opus e anexa foto/documento).
- **O painel web não tem o botão** — nem clipe, nem microfone. É a única peça que falta para a
  paridade com o ZigChat neste ponto.
- **Demanda real**: em produção, os clientes mandaram **780 áudios em 30 dias** e o operador no
  navegador não consegue responder com áudio; só **10 mídias de saída** em 30 dias (todas do app).
- **Duas armadilhas técnicas** decidem o desenho: o WhatsApp só aceita **OGG/Opus** como nota de voz
  (Chrome grava WebM/Opus, Safari grava MP4/AAC — precisa **converter no servidor**, e o PyAV que já
  faz isso na voz do agente está na imagem da API); e as Server Actions do Next têm **corpo de 1 MB**
  (não há `bodySizeLimit` configurado) — o upload tem que ir por **Route Handler** (proxy) até a API.
- **Esforço**: 1 PR de backend pequena (conversão + testes) e 1 PR de frontend média (composer com
  clipe + microfone + prévia + proxy). WABA fica de fora (produção tem **3/3 conexões Evolution**).

## 2. O que existe hoje (verificado no código)

| Peça | Onde | Estado |
|---|---|---|
| Endpoint multipart | `server/routes/atendimento.py::responder_midia` | ✅ `arquivo` + `legenda` (legenda passa por `render_template`, aceita `{{cliente.nome}}`); perm `atendimento.write`; MIMEs `audio/*`, jpeg/png/webp/gif, mp4, pdf, doc/docx/xls/xlsx, txt; 400 para o resto |
| Envio | `shared/outbound.py::send_outbound_manual_midia` | ✅ `audio/*` → `send_audio` (PTT); resto → `send_media` com `mediatype`/`caption`/`fileName`; teto `MIDIA_MAX_BYTES = 16 MB`; erro explícito em conexão sem suporte |
| Evolution | `worker/evolution_client.py` | ✅ `sendWhatsAppAudio` (base64 ou URL) e `sendMedia`; **modo mock** devolve `mock-evo-audio-…` — dá para validar no dev sem WhatsApp |
| WABA | `integrations/waba/client.py` | ❌ só `send_message`/`send_typing`; mídia exigiria `POST /media` do Graph e envio por `media_id`. **Produção: 3/3 conexões ativas são Evolution** |
| Persistência | mig 146 `response_media_url`/`response_media_type` | ✅ grava como data-URL base64 **no banco** (a mídia inbound já foi para o MinIO nas migs 183/184; a de saída não) — 1,3 MB em 30 dias, irrelevante hoje |
| Timeline web | `atendimento-drawer.tsx` ~1442 | ✅ renderiza `response_media_*` (bolha de saída com player/imagem/documento) — construído para o app, serve o web sem mudança |
| App Android | `ui/conversa/Anexos.kt`, `MensagensRepository.kt` | ✅ grava `audio/ogg` (API ≥ 29; abaixo o mic fica desabilitado), anexa foto/documento, "Enviando áudio…" |
| **Composer web** | `atendimento-drawer.tsx` | ❌ **nada**: sem clipe, sem microfone, sem colar imagem, sem arrastar arquivo |

## 3. O alvo (o que o ZigChat entrega e o operador espera)

1. **Clipe** no composer: escolher arquivo (imagem, vídeo, PDF/Office), **colar** imagem da área de
   transferência, **arrastar** para a conversa; prévia (miniatura ou chip com nome/tamanho) antes de
   enviar; o texto do composer vira a **legenda**; remover antes de enviar.
2. **Microfone**: clicar para gravar (ou segurar), cronômetro, **cancelar**, ouvir a prévia,
   enviar; chega ao cliente como **nota de voz** (player + forma de onda), não como arquivo.
3. **Feedback**: bolha "Enviando…" e erro legível (permissão de microfone negada, arquivo grande,
   tipo não suportado, conexão sem suporte) — sem `alert()`, pelo `toast`/`ApiError` do kit.
4. Funciona **no celular pelo navegador** (o dono opera pelo telefone): Android Chrome e iOS Safari.

Fora do alvo nesta leva: transcrição do áudio de saída (só faz sentido para o inbound, que já
existe), envio por WABA, múltiplos arquivos numa só mensagem (o WhatsApp manda um por vez mesmo).

## 4. As lacunas e como fechar

### 4.1 Nota de voz: o formato (backend, obrigatório)

`MediaRecorder` grava em formato que depende do navegador: Chrome/Edge/Android →
`audio/webm;codecs=opus`; Firefox → `audio/ogg;codecs=opus`; **Safari/iOS → `audio/mp4` (AAC)**.
O WhatsApp só reconhece nota de voz em **OGG/Opus**; mandar WebM ou AAC por `sendWhatsAppAudio`
chega como arquivo (ou falha). O app resolve gravando direto em OGG — o navegador não tem essa opção.

Proposta: **converter no servidor**, em `shared/outbound.py` (ou `shared/audio.py`), antes do
`send_audio`: se o MIME de áudio não for `audio/ogg` com Opus → PyAV → OGG/Opus mono 48 kHz. É o
mesmo `_pcm16_para_ogg_opus` de `shared/voz.py` (voz do agente), generalizado para decodificar
qualquer entrada (`av.open` do WebM/MP4 → resample → `libopus`). WebM/Opus é só **remux** (sem
recodificar); MP4/AAC recodifica (≈ tempo real ÷ 20). Guardar no banco já convertido (`audio/ogg`),
para a bolha do painel tocar o mesmo arquivo que o cliente recebeu. Alternativa descartada:
codificar no navegador com WASM (opus-recorder) — 300 KB de bundle e mais um caminho a manter.

### 4.2 Tamanho do upload (frontend, obrigatório)

Server Action do Next tem corpo de **1 MB por padrão** (`next.config.ts` não define
`experimental.serverActions.bodySizeLimit`) — um PDF de 3 MB ou um vídeo falha antes de chegar à
API (o upload de avatar de hoje, ≤ 2 MB, provavelmente já tropeça acima de 1 MB). Proposta:
**Route Handler** `frontend/src/app/api/atendimentos/[id]/midia/route.ts` que repassa o multipart
para `INTERNAL_API_URL/api/atendimentos/{id}/responder-midia` com o service token e os headers de
sessão — mesmo desenho do proxy `/api/sse/empresa` (ADR-003: o token nunca vai ao navegador; nada
de axios no cliente). Sem limite artificial; o teto continua sendo o `MIDIA_MAX_BYTES` da API.

### 4.3 O composer (frontend)

`atendimento-drawer.tsx` já tem 1.900 linhas; a nova peça nasce em arquivo próprio,
`composer-midia.tsx`, plugada ao composer:

- **Estado**: `anexo: { file, kind: "imagem"|"video"|"documento"|"audio", previewUrl } | null`;
  `gravando: { inicio, stream, recorder, chunks } | null`.
- **Clipe**: `<input type="file" accept="…">` do kit (`Input`), + `onPaste` do textarea (imagem da
  área de transferência) + `onDrop` na coluna da conversa (overlay "Solte para anexar" — sem
  `fixed inset-0`; usar `absolute` dentro do painel). Validar tipo/tamanho no cliente com a mesma
  lista da API antes de subir.
- **Microfone**: `navigator.mediaDevices.getUserMedia({ audio: true })` → `MediaRecorder` com o
  `mimeType` que `isTypeSupported` aceitar (`audio/ogg;codecs=opus` → `audio/webm;codecs=opus` →
  `audio/mp4`); cronômetro; **Cancelar** descarta; **Parar** vira prévia com `<audio controls>`;
  **Enviar** sobe como `arquivo` com o MIME gravado (o servidor converte). Exige HTTPS (dev e prod
  têm) e permissão — negada → mensagem do kit, botão fica desabilitado até recarregar.
- **Envio**: `fetch("/api/atendimentos/{id}/midia", { method: "POST", body: FormData })` (mesma
  origem, proxy) → sucesso: `reload()` da timeline e limpar composer; erro: `ApiError` sem detalhe
  técnico (regra do painel: erro sem detalhe técnico).
- **Regras do repo**: só componentes do kit (o `<input type="file">` cru conta em `form_cru` —
  encapsular em `components/ui/` ou usar `Input`), sem `confirm()`, sem paleta crua,
  `prefetch={false}` não se aplica; `scripts/ui_metrics.sh --check` não pode subir.
- **Celular**: o botão do microfone precisa de `touch-action: none` se for "segurar para gravar";
  mais simples e robusto: **toque para gravar / toque para parar** (o app Android faz assim).

### 4.4 Persistência no bucket (backend, desejável, PR própria)

A mídia de saída ainda vai como base64 para `message_queue.response_media_url`, enquanto a inbound
já vive no MinIO (`media_arquivo_uuid`, migs 183/184) e some da coluna. Com o web enviando áudio,
o volume cresce (hoje 1,3 MB/30 d só pelo app). Proposta: coluna `response_media_arquivo_uuid`
(migration), gravar via `shared/arquivo` + `storage` e servir pelo mesmo `get_mensagem_midia`
(que já resolve o lado de saída — `test_get_mensagem_midia_lado_out_le_a_coluna_do_operador`).
Não bloqueia a leva; entra depois, com o mesmo cuidado da mig 184 (a retenção é decisão do dono —
ver a análise do base64 em `message_queue` na memória do projeto).

## 5. Riscos e gotchas conhecidos

- **HEIC do iPhone**: `accept="image/*"` no iOS pode entregar `image/heic`, que a API recusa (400).
  Tratar no cliente: pedir `image/jpeg,image/png,image/webp` explícitos (o iOS converte para JPEG
  ao restringir) e mostrar a mensagem certa.
- **Mock do dev** esconde Editar/Apagar de propósito (`mock-evo-`); a mídia enviada em mock aparece
  na timeline pela data-URL — validação visual funciona, entrega real só com a Evolution local
  (há uma Evolution local no dev) ou em produção.
- **Rate limit admin** (60 req/min por usuário) e o `MIDIA_MAX_BYTES` de 16 MB valem para o proxy.
- **Conexão WABA** devolve 400 com razão explícita — o botão deve existir, mas o erro precisa ser
  legível ("esta conexão não envia arquivos").
- **Áudio longo**: WebM de 5 min ≈ 2–4 MB; conversão em MP4/AAC de 5 min ≈ 15 s de CPU na API
  — aceitável; acima de ~10 min recusar no cliente (WhatsApp corta em 16 MB de qualquer jeito).
- **`response_apagada_at` e edição**: apagar mensagem já cobre mídia (mig 172); editar não se
  aplica (o WhatsApp não edita mídia) — esconder "Editar" na bolha de mídia, como o app.

## 6. Plano em PRs (ordem)

1. **PR A — backend `nota de voz em qualquer formato`** (`feat/outbound-audio-transcode`):
   conversão para OGG/Opus em `send_outbound_manual_midia` quando `audio/*` ≠ ogg/opus; unit com
   WebM/Opus e MP4/AAC gerados pelo próprio PyAV no teste; E2E `docker_demo` em modo mock (a row
   grava `audio/ogg`); `CLAUDE.md`. Sem migration.
2. **PR B — frontend `composer com clipe e microfone`** (`feat/composer-midia`): Route Handler
   proxy; `composer-midia.tsx` (clipe + colar + arrastar + prévia + legenda; microfone com
   cronômetro/cancelar/prévia); estados de erro; validação no dev com Playwright (upload de PDF e
   imagem, gravação simulada via `MediaRecorder` em headless com `--use-fake-device-for-media-stream`),
   capturas 1440/390, light/dark; `ui_metrics --check`.
3. **PR C — mídia de saída no bucket** (`feat/outbound-midia-storage`, migration): opcional, quando
   o volume justificar.

## 7. Decisões do dono

1. **Gravar por toque** (toque começa, toque para) ou **segurar para gravar** (estilo WhatsApp)?
   Recomendo toque: funciona igual no desktop e no celular, sem gesto que escapa.
2. **Vídeo** entra na 1ª leva? A API já aceita `video/mp4`; o custo é só a prévia. Recomendo sim.
3. **Legenda** = texto do composer no momento do envio (uma mensagem só, como o WhatsApp) — ok?
4. PR C (bucket) agora ou quando o volume pedir? Recomendo depois de medir 30 dias de uso web.

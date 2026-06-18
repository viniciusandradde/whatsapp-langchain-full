# Nexus Disparador — extensão Chrome (MV3)

Captura contatos e grupos do **WhatsApp Web** e envia para o ChatNexus
(endpoints `/api/captura/*`). Artefato em **quarentena**: distribuído como
pasta carregada manualmente (não vai pra Chrome Web Store), fala APENAS com
`/api/captura/*` usando a **API key da empresa** (escopo `capture`) — nunca o
token de serviço.

## ⚠️ Aviso (ToS / banimento / LGPD)

Capturar e disparar a partir de uma sessão **pessoal** do WhatsApp Web viola os
Termos do WhatsApp e pode **banir o número**. Não há volume "seguro" garantido.
O uso é responsabilidade do operador, que deve ter consentimento dos contatos.
Para volume sustentável, use o **canal oficial (WABA)** pelo painel.

## Instalação (load unpacked)

1. No painel do ChatNexus: **Disparador → API keys → Nova chave** (copie o
   segredo `nxs_<empresa>_<hex>` — exibido só uma vez).
2. Chrome → `chrome://extensions` → ative **Modo do desenvolvedor**.
3. **Carregar sem compactação** → selecione esta pasta `extension/`.
4. Abra as **Opções** da extensão → cole a **URL do backend**
   (ex.: `https://api.vsanexus.com`) e a **API key** → **Salvar** →
   **Testar conexão** (deve mostrar a empresa + escopos).

## Uso

1. Abra `https://web.whatsapp.com` e aguarde carregar (abra uma conversa).
2. Clique no ícone da extensão → aba **Captura (WPP)**:
   - **Capturar contatos** → envia contatos pro staging.
   - **Capturar grupos + membros** → envia grupos e seus membros.
3. No painel: **Disparador → Contatos/Grupos** para ver o que chegou e
   **promover** ao CRM; depois **Campanhas → Nova** para disparar.

## Arquitetura

```
popup.js ──(chrome.tabs.sendMessage)──▶ content.js (ISOLATED)
                                          │ injeta + postMessage
                                          ▼
                                        inject.js (MAIN world)
                                          │ hooka window.Store (moduleRaid/WPP)
                                          ▼ postMessage de volta
content.js ──(chrome.runtime.sendMessage)──▶ background.js (service worker)
                                               │ guarda API key (chrome.storage)
                                               ▼ POST Bearer
                                             /api/captura/*  (backend)
```

## Manutenção (parte frágil)

Todo o acoplamento com o WhatsApp Web vive em **`inject.js`** (constante
`SCRAPE_VERSION`). Quando a Meta mudar o store e a captura parar:
- Verifique o console da página (`[nexus] inject pronto …`).
- Ajuste `findStore()` / `scrapeContatos()` / `scrapeGrupos()` e suba a versão.
Nenhum outro arquivo precisa mudar.

## Identidade dos contatos

- Individuais do store vêm como `@c.us`; convertidos para `@s.whatsapp.net`.
- Membros multi-device podem vir como `@lid` (sem telefone) — enviados como
  `wa_jid`; o backend usa `wa_jid` como identidade primária.

## 📞 Ligações de voz (WaVoIP)

A aba **Ligações** do painel faz **ligações de voz automáticas** que tocam um
**áudio pré-gravado** ao serem atendidas. Usa o SDK oficial **WaVoIP**
(`@wavoip/wavoip-webphone`, vendorizado em `vendor/wavoip-sdk.js`), carregado no
MAIN world sob demanda pelo `content.js`.

- **Pré-requisito**: você precisa de **tokens WaVoIP** — serviço **pago**
  (wavoip.com). Cada token vincula 1 número WhatsApp. Cole os tokens na aba,
  "Conectar tokens" e confira que o device fica **online (🟢 open)**.
- **Mecânica**: `inject.js` registra os tokens (`wavoip.device.add`), intercepta
  o `getUserMedia` pra injetar o áudio no lugar do microfone, inicia a ligação
  (`wavoip.call.start`) e acompanha o estado por `getCallActive()` — ao atender,
  toca o áudio; ao terminar, desliga e passa pro próximo.
- **Híbrido**: registra a campanha no Nexus (origem `extensao`) — atendidas =
  `enviado`, não-atendidas/erro = `falhou` (com motivo). Aparece em `/campanhas`.
- ⚠️ **Risco**: ligação automática em massa **queima número rápido** e tem
  exposição legal (spam de voz). Defaults conservadores (20–45s entre ligações,
  pausa periódica). Use com consentimento, baixo volume e número descartável.

Toda a lógica WaVoIP (frágil — depende do SDK de terceiro) está isolada num
bloco próprio em `inject.js` (`window.wavoip*`).

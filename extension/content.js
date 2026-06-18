// Content script (ISOLATED world). Injeta inject.js no MAIN world (onde vive o
// window.Store do WhatsApp Web), faz a ponte de comandos popup→página e
// repassa os dados raspados para o background (que tem a API key).

// 1) Injeta o script de página (MAIN world) via recurso web-acessível.
(function injectPageScript() {
  try {
    const s = document.createElement("script");
    s.src = chrome.runtime.getURL("inject.js");
    s.onload = () => s.remove();
    (document.head || document.documentElement).appendChild(s);
  } catch (e) {
    console.warn("[nexus] falha ao injetar inject.js", e);
  }
})();

// Correlaciona pedidos com respostas da página.
const pendentes = new Map();
let seq = 0;

window.addEventListener("message", (ev) => {
  const d = ev.data;
  if (!d || d.source !== "nexus-page" || d.reqId == null) return;
  const cb = pendentes.get(d.reqId);
  if (cb) {
    pendentes.delete(d.reqId);
    cb(d);
  }
});

function pedirPagina(payload, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const reqId = ++seq;
    pendentes.set(reqId, resolve);
    window.postMessage({ source: "nexus-ext", reqId, ...payload }, "*");
    setTimeout(() => {
      if (pendentes.has(reqId)) {
        pendentes.delete(reqId);
        reject(new Error("timeout: o WhatsApp Web não respondeu"));
      }
    }, timeoutMs);
  });
}

function pedirScrape(what) {
  return pedirPagina({ cmd: "scrape", what });
}

// --- Disparo in-browser (WPPConnect/wa-js) ---
// wa-js (window.WPP) é pesado (~500KB) → injeta sob demanda, uma vez só.
let _waJsInjetado = false;
function injetarWaJs() {
  if (_waJsInjetado) return;
  _waJsInjetado = true;
  const s = document.createElement("script");
  s.src = chrome.runtime.getURL("vendor/wa-js.js");
  (document.head || document.documentElement).appendChild(s);
}

async function garantirWpp() {
  injetarWaJs();
  // dá um tempinho pro script carregar antes de checar (ensure-wpp espera onReady).
  return pedirPagina({ cmd: "ensure-wpp" }, 70000);
}

// --- WaVoIP (ligações de voz) — SDK pesado de terceiro, injeta sob demanda ---
let _waVoipInjetado = false;
function injetarWaVoip() {
  if (_waVoipInjetado) return;
  _waVoipInjetado = true;
  const s = document.createElement("script");
  s.src = chrome.runtime.getURL("vendor/wavoip-sdk.js");
  (document.head || document.documentElement).appendChild(s);
}

async function wavoipEnsure() {
  injetarWaVoip();
  return pedirPagina({ cmd: "wavoip-ensure" }, 70000);
}
async function wavoipConnect(tokens) {
  injetarWaVoip();
  return pedirPagina({ cmd: "wavoip-connect", tokens }, 70000);
}
async function wavoipStatus() {
  return pedirPagina({ cmd: "wavoip-status" }, 15000);
}
async function wavoipAudio(dataUrl) {
  return pedirPagina({ cmd: "wavoip-audio", dataUrl }, 30000);
}
async function wavoipCall(payload) {
  // payload: { telefone→phone, token, gain, ringTimeoutMs, maxTalkMs }
  return pedirPagina({ cmd: "wavoip-call", ...payload }, 180000);
}
async function wavoipStop() {
  return pedirPagina({ cmd: "wavoip-stop" }, 10000);
}

async function enviarMsg(telefone, texto, tipo) {
  return pedirPagina({ cmd: "send", telefone, texto, tipo }, 60000);
}

async function enviarMidia(telefone, dataUrl, filename, caption) {
  return pedirPagina(
    { cmd: "send", tipo: "midia", telefone, dataUrl, filename, caption },
    120000
  );
}

async function validarNumero(telefone) {
  return pedirPagina({ cmd: "validar", telefone }, 30000);
}

// Tipos ricos (enquete/localização/vcard/pix/evento/lista/convite): payload livre.
async function enviarTipo(telefone, payload) {
  return pedirPagina({ cmd: "send", telefone, ...payload }, 120000);
}

async function enviarBackground(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (r) => resolve(r || { ok: false, error: "sem resposta do background" }));
  });
}

// 2) Recebe comandos do popup.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "capturar" && msg.what === "contatos") {
        const page = await pedirScrape("contatos");
        if (page.error) throw new Error(page.error);
        const r = await enviarBackground({
          type: "ingest:contatos",
          contatos: page.contatos || [],
        });
        sendResponse({ ...r, raspados: (page.contatos || []).length });
      } else if (msg.type === "capturar" && msg.what === "grupos") {
        const page = await pedirScrape("grupos");
        if (page.error) throw new Error(page.error);
        const grupos = page.grupos || [];
        const rg = await enviarBackground({ type: "ingest:grupos", grupos });
        // membros por grupo (best-effort)
        let membrosTotal = 0;
        for (const g of grupos) {
          if (!g.membros || !g.membros.length) continue;
          const rm = await enviarBackground({
            type: "ingest:membros",
            waGroupId: g.wa_group_id,
            membros: g.membros,
          });
          if (rm.ok) membrosTotal += rm.data?.novos || 0;
        }
        sendResponse({ ...rg, raspados: grupos.length, membrosNovos: membrosTotal });
      } else if (msg.type === "wpp-status") {
        // E0: carrega wa-js sob demanda e reporta se a sessão está pronta/logada.
        const r = await garantirWpp();
        if (r.error) throw new Error(r.error);
        sendResponse({
          ok: true,
          ready: !!r.ready,
          authenticated: !!r.authenticated,
        });
      } else {
        sendResponse({ ok: false, error: "comando desconhecido" });
      }
    } catch (e) {
      sendResponse({ ok: false, error: e.message });
    }
  })();
  return true;
});

// Expõe a ponte (mesmo ISOLATED world) pro painel injetado (panel.js).
window.__nexusBridge = {
  garantirWpp,
  enviarMsg,
  enviarMidia,
  enviarTipo,
  validarNumero,
  enviarBackground,
  pedirScrape,
  // WaVoIP (ligações de voz)
  wavoipEnsure,
  wavoipConnect,
  wavoipStatus,
  wavoipAudio,
  wavoipCall,
  wavoipStop,
};

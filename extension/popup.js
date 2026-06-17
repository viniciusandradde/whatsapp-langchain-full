// Popup: abas + dispara captura na aba do WhatsApp Web (via content.js).

const log = (m) => (document.getElementById("log").textContent = m);

// Abas
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById("panel-" + t.dataset.tab).classList.add("active");
  });
});

document.getElementById("btn-options").addEventListener("click", () =>
  chrome.runtime.openOptionsPage()
);

async function abaWhatsApp() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/https:\/\/web\.whatsapp\.com\//.test(tab.url || "")) {
    throw new Error("Abra esta extensão na aba do web.whatsapp.com.");
  }
  return tab.id;
}

function enviar(tabId, what) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { type: "capturar", what }, (r) =>
      resolve(r || { ok: false, error: "sem resposta (recarregue o WhatsApp Web)" })
    );
  });
}

async function capturar(what, rotulo) {
  try {
    log(`Capturando ${rotulo}…`);
    const tabId = await abaWhatsApp();
    const r = await enviar(tabId, what);
    if (!r.ok) throw new Error(r.error);
    const d = r.data || {};
    let msg = `✅ ${rotulo}: ${r.raspados ?? "?"} raspados · ${d.novos ?? 0} novos`;
    if (r.membrosNovos != null) msg += ` · ${r.membrosNovos} membros novos`;
    log(msg);
  } catch (e) {
    log("❌ " + e.message);
  }
}

document
  .getElementById("btn-contatos")
  .addEventListener("click", () => capturar("contatos", "contatos"));
document
  .getElementById("btn-grupos")
  .addEventListener("click", () => capturar("grupos", "grupos"));

// E0 ZDG-clone: testa o carregamento do WPPConnect (wa-js) + estado da sessão.
function pedir(tabId, type) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { type }, (r) =>
      resolve(r || { ok: false, error: "sem resposta (recarregue o WhatsApp Web)" })
    );
  });
}

document.getElementById("btn-wpp-status").addEventListener("click", async () => {
  try {
    log("Carregando WPPConnect (pode levar alguns segundos)…");
    const tabId = await abaWhatsApp();
    const r = await pedir(tabId, "wpp-status");
    if (!r.ok) throw new Error(r.error);
    log(
      `WPP pronto: ${r.ready ? "sim" : "não"} · sessão logada: ${r.authenticated ? "sim ✅" : "não ❌"}`
    );
  } catch (e) {
    log("❌ " + e.message);
  }
});

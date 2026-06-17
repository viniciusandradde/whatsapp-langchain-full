// Opções: salva API key + URL do backend; testa via /api/disparador/status.

const $ = (id) => document.getElementById(id);
const msg = (m) => ($("msg").textContent = m);

(async function carregar() {
  const { apiKey, backendUrl } = await chrome.storage.local.get([
    "apiKey",
    "backendUrl",
  ]);
  if (apiKey) $("apiKey").value = apiKey;
  if (backendUrl) $("backendUrl").value = backendUrl;
})();

$("save").addEventListener("click", async () => {
  const apiKey = $("apiKey").value.trim();
  const backendUrl = $("backendUrl").value.trim().replace(/\/+$/, "");
  await chrome.storage.local.set({ apiKey, backendUrl });
  msg("✅ Salvo.");
});

$("test").addEventListener("click", async () => {
  // salva antes de testar
  const apiKey = $("apiKey").value.trim();
  const backendUrl = $("backendUrl").value.trim().replace(/\/+$/, "");
  await chrome.storage.local.set({ apiKey, backendUrl });
  msg("Testando…");
  chrome.runtime.sendMessage({ type: "test" }, (r) => {
    if (!r) return msg("❌ sem resposta do background");
    if (!r.ok) return msg("❌ " + r.error);
    const d = r.data || {};
    msg(
      `✅ Conectado · empresa ${d.empresa_id} · escopos: ${(d.scopes || []).join(", ")}`
    );
  });
});

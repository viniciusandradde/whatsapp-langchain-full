// Service worker (MV3) — guarda config (API key + URL do backend) e faz os
// POSTs autenticados para /api/captura/*. A API key NUNCA é exposta ao contexto
// da página (MAIN world); fica só aqui e no chrome.storage.

const SCOPE_HINT = "capture";

async function getConfig() {
  const { apiKey, backendUrl } = await chrome.storage.local.get([
    "apiKey",
    "backendUrl",
  ]);
  return {
    apiKey: (apiKey || "").trim(),
    backendUrl: (backendUrl || "").replace(/\/+$/, ""),
  };
}

async function apiPost(path, body, attempt = 0) {
  const { apiKey, backendUrl } = await getConfig();
  if (!apiKey || !backendUrl) {
    throw new Error("Configure a API key e a URL do backend nas opções.");
  }
  let resp;
  try {
    resp = await fetch(`${backendUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
    });
  } catch (e) {
    // erro de rede — retry exponencial até 2x
    if (attempt < 2) {
      await new Promise((r) => setTimeout(r, 1000 * Math.pow(5, attempt)));
      return apiPost(path, body, attempt + 1);
    }
    throw new Error(`Falha de rede: ${e.message}`);
  }
  if (resp.status === 401) throw new Error("API key inválida (401).");
  if (resp.status === 403)
    throw new Error(`API key sem escopo "${SCOPE_HINT}" (403).`);
  if (resp.status === 429) throw new Error("Rate limit excedido (429).");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

async function apiGet(path) {
  const { apiKey, backendUrl } = await getConfig();
  if (!apiKey || !backendUrl) {
    throw new Error("Configure a API key e a URL do backend nas opções.");
  }
  const resp = await fetch(`${backendUrl}${path}`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// Envia em lotes (o backend aceita até ~2000/request).
async function enviarEmLotes(path, key, itens, lote = 500) {
  let novos = 0;
  let total = 0;
  for (let i = 0; i < itens.length; i += lote) {
    const fatia = itens.slice(i, i + lote);
    const r = await apiPost(path, { [key]: fatia });
    novos += r.novos || 0;
    total += fatia.length;
  }
  return { total, novos };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "test") {
        const r = await apiGet("/api/disparador/status");
        sendResponse({ ok: true, data: r });
      } else if (msg.type === "ingest:contatos") {
        const r = await enviarEmLotes(
          "/api/captura/contatos",
          "contatos",
          msg.contatos || []
        );
        sendResponse({ ok: true, data: r });
      } else if (msg.type === "ingest:grupos") {
        const r = await enviarEmLotes(
          "/api/captura/grupos",
          "grupos",
          msg.grupos || []
        );
        sendResponse({ ok: true, data: r });
      } else if (msg.type === "ingest:membros") {
        const r = await apiPost(
          `/api/captura/grupos/${encodeURIComponent(msg.waGroupId)}/membros`,
          { membros: msg.membros || [] }
        );
        sendResponse({ ok: true, data: r });
      } else if (msg.type === "ext:campanha") {
        const r = await apiPost("/api/disparador/ext/campanha", {
          nome: msg.nome,
          mensagem: msg.mensagem || null,
          telefones: msg.telefones || [],
        });
        sendResponse({ ok: true, data: r });
      } else if (msg.type === "ext:report") {
        const r = await apiPost(
          `/api/disparador/ext/campanha/${msg.campanhaId}/report`,
          { items: msg.items || [] }
        );
        sendResponse({ ok: true, data: r });
      } else {
        sendResponse({ ok: false, error: "tipo desconhecido" });
      }
    } catch (e) {
      sendResponse({ ok: false, error: e.message });
    }
  })();
  return true; // resposta assíncrona
});

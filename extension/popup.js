// Popup do Nexus Disparador: captura (importar/CSV) + canal oficial (WABA).

const log = (m) => (document.getElementById("log").textContent = m);
const wlog = (m) => (document.getElementById("waba-log").textContent = m);

// ---- Abas ----
document.querySelectorAll(".nx-tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".nx-tab").forEach((x) => x.classList.remove("on"));
    document.querySelectorAll(".nx-panel").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    document.getElementById("panel-" + t.dataset.tab).classList.add("on");
    if (t.dataset.tab === "oficial") carregarConexoes();
  });
});

document
  .getElementById("btn-options")
  .addEventListener("click", () => chrome.runtime.openOptionsPage());

async function abaWhatsApp() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/https:\/\/web\.whatsapp\.com\//.test(tab.url || "")) {
    throw new Error("Abra a extensão na aba do WhatsApp Web.");
  }
  return tab.id;
}

function pedirAba(tabId, msg) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (r) =>
      resolve(r || { ok: false, error: "sem resposta (recarregue o WhatsApp Web)" })
    );
  });
}

function pedirBg(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (r) =>
      resolve(r || { ok: false, error: "sem resposta do serviço" })
    );
  });
}

// ---- Captura (importar pro Nexus) ----
async function capturar(what, rotulo) {
  try {
    log(`Importando ${rotulo}…`);
    const tabId = await abaWhatsApp();
    const r = await pedirAba(tabId, { type: "capturar", what });
    if (!r.ok) throw new Error(r.error);
    const d = r.data || {};
    let msg = `✅ ${rotulo}: ${r.raspados ?? "?"} lidos · ${d.novos ?? 0} novos`;
    if (r.membrosNovos != null) msg += ` · ${r.membrosNovos} membros novos`;
    log(msg);
  } catch (e) {
    log("❌ " + e.message);
  }
}

document.getElementById("btn-contatos").addEventListener("click", () => capturar("contatos", "contatos"));
document.getElementById("btn-grupos").addEventListener("click", () => capturar("grupos", "grupos"));

// ---- Exportar CSV (local, sem backend) ----
function csvCell(v) {
  const s = v == null ? "" : String(v);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function baixarCsv(nome, linhas) {
  const conteudo = linhas.map((l) => l.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob(["﻿" + conteudo], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function exportarCsv(what) {
  try {
    log(`Lendo ${what} do WhatsApp Web…`);
    const tabId = await abaWhatsApp();
    const r = await pedirAba(tabId, { type: "exportar", what });
    if (!r.ok) throw new Error(r.error);
    if (what === "contatos") {
      const c = r.contatos || [];
      baixarCsv("contatos.csv", [
        ["nome", "telefone", "wa_jid", "is_business"],
        ...c.map((x) => [
          x.name || x.push_name || "",
          (x.wa_jid || "").split("@")[0],
          x.wa_jid || "",
          x.is_business ? "sim" : "nao",
        ]),
      ]);
      log(`✅ ${c.length} contatos exportados.`);
    } else {
      const g = r.grupos || [];
      baixarCsv("grupos.csv", [
        ["nome", "wa_group_id", "participantes"],
        ...g.map((x) => [x.nome || "", x.wa_group_id || "", x.participantes_count ?? ""]),
      ]);
      log(`✅ ${g.length} grupos exportados.`);
    }
  } catch (e) {
    log("❌ " + e.message);
  }
}

document.getElementById("btn-csv-contatos").addEventListener("click", () => exportarCsv("contatos"));
document.getElementById("btn-csv-grupos").addEventListener("click", () => exportarCsv("grupos"));

// ---- Testar sessão WPP ----
document.getElementById("btn-wpp-status").addEventListener("click", async () => {
  try {
    log("Carregando WhatsApp Web (pode levar alguns segundos)…");
    const tabId = await abaWhatsApp();
    const r = await pedirAba(tabId, { type: "wpp-status" });
    if (!r.ok) throw new Error(r.error);
    log(`Sessão pronta: ${r.ready ? "sim" : "não"} · conectada: ${r.authenticated ? "sim ✅" : "não ❌"}`);
  } catch (e) {
    log("❌ " + e.message);
  }
});

// ---- Canal oficial (WABA via backend Nexus) ----
let _conexoesCarregadas = false;

async function carregarConexoes() {
  if (_conexoesCarregadas) return;
  const sel = document.getElementById("waba-conexao");
  const r = await pedirBg({ type: "ext:conexoes" });
  if (!r.ok) {
    wlog("❌ " + r.error);
    sel.innerHTML = '<option value="">—</option>';
    return;
  }
  const items = (r.data && r.data.items) || [];
  if (!items.length) {
    sel.innerHTML = '<option value="">Nenhuma conexão oficial</option>';
    wlog("Configure uma conexão WABA no painel (Conexões).");
    return;
  }
  sel.innerHTML =
    '<option value="">Selecione…</option>' +
    items.map((c) => `<option value="${c.id}">${c.display_name || c.from_number} (${c.provider})</option>`).join("");
  _conexoesCarregadas = true;
  wlog("Selecione a conexão e o template.");
}

document.getElementById("waba-conexao").addEventListener("change", async (e) => {
  const conexaoId = e.target.value;
  const selT = document.getElementById("waba-template");
  document.getElementById("waba-vars").innerHTML = "";
  if (!conexaoId) {
    selT.innerHTML = '<option value="">Selecione a conexão</option>';
    return;
  }
  selT.innerHTML = '<option value="">Carregando…</option>';
  const r = await pedirBg({ type: "ext:templates", conexaoId: Number(conexaoId) });
  if (!r.ok) {
    selT.innerHTML = '<option value="">—</option>';
    wlog("❌ " + r.error);
    return;
  }
  const items = (r.data && r.data.items) || [];
  if (!items.length) {
    selT.innerHTML = '<option value="">Nenhum template aprovado</option>';
    wlog("Aprove um template no painel (Conexões → Templates).");
    return;
  }
  window.__tpls = items;
  selT.innerHTML =
    '<option value="">Selecione…</option>' +
    items.map((t) => `<option value="${t.id}">${t.nome} (${t.idioma || "pt_BR"})</option>`).join("");
  wlog("Selecione o template.");
});

document.getElementById("waba-template").addEventListener("change", (e) => {
  const box = document.getElementById("waba-vars");
  box.innerHTML = "";
  const tpl = (window.__tpls || []).find((t) => String(t.id) === e.target.value);
  const vars = (tpl && tpl.variaveis) || [];
  if (!vars.length) return;
  box.innerHTML =
    '<label class="nx-label">Variáveis do template</label>' +
    vars
      .map(
        (v) =>
          `<div><input class="nx-input" data-var="${v}" placeholder="${v}" /></div>`
      )
      .join("");
});

document.getElementById("btn-waba-enviar").addEventListener("click", async () => {
  try {
    const conexaoId = Number(document.getElementById("waba-conexao").value);
    const templateId = Number(document.getElementById("waba-template").value);
    if (!conexaoId || !templateId) throw new Error("Selecione conexão e template.");
    const telefones = document
      .getElementById("waba-numeros")
      .value.split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!telefones.length) throw new Error("Informe ao menos um número.");
    const variaveis = {};
    document.querySelectorAll("#waba-vars input[data-var]").forEach((i) => {
      variaveis[i.dataset.var] = i.value;
    });
    const agenda = document.getElementById("waba-agenda").value;
    wlog(`Criando campanha para ${telefones.length} número(s)…`);
    const r = await pedirBg({
      type: "ext:campanha-template",
      body: {
        nome: `Disparo oficial ${new Date().toLocaleString("pt-BR")}`,
        conexao_id: conexaoId,
        message_template_id: templateId,
        template_variaveis: variaveis,
        telefones,
        scheduled_at: agenda ? new Date(agenda).toISOString() : null,
      },
    });
    if (!r.ok) throw new Error(r.error);
    const d = r.data || {};
    wlog(`✅ Campanha #${d.campanha_id} criada (${d.total} destinatários). O envio é feito pelo Nexus — acompanhe em Campanhas.`);
  } catch (e) {
    wlog("❌ " + e.message);
  }
});

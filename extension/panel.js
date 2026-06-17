// Painel Nexus Disparador (Slice E1) — injetado no WhatsApp Web (ISOLATED world).
// Envia in-browser via WPPConnect (window.__nexusBridge.enviarMsg → inject → WPP)
// e reporta os acks pro Nexus (ext:campanha + ext:report) = histórico no /campanhas.
//
// Anti-ban (pesquisa + ZDG): jitter aleatório min/max + delays escalonados + pausa
// longa periódica + gate de sessão `open`. play/pause/stop.

(function () {
  "use strict";
  if (window.__nexusPanelLoaded) return;
  window.__nexusPanelLoaded = true;

  const B = () => window.__nexusBridge || {};
  const $ = (id) => document.getElementById(id);

  // ---- estado do disparo ----
  let rodando = false;
  let pausado = false;
  let parar = false;

  // ---- parsing da lista + variáveis ----
  function parseLista(texto) {
    const linhas = (texto || "").split("\n");
    const out = [];
    for (const ln of linhas) {
      const campos = ln
        .split(/[,;\t]/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      if (!campos.length) continue;
      const tel = campos.find((c) => (c.match(/\d/g) || []).length >= 8);
      if (!tel) continue;
      const nome = campos.find((c) => c !== tel) || "";
      out.push({ telefone: tel, nome, campos });
    }
    return out;
  }

  function spintax(txt) {
    // {a|b|c} → escolha aleatória; resolve aninhados de dentro pra fora.
    let s = txt;
    let guard = 0;
    while (/\{[^{}]*\|[^{}]*\}/.test(s) && guard++ < 50) {
      s = s.replace(/\{([^{}]*\|[^{}]*)\}/g, (_, grp) => {
        const opts = grp.split("|");
        return opts[Math.floor(Math.random() * opts.length)];
      });
    }
    return s;
  }

  function aplicarVars(msg, row) {
    let m = msg;
    m = m.replace(/\[nome\]/gi, row.nome || "");
    m = m.replace(/\[telefone\]/gi, row.telefone || "");
    m = m.replace(/\[campo(\d+)\]/gi, (_, n) => row.campos[Number(n) - 1] || "");
    return spintax(m);
  }

  // ---- delays anti-ban escalonados ----
  function rnd(min, max) {
    return Math.floor(min + Math.random() * Math.max(0, max - min));
  }
  function delayMs(idx, min, max, pausaCada, pausaSeg) {
    let d = rnd(min, max);
    if (idx > 0 && idx % 5 === 0) d += 3000;
    if (idx > 0 && idx % 20 === 0) d += 8000;
    if (idx > 0 && idx % 50 === 0) d += 15000;
    // pausa longa periódica (descanso)
    if (pausaCada > 0 && idx > 0 && idx % pausaCada === 0) d += pausaSeg * 1000;
    return d;
  }

  // sleep cancelável (respeita pause/stop)
  async function sleepCancelavel(ms) {
    const fim = Date.now() + ms;
    while (Date.now() < fim) {
      if (parar) throw new Error("__parado__");
      while (pausado && !parar) await new Promise((r) => setTimeout(r, 300));
      if (parar) throw new Error("__parado__");
      await new Promise((r) => setTimeout(r, Math.min(300, fim - Date.now())));
    }
  }

  // ---- UI ----
  function montar() {
    if ($("nexus-fab")) return;
    const fab = document.createElement("button");
    fab.id = "nexus-fab";
    fab.title = "Nexus Disparador";
    fab.textContent = "🚀";
    fab.onclick = () => $("nexus-panel").classList.toggle("open");
    document.body.appendChild(fab);

    const p = document.createElement("div");
    p.id = "nexus-panel";
    p.innerHTML = `
      <div class="nx-head">
        <span>🚀 Nexus Disparador</span>
        <span class="nx-x" id="nx-close">✕</span>
      </div>
      <div class="nx-body">
        <label>Contatos (1 por linha — nome,telefone,campo1…)</label>
        <textarea id="nx-lista" rows="5" placeholder="João,+5511999999999
Maria,+5511988888888"></textarea>
        <label>Mensagem ([nome], [telefone], [campo1] · spintax {oi|olá})</label>
        <textarea id="nx-msg" rows="4" placeholder="Olá [nome]! {Tudo bem|Como vai}?"></textarea>
        <label>📎 Anexos (imagem/vídeo/áudio/doc — a mensagem vira legenda)</label>
        <input id="nx-files" type="file" multiple
          accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.zip">
        <div class="nx-hint" id="nx-files-info">Nenhum anexo. (mídia em massa = maior risco de ban)</div>
        <div class="nx-row">
          <div><label>Intervalo mín (s)</label><input id="nx-min" type="number" value="5" min="1"></div>
          <div><label>Intervalo máx (s)</label><input id="nx-max" type="number" value="15" min="1"></div>
        </div>
        <div class="nx-row">
          <div><label>Pausa a cada</label><input id="nx-pausa-cada" type="number" value="50" min="0"></div>
          <div><label>Pausa (s)</label><input id="nx-pausa-seg" type="number" value="600" min="0"></div>
        </div>
        <button class="nx-btn" id="nx-start">Iniciar disparo</button>
        <div class="nx-ctrls">
          <button class="nx-btn nx-sec" id="nx-pause" disabled>Pausar</button>
          <button class="nx-btn nx-stop" id="nx-stop" disabled>Parar</button>
        </div>
        <div class="nx-bar"><i id="nx-bar"></i></div>
        <div class="nx-log" id="nx-log">Pronto. Abra o WhatsApp Web logado.</div>
        <button class="nx-btn nx-sec" id="nx-csv" style="display:none">Baixar falhas (CSV)</button>
        <div class="nx-warn">⚠️ Disparo em massa pela sua sessão pode <b>banir o número</b>.
          Aqueça o número, use lotes pequenos e intervalos altos. Volume real → WABA oficial.</div>
      </div>`;
    document.body.appendChild(p);
    $("nx-close").onclick = () => p.classList.remove("open");
    $("nx-start").onclick = iniciar;
    $("nx-pause").onclick = () => {
      pausado = !pausado;
      $("nx-pause").textContent = pausado ? "Continuar" : "Pausar";
      log(pausado ? "⏸ Pausado." : "▶ Retomando…");
    };
    $("nx-stop").onclick = () => {
      parar = true;
      log("⏹ Parando…");
    };
    $("nx-files").onchange = async (e) => {
      const files = Array.from(e.target.files || []);
      anexos = [];
      for (const f of files) {
        if (f.size > 16 * 1024 * 1024) {
          log("❌ " + f.name + " ignorado (> 16MB).");
          continue;
        }
        try {
          const dataUrl = await new Promise((res, rej) => {
            const rd = new FileReader();
            rd.onload = () => res(rd.result);
            rd.onerror = rej;
            rd.readAsDataURL(f);
          });
          anexos.push({ dataUrl, filename: f.name });
        } catch (_) {
          log("❌ falha ao ler " + f.name);
        }
      }
      $("nx-files-info").textContent = anexos.length
        ? `${anexos.length} anexo(s) pronto(s). 1º leva a legenda.`
        : "Nenhum anexo.";
    };
  }

  function log(m) {
    const el = $("nx-log");
    if (el) el.textContent = m;
  }
  function setBar(pct) {
    const el = $("nx-bar");
    if (el) el.style.width = Math.max(0, Math.min(100, pct)) + "%";
  }
  let falhasCsv = [];
  let anexos = []; // [{dataUrl, filename}]

  async function iniciar() {
    if (rodando) return;
    const lista = parseLista($("nx-lista").value);
    const msg = $("nx-msg").value.trim();
    if (!lista.length) return log("❌ Adicione contatos válidos (com telefone).");
    if (!msg && !anexos.length)
      return log("❌ Escreva a mensagem ou anexe um arquivo.");
    const min = Math.max(1, Number($("nx-min").value || 5)) * 1000;
    const max = Math.max(min, Number($("nx-max").value || 15) * 1000);
    const pausaCada = Math.max(0, Number($("nx-pausa-cada").value || 0));
    const pausaSeg = Math.max(0, Number($("nx-pausa-seg").value || 0));

    rodando = true;
    pausado = false;
    parar = false;
    falhasCsv = [];
    $("nx-start").disabled = true;
    $("nx-pause").disabled = false;
    $("nx-stop").disabled = false;
    $("nx-csv").style.display = "none";

    try {
      // 1) gate de sessão
      log("Verificando sessão do WhatsApp…");
      const wpp = await B().garantirWpp();
      if (wpp.error) throw new Error(wpp.error);
      if (!wpp.authenticated)
        throw new Error("Sessão do WhatsApp não está logada. Escaneie o QR e tente.");

      // 2) cria campanha no Nexus (híbrido — histórico/CRM)
      let campanhaId = null;
      const criar = await B().enviarBackground({
        type: "ext:campanha",
        nome: "Disparo extensão " + new Date().toLocaleString("pt-BR"),
        mensagem: msg,
        telefones: lista.map((r) => r.telefone),
      });
      if (criar.ok) campanhaId = criar.data.campanha_id;
      else log("⚠️ Sem registro no Nexus (" + criar.error + ") — segue só local.");

      // 3) loop de envio
      let enviados = 0;
      let falhas = 0;
      let reportBuf = [];
      const total = lista.length;

      async function flushReport() {
        if (campanhaId && reportBuf.length) {
          const itens = reportBuf;
          reportBuf = [];
          await B().enviarBackground({
            type: "ext:report",
            campanhaId,
            items: itens,
          });
        }
      }

      for (let i = 0; i < total; i++) {
        if (parar) break;
        while (pausado && !parar) await new Promise((r) => setTimeout(r, 300));
        if (parar) break;

        const row = lista[i];
        const texto = aplicarVars(msg, row);
        let status = "enviado";
        let erro = null;
        let wamid = "";
        try {
          let r;
          if (anexos.length) {
            // 1º anexo leva a legenda (mensagem); os demais sem legenda.
            for (let a = 0; a < anexos.length; a++) {
              r = await B().enviarMidia(
                row.telefone,
                anexos[a].dataUrl,
                anexos[a].filename,
                a === 0 ? texto : ""
              );
              if (r.error || !r.ok) break;
            }
          } else {
            r = await B().enviarMsg(row.telefone, texto, "texto");
          }
          if (!r || r.error || !r.ok) {
            status = "falhou";
            erro = (r && r.error) || "falha desconhecida";
          } else {
            wamid = r.wamid || "";
          }
        } catch (e) {
          status = "falhou";
          erro = e.message;
        }
        if (status === "enviado") enviados++;
        else {
          falhas++;
          falhasCsv.push([row.nome, row.telefone, (erro || "").replace(/[\n,]/g, " ")]);
        }
        reportBuf.push({ telefone: row.telefone, status, erro, wamid });

        const feitos = i + 1;
        setBar((feitos / total) * 100);
        log(`Enviando ${feitos}/${total} · ✅ ${enviados} · ❌ ${falhas}`);
        if (reportBuf.length >= 10) await flushReport();

        // anti-ban: espera antes do próximo (não no último)
        if (feitos < total && !parar) {
          const d = delayMs(feitos, min, max, pausaCada, pausaSeg);
          await sleepCancelavel(d);
        }
      }
      await flushReport();
      log(
        `${parar ? "⏹ Parado" : "✅ Concluído"}: ${enviados} enviados · ${falhas} falhas de ${total}.`
      );
      if (falhasCsv.length) $("nx-csv").style.display = "block";
    } catch (e) {
      if (e.message !== "__parado__") log("❌ " + e.message);
    } finally {
      rodando = false;
      pausado = false;
      parar = false;
      $("nx-start").disabled = false;
      $("nx-pause").disabled = true;
      $("nx-pause").textContent = "Pausar";
      $("nx-stop").disabled = true;
    }
  }

  // export CSV de falhas
  document.addEventListener("click", (e) => {
    if (e.target && e.target.id === "nx-csv") {
      const linhas = [["nome", "telefone", "erro"], ...falhasCsv]
        .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
        .join("\n");
      const blob = new Blob([linhas], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "falhas-disparo.csv";
      a.click();
    }
  });

  // monta quando o WhatsApp Web carregar
  function aguardarEMontar() {
    if (document.querySelector("#pane-side, #app")) montar();
    else setTimeout(aguardarEMontar, 1500);
  }
  aguardarEMontar();
})();

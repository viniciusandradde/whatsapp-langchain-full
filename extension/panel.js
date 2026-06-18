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

  function telDoJid(jid) {
    if (jid && jid.endsWith("@s.whatsapp.net")) {
      const d = jid.split("@")[0].replace(/\D/g, "");
      return d ? "+" + d : null;
    }
    return null; // @lid não tem telefone derivável
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
      <div class="nx-tabs">
        <button class="nx-tab nx-tab-on" id="nx-tab-msg">💬 Mensagens</button>
        <button class="nx-tab" id="nx-tab-voz">📞 Ligações</button>
      </div>
      <div class="nx-body" id="nx-msg-body">
        <label>Contatos (1 por linha — nome,telefone,campo1…)</label>
        <textarea id="nx-lista" rows="5" placeholder="João,+5511999999999
Maria,+5511988888888"></textarea>
        <div class="nx-ctrls">
          <button class="nx-btn nx-sec" id="nx-validar">Validar nº</button>
          <button class="nx-btn nx-sec" id="nx-imp-contatos">Importar contatos</button>
          <button class="nx-btn nx-sec" id="nx-imp-grupos">Importar grupos</button>
        </div>
        <label>Mensagem ([nome], [telefone], [campo1] · spintax {oi|olá})</label>
        <textarea id="nx-msg" rows="4" placeholder="Olá [nome]! {Tudo bem|Como vai}?"></textarea>
        <label>Tipo de mensagem</label>
        <select id="nx-tipo">
          <option value="texto">Texto / mídia</option>
          <option value="enquete">Enquete</option>
          <option value="localizacao">Localização</option>
          <option value="vcard">Contato (vCard)</option>
          <option value="pix">PIX</option>
          <option value="evento">Evento</option>
          <option value="lista">Lista / menu</option>
          <option value="convite-grupo">Convite de grupo</option>
        </select>
        <div id="nx-tipo-campos">
          <div data-tipo="enquete" style="display:none">
            <label>Pergunta</label><input id="nx-enq-perg" placeholder="Qual sua preferência?">
            <label>Opções (1 por linha)</label><textarea id="nx-enq-opcoes" rows="3" placeholder="Opção A
Opção B"></textarea>
            <label><input type="checkbox" id="nx-enq-multi"> Permitir múltiplas</label>
          </div>
          <div data-tipo="localizacao" style="display:none">
            <div class="nx-row">
              <div><label>Latitude</label><input id="nx-loc-lat" placeholder="-23.55"></div>
              <div><label>Longitude</label><input id="nx-loc-lng" placeholder="-46.63"></div>
            </div>
            <label>Nome / endereço</label><input id="nx-loc-nome" placeholder="Loja Centro">
          </div>
          <div data-tipo="vcard" style="display:none">
            <label>Nome do contato</label><input id="nx-vc-nome" placeholder="Suporte">
            <label>Telefone do contato</label><input id="nx-vc-tel" placeholder="+5511999999999">
          </div>
          <div data-tipo="pix" style="display:none">
            <label>Tipo de chave</label>
            <select id="nx-pix-tipo"><option>CPF</option><option>CNPJ</option><option>EMAIL</option><option>PHONE</option><option>EVP</option></select>
            <label>Chave</label><input id="nx-pix-chave" placeholder="chave pix">
            <label>Nome do recebedor</label><input id="nx-pix-nome" placeholder="Empresa LTDA">
          </div>
          <div data-tipo="evento" style="display:none">
            <label>Nome do evento</label><input id="nx-ev-nome">
            <label>Descrição</label><input id="nx-ev-desc">
            <div class="nx-row">
              <div><label>Início</label><input id="nx-ev-inicio" type="datetime-local"></div>
              <div><label>Fim</label><input id="nx-ev-fim" type="datetime-local"></div>
            </div>
            <label>Local</label><input id="nx-ev-local">
          </div>
          <div data-tipo="lista" style="display:none">
            <label>Texto do botão</label><input id="nx-li-btn" placeholder="Ver opções">
            <label>Título / descrição</label><input id="nx-li-desc" placeholder="Cardápio">
            <label>Itens (titulo|descrição, 1 por linha)</label>
            <textarea id="nx-li-rows" rows="3" placeholder="Pizza|R$40
Refri|R$8"></textarea>
          </div>
          <div data-tipo="convite-grupo" style="display:none">
            <label>Group ID (xxxx@g.us)</label><input id="nx-cg-gid" placeholder="1203...@g.us">
            <label>Invite code</label><input id="nx-cg-code" placeholder="abc123">
            <label>Legenda</label><input id="nx-cg-cap" placeholder="Entra no grupo!">
          </div>
        </div>
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
          Aqueça o número, use lotes pequenos e intervalos altos.</div>
        <div class="nx-hint">📨 <b>Volume seguro / API Oficial (WABA)</b>: use o painel do
          Nexus → <a id="nx-link-painel" href="#" target="_blank" style="color:#075e54">Campanhas</a>
          (template aprovado, sem risco de ban, funciona no celular).</div>
      </div>
      <div class="nx-body" id="nx-voz-body" style="display:none">
        <div class="nx-warn">📞 <b>Ligações de voz automáticas (WaVoIP)</b> tocam um áudio
          pré-gravado. Requer <b>tokens WaVoIP</b> (serviço pago — wavoip.com). Ligação
          automática em massa <b>queima número rápido</b> e pode ter implicações legais
          (spam de voz). Use com consentimento e em baixo volume.</div>
        <label>Tokens WaVoIP (1 por linha)</label>
        <textarea id="nx-voz-tokens" rows="2" placeholder="cole aqui os tokens dos seus números WaVoIP"></textarea>
        <div class="nx-ctrls">
          <button class="nx-btn nx-sec" id="nx-voz-conectar">Conectar tokens</button>
          <button class="nx-btn nx-sec" id="nx-voz-status">Ver status</button>
        </div>
        <div class="nx-hint" id="nx-voz-devs">Nenhum device conectado.</div>
        <label>🔊 Áudio da ligação (mp3/ogg/wav — tocado ao atender)</label>
        <input id="nx-voz-audio" type="file" accept="audio/*">
        <div class="nx-hint" id="nx-voz-audio-info">Nenhum áudio.</div>
        <label>Contatos (1 por linha — nome,telefone)</label>
        <textarea id="nx-voz-lista" rows="5" placeholder="João,+5511999999999"></textarea>
        <div class="nx-row">
          <div><label>Intervalo mín (s)</label><input id="nx-voz-min" type="number" value="20" min="5"></div>
          <div><label>Intervalo máx (s)</label><input id="nx-voz-max" type="number" value="45" min="5"></div>
        </div>
        <div class="nx-row">
          <div><label>Toca por até (s)</label><input id="nx-voz-ring" type="number" value="40" min="10"></div>
          <div><label>Pausa a cada</label><input id="nx-voz-pausa-cada" type="number" value="30" min="0"></div>
        </div>
        <div class="nx-row">
          <div><label>Pausa (s)</label><input id="nx-voz-pausa-seg" type="number" value="600" min="0"></div>
          <div></div>
        </div>
        <button class="nx-btn" id="nx-voz-start">Iniciar ligações</button>
        <div class="nx-ctrls">
          <button class="nx-btn nx-sec" id="nx-voz-pause" disabled>Pausar</button>
          <button class="nx-btn nx-stop" id="nx-voz-stop" disabled>Parar</button>
        </div>
        <div class="nx-bar"><i id="nx-voz-bar"></i></div>
        <div class="nx-log" id="nx-voz-log">Pronto. Conecte os tokens e o áudio.</div>
        <button class="nx-btn nx-sec" id="nx-voz-csv" style="display:none">Baixar não-atendidas (CSV)</button>
      </div>`;
    document.body.appendChild(p);
    // tabs
    const setTab = (voz) => {
      $("nx-tab-msg").classList.toggle("nx-tab-on", !voz);
      $("nx-tab-voz").classList.toggle("nx-tab-on", voz);
      $("nx-msg-body").style.display = voz ? "none" : "block";
      $("nx-voz-body").style.display = voz ? "block" : "none";
    };
    $("nx-tab-msg").onclick = () => setTab(false);
    $("nx-tab-voz").onclick = () => setTab(true);
    // WaVoIP wiring
    $("nx-voz-conectar").onclick = vozConectar;
    $("nx-voz-status").onclick = vozStatus;
    $("nx-voz-audio").onchange = vozCarregarAudio;
    $("nx-voz-start").onclick = iniciarVoz;
    $("nx-voz-pause").onclick = () => {
      pausado = !pausado;
      $("nx-voz-pause").textContent = pausado ? "Continuar" : "Pausar";
      vozLog(pausado ? "⏸ Pausado." : "▶ Retomando…");
    };
    $("nx-voz-stop").onclick = () => {
      parar = true;
      vozLog("⏹ Parando…");
      B().wavoipStop && B().wavoipStop();
    };
    // pré-carrega tokens WaVoIP salvos
    try {
      chrome.storage.local.get(["wavoipTokens"], (r) => {
        if (r && Array.isArray(r.wavoipTokens) && r.wavoipTokens.length)
          $("nx-voz-tokens").value = r.wavoipTokens.join("\n");
      });
    } catch (_) {}
    $("nx-close").onclick = () => p.classList.remove("open");
    const link = $("nx-link-painel");
    if (link)
      link.onclick = async (e) => {
        e.preventDefault();
        const cfg = await B().enviarBackground({ type: "get-config" });
        let url = "https://chat.vsanexus.com/campanhas";
        if (cfg && cfg.backendUrl) {
          try {
            const u = new URL(cfg.backendUrl);
            url = `${u.protocol}//${u.host.replace(/^api\./, "chat.")}/campanhas`;
          } catch (_) {}
        }
        window.open(url, "_blank");
      };
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
    $("nx-validar").onclick = validarLista;
    $("nx-imp-contatos").onclick = () => importar("contatos");
    $("nx-imp-grupos").onclick = () => importar("grupos");
    $("nx-tipo").onchange = () => {
      const t = $("nx-tipo").value;
      document.querySelectorAll("#nx-tipo-campos > div").forEach((d) => {
        d.style.display = d.getAttribute("data-tipo") === t ? "block" : "none";
      });
    };
  }

  // Monta o payload do tipo rico selecionado (fixo p/ todos os destinatários).
  function payloadTipo(tipo) {
    if (tipo === "enquete") {
      return {
        tipo,
        pergunta: $("nx-enq-perg").value.trim(),
        opcoes: $("nx-enq-opcoes").value.split("\n").map((s) => s.trim()).filter(Boolean),
        multipla: $("nx-enq-multi").checked,
      };
    }
    if (tipo === "localizacao") {
      return {
        tipo,
        lat: $("nx-loc-lat").value.trim(),
        lng: $("nx-loc-lng").value.trim(),
        nome: $("nx-loc-nome").value.trim(),
        endereco: $("nx-loc-nome").value.trim(),
      };
    }
    if (tipo === "vcard") {
      return {
        tipo,
        contatoNome: $("nx-vc-nome").value.trim(),
        contatoTelefone: $("nx-vc-tel").value.trim(),
      };
    }
    if (tipo === "pix") {
      return {
        tipo,
        pixTipo: $("nx-pix-tipo").value,
        pixChave: $("nx-pix-chave").value.trim(),
        pixNome: $("nx-pix-nome").value.trim(),
      };
    }
    if (tipo === "evento") {
      return {
        tipo,
        evNome: $("nx-ev-nome").value.trim(),
        evDesc: $("nx-ev-desc").value.trim(),
        evInicio: $("nx-ev-inicio").value,
        evFim: $("nx-ev-fim").value,
        evLocal: $("nx-ev-local").value.trim(),
      };
    }
    if (tipo === "lista") {
      const titulo = $("nx-li-desc").value.trim() || "Opções";
      const rows = $("nx-li-rows")
        .value.split("\n")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((ln, i) => {
          const [t, d] = ln.split("|");
          return { rowId: "r" + i, title: (t || "").trim(), description: (d || "").trim() };
        });
      return {
        tipo,
        btn: $("nx-li-btn").value.trim() || "Ver opções",
        desc: $("nx-li-desc").value.trim(),
        titulo,
        sections: [{ title: titulo, rows }],
      };
    }
    if (tipo === "convite-grupo") {
      return {
        tipo,
        groupId: $("nx-cg-gid").value.trim(),
        inviteCode: $("nx-cg-code").value.trim(),
        caption: $("nx-cg-cap").value.trim(),
      };
    }
    return null;
  }

  function validarPayloadTipo(p) {
    if (p.tipo === "enquete" && (!p.pergunta || p.opcoes.length < 2))
      return "Enquete precisa de pergunta + 2 opções.";
    if (p.tipo === "localizacao" && (!p.lat || !p.lng))
      return "Informe latitude e longitude.";
    if (p.tipo === "vcard" && !p.contatoTelefone) return "Informe o telefone do contato.";
    if (p.tipo === "pix" && !p.pixChave) return "Informe a chave PIX.";
    if (p.tipo === "evento" && !p.evNome) return "Informe o nome do evento.";
    if (p.tipo === "lista" && !p.sections[0].rows.length) return "Adicione itens na lista.";
    if (p.tipo === "convite-grupo" && !p.groupId) return "Informe o Group ID.";
    return null;
  }

  async function validarLista() {
    if (rodando) return;
    const lista = parseLista($("nx-lista").value);
    if (!lista.length) return log("❌ Nada pra validar.");
    try {
      log("Verificando sessão…");
      const wpp = await B().garantirWpp();
      if (wpp.error) throw new Error(wpp.error);
      if (!wpp.authenticated) throw new Error("WhatsApp não logado.");
      const validos = [];
      let invalidos = 0;
      for (let i = 0; i < lista.length; i++) {
        const r = await B().validarNumero(lista[i].telefone);
        setBar(((i + 1) / lista.length) * 100);
        log(`Validando ${i + 1}/${lista.length} · ✅ ${validos.length} · ❌ ${invalidos}`);
        if (r.ok && r.exists) {
          // usa o número real (wid) quando vier, pra normalizar regra-do-9
          const real = telDoJid(r.wid || "") || lista[i].telefone;
          validos.push(
            [lista[i].nome, real, ...lista[i].campos.filter((c) => c !== lista[i].telefone && c !== lista[i].nome)]
              .filter(Boolean)
              .join(",")
          );
        } else {
          invalidos++;
        }
        await new Promise((res) => setTimeout(res, 400)); // rate-limit suave
      }
      $("nx-lista").value = validos.join("\n");
      log(`✅ ${validos.length} válidos · ❌ ${invalidos} removidos da lista.`);
      setBar(0);
    } catch (e) {
      log("❌ " + e.message);
    }
  }

  async function importar(tipo) {
    try {
      log(`Importando ${tipo} do WhatsApp…`);
      const page = await B().pedirScrape(tipo);
      if (page.error) throw new Error(page.error);
      const linhas = [];
      const vistos = new Set();
      const add = (nome, tel) => {
        if (!tel || vistos.has(tel)) return;
        vistos.add(tel);
        linhas.push((nome ? nome + "," : "") + tel);
      };
      if (tipo === "contatos") {
        for (const c of page.contatos || []) add(c.push_name || c.name || "", telDoJid(c.wa_jid));
      } else {
        for (const g of page.grupos || [])
          for (const m of g.membros || []) add("", telDoJid(m.wa_jid));
      }
      const atual = $("nx-lista").value.trim();
      $("nx-lista").value = (atual ? atual + "\n" : "") + linhas.join("\n");
      log(`✅ ${linhas.length} ${tipo === "contatos" ? "contatos" : "membros"} com telefone adicionados.`);
    } catch (e) {
      log("❌ " + e.message);
    }
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
    const tipo = $("nx-tipo").value;
    if (!lista.length) return log("❌ Adicione contatos válidos (com telefone).");
    let payloadFixo = null;
    if (tipo === "texto") {
      if (!msg && !anexos.length)
        return log("❌ Escreva a mensagem ou anexe um arquivo.");
    } else {
      payloadFixo = payloadTipo(tipo);
      const err = validarPayloadTipo(payloadFixo);
      if (err) return log("❌ " + err);
    }
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
          if (payloadFixo) {
            // tipo rico (enquete/pix/evento/lista/localização/vcard/convite)
            r = await B().enviarTipo(row.telefone, payloadFixo);
          } else if (anexos.length) {
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

  // ════════════════════════════════════════════════════════════════
  //  WaVoIP — ligações de voz automáticas (áudio pré-gravado)
  // ════════════════════════════════════════════════════════════════
  let vozAudio = null; // { dataUrl, filename }
  let vozTokensOk = []; // tokens com device 'open'
  let vozFalhasCsv = [];

  function vozLog(m) {
    const el = $("nx-voz-log");
    if (el) el.textContent = m;
  }
  function vozSetBar(pct) {
    const el = $("nx-voz-bar");
    if (el) el.style.width = Math.max(0, Math.min(100, pct)) + "%";
  }

  async function vozConectar() {
    const tokens = ($("nx-voz-tokens").value || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!tokens.length) return vozLog("❌ Cole pelo menos 1 token WaVoIP.");
    vozLog("Carregando SDK WaVoIP e registrando tokens…");
    try {
      const r = await B().wavoipConnect(tokens);
      if (r.error) throw new Error(r.error);
      // salva os tokens pra reuso (chrome.storage via content world).
      try {
        chrome.storage.local.set({ wavoipTokens: tokens });
      } catch (_) {}
      await vozStatus();
    } catch (e) {
      vozLog("❌ " + e.message);
    }
  }

  async function vozStatus() {
    try {
      const r = await B().wavoipStatus();
      if (r.error) throw new Error(r.error);
      const devs = r.devices || [];
      vozTokensOk = devs.filter((d) => d.status === "open").map((d) => d.token);
      const abertos = vozTokensOk.length;
      const linhas = devs
        .map((d) => `${d.status === "open" ? "🟢" : "⚪"} ${d.contact || d.token.slice(0, 8)} (${d.status})`)
        .join(" · ");
      $("nx-voz-devs").textContent = devs.length
        ? `${abertos}/${devs.length} online — ${linhas}`
        : "Nenhum device. Confira os tokens / vincule o número no WaVoIP.";
    } catch (e) {
      $("nx-voz-devs").textContent = "Status indisponível: " + e.message;
    }
  }

  async function vozCarregarAudio(e) {
    const f = (e.target.files || [])[0];
    if (!f) {
      vozAudio = null;
      $("nx-voz-audio-info").textContent = "Nenhum áudio.";
      return;
    }
    if (f.size > 16 * 1024 * 1024) {
      $("nx-voz-audio-info").textContent = "❌ áudio > 16MB.";
      return;
    }
    try {
      const dataUrl = await new Promise((res, rej) => {
        const rd = new FileReader();
        rd.onload = () => res(rd.result);
        rd.onerror = rej;
        rd.readAsDataURL(f);
      });
      vozAudio = { dataUrl, filename: f.name };
      $("nx-voz-audio-info").textContent = `🔊 ${f.name} pronto.`;
    } catch (_) {
      $("nx-voz-audio-info").textContent = "❌ falha ao ler o áudio.";
    }
  }

  async function iniciarVoz() {
    if (rodando) return;
    const lista = parseLista($("nx-voz-lista").value);
    if (!lista.length) return vozLog("❌ Adicione contatos válidos (com telefone).");
    if (!vozAudio) return vozLog("❌ Selecione o áudio da ligação.");
    if (!vozTokensOk.length) {
      await vozStatus();
      if (!vozTokensOk.length)
        return vozLog("❌ Nenhum número WaVoIP online. Conecte os tokens.");
    }
    const min = Math.max(5, Number($("nx-voz-min").value || 20)) * 1000;
    const max = Math.max(min, Number($("nx-voz-max").value || 45) * 1000);
    const ringMs = Math.max(10, Number($("nx-voz-ring").value || 40)) * 1000;
    const pausaCada = Math.max(0, Number($("nx-voz-pausa-cada").value || 0));
    const pausaSeg = Math.max(0, Number($("nx-voz-pausa-seg").value || 0));

    rodando = true;
    pausado = false;
    parar = false;
    vozFalhasCsv = [];
    $("nx-voz-start").disabled = true;
    $("nx-voz-pause").disabled = false;
    $("nx-voz-stop").disabled = false;
    $("nx-voz-csv").style.display = "none";

    try {
      vozLog("Preparando áudio…");
      const prep = await B().wavoipAudio(vozAudio.dataUrl);
      if (prep.error) throw new Error(prep.error);

      // híbrido: registra como campanha no Nexus (origem extensão)
      let campanhaId = null;
      const criar = await B().enviarBackground({
        type: "ext:campanha",
        nome: "Ligações WaVoIP " + new Date().toLocaleString("pt-BR"),
        mensagem: "[Ligação de voz] " + vozAudio.filename,
        telefones: lista.map((r) => r.telefone),
      });
      if (criar.ok) campanhaId = criar.data.campanha_id;
      else vozLog("⚠️ Sem registro no Nexus (" + criar.error + ") — segue só local.");

      let ok = 0;
      let naoAtendidas = 0;
      let falhas = 0;
      let reportBuf = [];
      const total = lista.length;

      async function flushReport() {
        if (campanhaId && reportBuf.length) {
          const itens = reportBuf;
          reportBuf = [];
          await B().enviarBackground({ type: "ext:report", campanhaId, items: itens });
        }
      }

      for (let i = 0; i < total; i++) {
        if (parar) break;
        while (pausado && !parar) await new Promise((r) => setTimeout(r, 300));
        if (parar) break;

        const row = lista[i];
        const token = vozTokensOk[i % vozTokensOk.length]; // round-robin
        let status = "enviado"; // atendida = "enviado" no modelo de campanha
        let erro = null;
        try {
          const r = await B().wavoipCall({
            telefone: row.telefone,
            phone: row.telefone,
            token,
            ringTimeoutMs: ringMs,
          });
          if (r.error) {
            status = "falhou";
            erro = r.error;
          } else if (r.status === "completed" && r.answered) {
            status = "enviado";
          } else if (r.status === "unanswered") {
            status = "falhou";
            erro = "não atendida";
          } else {
            status = "falhou";
            erro = r.error || "não completada";
          }
        } catch (e) {
          status = "falhou";
          erro = e.message;
        }

        if (status === "enviado") ok++;
        else {
          falhas++;
          if (erro === "não atendida") naoAtendidas++;
          vozFalhasCsv.push([row.nome, row.telefone, (erro || "").replace(/[\n,]/g, " ")]);
        }
        reportBuf.push({ telefone: row.telefone, status, erro, wamid: "" });

        const feitos = i + 1;
        vozSetBar((feitos / total) * 100);
        vozLog(`Ligando ${feitos}/${total} · ✅ ${ok} atendidas · 📵 ${naoAtendidas} · ❌ ${falhas - naoAtendidas} erro`);
        if (reportBuf.length >= 5) await flushReport();

        if (feitos < total && !parar) {
          const d = delayMs(feitos, min, max, pausaCada, pausaSeg);
          await sleepCancelavel(d);
        }
      }
      await flushReport();
      vozLog(`${parar ? "⏹ Parado" : "✅ Concluído"}: ${ok} atendidas · ${naoAtendidas} não-atendidas · ${falhas - naoAtendidas} erros de ${total}.`);
      if (vozFalhasCsv.length) $("nx-voz-csv").style.display = "block";
    } catch (e) {
      if (e.message !== "__parado__") vozLog("❌ " + e.message);
    } finally {
      rodando = false;
      pausado = false;
      parar = false;
      $("nx-voz-start").disabled = false;
      $("nx-voz-pause").disabled = true;
      $("nx-voz-pause").textContent = "Pausar";
      $("nx-voz-stop").disabled = true;
    }
  }

  // export CSV de falhas
  document.addEventListener("click", (e) => {
    if (e.target && e.target.id === "nx-voz-csv") {
      const linhas = [["nome", "telefone", "motivo"], ...vozFalhasCsv]
        .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
        .join("\n");
      const blob = new Blob([linhas], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "ligacoes-nao-atendidas.csv";
      a.click();
      return;
    }
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

// inject.js — roda no MAIN world da página web.whatsapp.com.
//
// ⚠️ PARTE FRÁGIL E ISOLADA: depende do store interno do WhatsApp Web, que a
// Meta ofusca/rotaciona. TODO o acoplamento com o WhatsApp vive aqui. Quando
// quebrar, ajuste só este arquivo e suba o SCRAPE_VERSION.
//
// Estratégia: tenta o window.WPP (se a página tiver WA-JS), senão usa moduleRaid
// pra achar o `Store` no webpack do WhatsApp. Normaliza JID pro padrão do
// backend (@s.whatsapp.net p/ individual; @lid e @g.us preservados).

(function () {
  "use strict";
  const SCRAPE_VERSION = "2026-06-16.1";

  // ---- moduleRaid mínimo (extrai módulos do webpack do WhatsApp) ----
  function moduleRaid() {
    const id = "nexusModuleRaid";
    const modules = {};
    const tag = self.webpackChunkwhatsapp_web_client || self.webpackChunk;
    if (!tag) return null;
    try {
      tag.push([
        [id],
        {},
        (req) => {
          for (const m of Object.keys(req.m)) {
            try {
              modules[m] = req(m);
            } catch (_) {}
          }
        },
      ]);
    } catch (_) {
      return null;
    }
    return modules;
  }

  function findStore() {
    // wa-js (WPP): os stores têm sufixo *Store (ContactStore, ChatStore…).
    // Normalizamos pros nomes que scrapeContatos/scrapeGrupos esperam.
    if (self.WPP && self.WPP.whatsapp) {
      const W = self.WPP.whatsapp;
      const Contact = W.ContactStore || W.Contact;
      if (Contact) {
        return {
          kind: "store",
          S: {
            Contact: Contact,
            Chat: W.ChatStore || W.Chat,
            GroupMetadata: W.GroupMetadataStore || W.GroupMetadata,
          },
        };
      }
    }
    if (self.Store && self.Store.Contact) return { kind: "store", S: self.Store };
    const mods = moduleRaid();
    if (!mods) return null;
    const S = {};
    for (const k of Object.keys(mods)) {
      const m = mods[k];
      if (!m || typeof m !== "object") continue;
      if (m.Contact && m.Chat) return { kind: "store", S: m };
      if (m.default && m.default.Contact) return { kind: "store", S: m.default };
      if (m.Contact && !S.Contact) S.Contact = m.Contact;
      if (m.Chat && !S.Chat) S.Chat = m.Chat;
      if (m.GroupMetadata && !S.GroupMetadata) S.GroupMetadata = m.GroupMetadata;
    }
    return S.Contact ? { kind: "store", S } : null;
  }

  function jidOf(model) {
    const id = model && (model.id || (model.attributes && model.attributes.id));
    let s = (id && (id._serialized || id)) || "";
    if (typeof s !== "string") s = String(s);
    return s;
  }

  function normJid(s) {
    if (!s) return "";
    if (s.endsWith("@c.us")) return s.replace("@c.us", "@s.whatsapp.net");
    return s; // @lid, @g.us, @s.whatsapp.net preservados
  }

  function arr(collection) {
    if (!collection) return [];
    if (typeof collection.getModelsArray === "function")
      return collection.getModelsArray();
    if (Array.isArray(collection.models)) return collection.models;
    if (Array.isArray(collection._models)) return collection._models;
    return [];
  }

  function scrapeContatos(S) {
    const out = [];
    for (const c of arr(S.Contact)) {
      const a = c.attributes || c;
      const jid = normJid(jidOf(c));
      if (!jid || jid.endsWith("@g.us")) continue;
      if (a.isMe) continue;
      const verified = a.verifiedName || null;
      out.push({
        wa_jid: jid,
        push_name: a.pushname || a.notify || null,
        name: a.name || a.formattedName || null,
        is_business: !!(a.isBusiness || verified),
        verified_name: verified,
      });
    }
    return out;
  }

  function scrapeGrupos(S) {
    const out = [];
    for (const ch of arr(S.Chat)) {
      const a = ch.attributes || ch;
      const jid = jidOf(ch);
      if (!jid.endsWith("@g.us")) continue;
      const meta =
        (S.GroupMetadata &&
          S.GroupMetadata.get &&
          S.GroupMetadata.get(jid)) ||
        null;
      // participants pode ser array OU coleção (getModelsArray) no wa-js.
      const parts = meta
        ? Array.isArray(meta.participants)
          ? meta.participants
          : arr(meta.participants)
        : [];
      const membros = parts
        .map((p) => {
          const pa = p.attributes || p;
          const pj = normJid(jidOf(p) || (pa.id && pa.id._serialized) || "");
          return pj ? { wa_jid: pj, is_admin: !!(pa.isAdmin || pa.isSuperAdmin) } : null;
        })
        .filter(Boolean);
      out.push({
        wa_group_id: jid,
        nome: a.name || a.formattedTitle || (meta && meta.subject) || null,
        descricao: (meta && meta.desc) || null,
        participantes_count: membros.length || (meta && meta.size) || 0,
        membros,
      });
    }
    return out;
  }

  window.addEventListener("message", (ev) => {
    const d = ev.data;
    if (!d || d.source !== "nexus-ext" || d.cmd !== "scrape") return;
    const reply = (payload) =>
      window.postMessage(
        { source: "nexus-page", reqId: d.reqId, version: SCRAPE_VERSION, ...payload },
        "*"
      );
    try {
      const found = findStore();
      if (!found) {
        reply({ error: "store do WhatsApp não encontrado (abra uma conversa e aguarde carregar)" });
        return;
      }
      const S = found.S;
      if (d.what === "contatos") reply({ contatos: scrapeContatos(S) });
      else if (d.what === "grupos") reply({ grupos: scrapeGrupos(S) });
      else reply({ error: "tipo inválido" });
    } catch (e) {
      reply({ error: "falha no scrape: " + (e && e.message) });
    }
  });

  // --- Disparo in-browser via WPPConnect (window.WPP, carregado sob demanda
  // pelo content.js). E0: ensure-wpp (sessão pronta?) + send texto. Tipos ricos
  // entram nas próximas slices. ---
  function jidParaChat(telefone) {
    const raw = String(telefone || "").trim();
    // Já é JID completo? respeita.
    if (/@(g\.us|c\.us|s\.whatsapp\.net|lid)$/.test(raw)) {
      return raw.replace("@s.whatsapp.net", "@c.us");
    }
    // Group ID formato antigo (com hífen): 1234567890-1234567890 → @g.us
    if (/^\d{8,}-\d{4,}$/.test(raw)) return raw + "@g.us";
    const digits = raw.replace(/\D/g, "");
    // Group ID novo: numérico longo (≥16 díg, ex. 120363…) → @g.us.
    // Telefones têm ~12-13 díg, então o limiar separa com folga.
    if (digits.length >= 16) return digits + "@g.us";
    return digits + "@c.us";
  }

  window.addEventListener("message", (ev) => {
    const d = ev.data;
    if (!d || d.source !== "nexus-ext") return;
    if (d.cmd !== "ensure-wpp" && d.cmd !== "send" && d.cmd !== "validar") return;
    const reply = (payload) =>
      window.postMessage({ source: "nexus-page", reqId: d.reqId, ...payload }, "*");
    (async () => {
      try {
        // Espera o window.WPP aparecer: o vendor/wa-js.js (~502KB) é injetado
        // via <script> e leva um tempinho pra executar. Sem o poll, o handler
        // falhava na hora com "WPP não carregado" (race) em vez de aguardar.
        async function aguardarWPP(timeoutMs) {
          const fim = Date.now() + timeoutMs;
          while (!window.WPP && Date.now() < fim) {
            await new Promise((r) => setTimeout(r, 150));
          }
          return window.WPP || null;
        }
        let WPP = window.WPP;
        if (!WPP) {
          // ensure-wpp pode esperar mais (acabou de injetar o script); os
          // demais comandos só rodam após ensure-wpp, então 5s basta.
          WPP = await aguardarWPP(d.cmd === "ensure-wpp" ? 20000 : 5000);
        }
        if (!WPP) {
          reply({
            error:
              "wa-js não carregou — recarregue o WhatsApp Web e tente de novo.",
          });
          return;
        }
        if (d.cmd === "validar") {
          // checa se o número tem WhatsApp (onWhatsApp). Retorna o número real
          // (wid) — útil pra regra-do-9 do BR.
          const num = String(d.telefone || "").replace(/\D/g, "");
          const res = await WPP.contact.queryExists(num);
          const wid = res && (res.wid?._serialized || res.wid || res.id?._serialized);
          reply({ ok: true, exists: !!res, wid: wid ? String(wid) : null });
          return;
        }
        if (d.cmd === "ensure-wpp") {
          if (!WPP.isReady) {
            await new Promise((res, rej) => {
              const t = setTimeout(() => rej(new Error("WPP não ficou pronto (60s)")), 60000);
              WPP.webpack.onReady(() => {
                clearTimeout(t);
                res();
              });
            });
          }
          let auth = false;
          try {
            auth = !!(WPP.conn && (await WPP.conn.isAuthenticated()));
          } catch (_) {}
          try {
            console.info("[nexus] WPP pronto", { ready: true, authenticated: auth });
          } catch (_) {}
          reply({ ok: true, ready: true, authenticated: auth });
          return;
        }
        // cmd === "send"
        const chatId = jidParaChat(d.telefone);
        let r;
        if (!d.tipo || d.tipo === "texto") {
          r = await WPP.chat.sendTextMessage(chatId, d.texto || "", {
            createChat: true,
          });
        } else if (d.tipo === "midia") {
          // d.dataUrl = data URI base64; wa-js auto-detecta o tipo pelo mime.
          r = await WPP.chat.sendFileMessage(chatId, d.dataUrl, {
            type: "auto-detect",
            caption: d.caption || undefined,
            filename: d.filename || "arquivo",
            createChat: true,
          });
        } else if (d.tipo === "enquete") {
          r = await WPP.chat.sendCreatePollMessage(
            chatId,
            d.pergunta || "",
            d.opcoes || [],
            { selectableCount: d.multipla ? (d.opcoes || []).length : 1, createChat: true }
          );
        } else if (d.tipo === "localizacao") {
          r = await WPP.chat.sendLocationMessage(chatId, {
            lat: Number(d.lat),
            lng: Number(d.lng),
            name: d.nome || undefined,
            address: d.endereco || undefined,
            createChat: true,
          });
        } else if (d.tipo === "vcard") {
          r = await WPP.chat.sendVCardContactMessage(
            chatId,
            { id: jidParaChat(d.contatoTelefone), name: d.contatoNome || "Contato" },
            { createChat: true }
          );
        } else if (d.tipo === "pix") {
          r = await WPP.chat.sendPixKeyMessage(chatId, {
            type: d.pixTipo,
            key: d.pixChave,
            name: d.pixNome,
            createChat: true,
          });
        } else if (d.tipo === "evento") {
          r = await WPP.chat.sendEventMessage(chatId, {
            name: d.evNome || "",
            description: d.evDesc || undefined,
            startTime: d.evInicio ? Math.floor(new Date(d.evInicio).getTime() / 1000) : undefined,
            endTime: d.evFim ? Math.floor(new Date(d.evFim).getTime() / 1000) : undefined,
            location: d.evLocal || undefined,
            createChat: true,
          });
        } else if (d.tipo === "lista") {
          r = await WPP.chat.sendListMessage(chatId, {
            buttonText: d.btn || "Ver opções",
            description: d.desc || "",
            title: d.titulo || undefined,
            footer: d.rodape || undefined,
            sections: d.sections || [],
            createChat: true,
          });
        } else if (d.tipo === "convite-grupo") {
          r = await WPP.chat.sendGroupInviteMessage(chatId, {
            groupId: d.groupId,
            inviteCode: d.inviteCode,
            inviteCaption: d.caption || undefined,
            groupName: d.groupName || undefined,
            createChat: true,
          });
        } else {
          reply({ error: "tipo de envio ainda não suportado: " + d.tipo });
          return;
        }
        const wamid =
          (r && (r.id?._serialized || r.id)) ||
          (r && r.sendMsgResult) ||
          "";
        reply({ ok: true, wamid: String(wamid || "") });
      } catch (e) {
        reply({ error: (e && e.message) || String(e) });
      }
    })();
  });

  // ════════════════════════════════════════════════════════════════
  //  WaVoIP — ligações de voz automáticas (SDK @wavoip/wavoip-webphone)
  //
  //  ⚠️ FRÁGIL/ISOLADO: depende do SDK de terceiros (window.wavoipWebphone /
  //  window.wavoip), carregado sob demanda pelo content.js (vendor/wavoip-sdk.js).
  //  Reimplementa a lógica do disparador ZDG (NÃO copia o código): registra
  //  tokens como devices, intercepta o getUserMedia pra injetar um áudio na
  //  chamada, e disca em massa lendo o estado via call.getCallActive().
  //
  //  Tokens WaVoIP = serviço PAGO (wavoip.com); cada token vincula 1 número.
  // ════════════════════════════════════════════════════════════════
  (function () {
    const _digits = (s) => String(s == null ? "" : s).replace(/\D/g, "");
    let _rendered = false;
    let _registered = {};
    let _ctx = null;
    let _intercepted = false;
    let _audioBuffer = null; // AudioBuffer pré-decodificado (1x por campanha)
    let _active = null; // { source, stream, started }

    function audioCtx() {
      if (_ctx) return _ctx;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) throw new Error("AudioContext indisponível.");
      _ctx = new AC();
      return _ctx;
    }

    // Substitui getUserMedia: enquanto houver áudio ativo (__nexusMP3Stream),
    // o SDK recebe o arquivo no lugar do microfone. Sem áudio ativo → original.
    function interceptMic() {
      if (_intercepted) return;
      const md = navigator.mediaDevices;
      if (!md || typeof md.getUserMedia !== "function") return;
      const orig = md.getUserMedia.bind(md);
      window.__nexusOrigGUM = orig;
      md.getUserMedia = function (constraints) {
        try {
          if (constraints && constraints.audio && window.__nexusMP3Stream) {
            return Promise.resolve(window.__nexusMP3Stream);
          }
        } catch (_) {}
        return orig(constraints);
      };
      _intercepted = true;
    }
    try {
      interceptMic();
    } catch (_) {}

    async function decodeAudio(dataUrl) {
      const resp = await fetch(dataUrl);
      const buf = await resp.arrayBuffer();
      const ctx = audioCtx();
      return await new Promise((resolve, reject) => {
        try {
          const p = ctx.decodeAudioData(buf, resolve, reject);
          if (p && typeof p.then === "function") p.then(resolve, reject);
        } catch (e) {
          reject(e);
        }
      });
    }

    function buildStream(buffer, gainVal) {
      const ctx = audioCtx();
      const dest = ctx.createMediaStreamDestination();
      const rec = { source: null, stream: dest.stream, started: false };
      if (buffer) {
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        src.loop = false;
        const gain = ctx.createGain();
        gain.gain.value = typeof gainVal === "number" ? gainVal : 1.0;
        src.connect(gain);
        gain.connect(dest);
        rec.source = src;
      }
      return rec;
    }

    function clearAudio() {
      if (_active) {
        try {
          if (_active.source && _active.started) _active.source.stop();
        } catch (_) {}
        try {
          _active.stream.getTracks().forEach((t) => t.stop());
        } catch (_) {}
      }
      _active = null;
      window.__nexusMP3Stream = null;
    }

    function startAudio(onEnded) {
      if (!_active || !_active.source || _active.started) return;
      try {
        const ctx = audioCtx();
        if (ctx.state === "suspended") {
          try {
            ctx.resume();
          } catch (_) {}
        }
        _active.started = true;
        if (typeof onEnded === "function")
          _active.source.onended = () => {
            try {
              onEnded();
            } catch (_) {}
          };
        _active.source.start();
      } catch (_) {}
    }

    function getActiveCall() {
      try {
        const c = window.wavoip && window.wavoip.call;
        if (c && typeof c.getCallActive === "function")
          return c.getCallActive() || null;
      } catch (_) {}
      return null;
    }

    function matchesPhone(active, phone) {
      if (!active) return false;
      const p = active.peer && (active.peer.phone || active.peer.number || active.peer.id);
      if (!p) return true; // softphone de 1 linha: a única ativa é a nossa
      const a = _digits(p);
      const b = _digits(phone);
      return !!a && !!b && (a === b || a.slice(-8) === b.slice(-8));
    }

    function isAnswered(active, phone) {
      if (!matchesPhone(active, phone)) return false;
      const st = String((active && active.status) || "").toUpperCase();
      if (!st) return true;
      return ["ACTIVE", "ACCEPTED", "IN_CALL", "ONGOING"].includes(st);
    }

    function hangup() {
      try {
        const c = window.wavoip && window.wavoip.call;
        if (c && typeof c.end === "function") return c.end();
        if (c && typeof c.hangup === "function") return c.hangup();
      } catch (_) {}
    }

    function getDevices() {
      try {
        const d = window.wavoip && window.wavoip.device;
        if (d && typeof d.get === "function") return d.get() || [];
      } catch (_) {}
      return [];
    }

    async function ensureSdk() {
      // content.js injeta vendor/wavoip-sdk.js; aqui só esperamos aparecer.
      let tries = 0;
      while (!window.wavoipWebphone && tries < 300) {
        await new Promise((r) => setTimeout(r, 100));
        tries++;
      }
      if (!window.wavoipWebphone)
        throw new Error("SDK WaVoIP não carregou (dê F5 no WhatsApp Web).");
      if (!_rendered) {
        try {
          if (typeof window.wavoipWebphone.render === "function") {
            await window.wavoipWebphone.render({
              buttonPosition: {
                x: window.innerWidth - 90,
                y: window.innerHeight - 130,
              },
            });
          }
        } catch (_) {}
        _rendered = true;
        try {
          const s = window.wavoip && window.wavoip.settings;
          if (s && s.setShowWidgetButton) s.setShowWidgetButton(false);
        } catch (_) {}
      }
    }

    function registerTokens(tokens) {
      const dev = window.wavoip && window.wavoip.device;
      const addFn =
        dev &&
        (typeof dev.add === "function"
          ? dev.add
          : typeof dev.addDevice === "function"
            ? dev.addDevice
            : null);
      if (!addFn) throw new Error("SDK WaVoIP indisponível (window.wavoip).");
      (tokens || []).forEach((tk) => {
        if (!tk || _registered[tk]) return;
        try {
          addFn.call(dev, tk);
          _registered[tk] = true;
        } catch (_) {}
      });
    }

    // Disca 1 número e resolve SÓ quando a ligação termina (pra o caller poder
    // discar a próxima). Toca o áudio ao atender; ao terminar o áudio, desliga.
    function placeCall(opts) {
      opts = opts || {};
      const phone = _digits(opts.phone);
      const token = opts.token;
      const ringMs = opts.ringTimeoutMs || 45000;
      const maxTalkMs = opts.maxTalkMs || 120000;
      const postAudioMs = typeof opts.postAudioMs === "number" ? opts.postAudioMs : 1200;
      const endOnAudioFinish = opts.endOnAudioFinish !== false;

      return new Promise((resolve) => {
        const c = window.wavoip && window.wavoip.call;
        if (!c) {
          resolve({ status: "failed", answered: false, error: "WaVoIP não conectado." });
          return;
        }
        if (!phone) {
          resolve({ status: "failed", answered: false, error: "Número inválido." });
          return;
        }

        let settled = false;
        let phase = "ringing";
        let answered = false;
        let answeredAt = 0;
        let endingAt = 0;
        let endingResult = "completed";
        const startedAt = Date.now();
        let poll = null;

        function finish(status, err) {
          if (settled) return;
          settled = true;
          if (poll) clearInterval(poll);
          clearAudio();
          resolve({
            status,
            answered,
            duration: answeredAt ? Math.round((Date.now() - answeredAt) / 1000) : 0,
            error: err || null,
          });
        }
        function beginEnding(result) {
          if (phase === "ending") return;
          phase = "ending";
          endingResult = result;
          endingAt = Date.now();
          hangup();
        }

        try {
          _active = buildStream(_audioBuffer, opts.gain);
          window.__nexusMP3Stream = _active.stream;
          const ctx0 = audioCtx();
          if (ctx0.state === "suspended") {
            try {
              ctx0.resume();
            } catch (_) {}
          }
        } catch (_) {
          window.__nexusMP3Stream = null;
        }

        let ret;
        try {
          ret =
            typeof c.start === "function"
              ? c.start(phone, { fromTokens: [token] })
              : c.startCall(phone, [token]);
        } catch (e) {
          finish("failed", (e && e.message) || "falha ao iniciar a ligação");
          return;
        }
        Promise.resolve(ret).then((r) => {
          if (r && r.err) {
            const em =
              r.err.message ||
              (r.err.devices ? "nenhum device pro token" : "falha ao iniciar");
            finish("failed", em);
          }
        }, () => {});

        poll = setInterval(() => {
          if (settled) return;
          const active = getActiveCall();
          const matched = matchesPhone(active, phone);
          if (phase === "ringing") {
            if (isAnswered(active, phone)) {
              phase = "answered";
              answered = true;
              answeredAt = Date.now();
              startAudio(() => {
                if (endOnAudioFinish)
                  setTimeout(() => beginEnding("completed"), postAudioMs);
              });
            } else if (Date.now() - startedAt > ringMs) {
              beginEnding("unanswered");
            }
            return;
          }
          if (phase === "answered") {
            if (!matched) {
              finish("completed");
              return;
            }
            if (Date.now() - answeredAt > maxTalkMs) beginEnding("completed");
            return;
          }
          // ending: resolve só quando a ligação realmente sai do slot ativo.
          if (!matched || Date.now() - endingAt > 8000) finish(endingResult);
        }, 500);
      });
    }

    window.addEventListener("message", (ev) => {
      const d = ev.data;
      if (!d || d.source !== "nexus-ext" || !d.cmd || d.cmd.indexOf("wavoip-") !== 0)
        return;
      const reply = (payload) =>
        window.postMessage({ source: "nexus-page", reqId: d.reqId, ...payload }, "*");
      (async () => {
        try {
          if (d.cmd === "wavoip-ensure") {
            await ensureSdk();
            reply({ ok: true, ready: true });
          } else if (d.cmd === "wavoip-connect") {
            await ensureSdk();
            registerTokens(d.tokens || []);
            reply({ ok: true });
          } else if (d.cmd === "wavoip-status") {
            const devs = getDevices().map((x) => ({
              token: x.token,
              status: String(x.status || "").toLowerCase(),
              contact: x.contact || null,
            }));
            reply({ ok: true, devices: devs });
          } else if (d.cmd === "wavoip-audio") {
            _audioBuffer = d.dataUrl ? await decodeAudio(d.dataUrl) : null;
            reply({ ok: true, segundos: _audioBuffer ? Math.round(_audioBuffer.duration) : 0 });
          } else if (d.cmd === "wavoip-call") {
            const r = await placeCall(d);
            reply({ ok: true, ...r });
          } else if (d.cmd === "wavoip-stop") {
            hangup();
            clearAudio();
            reply({ ok: true });
          } else {
            reply({ error: "comando wavoip desconhecido: " + d.cmd });
          }
        } catch (e) {
          reply({ error: (e && e.message) || String(e) });
        }
      })();
    });
  })();

  console.info("[nexus] inject pronto, scrape_version=" + SCRAPE_VERSION);
})();

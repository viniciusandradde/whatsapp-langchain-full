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
    if (self.WPP && self.WPP.whatsapp) return { kind: "wpp", S: self.WPP.whatsapp };
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
      const parts = meta ? arr({ models: meta.participants }) : [];
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
    const digits = String(telefone || "").replace(/\D/g, "");
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
        const WPP = window.WPP;
        if (!WPP) {
          reply({ error: "WPP (wa-js) não carregado na página" });
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

  console.info("[nexus] inject pronto, scrape_version=" + SCRAPE_VERSION);
})();

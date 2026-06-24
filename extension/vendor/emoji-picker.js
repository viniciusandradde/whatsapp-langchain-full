/* Emoji picker leve do Nexus — auto-contido, sem dependências externas.
 * Lista curada por categoria (os mais usados em atendimento/marketing BR).
 * API: NexusEmoji.attach(botaoEl, textareaEl) — abre um popover no clique e
 * insere o emoji na posição do cursor do textarea. Estilo via classes .nxe-*
 * (definidas em nexus-ui.css / panel.css). */
(function () {
  "use strict";
  if (window.NexusEmoji) return;

  var EMOJI = {
    "Rostos": "😀 😃 😄 😁 😆 😅 😂 🤣 🙂 🙃 😉 😊 😇 🥰 😍 🤩 😘 😗 😋 😛 🤪 🤗 🤔 😐 😶 🙄 😏 😴 😌 😎 🤓 🥳 😢 😭 😤 😠 😡 🤯 😱 😳 🥺 😬 🙏",
    "Gestos": "👍 👎 👌 ✌️ 🤞 🤙 👋 🙌 👏 🤝 💪 🫶 ✍️ 🤲 👇 👉 👈 ☝️ ✋ 🖐️",
    "Coração": "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💔 ❣️ 💕 💞 💓 💗 💖 💘 💝 ❤️‍🔥",
    "Objetos": "📱 💻 📞 ☎️ 📲 📧 ✉️ 📨 📩 📦 🛒 🏷️ 💰 💳 🧾 📅 📆 ⏰ ⌛ 🔔 📢 📣 🔑 ✅ ❌ ⚠️ ❗ ❓ ⭐ 🔥 🎉 🎁 🚀 💡",
    "Comida": "☕ 🍕 🍔 🍟 🌭 🍿 🥤 🍺 🍷 🎂 🍰 🧁 🍫 🍬 🍩 🍎 🍓 🍇",
    "Comércio": "🛍️ 🏪 🏬 🏠 🏢 📍 🗺️ 🚗 🛵 ✈️ 📈 📉 💹 🤑 💸",
  };

  function parse(str) {
    return str.split(/\s+/).filter(function (e) {
      // descarta tokens quebrados (defensivo)
      return e && /\p{Emoji}/u.test(e);
    });
  }

  function buildPopover(textarea) {
    var pop = document.createElement("div");
    pop.className = "nxe-pop";
    var cats = Object.keys(EMOJI);
    var grid = document.createElement("div");
    grid.className = "nxe-grid";
    function render(cat) {
      grid.innerHTML = "";
      parse(EMOJI[cat]).forEach(function (em) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "nxe-em";
        b.textContent = em;
        b.onclick = function (e) {
          e.preventDefault();
          insert(textarea, em);
        };
        grid.appendChild(b);
      });
    }
    var tabs = document.createElement("div");
    tabs.className = "nxe-tabs";
    cats.forEach(function (cat, i) {
      var t = document.createElement("button");
      t.type = "button";
      t.className = "nxe-tab" + (i === 0 ? " on" : "");
      t.textContent = cat;
      t.onclick = function (e) {
        e.preventDefault();
        tabs.querySelectorAll(".nxe-tab").forEach(function (x) {
          x.classList.remove("on");
        });
        t.classList.add("on");
        render(cat);
      };
      tabs.appendChild(t);
    });
    pop.appendChild(tabs);
    pop.appendChild(grid);
    render(cats[0]);
    return pop;
  }

  function insert(textarea, em) {
    var start = textarea.selectionStart || 0;
    var end = textarea.selectionEnd || 0;
    var v = textarea.value;
    textarea.value = v.slice(0, start) + em + v.slice(end);
    var pos = start + em.length;
    textarea.setSelectionRange(pos, pos);
    textarea.focus();
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function attach(btn, textarea) {
    if (!btn || !textarea) return;
    var pop = null;
    function close() {
      if (pop) {
        pop.remove();
        pop = null;
        document.removeEventListener("click", onDoc, true);
      }
    }
    function onDoc(e) {
      if (pop && !pop.contains(e.target) && e.target !== btn) close();
    }
    btn.onclick = function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (pop) return close();
      pop = buildPopover(textarea);
      // posiciona relativo ao container do botão
      var host = btn.offsetParent || btn.parentNode || document.body;
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      host.appendChild(pop);
      setTimeout(function () {
        document.addEventListener("click", onDoc, true);
      }, 0);
    };
  }

  window.NexusEmoji = { attach: attach };
})();

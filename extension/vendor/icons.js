/* Ícones do design system Nexus (estilo lucide — SVG stroke, herda currentColor).
 * Sem emoji. Uso: NexusIcons.svg("send", 16) → string SVG inline.
 * Os paths são do lucide.dev (ISC). */
(function () {
  "use strict";
  if (window.NexusIcons) return;

  var P = {
    // navegação / ações
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "message-circle":
      '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    phone:
      '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92Z"/>',
    smile:
      '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" x2="9.01" y1="9" y2="9"/><line x1="15" x2="15.01" y1="9" y2="9"/>',
    paperclip:
      '<path d="M13.234 20.252 21 12.3a3 3 0 0 0 0-4.243l-1.06-1.06a3 3 0 0 0-4.243 0l-9.193 9.193a5 5 0 0 0 0 7.071 5 5 0 0 0 7.071 0l9.193-9.193"/>',
    film:
      '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18M17 3v18M3 7.5h4M17 7.5h4M3 12h18M3 16.5h4M17 16.5h4"/>',
    music:
      '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "file-text":
      '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8M16 13H8M16 17H8"/>',
    "stop-circle":
      '<circle cx="12" cy="12" r="10"/><rect width="6" height="6" x="9" y="9"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    "alert-triangle":
      '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4M12 17h.01"/>',
  };

  function svg(name, size) {
    var d = P[name] || "";
    var s = size || 16;
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="' +
      s +
      '" height="' +
      s +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
      'style="display:inline-block;vertical-align:middle;flex:0 0 auto">' +
      d +
      "</svg>"
    );
  }

  window.NexusIcons = { svg: svg };
})();

/**
 * Service Worker mínimo do Nexus Chat AI (PWA installable).
 *
 * Critérios do Chrome pra PWA installable:
 *  1. HTTPS + manifest com name/icons 192+512/start_url/display=standalone ✓
 *  2. Service Worker registrado COM `fetch` handler que efetivamente
 *     responda (não basta listener vazio — precisa `event.respondWith`).
 *
 * Bug histórico: o handler antigo era vazio (sem respondWith), o que
 * NÃO satisfaz o critério "non-empty fetch handler" do Chrome — a barra
 * de instalação não aparecia, só fallback "Criar atalho".
 *
 * Estratégia atual: passthrough simples (sem cache). Quando quisermos
 * offline real, trocar pra stale-while-revalidate em assets estáticos
 * + network-first nas /api.
 */

const SW_VERSION = "v2-2026-05-19";

self.addEventListener("install", () => {
  // Ativa imediatamente sem esperar o user fechar abas
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Toma controle de todas as abas abertas
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Não interceptamos non-GET (POST/PATCH/etc) — Chrome não exige.
  if (req.method !== "GET") return;

  // Não interceptamos cross-origin (CDN, telemetria, etc.).
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Passthrough simples. respondWith é o que torna o handler "non-empty"
  // pra Chrome aceitar a página como installable.
  event.respondWith(
    fetch(req).catch(
      () =>
        new Response("", {
          status: 503,
          statusText: "offline",
        }),
    ),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

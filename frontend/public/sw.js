/**
 * Service Worker mínimo (Sprint Q.2 fix).
 *
 * Existe APENAS pra Chrome aceitar o site como PWA installable.
 * Não cacheia nada — toda request vai pra rede (passthrough).
 *
 * Quando quiser offline real (Sprint futuro), adicionar Cache API
 * pra shell + estratégia stale-while-revalidate em assets estáticos.
 */

self.addEventListener("install", (event) => {
  // Ativa imediatamente sem esperar o user fechar abas
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Toma controle de todas as abas abertas
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Passthrough — não cacheia, só observa.
  // Chrome exige fetch handler pra reconhecer SW.
  // event.respondWith(fetch(event.request)) é opcional aqui.
});

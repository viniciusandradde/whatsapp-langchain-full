"use client";

/**
 * Registra o service worker do PWA (Sprint Q.2).
 *
 * Componente client minúsculo que roda 1× no mount. Sem render.
 * Falha graceful — se SW não registra, app continua funcionando normal.
 */

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    // Só em produção — evita warning de cache stale em dev
    if (process.env.NODE_ENV !== "production") return;

    const register = async () => {
      try {
        await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("SW registration failed", err);
      }
    };
    void register();
  }, []);

  return null;
}

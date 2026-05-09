import type { MetadataRoute } from "next";

/**
 * PWA manifest — Sprint Q.2.
 *
 * Permite "Adicionar à tela inicial" no Chrome/Safari/Edge mobile.
 * Sem service worker (sem offline real) — versão "tier 1" installable.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nexus Chat AI",
    short_name: "Nexus Chat",
    description:
      "Painel administrativo Nexus Chat AI — VSA Tech. Atendimento via WhatsApp com agentes de IA.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#0d0d10",
    theme_color: "#0d0d10",
    lang: "pt-BR",
    categories: ["business", "productivity", "communication"],
    icons: [
      {
        src: "/icon.png",
        sizes: "256x256",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon.png",
        sizes: "256x256",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/apple-icon.png",
        sizes: "180x180",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}

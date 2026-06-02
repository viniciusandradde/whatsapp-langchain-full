import type { NextConfig } from "next";

// Proxy de estáticos (avatares de usuário + logos de empresa) servidos pela API
// via StaticFiles. Sem isso, `/uploads/*` cai no Next (404) — o domínio do front
// não conhece a rota. Roteia server-to-server pra API interna.
const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  // Gera build otimizado para Docker (copia apenas o necessário para rodar)
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/uploads/:path*",
        destination: `${API_URL}/uploads/:path*`,
      },
    ];
  },
};

export default nextConfig;

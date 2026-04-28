import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Gera build otimizado para Docker (copia apenas o necessário para rodar)
  output: "standalone",
};

export default nextConfig;

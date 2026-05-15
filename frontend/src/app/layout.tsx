import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppShell } from "@/components/app-shell";
import { EmpresaSwitcher } from "@/components/empresa-switcher";
import { InstallPwaPrompt } from "@/components/install-pwa-prompt";
import { PermissionsProvider } from "@/components/permissions-context";
import { ServiceWorkerRegister } from "@/components/sw-register";
import {
  SidebarProvider,
  SIDEBAR_INIT_SCRIPT,
} from "@/components/sidebar-context";
import { getMyEmpresas, getMyPermissions } from "@/lib/api";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

async function resolveEmpresaSwitcher() {
  // Tentamos buscar a lista de empresas do user — se a session estiver
  // ausente (rota /login, primeiro carregamento) ou a API falhar, o
  // switcher simplesmente não renderiza.
  try {
    const { empresas } = await getMyEmpresas();
    if (!empresas || empresas.length === 0) return null;
    const cookieStore = await cookies();
    const raw = cookieStore.get(ACTIVE_EMPRESA_COOKIE)?.value;
    const active = raw ? Number(raw) : empresas[0].id;
    return <EmpresaSwitcher empresas={empresas} activeEmpresaId={active} />;
  } catch {
    return null;
  }
}

async function resolveInitialPermissions() {
  // Carrega perms server-side pra o Provider já bootar com state válido.
  // Em /login (sem session), retorna [] — Client Components com
  // usePermission vão tratar como "não tem nada", o que é correto pro
  // contexto não-autenticado.
  try {
    const r = await getMyPermissions();
    return { permissoes: r.permissoes ?? [], perfis: r.perfis ?? [] };
  } catch {
    return { permissoes: [], perfis: [] };
  }
}

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Nexus Chat AI",
  description: "Painel administrativo Nexus Chat AI — VSA Tech",
  applicationName: "Nexus Chat AI",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icon.png", type: "image/png", sizes: "192x192" },
      { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: { url: "/apple-touch-icon.png", sizes: "180x180" },
    shortcut: "/favicon.ico",
  },
  appleWebApp: {
    capable: true,
    title: "Nexus Chat",
    statusBarStyle: "black-translucent",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
  themeColor: "#0d0d10",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [empresaSwitcher, initialPerms] = await Promise.all([
    resolveEmpresaSwitcher(),
    resolveInitialPermissions(),
  ]);
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        {/* Anti-FOUC: aplica data-theme do localStorage antes do React
            montar. Sem isso há flash escuro→claro no carregamento. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* Anti-flash sidebar: aplica data-sidebar-collapsed antes da
            hidratação. Evita flicker w-64 → w-16 quando colapsada. */}
        <script dangerouslySetInnerHTML={{ __html: SIDEBAR_INIT_SCRIPT }} />
      </head>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
        suppressHydrationWarning
      >
        {/* Ambient Light Orbs — suaves, mais difusos pra reduzir saturação visual */}
        <div
          aria-hidden
          className="fixed top-[-150px] left-[-150px] w-[600px] h-[600px] bg-brand-primary/[0.08] blur-[120px] rounded-full pointer-events-none -z-10 animate-float"
        />
        <div
          aria-hidden
          className="fixed bottom-[-100px] right-[-100px] w-[500px] h-[500px] bg-brand-secondary/[0.08] blur-[120px] rounded-full pointer-events-none -z-10 animate-float"
          style={{ animationDelay: "2s" }}
        />
        <div
          aria-hidden
          className="fixed top-[30%] right-[35%] w-[350px] h-[350px] bg-brand-primary/[0.05] blur-[110px] rounded-full pointer-events-none -z-10 animate-pulse-slow"
        />
        <PermissionsProvider
          initialPerms={initialPerms.permissoes}
          initialPerfis={initialPerms.perfis}
        >
          <SidebarProvider>
            <AppShell empresaSwitcher={empresaSwitcher}>{children}</AppShell>
          </SidebarProvider>
        </PermissionsProvider>
        <ServiceWorkerRegister />
        <InstallPwaPrompt />
      </body>
    </html>
  );
}

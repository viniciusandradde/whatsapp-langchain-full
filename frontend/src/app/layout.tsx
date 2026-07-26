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
import {
  DEFAULT_THEME,
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
  type ThemeName,
} from "@/lib/theme-constants";
import "./globals.css";

const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export interface EmpresaBrand {
  nome: string;
  logo_path: string | null;
  cor_primaria: string | null;
  cor_secundaria: string | null;
}

async function resolveEmpresaUI(): Promise<{
  switcher: React.ReactNode;
  brand: EmpresaBrand | null;
}> {
  // Busca empresas do user UMA vez — deriva o switcher + a marca (white-label)
  // da empresa ATIVA pra pintar logo/nome/cores no sidebar.
  try {
    const { empresas } = await getMyEmpresas();
    if (!empresas || empresas.length === 0) return { switcher: null, brand: null };
    const cookieStore = await cookies();
    const raw = cookieStore.get(ACTIVE_EMPRESA_COOKIE)?.value;
    const active = raw ? Number(raw) : null;
    // empresas vem ordenado is_default DESC → [0] é a default.
    const ativa = empresas.find((e) => e.id === active) ?? empresas[0];
    const brand: EmpresaBrand = {
      nome: ativa.nome_exibicao?.trim() || ativa.nome,
      logo_path: ativa.logo_path ?? null,
      cor_primaria: ativa.cor_primaria ?? null,
      cor_secundaria: ativa.cor_secundaria ?? null,
    };
    return {
      switcher: <EmpresaSwitcher empresas={empresas} activeEmpresaId={active} />,
      brand,
    };
  } catch {
    return { switcher: null, brand: null };
  }
}

/** CSS vars de marca por empresa — sobrescreve --brand-* sem tocar nos temas. */
function brandStyleVars(brand: EmpresaBrand | null): string | null {
  if (!brand?.cor_primaria && !brand?.cor_secundaria) return null;
  const lines: string[] = [];
  if (brand.cor_primaria) {
    lines.push(`--brand-primary:${brand.cor_primaria};`);
    lines.push(
      `--brand-primary-light:color-mix(in srgb, ${brand.cor_primaria}, white 18%);`
    );
    lines.push(
      `--brand-primary-dark:color-mix(in srgb, ${brand.cor_primaria}, black 18%);`
    );
  }
  if (brand.cor_secundaria) {
    lines.push(`--brand-secondary:${brand.cor_secundaria};`);
    lines.push(
      `--brand-secondary-light:color-mix(in srgb, ${brand.cor_secundaria}, white 18%);`
    );
    lines.push(
      `--brand-secondary-dark:color-mix(in srgb, ${brand.cor_secundaria}, black 18%);`
    );
  }
  return `:root{${lines.join("")}}`;
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
  // Obrigatorio pro PWA instalado no iPhone: sem `viewport-fit: cover` o iOS
  // NAO expoe as variaveis env(safe-area-inset-*), e o app renderiza embaixo
  // do notch e da barra de gestos. O padding que consome essas variaveis fica
  // em globals.css (.app-safe-area).
  viewportFit: "cover",
  // Barra do browser mobile segue o tema default (light). Quem usa tema
  // escuro só percebe na cor da barra — cosmético, sem media query por tema.
  themeColor: "#ffffff",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [{ switcher: empresaSwitcher, brand }, initialPerms] = await Promise.all([
    resolveEmpresaUI(),
    resolveInitialPermissions(),
  ]);
  const brandCss = brandStyleVars(brand);

  // Tema já no SSR (zero flash): cookie gravado pelo setTheme/init script.
  // Sem cookie válido → DEFAULT_THEME. O THEME_INIT_SCRIPT continua no
  // <head> só como migração (localStorage antigo sem cookie) e correção.
  const themeCookie = (await cookies()).get(THEME_STORAGE_KEY)?.value;
  const ssrTheme: ThemeName =
    themeCookie === "light" || themeCookie === "obsidian" || themeCookie === "black"
      ? themeCookie
      : DEFAULT_THEME;

  return (
    <html lang="pt-BR" data-theme={ssrTheme} suppressHydrationWarning>
      <head>
        {/* Anti-FOUC: aplica data-theme do localStorage antes do React
            montar. Sem isso há flash escuro→claro no carregamento. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* Anti-flash sidebar: aplica data-sidebar-collapsed antes da
            hidratação. Evita flicker w-64 → w-16 quando colapsada. */}
        <script dangerouslySetInnerHTML={{ __html: SIDEBAR_INIT_SCRIPT }} />
        {/* White-label: cores da marca da empresa ativa (sobrescreve --brand-*). */}
        {brandCss && (
          <style id="brand-vars" dangerouslySetInnerHTML={{ __html: brandCss }} />
        )}
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
            <AppShell empresaSwitcher={empresaSwitcher} brand={brand}>
              {children}
            </AppShell>
          </SidebarProvider>
        </PermissionsProvider>
        <ServiceWorkerRegister />
        <InstallPwaPrompt />
      </body>
    </html>
  );
}

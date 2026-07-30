import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppShell } from "@/components/app-shell";
import { EmpresaSwitcher } from "@/components/empresa-switcher";
import { InstallPwaPrompt } from "@/components/install-pwa-prompt";
import { PermissionsProvider } from "@/components/permissions-context";
import { ServiceWorkerRegister } from "@/components/sw-register";
import { SidebarProvider } from "@/components/ui/sidebar";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { getMyEmpresas, getMyPermissions } from "@/lib/api";
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

/**
 * Cor de texto legível sobre a cor da marca, por luminância relativa (WCAG).
 *
 * `color-mix` não sabe calcular contraste, e `--primary-foreground` fixo em
 * branco falha em marca clara (amarelo, lima, ciano): o rótulo do botão
 * primário some. Como o hex vem do banco e o layout é server-side, a conta é
 * feita aqui, onde dá pra fazer direito.
 */
function foregroundParaMarca(hex: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return "#ffffff";
  const canal = (i: number) => {
    const v = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const luminancia = 0.2126 * canal(0) + 0.7152 * canal(2) + 0.0722 * canal(4);
  // Ponto de virada 0.45: acima disso o branco perde contraste 4.5:1.
  return luminancia > 0.45 ? "#0a0a0a" : "#ffffff";
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
    lines.push(
      `--brand-primary-foreground:${foregroundParaMarca(brand.cor_primaria)};`
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
  // O primitivo Sidebar grava `sidebar_state` a cada toggle; ler aqui faz o SSR
  // já sair com a largura certa. Substitui o script anti-flash que existia.
  const sidebarAberta =
    (await cookies()).get("sidebar_state")?.value !== "false";

  return (
    // `suppressHydrationWarning` é exigência do next-themes: ele escreve a
    // classe de tema no <html> antes da hidratação, então servidor e cliente
    // divergem nesse atributo de propósito.
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        {/* White-label: cores da marca da empresa ativa (sobrescreve --brand-*). */}
        {brandCss && (
          <style id="brand-vars" dangerouslySetInnerHTML={{ __html: brandCss }} />
        )}
      </head>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
        suppressHydrationWarning
      >
        <ThemeProvider>
          <PermissionsProvider
            initialPerms={initialPerms.permissoes}
            initialPerfis={initialPerms.perfis}
          >
            <SidebarProvider defaultOpen={sidebarAberta}>
              <AppShell empresaSwitcher={empresaSwitcher} brand={brand}>
                {children}
              </AppShell>
            </SidebarProvider>
          </PermissionsProvider>
          <Toaster position="bottom-right" />
        </ThemeProvider>
        <ServiceWorkerRegister />
        <InstallPwaPrompt />
      </body>
    </html>
  );
}

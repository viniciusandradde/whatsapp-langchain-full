"use client";

/**
 * Shell da aplicação — controla se a sidebar aparece.
 *
 * Na rota /login, renderiza apenas o conteúdo (full viewport).
 * Nas demais rotas, renderiza sidebar + conteúdo com margem.
 *
 * `empresaSwitcher` (opcional) é renderizado no header da sidebar — server-
 * resolvido em `app/layout.tsx` pra evitar fetch client-side.
 */

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { useSidebar } from "@/components/sidebar-context";
import { TopNavTabs } from "@/components/top-nav-tabs";
import { cn } from "@/lib/utils";

export interface SidebarBrand {
  nome: string;
  logo_path: string | null;
}

export function AppShell({
  children,
  empresaSwitcher,
  brand,
}: {
  children: React.ReactNode;
  empresaSwitcher?: React.ReactNode;
  brand?: SidebarBrand | null;
}) {
  const pathname = usePathname();
  const { collapsed } = useSidebar();
  const isLogin = pathname === "/login";

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <>
      <Sidebar empresaSwitcher={empresaSwitcher} brand={brand} />
      <main
        className={cn(
          // p-4 no mobile: em 375px, 24px de padding de cada lado comem 13%
          // da largura util. Volta a p-6 a partir de md.
          "min-h-screen p-4 pt-16 md:p-6 md:pt-6",
          // Respeita notch/barra de gestos quando instalado como PWA no iOS.
          // Em browser comum env() resolve 0px e nada muda. Ver globals.css.
          "app-safe-area",
          "transition-[margin] duration-200 ease-out",
          collapsed ? "md:ml-16" : "md:ml-64"
        )}
      >
        <TopNavTabs />
        {children}
      </main>
    </>
  );
}

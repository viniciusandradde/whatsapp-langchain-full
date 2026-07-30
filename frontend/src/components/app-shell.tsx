"use client";

/**
 * Shell da aplicação — sidebar + área de conteúdo.
 *
 * Em `/login` renderiza só o conteúdo (viewport inteira).
 *
 * A largura máxima do conteúdo é decisão daqui: sem ela, 59 das 68 páginas
 * esticavam até a borda do monitor, e o campo de "slug" do formulário de agente
 * ficava com 1.500px pra receber 20 caracteres.
 */

import { usePathname } from "next/navigation";

import { AppSidebar } from "@/components/app-sidebar";
import type { SidebarBrand } from "@/components/nav-brand";
import { SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";

export type { SidebarBrand };

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

  if (pathname === "/login") {
    return <>{children}</>;
  }

  return (
    <>
      <AppSidebar empresaSwitcher={empresaSwitcher} brand={brand} />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-12 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <SidebarTrigger />
        </header>
        <div className="mx-auto w-full max-w-(--breakpoint-2xl) p-6">
          {children}
        </div>
      </SidebarInset>
    </>
  );
}

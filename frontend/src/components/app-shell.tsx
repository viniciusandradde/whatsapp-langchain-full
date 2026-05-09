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

export function AppShell({
  children,
  empresaSwitcher,
}: {
  children: React.ReactNode;
  empresaSwitcher?: React.ReactNode;
}) {
  const pathname = usePathname();
  const { collapsed } = useSidebar();
  const isLogin = pathname === "/login";

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <>
      <Sidebar empresaSwitcher={empresaSwitcher} />
      <main
        className={cn(
          "min-h-screen p-6 pt-16 md:pt-6",
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

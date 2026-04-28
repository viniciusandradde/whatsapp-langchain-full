"use client";

/**
 * Shell da aplicação — controla se a sidebar aparece.
 *
 * Na rota /login, renderiza apenas o conteúdo (full viewport).
 * Nas demais rotas, renderiza sidebar + conteúdo com margem.
 */

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <>
      <Sidebar />
      <main className="min-h-screen md:ml-64 p-6 pt-16 md:pt-6">
        {children}
      </main>
    </>
  );
}

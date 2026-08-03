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
import { CommandPalette, CommandPaletteTrigger } from "@/components/command-palette";
import type { SidebarBrand } from "@/components/nav-brand";
import { SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";

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
    // O `w-full` não é decorativo. O SidebarProvider fica no layout raiz e
    // envolve **até** o login com um wrapper `display:flex`. Sem esticar
    // aqui, o conteúdo vira um flex item, encolhe até o `max-w-sm` do
    // formulário e cola na borda esquerda — o `justify-center` de dentro
    // passa a centralizar numa faixa de 24rem, não na tela. Gritante em
    // monitor largo e quase invisível no celular, que é por que passou.
    return <div className="w-full">{children}</div>;
  }

  // `delay=300` vale pro painel inteiro: o default do Base UI é 600ms, que é
  // tempo demais pra uma barra de 5 botões de ícone numa linha de tabela — o
  // ponteiro já passou pro botão seguinte antes de a dica aparecer.
  return (
    <TooltipProvider delay={300}>
      <AppSidebar empresaSwitcher={empresaSwitcher} brand={brand} />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-12 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <SidebarTrigger />
          <CommandPaletteTrigger />
        </header>
        <CommandPalette />
        <div className="mx-auto w-full max-w-(--breakpoint-2xl) p-6">
          {children}
        </div>
      </SidebarInset>
    </TooltipProvider>
  );
}

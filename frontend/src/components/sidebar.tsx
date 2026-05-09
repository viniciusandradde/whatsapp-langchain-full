"use client";

/**
 * Sidebar de navegação do painel administrativo.
 *
 * Componente client-side para interatividade (estado de abertura no mobile,
 * highlight da rota ativa via usePathname).
 */

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Headphones,
  Bot,
  Activity,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Smartphone,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MyStatusToggle } from "@/components/my-status-toggle";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { resolveGroup } from "@/components/top-nav-tabs";
import { useSidebar } from "@/components/sidebar-context";
import { signOut } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

// Sidebar enxuta — 6 grupos top-level (refator 2026-05-07).
// Cada grupo abre uma rota default e mostra as sub-páginas relacionadas como
// tabs horizontais via componente <TopNavTabs />. Preserva URLs existentes.
//
// `grupo` bate com chave em NAV_TABS_BY_GROUP (top-nav-tabs.tsx) e com
// GRUPO_PREFIXOS (active state shared).
type NavGroup = {
  grupo: string;
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
};

const NAV_GROUPS: NavGroup[] = [
  { grupo: "visao", href: "/dashboard/ia", label: "Visão Geral", icon: LayoutDashboard },
  { grupo: "operacao", href: "/atendimento", label: "Operação", icon: Headphones },
  { grupo: "ia", href: "/agents", label: "IA & Conteúdo", icon: Bot },
  { grupo: "conectividade", href: "/connections", label: "Conectividade", icon: Smartphone },
  { grupo: "governanca", href: "/companies", label: "Governança", icon: ShieldCheck },
  { grupo: "observabilidade", href: "/traces", label: "Observabilidade", icon: Activity },
];

export function Sidebar({
  empresaSwitcher,
}: {
  empresaSwitcher?: React.ReactNode;
} = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const { collapsed, toggle } = useSidebar();

  // Active state por GRUPO: destaca o grupo cuja resolveGroup() bate com a
  // URL atual. Isso garante consistência com TopNavTabs (mesma lógica).
  const grupoAtivo = resolveGroup(pathname);
  function isGroupActive(grupo: string): boolean {
    return grupoAtivo === grupo;
  }

  async function handleSignOut() {
    setSigningOut(true);

    try {
      await signOut();
    } finally {
      setOpen(false);
      router.push("/login");
      router.refresh();
      setSigningOut(false);
    }
  }

  return (
    <>
      {/* Botão mobile — só aparece em telas pequenas */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed top-4 left-4 z-50 md:hidden text-white"
        onClick={() => setOpen(!open)}
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>

      {/* Overlay mobile */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar — obsidian-900 com accent laranja Obsidian.
          Mobile: drawer (open/closed via state).
          Desktop: collapsed/expanded via context (localStorage). */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col bg-sidebar",
          "transition-[transform,width] duration-200 ease-out",
          open ? "translate-x-0" : "-translate-x-full",
          "md:translate-x-0",
          collapsed ? "md:w-16" : "md:w-64",
          // Mobile sempre w-64 (drawer)
          "w-64"
        )}
      >
        {/* Header com marca */}
        <div className={cn(
          "flex h-16 items-center gap-3",
          collapsed ? "md:px-3 md:justify-center px-6" : "px-6"
        )}>
          <Image
            src="/vsa-logo.png"
            alt="VSA Tech"
            width={28}
            height={28}
            className="rounded shrink-0"
            unoptimized
          />
          <div className={cn(collapsed && "md:hidden")}>
            <span className="text-sm font-semibold tracking-tight text-sidebar-foreground">
              VSA Tech
            </span>
            <span className="block text-[10px] uppercase tracking-[0.15em] text-sidebar-foreground/50">
              operations
            </span>
          </div>
        </div>

        {/* Toggle collapse/expand — só desktop */}
        <button
          type="button"
          onClick={toggle}
          className={cn(
            "hidden md:flex absolute -right-3 top-14 z-50",
            "size-6 items-center justify-center rounded-full",
            "border border-sidebar-border bg-sidebar shadow-sm",
            "text-sidebar-foreground/70 hover:text-sidebar-foreground",
            "transition-colors"
          )}
          title={collapsed ? "Expandir menu" : "Recolher menu"}
          aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
        >
          {collapsed ? (
            <ChevronRight className="size-3.5" />
          ) : (
            <ChevronLeft className="size-3.5" />
          )}
        </button>

        {/* Separador sutil */}
        <div className="mx-4 h-px bg-sidebar-border" />

        {/* Switcher de empresa (esconde quando colapsado) */}
        {empresaSwitcher && !collapsed ? (
          <div className="px-3 pt-3 md:block">
            {empresaSwitcher}
          </div>
        ) : null}

        {/* Navegação — 6 grupos top-level. */}
        <nav className="flex-1 overflow-y-auto py-4">
          <div className={cn("space-y-1", collapsed ? "md:px-2 px-3" : "px-3")}>
            {NAV_GROUPS.map((g) => (
              <Link
                key={g.grupo}
                href={g.href}
                onClick={() => setOpen(false)}
                title={collapsed ? g.label : undefined}
                className={cn(
                  "flex items-center rounded-lg text-sm transition-all duration-150",
                  collapsed
                    ? "md:justify-center md:px-2 md:py-2.5 gap-3 px-3 py-2.5"
                    : "gap-3 px-3 py-2.5",
                  isGroupActive(g.grupo)
                    ? "bg-sidebar-accent text-brand-primary font-medium shadow-glow-orange"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                )}
              >
                <g.icon className="h-4 w-4 shrink-0" />
                <span className={cn(collapsed && "md:hidden")}>{g.label}</span>
              </Link>
            ))}
          </div>
        </nav>

        {/* Footer */}
        <div className={cn("pb-4", collapsed ? "md:px-2 px-3" : "px-3")}>
          <div className="mx-1 mb-3 h-px bg-sidebar-border" />
          <div className={cn(collapsed && "md:hidden")}>
            <MyStatusToggle />
            <ThemeSwitcher />
          </div>
          <button
            type="button"
            title={collapsed ? "Sair" : undefined}
            className={cn(
              "flex w-full items-center rounded-lg text-sm",
              "text-sidebar-foreground/50 transition-colors",
              "hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
              "disabled:opacity-50",
              collapsed
                ? "md:justify-center md:px-2 md:py-2.5 gap-3 px-3 py-2.5"
                : "gap-3 px-3 py-2.5"
            )}
            onClick={handleSignOut}
            disabled={signingOut}
          >
            <LogOut className="h-4 w-4 shrink-0" />
            <span className={cn(collapsed && "md:hidden")}>
              {signingOut ? "Saindo..." : "Sair"}
            </span>
          </button>
        </div>
      </aside>
    </>
  );
}

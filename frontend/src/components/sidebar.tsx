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
  UsersRound,
  MessageSquare,
  MessagesSquare,
  Bot,
  Brain,
  Activity,
  Building2,
  Braces,
  Building,
  CalendarDays,
  Clock,
  DollarSign,
  Flag,
  FolderTree,
  ListOrdered,
  ListTree,
  Megaphone,
  Plug,
  ScrollText,
  ShieldCheck,
  Smartphone,
  LogOut,
  Menu,
  Webhook,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MyStatusToggle } from "@/components/my-status-toggle";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { resolveGroup } from "@/components/top-nav-tabs";
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

      {/* Sidebar — obsidian-900 com accent laranja Obsidian */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-sidebar transition-transform md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Header com marca */}
        <div className="flex h-16 items-center gap-3 px-6">
          <Image src="/vsa-logo.png" alt="VSA Tech" width={28} height={28} className="rounded" unoptimized />
          <div>
            <span className="text-sm font-semibold tracking-tight text-sidebar-foreground">
              VSA Tech
            </span>
            <span className="block text-[10px] uppercase tracking-[0.15em] text-sidebar-foreground/50">
              operations
            </span>
          </div>
        </div>

        {/* Separador sutil */}
        <div className="mx-4 h-px bg-sidebar-border" />

        {/* Switcher de empresa (renderizado só com >1 empresa ou superadmin) */}
        {empresaSwitcher ? (
          <div className="px-3 pt-3">{empresaSwitcher}</div>
        ) : null}

        {/* Navegação enxuta — 6 grupos top-level. Sub-páginas viram tabs
            horizontais via <TopNavTabs /> no AppShell. */}
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <div className="space-y-1">
            {NAV_GROUPS.map((g) => (
              <Link
                key={g.grupo}
                href={g.href}
                onClick={() => setOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all duration-150",
                  isGroupActive(g.grupo)
                    ? "bg-sidebar-accent text-brand-primary font-medium shadow-glow-orange"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                )}
              >
                <g.icon className="h-4 w-4" />
                {g.label}
              </Link>
            ))}
          </div>
        </nav>

        {/* Footer */}
        <div className="px-3 pb-4">
          <div className="mx-1 mb-3 h-px bg-sidebar-border" />
          <MyStatusToggle />
          <ThemeSwitcher />
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent/50 hover:text-sidebar-foreground disabled:opacity-50"
            onClick={handleSignOut}
            disabled={signingOut}
          >
            <LogOut className="h-4 w-4" />
            {signingOut ? "Saindo..." : "Sair"}
          </button>
        </div>
      </aside>
    </>
  );
}

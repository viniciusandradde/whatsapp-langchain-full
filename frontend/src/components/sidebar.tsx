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
  MessageSquare,
  Bot,
  ListOrdered,
  ShieldCheck,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { signOut } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chats", label: "Conversas", icon: MessageSquare },
  { href: "/agents", label: "Agentes", icon: Bot },
  { href: "/queue", label: "Fila", icon: ListOrdered },
  { href: "/settings", label: "Segurança", icon: ShieldCheck },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  // Verifica se a rota está ativa (match exato para "/" e prefixo para sub-rotas)
  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
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

      {/* Sidebar — fundo escuro hawk-navy */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-sidebar transition-transform md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Header com marca */}
        <div className="flex h-16 items-center gap-3 px-6">
          <Image src="/logo-hawk.png" alt="rhawk.pro" width={28} height={28} className="rounded" unoptimized />
          <div>
            <span className="text-sm font-semibold tracking-tight text-sidebar-foreground">
              rhawk.pro
            </span>
            <span className="block text-[10px] uppercase tracking-[0.15em] text-sidebar-foreground/50">
              operations
            </span>
          </div>
        </div>

        {/* Separador sutil */}
        <div className="mx-4 h-px bg-sidebar-border" />

        {/* Navegação */}
        <nav className="flex-1 space-y-0.5 px-3 py-4">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all duration-150",
                isActive(item.href)
                  ? "bg-sidebar-accent text-hawk-blue font-medium shadow-sm"
                  : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-3 pb-4">
          <div className="mx-1 mb-3 h-px bg-sidebar-border" />
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

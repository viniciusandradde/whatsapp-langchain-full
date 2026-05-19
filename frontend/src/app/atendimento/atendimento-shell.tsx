"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { Menu, PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type SidebarState = "expanded" | "collapsed" | "hidden";

interface ShellContextValue {
  /** Estado visível pra parent. Em mobile, "collapsed" comporta como "hidden". */
  state: SidebarState;
  /** Em mobile, controla overlay (drawer); em desktop, é o mesmo que `state`. */
  mobileOpen: boolean;
  toggle: () => void;
  closeMobile: () => void;
  isMobile: boolean;
}

const ShellContext = createContext<ShellContextValue | null>(null);

export function useAtendimentoShell(): ShellContextValue {
  const ctx = useContext(ShellContext);
  if (!ctx) {
    throw new Error("useAtendimentoShell precisa estar dentro de AtendimentoShell");
  }
  return ctx;
}

interface Props {
  children: React.ReactNode;
}

const STORAGE_KEY = "atd-sidebar-collapsed";

/**
 * Wrapper Client Component que coordena layout responsivo:
 *
 * - **Desktop (md+)**: sidebar inline na flex, alterna entre w-64 (expanded)
 *   e w-14 (collapsed, só ícones). Estado persiste em localStorage.
 * - **Mobile (<md)**: sidebar é off-canvas (fixed left), abre/fecha via
 *   backdrop + botão. Não persiste — abre sempre fechada.
 */
export function AtendimentoShell({ children }: Props) {
  const [isMobile, setIsMobile] = useState(false);
  const [collapsedDesktop, setCollapsedDesktop] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Detecta breakpoint Tailwind md (768px)
  useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    const sync = () => setIsMobile(mql.matches);
    sync();
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);

  // Carrega preferência desktop do localStorage
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "true") setCollapsedDesktop(true);
  }, []);

  const toggle = useCallback(() => {
    if (isMobile) {
      setMobileOpen((v) => !v);
    } else {
      setCollapsedDesktop((v) => {
        const next = !v;
        window.localStorage.setItem(STORAGE_KEY, String(next));
        return next;
      });
    }
  }, [isMobile]);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  const state: SidebarState = isMobile
    ? "hidden" // sidebar inline some em mobile (vira overlay)
    : collapsedDesktop
      ? "collapsed"
      : "expanded";

  return (
    <ShellContext.Provider
      value={{ state, mobileOpen, toggle, closeMobile, isMobile }}
    >
      <div className="flex h-[calc(100vh-4rem)] gap-0 -m-6">
        {children}
      </div>
    </ShellContext.Provider>
  );
}

/**
 * Botão de toggle pra usar no header da lista de atendimentos.
 * Em desktop: PanelLeftClose/PanelLeftOpen. Em mobile: Menu (hambúrguer).
 */
export function ShellToggleButton({ className }: { className?: string }) {
  const { state, mobileOpen, toggle, isMobile } = useAtendimentoShell();
  const Icon = isMobile
    ? Menu
    : state === "expanded"
      ? PanelLeftClose
      : PanelLeftOpen;
  const label = isMobile
    ? mobileOpen
      ? "Fechar menu"
      : "Abrir menu"
    : state === "expanded"
      ? "Recolher sidebar"
      : "Expandir sidebar";
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn("h-9 w-9 p-0", className)}
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}

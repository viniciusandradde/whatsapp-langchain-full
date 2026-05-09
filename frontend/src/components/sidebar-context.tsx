"use client";

/**
 * Sidebar collapsed state — compartilhado entre Sidebar e AppShell.
 *
 * Persiste em localStorage. SSR-safe: default expanded até hidratar.
 * Anti-flash: o layout.tsx injeta script inline que aplica
 * `data-sidebar-collapsed` em <html> antes da hidratação.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "sidebar:collapsed";

interface SidebarContextValue {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (v: boolean) => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsedState] = useState(false);

  // Hidrata do localStorage (ou do data-attribute setado pelo anti-flash script)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "1") setCollapsedState(true);
    else if (stored === "0") setCollapsedState(false);
  }, []);

  const setCollapsed = useCallback((v: boolean) => {
    setCollapsedState(v);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, v ? "1" : "0");
      document.documentElement.dataset.sidebarCollapsed = v ? "1" : "0";
    }
  }, []);

  const toggle = useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
        document.documentElement.dataset.sidebarCollapsed = next ? "1" : "0";
      }
      return next;
    });
  }, []);

  return (
    <SidebarContext.Provider value={{ collapsed, toggle, setCollapsed }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  const ctx = useContext(SidebarContext);
  if (!ctx) {
    // Fallback safe quando usado fora do Provider (ex: SSR antes de mount)
    return { collapsed: false, toggle: () => {}, setCollapsed: () => {} };
  }
  return ctx;
}

/**
 * Anti-flash inline script — roda antes da hidratação React.
 * Lê localStorage e aplica `data-sidebar-collapsed` no <html>, evitando
 * piscar w-64 → w-16 quando o estado é "colapsado".
 */
export const SIDEBAR_INIT_SCRIPT = `
(function() {
  try {
    var v = localStorage.getItem("${STORAGE_KEY}");
    if (v === "1") {
      document.documentElement.dataset.sidebarCollapsed = "1";
    }
  } catch (e) {}
})();
`;

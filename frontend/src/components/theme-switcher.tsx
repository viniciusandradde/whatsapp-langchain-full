"use client";

import { useState } from "react";
import { Palette, Check } from "lucide-react";

import { useTheme, THEMES } from "@/lib/theme";

/**
 * Botão "Tema" que abre dropdown com 3 paletas. Pequeno o suficiente
 * pra entrar no footer do sidebar; persiste via localStorage.
 */
export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Palette className="h-4 w-4" />
        Tema
        <span className="ml-auto text-xs text-sidebar-foreground/40">
          {THEMES.find((t) => t.id === theme)?.emoji}
        </span>
      </button>

      {open && (
        <>
          {/* overlay pra fechar ao clicar fora */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <ul
            className="absolute bottom-full left-0 right-0 z-50 mb-2 overflow-hidden rounded-lg border border-sidebar-border bg-popover shadow-lg"
            role="listbox"
          >
            {THEMES.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={theme === t.id}
                  onClick={() => {
                    setTheme(t.id);
                    setOpen(false);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-sidebar-accent/40"
                >
                  <span>{t.emoji}</span>
                  <span className="flex-1">{t.label}</span>
                  {theme === t.id && (
                    <Check className="h-3.5 w-3.5 text-brand-primary" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

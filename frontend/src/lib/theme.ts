"use client";

/**
 * Multi-paleta sem dependência externa (sem next-themes).
 *
 * 3 temas: 'light' (default), 'obsidian' (escuro), 'black' (preto puro).
 *
 * Estado mora em <html data-theme="..."> + cookie (SSR) + localStorage.
 * O SSR já renderiza o data-theme certo a partir do cookie; o script
 * inline (theme-constants) só migra escolhas antigas de localStorage.
 *
 * Constantes moram em theme-constants.ts (módulo neutro): o layout server
 * NÃO pode importá-las daqui — "use client" vira client-reference no
 * server e a chave do cookie deixa de ser string (bug do flash de tema).
 */

import { useEffect, useState } from "react";

import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  type ThemeName,
} from "@/lib/theme-constants";

export {
  DEFAULT_THEME,
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
  THEMES,
  type ThemeName,
} from "@/lib/theme-constants";

/** Sincroniza com o data-theme aplicado (SSR/cookie). */
export function useTheme(): {
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
} {
  const [theme, setThemeState] = useState<ThemeName>(DEFAULT_THEME);

  useEffect(() => {
    // Lê o valor que o SSR/inline script já aplicou pra evitar mismatch
    const current = (document.documentElement.getAttribute("data-theme") ||
      DEFAULT_THEME) as ThemeName;
    setThemeState(current);
  }, []);

  function setTheme(next: ThemeName) {
    setThemeState(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
      // Cookie: o SSR renderiza <html data-theme> a partir dele — zero
      // flash em qualquer tema (localStorage só é legível no client).
      document.cookie = `${THEME_STORAGE_KEY}=${next}; path=/; max-age=31536000; samesite=lax`;
    } catch {
      /* localStorage indisponível (private mode/iframe) — ok, só não persiste */
    }
  }

  return { theme, setTheme };
}

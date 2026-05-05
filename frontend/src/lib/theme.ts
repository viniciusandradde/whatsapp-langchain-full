"use client";

/**
 * Multi-paleta sem dependência externa (sem next-themes).
 *
 * 3 temas: 'obsidian' (default), 'light' (branca), 'black' (preto puro).
 *
 * Estado mora em <html data-theme="..."> + localStorage. O script inline
 * em layout.tsx aplica antes do React montar, evitando FOUC.
 */

import { useEffect, useState } from "react";

export type ThemeName = "obsidian" | "light" | "black";

export const THEME_STORAGE_KEY = "vsa-theme";
export const THEMES: { id: ThemeName; label: string; emoji: string }[] = [
  { id: "obsidian", label: "Obsidian (escuro)", emoji: "🌑" },
  { id: "light", label: "Branco", emoji: "☀️" },
  { id: "black", label: "Preto puro", emoji: "⬛" },
];

/** Sincroniza com localStorage no client. SSR retorna 'obsidian' default. */
export function useTheme(): {
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
} {
  const [theme, setThemeState] = useState<ThemeName>("obsidian");

  useEffect(() => {
    // Lê o valor que o inline script já aplicou pra evitar mismatch
    const current = (document.documentElement.getAttribute("data-theme") ||
      "obsidian") as ThemeName;
    setThemeState(current);
  }, []);

  function setTheme(next: ThemeName) {
    setThemeState(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* localStorage indisponível (private mode/iframe) — ok, só não persiste */
    }
  }

  return { theme, setTheme };
}

/**
 * String do script inline pra <head>. Aplica o tema persistido ANTES do
 * React montar — sem isso há flash escuro→claro a cada navegação no
 * tema light. Usa try/catch porque localStorage pode quebrar em iframe.
 */
export const THEME_INIT_SCRIPT = `
(function(){try{
  var t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
  if(t==="light"||t==="black"||t==="obsidian"){
    document.documentElement.setAttribute("data-theme",t);
  }
}catch(e){}})();
`.trim();

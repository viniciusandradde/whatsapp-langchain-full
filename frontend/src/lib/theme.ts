"use client";

/**
 * Multi-paleta sem dependência externa (sem next-themes).
 *
 * 3 temas: 'light' (default), 'obsidian' (escuro), 'black' (preto puro).
 *
 * Estado mora em <html data-theme="..."> + localStorage. O script inline
 * em layout.tsx aplica antes do React montar, evitando FOUC. Quem nunca
 * escolheu tema (sem localStorage) cai no DEFAULT_THEME; quem já escolheu
 * mantém a escolha.
 */

import { useEffect, useState } from "react";

export type ThemeName = "obsidian" | "light" | "black";

export const THEME_STORAGE_KEY = "vsa-theme";
export const DEFAULT_THEME: ThemeName = "light";
export const THEMES: { id: ThemeName; label: string; emoji: string }[] = [
  { id: "light", label: "Branco", emoji: "☀️" },
  { id: "obsidian", label: "Obsidian (escuro)", emoji: "🌑" },
  { id: "black", label: "Preto puro", emoji: "⬛" },
];

/** Sincroniza com localStorage no client. SSR retorna o DEFAULT_THEME. */
export function useTheme(): {
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
} {
  const [theme, setThemeState] = useState<ThemeName>(DEFAULT_THEME);

  useEffect(() => {
    // Lê o valor que o inline script já aplicou pra evitar mismatch
    const current = (document.documentElement.getAttribute("data-theme") ||
      DEFAULT_THEME) as ThemeName;
    setThemeState(current);
  }, []);

  function setTheme(next: ThemeName) {
    setThemeState(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
      // Cookie: permite o SSR renderizar <html data-theme> já certo no
      // primeiro byte — zero flash em qualquer tema (localStorage só é
      // legível no client, tarde demais com streaming).
      document.cookie = `${THEME_STORAGE_KEY}=${next}; path=/; max-age=31536000; samesite=lax`;
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
  var k=${JSON.stringify(THEME_STORAGE_KEY)};
  var t=localStorage.getItem(k);
  if(t!=="light"&&t!=="black"&&t!=="obsidian"){t=${JSON.stringify(DEFAULT_THEME)};}
  var el=document.documentElement;
  if(el.getAttribute("data-theme")!==t){el.setAttribute("data-theme",t);}
  // Migração: garante o cookie pro SSR acertar já no próximo load.
  document.cookie=k+"="+t+"; path=/; max-age=31536000; samesite=lax";
}catch(e){}})();
`.trim();

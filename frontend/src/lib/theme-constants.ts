/**
 * Constantes de tema num módulo NEUTRO (sem "use client").
 *
 * O layout (Server Component) precisa de THEME_STORAGE_KEY/DEFAULT_THEME pra
 * ler o cookie e renderizar <html data-theme> no SSR. Importar essas
 * constantes do theme.ts ("use client") fazia o bundler entregar uma
 * client-reference no server — o cookieJar.get(chave) retornava undefined
 * mesmo com o cookie presente (bug do flash: SSR sempre caía no default).
 * Módulo compartilhado resolve: client (hook) e server importam daqui.
 */

export type ThemeName = "obsidian" | "light" | "black";

export const THEME_STORAGE_KEY = "vsa-theme";
export const DEFAULT_THEME: ThemeName = "light";
export const THEMES: { id: ThemeName; label: string; emoji: string }[] = [
  { id: "light", label: "Branco", emoji: "☀️" },
  { id: "obsidian", label: "Obsidian (escuro)", emoji: "🌑" },
  { id: "black", label: "Preto puro", emoji: "⬛" },
];

/**
 * Script inline pro <head>: migra a escolha antiga (localStorage) pro cookie
 * (que o SSR usa) e corrige divergência de data-theme no primeiro load.
 */
export const THEME_INIT_SCRIPT = `
(function(){try{
  var k=${JSON.stringify(THEME_STORAGE_KEY)};
  var t=localStorage.getItem(k);
  if(t!=="light"&&t!=="black"&&t!=="obsidian"){t=${JSON.stringify(DEFAULT_THEME)};}
  var el=document.documentElement;
  if(el.getAttribute("data-theme")!==t){el.setAttribute("data-theme",t);}
  document.cookie=k+"="+t+"; path=/; max-age=31536000; samesite=lax";
}catch(e){}})();
`.trim();

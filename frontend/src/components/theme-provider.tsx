"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Tema claro/escuro via `next-themes`, com `attribute="class"`.
 *
 * Substitui o mecanismo anterior (`data-theme` com três valores + cookie +
 * script inline próprio). O motivo não é modismo: `dark:` do Tailwind depende
 * da CLASSE `dark` no ancestral, e o esquema por atributo nunca a aplicava —
 * 130 utilitários `dark:` espalhados pelo app, mais os que vêm dentro dos
 * componentes do shadcn, eram código morto. Ver ADR-010.
 *
 * `enableSystem={false}`: o painel abre no claro por decisão de produto, não
 * pela preferência do sistema operacional. Quem quiser escuro escolhe, e a
 * escolha persiste em localStorage.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      enableSystem={false}
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}

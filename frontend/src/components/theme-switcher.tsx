"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

/**
 * Alterna claro/escuro. Antes eram três paletas (light/obsidian/black) num
 * dropdown escrito à mão, com overlay `fixed inset-0` próprio; agora são duas,
 * que é o par que o shadcn e os componentes instalados suportam.
 *
 * Quem decide o que aparece é o CSS, não o React: os dois ícones e os dois
 * rótulos são renderizados, e a variante `dark:` esconde o par errado. Isso
 * evita o mismatch de hidratação — o servidor não conhece o tema (mora no
 * localStorage), então qualquer `theme === "dark" ? A : B` no render diverge do
 * cliente. O padrão comum pra isso é um `useState`+`useEffect` de "mounted",
 * que é justamente o antipadrão que esta migração está removendo.
 */
export function ThemeSwitcher() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className="w-full justify-start gap-3 px-3 text-sidebar-foreground/60 hover:text-sidebar-foreground"
      aria-label="Alternar entre tema claro e escuro"
    >
      <Sun className="h-4 w-4 dark:hidden" />
      <Moon className="hidden h-4 w-4 dark:block" />
      Tema
      <span className="ml-auto text-xs text-sidebar-foreground/40">
        <span className="dark:hidden">claro</span>
        <span className="hidden dark:inline">escuro</span>
      </span>
    </Button>
  );
}

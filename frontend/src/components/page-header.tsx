import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Cabeçalho de página — um só.
 *
 * A auditoria encontrou 7 variantes de `<h1>` em 66 arquivos (`text-2xl
 * font-semibold` em 52, `text-xl` em 6, `text-4xl font-bold` em 2…), cada tela
 * com seu próprio espaçamento e sua própria forma de pendurar botões no canto.
 *
 * A descrição é opcional e serve pra dizer o que a tela resolve — não pra
 * documentar implementação. Nome de tabela, de coluna, de sprint e caminho de
 * arquivo não entram aqui.
 */
export function PageHeader({
  titulo,
  descricao,
  icon: Icone,
  acoes,
  className,
}: {
  titulo: string;
  descricao?: string;
  icon?: LucideIcon;
  acoes?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-6 flex flex-wrap items-start justify-between gap-4",
        className
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        {Icone ? (
          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icone className="size-5" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {titulo}
          </h1>
          {descricao ? (
            <p className="mt-1 text-sm text-muted-foreground">{descricao}</p>
          ) : null}
        </div>
      </div>
      {acoes ? <div className="flex shrink-0 gap-2">{acoes}</div> : null}
    </div>
  );
}

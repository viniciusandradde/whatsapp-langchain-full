import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Sprint F.2 — empty state padronizado.
 *
 * Uso típico em listas vazias (atendimentos, agentes, clientes, etc).
 * Padroniza visual + CTA opcional pra orientar o user no próximo passo.
 *
 * @example
 *   <EmptyState
 *     icon={Headphones}
 *     title="Nenhum atendimento aberto"
 *     description="Quando um cliente mandar mensagem, vai aparecer aqui."
 *     action={{ label: "Configurar conexão", href: "/connections" }}
 *   />
 */
export interface EmptyStateProps {
  /** Ícone do lucide-react (default: Inbox). */
  icon?: LucideIcon;
  /** Título curto (h3). Obrigatório. */
  title: string;
  /** Texto explicativo opcional (1-2 linhas). */
  description?: string;
  /** CTA primário (botão) opcional. */
  action?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
  /** CTA secundário opcional. */
  secondaryAction?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
  /** Tamanho — afeta padding + tamanho do ícone. */
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  secondaryAction,
  size = "md",
  className,
}: EmptyStateProps) {
  const padding = { sm: "py-6", md: "py-10", lg: "py-16" }[size];
  const iconSize = { sm: "size-8", md: "size-10", lg: "size-12" }[size];
  const iconWrapSize = { sm: "size-14", md: "size-16", lg: "size-20" }[size];
  const titleSize = {
    sm: "text-sm",
    md: "text-base",
    lg: "text-lg",
  }[size];

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 text-center",
        padding,
        className
      )}
    >
      <div
        className={cn(
          "flex items-center justify-center rounded-full bg-white/[0.04]",
          iconWrapSize
        )}
      >
        <Icon className={cn("text-muted-foreground", iconSize)} />
      </div>
      <div className="space-y-1">
        <p className={cn("font-medium text-foreground", titleSize)}>{title}</p>
        {description && (
          <p className="max-w-md text-xs text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {(action || secondaryAction) && (
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          {action &&
            (action.href ? (
              <a
                href={action.href}
                className="inline-flex h-8 items-center justify-center rounded-md bg-brand-primary px-3 text-xs font-medium text-white hover:bg-brand-primary/90"
              >
                {action.label}
              </a>
            ) : (
              <Button size="sm" onClick={action.onClick}>
                {action.label}
              </Button>
            ))}
          {secondaryAction &&
            (secondaryAction.href ? (
              <a
                href={secondaryAction.href}
                className="inline-flex h-8 items-center justify-center rounded-md border border-white/15 px-3 text-xs font-medium hover:bg-white/5"
              >
                {secondaryAction.label}
              </a>
            ) : (
              <Button variant="outline" size="sm" onClick={secondaryAction.onClick}>
                {secondaryAction.label}
              </Button>
            ))}
        </div>
      )}
    </div>
  );
}

import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        // Pílula de tinta translúcida sobre o token — legível nos dois temas
        // sem precisar de par `text-x-700 dark:text-x-300` (que, aliás, nunca
        // funcionou: a classe `dark` não existia. Ver ADR-010).
        default: "bg-primary/15 text-primary [a]:hover:bg-primary/25",
        secondary:
          "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive:
          "bg-destructive/15 text-destructive [a]:hover:bg-destructive/25 focus-visible:ring-destructive/30",
        outline:
          "border-border text-foreground/80 [a]:hover:bg-accent [a]:hover:text-accent-foreground",
        ghost: "text-muted-foreground hover:bg-accent hover:text-foreground",
        success: "bg-success/15 text-success [a]:hover:bg-success/25",
        warning: "bg-warning/15 text-warning [a]:hover:bg-warning/25",
        link: "text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }

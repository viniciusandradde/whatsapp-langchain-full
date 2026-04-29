import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        // Obsidian — pílulas com tinta translúcida da paleta brand.
        default:
          "bg-brand-primary/15 text-brand-primary-light [a]:hover:bg-brand-primary/25",
        secondary:
          "bg-brand-secondary/15 text-brand-secondary-light [a]:hover:bg-brand-secondary/25",
        destructive:
          "bg-destructive/15 text-destructive [a]:hover:bg-destructive/25 focus-visible:ring-destructive/30",
        outline:
          "border-white/10 text-foreground/80 [a]:hover:bg-white/[0.06] [a]:hover:text-foreground",
        ghost:
          "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
        success:
          "bg-vsa-success/15 text-emerald-300 [a]:hover:bg-vsa-success/25",
        gradient:
          "bg-vsa-brand text-white shadow-vsa-orange [a]:hover:shadow-glow-orange-lg",
        link: "text-brand-primary underline-offset-4 hover:underline",
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

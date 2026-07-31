"use client"

import * as React from "react"
import Link from "next/link"
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // Sólido, com a cor da marca vinda do token. Era um gradiente
        // laranja→azul com glow e `-translate-y-px`: como TODO botão primário
        // usava, a auditoria contou nove gradientes numa tela só, e a lista de
        // agentes virava uma pilha de barras coloridas. Ver ADR-014.
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline:
          "border-input bg-background text-foreground hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "text-muted-foreground hover:bg-accent hover:text-accent-foreground aria-expanded:bg-accent aria-expanded:text-accent-foreground",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 focus-visible:ring-destructive/30",
        link: "text-primary underline-offset-4 hover:underline",
        // O gradiente sobrevive como escolha explícita: UMA ação primária por
        // tela pode pedir destaque extra. Deixar de ser o default é o ponto.
        brand:
          "bg-linear-to-r from-brand-primary to-brand-secondary text-white font-semibold hover:brightness-110",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

/**
 * Botão que navega — visual de `Button`, semântica de link.
 *
 * O `ButtonPrimitive` do Base UI assume `nativeButton` e reclama em runtime
 * quando o `render` devolve outra coisa: "A component that acts as a button
 * expected a native <button>". `Button render={<Link/>}` cru dispara isso em
 * toda tela com um "Novo X" que leva pra outra rota.
 *
 * Aninhar `<Link><Button/></Link>` (o padrão antigo) esconde o aviso e cria
 * um `<button>` dentro de `<a>` — dois alvos interativos empilhados, que o
 * leitor de tela anuncia duas vezes.
 *
 * Uso: `<ButtonLink href="/catalog/models/new">Novo modelo</ButtonLink>`
 */
function ButtonLink({
  href,
  ...props
}: Omit<React.ComponentProps<typeof Button>, "render" | "nativeButton"> & {
  href: string
}) {
  return <Button nativeButton={false} render={<Link href={href} />} {...props} />
}

export { Button, ButtonLink, buttonVariants }

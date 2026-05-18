"use client";

import { X } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  nome: string;
  cor?: string | null;
  size?: "sm" | "md";
  onRemove?: () => void;
  porIa?: boolean;
}

/**
 * Pílula colorida pra exibir uma tag. Quando a cor é hex válida, usa como
 * background com texto contrastante; senão cai num neutro do tema.
 */
export function TagChip({
  nome,
  cor,
  size = "sm",
  onRemove,
  porIa = false,
}: Props) {
  const isHex = !!cor && /^#[0-9a-fA-F]{6}$/.test(cor);
  const style = isHex
    ? {
        backgroundColor: cor!,
        color: isLightBg(cor!) ? "#1f2937" : "#fff",
      }
    : undefined;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full font-medium leading-none",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        !isHex && "bg-muted text-foreground"
      )}
      style={style}
      title={porIa ? `${nome} — aplicado pela IA` : nome}
    >
      {porIa && <span aria-hidden>🤖</span>}
      <span className="max-w-[10rem] truncate">{nome}</span>
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-black/10"
          aria-label={`Remover tag ${nome}`}
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
}

function isLightBg(hex: string): boolean {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  // Luminância YIQ — abaixo de 150 é "escuro"
  return (r * 299 + g * 587 + b * 114) / 1000 > 150;
}

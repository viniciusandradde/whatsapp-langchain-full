/**
 * Marca do provedor no card do seletor de modelos (ADR-004).
 *
 * Sem baixar logo de terceiro: cada provedor vira um monograma (1–2 letras)
 * num quadrado do tema, com um tom de fundo estável por nome para o olho
 * separar Google de OpenAI na lista longa. Só tokens do tema — nada de cor
 * literal, e o mesmo em claro e escuro.
 */

import { cn } from "@/lib/utils";

const MONOGRAMA: Record<string, string> = {
  google: "G",
  openai: "AI",
  anthropic: "A\\",
  qwen: "Qw",
  deepseek: "DS",
  moonshotai: "Ki",
  amazon: "Az",
  "meta-llama": "M",
  mistralai: "Mi",
  "x-ai": "xA",
  "z-ai": "Z",
  microsoft: "MS",
  cohere: "Co",
  perplexity: "Px",
  nvidia: "Nv",
  minimax: "Mx",
  tencent: "Tc",
  baidu: "Bd",
};

// Fundos alternados por provedor: tinta translúcida sobre um token, legível
// nos dois temas (mesmo padrão dos badges do kit). Sem `brand-secondary`:
// é cor de marca por empresa e pode ser branco.
const TONS = [
  "bg-brand-primary/15 text-brand-primary",
  "bg-chart-3/15 text-chart-3",
  "bg-success/15 text-success",
  "bg-warning/15 text-warning",
  "bg-muted text-foreground",
] as const;

function tomDe(provedor: string): string {
  let h = 0;
  for (const c of provedor) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TONS[h % TONS.length];
}

export function monogramaDe(provedor: string): string {
  const m = MONOGRAMA[provedor];
  if (m) return m;
  return provedor.replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase() || "?";
}

export function LogoProvedor({
  provedor,
  className,
}: {
  provedor: string;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-lg font-mono text-xs font-bold tracking-tight",
        tomDe(provedor),
        className
      )}
    >
      {monogramaDe(provedor)}
    </span>
  );
}

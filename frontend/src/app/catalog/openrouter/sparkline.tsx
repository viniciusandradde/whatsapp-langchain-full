"use client";

/**
 * Gráfico de linha SVG sem lib (padrão do repo: SVG/CSS com --chart-N).
 * Dumb: recebe pontos numéricos já ordenados no eixo X; null vira buraco
 * (a linha quebra em segmentos — dado ausente não vira zero).
 */
export function Sparkline({
  valores,
  altura = 48,
  cor = "var(--chart-1)",
  invertido = false,
  formato,
}: {
  valores: (number | null)[];
  altura?: number;
  cor?: string;
  /** true = menor é melhor no topo (ex.: posição no ranking). */
  invertido?: boolean;
  formato?: (v: number) => string;
}) {
  const validos = valores.filter((v): v is number => v != null);
  if (validos.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        Ainda sem pontos suficientes — a série cresce a cada coleta.
      </p>
    );
  }
  const min = Math.min(...validos);
  const max = Math.max(...validos);
  const span = max - min || 1;
  const w = 100;
  const pad = 4;
  const h = altura;
  const y = (v: number) => {
    const norm = (v - min) / span;
    const t = invertido ? norm : 1 - norm;
    return pad + t * (h - 2 * pad);
  };
  const x = (i: number) =>
    valores.length > 1 ? (i / (valores.length - 1)) * w : 0;

  // Segmentos contínuos — null quebra a linha em vez de interpolar.
  const segmentos: string[] = [];
  let atual: string[] = [];
  valores.forEach((v, i) => {
    if (v == null) {
      if (atual.length > 1) segmentos.push(atual.join(" "));
      atual = [];
      return;
    }
    atual.push(`${x(i).toFixed(2)},${y(v).toFixed(2)}`);
  });
  if (atual.length > 1) segmentos.push(atual.join(" "));

  const ultimo = [...valores].reverse().find((v) => v != null) as number;
  const fmt = formato ?? ((v: number) => String(Math.round(v)));

  return (
    <div className="space-y-0.5">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ height: h }}
        preserveAspectRatio="none"
        role="img"
      >
        {segmentos.map((pts, i) => (
          <polyline
            key={i}
            points={pts}
            fill="none"
            stroke={cor}
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      <p className="flex justify-between text-xs text-muted-foreground">
        <span>
          {invertido ? "melhor" : "min"} {fmt(min)} · max{" "}
          {fmt(max)}
        </span>
        <span>agora {fmt(ultimo)}</span>
      </p>
    </div>
  );
}

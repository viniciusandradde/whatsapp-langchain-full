"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Bot, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";

import { loadContadoresAction } from "./actions";

/**
 * Faixa de uso do plano no topo da fila (ADR-005 D5, leva A).
 *
 * Lê a MESMA query `["contadores"]` do rail (cache compartilhado — nenhum
 * fetch a mais; o SSE e o intervalo de 60 s já a revalidam). Só aparece a
 * partir de 80 % dos atendimentos do mês do plano; ao atingir o limite muda
 * de tom: a IA está pausada e os atendentes continuam. Leva ao `/billing`,
 * onde o plano se resolve.
 */
export function BannerPlano() {
  const { data } = useQuery({
    queryKey: ["contadores"],
    queryFn: async () => {
      const r = await loadContadoresAction();
      if (!r.ok) throw new Error(r.error);
      return r.contadores;
    },
    staleTime: 60_000,
  });
  const uso = data?.plano?.atendimentos_mes;
  if (!uso || uso.limite == null || !uso.em_alerta) return null;

  const pausada = uso.atingido;
  const Icone = pausada ? TriangleAlert : Bot;
  return (
    <Link
      href="/billing"
      prefetch={false}
      role="status"
      className={cn(
        "flex items-center gap-2 border-b px-3 py-1.5 text-xs transition-colors",
        pausada
          ? "border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/15"
          : "border-warning/30 bg-warning/10 text-warning hover:bg-warning/15"
      )}
    >
      <Icone className="size-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 truncate">
        {pausada
          ? `Limite do plano atingido (${uso.usado}/${uso.limite} atendimentos no mês) — IA pausada, atendentes continuam.`
          : `${uso.usado} de ${uso.limite} atendimentos do plano neste mês (${Math.round(uso.percentual ?? 0)}%).`}
      </span>
      <span className="shrink-0 font-medium underline-offset-2 hover:underline">
        Ver plano
      </span>
    </Link>
  );
}

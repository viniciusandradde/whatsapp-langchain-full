"use client";

/**
 * Banner de vencimento do plano (ADR-005 leva E) — aparece no topo do painel
 * a partir de 7 dias do vencimento e some sozinho quando a vigência é
 * estendida (o layout recarrega o plano) ou quando a conta é rebaixada para
 * Free (sem data, nada a avisar). Lê do `usePlano()`: nenhum fetch novo.
 *
 * Os textos seguem os do WhatsApp (`shared/plano_vigencia.py`): sem termo
 * técnico, com a data e o fim da carência por extenso.
 */

import Link from "next/link";
import { CalendarClock, TriangleAlert } from "lucide-react";

import { usePlano } from "@/components/plano-context";
import { dataCivil } from "@/lib/formato";
import { cn } from "@/lib/utils";

function somaDias(iso: string, dias: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const data = new Date(Date.UTC(y, m - 1, d + dias));
  return data.toISOString().slice(0, 10);
}

export function BannerVigencia() {
  const { plano } = usePlano();
  if (!plano || plano.dias_para_vencer === null || !plano.valido_ate) return null;
  const dias = plano.dias_para_vencer;
  if (dias > 7) return null;

  const vencido = dias < 0;
  const limite = dataCivil(somaDias(plano.valido_ate, plano.carencia_dias));
  const quando =
    dias === 0 ? "vence hoje" : dias === 1 ? "vence amanhã" : `vence em ${dias} dias`;

  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-2.5 border-b px-4 py-2 text-sm",
        vencido
          ? "border-destructive/40 bg-destructive/10 text-foreground"
          : "border-warning/40 bg-warning/10 text-foreground"
      )}
    >
      {vencido ? (
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
      ) : (
        <CalendarClock className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      )}
      <p className="min-w-0 flex-1">
        {vencido ? (
          <>
            O plano <span className="font-medium">{plano.nome}</span> venceu em{" "}
            {dataCivil(plano.valido_ate)}. Você tem até <span className="font-medium">{limite}</span>{" "}
            para renovar — depois disso a conta volta ao plano Free (os atendimentos continuam; os
            recursos do {plano.nome} ficam pausados).
          </>
        ) : (
          <>
            O plano <span className="font-medium">{plano.nome}</span> {quando} (
            {dataCivil(plano.valido_ate)}). Renove até lá para continuar com todos os recursos.
          </>
        )}{" "}
        <Link href="/billing" prefetch={false} className="font-medium underline underline-offset-2">
          Ver plano e cobrança
        </Link>
      </p>
    </div>
  );
}

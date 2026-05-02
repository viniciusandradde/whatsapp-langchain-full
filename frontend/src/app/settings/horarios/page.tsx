import { Clock } from "lucide-react";

import {
  getFeriados,
  getHorarios,
  getHorariosStatus,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { HorariosManager } from "./horarios-manager";

export const dynamic = "force-dynamic";

export default async function HorariosPage() {
  await requireSession();

  let horarios: Awaited<ReturnType<typeof getHorarios>>["horarios"] = [];
  let feriados: Awaited<ReturnType<typeof getFeriados>>["feriados"] = [];
  let isOpen: boolean | null = null;
  let error: string | null = null;
  try {
    const [h, f, s] = await Promise.all([
      getHorarios(),
      getFeriados(),
      getHorariosStatus(),
    ]);
    horarios = h.horarios;
    feriados = f.feriados;
    isOpen = s.is_open;
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro ao carregar configurações de horário.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Clock className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">
              Horário de funcionamento
            </h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Quando estamos abertos. Fora do expediente, o agente recebe{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                [FORA DO EXPEDIENTE]
              </code>{" "}
              no input.
            </p>
          </div>
        </div>
        {isOpen !== null && (
          <span
            className={
              "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs " +
              (isOpen
                ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
                : "border-amber-500/50 bg-amber-500/10 text-amber-300")
            }
          >
            <span
              className={
                "size-2 rounded-full " +
                (isOpen ? "bg-emerald-400" : "bg-amber-400")
              }
            />
            {isOpen ? "Aberto agora" : "Fechado agora"}
          </span>
        )}
      </div>

      <HorariosManager
        initialHorarios={horarios}
        initialFeriados={feriados}
        loadError={error}
      />
    </div>
  );
}

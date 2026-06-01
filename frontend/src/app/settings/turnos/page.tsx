import { Clock } from "lucide-react";

import { requireSession } from "@/lib/session";

import { TurnosClient } from "./turnos-client";

export const dynamic = "force-dynamic";

export default async function TurnosPage() {
  await requireSession();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Clock className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Turnos / Jornada</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Defina janelas de horário de trabalho e atribua atendentes a cada
            turno.
          </p>
        </div>
      </div>

      <TurnosClient />
    </div>
  );
}

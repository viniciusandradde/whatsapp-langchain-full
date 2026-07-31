import { Clock } from "lucide-react";

import { PageHeader } from "@/components/page-header";

import { requireSession } from "@/lib/session";

import { TurnosClient } from "./turnos-client";

export const dynamic = "force-dynamic";

export default async function TurnosPage() {
  await requireSession();

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Turnos e jornada"
        descricao="Defina janelas de horário de trabalho e atribua atendentes a cada turno."
        icon={Clock}
      />

      <TurnosClient />
    </div>
  );
}

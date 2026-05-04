import { CalendarCog } from "lucide-react";

import { getCalendarRegras } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { RegrasForm } from "./regras-form";

export const dynamic = "force-dynamic";

/**
 * Página /settings/calendar-rules — regras de negócio do agendamento (S3+S4).
 *
 * Toggle requer_aprovacao + horário comercial + antecedência + dias.
 * Aplicado em find_free_slots e create_event antes de chamar Google.
 */
export default async function CalendarRulesPage() {
  await requireSession();

  let regras: Awaited<ReturnType<typeof getCalendarRegras>> | null = null;
  let loadError: string | null = null;

  try {
    regras = await getCalendarRegras();
  } catch (e) {
    loadError =
      e instanceof Error ? e.message : "Erro desconhecido ao carregar regras.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <CalendarCog className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Regras de agendamento</h1>
      </div>

      {loadError ? (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {loadError}
        </div>
      ) : regras ? (
        <RegrasForm initial={regras} />
      ) : null}
    </div>
  );
}

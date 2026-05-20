import { redirect } from "next/navigation";

import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Página raiz — redireciona pra Dashboard de Atendimento operacional.
 *
 * Operador entra direto na visão do dia (KPIs + filas + gráficos).
 * Dashboard IA continua acessível via menu "IA & Conteúdo" → 1ª aba.
 */
export default async function RootPage() {
  await requireSession();
  redirect("/dashboard/atendimento");
}

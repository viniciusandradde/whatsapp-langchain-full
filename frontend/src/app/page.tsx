import { redirect } from "next/navigation";

import { requireSession } from "@/lib/session";
import { fetchOnboardingStatusAction } from "./onboarding/actions";

export const dynamic = "force-dynamic";

/**
 * Página raiz — decide entre onboarding e dashboard.
 *
 * Até 2026-07-30 mandava todo mundo direto pro dashboard, e `/onboarding`
 * ficava órfã: a tela existia, com 4 passos e barra de progresso, e nenhum
 * link, menu ou redirect apontava pra ela. Cliente novo caía na visão
 * operacional sem saber que existia um caminho guiado.
 *
 * A checagem custa 4 chamadas de API, mas só acontece em "/" — que é onde o
 * login cai, uma vez por sessão. Empresa com os 4 passos feitos nunca mais vê
 * o wizard; quem quiser rever entra pelo menu (grupo "Visão Geral").
 */
export default async function RootPage() {
  await requireSession();

  const status = await fetchOnboardingStatusAction();
  redirect(status.completo ? "/dashboard/atendimento" : "/onboarding");
}

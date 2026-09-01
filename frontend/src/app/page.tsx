import { redirect } from "next/navigation";

import { getMyPermissions } from "@/lib/api";
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
 *
 * Duas saídas, não uma (mig 160): completar os 4 passos **ou** ter clicado em
 * "Pular". Antes só a primeira existia, e ela estava quebrada — a contagem de
 * atendentes lia `.items` de um endpoint que devolve lista pura, então dava
 * sempre 0 e `completo` nunca virava true. Resultado: o wizard reaparecia em
 * todo login, e o botão "Pular", que não gravava nada, não adiantava.
 *
 * Desde 2026-08-31 quem atende cai direto na fila (`/atendimento`), não na
 * visão geral: a decisão é por permissão porque `/atendimento` não tem guard
 * próprio no front — perfil customizado sem `atendimento.read` cairia numa
 * tela vazia sem rota de saída (o grupo Operação nem aparece no menu).
 */
export default async function RootPage() {
  await requireSession();

  const [status, perms] = await Promise.all([
    fetchOnboardingStatusAction(),
    getMyPermissions().catch(() => null),
  ]);
  const guiar = !status.completo && !status.dispensado;
  redirect(guiar ? "/onboarding" : destinoPosLogin(perms?.permissoes));
}

/** Mesma regra do `hasPerm` do painel: match exato ou variantes .all/.own. */
function destinoPosLogin(permissoes: string[] | null | undefined) {
  const set = new Set(permissoes ?? []);
  const podeAtender =
    set.has("atendimento.read") ||
    set.has("atendimento.read.all") ||
    set.has("atendimento.read.own");
  return podeAtender ? "/atendimento" : "/dashboard/atendimento";
}

import { redirect } from "next/navigation";

import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Página raiz — redireciona pra Visão Geral (Dashboard IA).
 *
 * O sidebar "Visão Geral" aponta pra /dashboard/ia, então a raiz cai lá pra
 * manter consistência (independente de bookmarks/última URL no browser).
 */
export default async function RootPage() {
  await requireSession();
  redirect("/dashboard/ia");
}

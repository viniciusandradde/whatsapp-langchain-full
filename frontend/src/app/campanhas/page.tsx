import { getCampanhas, getConexoes } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { CampanhasPageClient } from "./campanhas-page-client";

export const dynamic = "force-dynamic";

export default async function CampanhasPage() {
  await requireSession();

  let items: Awaited<ReturnType<typeof getCampanhas>>["items"] = [];
  let conexoes: Awaited<ReturnType<typeof getConexoes>>["conexoes"] = [];
  let error: string | null = null;
  try {
    [{ items }, { conexoes }] = await Promise.all([
      getCampanhas(),
      getConexoes(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar campanhas.";
  }

  return (
    <CampanhasPageClient
      initialCampanhas={items}
      conexoes={conexoes}
      loadError={error}
    />
  );
}

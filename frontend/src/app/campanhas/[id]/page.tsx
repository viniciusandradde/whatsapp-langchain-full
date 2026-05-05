import { notFound } from "next/navigation";

import { getCampanha, getCampanhaDestinatarios } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { CampanhaDetailClient } from "./campanha-detail-client";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function CampanhaDetailPage({ params }: Props) {
  await requireSession();
  const { id } = await params;
  const campId = Number(id);
  if (!Number.isFinite(campId)) notFound();

  let camp;
  let dest;
  let error: string | null = null;
  try {
    [camp, dest] = await Promise.all([
      getCampanha(campId),
      getCampanhaDestinatarios(campId),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar campanha.";
  }

  if (!camp && !error) notFound();

  return (
    <CampanhaDetailClient
      campanha={camp!}
      destinatariosIniciais={dest?.items ?? []}
      loadError={error}
    />
  );
}

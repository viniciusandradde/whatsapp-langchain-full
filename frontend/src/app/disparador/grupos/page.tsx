import { getGruposCapturados, type GrupoCapturado } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { GruposClient } from "./grupos-client";

export const dynamic = "force-dynamic";
export const metadata = { title: "Disparador · Grupos capturados" };

export default async function GruposPage() {
  await requireSession();
  let initial: GrupoCapturado[] = [];
  try {
    initial = (await getGruposCapturados()).items;
  } catch {
    initial = [];
  }
  return <GruposClient initial={initial} />;
}

import { getGruposCapturados, type GrupoCapturado } from "@/lib/api";

import { GruposClient } from "./grupos-client";

export const metadata = { title: "Disparador · Grupos capturados" };

export default async function GruposPage() {
  let initial: GrupoCapturado[] = [];
  try {
    initial = (await getGruposCapturados()).items;
  } catch {
    initial = [];
  }
  return <GruposClient initial={initial} />;
}

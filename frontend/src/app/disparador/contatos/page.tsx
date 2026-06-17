import { getContatosCapturados, type ContatoCapturado } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ContatosClient } from "./contatos-client";

export const dynamic = "force-dynamic";
export const metadata = { title: "Disparador · Contatos capturados" };

export default async function ContatosPage() {
  await requireSession();
  let initial: ContatoCapturado[] = [];
  try {
    initial = (await getContatosCapturados()).items;
  } catch {
    initial = [];
  }
  return <ContatosClient initial={initial} />;
}

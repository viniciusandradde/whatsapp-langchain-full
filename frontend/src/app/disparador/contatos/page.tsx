import { getContatosCapturados, type ContatoCapturado } from "@/lib/api";

import { ContatosClient } from "./contatos-client";

export const metadata = { title: "Disparador · Contatos capturados" };

export default async function ContatosPage() {
  let initial: ContatoCapturado[] = [];
  try {
    initial = (await getContatosCapturados()).items;
  } catch {
    initial = [];
  }
  return <ContatosClient initial={initial} />;
}

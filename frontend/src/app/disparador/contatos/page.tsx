import {
  getConexoes,
  getContatosCapturados,
  type Conexao,
  type ContatoCapturado,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ContatosClient } from "./contatos-client";

export const dynamic = "force-dynamic";
export const metadata = { title: "Disparador · Contatos capturados" };

export default async function ContatosPage() {
  await requireSession();
  let initial: ContatoCapturado[] = [];
  let evolution: Conexao[] = [];
  let total = 0;
  let promoviveis = 0;
  try {
    const [contatos, conexoes] = await Promise.all([
      // Mesma página que o cliente exibe. Buscar 1.000 pra mostrar 200 era
      // transferir 5x o necessário em toda visita.
      getContatosCapturados({ limit: 200 }),
      getConexoes(),
    ]);
    initial = contatos.items;
    total = contatos.total;
    promoviveis = contatos.promoviveis;
    evolution = conexoes.conexoes.filter(
      (c) => c.provider === "evolution" && c.status === "active"
    );
  } catch {
    initial = [];
  }
  return (
    <ContatosClient
      initial={initial}
      total={total}
      promoviveis={promoviveis}
      evolution={evolution}
    />
  );
}

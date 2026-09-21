"use client";

/**
 * Banner de conexão caída (mig 196) — no topo do painel enquanto alguma
 * conexão de WhatsApp da empresa ativa estiver fora (episódio `conexao_caida`
 * aberto pelo monitor ou estado `disconnected`/`error` gravado pelo webhook).
 * Some sozinho quando a conexão volta: o tick do worker resolve o episódio e
 * o webhook grava `open`.
 *
 * Uma chamada leve a cada 5 min pelo cliente (não roda em toda navegação
 * server-side como o `resolveEmpresaUI`). Texto sem termo técnico, como os
 * avisos do canal (`shared/saude_conexoes.py`).
 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { WifiOff } from "lucide-react";

import { loadBannerConexaoAction } from "@/app/monitor/conexoes/actions";
import { dataHora } from "@/lib/formato";

function nomeConexao(c: {
  display_name: string | null;
  from_number: string | null;
}): string {
  const nome = (c.display_name ?? "").trim();
  const numero = (c.from_number ?? "").startsWith("evolution:")
    ? ""
    : (c.from_number ?? "");
  return [nome, numero].filter(Boolean).join(" ") || "de atendimento";
}

export function BannerConexao() {
  const { data } = useQuery({
    queryKey: ["banner-conexao"],
    queryFn: async () => {
      const r = await loadBannerConexaoAction();
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 60_000,
    refetchInterval: 300_000,
    retry: false,
  });
  const caidas = data?.caidas ?? [];
  if (caidas.length === 0) return null;

  const primeira = caidas[0];
  const quando = primeira.desde ? ` desde ${dataHora(primeira.desde)}` : "";
  const outras =
    caidas.length > 1 ? ` e mais ${caidas.length - 1} conexão(ões)` : "";

  return (
    <div
      role="status"
      className="flex items-start gap-2.5 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-foreground"
    >
      <WifiOff
        className="mt-0.5 size-4 shrink-0 text-destructive"
        aria-hidden
      />
      <p className="min-w-0 flex-1">
        O WhatsApp <span className="font-medium">{nomeConexao(primeira)}</span>{" "}
        está desconectado
        {quando} ({primeira.motivo}){outras}. As mensagens dos clientes não
        estão chegando aqui.{" "}
        <Link
          href="/connections"
          prefetch={false}
          className="font-medium underline underline-offset-2"
        >
          Abra Conexões para reconectar
        </Link>
        .
      </p>
    </div>
  );
}

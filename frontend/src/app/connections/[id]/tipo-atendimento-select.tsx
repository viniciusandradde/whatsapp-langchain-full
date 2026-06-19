"use client";

import { useState, useTransition } from "react";

import { patchConexaoAction } from "../actions";

const OPCOES = [
  { v: "ia", label: "IA (agente responde)" },
  { v: "manual", label: "Manual (só disparo / humano)" },
  { v: "hibrido", label: "Híbrido" },
];

/** Define a finalidade do número: IA = atendimento pelo agente; Manual = número
 * dedicado a disparo (a IA não responde automático). */
export function TipoAtendimentoSelect({
  conexaoId,
  initial,
}: {
  conexaoId: number;
  initial: string;
}) {
  const [valor, setValor] = useState(initial || "ia");
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, start] = useTransition();

  function onChange(novo: string) {
    setValor(novo);
    setMsg(null);
    start(async () => {
      const r = await patchConexaoAction(conexaoId, { tipo_atendimento: novo });
      setMsg(r.ok ? "✓ salvo" : `erro: ${r.error}`);
    });
  }

  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        Tipo de atendimento
      </div>
      <select
        value={valor}
        disabled={saving}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 h-8 w-full rounded-md border border-border/40 bg-background px-2 text-sm"
      >
        {OPCOES.map((o) => (
          <option key={o.v} value={o.v}>
            {o.label}
          </option>
        ))}
      </select>
      {msg && (
        <span
          className={
            msg.startsWith("erro")
              ? "text-xs text-destructive"
              : "text-xs text-emerald-400"
          }
        >
          {msg}
        </span>
      )}
    </div>
  );
}

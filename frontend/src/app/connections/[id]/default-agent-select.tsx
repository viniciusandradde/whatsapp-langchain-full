"use client";

import { useEffect, useState, useTransition } from "react";

import { patchConexaoAction } from "../actions";

/** Select do agente padrão da conexão — o webhook carimba esse slug em cada
 * conversa nova (rótulo no painel + thread). Lista os agentes ativos da
 * empresa; se o valor atual não estiver na lista (ex.: slug legado do
 * catálogo como "vsa_tech"), mantém como opção pra não sumir com o valor. */
export function DefaultAgentSelect({
  conexaoId,
  initial,
}: {
  conexaoId: number;
  initial: string;
}) {
  const [valor, setValor] = useState(initial || "");
  const [agentes, setAgentes] = useState<{ slug: string; nome: string }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, start] = useTransition();

  useEffect(() => {
    import("../actions").then(({ loadAgentesEmpresaAction }) =>
      loadAgentesEmpresaAction().then((r) => {
        if (r.ok) setAgentes(r.data);
      })
    );
  }, []);

  const opcoes = agentes.some((a) => a.slug === valor)
    ? agentes
    : valor
      ? [{ slug: valor, nome: `${valor} (legado)` }, ...agentes]
      : agentes;

  function onChange(novo: string) {
    setValor(novo);
    setMsg(null);
    start(async () => {
      const r = await patchConexaoAction(conexaoId, { default_agent_id: novo });
      setMsg(r.ok ? "✓ salvo" : `erro: ${r.error}`);
    });
  }

  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        Agente padrão
      </div>
      <select
        value={valor}
        disabled={saving || opcoes.length === 0}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 h-8 w-full rounded-md border border-border/40 bg-background px-2 text-sm"
      >
        {opcoes.length === 0 && <option value="">Carregando…</option>}
        {opcoes.map((a) => (
          <option key={a.slug} value={a.slug}>
            {a.nome}
          </option>
        ))}
      </select>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Conversas novas desta conexão entram com este agente.
      </p>
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

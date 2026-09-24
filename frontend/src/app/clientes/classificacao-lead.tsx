"use client";

import { useState, useTransition } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { Cliente } from "@/lib/api";
import {
  ESTAGIOS_FUNIL,
  ESTAGIO_CHIP,
  TEMPERATURAS,
  TEMPERATURA_CHIP,
  rotuloEstagio,
  rotuloTemperatura,
  type EstagioFunil,
  type Temperatura,
} from "@/lib/lead";
import { cn } from "@/lib/utils";

import { carregarClienteAction, classificarClienteAction } from "./actions";

type Classificacao = Pick<
  Cliente,
  | "id"
  | "lifecycle_stage"
  | "temperatura"
  | "score"
  | "classificacao_origem"
  | "classificacao_motivo"
>;

/** Chips de estágio + temperatura (lista de clientes e painel da conversa). */
export function ChipsLead({
  cliente,
  curto = false,
}: {
  cliente: Pick<Cliente, "lifecycle_stage" | "temperatura" | "classificacao_origem">;
  curto?: boolean;
}) {
  const estagio = cliente.lifecycle_stage as EstagioFunil | null;
  const temp = cliente.temperatura as Temperatura | null;
  if (!estagio && !temp) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {estagio && (
        <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", ESTAGIO_CHIP[estagio])}>
          {rotuloEstagio(estagio, curto)}
        </span>
      )}
      {temp && (
        <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", TEMPERATURA_CHIP[temp])}>
          {rotuloTemperatura(temp)}
        </span>
      )}
      {cliente.classificacao_origem === "ia" && (
        <span
          className="inline-flex items-center gap-0.5 text-xs text-muted-foreground"
          title="Sugerido pela IA, ainda não confirmado"
        >
          <Sparkles className="size-3" aria-hidden />
          sugestão
        </span>
      )}
    </span>
  );
}

/**
 * Bloco "Classificação do lead" — estágio do funil, temperatura e pontuação.
 * Salvar ou confirmar grava como classificação manual: a IA não mexe mais.
 * Usado na ficha do cliente e no painel de informações da conversa.
 */
export function ClassificacaoLead({
  cliente,
  compacto = false,
  onSalvo,
}: {
  cliente: Classificacao;
  compacto?: boolean;
  onSalvo?: (c: Cliente) => void;
}) {
  const [estagio, setEstagio] = useState<string | null>(cliente.lifecycle_stage);
  const [temp, setTemp] = useState<string | null>(cliente.temperatura);
  const [score, setScore] = useState<string>(cliente.score?.toString() ?? "");
  const [origem, setOrigem] = useState(cliente.classificacao_origem);
  const [motivo, setMotivo] = useState(cliente.classificacao_motivo);
  // O que está gravado — compara com a edição para habilitar "Salvar".
  const [base, setBase] = useState({
    estagio: cliente.lifecycle_stage as string | null,
    temp: cliente.temperatura as string | null,
    score: cliente.score?.toString() ?? "",
  });
  const [pendente, startTransition] = useTransition();

  const mudou = estagio !== base.estagio || temp !== base.temp || score !== base.score;
  const sugestaoIa = origem === "ia";

  function salvar() {
    const n = score.trim() === "" ? null : Number(score);
    if (n !== null && (!Number.isInteger(n) || n < 0 || n > 100)) {
      toast.error("A pontuação vai de 0 a 100.");
      return;
    }
    startTransition(async () => {
      const r = await classificarClienteAction(cliente.id, {
        lifecycle_stage: (estagio as Cliente["lifecycle_stage"]) ?? null,
        temperatura: (temp as Cliente["temperatura"]) ?? null,
        score: n,
      });
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      const confirmou = sugestaoIa && !mudou;
      setBase({ estagio, temp, score: n === null ? "" : String(n) });
      setOrigem("manual");
      setMotivo(null);
      onSalvo?.(r.cliente);
      toast.success(confirmou ? "Sugestão confirmada" : "Classificação salva");
    });
  }

  return (
    <div className="space-y-3">
      {sugestaoIa && (
        <div className="flex items-start gap-2 rounded-md bg-muted/60 px-3 py-2 text-sm">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0">
            <p className="font-medium">Sugestão da IA</p>
            {motivo && <p className="text-muted-foreground wrap-anywhere">{motivo}</p>}
          </div>
        </div>
      )}

      <fieldset className="space-y-1.5">
        <legend className="text-xs font-medium text-muted-foreground">Estágio do funil</legend>
        <div className={cn("grid gap-1", compacto ? "grid-cols-3" : "grid-cols-3 sm:grid-cols-6")}>
          {ESTAGIOS_FUNIL.map((e) => (
            <button
              key={e.valor}
              type="button"
              title={e.dica}
              aria-pressed={estagio === e.valor}
              onClick={() => setEstagio(estagio === e.valor ? null : e.valor)}
              className={cn(
                "rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                estagio === e.valor
                  ? cn("border-transparent", ESTAGIO_CHIP[e.valor])
                  : "border-border text-muted-foreground hover:bg-muted"
              )}
            >
              {e.curto}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-end gap-3">
        <fieldset className="space-y-1.5">
          <legend className="text-xs font-medium text-muted-foreground">Temperatura</legend>
          <div className="flex gap-1">
            {TEMPERATURAS.map((t) => (
              <button
                key={t.valor}
                type="button"
                title={t.dica}
                aria-pressed={temp === t.valor}
                onClick={() => setTemp(temp === t.valor ? null : t.valor)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                  temp === t.valor
                    ? cn("border-transparent", TEMPERATURA_CHIP[t.valor])
                    : "border-border text-muted-foreground hover:bg-muted"
                )}
              >
                {t.rotulo}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="space-y-1.5">
          <span className="block text-xs font-medium text-muted-foreground">Pontuação</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={100}
            value={score}
            onChange={(e) => setScore(e.target.value)}
            placeholder="0 a 100"
            className="h-8 w-24 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
          />
        </label>

        <div className="ml-auto flex gap-2">
          {sugestaoIa && !mudou ? (
            <Button type="button" size="sm" onClick={salvar} disabled={pendente}>
              <Check className="size-3.5" />
              Confirmar sugestão
            </Button>
          ) : (
            <Button type="button" size="sm" onClick={salvar} disabled={pendente || !mudou}>
              Salvar
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * O bloco dentro do painel de informações da conversa: busca o cliente pelo
 * id (o atendimento não traz a classificação) e mantém o cache em dia ao
 * salvar. Sem permissão de ver clientes, some em silêncio.
 */
export function ClassificacaoLeadConversa({ clienteId }: { clienteId: number }) {
  const qc = useQueryClient();
  const chave = ["cliente-classificacao", clienteId];
  const { data, isLoading } = useQuery({
    queryKey: chave,
    queryFn: async () => {
      const r = await carregarClienteAction(clienteId);
      if (!r.ok) throw new Error(r.error);
      return r.cliente;
    },
    staleTime: 30_000,
    retry: false,
  });
  if (isLoading) {
    return <div className="h-24 animate-pulse rounded-md bg-muted/60" aria-hidden />;
  }
  if (!data) return null;
  return (
    <ClassificacaoLead
      key={`${data.id}-${data.classificado_em ?? ""}`}
      cliente={data}
      compacto
      onSalvo={(c) => qc.setQueryData(chave, c)}
    />
  );
}

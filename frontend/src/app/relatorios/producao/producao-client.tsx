"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type {
  AchadoProducao,
  ConfigProducao,
  PainelProducao,
  RelatorioProducao,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { gerarAction, loadPainelAction, salvarConfigAction } from "./actions";

/** Severidade vira cor sem número solto na classe — o portão de UI reprova. */
const COR: Record<AchadoProducao["severidade"], string> = {
  ok: "border-border bg-muted text-muted-foreground",
  atencao: "border-warning/40 bg-warning/10 text-foreground",
  critico: "border-destructive/40 bg-destructive/10 text-foreground",
};

const ROTULO: Record<AchadoProducao["severidade"], string> = {
  ok: "Tudo certo",
  atencao: "Atenção",
  critico: "Crítico",
};

function quando(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ProducaoClient({ inicial }: { inicial: PainelProducao }) {
  const [painel, setPainel] = useState(inicial);
  const [pedindo, setPedindo] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [cfg, setCfg] = useState<ConfigProducao>(inicial.config);

  async function recarregar() {
    const r = await loadPainelAction();
    if (r.ok) setPainel(r.data);
  }

  async function gerar() {
    setPedindo(true);
    const r = await gerarAction();
    setPedindo(false);
    if (!r.ok) {
      toast.error(r.error);
      return;
    }
    // 202: o host produz no próximo ciclo. Prometer "pronto" aqui seria mentira.
    toast.success(
      r.data.ja_existia
        ? "Já havia um pedido na fila — ele será atendido no próximo ciclo."
        : "Pedido na fila. O relatório aparece aqui em instantes."
    );
    await recarregar();
  }

  async function salvar() {
    setSalvando(true);
    const r = await salvarConfigAction(cfg);
    setSalvando(false);
    if (!r.ok) {
      toast.error(r.error);
      return;
    }
    toast.success("Agendamento salvo.");
    await recarregar();
  }

  const ultimo: RelatorioProducao | undefined = painel.relatorios[0];

  return (
    <div className="space-y-6">
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Gerar agora</p>
            <p className="text-sm text-muted-foreground">
              O relatório é produzido no servidor, não aqui — leva alguns
              instantes até aparecer na lista.
            </p>
          </div>
          <Button onClick={gerar} disabled={pedindo || !!painel.pendente}>
            {painel.pendente
              ? "Gerando…"
              : pedindo
                ? "Pedindo…"
                : "Gerar agora"}
          </Button>
        </div>
      </Card>

      <Card className="space-y-4 p-4">
        <p className="text-sm font-medium">Agendamento</p>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex items-center gap-2">
            <Switch
              id="ativo"
              checked={cfg.ativo}
              onCheckedChange={(v) => setCfg({ ...cfg, ativo: v })}
            />
            <Label htmlFor="ativo">Enviar todo dia</Label>
          </div>
          <div className="space-y-1">
            <Label htmlFor="horario">Horário</Label>
            <Input
              id="horario"
              type="time"
              className="w-32"
              value={cfg.horario}
              onChange={(e) => setCfg({ ...cfg, horario: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tz">Fuso</Label>
            <Input
              id="tz"
              className="w-56"
              value={cfg.tz}
              onChange={(e) => setCfg({ ...cfg, tz: e.target.value })}
            />
          </div>
          <Button variant="outline" onClick={salvar} disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar"}
          </Button>
        </div>
        {painel.config.last_run_date && (
          <p className="text-sm text-muted-foreground">
            Último envio agendado: {painel.config.last_run_date}
          </p>
        )}
      </Card>

      {ultimo && <Relatorio r={ultimo} destaque />}

      {painel.relatorios.length > 1 && (
        <div className="space-y-3">
          <p className="text-sm font-medium">Anteriores</p>
          {painel.relatorios.slice(1).map((r) => (
            <Relatorio key={r.id} r={r} />
          ))}
        </div>
      )}

      {painel.relatorios.length === 0 && (
        <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Nenhum relatório ainda</p>
          <p className="mt-1 text-sm">
            O primeiro aparece no próximo horário agendado, ou clique em
            &ldquo;Gerar agora&rdquo;.
          </p>
        </div>
      )}
    </div>
  );
}

function Relatorio({
  r,
  destaque = false,
}: {
  r: RelatorioProducao;
  destaque?: boolean;
}) {
  const [aberto, setAberto] = useState(destaque);
  return (
    <Card className={cn("p-4", destaque && "border-primary/40")}>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-md border px-2 py-0.5 text-xs font-medium",
              COR[r.severidade]
            )}
          >
            {ROTULO[r.severidade]}
          </span>
          <span className="text-sm">{quando(r.criado_at)}</span>
          <span className="text-sm text-muted-foreground">
            {r.origem === "manual" ? "sob demanda" : "agendado"}
          </span>
        </span>
        <span className="text-sm text-muted-foreground">
          {aberto ? "ocultar" : "ver"}
        </span>
      </button>

      {aberto && (
        <div className="mt-4 space-y-4">
          {/* Os achados vêm primeiro e separados: são a parte verificável, com
              limiar e evidência. O texto abaixo é redação. */}
          {r.achados.length > 0 ? (
            <div className="space-y-2">
              {r.achados.map((a) => (
                <div
                  key={a.chave}
                  className={cn("rounded-md border p-3", COR[a.severidade])}
                >
                  <p className="text-sm font-medium">{a.titulo}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {a.evidencia}
                  </p>
                  <p className="mt-1 text-sm">{a.acao}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nenhuma checagem encontrou problema.
            </p>
          )}

          {r.texto && (
            <div>
              <p className="whitespace-pre-wrap text-sm">{r.texto}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Achados são determinísticos; o texto acima é redação por IA
                {r.modelo ? ` (${r.modelo})` : ""}.
              </p>
            </div>
          )}
          {r.erro && (
            <p className="text-xs text-muted-foreground">
              Sem redação por IA: {r.erro}. Os achados acima valem assim mesmo.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";
import { ArrowLeft, Megaphone, Send, Square } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Campanha, CampanhaDestinatario } from "@/lib/api";

import {
  abortCampanhaAction,
  dispatchCampanhaAction,
  refreshCampanhaAction,
} from "../actions";

interface Props {
  campanha: Campanha;
  destinatariosIniciais: CampanhaDestinatario[];
  loadError?: string | null;
}

const STATUS_LABELS: Record<Campanha["status"], string> = {
  draft: "rascunho",
  running: "em execução",
  done: "concluída",
  partial: "parcial",
  aborted: "abortada",
};

export function CampanhaDetailClient({
  campanha: initial,
  destinatariosIniciais,
  loadError,
}: Props) {
  const [c, setC] = useState(initial);
  const [dest, setDest] = useState(destinatariosIniciais);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Polling enquanto running ou draft (pra pegar updates rápidos)
  useEffect(() => {
    if (c.status !== "running") return;
    const interval = setInterval(async () => {
      const r = await refreshCampanhaAction(c.id);
      if (r.ok) {
        setC(r.campanha);
        setDest(r.destinatarios);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [c.id, c.status]);

  function handleDispatch() {
    if (!confirm(`Disparar a campanha "${c.nome}" pra ${c.total_destinatarios} destinatários?`))
      return;
    setError(null);
    startTransition(async () => {
      const r = await dispatchCampanhaAction(c.id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setC({ ...c, status: "running", started_at: new Date().toISOString() });
    });
  }

  function handleAbort() {
    if (!confirm("Abortar campanha em execução? Pendentes não serão enviados."))
      return;
    setError(null);
    startTransition(async () => {
      const r = await abortCampanhaAction(c.id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setC({ ...c, status: "aborted" });
    });
  }

  const progress =
    c.total_destinatarios > 0
      ? ((c.enviados + c.falhas) / c.total_destinatarios) * 100
      : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/campanhas">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="size-4" />
            </Button>
          </Link>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Megaphone className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold">{c.nome}</h1>
              <Badge>{STATUS_LABELS[c.status]}</Badge>
            </div>
            {c.descricao && (
              <p className="text-sm text-muted-foreground">{c.descricao}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {c.status === "draft" && (
            <Button onClick={handleDispatch} disabled={isPending}>
              <Send className="size-3.5" />
              Disparar
            </Button>
          )}
          {c.status === "running" && (
            <Button variant="destructive" onClick={handleAbort} disabled={isPending}>
              <Square className="size-3.5" />
              Abortar
            </Button>
          )}
        </div>
      </div>

      {loadError && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {loadError}
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Progresso</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Total</p>
              <p className="text-2xl font-semibold">{c.total_destinatarios}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Enviados</p>
              <p className="text-2xl font-semibold text-emerald-400">
                {c.enviados}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Falhas</p>
              <p className="text-2xl font-semibold text-destructive">
                {c.falhas}
              </p>
            </div>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mensagem</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="whitespace-pre-wrap rounded-md bg-white/[0.04] p-3 text-sm">
            {c.mensagem}
          </pre>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Destinatários ({dest.length}{" "}
            {dest.length === 200 ? "mostrados, há mais" : ""})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {dest.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum destinatário.</p>
          ) : (
            <ul className="divide-y rounded-md border max-h-96 overflow-y-auto">
              {dest.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center justify-between gap-2 p-2.5"
                >
                  <p className="font-mono text-xs">{d.telefone}</p>
                  <div className="flex items-center gap-2">
                    {d.erro && (
                      <span className="max-w-xs truncate text-[10px] text-destructive">
                        {d.erro}
                      </span>
                    )}
                    <Badge
                      variant={
                        d.status === "enviado"
                          ? "secondary"
                          : d.status === "falhou"
                            ? "destructive"
                            : "outline"
                      }
                    >
                      {d.status}
                    </Badge>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

"use client";

import { Loader2, Star, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { HistoricoDetalhe, HistoricoRow } from "@/lib/api";

import { loadHistoricoDetalheAction } from "./actions";

function fmt(s: string | null | undefined): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const EVENTO_LABEL: Record<string, string> = {
  aberto: "Atendimento aberto",
  triagem: "Triagem IA concluída",
  transferencia: "Transferência",
  fechado: "Atendimento finalizado",
  avaliacao: "Avaliação recebida",
};

export function HistoricoDetalheDrawer({
  row,
  onClose,
}: {
  row: HistoricoRow;
  onClose: () => void;
}) {
  const [detalhe, setDetalhe] = useState<HistoricoDetalhe | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    loadHistoricoDetalheAction(row.id).then((res) => {
      if (!alive) return;
      if (res.ok) setDetalhe(res.detalhe);
      else setError(res.error);
    });
    return () => {
      alive = false;
    };
  }, [row.id]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-full max-w-2xl flex-col border-l bg-background shadow-xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b p-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-muted-foreground">
                {row.protocolo ?? `#${row.id}`}
              </span>
              <Badge variant="outline">{row.status}</Badge>
            </div>
            <h2 className="mt-1 text-lg font-semibold">
              {row.cliente_nome ?? "Cliente"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {row.cliente_telefone} · {row.conexao_nome ?? "—"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Metadados */}
        <div className="grid grid-cols-2 gap-2 border-b p-4 text-sm sm:grid-cols-3">
          <Meta label="Início" value={fmt(row.created_at)} />
          <Meta label="Fim" value={fmt(row.closed_at)} />
          <Meta label="Atendente" value={row.atendente_nome ?? "IA"} />
          <Meta label="Departamento" value={row.departamento_nome ?? "—"} />
          <Meta label="Prioridade" value={row.prioridade ?? "—"} />
          <Meta
            label="CSAT"
            value={row.nota_csat != null ? `${row.nota_csat}/10` : "—"}
          />
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {error && (
            <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          {!detalhe && !error && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Carregando...
            </div>
          )}

          {detalhe && (
            <>
              {/* Tags */}
              {detalhe.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {detalhe.tags.map((t) => (
                    <span
                      key={t.id}
                      className="rounded-full px-2 py-0.5 text-xs"
                      style={{
                        backgroundColor: (t.cor ?? "#888") + "22",
                        color: t.cor ?? undefined,
                      }}
                    >
                      {t.nome}
                      {t.aplicado_por_ia ? " · IA" : ""}
                    </span>
                  ))}
                </div>
              )}

              {/* Resumo IA */}
              {typeof detalhe.atendimento.resumo_ia === "string" &&
                detalhe.atendimento.resumo_ia && (
                  <Section title="Resumo da IA">
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {detalhe.atendimento.resumo_ia as string}
                    </p>
                  </Section>
                )}

              {/* Avaliação */}
              {detalhe.avaliacao && (
                <Section title="Avaliação (CSAT)">
                  <div className="flex items-center gap-2">
                    <Star className="h-4 w-4 text-amber-500" />
                    <span className="font-semibold">
                      {detalhe.avaliacao.nota}/10
                    </span>
                    <Badge variant="secondary">{detalhe.avaliacao.categoria}</Badge>
                  </div>
                  {detalhe.avaliacao.comentario && (
                    <p className="mt-1 text-sm text-muted-foreground">
                      “{detalhe.avaliacao.comentario}”
                    </p>
                  )}
                </Section>
              )}

              {/* Timeline de mensagens */}
              <Section title={`Conversa (${detalhe.mensagens.length})`}>
                <div className="space-y-2">
                  {detalhe.mensagens.map((m, i) => (
                    <Mensagem key={i} m={m} />
                  ))}
                </div>
              </Section>

              {/* Transferências */}
              {detalhe.transferencias.length > 0 && (
                <Section title="Transferências">
                  <ul className="space-y-1 text-sm">
                    {detalhe.transferencias.map((t) => (
                      <li key={t.id} className="text-muted-foreground">
                        {fmt(t.created_at)} →{" "}
                        {t.para_depto_nome || t.para_user_nome || "—"}
                        {t.motivo ? ` · ${t.motivo}` : ""}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Jornada no chatbot/menu */}
              {detalhe.menu_historico.length > 0 && (
                <Section title="Jornada no chatbot">
                  <ol className="space-y-1 text-sm">
                    {detalhe.menu_historico.map((s, i) => (
                      <li key={i} className="text-muted-foreground">
                        <span className="text-foreground">
                          {s.item_label ?? s.menu_nome ?? "Menu"}
                        </span>
                        {s.resposta ? ` · respondeu “${s.resposta}”` : ""} ·{" "}
                        {fmt(s.escolhido_at)}
                      </li>
                    ))}
                  </ol>
                </Section>
              )}

              {/* Eventos */}
              {detalhe.eventos.length > 0 && (
                <Section title="Linha do tempo">
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {detalhe.eventos.map((e, i) => (
                      <li key={i}>
                        <span className="text-foreground">
                          {EVENTO_LABEL[e.tipo] ?? e.tipo}
                        </span>{" "}
                        · {fmt(String(e.at))}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium capitalize">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Mensagem({
  m,
}: {
  m: {
    incoming_message: string | null;
    response: string | null;
    interna?: boolean;
    created_at: string | null;
  };
}) {
  // Nota interna
  if (m.interna && m.response) {
    return (
      <div className="rounded-md border border-amber-400/40 bg-amber-50/50 px-3 py-2 text-sm dark:bg-amber-950/20">
        <span className="text-xs font-medium text-amber-700 dark:text-amber-400">
          Nota interna
        </span>
        <p className="whitespace-pre-wrap">{m.response}</p>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {m.incoming_message && (
        <div className="max-w-[80%] rounded-lg bg-muted px-3 py-2 text-sm">
          {m.incoming_message}
        </div>
      )}
      {m.response && (
        <div className="ml-auto max-w-[80%] rounded-lg bg-primary/10 px-3 py-2 text-sm">
          {m.response}
        </div>
      )}
    </div>
  );
}

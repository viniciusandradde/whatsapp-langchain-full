"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { Megaphone, Plus, Send, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Campanha, Conexao } from "@/lib/api";

import { createCampanhaAction } from "./actions";

interface Props {
  initialCampanhas: Campanha[];
  conexoes: Conexao[];
  loadError?: string | null;
}

const STATUS_LABELS: Record<Campanha["status"], string> = {
  draft: "rascunho",
  running: "em execução",
  done: "concluída",
  partial: "parcial",
  aborted: "abortada",
};

const STATUS_VARIANTS: Record<Campanha["status"], "default" | "outline" | "secondary" | "destructive"> = {
  draft: "outline",
  running: "default",
  done: "secondary",
  partial: "outline",
  aborted: "destructive",
};

export function CampanhasPageClient({
  initialCampanhas,
  conexoes,
  loadError,
}: Props) {
  const [campanhas, setCampanhas] = useState(initialCampanhas);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const fd = new FormData(e.currentTarget);
    const telefonesRaw = String(fd.get("telefones") || "").trim();
    const telefones = telefonesRaw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (telefones.length === 0) {
      setError("Adicione ao menos 1 telefone.");
      return;
    }

    const conexaoRaw = String(fd.get("conexao_id") || "").trim();
    const modeloRaw = String(fd.get("modelo_mensagem_id") || "").trim();
    const tagsRaw = String(fd.get("filtro_tags") || "").trim();
    const scheduledRaw = String(fd.get("scheduled_at") || "").trim();
    const body = {
      nome: String(fd.get("nome") || "").trim(),
      descricao: (String(fd.get("descricao") || "").trim() || null) as
        | string
        | null,
      mensagem: String(fd.get("mensagem") || "").trim(),
      conexao_id: conexaoRaw ? Number(conexaoRaw) : null,
      intervalo_ms: Number(fd.get("intervalo_ms") || 500),
      max_destinatarios: Number(fd.get("max_destinatarios") || 1000),
      telefones,
      // Sub-fase B+ paridade ZigChat (mig 051)
      modelo_mensagem_id: modeloRaw ? Number(modeloRaw) : null,
      scheduled_at: scheduledRaw ? new Date(scheduledRaw).toISOString() : null,
      tipo: (String(fd.get("tipo") || "broadcast") as "broadcast" | "transactional" | "reativacao"),
      filtro_segmento: String(fd.get("filtro_segmento") || "").trim() || null,
      filtro_tags: tagsRaw
        ? tagsRaw.split(",").map((s) => s.trim()).filter(Boolean)
        : null,
    };

    startTransition(async () => {
      const r = await createCampanhaAction(body);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setCampanhas([r.data, ...campanhas]);
      setCreating(false);
      setSuccess(`Campanha criada com ${r.data.total_destinatarios} destinatário(s).`);
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Megaphone className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Campanhas</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Broadcast de mensagem pra lista de telefones via WhatsApp.
            </p>
          </div>
        </div>
        <Button
          onClick={() => setCreating(true)}
          disabled={creating || isPending}
        >
          <Plus className="size-4" />
          Nova campanha
        </Button>
      </div>

      {loadError && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {loadError}
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-emerald-300">{success}</p>}

      {creating && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Nova campanha</CardTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCreating(false)}
              >
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Nome
                </label>
                <input
                  name="nome"
                  required
                  maxLength={120}
                  placeholder="Promoção Black Friday"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Descrição (opcional)
                </label>
                <input
                  name="descricao"
                  maxLength={500}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Mensagem
                </label>
                <textarea
                  name="mensagem"
                  required
                  maxLength={4000}
                  rows={4}
                  placeholder="Olá! Promoção válida até..."
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                    Conexão
                  </label>
                  <select
                    name="conexao_id"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="">Primeira ativa</option>
                    {conexoes.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.from_number} ({c.provider})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                    Intervalo (ms)
                  </label>
                  <input
                    type="number"
                    name="intervalo_ms"
                    defaultValue={500}
                    min={0}
                    max={60_000}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                    Máx destinatários
                  </label>
                  <input
                    type="number"
                    name="max_destinatarios"
                    defaultValue={1000}
                    min={1}
                    max={10_000}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Telefones (1 por linha, vírgula ou espaço)
                </label>
                <textarea
                  name="telefones"
                  required
                  rows={6}
                  placeholder={"+5511999999999\n+5511988888888"}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Telefones inválidos (&lt;8 dígitos) são descartados.
                  Duplicados são ignorados.
                </p>
              </div>

              {/* Sub-fase B+ paridade ZigChat (mig 051) */}
              <div className="rounded-md border border-border/40 bg-muted/20 p-3 space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide">
                  Avançado (paridade ZigChat)
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Tipo
                    </label>
                    <select
                      name="tipo"
                      defaultValue="broadcast"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      <option value="broadcast">Broadcast (livre)</option>
                      <option value="transactional">Transacional</option>
                      <option value="reativacao">Reativação</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Template (modelo_mensagem ID)
                    </label>
                    <input
                      type="number"
                      name="modelo_mensagem_id"
                      placeholder="ID em /modelos"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      Pra HSM aprovado (WABA) — substitui campo Mensagem
                    </p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Agendar pra (datetime local)
                    </label>
                    <input
                      type="datetime-local"
                      name="scheduled_at"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      Vazio = inicia manualmente
                    </p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Filtro: segmento
                    </label>
                    <input
                      type="text"
                      name="filtro_segmento"
                      maxLength={120}
                      placeholder='Ex: "lead-quente"'
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Filtro: tags (separadas por vírgula)
                    </label>
                    <input
                      type="text"
                      name="filtro_tags"
                      placeholder="vip, eventos-2026"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Filtros são metadados — NÃO substituem a lista de telefones
                  (filtrar de fato fica pra dispatcher futuro).
                </p>
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setCreating(false)}
                  disabled={isPending}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={isPending}>
                  <Send className="size-3.5" />
                  Criar como rascunho
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {campanhas.length} campanha(s)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {campanhas.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma campanha ainda. Use &quot;Nova campanha&quot; pra criar.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {campanhas.map((c) => (
                <li key={c.id} className="p-3">
                  <Link
                    href={`/campanhas/${c.id}`}
                    className="flex items-start justify-between gap-3 hover:opacity-80"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{c.nome}</p>
                        <Badge variant={STATUS_VARIANTS[c.status]}>
                          {STATUS_LABELS[c.status]}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {c.enviados}/{c.total_destinatarios} enviados ·
                        {" "}{c.falhas} falhas ·{" "}
                        {new Date(c.created_at).toLocaleString("pt-BR")}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

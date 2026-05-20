"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  CircleCheck,
  CircleX,
  Clock,
  Download,
  FileText,
  PlusCircle,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { WabaTemplate, WabaTemplateStatus } from "@/lib/api";

import {
  deleteTemplateAction,
  importFromMetaAction,
  syncTemplateAction,
} from "./actions";
import { NewTemplateModal } from "./new-template-modal";
import { TestSendModal } from "./test-send-modal";

interface Props {
  conexaoId: number;
  initialTemplates: WabaTemplate[];
}

const STATUS_CFG: Record<
  WabaTemplateStatus,
  { label: string; cls: string; icon: typeof CircleCheck }
> = {
  draft: {
    label: "Rascunho",
    cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    icon: FileText,
  },
  pending: {
    label: "Pendente",
    cls: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    icon: Clock,
  },
  approved: {
    label: "Aprovado",
    cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    icon: CircleCheck,
  },
  rejected: {
    label: "Rejeitado",
    cls: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    icon: CircleX,
  },
  paused: {
    label: "Pausado",
    cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    icon: Clock,
  },
  disabled: {
    label: "Desativado",
    cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    icon: CircleX,
  },
};

function StatusBadge({ status }: { status: WabaTemplateStatus }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft;
  const Icon = cfg.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs",
        cfg.cls
      )}
    >
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

export function TemplatesList({ conexaoId, initialTemplates }: Props) {
  const router = useRouter();
  const [templates, setTemplates] = useState(initialTemplates);
  const [showNew, setShowNew] = useState(false);
  const [testSendId, setTestSendId] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [, startTransition] = useTransition();

  function handleSync(id: number) {
    setBusy(id);
    startTransition(async () => {
      const r = await syncTemplateAction(conexaoId, id);
      setBusy(null);
      if (r.ok && r.data) {
        setTemplates((prev) => prev.map((t) => (t.id === id ? r.data! : t)));
      } else if (!r.ok) {
        alert(`Erro: ${r.error}`);
      }
    });
  }

  function handleDelete(id: number) {
    if (!confirm("Excluir template? (Também remove da Meta)")) return;
    setBusy(id);
    startTransition(async () => {
      const r = await deleteTemplateAction(conexaoId, id);
      setBusy(null);
      if (r.ok) setTemplates((prev) => prev.filter((t) => t.id !== id));
      else alert(`Erro: ${r.error}`);
    });
  }

  function handleImport() {
    if (
      !confirm(
        "Importar templates já aprovados na Meta que ainda não estão no painel?"
      )
    )
      return;
    startTransition(async () => {
      const r = await importFromMetaAction(conexaoId);
      if (r.ok) {
        alert(
          `Importação concluída: ${r.data!.imported} novos, ${r.data!.skipped} já existentes.`
        );
        router.refresh();
      } else {
        alert(`Erro: ${r.error}`);
      }
    });
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {templates.length}{" "}
          {templates.length === 1 ? "template" : "templates"} cadastrados
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleImport} className="gap-1.5">
            <Download className="h-4 w-4" />
            Importar da Meta
          </Button>
          <Button onClick={() => setShowNew(true)} className="gap-1.5">
            <PlusCircle className="h-4 w-4" />
            Novo template
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border/40">
        {templates.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-12 text-sm text-muted-foreground">
            <FileText className="h-8 w-8 opacity-50" />
            <p>Nenhum template cadastrado.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border/40 bg-muted/20">
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">Nome</th>
                <th className="px-3 py-2 font-medium">Categoria</th>
                <th className="px-3 py-2 font-medium">Idioma</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="w-32 px-3 py-2 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-border/20 last:border-0 hover:bg-muted/10"
                >
                  <td className="px-3 py-2 font-mono text-xs">{t.nome}</td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className="font-normal text-xs">
                      {t.categoria}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {t.idioma}
                  </td>
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <StatusBadge status={t.status} />
                      {t.status === "rejected" && t.motivo_rejeicao && (
                        <p
                          className="max-w-[300px] truncate text-[10px] text-rose-400"
                          title={t.motivo_rejeicao}
                        >
                          {t.motivo_rejeicao}
                        </p>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      {t.meta_template_id && (
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Sincronizar status com Meta"
                          disabled={busy === t.id}
                          onClick={() => handleSync(t.id)}
                          className="h-7 w-7 p-0"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      {t.status === "approved" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Testar envio"
                          onClick={() => setTestSendId(t.id)}
                          className="h-7 w-7 p-0"
                        >
                          <Send className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Excluir"
                        disabled={busy === t.id}
                        onClick={() => handleDelete(t.id)}
                        className="h-7 w-7 p-0 text-rose-400 hover:text-rose-300"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showNew && (
        <NewTemplateModal
          conexaoId={conexaoId}
          onClose={(refresh) => {
            setShowNew(false);
            if (refresh) router.refresh();
          }}
        />
      )}
      {testSendId !== null && (
        <TestSendModal
          conexaoId={conexaoId}
          template={templates.find((t) => t.id === testSendId)!}
          onClose={() => setTestSendId(null)}
        />
      )}
    </>
  );
}

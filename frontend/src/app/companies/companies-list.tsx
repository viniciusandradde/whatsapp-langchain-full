"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Loader2, Plus, Pencil, RotateCcw, Users } from "lucide-react";

import { reativarEmpresaAction } from "./actions";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Empresa } from "@/lib/api";

import { CsatConfigSection, EmpresaForm } from "./empresa-form";

interface Props {
  empresas: Empresa[];
}

export function CompaniesList({ empresas }: Props) {
  const [editing, setEditing] = useState<Empresa | "new" | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Empresas em que você tem acesso. Quem cria vira admin.
        </p>
        {editing !== "new" && (
          <Button onClick={() => setEditing("new")}>
            <Plus className="size-4" />
            Nova empresa
          </Button>
        )}
      </div>

      {editing === "new" && <EmpresaForm onDone={() => setEditing(null)} />}
      {editing && editing !== "new" && (
        <>
          <EmpresaForm initial={editing} onDone={() => setEditing(null)} />
          <CsatConfigSection empresaId={editing.id} />
        </>
      )}

      {empresas.length === 0 && !editing && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Nenhuma empresa</p>
          <p className="mt-1 text-sm">
            Crie a primeira pra hospedar conexões e agentes.
          </p>
        </div>
      )}

      {empresas.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {empresas.map((e) => {
            const isAdmin = e.my_role === "admin";
            return (
              <Card key={e.id}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle className="truncate">{e.nome}</CardTitle>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {e.slug}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge variant="secondary">{e.plano}</Badge>
                      {e.my_role && (
                        <Badge
                          variant={
                            e.my_role === "admin" ? "default" : "outline"
                          }
                        >
                          {e.my_role}
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-1.5 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Status</span>
                    <StatusBadge status={e.status} />
                  </div>
                  {e.status !== "active" && (
                    <p className="text-xs text-amber-500">
                      Empresa fora do ar: não aparece no seletor de empresas.
                      {isAdmin && " Use Reativar pra voltar."}
                    </p>
                  )}
                  {e.doc && <Row label="Documento" value={e.doc} mono />}
                </CardContent>
                <div className="flex items-center justify-end gap-2 px-4 pb-4">
                  <Link
                    href={`/companies/${e.id}/members`}
                    className="inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-[0.8rem] text-muted-foreground transition-all hover:bg-white/[0.05] hover:text-foreground"
                  >
                    <Users className="size-3.5" />
                    Membros
                  </Link>
                  {isAdmin && e.status !== "active" && (
                    <ReativarButton empresaId={e.id} nome={e.nome} />
                  )}
                  {isAdmin && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditing(e)}
                    >
                      <Pencil className="size-3.5" />
                      Editar
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  active: {
    label: "ativa",
    className: "bg-green-500/15 text-green-700 dark:text-green-400",
  },
  suspended: {
    label: "suspensa",
    className: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  },
  archived: {
    label: "arquivada",
    className: "bg-muted text-muted-foreground",
  },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? {
    label: status,
    className: "bg-muted text-muted-foreground",
  };
  return (
    <span
      className={`inline-flex rounded px-1.5 py-0.5 text-xs ${s.className}`}
    >
      {s.label}
    </span>
  );
}

function ReativarButton({
  empresaId,
  nome,
}: {
  empresaId: number;
  nome: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();
  const handle = () => {
    if (!confirm(`Reativar a empresa "${nome}"?`)) return;
    setBusy(true);
    startTransition(async () => {
      const r = await reativarEmpresaAction(empresaId);
      setBusy(false);
      if (r.ok) router.refresh();
      else alert(`Erro: ${r.error}`);
    });
  };
  return (
    <Button variant="outline" size="sm" onClick={handle} disabled={busy}>
      {busy ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : (
        <RotateCcw className="size-3.5" />
      )}
      Reativar
    </Button>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-xs" : ""}>{value}</span>
    </div>
  );
}

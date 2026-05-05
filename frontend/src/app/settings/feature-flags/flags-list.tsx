"use client";

import { useState, useTransition } from "react";
import { Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { FeatureFlag } from "@/lib/api";

import { deleteFlagAction, upsertFlagAction } from "./actions";

interface Props {
  initialFlags: FeatureFlag[];
}

export function FlagsList({ initialFlags }: Props) {
  const [flags, setFlags] = useState(initialFlags);
  const [editing, setEditing] = useState<FeatureFlag | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const fd = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await upsertFlagAction(fd);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      if (r.flag) {
        const next = [...flags];
        const idx = next.findIndex((f) => f.key === r.flag!.key);
        if (idx >= 0) next[idx] = r.flag;
        else next.push(r.flag);
        next.sort((a, b) => a.key.localeCompare(b.key));
        setFlags(next);
      }
      setEditing(null);
      setSuccess("Flag salva.");
    });
  }

  function handleDelete(key: string) {
    if (!confirm(`Deletar flag "${key}"?`)) return;
    setError(null);
    startTransition(async () => {
      const r = await deleteFlagAction(key);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setFlags((prev) => prev.filter((f) => f.key !== key));
      setSuccess("Flag removida.");
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {flags.length} flag(s) configurada(s)
        </p>
        <Button onClick={() => setEditing("new")} disabled={isPending}>
          <Plus className="size-3.5" />
          Nova flag
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-emerald-300">{success}</p>}

      {editing && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {editing === "new" ? "Nova flag" : `Editar "${editing.key}"`}
              </CardTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setEditing(null)}
              >
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Key (kebab-case)
                </label>
                <input
                  name="key"
                  required
                  pattern="[a-z0-9_-]+"
                  defaultValue={editing === "new" ? "" : editing.key}
                  readOnly={editing !== "new"}
                  placeholder="mcp_beta"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm read-only:opacity-60"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Value (JSON — booleano/string/objeto)
                </label>
                <input
                  name="value"
                  defaultValue={
                    editing === "new"
                      ? "true"
                      : JSON.stringify(editing.value)
                  }
                  placeholder="true"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Ex: <code>true</code> · <code>"variant_A"</code> ·{" "}
                  <code>{`{"limit":100}`}</code>
                </p>
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Descrição
                </label>
                <input
                  name="descricao"
                  defaultValue={
                    editing === "new" ? "" : editing.descricao ?? ""
                  }
                  maxLength={300}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="ativo"
                  defaultChecked={editing === "new" ? true : editing.ativo}
                  className="size-4"
                />
                Ativo (cache invalidate ocorre no save)
              </label>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setEditing(null)}
                  disabled={isPending}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={isPending}>
                  Salvar
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {flags.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              Nenhuma flag. Use "Nova flag" pra ativar feature opt-in numa empresa.
            </p>
          ) : (
            <ul className="divide-y">
              {flags.map((f) => (
                <li
                  key={f.id}
                  className="flex items-start justify-between gap-3 p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="font-mono text-sm font-semibold">
                        {f.key}
                      </code>
                      <Badge variant={f.ativo ? "default" : "outline"}>
                        {f.ativo ? "ativo" : "inativo"}
                      </Badge>
                      <code className="font-mono text-[11px] text-muted-foreground">
                        {JSON.stringify(f.value)}
                      </code>
                    </div>
                    {f.descricao && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {f.descricao}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setEditing(f)}
                    >
                      Editar
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(f.key)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
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

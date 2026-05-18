"use client";

import { useState, useTransition } from "react";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";

import { TagChip } from "@/app/atendimento/tag-chip";
import {
  createTagAction,
  deleteTagAction,
  loadTagsAction,
  updateTagAction,
} from "@/app/atendimento/actions";
import { Button } from "@/components/ui/button";
import { usePermission } from "@/hooks/use-permission";
import type { Tag } from "@/lib/api";

const CORES = [
  "#64748b",
  "#dc2626",
  "#ea580c",
  "#ca8a04",
  "#16a34a",
  "#0891b2",
  "#2563eb",
  "#9333ea",
  "#db2777",
];

interface Props {
  initialTags: Tag[];
}

export function TagsAdmin({ initialTags }: Props) {
  const canManage = usePermission("tag.manage");
  const [tags, setTags] = useState<Tag[]>(initialTags);
  const [editing, setEditing] = useState<Tag | "new" | null>(null);

  const refresh = async () => {
    const r = await loadTagsAction(false);
    if (r.ok) setTags(r.tags);
  };

  if (!canManage) {
    return (
      <p className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
        Você não tem permissão para gerenciar tags (
        <code className="rounded bg-muted px-1 text-xs">tag.manage</code>).
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing("new")} size="sm">
          <Plus className="mr-1 h-4 w-4" />
          Nova tag
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left">Tag</th>
              <th className="px-3 py-2 text-left">Cor</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {tags.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  className="px-3 py-6 text-center text-muted-foreground"
                >
                  Nenhuma tag cadastrada.
                </td>
              </tr>
            )}
            {tags.map((tag) => (
              <tr key={tag.id} className="border-t">
                <td className="px-3 py-2">
                  <TagChip nome={tag.nome} cor={tag.cor} size="sm" />
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                  {tag.cor ?? "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex rounded px-1.5 py-0.5 text-xs ${
                      tag.ativo
                        ? "bg-green-500/15 text-green-700 dark:text-green-400"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {tag.ativo ? "ativa" : "inativa"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => setEditing(tag)}
                    title="Editar"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <DeleteButton tag={tag} onDeleted={refresh} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing !== null && (
        <TagModal
          tag={editing === "new" ? null : editing}
          onClose={(refreshed) => {
            setEditing(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </div>
  );
}

function DeleteButton({
  tag,
  onDeleted,
}: {
  tag: Tag;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();
  const handle = () => {
    if (
      !confirm(
        `Excluir tag "${tag.nome}"? Será removida de todos os atendimentos.`
      )
    )
      return;
    setBusy(true);
    startTransition(async () => {
      const r = await deleteTagAction(tag.id);
      setBusy(false);
      if (r.ok) onDeleted();
      else alert(`Erro: ${r.error}`);
    });
  };
  return (
    <Button
      size="sm"
      variant="ghost"
      className="h-7 w-7 p-0 hover:text-destructive"
      onClick={handle}
      disabled={busy}
      title="Excluir"
    >
      {busy ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Trash2 className="h-3.5 w-3.5" />
      )}
    </Button>
  );
}

function TagModal({
  tag,
  onClose,
}: {
  tag: Tag | null;
  onClose: (refreshed: boolean) => void;
}) {
  const isEdit = tag !== null;
  const [nome, setNome] = useState(tag?.nome ?? "");
  const [cor, setCor] = useState<string | null>(tag?.cor ?? "#64748b");
  const [ativo, setAtivo] = useState(tag?.ativo ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const n = nome.trim();
    if (!n) return setError("Informe um nome.");
    setBusy(true);
    setError(null);
    startTransition(async () => {
      const r = isEdit
        ? await updateTagAction(tag!.id, { nome: n, cor, ativo })
        : await createTagAction({ nome: n, cor });
      setBusy(false);
      if (r.ok) onClose(true);
      else setError(r.error);
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => onClose(false)}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b p-4">
          <h2 className="text-lg font-semibold">
            {isEdit ? "Editar tag" : "Nova tag"}
          </h2>
        </div>
        <form onSubmit={submit} className="space-y-4 p-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Nome <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              autoFocus
              maxLength={80}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex: VIP, Urgente, Cobrança"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Cor</label>
            <div className="flex flex-wrap gap-2">
              {CORES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCor(c)}
                  className="h-7 w-7 rounded-full border-2 transition-all"
                  style={{
                    backgroundColor: c,
                    borderColor: cor === c ? "#fff" : "transparent",
                    boxShadow: cor === c ? `0 0 0 2px ${c}` : undefined,
                  }}
                  aria-label={`Cor ${c}`}
                />
              ))}
            </div>
          </div>
          {isEdit && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={ativo}
                onChange={(e) => setAtivo(e.target.checked)}
              />
              Ativa (aparece nas opções de aplicar)
            </label>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onClose(false)}
              disabled={busy}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={busy}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEdit ? "Salvar" : "Criar tag"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

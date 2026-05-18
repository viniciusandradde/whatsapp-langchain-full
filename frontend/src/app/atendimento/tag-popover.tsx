"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { Check, Loader2, Plus, Search, Tag as TagIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { usePermission } from "@/hooks/use-permission";
import type { AtendimentoTag, Tag } from "@/lib/api";

import {
  applyTagsAtendimentoAction,
  createTagAction,
  loadTagsAction,
  loadTagsAtendimentoAction,
} from "./actions";
import { TagChip } from "./tag-chip";

interface Props {
  atendimentoId: number;
  initialTags?: AtendimentoTag[];
  /** Notifica quando há mudança (depois do apply) pra UI parent atualizar */
  onChange?: () => void;
}

/**
 * Popover de seleção de tags do atendimento. Lista todas as tags da empresa;
 * marca as que já estão aplicadas. Click toggle (apply/remove via delta API).
 *
 * Admin (perm `tag.manage`) vê botão "+ Nova tag" pra criar inline.
 */
export function TagPopover({ atendimentoId, initialTags, onChange }: Props) {
  const canManageTags = usePermission("tag.manage");
  const [open, setOpen] = useState(false);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [applied, setApplied] = useState<AtendimentoTag[]>(initialTags ?? []);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();
  const [busy, setBusy] = useState<number | null>(null);

  const appliedIds = useMemo(
    () => new Set(applied.map((a) => a.id)),
    [applied]
  );

  // Carrega lista quando abrir
  useEffect(() => {
    if (!open) return;
    (async () => {
      const [a, t] = await Promise.all([
        loadTagsAtendimentoAction(atendimentoId),
        loadTagsAction(true),
      ]);
      if (a.ok) setApplied(a.tags);
      if (t.ok) setAllTags(t.tags);
    })();
  }, [open, atendimentoId]);

  const visibleTags = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return allTags;
    return allTags.filter((t) => t.nome.toLowerCase().includes(q));
  }, [allTags, search]);

  const toggle = (tag: Tag) => {
    setBusy(tag.id);
    setError(null);
    const isOn = appliedIds.has(tag.id);
    startTransition(async () => {
      const r = await applyTagsAtendimentoAction(atendimentoId, {
        add: isOn ? [] : [tag.id],
        remove: isOn ? [tag.id] : [],
      });
      setBusy(null);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      // Refresh aplicadas
      const a = await loadTagsAtendimentoAction(atendimentoId);
      if (a.ok) setApplied(a.tags);
      onChange?.();
    });
  };

  const create = () => {
    const nome = newName.trim();
    if (!nome) return;
    setError(null);
    setCreating(true);
    startTransition(async () => {
      const r = await createTagAction({ nome });
      setCreating(false);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setNewName("");
      // Adiciona à lista + aplica logo
      setAllTags((prev) => [...prev, r.tag]);
      await applyTagsAtendimentoAction(atendimentoId, {
        add: [r.tag.id],
        remove: [],
      });
      const a = await loadTagsAtendimentoAction(atendimentoId);
      if (a.ok) setApplied(a.tags);
      onChange?.();
    });
  };

  return (
    <div className="relative inline-block">
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen((v) => !v)}
        className="h-7 gap-1"
      >
        <TagIcon className="h-3.5 w-3.5" />
        Tags
        {applied.length > 0 && (
          <span className="ml-1 rounded-full bg-brand-primary/15 px-1.5 text-xs font-medium text-brand-primary">
            {applied.length}
          </span>
        )}
      </Button>

      {open && (
        <>
          {/* Backdrop pra fechar ao clicar fora */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 z-50 mt-1 w-72 rounded-lg border bg-popover p-3 shadow-lg">
            <div className="mb-2 flex items-center gap-2 rounded-md border bg-background px-2 py-1">
              <Search className="h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar tag..."
                className="w-full bg-transparent text-sm focus:outline-none"
              />
            </div>

            <ul className="max-h-64 space-y-0.5 overflow-y-auto">
              {visibleTags.length === 0 && (
                <li className="py-2 text-center text-xs text-muted-foreground">
                  {search ? "Nenhuma tag encontrada." : "Nenhuma tag cadastrada."}
                </li>
              )}
              {visibleTags.map((tag) => {
                const isOn = appliedIds.has(tag.id);
                return (
                  <li key={tag.id}>
                    <button
                      type="button"
                      onClick={() => toggle(tag)}
                      disabled={busy === tag.id}
                      className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted transition-colors disabled:opacity-50"
                    >
                      <TagChip nome={tag.nome} cor={tag.cor} size="sm" />
                      {busy === tag.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                      ) : isOn ? (
                        <Check className="h-3.5 w-3.5 text-brand-primary" />
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>

            {canManageTags && (
              <div className="mt-2 border-t pt-2">
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && create()}
                    placeholder="Nova tag..."
                    className="w-full rounded-md border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 shrink-0 p-0"
                    onClick={create}
                    disabled={!newName.trim() || creating}
                  >
                    {creating ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Plus className="h-3 w-3" />
                    )}
                  </Button>
                </div>
              </div>
            )}

            {error && (
              <p className="mt-2 text-xs text-destructive">{error}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

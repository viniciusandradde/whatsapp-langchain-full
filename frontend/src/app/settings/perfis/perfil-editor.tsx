"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { Save, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PermissaoCatalogo } from "@/lib/api";

import {
  createPerfilAction,
  loadPerfilAction,
  updatePerfilAction,
} from "./actions";

interface Props {
  mode: "new" | "edit";
  perfilId?: number;
  catalogo: PermissaoCatalogo[];
  onClose: () => void;
}

export function PerfilEditor({ mode, perfilId, catalogo, onClose }: Props) {
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [perms, setPerms] = useState<Set<string>>(new Set());
  const [isSystem, setIsSystem] = useState(false);
  const [loading, setLoading] = useState(mode === "edit");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Carrega perfil existente quando abre em modo edit
  useEffect(() => {
    if (mode !== "edit" || !perfilId) return;
    let cancelled = false;
    (async () => {
      const r = await loadPerfilAction(perfilId);
      if (cancelled) return;
      if (!r.ok) {
        setError(r.error);
        setLoading(false);
        return;
      }
      setNome(r.perfil.nome);
      setDescricao(r.perfil.descricao ?? "");
      setPerms(new Set(r.perfil.permissoes ?? []));
      setIsSystem(r.perfil.is_system);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, perfilId]);

  // Agrupa catálogo por módulo pro checkbox tree
  const grouped = useMemo(() => {
    const map = new Map<string, PermissaoCatalogo[]>();
    for (const p of catalogo) {
      const arr = map.get(p.modulo) ?? [];
      arr.push(p);
      map.set(p.modulo, arr);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [catalogo]);

  function togglePerm(codigo: string) {
    if (isSystem) return;
    setPerms((prev) => {
      const next = new Set(prev);
      if (next.has(codigo)) next.delete(codigo);
      else next.add(codigo);
      return next;
    });
  }

  function toggleModulo(perms_modulo: PermissaoCatalogo[]) {
    if (isSystem) return;
    const codes = perms_modulo.map((p) => p.codigo);
    const allSelected = codes.every((c) => perms.has(c));
    setPerms((prev) => {
      const next = new Set(prev);
      for (const c of codes) {
        if (allSelected) next.delete(c);
        else next.add(c);
      }
      return next;
    });
  }

  function handleSave() {
    if (isSystem) {
      setError("Perfil system não pode ser editado.");
      return;
    }
    if (!nome.trim()) {
      setError("Nome é obrigatório.");
      return;
    }
    setError(null);
    startTransition(async () => {
      const body = {
        nome: nome.trim(),
        descricao: descricao.trim() || null,
        permissoes: Array.from(perms),
      };
      const r =
        mode === "new"
          ? await createPerfilAction(body)
          : await updatePerfilAction(perfilId!, {
              permissoes: body.permissoes,
              descricao: body.descricao,
            });
      if (!r.ok) {
        setError(r.error);
        return;
      }
      onClose();
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">
            {mode === "new"
              ? "Novo perfil"
              : isSystem
                ? `Perfil "${nome}" (system, read-only)`
                : `Editar perfil "${nome}"`}
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar">
            <X className="size-4" />
          </Button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {loading ? (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          ) : (
            <>
              <div>
                <label className="text-sm font-medium" htmlFor="nome">
                  Nome
                </label>
                <input
                  id="nome"
                  type="text"
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  disabled={mode === "edit" || isSystem || isPending}
                  className="mt-1.5 w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm disabled:opacity-50"
                />
                {mode === "edit" && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Nome não pode ser alterado depois de criado.
                  </p>
                )}
              </div>

              <div>
                <label className="text-sm font-medium" htmlFor="desc">
                  Descrição
                </label>
                <input
                  id="desc"
                  type="text"
                  value={descricao}
                  onChange={(e) => setDescricao(e.target.value)}
                  disabled={isSystem || isPending}
                  className="mt-1.5 w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm disabled:opacity-50"
                />
              </div>

              <div>
                <p className="text-sm font-medium">
                  Permissões ({perms.size}/{catalogo.length})
                </p>
                <div className="mt-3 space-y-3">
                  {grouped.map(([modulo, perms_modulo]) => {
                    const allSelected = perms_modulo.every((p) => perms.has(p.codigo));
                    const someSelected = perms_modulo.some((p) => perms.has(p.codigo));
                    return (
                      <div
                        key={modulo}
                        className="rounded-md border border-white/[0.06] bg-white/[0.02] p-3"
                      >
                        <label className="mb-2 flex items-center gap-2 text-sm font-semibold">
                          <input
                            type="checkbox"
                            checked={allSelected}
                            ref={(el) => {
                              if (el) el.indeterminate = someSelected && !allSelected;
                            }}
                            onChange={() => toggleModulo(perms_modulo)}
                            disabled={isSystem || isPending}
                            className="size-4"
                          />
                          <span className="capitalize">{modulo}</span>
                          <span className="text-xs text-muted-foreground">
                            ({perms_modulo.filter((p) => perms.has(p.codigo)).length}/{perms_modulo.length})
                          </span>
                        </label>
                        <ul className="ml-6 space-y-1">
                          {perms_modulo.map((p) => (
                            <li key={p.codigo}>
                              <label className="flex items-start gap-2 text-xs">
                                <input
                                  type="checkbox"
                                  checked={perms.has(p.codigo)}
                                  onChange={() => togglePerm(p.codigo)}
                                  disabled={isSystem || isPending}
                                  className="mt-0.5 size-3.5"
                                />
                                <div>
                                  <span className="font-mono text-[11px]">{p.codigo}</span>
                                  <span className="ml-2 text-muted-foreground">{p.descricao}</span>
                                </div>
                              </label>
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              </div>

              {error && (
                <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t p-4">
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {isSystem ? "Fechar" : "Cancelar"}
          </Button>
          {!isSystem && (
            <Button onClick={handleSave} disabled={loading || isPending}>
              <Save className="size-3.5" />
              Salvar
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
}

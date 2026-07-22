"use client";

import { useState, useTransition } from "react";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { usePermission } from "@/hooks/use-permission";
import type { WhitelistNumero } from "@/lib/api";

import {
  createWhitelistAction,
  deleteWhitelistAction,
  loadWhitelistAction,
  updateWhitelistAction,
} from "./actions";

interface Props {
  initialItems: WhitelistNumero[];
}

export function WhitelistAdmin({ initialItems }: Props) {
  const canManage = usePermission("whitelist.manage");
  const [items, setItems] = useState<WhitelistNumero[]>(initialItems);
  const [editing, setEditing] = useState<WhitelistNumero | "new" | null>(null);

  const refresh = async () => {
    const r = await loadWhitelistAction();
    if (r.ok) setItems(r.data);
  };

  if (!canManage) {
    return (
      <p className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
        Você não tem permissão para gerenciar a whitelist (
        <code className="rounded bg-muted px-1 text-xs">whitelist.manage</code>
        ).
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing("new")} size="sm">
          <Plus className="mr-1 h-4 w-4" />
          Novo número
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left">Telefone</th>
              <th className="px-3 py-2 text-left">Nome</th>
              <th className="px-3 py-2 text-left">Cadastrado em</th>
              <th className="px-3 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  className="px-3 py-6 text-center text-muted-foreground"
                >
                  Nenhum número cadastrado — a IA responde a todos os contatos.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-t">
                <td className="px-3 py-2 font-mono text-xs">{item.telefone}</td>
                <td className="px-3 py-2">{item.nome || "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {item.created_at
                    ? new Date(item.created_at).toLocaleDateString("pt-BR")
                    : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => setEditing(item)}
                    title="Editar nome"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <DeleteButton item={item} onDeleted={refresh} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing !== null && (
        <WhitelistModal
          item={editing === "new" ? null : editing}
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
  item,
  onDeleted,
}: {
  item: WhitelistNumero;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();
  const handle = () => {
    if (
      !confirm(
        `Remover ${item.nome || item.telefone} da whitelist? A IA voltará a responder esse número.`
      )
    )
      return;
    setBusy(true);
    startTransition(async () => {
      const r = await deleteWhitelistAction(item.id);
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
      title="Remover"
    >
      {busy ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Trash2 className="h-3.5 w-3.5" />
      )}
    </Button>
  );
}

function WhitelistModal({
  item,
  onClose,
}: {
  item: WhitelistNumero | null;
  onClose: (refreshed: boolean) => void;
}) {
  const isEdit = item !== null;
  const [telefone, setTelefone] = useState(item?.telefone ?? "");
  const [nome, setNome] = useState(item?.nome ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = telefone.trim();
    if (!isEdit && !t) return setError("Informe o telefone.");
    setBusy(true);
    setError(null);
    startTransition(async () => {
      const r = isEdit
        ? await updateWhitelistAction(item!.id, { nome: nome.trim() || null })
        : await createWhitelistAction({ telefone: t, nome: nome.trim() || null });
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
            {isEdit ? "Editar número" : "Novo número na whitelist"}
          </h2>
        </div>
        <form onSubmit={submit} className="space-y-4 p-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Telefone {!isEdit && <span className="text-destructive">*</span>}
            </label>
            <input
              type="tel"
              autoFocus={!isEdit}
              maxLength={32}
              value={telefone}
              disabled={isEdit}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="+5511999999999"
              className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary disabled:opacity-60"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {isEdit
                ? "O telefone não é editável — remova e cadastre de novo se errou o número."
                : "Informe com DDI e DDD, ex.: +5511999999999."}
            </p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Nome / apelido
            </label>
            <input
              type="text"
              maxLength={80}
              autoFocus={isEdit}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex: Mãe, Pai, Esposa"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary"
            />
          </div>
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
              {isEdit ? "Salvar" : "Adicionar"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

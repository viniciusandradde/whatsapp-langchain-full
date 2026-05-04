"use client";

import { useState, useTransition } from "react";
import { CheckCircle2, KeyRound, Trash2, UserPlus, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { EmpresaMembro } from "@/lib/api";

import {
  addMemberAction,
  changeMemberRoleAction,
  generateResetLinkAction,
  removeMemberAction,
  setMemberStatusAction,
} from "./actions";

interface Props {
  empresaId: number;
  members: EmpresaMembro[];
}

const SELECT_CLASS =
  "rounded-md border border-white/10 bg-obsidian-800 px-2 py-1 text-xs " +
  "focus:outline-none focus:ring-2 focus:ring-brand-primary/30";

const INPUT_CLASS =
  "rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-primary/30";

export function MembersList({ empresaId, members }: Props) {
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleAdd(formData: FormData) {
    setError(null);
    startTransition(async () => {
      const result = await addMemberAction(empresaId, formData);
      if (!result.ok) setError(result.error);
      else setShowAdd(false);
    });
  }

  function handleChangeRole(userId: string, newRole: string) {
    setError(null);
    startTransition(async () => {
      const result = await changeMemberRoleAction(empresaId, userId, newRole);
      if (!result.ok) setError(result.error);
    });
  }

  function handleRemove(userId: string) {
    if (!confirm(`Remover ${userId} da empresa?`)) return;
    setError(null);
    startTransition(async () => {
      const result = await removeMemberAction(empresaId, userId);
      if (!result.ok) setError(result.error);
    });
  }

  function handleToggleStatus(userId: string, currentStatus: string | null) {
    const next = currentStatus === "disabled" ? "active" : "disabled";
    const verb = next === "disabled" ? "Desativar" : "Reativar";
    if (!confirm(`${verb} ${userId}?`)) return;
    setError(null);
    startTransition(async () => {
      const result = await setMemberStatusAction(empresaId, userId, next);
      if (!result.ok) setError(result.error);
    });
  }

  async function handleGenerateResetLink(userId: string) {
    if (
      !confirm(
        "Gerar link de reset de senha?\n\nO link será mostrado pra você " +
          "copiar e enviar ao usuário pelo canal que preferir (WhatsApp, etc). " +
          "Expira em 1 hora.",
      )
    )
      return;
    setError(null);
    const result = await generateResetLinkAction(userId);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    // Mostra prompt com o link pra cópia (textarea pra facilitar select all).
    window.prompt("Link de reset (copie e envie ao usuário):", result.link);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {members.length} {members.length === 1 ? "membro" : "membros"}
        </p>
        {!showAdd && (
          <Button onClick={() => setShowAdd(true)} disabled={isPending}>
            <UserPlus className="size-4" />
            Adicionar membro
          </Button>
        )}
      </div>

      {showAdd && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Adicionar membro</CardTitle>
          </CardHeader>
          <CardContent>
            <form action={handleAdd} className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[260px] space-y-1.5">
                <label htmlFor="user_id" className="text-sm font-medium">
                  User ID (Better Auth UUID)
                </label>
                <input
                  id="user_id"
                  name="user_id"
                  required
                  placeholder="36ba74da-e859-442d-94a5-3cc69a29cc39"
                  className={`${INPUT_CLASS} w-full font-mono text-xs`}
                  disabled={isPending}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="role" className="text-sm font-medium">
                  Role
                </label>
                <select
                  id="role"
                  name="role"
                  defaultValue="operator"
                  className={`${SELECT_CLASS} h-9 px-3 text-sm`}
                  disabled={isPending}
                >
                  <option value="admin">admin</option>
                  <option value="operator">operator</option>
                  <option value="viewer">viewer</option>
                </select>
              </div>
              <Button type="submit" disabled={isPending}>
                Adicionar
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowAdd(false)}
                disabled={isPending}
              >
                Cancelar
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
        <table className="w-full text-sm">
          <thead className="bg-white/[0.02] text-left text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Email</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Default</th>
              <th className="px-3 py-2 font-medium">Joined</th>
              <th className="px-3 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const isDisabled = m.status === "disabled";
              return (
                <tr key={m.user_id} className="border-t border-white/[0.06]">
                  <td className="px-3 py-2">
                    <div className="text-sm">{m.email ?? "(sem email)"}</div>
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {m.user_id}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      defaultValue={m.role}
                      onChange={(e) =>
                        handleChangeRole(m.user_id, e.target.value)
                      }
                      className={SELECT_CLASS}
                      disabled={isPending || isDisabled}
                    >
                      <option value="admin">admin</option>
                      <option value="operator">operator</option>
                      <option value="viewer">viewer</option>
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    {isDisabled ? (
                      <Badge variant="destructive">desativado</Badge>
                    ) : (
                      <Badge variant="outline">ativo</Badge>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {m.is_default && <Badge variant="outline">default</Badge>}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {new Date(m.joined_at).toISOString().slice(0, 10)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        title={isDisabled ? "Reativar" : "Desativar"}
                        onClick={() =>
                          handleToggleStatus(m.user_id, m.status ?? null)
                        }
                        disabled={isPending}
                      >
                        {isDisabled ? (
                          <CheckCircle2 className="size-3.5" />
                        ) : (
                          <XCircle className="size-3.5" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Gerar link de reset de senha"
                        onClick={() => handleGenerateResetLink(m.user_id)}
                        disabled={isPending}
                      >
                        <KeyRound className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Remover membro"
                        onClick={() => handleRemove(m.user_id)}
                        disabled={isPending}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

"use client";

import { useState, useTransition } from "react";
import { ShieldCheck, Plus, Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PerfilAcesso, PermissaoCatalogo } from "@/lib/api";

import { PerfilEditor } from "./perfil-editor";
import { deletePerfilAction } from "./actions";
import { plural } from "@/lib/formato";

interface Props {
  perfis: PerfilAcesso[];
  catalogo: PermissaoCatalogo[];
}

type EditingState =
  | { kind: "closed" }
  | { kind: "new" }
  | { kind: "edit"; perfilId: number };

export function PerfisList({ perfis, catalogo }: Props) {
  const [editing, setEditing] = useState<EditingState>({ kind: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleDelete(p: PerfilAcesso) {
    if (p.is_system) {
      setError("Perfil do sistema não pode ser excluído.");
      return;
    }
    if (
      !confirm(
        `Excluir o perfil "${p.nome}"? ${plural(p.users_count, "usuário")} perde essas permissões.`
      )
    )
      return;
    setError(null);
    startTransition(async () => {
      const r = await deletePerfilAction(p.id);
      if (!r.ok) setError(r.error);
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {plural(perfis.length, "perfil", "perfis")} ·{" "}
          {perfis.filter((p) => p.is_system).length} do sistema ·{" "}
          {plural(perfis.filter((p) => !p.is_system).length, "personalizado")}
        </p>
        <Button onClick={() => setEditing({ kind: "new" })} disabled={isPending}>
          <Plus className="size-4" />
          Novo perfil
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {perfis.map((p) => (
          <Card key={p.id}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="size-4 text-brand-primary" />
                  <CardTitle className="text-base">{p.nome}</CardTitle>
                  {p.is_system && (
                    <Badge variant="outline" className="text-[10px]">
                      do sistema
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setEditing({ kind: "edit", perfilId: p.id })}
                    title={p.is_system ? "Visualizar — perfil do sistema não é editável" : "Editar perfil"}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  {!p.is_system && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(p)}
                      disabled={isPending}
                      title="Deletar"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {p.descricao && (
                <p className="text-sm text-muted-foreground">{p.descricao}</p>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                {plural(p.perms_count, "permissão", "permissões")} ·{" "}
                {plural(p.users_count, "usuário")}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {editing.kind !== "closed" && (
        <PerfilEditor
          mode={editing.kind}
          perfilId={editing.kind === "edit" ? editing.perfilId : undefined}
          catalogo={catalogo}
          onClose={() => setEditing({ kind: "closed" })}
        />
      )}
    </div>
  );
}

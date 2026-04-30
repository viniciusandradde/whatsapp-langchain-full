"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus, Pencil, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Empresa } from "@/lib/api";

import { EmpresaForm } from "./empresa-form";

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
        <EmpresaForm initial={editing} onDone={() => setEditing(null)} />
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
                  <Row label="Status" value={e.status} />
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

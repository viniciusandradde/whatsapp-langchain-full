"use client";

import { useEffect, useState } from "react";
import { UsersRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { GrupoCapturado } from "@/lib/api";

import { listGruposAction } from "../actions";

export function GruposClient() {
  const [grupos, setGrupos] = useState<GrupoCapturado[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const r = await listGruposAction();
      if (r.ok) setGrupos(r.data);
      else setErro(r.error);
    })();
  }, []);

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center gap-2">
        <UsersRound className="h-5 w-5" />
        <h1 className="text-xl font-semibold">Grupos capturados</h1>
      </div>

      {erro && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{erro}</div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{grupos.length} grupo(s)</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Participantes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {grupos.map((g) => (
                <TableRow key={g.id}>
                  <TableCell>{g.nome || g.wa_group_id}</TableCell>
                  <TableCell>
                    <Badge>{g.tipo}</Badge>
                  </TableCell>
                  <TableCell>{g.participantes_count}</TableCell>
                </TableRow>
              ))}
              {grupos.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={3}
                    className="text-center text-sm text-muted-foreground"
                  >
                    Nenhum grupo capturado.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

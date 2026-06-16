"use client";

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

export function GruposClient({ initial }: { initial: GrupoCapturado[] }) {
  const grupos = initial;

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center gap-2">
        <UsersRound className="h-5 w-5" />
        <h1 className="text-xl font-semibold">Grupos capturados</h1>
      </div>

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

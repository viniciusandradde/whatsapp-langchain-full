"use client";

import { useEffect, useState, useTransition } from "react";
import { UserPlus, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ContatoCapturado } from "@/lib/api";

import { listContatosAction, promoverContatosAction } from "../actions";

export function ContatosClient() {
  const [contatos, setContatos] = useState<ContatoCapturado[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();

  async function carregar() {
    const r = await listContatosAction();
    if (r.ok) setContatos(r.data);
    else setErro(r.error);
  }

  useEffect(() => {
    void carregar();
  }, []);

  function toggle(id: number) {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function promover() {
    setErro(null);
    setMsg(null);
    start(async () => {
      const r = await promoverContatosAction([...sel]);
      if (!r.ok) {
        setErro(r.error);
        return;
      }
      setMsg(`${r.data} contato(s) promovido(s) para o CRM.`);
      setSel(new Set());
      await carregar();
    });
  }

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center gap-2">
        <Users className="h-5 w-5" />
        <h1 className="text-xl font-semibold">Contatos capturados</h1>
      </div>

      {erro && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{erro}</div>
      )}
      {msg && (
        <div className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
          {msg}
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            {contatos.length} contato(s) · {sel.size} selecionado(s)
          </CardTitle>
          <Button
            size="sm"
            disabled={pending || sel.size === 0}
            onClick={promover}
          >
            <UserPlus className="mr-1 h-4 w-4" /> Promover p/ CRM
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead></TableHead>
                <TableHead>Nome</TableHead>
                <TableHead>Telefone</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contatos.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      checked={sel.has(c.id)}
                      disabled={!c.telefone || !!c.promovido_at}
                      onChange={() => toggle(c.id)}
                    />
                  </TableCell>
                  <TableCell>{c.push_name || "—"}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {c.telefone || (
                      <span className="text-muted-foreground">só-LID</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {c.is_business ? (
                      <Badge>business</Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {c.promovido_at ? (
                      <Badge>no CRM</Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">staging</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {contatos.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center text-sm text-muted-foreground"
                  >
                    Nenhum contato capturado. Use a extensão ou capture via
                    Evolution.
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

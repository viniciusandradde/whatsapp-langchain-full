"use client";

import { useState, useTransition } from "react";
import { Copy, KeyRound, Plus, Trash2 } from "lucide-react";

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
import type { DisparadorApiKey } from "@/lib/api";

import {
  createApiKeyAction,
  listApiKeysAction,
  revokeApiKeyAction,
} from "../actions";

const SCOPES = ["capture", "dispatch", "templates"] as const;

export function ApiKeysClient({ initial }: { initial: DisparadorApiKey[] }) {
  const [keys, setKeys] = useState<DisparadorApiKey[]>(initial);
  const [erro, setErro] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [scopes, setScopes] = useState<string[]>(["capture"]);
  const [novaChave, setNovaChave] = useState<string | null>(null);
  const [pending, start] = useTransition();

  async function carregar() {
    const r = await listApiKeysAction();
    if (r.ok) setKeys(r.data);
    else setErro(r.error);
  }

  function criar() {
    setErro(null);
    start(async () => {
      const r = await createApiKeyAction(label.trim(), scopes);
      if (!r.ok) {
        setErro(r.error);
        return;
      }
      setNovaChave(r.data.key);
      setLabel("");
      await carregar();
    });
  }

  function revogar(id: number) {
    start(async () => {
      const r = await revokeApiKeyAction(id);
      if (!r.ok) setErro(r.error);
      else await carregar();
    });
  }

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center gap-2">
        <KeyRound className="h-5 w-5" />
        <h1 className="text-xl font-semibold">API keys do Disparador</h1>
      </div>

      {erro && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{erro}</div>
      )}

      {novaChave && (
        <div className="rounded-md border border-emerald-300 bg-emerald-50 p-4 text-sm">
          <p className="font-medium text-emerald-800">
            Copie agora — esta chave NÃO será exibida novamente:
          </p>
          <div className="mt-2 flex items-center gap-2">
            {/* Caixa emerald-50 é fixa (clara nos 3 temas) → texto escuro fixo */}
            <code className="flex-1 break-all rounded bg-white px-2 py-1 font-mono text-slate-900">
              {novaChave}
            </code>
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigator.clipboard?.writeText(novaChave)}
            >
              <Copy className="h-4 w-4" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setNovaChave(null)}>
              OK
            </Button>
          </div>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nova chave</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            placeholder="Nome descritivo (ex: Extensão Chrome - João)"
            value={label}
            maxLength={100}
            onChange={(e) => setLabel(e.target.value)}
          />
          <div className="flex flex-wrap gap-3 text-sm">
            {SCOPES.map((s) => (
              <label key={s} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={scopes.includes(s)}
                  onChange={(e) =>
                    setScopes((prev) =>
                      e.target.checked
                        ? [...prev, s]
                        : prev.filter((x) => x !== s)
                    )
                  }
                />
                {s}
              </label>
            ))}
          </div>
          <Button onClick={criar} disabled={pending || !label.trim()}>
            <Plus className="mr-1 h-4 w-4" /> Criar chave
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chaves</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Prefixo</TableHead>
                <TableHead>Escopos</TableHead>
                <TableHead>Status</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>{k.label}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {k.key_prefix}…
                  </TableCell>
                  <TableCell>{(k.scopes || []).join(", ")}</TableCell>
                  <TableCell>
                    {k.revoked_at ? (
                      <Badge variant="destructive">revogada</Badge>
                    ) : (
                      <Badge>ativa</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {!k.revoked_at && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={pending}
                        onClick={() => revogar(k.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {keys.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                    Nenhuma chave ainda.
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

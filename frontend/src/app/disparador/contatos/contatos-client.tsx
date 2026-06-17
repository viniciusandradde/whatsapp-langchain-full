"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { DownloadCloud, Megaphone, UserPlus, Users } from "lucide-react";

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
import type { Conexao, ContatoCapturado } from "@/lib/api";

import {
  capturarViaEvolutionAction,
  getCapturaLoteAction,
  listContatosAction,
  promoverContatosAction,
} from "../actions";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function ContatosClient({
  initial,
  evolution,
}: {
  initial: ContatoCapturado[];
  evolution: Conexao[];
}) {
  const [contatos, setContatos] = useState<ContatoCapturado[]>(initial);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [conexaoId, setConexaoId] = useState<number | "">(
    evolution[0]?.id ?? ""
  );
  const [capturando, setCapturando] = useState<string | null>(null);
  const router = useRouter();

  function criarCampanha() {
    const telefones = contatos
      .filter((c) => sel.has(c.id) && c.telefone)
      .map((c) => c.telefone as string);
    if (telefones.length === 0) {
      setErro("Selecione contatos com telefone para criar a campanha.");
      return;
    }
    try {
      sessionStorage.setItem("campanha_telefones", telefones.join("\n"));
    } catch {
      /* ignora */
    }
    router.push("/campanhas");
  }

  async function carregar() {
    const r = await listContatosAction();
    if (r.ok) setContatos(r.data);
    else setErro(r.error);
  }

  function toggle(id: number) {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Contatos selecionáveis (com telefone e ainda não promovidos).
  const selecionaveis = contatos.filter((c) => c.telefone && !c.promovido_at);
  const todosSelecionados =
    selecionaveis.length > 0 && selecionaveis.every((c) => sel.has(c.id));

  function toggleTodos() {
    setSel(
      todosSelecionados
        ? new Set<number>()
        : new Set(selecionaveis.map((c) => c.id))
    );
  }

  function promover() {
    setErro(null);
    setMsg(null);
    start(async () => {
      const r = await promoverContatosAction([...sel]);
      if (!r.ok) return setErro(r.error);
      setMsg(`${r.data} contato(s) promovido(s) para o CRM.`);
      setSel(new Set());
      await carregar();
    });
  }

  async function capturar(tipo: "contatos" | "grupos") {
    setErro(null);
    setMsg(null);
    if (conexaoId === "") return setErro("Selecione uma conexão Evolution.");
    setCapturando(`Iniciando captura de ${tipo}…`);
    const r = await capturarViaEvolutionAction(Number(conexaoId), tipo);
    if (!r.ok) {
      setCapturando(null);
      return setErro(r.error);
    }
    // polling do lote (captura roda em background no servidor)
    const loteId = r.data.lote_id;
    for (let i = 0; i < 40; i++) {
      await sleep(2000);
      const lr = await getCapturaLoteAction(loteId);
      if (!lr.ok) continue;
      const l = lr.data;
      setCapturando(
        `Capturando ${tipo}… ${l.total_novos} novos / ${l.total_recebidos} recebidos (${l.status})`
      );
      if (l.status === "concluido" || l.status === "parcial" || l.status === "erro") {
        setCapturando(null);
        if (l.status === "erro") setErro(l.erro || "Falha na captura.");
        else
          setMsg(
            `✅ Captura de ${tipo}: ${l.total_novos} novos, ${l.total_atualizados} atualizados.`
          );
        await carregar();
        return;
      }
    }
    setCapturando(null);
    setMsg("Captura ainda processando — recarregue em instantes.");
    await carregar();
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

      {/* Captura server-side via Evolution (robusta, sem extensão) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Capturar via Evolution</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {evolution.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma conexão Evolution ativa. Conecte uma em{" "}
              <strong>Conexões</strong> para capturar pelo servidor.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className="rounded-md border px-3 py-2 text-sm"
                  value={conexaoId}
                  onChange={(e) =>
                    setConexaoId(e.target.value ? Number(e.target.value) : "")
                  }
                >
                  {evolution.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name || c.from_number || `Evolution #${c.id}`}
                    </option>
                  ))}
                </select>
                <Button
                  size="sm"
                  disabled={!!capturando}
                  onClick={() => capturar("contatos")}
                >
                  <DownloadCloud className="mr-1 h-4 w-4" /> Capturar contatos
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!!capturando}
                  onClick={() => capturar("grupos")}
                >
                  <DownloadCloud className="mr-1 h-4 w-4" /> Capturar grupos
                </Button>
              </div>
              {capturando && (
                <p className="text-sm text-muted-foreground">{capturando}</p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            {contatos.length} contato(s) · {sel.size} selecionado(s)
          </CardTitle>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={sel.size === 0}
              onClick={criarCampanha}
            >
              <Megaphone className="mr-1 h-4 w-4" /> Criar campanha
            </Button>
            <Button size="sm" disabled={pending || sel.size === 0} onClick={promover}>
              <UserPlus className="mr-1 h-4 w-4" /> Promover p/ CRM
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <input
                    type="checkbox"
                    aria-label="Selecionar todos"
                    checked={todosSelecionados}
                    disabled={selecionaveis.length === 0}
                    onChange={toggleTodos}
                  />
                </TableHead>
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
                    Nenhum contato capturado ainda. Use “Capturar via Evolution”
                    acima.
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

"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  ChevronLeft,
  ChevronRight,
  DownloadCloud,
  Megaphone,
  Search,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import { plural } from "@/lib/formato";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  despromoverContatosAction,
  getCapturaLoteAction,
  listContatosAction,
  promoverContatosAction,
  promoverTodosContatosAction,
} from "../actions";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * 200 por página, não 1.000.
 *
 * O botão "Carregar mais" refazia a busca com `limit` crescente e mantinha
 * tudo no DOM: pra chegar no contato 19.000 eram 19 cliques e 19 mil linhas
 * renderizadas. Paginar por `offset` mantém o DOM constante.
 */
const PAGINA = 200;

export function ContatosClient({
  initial,
  total: totalInicial,
  promoviveis: promoviveisInicial,
  evolution,
}: {
  initial: ContatoCapturado[];
  total: number;
  promoviveis: number;
  evolution: Conexao[];
}) {
  const [contatos, setContatos] = useState<ContatoCapturado[]>(
    initial
  );
  const [pagina, setPagina] = useState(0);
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [confirmandoPromoverTodos, setConfirmandoPromoverTodos] =
    useState(false);
  const [total, setTotal] = useState(totalInicial);
  const [promoviveis, setPromoviveis] = useState(promoviveisInicial);
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

  async function carregar(p = pagina, termo = busca) {
    const r = await listContatosAction({
      limit: PAGINA,
      offset: p * PAGINA,
      q: termo,
    });
    if (r.ok) {
      setContatos(r.data.items);
      setTotal(r.data.total);
      setPromoviveis(r.data.promoviveis);
    } else setErro(r.error);
  }

  function toggle(id: number) {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Selecionáveis = qualquer um com telefone (promovido ou não). Os botões
  // filtram por estado: Promover age nos não-promovidos, Remover nos promovidos.
  const selecionaveis = contatos.filter((c) => c.telefone);
  const todosSelecionados =
    selecionaveis.length > 0 && selecionaveis.every((c) => sel.has(c.id));
  // Quantos dos selecionados já estão no CRM (pra habilitar "Remover do CRM").
  const selPromovidos = contatos.filter(
    (c) => sel.has(c.id) && c.promovido_at
  ).length;

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
      setMsg(`${plural(r.data, "contato")} promovido${r.data === 1 ? "" : "s"} para o CRM.`);
      setSel(new Set());
      await carregar();
    });
  }

  // Promove TODOS os capturados com telefone (server-side) — não depende da
  // lista visível, que antes capava em 200.
  // Sem confirmação nenhuma, isto promovia 8.596 registros num clique.
  function promoverTodos() {
    setErro(null);
    setMsg(null);
    start(async () => {
      const r = await promoverTodosContatosAction();
      if (!r.ok) return setErro(r.error);
      setMsg(`${plural(r.data, "contato")} no CRM.`);
      setSel(new Set());
      await carregar();
    });
  }

  // Busca é server-side: filtrar só a página carregada acharia 1 em cada 99
  // numa base de 20 mil.
  function buscar(termo = busca) {
    setPagina(0);
    setBuscaAplicada(termo.trim());
    start(async () => {
      await carregar(0, termo);
    });
  }

  async function irParaPagina(p: number) {
    setErro(null);
    setSel(new Set());
    setPagina(p);
    const r = await listContatosAction({
      limit: PAGINA,
      offset: p * PAGINA,
      q: buscaAplicada,
    });
    if (r.ok) {
      setContatos(r.data.items);
      setTotal(r.data.total);
      setPromoviveis(r.data.promoviveis);
    } else setErro(r.error);
  }

  function removerDoCrm() {
    setErro(null);
    setMsg(null);
    start(async () => {
      const r = await despromoverContatosAction([...sel]);
      if (!r.ok) return setErro(r.error);
      const { removidos, mantidos_com_atendimento } = r.data;
      let m = `${plural(removidos, "contato")} removido${removidos === 1 ? "" : "s"} do CRM.`;
      if (mantidos_com_atendimento > 0) {
        m += ` ${plural(mantidos_com_atendimento, "contato")} mantido${mantidos_com_atendimento === 1 ? "" : "s"} por já ter atendimento — o histórico é preservado.`;
      }
      setMsg(m);
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
          <CardTitle className="text-base font-normal">
            <span className="font-medium">{plural(total, "contato")}</span>
            {sel.size > 0 && ` · ${sel.size} selecionado${sel.size === 1 ? "" : "s"}`}
            {promoviveis > 0 &&
              ` · ${promoviveis.toLocaleString("pt-BR")} fora do CRM`}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            {total > PAGINA && (
              <div className="flex items-center gap-1 text-sm">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={pending || pagina === 0}
                  onClick={() => irParaPagina(pagina - 1)}
                  aria-label="Página anterior"
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <span className="min-w-24 text-center text-muted-foreground">
                  {pagina + 1} de {Math.ceil(total / PAGINA)}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={pending || (pagina + 1) * PAGINA >= total}
                  onClick={() => irParaPagina(pagina + 1)}
                  aria-label="Próxima página"
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            )}
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
            {promoviveis > 0 && (
              <Button
                size="sm"
                variant="default"
                disabled={pending}
                onClick={() => setConfirmandoPromoverTodos(true)}
                title="Promove todos os contatos com telefone, inclusive os que não estão nesta página"
              >
                <UserPlus className="mr-1 h-4 w-4" /> Promover todos ({promoviveis})
              </Button>
            )}
            {selPromovidos > 0 && (
              <Button
                size="sm"
                variant="destructive"
                disabled={pending}
                onClick={removerDoCrm}
              >
                <UserMinus className="mr-1 h-4 w-4" /> Remover do CRM (
                {selPromovidos})
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <form
              className="flex w-full max-w-md items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                buscar();
              }}
            >
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="Buscar por nome ou telefone"
                  className="pl-8"
                  aria-label="Buscar contato por nome ou telefone"
                />
              </div>
              {/* Botão explícito: Enter sozinho é atalho invisível — quem não
                  souber que existe fica achando que a busca não funciona. */}
              <Button type="submit" variant="outline" size="sm" disabled={pending}>
                Buscar
              </Button>
              {buscaAplicada && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={pending}
                  onClick={() => {
                    setBusca("");
                    buscar("");
                  }}
                >
                  Limpar
                </Button>
              )}
            </form>
          </div>
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
                      disabled={!c.telefone}
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
                      <Badge variant="success">No CRM</Badge>
                    ) : (
                      <Badge variant="outline">Só capturado</Badge>
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

      {/* Ação em massa acima de 50 registros exige digitar o total (contrato
          C4): quem clicou sem ler não consegue confirmar por acidente. */}
      <ConfirmDestrutivo
        aberto={confirmandoPromoverTodos}
        onAbertoChange={setConfirmandoPromoverTodos}
        titulo="Promover todos os contatos para o CRM"
        objeto={`${plural(promoviveis, "contato")} que ainda não está${promoviveis === 1 ? "" : "ão"} no CRM`}
        descricao="Vale para todos os contatos capturados com telefone — inclusive os que não aparecem nesta página."
        rotuloAcao="Promover todos"
        exigeDigitar={promoviveis > 50 ? String(promoviveis) : undefined}
        onConfirmar={promoverTodos}
      />
    </div>
  );
}

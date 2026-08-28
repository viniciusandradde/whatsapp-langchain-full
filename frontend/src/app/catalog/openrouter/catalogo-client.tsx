"use client";

import { useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { ArrowUpDown, CheckCircle2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  IaAlerta,
  OpenRouterEvento,
  OpenRouterModelo,
  OpenRouterProvedor,
  OpenRouterStatus,
  RankingModelo,
  SaudeFuncao,
  SaudeModelo,
} from "@/lib/api";

import { EventosFeed } from "./eventos-feed";
import { VisaoGeral } from "./visao-geral";

import { promoverAction, sincronizarAction, statusAction } from "./actions";

/** USD por token (formato OpenRouter) → "US$ X,XX /Mtok" legível. */
function precoMtok(porToken: string | null | undefined): string {
  const v = Number(porToken);
  if (!porToken || !Number.isFinite(v) || v === 0) return "—";
  return `$${(v * 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}`;
}

function contexto(n: number | null): string {
  if (!n) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toLocaleString("pt-BR")}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

function quando(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  return h < 48 ? `há ${h} h` : `há ${Math.round(h / 24)} dias`;
}

type SortKey = "slug" | "intel" | "preco" | "contexto";

export function CatalogoClient({
  status,
  modelosIniciais,
  provedores,
  saude,
  rankings,
  alertas,
  eventos,
}: {
  status: OpenRouterStatus | null;
  modelosIniciais: OpenRouterModelo[];
  provedores: OpenRouterProvedor[];
  saude: { funcoes: SaudeFuncao[]; saude: Record<string, SaudeModelo> } | null;
  rankings: { ultimo_dia: string | null; items: RankingModelo[] } | null;
  alertas: { ativos: IaAlerta[]; resolvidos: IaAlerta[] } | null;
  eventos: OpenRouterEvento[];
}) {
  const [st, setSt] = useState(status);
  const [modelos, setModelos] = useState(modelosIniciais);
  const [busca, setBusca] = useState("");
  const [modalidade, setModalidade] = useState<string>("");
  const [sort, setSort] = useState<SortKey>("intel");
  const [sincronizando, startSync] = useTransition();
  const [promovendo, setPromovendo] = useState<string | null>(null);

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    let lista = modelos;
    if (q) {
      lista = lista.filter(
        (m) =>
          m.slug.toLowerCase().includes(q) || m.nome.toLowerCase().includes(q)
      );
    }
    if (modalidade) {
      lista = lista.filter((m) => m.input_modalities.includes(modalidade));
    }
    const intel = (m: OpenRouterModelo) =>
      m.benchmarks?.artificial_analysis?.intelligence_index ?? -1;
    const preco = (m: OpenRouterModelo) => Number(m.pricing?.prompt) || 0;
    return [...lista].sort((a, b) => {
      if (sort === "slug") return a.slug.localeCompare(b.slug);
      if (sort === "preco") return preco(a) - preco(b);
      if (sort === "contexto")
        return (b.context_length ?? 0) - (a.context_length ?? 0);
      return intel(b) - intel(a);
    });
  }, [modelos, busca, modalidade, sort]);

  function sincronizar() {
    startSync(async () => {
      const r = await sincronizarAction();
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      toast.success("Sincronização iniciada — leva ~10 segundos.");
      // O sync é 202/background: consulta o status até o carimbo mudar.
      const antes = st?.catalogo_sync_at ?? null;
      for (let i = 0; i < 10; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const s = await statusAction();
        if (s.ok && s.data.catalogo_sync_at !== antes) {
          setSt(s.data);
          toast.success(
            `Catálogo atualizado: ${s.data.total_modelos} modelos, ${s.data.total_provedores} provedores. Recarregue para ver a lista nova.`
          );
          return;
        }
      }
      toast.warning("O sync ainda não terminou — confira o carimbo em instantes.");
    });
  }

  async function promover(m: OpenRouterModelo) {
    setPromovendo(m.slug);
    try {
      // Modalidade de entrada decide o tipo no curado: quem lê imagem é
      // cadastrado como mídia (serve visão/OCR); o resto entra como chat.
      const tipo = m.input_modalities.includes("image") ? "midia" : "chat";
      const r = await promoverAction(m.slug, tipo);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      setModelos((atual) =>
        atual.map((x) => (x.slug === m.slug ? { ...x, promovido: true } : x))
      );
      toast.success(`${m.slug} promovido ao catálogo curado com preços.`);
    } finally {
      setPromovendo(null);
    }
  }

  const MODALIDADES = ["text", "image", "audio", "file"] as const;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Catálogo sincronizado {quando(st?.catalogo_sync_at)}
          {st?.total_modelos
            ? ` · ${st.total_modelos} modelos · ${st.total_provedores} provedores`
            : ""}
          {st?.erro ? (
            <span className="text-destructive"> · último erro: {st.erro}</span>
          ) : null}
        </p>
        <Button onClick={sincronizar} disabled={sincronizando} size="sm">
          <RefreshCw
            className={sincronizando ? "size-4 animate-spin" : "size-4"}
          />
          Sincronizar agora
        </Button>
      </div>

      <Tabs defaultValue={saude ? "visao" : "modelos"}>
        <TabsList>
          {saude ? <TabsTrigger value="visao">Visão geral</TabsTrigger> : null}
          <TabsTrigger value="novidades">
            Novidades{eventos.length > 0 ? ` (${eventos.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="modelos">
            Modelos ({modelos.length})
          </TabsTrigger>
          <TabsTrigger value="provedores">
            Provedores ({provedores.length})
          </TabsTrigger>
        </TabsList>

        {saude ? (
          <TabsContent value="visao">
            <VisaoGeral
              funcoes={saude.funcoes}
              saude={saude.saude}
              modelos={modelos}
              rankings={rankings}
              alertas={alertas}
            />
          </TabsContent>
        ) : null}

        <TabsContent value="novidades">
          <Card>
            <CardContent className="pt-4">
              <EventosFeed eventos={eventos} />
              <p className="mt-3 text-xs text-muted-foreground">
                Gerado por diff entre sincronizações do catálogo e dos
                rankings — o OpenRouter não publica notícias por API oficial.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="modelos" className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              placeholder="Buscar por slug ou nome…"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="max-w-xs"
            />
            <div className="flex gap-1">
              {MODALIDADES.map((mod) => (
                <Button
                  key={mod}
                  size="sm"
                  variant={modalidade === mod ? "default" : "outline"}
                  onClick={() => setModalidade(modalidade === mod ? "" : mod)}
                >
                  {mod === "text"
                    ? "Texto"
                    : mod === "image"
                      ? "Imagem"
                      : mod === "audio"
                        ? "Áudio"
                        : "Arquivos"}
                </Button>
              ))}
            </div>
          </div>

          {visiveis.length === 0 ? (
            <EmptyState
              title="Nenhum modelo"
              description={
                modelos.length === 0
                  ? "Clique em Sincronizar agora para trazer o catálogo do OpenRouter."
                  : "Nenhum modelo casa com o filtro."
              }
            />
          ) : (
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>
                          <button
                            className="inline-flex items-center gap-1"
                            onClick={() => setSort("slug")}
                          >
                            Modelo <ArrowUpDown className="size-3" />
                          </button>
                        </TableHead>
                        <TableHead>Modalidades</TableHead>
                        <TableHead>
                          <button
                            className="inline-flex items-center gap-1"
                            onClick={() => setSort("intel")}
                          >
                            Benchmark <ArrowUpDown className="size-3" />
                          </button>
                        </TableHead>
                        <TableHead>
                          <button
                            className="inline-flex items-center gap-1"
                            onClick={() => setSort("preco")}
                          >
                            Entrada /Mtok <ArrowUpDown className="size-3" />
                          </button>
                        </TableHead>
                        <TableHead>Saída /Mtok</TableHead>
                        <TableHead>
                          <button
                            className="inline-flex items-center gap-1"
                            onClick={() => setSort("contexto")}
                          >
                            Contexto <ArrowUpDown className="size-3" />
                          </button>
                        </TableHead>
                        <TableHead className="text-right">Curado</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visiveis.slice(0, 200).map((m) => {
                        const aa = m.benchmarks?.artificial_analysis;
                        return (
                          <TableRow key={m.slug}>
                            <TableCell>
                              <Link
                                href={`/catalog/openrouter/modelo/${m.slug}`}
                                className="font-medium underline-offset-2 hover:underline"
                              >
                                {m.slug}
                              </Link>
                              <div className="text-xs text-muted-foreground">
                                {m.nome}
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                {m.input_modalities.map((mod) => (
                                  <Badge key={mod} variant="outline">
                                    {mod}
                                  </Badge>
                                ))}
                              </div>
                            </TableCell>
                            <TableCell>
                              {aa?.intelligence_index != null ? (
                                <Badge variant="secondary">
                                  {Math.round(aa.intelligence_index)}
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </TableCell>
                            <TableCell>{precoMtok(m.pricing?.prompt)}</TableCell>
                            <TableCell>
                              {precoMtok(m.pricing?.completion)}
                            </TableCell>
                            <TableCell>{contexto(m.context_length)}</TableCell>
                            <TableCell className="text-right">
                              {m.promovido ? (
                                <Badge variant="success">
                                  <CheckCircle2 className="size-3" /> no curado
                                </Badge>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={promovendo === m.slug}
                                  onClick={() => promover(m)}
                                >
                                  Promover
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
                {visiveis.length > 200 ? (
                  <p className="p-3 text-xs text-muted-foreground">
                    Mostrando 200 de {visiveis.length} — refine a busca.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="provedores">
          {provedores.length === 0 ? (
            <EmptyState
              title="Nenhum provedor"
              description="Clique em Sincronizar agora para trazer o catálogo do OpenRouter."
            />
          ) : (
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Provedor</TableHead>
                        <TableHead>Sede</TableHead>
                        <TableHead>Datacenters</TableHead>
                        <TableHead>Políticas</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {provedores.map((p) => (
                        <TableRow key={p.slug}>
                          <TableCell>
                            <div className="font-medium">{p.nome}</div>
                            <div className="text-xs text-muted-foreground">
                              {p.slug}
                            </div>
                          </TableCell>
                          <TableCell>{p.hq || "—"}</TableCell>
                          <TableCell>
                            {Array.isArray(p.datacenters) &&
                            p.datacenters.length > 0
                              ? p.datacenters.join(", ")
                              : "—"}
                          </TableCell>
                          <TableCell>
                            <div className="flex gap-2 text-xs">
                              {p.privacy_policy_url ? (
                                <a
                                  href={p.privacy_policy_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="underline"
                                >
                                  privacidade
                                </a>
                              ) : null}
                              {p.status_page_url ? (
                                <a
                                  href={p.status_page_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="underline"
                                >
                                  status
                                </a>
                              ) : null}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

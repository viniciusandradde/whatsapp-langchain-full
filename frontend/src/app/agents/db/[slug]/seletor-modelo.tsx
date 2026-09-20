"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowDown,
  ArrowUp,
  BadgeDollarSign,
  Brain,
  Code,
  Eye,
  FilterX,
  Lock,
  Search,
  TrendingUp,
} from "lucide-react";

import { ApiError } from "@/components/ui/api-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  AgenteIA,
  ModeloCatalogo,
  ModeloLLM,
  PlanoCatalogo,
  TierContexto,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { carregarCatalogoModelosAction } from "./actions";
import {
  ORDEM,
  TIER_PADRAO,
  TIERS,
  cabeNoModelo,
  creditosPorMensagem,
  formatarChars,
  modeloBloqueado,
  rotuloPlano,
  rotuloTier,
  tierBloqueado,
  usdPorMensagem,
} from "./creditos";
import { LogoProvedor } from "./logos-provedor";

/**
 * Seletor de modelos do agente (ADR-004) — "Modelos Disponíveis".
 *
 * Lista o catálogo COMPLETO do OpenRouter em cards com o custo estimado em
 * créditos por tamanho de contexto, filtros por capacidade, abas por
 * fabricante e a seção "Tamanho do Contexto" (Lite → Extended) que o worker
 * honra de verdade (`agente_ia.contexto_tamanho`).
 *
 * Contrato com o form do editor: três hidden inputs (`modelo_provedor`,
 * `modelo_nome`, `contexto_tamanho`) — os names não podem repetir no
 * restante da aba. Busca, filtros, ordenação e aba de provedor são estado
 * local (D7); só o que vai no form é persistido.
 *
 * Catálogo indisponível → `SeletorCurado` (os dois selects do curado de
 * sempre), para a aba nunca ficar sem jeito de escolher modelo.
 *
 * Gate por plano (mig 188): o catálogo traz `plano` (tier máximo e se
 * libera modelos premium). Tier e modelo acima do plano ficam travados na
 * tela (toast ao tocar) — o PUT devolveria 402 de qualquer jeito. Agente
 * salvo acima do plano (downgrade) é mostrado rebaixado, que é o que o
 * worker aplica.
 */

type Ordem = "relevancia" | "nome" | "preco" | "contexto" | "novos";

interface Filtros {
  promo: boolean;
  visao: boolean;
  pensamento: boolean;
  tools: boolean;
}

const FILTROS_VAZIOS: Filtros = { promo: false, visao: false, pensamento: false, tools: false };

const ORDEM_ROTULO: Record<Ordem, string> = {
  relevancia: "Relevância",
  nome: "Nome",
  preco: "Preço",
  contexto: "Contexto",
  novos: "Mais novos",
};

// Ponto colorido de cada tier — o mesmo nos cards, no resumo e na seção.
// Escala de "calor" com tokens ESTÁVEIS: `brand-secondary` é cor de marca
// por empresa (na empresa 1 é branco) e não serve como semântica.
const PONTO_TIER: Record<TierContexto, string> = {
  lite: "bg-success",
  regular: "bg-chart-3",
  medium: "bg-warning",
  large: "bg-brand-primary",
  extended: "bg-destructive",
};

// Cards por leva: 447 cards de uma vez travam o celular; a lista cresce sob
// demanda e o contador diz quantos faltam.
const CARDS_POR_LEVA = 48;

const CHIPS: { chave: keyof Filtros; rotulo: string; Icone: typeof Eye }[] = [
  { chave: "promo", rotulo: "Promoção", Icone: BadgeDollarSign },
  { chave: "visao", rotulo: "Visão", Icone: Eye },
  { chave: "pensamento", rotulo: "Pensamento", Icone: Brain },
  { chave: "tools", rotulo: "HTTP Tools", Icone: Code },
];

/** "Google: Gemini 2.5 Flash" → "Gemini 2.5 Flash" — o fabricante já está na 2ª linha. */
export function nomeCurto(m: Pick<ModeloCatalogo, "nome" | "provedor_nome">): string {
  const i = m.nome.indexOf(":");
  return i > 0 ? m.nome.slice(i + 1).trim() || m.nome : m.nome;
}

function normalizar(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function slugAtualDe(a: AgenteIA): string | null {
  if (a.modelo_provedor && a.modelo_nome) return `${a.modelo_provedor}/${a.modelo_nome}`;
  return a.modelo || null;
}

function comparador(
  ordem: Ordem,
  slugSelecionado: string | null
): (a: ModeloCatalogo, b: ModeloCatalogo) => number {
  const porNome = (a: ModeloCatalogo, b: ModeloCatalogo) =>
    nomeCurto(a).localeCompare(nomeCurto(b), "pt-BR");
  const primeiro = (x: boolean) => (x ? 0 : 1);
  const porPreco = (a: ModeloCatalogo, b: ModeloCatalogo) =>
    (a.preco_prompt ?? Number.POSITIVE_INFINITY) - (b.preco_prompt ?? Number.POSITIVE_INFINITY);
  switch (ordem) {
    case "nome":
      return porNome;
    case "preco":
      return (a, b) => porPreco(a, b) || porNome(a, b);
    case "contexto":
      return (a, b) => (b.context_length ?? -1) - (a.context_length ?? -1) || porNome(a, b);
    case "novos":
      return (a, b) => primeiro(a.novo) - primeiro(b.novo) || porNome(a, b);
    default:
      // O modelo atual do agente vem primeiro: é o que o operador quer ver
      // ao abrir a aba, antes de comparar com o resto.
      return (a, b) =>
        primeiro(a.slug === slugSelecionado) - primeiro(b.slug === slugSelecionado) ||
        primeiro(a.curado) - primeiro(b.curado) ||
        primeiro(a.tendencia) - primeiro(b.tendencia) ||
        primeiro(a.novo) - primeiro(b.novo) ||
        porPreco(a, b) ||
        porNome(a, b);
  }
}

function formatarUsd(v: number): string {
  return `US$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`;
}

export function SeletorModelo({ agente, curados }: { agente: AgenteIA; curados: ModeloLLM[] }) {
  const [slugSelecionado, setSlugSelecionado] = useState<string | null>(slugAtualDe(agente));
  const [tier, setTier] = useState<TierContexto>(agente.contexto_tamanho ?? TIER_PADRAO);

  const catalogo = useQuery({
    queryKey: ["catalogo-modelos"],
    queryFn: async () => {
      const r = await carregarCatalogoModelosAction();
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 10 * 60_000,
  });

  const provedorSel = slugSelecionado?.split("/")[0] ?? "";
  const nomeSel = slugSelecionado?.split("/").slice(1).join("/") ?? "";
  const plano = catalogo.data?.plano ?? null;
  const itens = catalogo.data?.itens;
  const selecionado = itens?.find((m) => m.slug === slugSelecionado) ?? null;

  // Tier acima do plano (agente salvo antes de um downgrade): o que vai no
  // form e o que o resumo mostra é o rebaixado — o mesmo que o worker
  // aplica. Derivação pura, sem efeito.
  const tierEfetivo: TierContexto = plano && tierBloqueado(tier, plano) ? plano.contexto_max : tier;
  const modeloAtualBloqueado = !!(plano && selecionado && modeloBloqueado(selecionado, plano));

  return (
    <div className="space-y-4 md:col-span-2">
      {/* O que o form salva. `readOnly`: o valor vem do estado, não de digitação. */}
      <Input type="hidden" name="modelo_provedor" value={provedorSel} readOnly />
      <Input type="hidden" name="modelo_nome" value={nomeSel} readOnly />
      <Input type="hidden" name="contexto_tamanho" value={tierEfetivo} readOnly />

      {catalogo.isPending ? (
        <SkeletonCatalogo />
      ) : catalogo.isError ? (
        <>
          <ApiError
            error={catalogo.error}
            title="Não deu para carregar o catálogo de modelos"
            variant="inline"
            onRetry={() => void catalogo.refetch()}
          />
          <SeletorCurado
            curados={curados}
            slug={slugSelecionado}
            onChange={setSlugSelecionado}
          />
        </>
      ) : (
        <Catalogo
          itens={catalogo.data.itens}
          plano={catalogo.data.plano}
          slugSelecionado={slugSelecionado}
          onSelecionar={setSlugSelecionado}
          tier={tierEfetivo}
        />
      )}

      {modeloAtualBloqueado && plano && (
        <p
          role="alert"
          className="rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm text-foreground"
        >
          O modelo atual do agente é premium e não está no plano {plano.nome}. Escolha outro
          modelo para salvar
          {plano.upgrade_sugerido
            ? ` — ou faça upgrade para o plano ${rotuloPlano(plano.upgrade_sugerido)}.`
            : "."}
        </p>
      )}

      <TamanhoDoContexto
        tier={tierEfetivo}
        tierSalvo={tier}
        plano={plano}
        onChange={setTier}
        modelo={selecionado}
      />

      {(agente.prompt_override ?? "").length > TIERS[tierEfetivo] && (
        <p
          role="alert"
          className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
        >
          O prompt do agente ({formatarChars((agente.prompt_override ?? "").length)} caracteres)
          excede o número de caracteres suportado neste tamanho de contexto. Reduza o prompt
          ou aumente o Tamanho do Contexto.
        </p>
      )}
    </div>
  );
}

// ---- Catálogo: resumo, busca, chips, ordenação, abas e cards ----------------

function Catalogo({
  itens,
  plano,
  slugSelecionado,
  onSelecionar,
  tier,
}: {
  itens: ModeloCatalogo[];
  plano: PlanoCatalogo;
  slugSelecionado: string | null;
  onSelecionar: (slug: string) => void;
  tier: TierContexto;
}) {
  const [busca, setBusca] = useState("");
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VAZIOS);
  const [ordem, setOrdem] = useState<Ordem>("relevancia");
  const [desc, setDesc] = useState(false);
  const [provedor, setProvedor] = useState<string>("todos");
  // "Mostrar mais" volta ao início quando a lista muda: o limite fica preso
  // à chave dos filtros, sem efeito (o React Compiler reprova setState em
  // efeito e isto é derivação pura).
  const [levas, setLevas] = useState<{ chave: string; n: number }>({ chave: "", n: 1 });

  const selecionado = itens.find((m) => m.slug === slugSelecionado) ?? null;

  // Busca + chips valem para a contagem das abas; a aba só recorta depois.
  const aposBusca = useMemo(() => {
    const q = normalizar(busca.trim());
    return itens.filter((m) => {
      if (filtros.promo && !m.promo) return false;
      if (filtros.visao && !m.visao) return false;
      if (filtros.pensamento && !m.pensamento) return false;
      if (filtros.tools && !m.tools) return false;
      if (!q) return true;
      return (
        normalizar(m.nome).includes(q) ||
        normalizar(m.slug).includes(q) ||
        normalizar(m.provedor_nome).includes(q)
      );
    });
  }, [itens, busca, filtros]);

  const abas = useMemo(() => {
    const contagem = new Map<string, { nome: string; n: number }>();
    for (const m of aposBusca) {
      const atual = contagem.get(m.provedor);
      if (atual) atual.n += 1;
      else contagem.set(m.provedor, { nome: m.provedor_nome, n: 1 });
    }
    return [...contagem.entries()]
      .map(([slug, { nome, n }]) => ({ slug, nome, n }))
      .sort((a, b) => b.n - a.n || a.nome.localeCompare(b.nome, "pt-BR"));
  }, [aposBusca]);

  const provedorAtivo = abas.some((a) => a.slug === provedor) ? provedor : "todos";

  const visiveis = useMemo(() => {
    const lista = aposBusca.filter((m) => provedorAtivo === "todos" || m.provedor === provedorAtivo);
    lista.sort(comparador(ordem, slugSelecionado));
    if (desc) lista.reverse();
    return lista;
  }, [aposBusca, provedorAtivo, ordem, desc, slugSelecionado]);

  const chaveLista = `${busca}|${JSON.stringify(filtros)}|${provedorAtivo}|${ordem}|${desc}`;
  const nLevas = levas.chave === chaveLista ? levas.n : 1;
  const limite = nLevas * CARDS_POR_LEVA;
  const restantes = Math.max(0, visiveis.length - limite);

  const temFiltro =
    busca.trim() !== "" || Object.values(filtros).some(Boolean) || provedorAtivo !== "todos";

  function limpar() {
    setBusca("");
    setFiltros(FILTROS_VAZIOS);
    setProvedor("todos");
  }

  const creditosSel = selecionado
    ? cabeNoModelo(selecionado, tier)
      ? creditosPorMensagem(selecionado.preco_prompt, selecionado.preco_completion, tier)
      : null
    : null;

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Modelos Disponíveis</h3>
        <p className="text-sm text-muted-foreground">
          Compare todos os modelos disponíveis e escolha o ideal para o seu agente.
        </p>
      </div>

      {/* Resumo do que está selecionado */}
      <div className="grid grid-cols-3 divide-x divide-border rounded-xl bg-brand-primary/5 p-3">
        <div className="min-w-0 pr-3">
          <p className="font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground">
            Modelo selecionado
          </p>
          <div className="mt-1 flex min-w-0 items-center gap-2">
            {selecionado ? (
              <LogoProvedor provedor={selecionado.provedor} className="size-7 text-[10px]" />
            ) : null}
            <span className="truncate text-sm font-semibold" title={slugSelecionado ?? undefined}>
              {selecionado ? nomeCurto(selecionado) : (slugSelecionado ?? "— nenhum —")}
            </span>
          </div>
        </div>
        <div className="min-w-0 px-3">
          <p className="font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground">
            Tamanho do contexto
          </p>
          <div className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
            <span className={cn("size-2 shrink-0 rounded-full", PONTO_TIER[tier])} aria-hidden />
            {rotuloTier(tier)}
          </div>
        </div>
        <div className="min-w-0 pl-3">
          <p className="font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground">
            Créditos
          </p>
          <div className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
            <BadgeDollarSign className="size-4 shrink-0 text-warning" aria-hidden />
            {creditosSel ?? (selecionado ? "—" : "?")}
          </div>
        </div>
      </div>

      {/* Busca */}
      <InputGroup className="h-9">
        <InputGroupAddon>
          <Search />
        </InputGroupAddon>
        <InputGroupInput
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar por modelo, fabricante ou provedor…"
          aria-label="Buscar modelo"
        />
      </InputGroup>

      {/* Chips de capacidade */}
      <div className="flex flex-wrap gap-1.5">
        {CHIPS.map(({ chave, rotulo, Icone }) => {
          const ativo = filtros[chave];
          return (
            <Button
              key={chave}
              type="button"
              variant="outline"
              size="sm"
              aria-pressed={ativo}
              onClick={() => setFiltros((f) => ({ ...f, [chave]: !f[chave] }))}
              className={cn(
                "rounded-full",
                ativo && "border-brand-primary bg-brand-primary/10 text-brand-primary"
              )}
            >
              <Icone className="size-3.5" />
              {rotulo}
            </Button>
          );
        })}
      </div>

      {/* Contagem + limpar */}
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">
          {visiveis.length} {visiveis.length === 1 ? "modelo encontrado" : "modelos encontrados"}
        </Badge>
        {/* ADR-005 leva B: sem `catalogo_completo` a API já manda só os
            recomendados — aqui só se explica por que a lista é curta. */}
        {plano.catalogo_completo === false && (
          <span className="text-xs text-muted-foreground">
            O plano {plano.nome} mostra os modelos recomendados
            {plano.upgrade_sugerido
              ? ` — o catálogo completo vem a partir do plano ${rotuloPlano(plano.upgrade_sugerido)}.`
              : "."}
          </span>
        )}
        {temFiltro && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={limpar}
            aria-label="Limpar filtros"
            title="Limpar filtros"
          >
            <FilterX className="size-4" />
          </Button>
        )}
      </div>

      {/* Ordenação */}
      <div className="flex items-center gap-2">
        <Select value={ordem} onValueChange={(v: string | null) => v && setOrdem(v as Ordem)}>
          <SelectTrigger className="w-full" aria-label="Ordenar por">
            <SelectValue>{(v: string | null) => ORDEM_ROTULO[(v as Ordem) ?? "relevancia"]}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(ORDEM_ROTULO) as Ordem[]).map((o) => (
              <SelectItem key={o} value={o}>
                {ORDEM_ROTULO[o]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => setDesc((d) => !d)}
          aria-label={desc ? "Ordem decrescente — inverter" : "Ordem crescente — inverter"}
          aria-pressed={desc}
          title="Inverter ordem"
          className="shrink-0"
        >
          {desc ? <ArrowUp className="size-4" /> : <ArrowDown className="size-4" />}
        </Button>
      </div>

      {/* Abas de provedor */}
      <ScrollArea className="w-full">
        <div className="flex w-max gap-1.5 pb-2" role="tablist" aria-label="Fabricante">
          <AbaProvedor
            ativa={provedorAtivo === "todos"}
            onClick={() => setProvedor("todos")}
            rotulo={`Todos · ${aposBusca.length}`}
          />
          {abas.map((a) => (
            <AbaProvedor
              key={a.slug}
              ativa={provedorAtivo === a.slug}
              onClick={() => setProvedor(a.slug)}
              rotulo={`${a.nome} · ${a.n}`}
              provedor={a.slug}
            />
          ))}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>

      {/* Cards */}
      {visiveis.length === 0 ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Nenhum modelo com esses filtros.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {slugSelecionado && !selecionado && (
            <CardForaDoCatalogo slug={slugSelecionado} />
          )}
          {visiveis.slice(0, limite).map((m) => (
            <CardModelo
              key={m.slug}
              modelo={m}
              tier={tier}
              plano={plano}
              selecionado={m.slug === slugSelecionado}
              onSelecionar={() => onSelecionar(m.slug)}
            />
          ))}
        </ul>
      )}
      {restantes > 0 && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            onClick={() => setLevas({ chave: chaveLista, n: nLevas + 1 })}
          >
            Mostrar mais ({restantes} restantes)
          </Button>
        </div>
      )}
    </div>
  );
}

function AbaProvedor({
  ativa,
  onClick,
  rotulo,
  provedor,
}: {
  ativa: boolean;
  onClick: () => void;
  rotulo: string;
  provedor?: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={ativa}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm font-medium transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        ativa
          ? "bg-brand-primary text-primary-foreground"
          : "bg-muted text-foreground hover:bg-muted/70"
      )}
    >
      {provedor ? (
        <LogoProvedor
          provedor={provedor}
          className={cn("size-5 rounded-md text-[9px]", ativa && "bg-primary-foreground/20 text-primary-foreground")}
        />
      ) : null}
      {rotulo}
    </button>
  );
}

function CardModelo({
  modelo: m,
  tier,
  plano,
  selecionado,
  onSelecionar,
}: {
  modelo: ModeloCatalogo;
  tier: TierContexto;
  plano: PlanoCatalogo;
  selecionado: boolean;
  onSelecionar: () => void;
}) {
  const bloqueado = modeloBloqueado(m, plano);
  function escolher() {
    if (bloqueado) {
      toast.info(
        `${nomeCurto(m)} é um modelo premium — não está no plano ${plano.nome}.` +
          (plano.upgrade_sugerido
            ? ` Disponível a partir do plano ${rotuloPlano(plano.upgrade_sugerido)}.`
            : "")
      );
      return;
    }
    onSelecionar();
  }
  return (
    <li className="min-w-0">
      <button
        type="button"
        aria-pressed={selecionado}
        aria-disabled={bloqueado || undefined}
        onClick={escolher}
        className={cn(
          "w-full rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
          selecionado && "border-l-4 border-l-success bg-success/5",
          bloqueado && "opacity-70"
        )}
      >
        <div className="flex items-start gap-2.5">
          <LogoProvedor provedor={m.provedor} />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="truncate font-semibold" title={m.slug}>
                {nomeCurto(m)}
              </span>
              {m.novo && (
                <span className="rounded-md bg-brand-primary px-1.5 py-px font-mono text-[10px] font-bold text-primary-foreground">
                  NEW
                </span>
              )}
              {m.tendencia && (
                <TrendingUp
                  className="size-4 text-success"
                  aria-label="Em alta no OpenRouter"
                  role="img"
                />
              )}
              {m.promo && (
                <span
                  className="inline-flex size-5 items-center justify-center rounded-full bg-success/15 text-success"
                  title="Promoção — gratuito ou preço zero de entrada"
                >
                  <BadgeDollarSign className="size-3.5" aria-label="Promoção" role="img" />
                </span>
              )}
              {m.curado && <Badge variant="secondary">Recomendado</Badge>}
              {bloqueado && (
                <span
                  className="inline-flex items-center gap-1 rounded-md bg-brand-primary/10 px-1.5 py-px font-mono text-[10px] font-bold text-brand-primary"
                  title={`Modelo premium — não está no plano ${plano.nome}`}
                >
                  <Lock className="size-3" aria-hidden />
                  BLOQUEADO →
                </span>
              )}
            </div>
            <p className="truncate text-sm text-muted-foreground">{m.provedor_nome}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Capacidade ativa={m.visao} Icone={Eye} rotulo="Visão (lê imagens)" />
            <Capacidade ativa={m.pensamento} Icone={Brain} rotulo="Pensamento (raciocínio)" />
            <Capacidade ativa={m.tools} Icone={Code} rotulo="HTTP Tools (chama ferramentas)" />
          </div>
        </div>

        <div className="mt-3 grid grid-cols-4 gap-1 sm:grid-cols-5">
          {ORDEM.map((t) => {
            const cabe = cabeNoModelo(m, t);
            const creditos = cabe
              ? creditosPorMensagem(m.preco_prompt, m.preco_completion, t)
              : null;
            const usd = cabe ? usdPorMensagem(m.preco_prompt, m.preco_completion, t) : null;
            return (
              <div
                key={t}
                className={cn(
                  "rounded-md px-1 py-1.5 text-center",
                  t === tier && "bg-brand-primary/10"
                )}
                title={
                  !cabe
                    ? `${rotuloTier(t)} não cabe na janela deste modelo`
                    : usd === null
                      ? "Preço desconhecido"
                      : `≈ ${formatarUsd(usd)} por mensagem`
                }
              >
                <div className="flex items-center justify-center gap-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <span className={cn("size-1.5 rounded-full", PONTO_TIER[t])} aria-hidden />
                  {t}
                </div>
                <div
                  className={cn(
                    "mt-0.5 text-lg font-semibold tabular-nums",
                    t === tier && "text-brand-primary"
                  )}
                >
                  {!cabe ? "—" : (creditos ?? "?")}
                </div>
              </div>
            );
          })}
        </div>
      </button>
    </li>
  );
}

function Capacidade({
  ativa,
  Icone,
  rotulo,
}: {
  ativa: boolean;
  Icone: typeof Eye;
  rotulo: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex size-7 items-center justify-center rounded-full",
        ativa ? "bg-muted text-foreground" : "text-muted-foreground/30"
      )}
      title={ativa ? rotulo : `Sem ${rotulo.toLowerCase()}`}
    >
      <Icone className="size-4" aria-label={ativa ? rotulo : `Sem ${rotulo}`} role="img" />
    </span>
  );
}

/** Modelo salvo no agente que não está (mais) no catálogo: continua selecionável. */
function CardForaDoCatalogo({ slug }: { slug: string }) {
  return (
    <li className="min-w-0">
      <div
        aria-current="true"
        className="w-full rounded-xl border border-l-4 border-l-success bg-success/5 p-3 text-left"
      >
        <div className="flex items-center gap-2.5">
          <LogoProvedor provedor={slug.split("/")[0].replace(/^~/, "")} />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="truncate font-mono text-sm font-semibold" title={slug}>
                {slug}
              </span>
              <Badge variant="warning">atual (fora do catálogo)</Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Continua salvo assim até você escolher outro modelo abaixo. Sem estimativa de
              créditos porque o preço não está no catálogo.
            </p>
          </div>
        </div>
      </div>
    </li>
  );
}

// ---- Tamanho do contexto -----------------------------------------------------

function TamanhoDoContexto({
  tier,
  tierSalvo,
  plano,
  onChange,
  modelo,
}: {
  tier: TierContexto;
  /** O que o agente tem gravado — difere de `tier` quando o plano rebaixou. */
  tierSalvo: TierContexto;
  plano: PlanoCatalogo | null;
  onChange: (t: TierContexto) => void;
  modelo: ModeloCatalogo | null;
}) {
  function escolher(t: TierContexto) {
    if (plano && tierBloqueado(t, plano)) {
      toast.info(
        `${rotuloTier(t)} não está no plano ${plano.nome} — ele libera até ${rotuloTier(plano.contexto_max)}.` +
          (plano.upgrade_sugerido
            ? ` Disponível a partir do plano ${rotuloPlano(plano.upgrade_sugerido)}.`
            : "")
      );
      return;
    }
    onChange(t);
  }
  return (
    <div className="space-y-2 border-t pt-4">
      <h3 className="text-base font-semibold">Tamanho do Contexto</h3>
      {plano && tierSalvo !== tier && (
        <p
          role="alert"
          className="rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm text-foreground"
        >
          O agente estava em {rotuloTier(tierSalvo)}, mas o plano {plano.nome} libera até{" "}
          {rotuloTier(plano.contexto_max)} — ele já opera como {rotuloTier(tier)} e é assim que
          vai ficar salvo
          {plano.upgrade_sugerido
            ? `, até o upgrade para o plano ${rotuloPlano(plano.upgrade_sugerido)}.`
            : "."}
        </p>
      )}
      <div className="space-y-2" role="radiogroup" aria-label="Tamanho do contexto">
        {ORDEM.map((t) => {
          const ativo = t === tier;
          const bloqueado = !!plano && tierBloqueado(t, plano);
          const cabe = modelo ? cabeNoModelo(modelo, t) : true;
          const creditos =
            modelo && cabe
              ? creditosPorMensagem(modelo.preco_prompt, modelo.preco_completion, t)
              : null;
          return (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={ativo}
              aria-disabled={bloqueado || undefined}
              onClick={() => escolher(t)}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-xl border p-3 text-left transition-colors hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                ativo ? "border-2 border-brand-primary bg-brand-primary/5" : "border-border",
                bloqueado && "opacity-70"
              )}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className={cn("size-2 rounded-full", PONTO_TIER[t])} aria-hidden />
                  <span className={cn("font-semibold", ativo && "text-brand-primary")}>
                    {rotuloTier(t)}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">{formatarChars(TIERS[t])} caracteres</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge variant={ativo ? "warning" : "outline"} className="font-mono tabular-nums">
                  {modelo ? (cabe ? `${creditos ?? "?"} C` : "—") : "? C"}
                </Badge>
                {bloqueado && plano && (
                  <Badge
                    variant="warning"
                    title={`Não está no plano ${plano.nome}`}
                    className="gap-1"
                  >
                    <Lock className="size-3" aria-hidden />
                    Premium
                    {plano.upgrade_sugerido
                      ? ` · a partir do ${rotuloPlano(plano.upgrade_sugerido)}`
                      : ""}
                  </Badge>
                )}
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-sm text-muted-foreground">
        Define quantos caracteres o agente consegue &quot;lembrar&quot; da conversa atual. Note
        que o custo em créditos varia conforme o tamanho do contexto selecionado.
      </p>
    </div>
  );
}

// ---- Fallback: catálogo indisponível → os dois selects do curado -----------

function SeletorCurado({
  curados,
  slug,
  onChange,
}: {
  curados: ModeloLLM[];
  slug: string | null;
  onChange: (slug: string | null) => void;
}) {
  const provedor = slug?.split("/")[0] ?? "";
  const nome = slug?.split("/").slice(1).join("/") ?? "";
  const provedores = [...new Set(curados.map((m) => m.provedor))].sort();
  const modelos = curados
    .filter((m) => m.provedor === provedor)
    .sort((x, y) => x.nome.localeCompare(y.nome));

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <div className="space-y-1.5">
        <Label>Provedor (catálogo curado)</Label>
        <Select
          value={provedor || null}
          onValueChange={(v: string | null) => onChange(v ? `${v}/` : null)}
        >
          <SelectTrigger className="w-full" aria-label="Provedor">
            <SelectValue placeholder="— selecione —">{(v: string | null) => v ?? "— selecione —"}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {provedores.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Modelo</Label>
        <Select
          value={nome || null}
          onValueChange={(v: string | null) => onChange(v ? `${provedor}/${v}` : null)}
          disabled={!provedor}
        >
          <SelectTrigger className="w-full" aria-label="Modelo">
            <SelectValue placeholder={provedor ? "— selecione —" : "(escolha o provedor)"}>
              {(v: string | null) => v ?? (provedor ? "— selecione —" : "(escolha o provedor)")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {modelos.map((m) => (
              <SelectItem key={m.id} value={m.nome}>
                {m.descricao ? `${m.nome} — ${m.descricao}` : m.nome}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function SkeletonCatalogo() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Carregando o catálogo de modelos">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-9 w-full" />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-36 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

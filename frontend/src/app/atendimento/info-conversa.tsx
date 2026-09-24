"use client";

import { useEffect } from "react";
import Link from "next/link";
import {
  Bot,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  ExternalLink,
  FolderOpen,
  Phone,
  Tag as TagIcon,
  Target,
  TriangleAlert,
  X,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useLocalStorage } from "@/hooks/use-local-storage";
import type { Atendimento, AtendimentoMensagem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ClassificacaoLeadConversa } from "@/app/clientes/classificacao-lead";

import { MediaPreview } from "./bolha-midia";
import { PainelCliente } from "./painel-cliente";
import {
  PRIORIDADE_CHIP,
  SENTIMENTO_CHIP,
  SITUACAO_AJUDA,
  SITUACAO_CHIP,
  SITUACAO_LABEL,
} from "./situacao";
import { TagPopover } from "./tag-popover";
import { formatarDataHoraCompleta } from "./timeline";

/** Iniciais pro avatar: "Stress Test" → "ST"; sem nome, "#" */
export function iniciaisDe(nome: string | null | undefined): string {
  const partes = (nome ?? "").trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "#";
  const a = partes[0][0] ?? "";
  const b = partes.length > 1 ? (partes[partes.length - 1][0] ?? "") : "";
  return (a + b).toUpperCase();
}

export type SecaoInfo = "contato" | "arquivos" | "triagem";

interface Props {
  atendimento: Atendimento;
  departamentoNome?: string | null;
  mensagens: AtendimentoMensagem[] | null;
  /** Seção que deve abrir em destaque (veio do ⋮ ou da faixa de triagem). */
  secao?: SecaoInfo;
  onFechar: () => void;
}

/**
 * Tudo que saiu do topo da conversa (conversa compacta, 2026-09): dados do
 * contato, protocolo/ID, tags, triagem da IA, coleta prévia, histórico e
 * arquivos. Continua a um toque — no avatar/nome do cabeçalho ou no ⋮ — mas
 * não ocupa mais a área da conversa.
 *
 * O MESMO conteúdo vai pra coluna lateral (desktop) e pro bottom sheet
 * (celular): `PainelInfo` escolhe o recipiente.
 */
export function InfoConversa({ atendimento, departamentoNome, mensagens, secao, onFechar }: Props) {
  const a = atendimento;
  const nome = a.cliente_nome ?? a.cliente_telefone ?? "Cliente";
  const arquivos = (mensagens ?? []).filter((m) => m.media_url || m.media_disponivel || m.response_media_url || m.response_media_disponivel);

  // Veio do ⋮ "Arquivos" ou da faixa de triagem: rola até a seção pedida.
  useEffect(() => {
    if (!secao || secao === "contato") return;
    document.getElementById(`info-${secao}`)?.scrollIntoView({ block: "start" });
  }, [secao]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start gap-3 border-b px-4 py-3">
        <Avatar size="lg">
          <AvatarFallback className="text-sm font-medium">{iniciaisDe(a.cliente_nome)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-semibold">{nome}</p>
          <p className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
            <Phone className="size-3 shrink-0" aria-hidden />
            {a.cliente_telefone ?? "—"}
          </p>
          {a.cliente_id && (
            <Link
              href={`/clientes/${a.cliente_id}`}
              prefetch={false}
              className="mt-1 inline-flex items-center gap-1 text-xs text-brand-primary hover:underline"
            >
              Ver ficha completa
              <ExternalLink className="size-3" aria-hidden />
            </Link>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onFechar} aria-label="Fechar informações">
          <X className="size-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3 text-sm">
        {/* Identificação do atendimento */}
        <section className="space-y-1.5">
          <Titulo>Atendimento</Titulo>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge
              variant="outline"
              className={cn("border-transparent", SITUACAO_CHIP[a.situacao])}
              title={SITUACAO_AJUDA[a.situacao]}
            >
              {SITUACAO_LABEL[a.situacao]}
            </Badge>
            {a.protocolo && (
              <Badge variant="outline" className="font-mono text-[10px]">
                #{a.protocolo}
              </Badge>
            )}
            <Badge variant="outline" className="font-mono text-[10px] text-muted-foreground">
              id {a.id}
            </Badge>
            {!a.iniciado_cliente && (
              <Badge variant="outline" className="text-[10px]" title="Conversa iniciada pela empresa">
                outbound
              </Badge>
            )}
            {a.solicitou_encerramento && (
              <Badge variant="outline" className="text-[10px]">
                pediu encerrar
              </Badge>
            )}
            {a.qtde_resposta_invalida > 0 && (
              <Badge
                variant="outline"
                className="text-[10px]"
                title={`Cliente errou ${a.qtde_resposta_invalida}× no menu/CSAT`}
              >
                <TriangleAlert className="size-3" />
                {a.qtde_resposta_invalida}
              </Badge>
            )}
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
            <dt>agente</dt>
            <dd className="truncate text-foreground">{a.agente_atual}</dd>
            <dt>setor</dt>
            <dd className="truncate text-foreground">{departamentoNome ?? "—"}</dd>
            <dt>aberto</dt>
            <dd className="text-foreground">{formatarDataHoraCompleta(a.created_at)}</dd>
          </dl>
        </section>

        {/* Tags do ATENDIMENTO (desta conversa) */}
        <section className="space-y-1.5">
          <Titulo icone={TagIcon}>Tags da conversa</Titulo>
          <TagPopover atendimentoId={a.id} />
        </section>

        <TriagemCard atendimento={a} destaque={secao === "triagem"} />
        <ColetaPreviaCard atendimento={a} />

        {/* Estágio do funil + temperatura do cliente (mig 201; a IA sugere). */}
        {a.cliente_id && (
          <section className="space-y-1.5">
            <Titulo icone={Target}>Classificação do lead</Titulo>
            <ClassificacaoLeadConversa clienteId={a.cliente_id} />
          </section>
        )}

        {/* Tags do cliente + último atendimento (painel do cliente de sempre) */}
        <PainelCliente
          atendimentoId={a.id}
          clienteId={a.cliente_id}
          clienteNome={a.cliente_nome ?? null}
          clienteTelefone={a.cliente_telefone ?? null}
        />

        <section className="space-y-1.5" id="info-arquivos">
          <Titulo icone={FolderOpen} destaque={secao === "arquivos"}>
            Arquivos{arquivos.length > 0 ? ` · ${arquivos.length}` : ""}
          </Titulo>
          <ArquivosDoAtendimento mensagens={mensagens} atendimentoId={a.id} />
        </section>
      </div>
    </div>
  );
}

function Titulo({
  children,
  icone: Icone,
  destaque,
}: {
  children: React.ReactNode;
  icone?: React.ComponentType<{ className?: string }>;
  destaque?: boolean;
}) {
  return (
    <h3
      className={cn(
        "flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground",
        destaque && "text-foreground"
      )}
    >
      {Icone && <Icone className="size-3" />}
      {children}
    </h3>
  );
}

/**
 * Recipiente do painel de informações: coluna lateral quando a conversa tem
 * largura pra isso (desktop com espaço), sheet lateral quando não tem (a
 * lista redimensionável e os dois sidebars comem a tela), bottom sheet no
 * celular. Só monta o conteúdo quando aberto — o histórico e as tags fazem
 * fetch ao montar.
 */
export function PainelInfo({
  aberto,
  recipiente,
  onAbertoChange,
  ...props
}: Props & {
  aberto: boolean;
  recipiente: "coluna" | "lateral" | "inferior";
  onAbertoChange: (v: boolean) => void;
}) {
  if (recipiente === "coluna") {
    if (!aberto) return null;
    return (
      <div className="flex w-80 shrink-0 flex-col border-l bg-card">
        <InfoConversa {...props} />
      </div>
    );
  }
  const inferior = recipiente === "inferior";
  return (
    <Sheet open={aberto} onOpenChange={onAbertoChange}>
      <SheetContent
        side={inferior ? "bottom" : "right"}
        showCloseButton={false}
        // `data-[side=bottom]:h-auto` do kit vence um `h-*` simples: sem a
        // variante, o sheet crescia com o conteúdo e o topo saía da tela.
        className={cn(
          "gap-0 p-0",
          inferior
            ? "max-h-[88dvh] rounded-t-2xl data-[side=bottom]:h-[88dvh]"
            : "w-full data-[side=right]:sm:max-w-sm"
        )}
      >
        <SheetTitle className="sr-only">Informações da conversa</SheetTitle>
        <SheetDescription className="sr-only">
          Dados do contato, tags, triagem, histórico e arquivos deste atendimento.
        </SheetDescription>
        {inferior && (
          <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-muted-foreground/30" aria-hidden />
        )}
        <InfoConversa {...props} />
      </SheetContent>
    </Sheet>
  );
}

/** Arquivos do atendimento — mídias de entrada e de saída, no array já
 *  carregado; sem fetch adicional. */
function ArquivosDoAtendimento({
  mensagens,
  atendimentoId,
}: {
  mensagens: AtendimentoMensagem[] | null;
  atendimentoId: number;
}) {
  const itens = (mensagens ?? []).flatMap((m) => {
    const out: {
      chave: string;
      url: string;
      tipo: string | null;
      nome: string | null;
      legenda?: string;
      quando: string | null;
    }[] = [];
    if (m.media_url || m.media_disponivel) {
      out.push({
        chave: `${m.id}-in`,
        url: m.media_url ?? `/api/proxy/midia/${atendimentoId}/${m.id}?lado=in`,
        tipo: m.media_type ?? null,
        nome: m.media_filename ?? null,
        legenda: m.incoming_message || undefined,
        quando: m.created_at,
      });
    }
    if (m.response_media_url || m.response_media_disponivel) {
      out.push({
        chave: `${m.id}-out`,
        url: m.response_media_url ?? `/api/proxy/midia/${atendimentoId}/${m.id}?lado=out`,
        tipo: m.response_media_type ?? null,
        nome: m.response_media_filename ?? null,
        legenda: m.response || undefined,
        quando: m.created_at,
      });
    }
    return out;
  });
  if (itens.length === 0) {
    return <p className="text-xs text-muted-foreground">Nenhum arquivo nesta conversa.</p>;
  }
  return (
    <div className="grid grid-cols-1 gap-2">
      {itens.map((f) => (
        <div key={f.chave} className="rounded-md border bg-muted/20 p-2">
          <MediaPreview url={f.url} type={f.tipo} caption={f.legenda} nome={f.nome} />
          <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground" title={f.nome ?? undefined}>
            {formatarDataHoraCompleta(f.quando)} · {f.nome ?? f.tipo ?? "—"}
          </p>
        </div>
      ))}
    </div>
  );
}

// Card "Triagem IA" — só quando o agente classificou ou gerou resumo.
function TriagemCard({ atendimento, destaque }: { atendimento: Atendimento; destaque?: boolean }) {
  const [collapsed, setCollapsed] = useCollapseState(`triagem-${atendimento.id}`, false);
  const [faixaOculta, setFaixaOculta] = useCollapseState(`triagem-faixa-${atendimento.id}`, false);
  const has =
    atendimento.resumo_ia ||
    atendimento.classificacao ||
    atendimento.prioridade ||
    atendimento.sentimento;
  if (!has) return null;

  return (
    <section className="space-y-1.5" id="info-triagem">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-expanded={!collapsed}
      >
        <Titulo icone={Bot} destaque={destaque}>
          Triagem da IA
          {atendimento.triagem_completa && (
            <Badge variant="outline" className="ml-1 text-[10px] normal-case tracking-normal">
              completa
            </Badge>
          )}
        </Titulo>
        {collapsed ? (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronUp className="size-3.5 text-muted-foreground" />
        )}
      </button>
      {!collapsed && (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            {atendimento.prioridade && (
              <span
                className={cn(
                  "inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium",
                  PRIORIDADE_CHIP[atendimento.prioridade]
                )}
              >
                prioridade: {atendimento.prioridade}
              </span>
            )}
            {atendimento.sentimento && (
              <span
                className={cn(
                  "inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium",
                  SENTIMENTO_CHIP[atendimento.sentimento]
                )}
              >
                sentimento: {atendimento.sentimento}
              </span>
            )}
            {atendimento.classificacao && (
              <Badge variant="outline" className="font-mono text-[10px]">
                {atendimento.classificacao}
              </Badge>
            )}
          </div>
          {atendimento.resumo_ia && (
            <div className="rounded-md bg-muted/40 p-2 text-xs">
              <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                Resumo do agente
              </div>
              <pre className="whitespace-pre-wrap font-sans leading-relaxed">
                {atendimento.resumo_ia}
              </pre>
            </div>
          )}
          {/* A faixa do topo foi fechada com o ✕: é daqui que ela volta. */}
          {faixaOculta && (
            <button
              type="button"
              onClick={() => setFaixaOculta(false)}
              className="text-[11px] text-brand-primary hover:underline"
            >
              Mostrar a faixa de triagem no topo da conversa
            </button>
          )}
        </>
      )}
    </section>
  );
}

// Card "Coleta prévia" — respostas do wizard de coleta que rodou antes de
// chegar no atendente. Só quando `coleta_resumo` está populado.
function ColetaPreviaCard({ atendimento }: { atendimento: Atendimento }) {
  const [collapsed, setCollapsed] = useCollapseState(`coleta-${atendimento.id}`, false);
  const resumo = atendimento.coleta_resumo;
  if (!resumo || !resumo.respostas) return null;
  const entries = Object.entries(resumo.respostas);
  if (entries.length === 0) return null;

  return (
    <section className="space-y-1.5">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-expanded={!collapsed}
      >
        <Titulo icone={ClipboardList}>
          Coleta prévia
          {resumo.item_label && (
            <Badge variant="outline" className="ml-1 text-[10px] normal-case tracking-normal">
              via “{resumo.item_label}”
            </Badge>
          )}
          {collapsed && (
            <span className="normal-case tracking-normal text-muted-foreground/70">
              ({entries.length} {entries.length === 1 ? "campo" : "campos"})
            </span>
          )}
        </Titulo>
        {collapsed ? (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronUp className="size-3.5 text-muted-foreground" />
        )}
      </button>
      {!collapsed && (
        <dl className="space-y-1.5 text-xs">
          {entries.map(([key, val]) => (
            <div key={key} className="flex flex-col gap-0.5">
              <dt className="text-[11px] font-medium text-muted-foreground">{val.label}</dt>
              <dd className="rounded-md bg-muted/40 px-2 py-1 font-mono text-foreground">
                {val.valor || <span className="italic text-muted-foreground">(sem resposta)</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

// Estado de collapse persistido em localStorage por chave (preferência por
// atendimento). Valores antigos eram "1"/"0" — por isso a coerção. Duas
// instâncias com a mesma chave ficam em sincronia (o hook notifica).
export function useCollapseState(key: string, initialCollapsed: boolean): [boolean, (next: boolean) => void] {
  const [salvo, setSalvo] = useLocalStorage<boolean | number>(
    `atendimento-card-collapsed:${key}`,
    initialCollapsed
  );
  return [Boolean(salvo), setSalvo];
}

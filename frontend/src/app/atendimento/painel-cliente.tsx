"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  History,
  Loader2,
  PauseCircle,
  Tag as TagIcon,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { Atendimento, Tag } from "@/lib/api";

import {
  aplicarTagsClienteAction,
  loadClienteHistoricoAction,
  loadTagsAction,
  loadTagsClienteAction,
} from "./actions";

type StatusKey = "aguardando" | "em_andamento" | "resolvido" | "abandonado";

const STATUS_META: Record<
  StatusKey,
  { label: string; cls: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  aguardando: {
    label: "Aguardando",
    cls: "text-warning",
    Icon: Clock,
  },
  em_andamento: {
    label: "Em andamento",
    cls: "text-brand-primary",
    Icon: PauseCircle,
  },
  resolvido: {
    label: "Resolvido",
    cls: "text-success",
    Icon: CheckCircle2,
  },
  abandonado: {
    label: "Abandonado",
    cls: "text-muted-foreground",
    Icon: XCircle,
  },
};

interface Props {
  atendimentoId: number;
  clienteId: number | null;
  clienteNome: string | null;
  clienteTelefone: string | null;
}

/**
 * Contexto do cliente pro atendente humano: tags da PESSOA e o último
 * atendimento anterior. Vive dentro do painel de informações da conversa
 * (`info-conversa.tsx`) — que só monta quando aberto, então o fetch do
 * histórico acontece ao montar (antes havia um botão de expandir aqui; o
 * recipiente é que abre e fecha agora). Nome e telefone ficam no cabeçalho
 * do painel, não repetidos aqui.
 */
export function PainelCliente({ atendimentoId, clienteId }: Props) {
  const [loading, setLoading] = useState(false);
  const [historico, setHistorico] = useState<Atendimento[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Guarda "já tentei carregar ESTE cliente" — `historico.length === 0` era
  // indistinguível de "carreguei e o cliente não tem nenhum atendimento
  // anterior", que é o caso mais comum (1ª interação). Cada resolução da
  // promise reavaliava a mesma condição vazia e disparava a Server Action de
  // novo — mesmo bug do popover de transferência (#133), achado em produção
  // 2026-09-17. `clienteIdRef` reseta a guarda quando o cliente muda SEM
  // remontar o componente.
  const historicoCarregado = useRef(false);
  const clienteIdRef = useRef<number | null>(null);

  // Carrega só o último atendimento anterior — quem precisa ver histórico
  // completo abre a ficha do cliente via "Ver ficha completa".
  useEffect(() => {
    if (clienteIdRef.current !== clienteId) {
      clienteIdRef.current = clienteId;
      historicoCarregado.current = false;
    }
    if (!clienteId || historicoCarregado.current || loading) return;
    setLoading(true);
    void loadClienteHistoricoAction(clienteId, {
      excludeId: atendimentoId,
      limit: 1,
    }).then((r) => {
      setLoading(false);
      if (r.ok) {
        setHistorico(r.atendimentos);
        historicoCarregado.current = true;
      } else {
        setError(r.error);
      }
    });
  }, [clienteId, atendimentoId, loading]);

  if (!clienteId) {
    return null;
  }

  return (
    <>
      {/* Tags do CLIENTE — alimentam as abas, que agrupam por pessoa.
          Marcar aqui vale pra TODA conversa dele, inclusive as próximas;
          tag no atendimento valeria só pra esta. */}
      <TagsDoCliente clienteId={clienteId} />

      {/* Último atendimento anterior — histórico completo via ficha */}
      <section>
        <div className="mb-1.5 flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground">
            <History className="size-3" />
            Último atendimento
          </h3>
          <Link
            href={`/clientes/${clienteId}`}
            prefetch={false}
            className="text-[10px] text-brand-primary hover:underline"
          >
            ver todos
          </Link>
        </div>

        {loading && (
          <p className="flex items-center gap-1.5 py-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Carregando…
          </p>
        )}

        {error && (
          <p className="flex items-center gap-1.5 py-2 text-xs text-destructive">
            <AlertCircle className="h-3 w-3" />
            {error}
          </p>
        )}

        {!loading && !error && historico.length === 0 && (
          <p className="py-1 text-xs text-muted-foreground">
            Nenhum atendimento anterior — esta é a primeira interação.
          </p>
        )}

        {!loading && historico.length > 0 && (
          <ul className="space-y-1.5">
            {historico.map((atd) => {
              const meta = STATUS_META[atd.status as StatusKey];
              const Icon = meta?.Icon ?? Clock;
              return (
                <li key={atd.id}>
                  {/* Não-clicável: re-abrir atendimento via ?focus= ainda
                      não é suportado em page.tsx. Quem quiser detalhe vai
                      pela ficha do cliente (link "ver todos" acima). */}
                  <div className="flex items-start gap-2 rounded-md bg-muted/30 px-2 py-1.5 text-xs">
                    <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", meta?.cls ?? "")} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1">
                        <span className="truncate font-medium">
                          {meta?.label ?? atd.status}
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          #{atd.protocolo ?? atd.id}
                        </span>
                      </div>
                      {atd.classificacao && (
                        <p className="truncate text-muted-foreground">{atd.classificacao}</p>
                      )}
                      <p className="text-[10px] text-muted-foreground">
                        {atd.created_at
                          ? new Date(atd.created_at).toLocaleDateString("pt-BR", {
                              day: "2-digit",
                              month: "short",
                              year: "2-digit",
                            })
                          : "—"}
                      </p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}


/**
 * Tags da PESSOA, não da conversa.
 *
 * É o que alimenta as abas: uma aba "Mackenzie" mostra as conversas de quem tem
 * essa tag, e a próxima conversa do mesmo cliente entra sozinha. Até aqui os
 * endpoints (`POST /api/clientes/{id}/tags`) existiam e **nenhuma tela os
 * chamava** — as abas ficavam permanentemente vazias.
 */
function TagsDoCliente({ clienteId }: { clienteId: number }) {
  const [disponiveis, setDisponiveis] = useState<Tag[]>([]);
  const [aplicadas, setAplicadas] = useState<string[] | null>(null);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    void loadTagsAction().then((r) => {
      if (r.ok) setDisponiveis(r.tags);
    });
    void loadTagsClienteAction(clienteId).then((r) => {
      if (r.ok) setAplicadas(r.tags);
      else setErro(r.error);
    });
  }, [clienteId]);

  async function alternar(nome: string) {
    if (aplicadas === null || salvando) return;
    const tinha = aplicadas.includes(nome);
    // Otimista: a lista responde no toque. Se falhar, volta ao que era — o
    // servidor é a verdade, e mostrar a tag aplicada sem estar seria pior.
    const antes = aplicadas;
    setAplicadas(tinha ? aplicadas.filter((n) => n !== nome) : [...aplicadas, nome]);
    setSalvando(nome);
    setErro(null);
    const r = await aplicarTagsClienteAction(
      clienteId,
      tinha ? [] : [nome],
      tinha ? [nome] : []
    );
    setSalvando(null);
    if (!r.ok) {
      setAplicadas(antes);
      setErro(r.error);
    }
  }

  if (disponiveis.length === 0) return null;

  return (
    <section>
      <h3 className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground">
        <TagIcon className="size-3" />
        Tags do cliente
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {disponiveis.map((t) => {
          const on = aplicadas?.includes(t.nome) ?? false;
          return (
            <button
              key={t.id}
              type="button"
              disabled={aplicadas === null || salvando !== null}
              onClick={() => void alternar(t.nome)}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors disabled:opacity-50 ${
                on
                  ? "border-brand-primary bg-brand-primary/15 text-foreground"
                  : "border-foreground/15 text-muted-foreground hover:bg-muted/50"
              }`}
              style={on && t.cor ? { borderColor: t.cor } : undefined}
            >
              {salvando === t.nome ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : null}
              {t.nome}
            </button>
          );
        })}
      </div>
      {erro && <p className="mt-1 text-xs text-destructive">{erro}</p>}
    </section>
  );
}

"use client";

import { diffLines } from "diff";
import {
  History,
  Loader2,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Sparkles,
  Undo2,
  UserRound,
} from "lucide-react";
import { useCallback, useMemo, useState, useTransition } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { AgenteIA, BateriaPlacar, PromptVersao } from "@/lib/api";

import {
  getVersaoPromptAction,
  listarVersoesPromptAction,
  restaurarVersaoPromptAction,
} from "./actions";

const ORIGEM_LABEL: Record<PromptVersao["origem"], string> = {
  inicial: "Inicial",
  edicao: "Edição",
  restauracao: "Restauração",
  backfill: "Recuperada",
};

function formatarQuando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const minutos = Math.round((Date.now() - d.getTime()) / 60000);
  if (minutos < 1) return "agora";
  if (minutos < 60) return `há ${minutos} min`;
  if (minutos < 60 * 24) return `há ${Math.round(minutos / 60)} h`;
  if (minutos < 60 * 24 * 7) return `há ${Math.round(minutos / 60 / 24)} dias`;
  return d.toLocaleDateString("pt-BR");
}

/**
 * Diff por linha contra o texto vivo. `diffLines` devolve blocos com
 * `added`/`removed`; as linhas sem marca são contexto e aparecem só
 * resumidas, senão um prompt de 30 KB vira uma parede de texto igual.
 */
function DiffPorLinha({ antigo, atual }: { antigo: string; atual: string }) {
  const blocos = useMemo(() => diffLines(antigo, atual), [antigo, atual]);
  const semMudanca = blocos.every((b) => !b.added && !b.removed);

  if (semMudanca) {
    return (
      <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        Idêntico ao texto atual.
      </p>
    );
  }

  return (
    // Quebra linha em vez de rolar na horizontal: prompt é prosa, e uma
    // instrução longa cortada na borda é justamente a que precisa ser lida.
    <div className="max-h-[60vh] overflow-y-auto rounded-md border">
      <pre className="whitespace-pre-wrap break-words text-[11px] leading-relaxed">
        {blocos.map((bloco, i) => {
          const linhas = bloco.value.replace(/\n$/, "").split("\n");
          if (!bloco.added && !bloco.removed) {
            // contexto: mostra no máximo 2 linhas de cada ponta
            const resumo =
              linhas.length > 4
                ? [
                    ...linhas.slice(0, 2),
                    `… ${linhas.length - 4} linhas iguais …`,
                    ...linhas.slice(-2),
                  ]
                : linhas;
            return resumo.map((l, j) => (
              <div key={`${i}-${j}`} className="px-2 text-muted-foreground">
                <span className="select-none opacity-40">{"  "}</span>
                {l}
              </div>
            ));
          }
          return linhas.map((l, j) => (
            <div
              key={`${i}-${j}`}
              className={
                bloco.added
                  ? "bg-emerald-500/10 px-2 text-emerald-700 dark:text-emerald-400"
                  : "bg-red-500/10 px-2 text-red-700 dark:text-red-400"
              }
            >
              <span className="select-none opacity-60">
                {bloco.added ? "+ " : "- "}
              </span>
              {l}
            </div>
          ));
        })}
      </pre>
    </div>
  );
}

/**
 * Selo da bateria de regressão. Destaca **vazamento** e não custo: cinco dos
 * doze cenários canônicos são ataque (injeção, exfiltração do prompt,
 * jailbreak), e quem defende contra eles é o próprio prompt — é esse número
 * que muda a decisão de promover ou voltar.
 */
function SeloBateria({ b }: { b: PromptVersao["bateria"] }) {
  if (!b) {
    return (
      <Badge
        variant="outline"
        className="gap-1 px-1.5 py-0 text-[10px] text-muted-foreground"
      >
        <ShieldQuestion className="size-2.5" /> não testada
      </Badge>
    );
  }
  const limpo = b.vazamentos === 0 && b.erros === 0;
  return (
    <Badge
      variant="outline"
      className={
        limpo
          ? "gap-1 border-emerald-500/40 px-1.5 py-0 text-[10px] text-emerald-700 dark:text-emerald-400"
          : "gap-1 border-amber-500/50 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-400"
      }
    >
      {limpo ? (
        <ShieldCheck className="size-2.5" />
      ) : (
        <ShieldAlert className="size-2.5" />
      )}
      {limpo
        ? `testada · ${b.cenarios ?? "?"} cenários`
        : `${b.vazamentos} vazamento(s)${b.erros ? ` · ${b.erros} erro(s)` : ""}`}
    </Badge>
  );
}

function PlacarBateria({ placar }: { placar: BateriaPlacar[] }) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/50 text-muted-foreground">
          <tr>
            <th className="px-2 py-1 text-left font-medium">Modelo</th>
            <th className="px-2 py-1 text-right font-medium">Vazam.</th>
            <th className="px-2 py-1 text-right font-medium">Erros</th>
            <th className="px-2 py-1 text-right font-medium">Tempo</th>
            <th className="px-2 py-1 text-right font-medium">Custo</th>
          </tr>
        </thead>
        <tbody>
          {placar.map((p) => (
            <tr key={p.modelo} className="border-t">
              {/* Trunca em vez de quebrar: nome de modelo em duas linhas
                  empurrava a coluna de custo pra fora do painel. */}
              <td
                className="max-w-[9rem] truncate px-2 py-1 font-mono"
                title={p.modelo}
              >
                {p.modelo}
              </td>
              <td
                className={`px-2 py-1 text-right ${
                  p.vazamentos > 0 ? "font-semibold text-amber-600" : ""
                }`}
              >
                {p.vazamentos}
              </td>
              <td className="px-2 py-1 text-right">{p.erros}</td>
              <td className="px-2 py-1 text-right">
                {(p.tempo_medio_ms / 1000).toFixed(1)}s
              </td>
              <td className="px-2 py-1 text-right">
                ${p.custo_total_usd.toFixed(4)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  slug: string;
  /** Texto vivo — é contra ele que o diff compara. */
  atual: string;
  /** Chamado após restaurar, pra recarregar o editor com o texto novo. */
  onRestaurado: (agente: AgenteIA) => void;
}

export function PromptHistorico({ slug, atual, onRestaurado }: Props) {
  const [aberto, setAberto] = useState(false);
  const [versoes, setVersoes] = useState<PromptVersao[] | null>(null);
  const [selecionada, setSelecionada] = useState<number | null>(null);
  // Guarda o detalhe inteiro (texto + placar completo), não só o texto: o
  // placar por modelo só vem nesta chamada, nunca na listagem.
  const [detalhe, setDetalhe] = useState<
    (PromptVersao & { texto: string }) | null
  >(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [isPending, startTransition] = useTransition();

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    const r = await listarVersoesPromptAction(slug);
    setCarregando(false);
    if (!r.ok) {
      setErro(r.error);
      return;
    }
    setVersoes(r.data);
  }, [slug]);

  // Carrega no clique, não num efeito: buscar o histórico é reação a uma
  // ação do usuário, e um `useEffect` que chama setState em cascata é
  // exatamente o que a regra `set-state-in-effect` recusa.
  function abrir() {
    setAberto(true);
    void carregar();
  }

  function abrirVersao(versao: number) {
    if (selecionada === versao) {
      setSelecionada(null);
      setDetalhe(null);
      return;
    }
    setSelecionada(versao);
    setDetalhe(null);
    setErro(null);
    startTransition(async () => {
      const r = await getVersaoPromptAction(slug, versao);
      if (!r.ok) {
        setErro(r.error);
        return;
      }
      setDetalhe(r.data);
    });
  }

  function restaurar(versao: number) {
    // Voltar pra uma versão que nunca passou pela bateria é decisão do
    // usuário, mas tem de ser informada: são as defesas contra injeção e
    // jailbreak que ficam sem aval.
    const alvo = (versoes ?? []).find((v) => v.versao === versao);
    const aviso = alvo?.bateria
      ? ""
      : `\n\nAtenção: esta versão nunca passou pela bateria de regressão — ` +
        `as defesas contra injeção e jailbreak dela não foram testadas.`;
    if (
      !confirm(
        `Restaurar a versão ${versao}?\n\nO texto atual não é apagado — ele ` +
          `continua no histórico, e a restauração entra como uma versão nova.` +
          aviso,
      )
    )
      return;
    setErro(null);
    startTransition(async () => {
      const r = await restaurarVersaoPromptAction(slug, versao);
      if (!r.ok) {
        setErro(r.error);
        return;
      }
      onRestaurado(r.data);
      setSelecionada(null);
      setDetalhe(null);
      await carregar();
    });
  }

  return (
    <>
      {/* Botão fora do SheetTrigger de propósito: o Sheet é Base UI, cujo
          Trigger usa `render` (não `asChild`), e o estado `aberto` já é
          controlado aqui — um clique direto é mais simples que a ponte. */}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={abrir}
      >
        <History className="size-3.5" />
        Histórico
        {versoes && versoes.length > 0 ? (
          <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px]">
            {versoes.length}
          </Badge>
        ) : null}
      </Button>

      <Sheet
        open={aberto}
        onOpenChange={(v) => {
          setAberto(v);
          // recarrega ao reabrir: o usuário pode ter salvo entre uma e outra
          if (!v) setVersoes(null);
        }}
      >
        <SheetContent className="flex w-full flex-col gap-0 sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <History className="size-4" /> Histórico do prompt
            </SheetTitle>
            <SheetDescription>
              Cada alteração vira uma versão. Restaurar não apaga nada — entra
              como versão nova, então dá pra voltar de novo.
            </SheetDescription>
          </SheetHeader>

          {erro ? (
            <p className="mx-4 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
              {erro}
            </p>
          ) : null}

          <ScrollArea className="flex-1 px-4 pb-4">
            {carregando ? (
              <p className="flex items-center gap-2 py-6 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Carregando…
              </p>
            ) : null}

            {versoes && versoes.length === 0 ? (
              <p className="py-6 text-xs text-muted-foreground">
                Ainda não há versões registradas para este agente.
              </p>
            ) : null}

            <ul className="space-y-2">
              {(versoes ?? []).map((v, i) => {
                const ehTopo = i === 0;
                const aberta = selecionada === v.versao;
                return (
                  <li key={v.versao} className="rounded-lg border">
                    <button
                      type="button"
                      onClick={() => abrirVersao(v.versao)}
                      className="flex w-full flex-col gap-1 p-3 text-left hover:bg-muted/50"
                    >
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold">
                          v{v.versao}
                        </span>
                        {ehTopo ? (
                          <Badge className="gap-1 px-1.5 py-0 text-[10px]">
                            <Sparkles className="size-2.5" /> em uso
                          </Badge>
                        ) : null}
                        <Badge
                          variant="outline"
                          className="px-1.5 py-0 text-[10px]"
                        >
                          {ORIGEM_LABEL[v.origem] ?? v.origem}
                        </Badge>
                        <SeloBateria b={v.bateria} />
                        <span className="text-[11px] text-muted-foreground">
                          {formatarQuando(v.criado_em)}
                        </span>
                      </span>
                      <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <UserRound className="size-3" />
                          {v.criado_por_nome ?? "—"}
                        </span>
                        <span>·</span>
                        <span>
                          {v.caracteres.toLocaleString("pt-BR")} caracteres
                        </span>
                        {v.restaurada_de != null ? (
                          <>
                            <span>·</span>
                            <span className="inline-flex items-center gap-1">
                              <Undo2 className="size-3" /> da v{v.restaurada_de}
                            </span>
                          </>
                        ) : null}
                      </span>
                      {v.nota ? (
                        <span className="text-[11px] italic text-foreground/80">
                          “{v.nota}”
                        </span>
                      ) : null}
                    </button>

                    {aberta ? (
                      <div className="space-y-2 border-t p-3">
                        {detalhe === null ? (
                          <p className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Loader2 className="size-3.5 animate-spin" />
                            Carregando o texto…
                          </p>
                        ) : (
                          <>
                            {detalhe.bateria_placar?.length ? (
                              <div className="space-y-1">
                                <p className="text-[11px] text-muted-foreground">
                                  Bateria de {detalhe.bateria?.cenarios ?? "?"}{" "}
                                  cenários — 5 deles são ataque (injeção,
                                  exfiltração do prompt, jailbreak).
                                </p>
                                <PlacarBateria
                                  placar={detalhe.bateria_placar}
                                />
                              </div>
                            ) : null}
                            <p className="text-[11px] text-muted-foreground">
                              Comparado com o texto atual:{" "}
                              <span className="text-red-600 dark:text-red-400">
                                vermelho sai
                              </span>
                              ,{" "}
                              <span className="text-emerald-600 dark:text-emerald-400">
                                verde entra
                              </span>
                              .
                            </p>
                            <DiffPorLinha
                              antigo={detalhe.texto}
                              atual={atual}
                            />
                            {!ehTopo ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                className="gap-1.5"
                                disabled={isPending}
                                onClick={() => restaurar(v.versao)}
                              >
                                {isPending ? (
                                  <Loader2 className="size-3.5 animate-spin" />
                                ) : (
                                  <RotateCcw className="size-3.5" />
                                )}
                                Restaurar esta versão
                              </Button>
                            ) : null}
                          </>
                        )}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </>
  );
}

"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Headphones, SearchX } from "lucide-react";
import { toast } from "sonner";

import type { Atendimento, Departamento, TipoVisualizacao } from "@/lib/api";
import { useColunaRedimensionavel } from "@/hooks/use-colunas-redimensionaveis";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { useMediaQuery } from "@/hooks/use-mobile";

import {
  carregarAtendimentosAction,
  loadAtendentesAction,
  marcarAtendimentoNaoLidoAction,
  type FiltrosFila,
} from "./actions";
import { agruparAtendimentos, type ModoAgrupamento } from "./agrupar";
import { AlcaColuna } from "./alca-coluna";
import { AtendimentoDrawer } from "./atendimento-drawer";
import { CardAtendimento } from "./card-atendimento";
import { GrupoFila } from "./grupo-fila";
import { ListaToolbar } from "./lista-toolbar";

interface Props {
  /** Render do servidor — vira `initialData` do Query (sem flash, sem refetch
   *  no mount). A partir daí quem manda na lista é o cache. */
  atendimentos: Atendimento[];
  tipo: TipoVisualizacao;
  /** Compõe a queryKey: trocar de filtro é outra chave, outro initialData. */
  filtros: FiltrosFila;
  /** Quem está logado — define "Meus atendimentos" e "(você)". */
  userId: string;
  departamentos: Departamento[];
}

// 440 por padrão: a 1440px com os dois sidebars abertos (256 + 256) sobram
// ~1150px pra lista + conversa, e 560 (o mock, que tem UM rail) deixaria a
// conversa com 320. O operador arrasta até 860 quando quiser.
const LIMITES_LISTA = { padrao: 440, min: 320, max: 860 };
// Defaults ESTÁVEIS pro `useLocalStorage` (entram no memo do snapshot).
const MODO_PADRAO: ModoAgrupamento = "status";
const SEM_GRUPOS_TOCADOS: Record<string, boolean> = {};

/**
 * Fila agrupada + conversa, lado a lado (inbox agrupado 2026-09).
 *
 * A lista continua vindo do servidor (filtros, `q`, paginação) e do cache do
 * Query (SSE invalida); o que é NOVO acontece no cliente sobre a página
 * carregada: agrupar por status/departamento/responsável, abrir/fechar
 * grupos, redimensionar a coluna. A conversa selecionada vive na URL
 * (`?id=`) — atualizada com `history.replaceState`, que o App Router
 * integra ao `useSearchParams` SEM re-renderizar a página no servidor;
 * recarregar ou trocar de aba do rail (que preserva o `id`) mantém a
 * conversa aberta.
 *
 * Abaixo de `lg` (tablet/celular) o drawer continua, porque 390px não
 * comportam duas colunas — e só UM drawer fica montado: escondido por CSS o
 * outro continuava vivo (SSE, LISTEN no Postgres e reload da timeline).
 */
export function AtendimentoList({
  atendimentos: iniciais,
  tipo,
  filtros,
  userId,
  departamentos,
}: Props) {
  const sp = useSearchParams();
  const queryClient = useQueryClient();
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  // A fila passa a ser servida pelo cache do Query: o evento SSE invalida a
  // chave e SÓ esta lista revalida — antes, `router.refresh()` refazia os
  // quatro fetches da página inteira a cada mensagem.
  const { data: atendimentos } = useQuery({
    queryKey: ["atendimentos", filtros],
    queryFn: async () => {
      const r = await carregarAtendimentosAction(filtros);
      // Lançar (em vez de devolver o erro) é o que liga o retry/backoff do
      // Query — inclusive o recuo no 429.
      if (!r.ok) throw new Error(r.error);
      return r.atendimentos;
    },
    initialData: iniciais,
  });

  // --- agrupamento ---------------------------------------------------------
  const [modo, setModo] = useLocalStorage<ModoAgrupamento>("atd-agrupar-por", MODO_PADRAO);
  // Só o modo "responsável" precisa dos nomes; nos outros nem consulta.
  const { data: atendentes } = useQuery({
    queryKey: ["atendentes"],
    queryFn: async () => {
      const r = await loadAtendentesAction();
      if (!r.ok) throw new Error(r.error);
      return r.atendentes;
    },
    staleTime: 60_000,
    enabled: modo === "responsavel",
  });
  const grupos = useMemo(
    () =>
      agruparAtendimentos(atendimentos, modo, {
        userId,
        departamentos,
        atendentes: atendentes ?? [],
      }),
    [atendimentos, modo, userId, departamentos, atendentes]
  );
  const nomeDepartamento = useMemo(
    () => new Map(departamentos.map((d) => [d.id, d.nome])),
    [departamentos]
  );

  // Aberto/fechado por grupo, persistido. Grupo que nunca foi tocado segue
  // o padrão do agrupamento (IA e "em atendimento" nascem fechados).
  const [abertos, setAbertos] = useLocalStorage<Record<string, boolean>>(
    "atd-grupos-abertos",
    SEM_GRUPOS_TOCADOS
  );
  const estaAberto = useCallback(
    (id: string, padrao: boolean) => abertos[id] ?? padrao,
    [abertos]
  );
  const alternarGrupo = (id: string) => {
    const g = grupos.find((x) => x.id === id);
    if (!g) return;
    setAbertos((prev) => ({ ...prev, [id]: !(prev[id] ?? g.abertoPorPadrao) }));
  };
  const algumAberto = grupos.some((g) => estaAberto(g.id, g.abertoPorPadrao));
  const alternarTodos = () => {
    const proximo = !algumAberto;
    setAbertos((prev) => {
      const novo = { ...prev };
      for (const g of grupos) novo[g.id] = proximo;
      return novo;
    });
  };

  // Relógio da lista: "há 12min" e "Sem resposta há 3h" envelhecem sem que
  // nada chegue — um tick por minuto re-renderiza a lista e os cards (sem
  // memo) recalculam os tempos; os helpers leem o relógio por conta própria
  // e o render aqui fica puro, como o React Compiler exige.
  const [, tick] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    const t = setInterval(tick, 60_000);
    return () => clearInterval(t);
  }, []);

  // --- conversa selecionada (?id=) -----------------------------------------
  const ativoId = Number(sp.get("id")) || null;
  // Último snapshot do selecionado: quando a conversa sai da página (mudou
  // de aba, foi resolvida) o painel não some no meio da leitura. Atualizado
  // DURANTE o render quando a lista traz a conversa (o padrão do React pra
  // "guardar informação de renders anteriores"), não num efeito.
  const encontrado = ativoId ? (atendimentos.find((a) => a.id === ativoId) ?? null) : null;
  const [snapshot, setSnapshot] = useState<Atendimento | null>(null);
  if (encontrado && encontrado !== snapshot) setSnapshot(encontrado);
  const ativo = encontrado ?? (snapshot?.id === ativoId ? snapshot : null);

  const definirId = useCallback((id: number | null) => {
    const params = new URLSearchParams(window.location.search);
    if (id) params.set("id", String(id));
    else params.delete("id");
    const qs = params.toString();
    // `replaceState` nativo: o App Router sincroniza `useSearchParams` sem
    // pedir a página ao servidor (um `router.replace` refaria os 4 fetches).
    window.history.replaceState(null, "", `${window.location.pathname}${qs ? `?${qs}` : ""}`);
  }, []);
  const selecionar = (a: Atendimento) => {
    setSnapshot(a);
    definirId(a.id);
  };
  const fechar = () => definirId(null);

  // Ação de estado no painel (atender, devolver, transferir): a conversa
  // fica aberta e a lista + contadores revalidam — o cabeçalho passa a
  // refletir o novo estado sem o operador reabrir.
  const aoConcluirAcao = () => {
    void queryClient.invalidateQueries({ queryKey: ["atendimentos"] });
    void queryClient.invalidateQueries({ queryKey: ["contadores"] });
  };

  async function marcarNaoLida(atendimentoId: number) {
    const r = await marcarAtendimentoNaoLidoAction(atendimentoId);
    if (!r.ok) {
      toast.error(r.error);
      return;
    }
    // O badge vem calculado no servidor — revalida só a fila.
    queryClient.invalidateQueries({ queryKey: ["atendimentos"] });
  }

  // --- largura da coluna ---------------------------------------------------
  const { largura, alcaProps } = useColunaRedimensionavel("atd-largura-lista", LIMITES_LISTA);

  // `FiltrosFila` é o parâmetro (opcional) de `getAtendimentos`; aqui sempre vem.
  const q = filtros?.q;

  const vazio =
    atendimentos.length === 0 ? (
      <div className="m-3 rounded-lg border border-dashed p-6 text-center text-muted-foreground">
        {q ? (
          <>
            <SearchX className="mx-auto mb-2 size-6 opacity-40" aria-hidden />
            <p className="font-medium">Nada encontrado para “{q}”</p>
            <p className="mt-1 text-sm">Busque por nome, telefone ou protocolo.</p>
          </>
        ) : (
          <>
            <p className="font-medium">Nenhum atendimento nessa caixa</p>
            <p className="mt-1 text-sm">
              {tipo === "grupos"
                ? "Atendimentos de grupos serão habilitados em uma versão futura."
                : "Quando uma mensagem nova chegar, ela aparece aqui automaticamente."}
            </p>
          </>
        )}
      </div>
    ) : null;

  return (
    <div className="flex min-h-0 flex-1 gap-0 lg:gap-1">
      <div
        className="@container flex w-full min-w-0 flex-col overflow-hidden rounded-lg border lg:w-(--largura-lista) lg:shrink-0"
        style={{ "--largura-lista": `${largura}px` } as React.CSSProperties}
      >
        <ListaToolbar
          q={q}
          modo={modo}
          onModo={setModo}
          algumAberto={algumAberto}
          onAlternarTodos={alternarTodos}
        />
        {vazio ?? (
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {grupos.map((g) => (
              <GrupoFila
                key={g.id}
                grupo={g}
                aberto={estaAberto(g.id, g.abertoPorPadrao)}
                onAlternar={alternarGrupo}
              >
                {g.itens.map((a) => (
                  <CardAtendimento
                    key={a.id}
                    atendimento={a}
                    selecionado={ativoId === a.id}
                    departamentoNome={
                      a.departamento_id != null ? nomeDepartamento.get(a.departamento_id) : null
                    }
                    onSelecionar={selecionar}
                    onMarcarNaoLida={(id) => void marcarNaoLida(id)}
                  />
                ))}
              </GrupoFila>
            ))}
          </ul>
        )}
      </div>

      {/* Alça entre lista e conversa — só desktop. Arrastar pra esquerda
          encolhe a lista (mín. 320px) e a conversa fica com o resto. */}
      <AlcaColuna alcaProps={alcaProps} />

      {/* Coluna da conversa — só desktop. `w-0` (e não só `min-w-0`): a
          largura intrínseca do drawer (barra de ações sem quebra) subia pela
          cadeia de flex até o <main> do app-shell, que não tem min-w-0 e
          crescia além da viewport — com a lista em 300px cabia, em 560 não.
          Com largura declarada zero a coluna não contribui pro min-content e
          fica só com a sobra do flex. */}
      <div className="hidden w-0 min-w-0 flex-1 overflow-hidden rounded-lg border lg:flex">
        {ativo && isDesktop ? (
          <AtendimentoDrawer
            key={ativo.id}
            atendimento={ativo}
            onClose={fechar}
            onAcaoConcluida={aoConcluirAcao}
            modo="painel"
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center text-muted-foreground">
            <Headphones className="size-8 opacity-40" />
            <p className="text-sm">
              {ativoId && !ativo
                ? "Essa conversa não está nesta caixa. Escolha outra na fila ao lado."
                : "Escolha uma conversa na fila ao lado."}
            </p>
          </div>
        )}
      </div>

      {/* Mobile mantém o overlay. */}
      {ativo && isDesktop === false && (
        <div className="lg:hidden">
          <AtendimentoDrawer
            key={ativo.id}
            atendimento={ativo}
            onClose={fechar}
            onAcaoConcluida={aoConcluirAcao}
          />
        </div>
      )}
    </div>
  );
}

import type { AtendenteStatus, Atendimento, Departamento } from "@/lib/api";

import { rotuloDonoCelular } from "./timeline";

/**
 * Agrupamento da fila (inbox agrupado 2026-09) — puro, sem React.
 *
 * Roda no cliente sobre a página já carregada (≤50 itens): a lista continua
 * vindo ordenada por `last_message_at` do servidor, e o agrupamento só a
 * reparte. Contagem por grupo é da página, não da empresa — o total global
 * continua sendo o do rail (`/contadores`).
 */

export type ModoAgrupamento = "status" | "departamento" | "responsavel";

export const MODOS_AGRUPAMENTO: { valor: ModoAgrupamento; rotulo: string }[] = [
  { valor: "status", rotulo: "Status" },
  { valor: "departamento", rotulo: "Departamento" },
  { valor: "responsavel", rotulo: "Responsável" },
];

export interface Grupo {
  /** Estável entre renders: chave do estado aberto/fechado (`status:meus`). */
  id: string;
  nome: string;
  /** Classe do ponto colorido — só tokens do tema. */
  ponto: string;
  /** O que o operador vê no hover do cabeçalho. */
  ajuda?: string;
  itens: Atendimento[];
  naoLidas: number;
  /** Fechado por padrão = o que a IA já está cuidando (não pede ação). */
  abertoPorPadrao: boolean;
}

export interface ContextoAgrupamento {
  userId: string;
  departamentos: Departamento[];
  atendentes: AtendenteStatus[];
}

type ChaveStatus =
  | "perdida"
  | "meus"
  | "humano"
  | "fila"
  | "andamento"
  | "ia"
  | "resolvida"
  | "abandonada"
  | "outros";

/**
 * Ordem fixa dos grupos por status: do que exige ação ao que já está
 * resolvido. Os grupos vazios não aparecem.
 */
const GRUPOS_STATUS: Record<
  ChaveStatus,
  Omit<Grupo, "id" | "itens" | "naoLidas">
> = {
  perdida: {
    nome: "Resposta não enviada",
    ponto: "bg-destructive",
    ajuda: "A resposta esgotou as tentativas de envio — o cliente não recebeu nada.",
    abertoPorPadrao: true,
  },
  meus: {
    nome: "Meus atendimentos",
    ponto: "bg-brand-primary",
    ajuda: "Conversas atribuídas a você.",
    abertoPorPadrao: true,
  },
  humano: {
    nome: "Humano solicitado",
    ponto: "bg-warning",
    ajuda: "A IA transferiu para um setor e ninguém assumiu.",
    abertoPorPadrao: true,
  },
  fila: {
    nome: "Aguardando atendimento",
    ponto: "bg-warning",
    ajuda: "Sem automação (número bloqueado ou conexão manual) e sem atendente.",
    abertoPorPadrao: true,
  },
  andamento: {
    nome: "Em atendimento",
    ponto: "bg-brand-secondary",
    ajuda: "Outro atendente está na conversa.",
    abertoPorPadrao: false,
  },
  ia: {
    nome: "Com a IA",
    ponto: "bg-success",
    ajuda: "A IA responde a próxima mensagem.",
    abertoPorPadrao: false,
  },
  resolvida: {
    nome: "Resolvidas",
    ponto: "bg-muted-foreground/40",
    abertoPorPadrao: true,
  },
  abandonada: {
    nome: "Abandonadas",
    ponto: "bg-muted-foreground/40",
    abertoPorPadrao: true,
  },
  outros: {
    nome: "Outros",
    ponto: "bg-muted-foreground/40",
    abertoPorPadrao: true,
  },
};

const ORDEM_STATUS: ChaveStatus[] = [
  "perdida",
  "meus",
  "humano",
  "fila",
  "andamento",
  "ia",
  "resolvida",
  "abandonada",
  "outros",
];

function ativo(a: Atendimento): boolean {
  return a.status === "aguardando" || a.status === "em_andamento";
}

/**
 * Primeira regra que casar. A ordem espelha a de `derivar_situacao` no
 * backend (fechado → dono humano → falha nossa → fila → IA), com um grupo a
 * mais na frente: o que é MEU vence tudo que está aberto, porque é a
 * carteira do operador.
 */
function chaveStatus(a: Atendimento, userId: string): ChaveStatus {
  if (a.situacao === "resolvida") return "resolvida";
  if (a.situacao === "abandonada") return "abandonada";
  if (a.situacao === "resposta_perdida") return "perdida";
  if (ativo(a) && a.assigned_to_user_id === userId) return "meus";
  if (a.situacao === "aguardando_humano") return "humano";
  if (a.situacao === "em_atendimento") return "andamento";
  if (a.situacao === "com_ia") return "ia";
  if (a.situacao === "sem_automacao") return "fila";
  return "outros";
}

function somarNaoLidas(itens: Atendimento[]): number {
  return itens.reduce((n, a) => n + a.nao_lidas, 0);
}

function agruparPorStatus(itens: Atendimento[], userId: string): Grupo[] {
  const baldes = new Map<ChaveStatus, Atendimento[]>();
  for (const a of itens) {
    const k = chaveStatus(a, userId);
    const balde = baldes.get(k);
    if (balde) balde.push(a);
    else baldes.set(k, [a]);
  }
  return ORDEM_STATUS.flatMap((k) => {
    const lista = baldes.get(k);
    if (!lista) return [];
    return [
      {
        id: `status:${k}`,
        ...GRUPOS_STATUS[k],
        itens: lista,
        naoLidas: somarNaoLidas(lista),
      },
    ];
  });
}

/**
 * Agrupa por uma chave livre (departamento, responsável), ordenando os
 * grupos pelo nome e deixando o "sem" por último.
 */
function agruparPorChave(
  itens: Atendimento[],
  opts: {
    prefixo: string;
    chave: (a: Atendimento) => string | null;
    nome: (chave: string) => string;
    nomeSem: string;
    ponto: string;
    primeiro?: string | null;
  }
): Grupo[] {
  const baldes = new Map<string | null, Atendimento[]>();
  for (const a of itens) {
    const k = opts.chave(a);
    const balde = baldes.get(k);
    if (balde) balde.push(a);
    else baldes.set(k, [a]);
  }
  const comChave = [...baldes.entries()]
    .filter((e): e is [string, Atendimento[]] => e[0] !== null)
    .map(([k, lista]) => ({ k, nome: opts.nome(k), lista }))
    .sort((x, y) => {
      // O grupo do próprio operador vem primeiro; o resto, por nome.
      if (opts.primeiro && x.k === opts.primeiro) return -1;
      if (opts.primeiro && y.k === opts.primeiro) return 1;
      return x.nome.localeCompare(y.nome, "pt-BR");
    });
  const grupos: Grupo[] = comChave.map(({ k, nome, lista }) => ({
    id: `${opts.prefixo}:${k}`,
    nome,
    ponto: opts.ponto,
    itens: lista,
    naoLidas: somarNaoLidas(lista),
    abertoPorPadrao: true,
  }));
  const sem = baldes.get(null);
  if (sem) {
    grupos.push({
      id: `${opts.prefixo}:sem`,
      nome: opts.nomeSem,
      ponto: "bg-muted-foreground/40",
      itens: sem,
      naoLidas: somarNaoLidas(sem),
      abertoPorPadrao: true,
    });
  }
  return grupos;
}

export function agruparAtendimentos(
  itens: Atendimento[],
  modo: ModoAgrupamento,
  ctx: ContextoAgrupamento
): Grupo[] {
  if (modo === "status") return agruparPorStatus(itens, ctx.userId);

  if (modo === "departamento") {
    const nomes = new Map(ctx.departamentos.map((d) => [String(d.id), d.nome]));
    return agruparPorChave(itens, {
      prefixo: "departamento",
      chave: (a) => (a.departamento_id == null ? null : String(a.departamento_id)),
      nome: (k) => nomes.get(k) ?? `Departamento #${k}`,
      nomeSem: "Sem departamento",
      ponto: "bg-brand-secondary",
    });
  }

  const nomes = new Map(
    ctx.atendentes.map((a) => [a.user_id, a.nome || a.email || a.user_id])
  );
  return agruparPorChave(itens, {
    prefixo: "responsavel",
    chave: (a) => a.assigned_to_user_id,
    nome: (k) =>
      k === ctx.userId
        ? `${nomes.get(k) ?? "Você"} (você)`
        : (rotuloDonoCelular(k) ?? nomes.get(k) ?? "Atendente"),
    nomeSem: "Sem responsável",
    ponto: "bg-brand-primary",
    primeiro: ctx.userId,
  });
}

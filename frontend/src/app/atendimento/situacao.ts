import type { SituacaoAtendimento } from "@/lib/api";

/**
 * Rótulo e cor de cada situação — fonte única do painel.
 *
 * Antes disto, `STATUS_LABEL` e `statusVariant` estavam duplicados em
 * `atendimento-list.tsx` e `atendimento-drawer.tsx`, e triplicados no Kotlin.
 * As cópias já haviam divergido: o web dizia "Em andamento" onde o app dizia
 * "Em atendimento", para o mesmo estado.
 *
 * As cores seguem o Chatvolt, que é a referência pedida: âmbar = precisa de
 * gente, verde = resolvida/saudável, vermelho reservado ao que exige ação.
 */
export const SITUACAO_LABEL: Record<SituacaoAtendimento, string> = {
  resposta_perdida: "Resposta não enviada",
  com_ia: "Com a IA",
  aguardando_humano: "Aguardando humano",
  em_atendimento: "Em atendimento",
  sem_automacao: "Sem automação",
  resolvida: "Resolvida",
  abandonada: "Abandonada",
};

/**
 * Classes Tailwind por situação.
 *
 * `sem_automacao` é deliberadamente CINZA e não vermelho: não é erro — é
 * configuração (whitelist ou conexão em modo manual). Pintar de vermelho faria
 * o operador tentar "consertar" algo que está como foi pedido. O que ele precisa
 * saber é apenas que ninguém automático vai responder ali.
 */
export const SITUACAO_CLASSE: Record<SituacaoAtendimento, string> = {
  // O ÚNICO vermelho entre as situações: é o estado em que o cliente ficou sem
  // retorno por falha nossa, e não por desenho.
  resposta_perdida:
    "border-red-500/50 bg-red-500/15 text-red-700 dark:text-red-300",
  com_ia: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  aguardando_humano: "border-amber-500/50 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  em_atendimento: "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  sem_automacao: "border-foreground/20 bg-foreground/5 text-muted-foreground",
  resolvida: "border-emerald-500/30 bg-transparent text-muted-foreground",
  abandonada: "border-foreground/15 bg-transparent text-muted-foreground",
};

/**
 * Explicação no hover. O rótulo cabe no card; o porquê, não.
 *
 * Vale principalmente para "Sem automação", que é o estado novo e o menos
 * óbvio — sem esta frase o operador não tem como saber que o silêncio é
 * intencional.
 */
export const SITUACAO_AJUDA: Record<SituacaoAtendimento, string> = {
  resposta_perdida:
    "A resposta esgotou as tentativas de envio e o cliente não recebeu nada. Reenvie pelo drawer.",
  com_ia: "A IA responde a próxima mensagem deste cliente.",
  aguardando_humano:
    "A IA transferiu para um setor e ninguém assumiu. Precisa de atendente.",
  em_atendimento: "Um operador assumiu; a IA está calada nesta conversa.",
  sem_automacao:
    "Nada automático responde aqui — número na lista de bloqueio ou conexão em modo manual.",
  resolvida: "Atendimento encerrado.",
  abandonada: "Encerrado sem resolução.",
};

/**
 * Ponto colorido por situação — versão compacta pro card da fila estreita.
 *
 * Só tokens do tema (destructive/warning/success/brand-primary/muted), nunca
 * paleta crua: o portão de métricas de UI conta cor-com-número e reprova o PR
 * se a contagem subir. O significado segue o SITUACAO_CLASSE: vermelho só na
 * resposta perdida; resolvida/abandonada/sem automação são neutros.
 */
export const SITUACAO_PONTO: Record<SituacaoAtendimento, string> = {
  resposta_perdida: "bg-destructive",
  com_ia: "bg-success",
  aguardando_humano: "bg-warning",
  em_atendimento: "bg-brand-primary",
  sem_automacao: "bg-muted-foreground/40",
  resolvida: "bg-muted-foreground/40",
  abandonada: "bg-muted-foreground/40",
};

/** Ponto por prioridade — só urgente/alta merecem tinta no card compacto. */
export const PRIORIDADE_PONTO: Record<string, string> = {
  urgente: "bg-destructive",
  alta: "bg-warning",
};

/**
 * Chip de automação do card agrupado (inbox agrupado 2026-09) — a versão
 * com texto do `SITUACAO_PONTO`, e com o MESMO significado: vermelho só na
 * resposta perdida; sem automação/resolvida/abandonada são neutros. Só
 * tokens do tema, pelo mesmo portão de métricas.
 */
export const SITUACAO_CHIP: Record<SituacaoAtendimento, string> = {
  resposta_perdida: "bg-destructive/10 text-destructive",
  com_ia: "bg-success/10 text-success",
  aguardando_humano: "bg-warning/10 text-warning",
  em_atendimento: "bg-brand-primary/10 text-brand-primary",
  sem_automacao: "bg-muted text-muted-foreground",
  resolvida: "bg-muted text-muted-foreground",
  abandonada: "bg-muted text-muted-foreground",
};

/** `99+` acima de 99, como no Chatvolt — número maior não muda a decisão. */
export function formatarNaoLidas(n: number): string {
  return n > 99 ? "99+" : String(n);
}

export type FaixaEspera = "normal" | "aviso" | "critico";

/**
 * Faixa do chip "Sem resposta há X": até 1 h é rotina, de 1 a 4 h pede
 * atenção, acima de 4 h é o cliente falando sozinho. Não é SLA por
 * departamento (`tolerancia_atend_inativo_min` segue sem uso) — é um
 * limiar fixo pra fila inteira, escolhido pra separar o dia do turno.
 */
export function faixaEspera(iso: string, agora: number = Date.now()): FaixaEspera {
  const min = (agora - new Date(iso).getTime()) / 60_000;
  if (min >= 240) return "critico";
  if (min >= 60) return "aviso";
  return "normal";
}

export const FAIXA_ESPERA_CLASSE: Record<FaixaEspera, string> = {
  normal: "bg-muted text-muted-foreground",
  aviso: "bg-warning/10 text-warning",
  critico: "bg-destructive/10 text-destructive",
};

/**
 * Tempo de espera legível: "agora", "12min", "3h 05min", "2d". Diferente do
 * `formatRelative` do card (que arredonda): aqui minutos ficam visíveis até
 * o dia, porque é a medida do que o cliente já esperou.
 */
export function formatarEspera(iso: string, agora: number = Date.now()): string {
  const min = Math.max(0, Math.floor((agora - new Date(iso).getTime()) / 60_000));
  if (min < 1) return "agora";
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ${String(min % 60).padStart(2, "0")}min`;
  return `${Math.floor(h / 24)}d`;
}

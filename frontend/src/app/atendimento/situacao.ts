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

/** `99+` acima de 99, como no Chatvolt — número maior não muda a decisão. */
export function formatarNaoLidas(n: number): string {
  return n > 99 ? "99+" : String(n);
}

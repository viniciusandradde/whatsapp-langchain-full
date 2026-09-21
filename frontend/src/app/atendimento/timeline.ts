import type { AtendimentoMensagem } from "@/lib/api";

/**
 * Timeline da conversa em itens renderizáveis (conversa compacta, 2026-09).
 *
 * Funções PURAS, sem React: cada row de `message_queue` vira zero ou mais
 * bolhas (a fala do cliente, a mídia, a resposta, o erro), e o que antes era
 * decidido dentro do JSX do drawer (qual marker do worker é qual, o que pode
 * ser reprocessado, qual lado da bolha) fica aqui, testável.
 *
 * Dois arranjos que o JSX antigo não fazia:
 *
 * - **Bolhas consecutivas do mesmo remetente viram UM grupo** com um só
 *   cabeçalho ("Cliente · 15:08"), em vez de repetir data completa e
 *   remetente em cada balão. O grupo quebra quando muda o lado, o dia ou
 *   quando passa mais de `INTERVALO_GRUPO_MIN` entre uma fala e a próxima.
 * - **Markers repetidos do worker viram UM aviso** por sequência: a lista de
 *   bloqueio da IA gravava "ninguém respondeu" em cada mensagem do cliente,
 *   e uma sequência de três "beleza / ok / obrigado" empilhava três avisos
 *   de linha inteira. Agora é um chip por sequência, e as mensagens que ele
 *   cobre vão junto (é por elas que o "Reprocessar com IA" existe).
 */

export type Lado = "in" | "out";

export type Remetente = "Cliente" | "IA" | "Operador" | "Sistema";

export interface BolhaTexto {
  tipo: "bolha";
  kind: "text";
  chave: string;
  lado: Lado;
  remetente: Remetente;
  msg: AtendimentoMensagem;
  text: string;
  /** Apagada para todos (mig 172): itálico, sem menu. */
  apagada?: boolean;
  /** Bolha de erro do processamento: inerte, com a frase fixa. */
  erro?: boolean;
  /** Reprocesso disponível (row `failed`) — o backend revalida. */
  podeReprocessar?: boolean;
}

export interface BolhaMidia {
  tipo: "bolha";
  kind: "media";
  chave: string;
  lado: Lado;
  remetente: Remetente;
  msg: AtendimentoMensagem;
  /** URL do proxy do Next — o conteúdo NÃO vem na lista. */
  mediaUrl: string;
  mediaType: string | null;
  caption?: string;
  /** Nome real do arquivo (migs 164/186); sem ele a bolha rotula pelo tipo. */
  nome?: string | null;
  /** Só inbound de áudio (mig 169): habilita a transcrição no painel. */
  transcrevivel?: boolean;
}

export type Bolha = BolhaTexto | BolhaMidia;

export interface Nota {
  tipo: "nota";
  chave: string;
  msg: AtendimentoMensagem;
}

export type VarianteAviso =
  | "whitelist"
  | "manual"
  | "handoff"
  | "fila"
  | "sem_agente"
  | "limite_plano"
  | "conversa_automatica";

export interface AvisoIa {
  tipo: "aviso_ia";
  chave: string;
  variante: VarianteAviso;
  /** Mensagens do cliente cobertas por este aviso, na ordem. */
  mensagens: AtendimentoMensagem[];
  /** Reprocesso oferecido (modo manual / lista de bloqueio). */
  podeReprocessar: boolean;
}

export interface GrupoBolhas {
  tipo: "grupo";
  chave: string;
  lado: Lado;
  remetente: Remetente;
  /** `created_at` da primeira bolha — é o horário do cabeçalho. */
  inicio: string | null;
  bolhas: Bolha[];
}

export type ItemTimeline = GrupoBolhas | Nota | AvisoIa;

/** Minutos de silêncio que quebram um grupo mesmo com o mesmo remetente. */
export const INTERVALO_GRUPO_MIN = 30;

const MARKERS: ReadonlyArray<readonly [string, VarianteAviso | null]> = [
  ["[handoff humano", "handoff"],
  ["[modo manual", "manual"],
  ["[whitelist", "whitelist"],
  ["[fila do departamento", "fila"],
  ["[IA sem agente cadastrado", "sem_agente"],
  // ADR-005 D5: a empresa passou dos atendimentos do mês do plano — a IA
  // para, o humano continua. Upgrade + reprocessar traz a IA de volta.
  ["[limite de atendimentos do plano", "limite_plano"],
  // Robô × robô (shared/conversa_automatica.py): o outro lado é uma URA ou
  // assistente virtual respondendo em segundos; a IA parou para não ficar
  // em loop. Não reprocessável: dentro da janela cairia na mesma guarda.
  ["[conversa automática", "conversa_automatica"],
  // O cliente escreveu de novo enquanto o modelo pensava; o turno seguinte
  // respondeu tudo. Não é aviso — a fala do cliente já está visível.
  ["[resposta superada", null],
];

/** Marker interno do worker no `response` → variante do aviso (ou `null`
 *  quando é marker sem aviso). `undefined` = não é marker. */
export function variantePorMarker(
  response: string | null | undefined
): VarianteAviso | null | undefined {
  if (!response) return undefined;
  for (const [prefixo, variante] of MARKERS) {
    if (response.startsWith(prefixo)) return variante;
  }
  return undefined;
}

export const AVISO_IA_TEXTO: Record<
  VarianteAviso,
  { chip: string; titulo: string; motivo: string }
> = {
  whitelist: {
    chip: "IA bloqueada",
    titulo: "IA bloqueada para este contato",
    motivo:
      "O número está na lista de bloqueio da IA: nenhuma conexão responde automaticamente. Ninguém respondeu a estas mensagens.",
  },
  manual: {
    chip: "IA desligada",
    titulo: "IA desligada nesta conexão",
    motivo:
      "A conexão está em modo manual, então o agente não respondeu. Ninguém respondeu a estas mensagens.",
  },
  handoff: {
    chip: "Operador respondendo",
    titulo: "Agente pausado",
    motivo:
      "Um operador assumiu a conversa; a IA fica calada até ser devolvida.",
  },
  fila: {
    chip: "Na fila do setor",
    titulo: "Encaminhado ao setor",
    motivo:
      "A IA transferiu para um departamento e a conversa aguarda um atendente assumir.",
  },
  sem_agente: {
    chip: "Sem agente de IA",
    titulo: "Conexão sem agente cadastrado",
    motivo:
      "A conexão está em modo IA mas não tem agente configurado. Ninguém respondeu a estas mensagens.",
  },
  conversa_automatica: {
    chip: "Robô do outro lado",
    titulo: "Parece um atendimento automático do outro lado",
    motivo:
      "As últimas mensagens deste contato têm cara de menu automático (banco, operadora, assistente virtual) e chegaram segundos depois da resposta da IA. Para não ficar em loop, o agente parou de responder. Volta sozinho quando o contato mandar uma mensagem normal depois de alguns minutos. Se for um número de empresa que o próprio negócio usa, coloque-o na lista de bloqueio da IA.",
  },
  limite_plano: {
    chip: "IA pausada pelo plano",
    titulo: "Limite de atendimentos do plano atingido",
    motivo:
      "A empresa passou do número de atendimentos por mês do plano. O agente de IA fica pausado até o próximo mês (ou até um upgrade); os atendentes continuam recebendo as conversas. Ninguém respondeu a estas mensagens.",
  },
};

/** Quem mandou a row de saída. `normalized_input` de envio manual é
 *  `manual:<user_id>` (`shared/outbound.py`); o resto veio do agente. */
export function remetenteDaResposta(m: AtendimentoMensagem): Remetente {
  const n = m.normalized_input ?? "";
  if (n.startsWith("manual:system:")) return "Sistema";
  if (n.startsWith("manual:")) return "Operador";
  return "IA";
}

function bolhasDaRow(m: AtendimentoMensagem, atendimentoId: number): Bolha[] {
  const bolhas: Bolha[] = [];

  if (m.media_disponivel || m.media_url) {
    bolhas.push({
      tipo: "bolha",
      kind: "media",
      chave: `${m.id}-in-media`,
      lado: "in",
      remetente: "Cliente",
      msg: m,
      mediaUrl: m.media_url ?? `/api/proxy/midia/${atendimentoId}/${m.id}?lado=in`,
      mediaType: m.media_type ?? null,
      caption: m.incoming_message || undefined,
      nome: m.media_filename ?? null,
      transcrevivel: (m.media_type ?? "").startsWith("audio/"),
    });
  } else if (m.incoming_message) {
    bolhas.push({
      tipo: "bolha",
      kind: "text",
      chave: `${m.id}-in`,
      lado: "in",
      remetente: "Cliente",
      msg: m,
      text: m.incoming_message,
    });
  }

  const marker = variantePorMarker(m.response);
  const ehMarker = marker !== undefined;
  const remetente = remetenteDaResposta(m);

  // Mídia enviada PELO OPERADOR (mig 146): fica em `response_media_url`, e
  // `response` é a legenda — não uma segunda bolha de texto.
  if (m.response_media_disponivel || m.response_media_url) {
    bolhas.push({
      tipo: "bolha",
      kind: "media",
      chave: `${m.id}-out-media`,
      lado: "out",
      remetente,
      msg: m,
      mediaUrl:
        m.response_media_url ?? `/api/proxy/midia/${atendimentoId}/${m.id}?lado=out`,
      mediaType: m.response_media_type ?? null,
      caption: !ehMarker && m.response ? m.response : undefined,
      nome: m.response_media_filename ?? null,
    });
  } else if (m.response && !ehMarker) {
    // Apagada para todos (mig 172): mostrar o texto faria o painel afirmar
    // que a mensagem foi entregue. Fica no banco para auditoria.
    bolhas.push(
      m.response_apagada
        ? {
            tipo: "bolha",
            kind: "text",
            chave: `${m.id}-out`,
            lado: "out",
            remetente,
            msg: m,
            text: "Mensagem apagada",
            apagada: true,
          }
        : {
            tipo: "bolha",
            kind: "text",
            chave: `${m.id}-out`,
            lado: "out",
            remetente,
            msg: m,
            text: m.response,
          }
    );
  }

  if (m.error) {
    // NUNCA o detalhe técnico como texto visível — frase fixa pro operador;
    // o erro real fica no `docker logs worker`.
    bolhas.push({
      tipo: "bolha",
      kind: "text",
      chave: `${m.id}-erro`,
      lado: "out",
      remetente: "Sistema",
      msg: m,
      text: "Falha ao processar essa mensagem. Tente reenviar ou entre em contato com o suporte.",
      erro: true,
      podeReprocessar: m.status === "failed",
    });
  }

  return bolhas;
}

function diaLocal(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function minutosEntre(a: string | null, b: string | null): number {
  if (!a || !b) return Infinity;
  return Math.abs(new Date(b).getTime() - new Date(a).getTime()) / 60_000;
}

/**
 * Rows → itens da timeline (na ordem recebida, que já é cronológica).
 *
 * Nota interna quebra qualquer grupo (ocupa a largura toda). O aviso da IA
 * entra DEPOIS do grupo das falas que ele cobre, e sequências de rows com o
 * MESMO marker se fundem num aviso só.
 */
export function montarTimeline(
  mensagens: AtendimentoMensagem[],
  atendimentoId: number
): ItemTimeline[] {
  const itens: ItemTimeline[] = [];
  let grupo: GrupoBolhas | null = null;
  let aviso: AvisoIa | null = null;

  const fecharGrupo = () => {
    if (grupo) itens.push(grupo);
    grupo = null;
  };
  const fecharAviso = () => {
    if (aviso) itens.push(aviso);
    aviso = null;
  };
  const empurrar = (b: Bolha) => {
    if (
      grupo &&
      grupo.lado === b.lado &&
      grupo.remetente === b.remetente &&
      diaLocal(grupo.inicio) === diaLocal(b.msg.created_at) &&
      minutosEntre(grupo.bolhas[grupo.bolhas.length - 1]?.msg.created_at ?? null, b.msg.created_at) <=
        INTERVALO_GRUPO_MIN
    ) {
      grupo.bolhas.push(b);
      return;
    }
    fecharGrupo();
    grupo = {
      tipo: "grupo",
      chave: `g-${b.chave}`,
      lado: b.lado,
      remetente: b.remetente,
      inicio: b.msg.created_at,
      bolhas: [b],
    };
  };

  for (const m of mensagens) {
    if (m.interna && m.response) {
      fecharGrupo();
      fecharAviso();
      itens.push({ tipo: "nota", chave: `n-${m.id}`, msg: m });
      continue;
    }

    const variante = variantePorMarker(m.response);
    const bolhas = bolhasDaRow(m, atendimentoId);

    // Esta row não continua a sequência do aviso pendente: o grupo das falas
    // cobertas fecha e o aviso entra logo abaixo dele — colado no que cobre.
    if (aviso && aviso.variante !== variante) {
      fecharGrupo();
      fecharAviso();
    }

    for (const b of bolhas) {
      // Resposta de verdade (ou mídia do operador) encerra o aviso; a fala do
      // cliente da MESMA row já entrou no grupo antes.
      if (b.lado === "out" && aviso) {
        fecharGrupo();
        fecharAviso();
      }
      empurrar(b);
    }

    if (variante) {
      if (aviso && aviso.variante === variante) {
        aviso.mensagens.push(m);
      } else {
        aviso = {
          tipo: "aviso_ia",
          chave: `a-${m.id}`,
          variante,
          mensagens: [m],
          podeReprocessar:
            variante === "manual" ||
            variante === "whitelist" ||
            variante === "limite_plano",
        };
      }
    }
  }
  fecharGrupo();
  fecharAviso();
  return itens;
}

const FMT_HORA = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });
const FMT_DIA = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });
const FMT_DIA_ANO = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/**
 * Horário compacto do cabeçalho do grupo: só a hora no mesmo dia, "17/09 ·
 * 15:09" em dia anterior do mesmo ano, e com o ano quando virou o ano.
 * `agora` é injetável pra teste e pro tick do relógio.
 */
export function formatarHoraCurta(iso: string | null, agora: Date = new Date()): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hora = FMT_HORA.format(d);
  if (diaLocal(iso) === diaLocal(agora.toISOString())) return hora;
  const dia = d.getFullYear() === agora.getFullYear() ? FMT_DIA.format(d) : FMT_DIA_ANO.format(d);
  return `${dia} · ${hora}`;
}

/** Data e hora completas, pro `title` da bolha e pro menu de contexto. */
export function formatarDataHoraCompleta(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

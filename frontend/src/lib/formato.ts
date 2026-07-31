/**
 * Formatação de texto e data — um lugar só.
 *
 * Motivo: a auditoria contou **50 plurais escritos como `(s)`** ("9 pasta(s)",
 * "61 permissão(ões)", "1 user(s)") e **5 formas diferentes** de formatar data
 * (`toLocaleString("pt-BR")`, `toLocaleString()` sem locale, `toLocaleDateString`,
 * `toLocaleTimeString` com `hour12`, e uma com fração). O mesmo dashboard
 * chegava a mostrar "264.3m" num tile e "4h24m" na tabela logo abaixo.
 */

const FUSO = "America/Sao_Paulo";

/**
 * Plural de verdade, com a forma irregular quando ela existe.
 *
 * @example plural(1, "pasta") // "1 pasta"
 * @example plural(9, "pasta") // "9 pastas"
 * @example plural(2, "documento", "documentos") // "2 documentos"
 */
export function plural(n: number, singular: string, pluralForma?: string) {
  const palavra = n === 1 ? singular : (pluralForma ?? `${singular}s`);
  return `${n.toLocaleString("pt-BR")} ${palavra}`;
}

/**
 * Data e hora: "30/07/2026 18:22".
 *
 * Aceita nulo e devolve travessão. Sem isso cada tela inventava o próprio
 * `?? "—"` antes de chamar — e algumas esqueciam, imprimindo "Invalid Date".
 */
export function dataHora(v: string | number | Date | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return new Date(v).toLocaleString("pt-BR", {
    timeZone: FUSO,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Só a data: "30/07/2026". Nulo vira travessão, como em `dataHora`. */
export function data(v: string | number | Date | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return new Date(v).toLocaleDateString("pt-BR", {
    timeZone: FUSO,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/**
 * Duração legível a partir de minutos.
 *
 * O dashboard mostrava "264.3m" — que são 4h24m. Minuto serve até uma hora;
 * acima disso o operador precisa converter de cabeça.
 */
export function duracaoMin(min: number): string {
  if (!Number.isFinite(min) || min < 0) return "—";
  if (min < 1) return "menos de 1 min";
  if (min < 60) return `${Math.round(min)} min`;
  const horas = Math.floor(min / 60);
  const resto = Math.round(min % 60);
  if (horas < 24) return resto ? `${horas}h${String(resto).padStart(2, "0")}` : `${horas}h`;
  const dias = Math.floor(horas / 24);
  const h = horas % 24;
  return h ? `${dias}d ${h}h` : `${dias}d`;
}

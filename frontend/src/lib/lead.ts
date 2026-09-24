/**
 * Classificação do lead (mig 201) — espelho de `ESTAGIOS_FUNIL` e
 * `TEMPERATURAS` em `shared/cliente.py`. A ordem é a do funil.
 *
 * Cores só por tokens semânticos (`brand-*` é a cor da marca da empresa, não
 * significado — na empresa 1 é branco).
 */

export const ESTAGIOS_FUNIL = [
  { valor: "lead", rotulo: "Lead", curto: "Lead", dica: "Primeiro contato, interesse ainda vago" },
  { valor: "mql", rotulo: "Lead qualificado (marketing)", curto: "MQL", dica: "Mostrou interesse real no produto ou serviço" },
  { valor: "sql", rotulo: "Lead qualificado (vendas)", curto: "SQL", dica: "Pronto para falar de compra: preço, condições, prazo" },
  { valor: "oportunidade", rotulo: "Oportunidade", curto: "Oportunidade", dica: "Pediu proposta ou está negociando" },
  { valor: "cliente", rotulo: "Cliente", curto: "Cliente", dica: "Fechou negócio" },
  { valor: "perdido", rotulo: "Perdido", curto: "Perdido", dica: "Desistiu ou não tem interesse" },
] as const;

export type EstagioFunil = (typeof ESTAGIOS_FUNIL)[number]["valor"];

export const TEMPERATURAS = [
  { valor: "frio", rotulo: "Frio", dica: "Curioso, sem urgência" },
  { valor: "morno", rotulo: "Morno", dica: "Interessado, sem prazo definido" },
  { valor: "quente", rotulo: "Quente", dica: "Quer resolver logo, tem orçamento ou prazo" },
] as const;

export type Temperatura = (typeof TEMPERATURAS)[number]["valor"];

export const ESTAGIO_CHIP: Record<EstagioFunil, string> = {
  lead: "bg-muted text-muted-foreground",
  mql: "bg-chart-3/10 text-chart-3",
  sql: "bg-chart-3/15 text-chart-3",
  oportunidade: "bg-warning/10 text-warning",
  cliente: "bg-success/10 text-success",
  perdido: "bg-destructive/10 text-destructive",
};

export const TEMPERATURA_CHIP: Record<Temperatura, string> = {
  frio: "bg-chart-3/10 text-chart-3",
  morno: "bg-warning/10 text-warning",
  quente: "bg-destructive/10 text-destructive",
};

export function rotuloEstagio(v: string | null | undefined, curto = false): string | null {
  const e = ESTAGIOS_FUNIL.find((x) => x.valor === v);
  if (!e) return null;
  return curto ? e.curto : e.rotulo;
}

export function rotuloTemperatura(v: string | null | undefined): string | null {
  return TEMPERATURAS.find((x) => x.valor === v)?.rotulo ?? null;
}

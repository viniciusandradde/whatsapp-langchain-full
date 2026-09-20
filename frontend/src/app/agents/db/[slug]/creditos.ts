/**
 * Tiers de contexto e créditos estimados (ADR-004) — espelho PURO de
 * `src/whatsapp_langchain/shared/contexto.py`.
 *
 * A fonte única é o backend; este arquivo existe para o card calcular os
 * 5 números sem uma chamada por modelo. Se um valor mudar lá, muda aqui,
 * e o teste ad hoc (ver a PR) confere os mesmos casos: Gemini 2.5 Flash em
 * `lite` = 2 créditos, em `extended` = 24.
 *
 * Crédito é unidade de EXIBIÇÃO (1 C = US$ 0,001), não de cobrança.
 */

import type { ModeloCatalogo, PlanoCatalogo, TierContexto } from "@/lib/api";

export const TIERS: Record<TierContexto, number> = {
  lite: 6_000,
  regular: 15_000,
  medium: 25_000,
  large: 35_000,
  extended: 300_000,
};

export const ORDEM: readonly TierContexto[] = ["lite", "regular", "medium", "large", "extended"];

/** Só sinalização visual nesta leva (D3): nada trava. */
export const PREMIUM: ReadonlySet<TierContexto> = new Set(["medium", "large", "extended"]);

export const TIER_PADRAO: TierContexto = "lite";

const CHARS_POR_TOKEN = 4;
const TOKENS_SAIDA_ESTIMADOS = 300;
const USD_POR_CREDITO = 0.001;

export function rotuloTier(tier: TierContexto): string {
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

export function charsParaTokens(chars: number): number {
  return Math.max(1, Math.floor(chars / CHARS_POR_TOKEN));
}

/**
 * Créditos estimados de UMA resposta com o histórico cheio no tier.
 * `null` quando o preço é desconhecido (o card mostra `?`).
 */
export function creditosPorMensagem(
  precoPrompt: number | null,
  precoCompletion: number | null,
  tier: TierContexto
): number | null {
  if (precoPrompt === null || precoCompletion === null) return null;
  const usd =
    charsParaTokens(TIERS[tier]) * precoPrompt + TOKENS_SAIDA_ESTIMADOS * precoCompletion;
  return Math.max(1, Math.ceil(usd / USD_POR_CREDITO));
}

/** O tier cabe na janela do modelo? Sem `context_length` assume que cabe. */
export function cabeNoModelo(modelo: Pick<ModeloCatalogo, "context_length">, tier: TierContexto) {
  if (modelo.context_length === null) return true;
  return charsParaTokens(TIERS[tier]) <= modelo.context_length;
}

/** Valor US$ real da estimativa, pro tooltip do card. */
export function usdPorMensagem(
  precoPrompt: number | null,
  precoCompletion: number | null,
  tier: TierContexto
): number | null {
  if (precoPrompt === null || precoCompletion === null) return null;
  return charsParaTokens(TIERS[tier]) * precoPrompt + TOKENS_SAIDA_ESTIMADOS * precoCompletion;
}

/**
 * Preço de ENTRADA acima disto torna o modelo "premium" (mig 188): só planos
 * com `modelos_premium`. US$ 5/Mtok é onde ficam os modelos de topo
 * (GPT-5 Pro, o1-pro); Opus/Sonnet a US$ 5 ficam liberados. Espelho de
 * `shared/contexto.py::PRECO_PROMPT_PREMIUM`.
 */
export const PRECO_PROMPT_PREMIUM = 5e-6;

export function modeloPremium(modelo: Pick<ModeloCatalogo, "preco_prompt">): boolean {
  return modelo.preco_prompt !== null && modelo.preco_prompt > PRECO_PROMPT_PREMIUM;
}

/** O plano não libera este modelo (o PUT devolveria 402). */
export function modeloBloqueado(
  modelo: Pick<ModeloCatalogo, "preco_prompt">,
  plano: Pick<PlanoCatalogo, "modelos_premium">
): boolean {
  return !plano.modelos_premium && modeloPremium(modelo);
}

/** O plano não libera este tier (o PUT devolveria 402). */
export function tierBloqueado(tier: TierContexto, plano: Pick<PlanoCatalogo, "contexto_max">) {
  return ORDEM.indexOf(tier) > ORDEM.indexOf(plano.contexto_max);
}

export function rotuloPlano(slug: string | null): string {
  return slug ? slug.charAt(0).toUpperCase() + slug.slice(1) : "";
}

export function formatarChars(n: number): string {
  return n.toLocaleString("pt-BR");
}

/**
 * Plano × recurso no painel (ADR-005 leva D) — módulo NEUTRO (sem React).
 *
 * As chaves são as de `plano.features` semeadas nas migrations (059, 122,
 * 134, 177, 188–192); os rótulos espelham `_ROTULO_FEATURE`/`_ROTULO_RECURSO`
 * de `server/dependencies_plano.py` em forma curta, para menu, tabela e
 * toast. Regra do dono (20/09): texto ao usuário final sem termo técnico,
 * sem `_`, sem "pro/pra".
 */

import type { ValorFeaturePlano } from "@/lib/api";

/** Rótulo curto de cada recurso de plano (booleano). */
export const ROTULO_FEATURE: Record<string, string> = {
  calendar: "Integração com o Google Agenda",
  voz: "Voz do agente",
  disparador: "Campanhas, contatos e extensão",
  disparador_media: "Campanhas com mídia",
  webhooks: "Webhooks de saída",
  rbac: "Perfis de acesso personalizados",
  waba: "Conexão pela API oficial da Meta",
  menu_moderno: "Menu moderno com botões do WhatsApp",
  white_label: "Marca própria (nome, logo e cores)",
  transcricao_operador: "Transcrição de áudio para o operador",
  documentos_cliente: "Leitura de documentos enviados pelo cliente",
  imagem_cliente: "Leitura de imagens enviadas pelo cliente",
  fewshot: "Aprendizado com exemplos",
  catalogo_completo: "Catálogo completo de modelos",
  modelos_premium: "Modelos premium",
  csat: "Pesquisa de satisfação",
  resumo_diario: "Resumo diário por WhatsApp",
  bateria_testes: "Bateria de testes do agente",
  observabilidade: "Fila de mensagens e rastreamentos",
  qualidade_ia: "Relatórios de qualidade da IA",
  // Tetos numéricos guardados em `features` (mig 192) e o tier de contexto.
  workflows_max: "Workflows ativos",
  departamentos_max: "Departamentos",
  menus_max: "Menus de chatbot",
  retencao_max_dias: "Retenção do histórico",
  auditoria_dias: "Janela do registro de auditoria",
  contexto_max: "Tamanho máximo do contexto do agente",
};

/** Rótulo de cada limite contado (`limites` do `PlanoEmpresa`). */
export const ROTULO_LIMITE: Record<string, string> = {
  conexoes: "Conexões de WhatsApp",
  usuarios: "Usuários",
  atendimentos_mes: "Atendimentos por mês",
  documentos_kb: "Documentos na base de conhecimento",
  agentes: "Agentes de IA",
  departamentos: "Departamentos",
  workflows: "Workflows ativos",
  menus: "Menus de chatbot",
  orcamento_ia_usd: "Orçamento de IA por mês",
};

export function rotuloFeature(chave: string): string {
  return ROTULO_FEATURE[chave] ?? "Este recurso";
}

/** "free" → "Free". O nome de verdade vem da API quando há um plano em mãos. */
export function rotuloPlano(slug: string | null | undefined): string {
  return slug ? slug.charAt(0).toUpperCase() + slug.slice(1) : "";
}

/**
 * Uma chave está liberada quando o valor é `true`, um teto maior que zero,
 * `null` (= ilimitado) ou um texto (tier). Chave AUSENTE conta como
 * bloqueada — é o mesmo lado para o qual o backend erra (`limite_numerico`).
 */
export function featureLiberada(
  features: Record<string, ValorFeaturePlano> | null | undefined,
  chave: string
): boolean {
  if (!features || !(chave in features)) return false;
  const v = features[chave];
  if (v === null) return true;
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v > 0;
  return v.length > 0;
}

/** Destino do cadeado: o `/billing` abre já explicando o recurso. */
export function linkBilling(chave?: string): string {
  return chave ? `/billing?feature=${encodeURIComponent(chave)}` : "/billing";
}

export function fraseUpgrade(upgrade: string | null | undefined): string {
  return upgrade
    ? `Disponível a partir do plano ${rotuloPlano(upgrade)}.`
    : "Fale com o suporte para ampliar o seu plano.";
}

/** Texto do toast/aviso quando o usuário toca num recurso fora do plano. */
export function mensagemBloqueio(
  chave: string,
  nomePlano: string,
  upgrade: string | null | undefined
): string {
  return `${rotuloFeature(chave)} não está no plano ${nomePlano}. ${fraseUpgrade(upgrade)}`;
}

/** "Ilimitado" em vez de "∞": é o que o cliente lê sem decodificar. */
export function formatarLimite(valor: number | null | undefined, unidade?: string): string {
  if (valor === null || valor === undefined) return "Ilimitado";
  const n = valor.toLocaleString("pt-BR");
  return unidade ? `${n} ${unidade}` : n;
}

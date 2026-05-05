/**
 * Recebe operations capturadas em runtime e produz lista deduplicada
 * + categorizada por entity.
 *
 * Categorização heurística: `getCliente` → cliente; `createCampanha` →
 * campanha; `listAtendimentoMensagens` → atendimento. Strip de
 * verbos comuns (get/list/create/update/delete/find/save/sync).
 */

import type { CapturedOperation, DedupedOperation } from "../types.js";

// Verbos PT (ZigChat usa nomenclatura em português) e EN.
// Ordem importa: primeiro match ganha — verbos mais longos antes dos
// curtos pra evitar match prematuro (ex: "buscar" precisa vir antes
// de "buscar*" se "buscar" for prefixo de outra palavra).
const VERB_PREFIXES = [
  // PT — comuns no ZigChat
  "filtrar",
  "buscar",
  "listar",
  "carregar",
  "criar",
  "atualizar",
  "salvar",
  "deletar",
  "remover",
  "apagar",
  "enviar",
  "marcar",
  "contar",
  "sincronizar",
  "importar",
  "exportar",
  "validar",
  "verificar",
  "limite",
  "aprovar",
  "rejeitar",
  "cancelar",
  "fechar",
  "abrir",
  "transferir",
  "atribuir",
  "ativar",
  "desativar",
  "habilitar",
  "desabilitar",
  // EN — fallback (rest APIs, ops que escapam o padrão)
  "get",
  "list",
  "find",
  "fetch",
  "search",
  "load",
  "show",
  "view",
  "read",
  "create",
  "add",
  "insert",
  "register",
  "update",
  "edit",
  "modify",
  "patch",
  "change",
  "delete",
  "remove",
  "destroy",
  "soft",
  "save",
  "store",
  "submit",
  "send",
  "dispatch",
  "trigger",
  "run",
  "execute",
  "perform",
  "sync",
  "import",
  "export",
  "upload",
  "download",
  "approve",
  "reject",
  "cancel",
  "close",
  "open",
  "claim",
  "transfer",
  "assign",
  "unassign",
  "enable",
  "disable",
  "activate",
  "deactivate",
];

/** Tira verbo + qualifiers + singulariza → categoria. */
export function categorize(operationName: string): string {
  let s = operationName;
  s = s.replace(/(?:Query|Mutation|GQL|Operation)$/i, "");

  const lower = s.toLowerCase();
  for (const v of VERB_PREFIXES) {
    if (lower.startsWith(v) && s.length > v.length) {
      s = s.slice(v.length);
      break;
    }
  }

  // Strip qualifiers que aparecem em QUALQUER posição: Por<algo>
  // (PorId, PorTelefone, PorNomeOuTel, PorUsuarioId, PorIbge…)
  s = s.replace(/Por[A-Z][a-zA-Z]*/g, "");

  // Strip suffixes técnicos comuns no schema ZigChat
  s = s.replace(
    /(Lazy|Count|Ativos?|Vinculados?|Historicos?|Final|Empresa)$/i,
    "",
  );

  // Quebra em chunks camelCase
  const tokens = s.match(/[A-Z][a-z]*|^[a-z]+/g) ?? [s];
  if (tokens.length === 0) return "uncategorized";

  // Pula primeiro chunk se for qualificador conhecido (atualizarStatusConexao
  // → conexao, não status). Forma e Campo aparecem em "buscarCamposCliente".
  const SKIP_FIRST = new Set([
    "status",
    "total",
    "limite",
    "campos",
    "campo",
    "form",
    "ultimo",
    "primeiro",
  ]);
  let chosen = tokens[0]!.toLowerCase();
  if (SKIP_FIRST.has(chosen) && tokens.length > 1) {
    chosen = tokens[1]!.toLowerCase();
  }

  return singularizePtBr(chosen);
}

/**
 * Singularização heurística PT-BR + EN. Não cobre 100% (português é
 * cheio de exceções) mas pega os padrões comuns no schema do ZigChat.
 *
 * Ordem importa: regras mais específicas primeiro.
 */
export function singularizePtBr(word: string): string {
  if (word.length <= 3) return word;
  // PT-BR
  if (word.endsWith("oes")) return word.slice(0, -3) + "ao"; // conexoes → conexao
  if (word.endsWith("aes")) return word.slice(0, -3) + "ao"; // capitaes → capitao
  if (word.endsWith("eis")) return word.slice(0, -3) + "el"; // papeis → papel
  if (word.endsWith("ais")) return word.slice(0, -3) + "al"; // animais → animal
  if (word.endsWith("ois")) return word.slice(0, -3) + "ol"; // anzois → anzol
  if (word.endsWith("uis")) return word.slice(0, -3) + "ul";
  // "ens" → "em" (mensagens → mensagem, jovens → jovem)
  if (word.endsWith("ens")) return word.slice(0, -3) + "em";
  if (word.endsWith("res")) return word.slice(0, -2); // setores → setor
  if (word.endsWith("ses")) return word.slice(0, -2); // meses → mes
  if (word.endsWith("zes")) return word.slice(0, -2); // luzes → luz
  if (word.endsWith("ies")) return word.slice(0, -3) + "y"; // categories → category (EN)
  if (word.endsWith("s") && !word.endsWith("ss"))
    return word.slice(0, -1); // genérico (atendimentos → atendimento)
  return word;
}

export function dedupe(captured: CapturedOperation[]): DedupedOperation[] {
  const byOpName = new Map<string, DedupedOperation>();

  for (const op of captured) {
    if (!op.operationName) continue;
    const key = op.operationName;
    const existing = byOpName.get(key);

    if (!existing) {
      byOpName.set(key, {
        operationName: key,
        querySnippet: op.querySnippet,
        occurrences: 1,
        routes: [op.routeWhereSeen],
        category: categorize(key),
        sampleVariables: op.variables,
        sampleResponseKeys: op.dataKeys,
      });
    } else {
      existing.occurrences += 1;
      if (!existing.routes.includes(op.routeWhereSeen)) {
        existing.routes.push(op.routeWhereSeen);
      }
      // Mantém o primeiro sample não-vazio
      if (!existing.sampleVariables && op.variables) {
        existing.sampleVariables = op.variables;
      }
      if (
        (!existing.sampleResponseKeys ||
          existing.sampleResponseKeys.length === 0) &&
        op.dataKeys &&
        op.dataKeys.length > 0
      ) {
        existing.sampleResponseKeys = op.dataKeys;
      }
    }
  }

  // Ordena alfabeticamente pra diff estável
  return [...byOpName.values()].sort((a, b) =>
    a.operationName.localeCompare(b.operationName),
  );
}

/** Agrupa deduped por categoria pra report. */
export function groupByCategory(
  ops: DedupedOperation[],
): Map<string, DedupedOperation[]> {
  const m = new Map<string, DedupedOperation[]>();
  for (const op of ops) {
    const arr = m.get(op.category) ?? [];
    arr.push(op);
    m.set(op.category, arr);
  }
  return m;
}

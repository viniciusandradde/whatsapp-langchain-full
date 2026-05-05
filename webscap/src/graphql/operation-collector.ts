/**
 * Recebe operations capturadas em runtime e produz lista deduplicada
 * + categorizada por entity.
 *
 * Categorização heurística: `getCliente` → cliente; `createCampanha` →
 * campanha; `listAtendimentoMensagens` → atendimento. Strip de
 * verbos comuns (get/list/create/update/delete/find/save/sync).
 */

import type { CapturedOperation, DedupedOperation } from "../types.js";

const VERB_PREFIXES = [
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

/** Tira o verbo prefixo + camelCase first lower → categoria. */
export function categorize(operationName: string): string {
  let s = operationName;
  // Remove "GraphQL" suffix se houver
  s = s.replace(/(?:Query|Mutation|GQL|Operation)$/i, "");

  // Remove verbo prefixo
  const lower = s.toLowerCase();
  for (const v of VERB_PREFIXES) {
    if (lower.startsWith(v) && s.length > v.length) {
      const next = s.charAt(v.length);
      if (next === next.toUpperCase()) {
        s = s.slice(v.length);
        break;
      }
    }
  }

  // Trata plurais simples (ClientesQuery → cliente)
  s = s.replace(/s$/, "");

  // camelCase → snake (mas só pega primeiro chunk pra categoria)
  // Ex: "AtendimentoMensagem" → "atendimento"
  const tokens = s.match(/[A-Z][a-z]*|^[a-z]+/g) ?? [s];
  const head = tokens[0]?.toLowerCase() ?? operationName.toLowerCase();
  return head || "uncategorized";
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

/**
 * Diff entre 2 schemas GraphQL (introspection JSON).
 *
 * Detecta:
 * - Types adicionados/removidos
 * - Fields adicionados/removidos por type
 * - Mudança de tipo em field (ex: String → Int!) — breaking
 * - Argumentos adicionados/removidos
 *
 * Output: SchemaDiff (estruturado) + render markdown changelog.
 *
 * Não detecta: deprecation, descrições, directives custom (raros em prod).
 */

import type {
  GqlField,
  GqlInputField,
  GqlIntrospectionType,
  GqlSchema,
} from "../types.js";

export interface FieldChange {
  fieldName: string;
  /** Antes/depois pra fields modificados. */
  before?: string;
  after?: string;
}

export interface TypeDiff {
  typeName: string;
  kind: "OBJECT" | "INPUT_OBJECT" | "ENUM" | "UNION" | "INTERFACE" | "SCALAR" | "UNKNOWN";
  status: "added" | "removed" | "modified";
  fieldsAdded: FieldChange[];
  fieldsRemoved: FieldChange[];
  fieldsChanged: FieldChange[];
}

export interface SchemaDiff {
  generatedAt: string;
  summary: {
    typesAdded: number;
    typesRemoved: number;
    typesModified: number;
    breakingChanges: number;
  };
  types: TypeDiff[];
}

function typeRef(t: GqlIntrospectionType | null | undefined): string {
  if (!t) return "Unknown";
  if (t.kind === "NON_NULL") return `${typeRef(t.ofType)}!`;
  if (t.kind === "LIST") return `[${typeRef(t.ofType)}]`;
  return t.name ?? "Unknown";
}

function fieldSig(f: GqlField | GqlInputField): string {
  const args =
    "args" in f && f.args && f.args.length > 0
      ? "(" +
        f.args
          .map((a) => `${a.name}: ${typeRef(a.type)}`)
          .join(", ") +
        ")"
      : "";
  return `${f.name}${args}: ${typeRef(f.type)}`;
}

function indexTypes(s: GqlSchema): Map<string, GqlIntrospectionType> {
  const m = new Map<string, GqlIntrospectionType>();
  for (const t of s.types) {
    if (!t.name || t.name.startsWith("__")) continue;
    m.set(t.name, t);
  }
  return m;
}

function indexFields(
  t: GqlIntrospectionType,
): Map<string, GqlField | GqlInputField> {
  const m = new Map<string, GqlField | GqlInputField>();
  if (t.kind === "INPUT_OBJECT") {
    for (const f of t.inputFields ?? []) m.set(f.name, f);
  } else {
    for (const f of t.fields ?? []) m.set(f.name, f);
  }
  return m;
}

export function computeSchemaDiff(
  before: GqlSchema,
  after: GqlSchema,
): SchemaDiff {
  const beforeIdx = indexTypes(before);
  const afterIdx = indexTypes(after);
  const types: TypeDiff[] = [];

  // Adicionados
  for (const [name, t] of afterIdx) {
    if (!beforeIdx.has(name)) {
      types.push({
        typeName: name,
        kind: (t.kind as TypeDiff["kind"]) ?? "UNKNOWN",
        status: "added",
        fieldsAdded: [],
        fieldsRemoved: [],
        fieldsChanged: [],
      });
    }
  }

  // Removidos
  for (const [name, t] of beforeIdx) {
    if (!afterIdx.has(name)) {
      types.push({
        typeName: name,
        kind: (t.kind as TypeDiff["kind"]) ?? "UNKNOWN",
        status: "removed",
        fieldsAdded: [],
        fieldsRemoved: [],
        fieldsChanged: [],
      });
    }
  }

  // Modificados
  for (const [name, tBefore] of beforeIdx) {
    const tAfter = afterIdx.get(name);
    if (!tAfter) continue;
    const fBefore = indexFields(tBefore);
    const fAfter = indexFields(tAfter);
    const added: FieldChange[] = [];
    const removed: FieldChange[] = [];
    const changed: FieldChange[] = [];

    for (const [fname, fa] of fAfter) {
      const fb = fBefore.get(fname);
      if (!fb) {
        added.push({ fieldName: fname, after: fieldSig(fa) });
      } else {
        const bSig = fieldSig(fb);
        const aSig = fieldSig(fa);
        if (bSig !== aSig) {
          changed.push({ fieldName: fname, before: bSig, after: aSig });
        }
      }
    }
    for (const [fname, fb] of fBefore) {
      if (!fAfter.has(fname))
        removed.push({ fieldName: fname, before: fieldSig(fb) });
    }

    if (added.length || removed.length || changed.length) {
      types.push({
        typeName: name,
        kind: (tAfter.kind as TypeDiff["kind"]) ?? "UNKNOWN",
        status: "modified",
        fieldsAdded: added,
        fieldsRemoved: removed,
        fieldsChanged: changed,
      });
    }
  }

  // Ordena: added > removed > modified, depois alfabético
  const order = { added: 0, removed: 1, modified: 2 };
  types.sort((a, b) => {
    if (order[a.status] !== order[b.status])
      return order[a.status] - order[b.status];
    return a.typeName.localeCompare(b.typeName);
  });

  // Breaking changes = removed types + removed fields + changed fields
  // (todo change de signature pode quebrar callers)
  const breaking =
    types.filter((t) => t.status === "removed").length +
    types.reduce(
      (sum, t) => sum + t.fieldsRemoved.length + t.fieldsChanged.length,
      0,
    );

  return {
    generatedAt: new Date().toISOString(),
    summary: {
      typesAdded: types.filter((t) => t.status === "added").length,
      typesRemoved: types.filter((t) => t.status === "removed").length,
      typesModified: types.filter((t) => t.status === "modified").length,
      breakingChanges: breaking,
    },
    types,
  };
}

export function renderSchemaDiffMarkdown(diff: SchemaDiff): string {
  const lines: string[] = [];
  lines.push("# GraphQL Schema Diff");
  lines.push("");
  lines.push(`> Gerado em ${diff.generatedAt}`);
  lines.push("");
  lines.push("## Resumo");
  lines.push("");
  lines.push(`- ➕ **${diff.summary.typesAdded}** types adicionados`);
  lines.push(`- ➖ **${diff.summary.typesRemoved}** types removidos`);
  lines.push(`- 🔄 **${diff.summary.typesModified}** types modificados`);
  lines.push(
    `- ⚠️ **${diff.summary.breakingChanges}** breaking changes (removed/changed fields)`,
  );
  lines.push("");

  for (const status of ["added", "removed", "modified"] as const) {
    const filtered = diff.types.filter((t) => t.status === status);
    if (filtered.length === 0) continue;
    const icon =
      status === "added" ? "➕" : status === "removed" ? "➖" : "🔄";
    lines.push(`## ${icon} ${cap(status)} (${filtered.length})`);
    lines.push("");
    for (const t of filtered) {
      lines.push(`### \`${t.typeName}\` (${t.kind.toLowerCase()})`);
      if (status === "modified") {
        if (t.fieldsAdded.length > 0) {
          lines.push("");
          lines.push("**Campos adicionados:**");
          for (const f of t.fieldsAdded) lines.push(`- ➕ \`${f.after}\``);
        }
        if (t.fieldsRemoved.length > 0) {
          lines.push("");
          lines.push("**Campos removidos (BREAKING):**");
          for (const f of t.fieldsRemoved)
            lines.push(`- ➖ \`${f.before}\``);
        }
        if (t.fieldsChanged.length > 0) {
          lines.push("");
          lines.push("**Campos alterados (possível BREAKING):**");
          for (const f of t.fieldsChanged) {
            lines.push(`- 🔄 \`${f.before}\` → \`${f.after}\``);
          }
        }
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

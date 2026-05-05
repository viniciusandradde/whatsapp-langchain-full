/**
 * Coverage report: cruza operations capturadas (categorizadas) com
 * tabelas existentes nas migrations Postgres do Nexus pra produzir
 * markdown navegável de gap analysis.
 *
 * Heurística:
 * - Lê db/migrations/*.sql, regex `CREATE TABLE [IF NOT EXISTS] (\w+)`
 * - Conta colunas por tabela (heurística — não AST SQL completa)
 * - Mapeia categoria ZigChat (ex: "cliente") → nome da tabela Nexus
 * - Status: covered (tabela existe + razoável), partial (existe mas gap
 *   visível), missing (sem tabela equivalente)
 */

import fs from "node:fs";
import path from "node:path";

import type {
  CoverageReport,
  CoverageRow,
  DedupedOperation,
  NexusEntity,
} from "../types.js";

const TABLE_RE = /CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?\s*\(/gi;

/**
 * Aliases pra categorias ZigChat que não batem 1:1 com tabela Nexus.
 * Refinado a partir do schema real (151 queries / 74 mutations) capturado
 * em 2026-04-29 — ver webscap/legacy/playwright/output/schema-summary.md.
 *
 * Convenção: categoria sempre lower-case, sem espaços. Lista vazia =
 * conhecida mas SEM equivalente no Nexus → status "missing" no report.
 */
const CATEGORY_TO_TABLE: Record<string, string[]> = {
  // --- COVERED no Nexus (Etapas 1+2 entregues) ---
  cliente: ["cliente"],
  clienteanotacao: ["cliente_anotacao"],
  clientemencao: ["cliente_anotacao"],
  tag: ["cliente_tag"],
  atendimento: ["atendimento"],
  atendimentomensagem: ["message_queue"],
  atendimentotransferencia: ["atendimento"],
  mensagem: ["message_queue"],
  conexao: ["conexao"],
  canal: ["conexao"],
  canalexterno: ["conexao"],
  telegram: ["conexao"],
  hook: ["hook", "hook_log", "hook_dead_letter"],
  hooktask: ["hook_log", "hook_dead_letter"],
  hookurl: ["hook"],
  campanha: ["campanha", "campanha_destinatario"],
  modelomensagem: ["modelo_mensagem"],
  modelo: ["modelo_mensagem"],
  template: ["modelo_mensagem", "waba_template"],
  waba: ["waba_template"],
  wabatemplate: ["waba_template"],
  agente: ["agente_ia_config"],
  agenteia: ["agente_ia_config"],
  ia: ["agente_ia_config"],
  iaexecucao: ["agente_ia_config"],
  iauso: ["agente_ia_config"],
  baseconhecimento: ["documento_conhecimento"],
  documento: ["documento_conhecimento"],
  conhecimento: ["documento_conhecimento"],
  variavel: ["variavel_ambiente"],
  variavelambiente: ["variavel_ambiente"],
  departamento: ["departamento"],
  horario: ["horario_funcionamento"],
  horariofuncionamento: ["horario_funcionamento"],
  feriado: ["feriado"],
  turno: ["horario_funcionamento"],
  empresa: ["empresa", "empresa_membro"],
  usuario: ["empresa_membro"],
  usuariocliente: ["empresa_membro"],
  vinculousuariocliente: ["empresa_membro"],
  user: ["empresa_membro"],
  pasta: ["pasta"],
  arquivo: ["documento_conhecimento", "pasta"],
  perfil: ["perfil_acesso"],
  permissao: ["permissao"],
  gruposistema: ["perfil_acesso", "permissao"],
  grupo: ["perfil_acesso"],
  calendario: ["empresa_calendar_config", "agendamento"],
  calendarioevento: ["agendamento"],
  agendamento: ["agendamento"],
  aprovacao: ["agendamento_aprovacao"],
  rate: ["rate_limit_bucket"],

  // --- MISSING no Nexus (gap real, ordem do ROADMAP) ---
  // E-commerce / catálogo (fora do MVP no roadmap original)
  produto: [],
  pedido: [],
  transacao: [],
  categoriaproduto: [],

  // Coleta de dados / forms
  formpadrao: [],
  formpadraoatendimento: [],

  // Chatbot menu (não-IA — abordagem alternativa ao agente)
  menu: [],
  item: [],
  menuitem: [],
  menuitemarquivo: [],
  atendimentomenuhistorico: [],

  // Notificações / mensagens automáticas
  aviso: [],
  sistemamensagem: [],

  // Auditoria
  geral: [],
  geralog: [],
  geral_log: [],
  apptraces: [],
  trace: [],

  // Misc
  cidade: [],
  termo: [],
  ultimotermo: [],

  // MCP servers (mencionado no ROADMAP M5 mas ainda backlog)
  mcpserver: [],
  mcp: [],
};

export function loadNexusEntities(migrationsDir: string): NexusEntity[] {
  if (!fs.existsSync(migrationsDir)) {
    throw new Error(`Diretório ${migrationsDir} não existe`);
  }
  const files = fs
    .readdirSync(migrationsDir)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  const found = new Map<string, NexusEntity>();

  for (const file of files) {
    const content = fs.readFileSync(path.join(migrationsDir, file), "utf8");
    let m: RegExpExecArray | null;
    TABLE_RE.lastIndex = 0;
    while ((m = TABLE_RE.exec(content))) {
      const name = m[1];
      if (!name) continue;
      // Conta colunas heuristicamente: linhas terminando com "," ou "\n)" no
      // bloco subsequente. Não-AST mas serve pra ordem de magnitude.
      const blockMatch = content
        .slice(m.index)
        .match(/CREATE\s+TABLE[^(]*\(([\s\S]*?)\n\)/i);
      let columnsCount = 0;
      if (blockMatch && blockMatch[1]) {
        const lines = blockMatch[1]
          .split("\n")
          .map((l) => l.trim())
          .filter(
            (l) =>
              l.length > 0 &&
              !l.startsWith("--") &&
              !/^(PRIMARY|UNIQUE|FOREIGN|CHECK|CONSTRAINT)/i.test(l),
          );
        columnsCount = lines.length;
      }
      // Mantém primeira ocorrência (mig original); ignora ALTER subsequentes
      if (!found.has(name)) {
        found.set(name, {
          name,
          source: file,
          columnsCount,
        });
      }
    }
  }

  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function buildCoverage(
  zigchatOps: DedupedOperation[],
  nexusEntities: NexusEntity[],
  zigchatRunPath: string,
  nexusMigrationsDir: string,
): CoverageReport {
  // Agrupa por categoria
  const byCategory = new Map<string, DedupedOperation[]>();
  for (const op of zigchatOps) {
    const arr = byCategory.get(op.category) ?? [];
    arr.push(op);
    byCategory.set(op.category, arr);
  }

  const entityByName = new Map(nexusEntities.map((e) => [e.name, e]));
  const rows: CoverageRow[] = [];

  for (const [category, ops] of byCategory) {
    const candidateTables = CATEGORY_TO_TABLE[category] ?? [category];
    const matched = candidateTables
      .map((t) => entityByName.get(t))
      .filter((x): x is NexusEntity => Boolean(x));

    let status: CoverageRow["status"];
    let notes: string | undefined;

    if (matched.length === 0) {
      status = "missing";
      notes =
        candidateTables.length > 0
          ? `Esperado tabela(s): ${candidateTables.join(", ")} — não encontradas`
          : "Sem mapeamento conhecido (revise CATEGORY_TO_TABLE)";
    } else {
      const totalColumns = matched.reduce(
        (sum, e) => sum + e.columnsCount,
        0,
      );
      // Heurística de "partial": muitas operations vs poucas colunas
      // sugerem campos faltando. Limite arbitrário 1.5 ops por coluna.
      if (ops.length > totalColumns * 1.5 && totalColumns > 0) {
        status = "partial";
        notes = `${ops.length} ops vs ${totalColumns} colunas em ${matched
          .map((e) => e.name)
          .join("+")} — possível gap de campos`;
      } else {
        status = "covered";
      }
    }

    rows.push({
      zigchatCategory: category,
      zigchatOpsCount: ops.length,
      zigchatOps: ops.map((o) => o.operationName).sort(),
      nexusEntity: matched[0] ?? null,
      status,
      notes,
    });
  }

  rows.sort((a, b) => {
    // missing primeiro (mais útil pro backlog), depois partial, depois covered
    const order = { missing: 0, partial: 1, covered: 2 };
    if (order[a.status] !== order[b.status])
      return order[a.status] - order[b.status];
    return b.zigchatOpsCount - a.zigchatOpsCount;
  });

  const summary = {
    totalCategories: rows.length,
    covered: rows.filter((r) => r.status === "covered").length,
    partial: rows.filter((r) => r.status === "partial").length,
    missing: rows.filter((r) => r.status === "missing").length,
  };

  return {
    generatedAt: new Date().toISOString(),
    zigchatRunPath,
    nexusMigrationsDir,
    summary,
    rows,
  };
}

export function renderCoverageMarkdown(report: CoverageReport): string {
  const lines: string[] = [];
  lines.push(`# Coverage Nexus vs ZigChat`);
  lines.push("");
  lines.push(`> Gerado em ${report.generatedAt}`);
  lines.push(`> ZigChat run: \`${report.zigchatRunPath}\``);
  lines.push(`> Nexus migrations: \`${report.nexusMigrationsDir}\``);
  lines.push("");
  lines.push("## Resumo");
  lines.push("");
  lines.push(
    `- **${report.summary.totalCategories}** categorias ZigChat detectadas`,
  );
  lines.push(`- ✅ **${report.summary.covered}** covered`);
  lines.push(`- ⚠️ **${report.summary.partial}** partial (gap de campos)`);
  lines.push(`- ❌ **${report.summary.missing}** missing (sem tabela)`);
  lines.push("");

  for (const status of ["missing", "partial", "covered"] as const) {
    const filtered = report.rows.filter((r) => r.status === status);
    if (filtered.length === 0) continue;
    const icon = status === "missing" ? "❌" : status === "partial" ? "⚠️" : "✅";
    lines.push(`## ${icon} ${cap(status)} (${filtered.length})`);
    lines.push("");
    lines.push("| Categoria ZigChat | Ops | Tabela Nexus | Notas |");
    lines.push("|---|---|---|---|");
    for (const r of filtered) {
      const nexusCol = r.nexusEntity
        ? `\`${r.nexusEntity.name}\` (${r.nexusEntity.columnsCount} cols, ${r.nexusEntity.source})`
        : "—";
      const notes = r.notes ?? "";
      lines.push(
        `| **${r.zigchatCategory}** | ${r.zigchatOpsCount} | ${nexusCol} | ${notes} |`,
      );
    }
    lines.push("");
  }

  // Detalhe das ops missing pra fácil priorização
  const missing = report.rows.filter((r) => r.status === "missing");
  if (missing.length > 0) {
    lines.push("## Detalhe — operations das categorias missing");
    lines.push("");
    for (const r of missing) {
      lines.push(`### ${r.zigchatCategory} (${r.zigchatOpsCount} ops)`);
      lines.push("");
      for (const op of r.zigchatOps) lines.push(`- \`${op}\``);
      lines.push("");
    }
  }

  return lines.join("\n");
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

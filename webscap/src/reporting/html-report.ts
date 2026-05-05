/**
 * HTML report single-file: dashboard navegável com schema explorer +
 * operations table + screenshots gallery + coverage.
 *
 * Sem JS framework: HTML+CSS+vanilla JS minimal pra abrir em qualquer
 * browser sem servidor. Imagens referenciadas relativas pro próprio
 * runDir.
 */

import path from "node:path";

import type {
  CaptureInventory,
  CoverageReport,
  GqlSchema,
  RouteVisit,
} from "../types.js";

export interface HtmlReportInput {
  capture: CaptureInventory;
  schema: GqlSchema | null;
  coverage: CoverageReport | null;
  runDir: string;
}

export function renderHtmlReport(input: HtmlReportInput): string {
  const { capture, schema, coverage, runDir } = input;
  const opsRows = capture.operations
    .map(
      (op) => `
    <tr>
      <td><code>${escape(op.operationName)}</code></td>
      <td><span class="badge">${escape(op.category)}</span></td>
      <td>${op.occurrences}</td>
      <td>${op.routes.map((r) => `<code>${escape(pathOnly(r))}</code>`).join(", ")}</td>
    </tr>`,
    )
    .join("");

  const coverageRows = coverage
    ? coverage.rows
        .map((r) => {
          const icon =
            r.status === "covered" ? "✅" : r.status === "partial" ? "⚠️" : "❌";
          return `
    <tr class="status-${r.status}">
      <td>${icon}</td>
      <td><strong>${escape(r.zigchatCategory)}</strong></td>
      <td>${r.zigchatOpsCount}</td>
      <td>${r.nexusEntity ? `<code>${escape(r.nexusEntity.name)}</code>` : "—"}</td>
      <td>${escape(r.notes ?? "")}</td>
    </tr>`;
        })
        .join("")
    : "<tr><td colspan='5'>Sem coverage data — rode <code>npm run coverage</code></td></tr>";

  const screenshotsHtml = capture.routes
    .filter((r) => r.screenshotPath && r.ok)
    .map(
      (r) => `
    <figure>
      <figcaption><code>${escape(pathOnly(r.url))}</code></figcaption>
      <img src="${rel(runDir, r.screenshotPath!)}" loading="lazy" alt="${escape(pathOnly(r.url))}" />
    </figure>`,
    )
    .join("");

  const schemaSummary = schema
    ? `
    <p>${schema.types.length} types totais.
       Query: <code>${escape(schema.queryType?.name ?? "—")}</code>.
       Mutation: <code>${escape(schema.mutationType?.name ?? "—")}</code>.</p>`
    : "<p>Sem schema — rode <code>npm run introspect</code></p>";

  const totalOps = capture.operations.reduce(
    (s, o) => s + o.occurrences,
    0,
  );

  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Webscap Report — ${escape(capture.capturedAt)}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 1rem 2rem; line-height: 1.5; }
  h1 { border-bottom: 2px solid #f97316; padding-bottom: .5rem; }
  h2 { border-bottom: 1px solid rgba(128,128,128,.3); padding-bottom: .3rem; margin-top: 2rem; }
  nav { position: sticky; top: 0; background: var(--bg, white); padding: .8rem 0; border-bottom: 1px solid rgba(128,128,128,.2); margin-bottom: 1.5rem; z-index: 10; }
  nav a { margin-right: 1rem; text-decoration: none; color: #f97316; font-weight: 500; }
  nav a:hover { text-decoration: underline; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
  th, td { text-align: left; padding: .5rem .75rem; border-bottom: 1px solid rgba(128,128,128,.2); }
  th { background: rgba(249,115,22,.08); font-weight: 600; }
  tr.status-missing { background: rgba(239,68,68,.05); }
  tr.status-partial { background: rgba(234,179,8,.05); }
  code { background: rgba(128,128,128,.1); padding: 0 .3rem; border-radius: 3px; font-size: .85rem; }
  .badge { display: inline-block; background: #f97316; color: white; padding: .1rem .5rem; border-radius: 999px; font-size: .75rem; }
  .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1rem 0; }
  .summary .card { background: rgba(128,128,128,.05); padding: 1rem; border-radius: 8px; border-left: 4px solid #f97316; }
  .summary .card .num { font-size: 2rem; font-weight: 700; color: #f97316; }
  .summary .card .label { font-size: .85rem; opacity: .7; text-transform: uppercase; letter-spacing: .05em; }
  figure { margin: 1rem 0; padding: .5rem; background: rgba(128,128,128,.05); border-radius: 6px; }
  figure figcaption { font-size: .85rem; opacity: .7; margin-bottom: .5rem; }
  figure img { max-width: 100%; border: 1px solid rgba(128,128,128,.2); border-radius: 4px; }
  details { margin: .5rem 0; }
  details summary { cursor: pointer; font-weight: 500; padding: .3rem 0; }
  @media (prefers-color-scheme: dark) {
    body { background: #0d0d10; color: #f5f5f5; }
    nav { background: #0d0d10; }
    .summary .card { background: rgba(255,255,255,.04); }
    figure { background: rgba(255,255,255,.04); }
  }
</style>
</head>
<body>
  <h1>Webscap Report</h1>
  <p><small>Capturado em <strong>${escape(capture.capturedAt)}</strong> contra <code>${escape(capture.baseUrl)}</code></small></p>

  <nav>
    <a href="#resumo">Resumo</a>
    <a href="#operations">Operations</a>
    <a href="#coverage">Coverage</a>
    <a href="#schema">Schema</a>
    <a href="#screenshots">Screenshots</a>
  </nav>

  <section id="resumo">
    <h2>Resumo</h2>
    <div class="summary">
      <div class="card"><div class="num">${capture.routes.length}</div><div class="label">Rotas visitadas</div></div>
      <div class="card"><div class="num">${capture.operations.length}</div><div class="label">Ops únicas</div></div>
      <div class="card"><div class="num">${totalOps}</div><div class="label">Chamadas GraphQL</div></div>
      <div class="card"><div class="num">${schema?.types.length ?? "—"}</div><div class="label">Schema types</div></div>
    </div>
  </section>

  <section id="operations">
    <h2>Operations capturadas</h2>
    <table>
      <thead><tr><th>OperationName</th><th>Categoria</th><th># uso</th><th>Rotas</th></tr></thead>
      <tbody>${opsRows}</tbody>
    </table>
  </section>

  <section id="coverage">
    <h2>Coverage Nexus vs ZigChat</h2>
    ${coverage ? `<p>${coverage.summary.covered} covered · ${coverage.summary.partial} partial · ${coverage.summary.missing} missing (${coverage.summary.totalCategories} categorias)</p>` : ""}
    <table>
      <thead><tr><th></th><th>Categoria ZigChat</th><th># ops</th><th>Tabela Nexus</th><th>Notas</th></tr></thead>
      <tbody>${coverageRows}</tbody>
    </table>
  </section>

  <section id="schema">
    <h2>Schema</h2>
    ${schemaSummary}
    <details><summary>Ver tipos OBJECT (${schema ? schema.types.filter((t) => t.kind === "OBJECT" && !t.name?.startsWith("__")).length : 0})</summary>
      <ul>
        ${schema ? schema.types.filter((t) => t.kind === "OBJECT" && !t.name?.startsWith("__")).map((t) => `<li><code>${escape(t.name ?? "")}</code> (${t.fields?.length ?? 0} fields)</li>`).join("") : ""}
      </ul>
    </details>
  </section>

  <section id="screenshots">
    <h2>Screenshots</h2>
    ${screenshotsHtml}
  </section>

  <footer>
    <hr>
    <small>Gerado por webscap v0.3 — ${new Date().toISOString()}</small>
  </footer>
</body>
</html>`;
}

function escape(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pathOnly(url: string): string {
  try {
    return new URL(url).pathname || url;
  } catch {
    return url;
  }
}

function rel(from: string, to: string): string {
  return path.relative(from, to) || to;
}

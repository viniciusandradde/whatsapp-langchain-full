/**
 * graphql-introspect.js — usa a sessão (auth.json) pra rodar
 * introspection query no /api/graphql do ZigChat e exportar o
 * schema completo (types, queries, mutations).
 *
 * Esse é o caminho mais rico pra mapear o backend em massa — em
 * minutos lista todas as operations com signatures, ao invés de
 * só ver o que aparece no UI.
 *
 * Uso:
 *   npm run graphql:introspect
 *
 * Saída:
 *   output/schema.json — schema bruto
 *   output/schema-summary.txt — resumo legível (queries + mutations)
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = "https://dev.zigchat.com.br";
const OUT_DIR = "output";
fs.mkdirSync(OUT_DIR, { recursive: true });

const INTROSPECTION_QUERY = `
  query IntrospectionQuery {
    __schema {
      queryType { name }
      mutationType { name }
      subscriptionType { name }
      types {
        kind
        name
        description
        fields(includeDeprecated: true) {
          name
          description
          args { name type { kind name ofType { kind name } } defaultValue }
          type { kind name ofType { kind name ofType { kind name } } }
        }
        inputFields {
          name
          type { kind name ofType { kind name } }
          defaultValue
        }
        enumValues(includeDeprecated: true) { name }
      }
    }
  }
`;

(async () => {
  if (!fs.existsSync("auth.json")) {
    console.error("auth.json não encontrado — rode `npm run login` primeiro.");
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ storageState: "auth.json" });
  const page = await ctx.newPage();
  await page.goto(BASE_URL + "/dashboard/panel", { waitUntil: "domcontentloaded" });

  // Roda a introspection no contexto da página — a sessão (cookies httpOnly +
  // headers) é aplicada automaticamente pelo browser.
  const result = await page.evaluate(async (query) => {
    const r = await fetch("/api/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ operationName: "IntrospectionQuery", query, variables: {} }),
    });
    return { status: r.status, body: await r.text() };
  }, INTROSPECTION_QUERY);

  if (result.status !== 200) {
    console.error("Introspection falhou:", result.status);
    console.error(result.body.slice(0, 500));
    await browser.close();
    process.exit(1);
  }

  const schema = JSON.parse(result.body);
  fs.writeFileSync(path.join(OUT_DIR, "schema.json"), JSON.stringify(schema, null, 2));

  // Resumo legível
  const types = schema.data.__schema.types;
  const queryType = schema.data.__schema.queryType?.name;
  const mutationType = schema.data.__schema.mutationType?.name;

  const summary = [];
  summary.push(`# ZigChat GraphQL Schema — capturado ${new Date().toISOString()}\n`);

  for (const root of [queryType, mutationType].filter(Boolean)) {
    const t = types.find((x) => x.name === root);
    if (!t) continue;
    summary.push(`\n## ${root} (${t.fields?.length || 0} operations)\n`);
    for (const f of t.fields || []) {
      const args = (f.args || [])
        .map((a) => `${a.name}: ${a.type.name || a.type.ofType?.name || "?"}`)
        .join(", ");
      const ret = f.type.name || f.type.ofType?.name || f.type.ofType?.ofType?.name || "?";
      summary.push(`- ${f.name}(${args}) → ${ret}`);
    }
  }

  fs.writeFileSync(path.join(OUT_DIR, "schema-summary.txt"), summary.join("\n") + "\n");
  console.log(`✓ schema.json (${(result.body.length / 1024).toFixed(1)} KB) + schema-summary.txt`);
  console.log(`  ${types.length} types totais`);
  await browser.close();
})();

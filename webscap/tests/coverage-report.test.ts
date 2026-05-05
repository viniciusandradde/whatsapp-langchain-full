import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  buildCoverage,
  loadNexusEntities,
  renderCoverageMarkdown,
} from "../src/reporting/coverage-report.js";
import type { DedupedOperation } from "../src/types.js";

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "webscap-test-"));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

function migration(name: string, body: string) {
  fs.writeFileSync(path.join(tmpDir, name), body);
}

describe("loadNexusEntities", () => {
  it("extrai tabelas + conta colunas (heurística)", () => {
    migration(
      "001_init.sql",
      `
CREATE TABLE cliente (
  id BIGSERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  empresa_id BIGINT NOT NULL
);

CREATE TABLE atendimento (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT REFERENCES cliente(id),
  status TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
      `,
    );
    const out = loadNexusEntities(tmpDir);
    expect(out.map((e) => e.name).sort()).toEqual(["atendimento", "cliente"]);
    const cli = out.find((e) => e.name === "cliente")!;
    expect(cli.columnsCount).toBeGreaterThanOrEqual(3);
    expect(cli.source).toBe("001_init.sql");
  });

  it("ignora ALTER TABLE em migrations subsequentes", () => {
    migration("001.sql", "CREATE TABLE cliente (id BIGSERIAL PRIMARY KEY);");
    migration("002.sql", "ALTER TABLE cliente ADD COLUMN nome TEXT;");
    const out = loadNexusEntities(tmpDir);
    expect(out).toHaveLength(1);
    expect(out[0]!.source).toBe("001.sql");
  });
});

describe("buildCoverage", () => {
  function op(operationName: string, category: string): DedupedOperation {
    return {
      operationName,
      querySnippet: "",
      occurrences: 1,
      routes: [],
      category,
    };
  }

  it("classifica covered/partial/missing", () => {
    migration(
      "001.sql",
      `
CREATE TABLE cliente (
  id BIGSERIAL PRIMARY KEY,
  nome TEXT,
  email TEXT,
  telefone TEXT,
  empresa_id BIGINT
);
      `,
    );
    const ents = loadNexusEntities(tmpDir);
    const ops = [
      op("getCliente", "cliente"),
      op("listClientes", "cliente"),
      op("createMcpServer", "mcpserver"),
      op("listMcpServers", "mcpserver"),
    ];
    const r = buildCoverage(ops, ents, "/tmp/run", tmpDir);

    expect(r.summary.totalCategories).toBe(2);
    expect(r.summary.covered).toBe(1);
    expect(r.summary.missing).toBe(1);

    const cliRow = r.rows.find((x) => x.zigchatCategory === "cliente")!;
    expect(cliRow.status).toBe("covered");
    expect(cliRow.nexusEntity?.name).toBe("cliente");

    const mcpRow = r.rows.find((x) => x.zigchatCategory === "mcpserver")!;
    expect(mcpRow.status).toBe("missing");
  });

  it("ordena: missing primeiro, depois partial, depois covered", () => {
    migration("001.sql", "CREATE TABLE cliente (id BIGSERIAL);");
    const ents = loadNexusEntities(tmpDir);
    const ops = [
      op("getCliente", "cliente"),
      op("getMcpServer", "mcpserver"),
    ];
    const r = buildCoverage(ops, ents, "/tmp", tmpDir);
    expect(r.rows[0]!.status).toBe("missing");
    expect(r.rows[1]!.status).toBe("covered");
  });
});

describe("renderCoverageMarkdown", () => {
  it("monta resumo + seções missing/partial/covered", () => {
    migration("001.sql", "CREATE TABLE cliente (id BIGSERIAL);");
    const ents = loadNexusEntities(tmpDir);
    const ops: DedupedOperation[] = [
      {
        operationName: "getCliente",
        category: "cliente",
        querySnippet: "",
        occurrences: 5,
        routes: ["/cliente"],
      },
      {
        operationName: "getMcpServer",
        category: "mcpserver",
        querySnippet: "",
        occurrences: 1,
        routes: ["/ia"],
      },
    ];
    const r = buildCoverage(ops, ents, "/tmp", tmpDir);
    const md = renderCoverageMarkdown(r);
    expect(md).toContain("# Coverage Nexus vs ZigChat");
    expect(md).toContain("Resumo");
    expect(md).toContain("Missing");
    expect(md).toContain("getMcpServer");
  });
});

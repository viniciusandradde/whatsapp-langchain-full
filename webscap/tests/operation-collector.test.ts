import { describe, expect, it } from "vitest";

import {
  categorize,
  dedupe,
  groupByCategory,
} from "../src/graphql/operation-collector.js";
import type { CapturedOperation } from "../src/types.js";

describe("categorize", () => {
  it("strip de verbos comuns (EN)", () => {
    expect(categorize("getCliente")).toBe("cliente");
    expect(categorize("listAtendimentos")).toBe("atendimento");
    expect(categorize("createCampanha")).toBe("campanha");
    expect(categorize("updateModeloMensagem")).toBe("modelo");
    expect(categorize("deleteHook")).toBe("hook");
  });

  it("strip de verbos PT (ZigChat usa português)", () => {
    expect(categorize("filtrarCliente")).toBe("cliente");
    expect(categorize("buscarClientePorId")).toBe("cliente");
    expect(categorize("listarDepartamentos")).toBe("departamento");
    expect(categorize("criarEmpresaVerifyToken")).toBe("empresa");
    expect(categorize("carregarMensagens")).toBe("mensagem");
    expect(categorize("contarAtendimentosAbertosUsuario")).toBe(
      "atendimento",
    );
  });

  it("extrai primeiro chunk camelCase pra categoria", () => {
    expect(categorize("AtendimentoMensagem")).toBe("atendimento");
    expect(categorize("getClienteAnotacao")).toBe("cliente");
  });

  it("não engasga em nomes sem verbo", () => {
    expect(categorize("Login")).toBe("login");
    expect(categorize("Ping")).toBe("ping");
  });
});

describe("dedupe", () => {
  it("agrupa por operationName e conta occurrences + routes", () => {
    const raw: CapturedOperation[] = [
      {
        operationName: "getCliente",
        variables: { id: 1 },
        querySnippet: "query getCliente",
        routeWhereSeen: "/cliente",
        capturedAt: "2026-05-05T00:00:00Z",
        dataKeys: ["cliente"],
      },
      {
        operationName: "getCliente",
        variables: { id: 2 },
        querySnippet: "query getCliente",
        routeWhereSeen: "/cliente",
        capturedAt: "2026-05-05T00:00:01Z",
      },
      {
        operationName: "getCliente",
        variables: { id: 3 },
        querySnippet: "query getCliente",
        routeWhereSeen: "/atendimento", // outra rota
        capturedAt: "2026-05-05T00:00:02Z",
      },
      {
        operationName: "listCampanhas",
        variables: null,
        querySnippet: "query listCampanhas",
        routeWhereSeen: "/campanha",
        capturedAt: "2026-05-05T00:00:03Z",
      },
    ];
    const out = dedupe(raw);
    expect(out).toHaveLength(2);
    const cli = out.find((o) => o.operationName === "getCliente")!;
    expect(cli.occurrences).toBe(3);
    expect(cli.routes.sort()).toEqual(["/atendimento", "/cliente"]);
    expect(cli.category).toBe("cliente");
    expect(cli.sampleVariables).toEqual({ id: 1 });
    expect(cli.sampleResponseKeys).toEqual(["cliente"]);
  });

  it("ignora ops sem operationName", () => {
    const raw: CapturedOperation[] = [
      {
        operationName: null,
        variables: null,
        querySnippet: "",
        routeWhereSeen: "/x",
        capturedAt: "",
      },
    ];
    expect(dedupe(raw)).toHaveLength(0);
  });
});

describe("groupByCategory", () => {
  it("agrupa deduped por categoria inferida", () => {
    const ops = dedupe([
      {
        operationName: "getCliente",
        variables: null,
        querySnippet: "",
        routeWhereSeen: "/x",
        capturedAt: "",
      },
      {
        operationName: "listClientes",
        variables: null,
        querySnippet: "",
        routeWhereSeen: "/x",
        capturedAt: "",
      },
      {
        operationName: "createCampanha",
        variables: null,
        querySnippet: "",
        routeWhereSeen: "/x",
        capturedAt: "",
      },
    ]);
    const g = groupByCategory(ops);
    expect(g.get("cliente")).toHaveLength(2);
    expect(g.get("campanha")).toHaveLength(1);
  });
});

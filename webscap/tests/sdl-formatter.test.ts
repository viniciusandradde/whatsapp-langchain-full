import { describe, expect, it } from "vitest";

import { formatSdl } from "../src/graphql/sdl-formatter.js";
import type { GqlSchema } from "../src/types.js";

describe("formatSdl", () => {
  it("emite schema definition + types ordenados", () => {
    const schema: GqlSchema = {
      queryType: { name: "Query" },
      mutationType: { name: "Mutation" },
      types: [
        {
          kind: "OBJECT",
          name: "Cliente",
          fields: [
            {
              name: "id",
              type: {
                kind: "NON_NULL",
                ofType: { kind: "SCALAR", name: "ID" },
              },
            },
            {
              name: "nome",
              type: { kind: "SCALAR", name: "String" },
            },
          ],
        },
        {
          kind: "OBJECT",
          name: "Atendimento",
          fields: [
            {
              name: "id",
              type: {
                kind: "NON_NULL",
                ofType: { kind: "SCALAR", name: "ID" },
              },
            },
          ],
        },
      ],
    };

    const sdl = formatSdl(schema);
    // Schema bloco
    expect(sdl).toContain("schema {");
    expect(sdl).toContain("query: Query");
    expect(sdl).toContain("mutation: Mutation");
    // Tipos ordenados alfabeticamente
    expect(sdl.indexOf("type Atendimento")).toBeLessThan(
      sdl.indexOf("type Cliente"),
    );
    // Refs com NonNull
    expect(sdl).toContain("id: ID!");
    expect(sdl).toContain("nome: String");
  });

  it("ignora introspection types (__Schema/__Type)", () => {
    const schema: GqlSchema = {
      queryType: { name: "Query" },
      types: [
        { kind: "OBJECT", name: "__Schema", fields: [] },
        { kind: "OBJECT", name: "Cliente", fields: [] },
      ],
    };
    const sdl = formatSdl(schema);
    expect(sdl).not.toContain("__Schema");
    expect(sdl).toContain("type Cliente");
  });

  it("trata ENUM + INPUT", () => {
    const schema: GqlSchema = {
      queryType: { name: "Query" },
      types: [
        {
          kind: "ENUM",
          name: "StatusAtendimento",
          enumValues: [{ name: "ABERTO" }, { name: "FECHADO" }],
        },
        {
          kind: "INPUT_OBJECT",
          name: "ClienteInput",
          inputFields: [
            { name: "nome", type: { kind: "SCALAR", name: "String" } },
          ],
        },
      ],
    };
    const sdl = formatSdl(schema);
    expect(sdl).toContain("enum StatusAtendimento");
    expect(sdl).toContain("ABERTO");
    expect(sdl).toContain("input ClienteInput");
  });
});

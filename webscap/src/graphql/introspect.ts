/**
 * Roda introspection no GraphQL do alvo via sessão Playwright.
 *
 * Sessão (cookies httpOnly + headers) é aplicada pelo browser
 * automaticamente — não precisamos extrair token manual. Em troca,
 * exigimos browser context já autenticado (storageState carregado).
 */

import type { Page } from "playwright";

import type { IntrospectionResponse } from "../types.js";

export const INTROSPECTION_QUERY = `
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
          args {
            name
            type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
            defaultValue
          }
          type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
        }
        inputFields {
          name
          type { kind name ofType { kind name ofType { kind name } } }
          defaultValue
        }
        enumValues(includeDeprecated: true) { name }
      }
    }
  }
`.trim();

export async function runIntrospection(
  page: Page,
  graphqlPath: string,
): Promise<IntrospectionResponse> {
  const result = await page.evaluate(
    async ({ url, query }) => {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          operationName: "IntrospectionQuery",
          query,
          variables: {},
        }),
      });
      return { status: r.status, body: await r.text() };
    },
    { url: graphqlPath, query: INTROSPECTION_QUERY },
  );

  if (result.status !== 200) {
    throw new Error(
      `Introspection HTTP ${result.status}: ${result.body.slice(0, 300)}`,
    );
  }

  const parsed = JSON.parse(result.body) as IntrospectionResponse;
  if (parsed.errors && parsed.errors.length > 0) {
    throw new Error(
      `Introspection GraphQL errors: ${parsed.errors
        .map((e) => e.message)
        .join("; ")}`,
    );
  }
  if (!parsed.data?.__schema) {
    throw new Error("Resposta sem __schema — introspection desabilitada?");
  }
  return parsed;
}

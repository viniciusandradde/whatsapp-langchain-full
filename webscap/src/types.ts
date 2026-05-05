/**
 * Tipos compartilhados pelos módulos do scraper.
 *
 * Mantido pequeno e centralizado: schema GraphQL, payloads de captura,
 * resultados de coverage. Tipos vivos usados por SDL formatter,
 * operation collector e reports.
 */

// ---- Config ----

export interface ScrapConfig {
  baseUrl: string;
  graphqlPath: string; // ex: "/api/graphql"
  authStorageFile: string; // ex: "auth.json"
  outputDir: string; // ex: "output"
  rateLimitRps: number; // máximo de requests/s do crawler
  retryMaxAttempts: number;
  retryBaseMs: number;
  navTimeoutMs: number;
}

export const DEFAULT_CONFIG: ScrapConfig = {
  baseUrl: "https://dev.zigchat.com.br",
  graphqlPath: "/api/graphql",
  authStorageFile: "auth.json",
  outputDir: "output",
  rateLimitRps: 2,
  retryMaxAttempts: 3,
  retryBaseMs: 500,
  navTimeoutMs: 30_000,
};

// ---- GraphQL schema (introspection raw) ----

export interface GqlIntrospectionType {
  kind: string;
  name?: string | null;
  description?: string | null;
  fields?: GqlField[] | null;
  inputFields?: GqlInputField[] | null;
  enumValues?: Array<{ name: string }> | null;
  ofType?: GqlIntrospectionType | null;
}

export interface GqlField {
  name: string;
  description?: string | null;
  args?: GqlInputField[];
  type: GqlIntrospectionType;
}

export interface GqlInputField {
  name: string;
  type: GqlIntrospectionType;
  defaultValue?: string | null;
}

export interface GqlSchema {
  queryType?: { name: string } | null;
  mutationType?: { name: string } | null;
  subscriptionType?: { name: string } | null;
  types: GqlIntrospectionType[];
}

export interface IntrospectionResponse {
  data?: { __schema: GqlSchema };
  errors?: Array<{ message: string }>;
}

// ---- Operations capturadas em runtime ----

export interface CapturedOperation {
  operationName: string | null;
  variables: unknown;
  querySnippet: string;
  routeWhereSeen: string;
  capturedAt: string; // ISO
  status?: number;
  errorCount?: number;
  dataKeys?: string[];
}

export interface DedupedOperation {
  operationName: string;
  /** Primeira variante de query vista (cobre 99% dos casos). */
  querySnippet: string;
  /** Quantas vezes o operation foi observado. */
  occurrences: number;
  routes: string[];
  /** Categoria inferida pelo prefixo (ex: "cliente", "atendimento"). */
  category: string;
  /** 1 exemplo real de variables + 1 de payload de resposta. */
  sampleVariables?: unknown;
  sampleResponseKeys?: string[];
}

// ---- Inventory de captura ----

export interface RouteVisit {
  url: string;
  finalUrl: string;
  ok: boolean;
  status?: number;
  errorMessage?: string;
  loadMs?: number;
  screenshotPath?: string;
  harPath?: string;
  capturedAt: string;
}

export interface CaptureInventory {
  baseUrl: string;
  capturedAt: string;
  routes: RouteVisit[];
  operations: DedupedOperation[];
  schemaSummaryPath?: string;
}

// ---- Coverage ----

export interface NexusEntity {
  /** Nome canônico (snake_case da tabela ex: "cliente", "campanha"). */
  name: string;
  /** Path da migration onde foi criada (primeira). */
  source: string;
  /** Heurística — quantas colunas modeladas. */
  columnsCount: number;
}

export interface CoverageRow {
  zigchatCategory: string;
  zigchatOpsCount: number;
  zigchatOps: string[];
  nexusEntity: NexusEntity | null;
  status: "covered" | "partial" | "missing";
  notes?: string;
}

export interface CoverageReport {
  generatedAt: string;
  zigchatRunPath: string;
  nexusMigrationsDir: string;
  summary: {
    totalCategories: number;
    covered: number;
    partial: number;
    missing: number;
  };
  rows: CoverageRow[];
}

/**
 * Cliente HTTP tipado para consumo server-side da API administrativa.
 *
 * IMPORTANTE: Este módulo só pode ser usado em Server Components e Route Handlers.
 * Nunca importe este arquivo em componentes "use client" — toda comunicação
 * entre frontend e API acontece no servidor, protegida pelo token interno.
 *
 * O frontend (Next.js) faz fetch server-side para a API (FastAPI) usando
 * INTERNAL_SERVICE_TOKEN. Isso é separado da autenticação do usuário (Better Auth).
 */
import "server-only";
import { cookies, headers as nextHeaders } from "next/headers";
import { auth } from "@/lib/auth";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

// --- Tipos de resposta da API ---

export interface Chat {
  phone_number: string;
  agent_id: string;
  thread_id: string;
  last_message: string;
  last_message_at: string | null;
  message_count: number;
  created_at: string | null;
}

export interface ChatsResponse {
  chats: Chat[];
  total: number;
  limit: number;
  offset: number;
}

export interface Message {
  id: number;
  agent_id: string;
  incoming_message: string;
  media_type: string | null;
  normalized_input: string | null;
  media_processing_status: string | null;
  response: string | null;
  status: string;
  created_at: string | null;
  processed_at: string | null;
  media_processing_error: string | null;
  error: string | null;
}

export interface ChatMessagesResponse {
  phone_number: string;
  messages: Message[];
}

export interface AgentsResponse {
  agents: string[];
}

export interface MetricsResponse {
  total_today: number;
  failures_today: number;
  avg_processing_time_seconds: number | null;
  queue_size: number;
}

export interface QueueMessage {
  id: number;
  phone_number: string;
  agent_id: string;
  incoming_message: string;
  status: string;
  created_at: string | null;
  attempts: number;
  error: string | null;
}

export interface QueueResponse {
  counters: {
    queued: number;
    processing: number;
    done: number;
    failed: number;
  };
  messages: QueueMessage[];
}

// --- Multi-tenancy ---

export interface Empresa {
  id: number;
  nome: string;
  slug: string;
  doc: string | null;
  plano: string;
  status: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EmpresasResponse {
  empresas: Empresa[];
}

export type ConexaoProvider = "twilio_sandbox" | "twilio_prod" | "waba";
export type ConexaoStatus = "active" | "disabled" | "error";

export interface Conexao {
  id: number;
  empresa_id: number;
  provider: ConexaoProvider;
  sid: string | null;
  from_number: string;
  display_name: string | null;
  default_agent_id: string;
  status: ConexaoStatus;
  is_default: boolean;
  payload_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ConexoesResponse {
  conexoes: Conexao[];
}

export interface ConexaoInput {
  provider: ConexaoProvider;
  sid?: string | null;
  from_number: string;
  display_name?: string | null;
  default_agent_id?: string;
  status?: ConexaoStatus;
  is_default?: boolean;
  payload_json?: Record<string, unknown>;
}

// --- Painel de modelos LLM por agente ---

export type ModelType = "chat" | "media";

export interface ModelInfo {
  id: string;
  label: string;
  type: ModelType;
}

export interface ModelsResponse {
  models: ModelInfo[];
}

export interface AgentLLMConfig {
  agent_id: string;
  chat_model: string;
  midia_model: string;
  chat_model_override: string | null;
  midia_model_override: string | null;
}

// --- Painel de traces (LangSmith) ---

export interface TraceInfo {
  run_id: string;
  name: string | null;
  status: string | null;
  start_time: string | null;
  end_time: string | null;
  latency_ms: number | null;
  total_tokens: number | null;
  thread_id: string | null;
  smith_url: string;
}

export interface TracesResponse {
  traces: TraceInfo[];
}

// --- Configuração ---

// URL interna da API — em Docker usa o nome do serviço (http://api:8000),
// em dev local usa localhost diretamente
const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const SERVICE_TOKEN = process.env.INTERNAL_SERVICE_TOKEN || "";

// --- Função base de fetch ---

interface ApiFetchOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  body?: unknown;
}

async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  ensureFrontendRuntimeConfig();

  const { method = "GET", body } = options;
  const url = `${API_URL}${path}`;

  const headers: Record<string, string> = {
    Authorization: `Bearer ${SERVICE_TOKEN}`,
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  // Multi-tenancy: a API espera X-User-Id (derivado da Better Auth
  // session) e opcionalmente X-Empresa-Id (cookie definido pelo
  // EmpresaSwitcher). Sem session válida o request dispara o redirect
  // de requireSession() — esse path não é exercitado em chamadas server-
  // only que já passaram por ele.
  try {
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    if (session?.user?.id) {
      headers["X-User-Id"] = session.user.id;
    }
  } catch {
    // Sem session — admin endpoints retornarão 401, comportamento esperado.
  }

  try {
    const empresaCookie = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;
    if (empresaCookie) {
      headers["X-Empresa-Id"] = empresaCookie;
    }
  } catch {
    // Sem contexto de cookies (build estático, etc.) — backend usa default.
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(
      `API error: ${response.status} ${response.statusText} (${path})`
    );
  }

  return response.json() as Promise<T>;
}

function toNumber(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }

  return 0;
}

function toNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === "number") {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }

  return null;
}

function normalizeMetricsResponse(data: unknown): MetricsResponse {
  const metrics =
    typeof data === "object" && data !== null
      ? (data as Record<string, unknown>)
      : {};

  return {
    total_today: toNumber(metrics.total_today),
    failures_today: toNumber(metrics.failures_today),
    avg_processing_time_seconds: toNullableNumber(
      metrics.avg_processing_time_seconds
    ),
    queue_size: toNumber(metrics.queue_size),
  };
}

// --- Funções tipadas ---

export async function getAgents(): Promise<AgentsResponse> {
  return apiFetch<AgentsResponse>("/api/agents");
}

export async function getChats(
  limit: number = 20,
  offset: number = 0
): Promise<ChatsResponse> {
  return apiFetch<ChatsResponse>(
    `/api/chats?limit=${limit}&offset=${offset}`
  );
}

export async function getChatMessages(
  phone: string,
  limit: number = 50,
  offset: number = 0
): Promise<ChatMessagesResponse> {
  return apiFetch<ChatMessagesResponse>(
    `/api/chats/${encodeURIComponent(phone)}?limit=${limit}&offset=${offset}`
  );
}

export async function getMetrics(): Promise<MetricsResponse> {
  const data = await apiFetch<unknown>("/api/metrics");
  return normalizeMetricsResponse(data);
}

export async function getQueue(): Promise<QueueResponse> {
  return apiFetch<QueueResponse>("/api/queue");
}

export async function getMyEmpresas(): Promise<EmpresasResponse> {
  return apiFetch<EmpresasResponse>("/api/empresas");
}

export async function getConexoes(): Promise<ConexoesResponse> {
  return apiFetch<ConexoesResponse>("/api/conexoes");
}

export async function createConexao(body: ConexaoInput): Promise<Conexao> {
  return apiFetch<Conexao>("/api/conexoes", { method: "POST", body });
}

export async function updateConexao(
  id: number,
  body: ConexaoInput
): Promise<Conexao> {
  return apiFetch<Conexao>(`/api/conexoes/${id}`, { method: "PUT", body });
}

export async function disableConexao(id: number): Promise<void> {
  await apiFetch<void>(`/api/conexoes/${id}`, { method: "DELETE" });
}

export async function getModels(): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>("/api/models");
}

export async function getAgentConfig(
  agentId: string
): Promise<AgentLLMConfig> {
  return apiFetch<AgentLLMConfig>(
    `/api/agents/${encodeURIComponent(agentId)}/config`
  );
}

export async function updateAgentConfig(
  agentId: string,
  body: { chat_model?: string | null; midia_model?: string | null }
): Promise<AgentLLMConfig> {
  return apiFetch<AgentLLMConfig>(
    `/api/agents/${encodeURIComponent(agentId)}/config`,
    { method: "PUT", body }
  );
}

export async function getTraces(params: {
  limit?: number;
  thread_id?: string;
} = {}): Promise<TracesResponse> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.thread_id) q.set("thread_id", params.thread_id);
  const qs = q.toString();
  return apiFetch<TracesResponse>(`/api/traces${qs ? `?${qs}` : ""}`);
}

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
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

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

// --- Configuração ---

// URL interna da API — em Docker usa o nome do serviço (http://api:8000),
// em dev local usa localhost diretamente
const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const SERVICE_TOKEN = process.env.INTERNAL_SERVICE_TOKEN || "";

// --- Função base de fetch ---

async function apiFetch<T>(path: string): Promise<T> {
  ensureFrontendRuntimeConfig();

  const url = `${API_URL}${path}`;

  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${SERVICE_TOKEN}`,
    },
    // Desabilita cache para dados operacionais em tempo real
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

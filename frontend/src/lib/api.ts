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
  /** Role do user logado nessa empresa (vindo do GET /api/empresas). */
  my_role?: "admin" | "operator" | "viewer" | null;
}

export interface EmpresaInput {
  nome: string;
  slug: string;
  plano?: string;
  doc?: string | null;
}

export interface EmpresaUpdateInput {
  nome?: string;
  slug?: string;
  plano?: string;
  doc?: string | null;
  status?: string;
}

export interface EmpresaMembro {
  empresa_id: number;
  user_id: string;
  role: "admin" | "operator" | "viewer";
  is_default: boolean;
  joined_at: string;
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

// --- M3 CRM Light: Cliente + Atendimento ---

export interface Cliente {
  id: number;
  empresa_id: number;
  telefone: string;
  nome: string | null;
  email: string | null;
  doc: string | null;
  status: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  tags: string[];
}

export interface ClienteAnotacao {
  id: number;
  cliente_id: number;
  user_id: string;
  conteudo: string;
  created_at: string;
}

export interface ClienteDetail {
  cliente: Cliente;
  anotacoes: ClienteAnotacao[];
}

export interface ClientesResponse {
  clientes: Cliente[];
}

export type AtendimentoStatus =
  | "aguardando"
  | "em_andamento"
  | "resolvido"
  | "abandonado";

export type TipoVisualizacao = "meus" | "aguardando" | "grupos" | "outros";

export interface Atendimento {
  id: number;
  empresa_id: number;
  cliente_id: number;
  conexao_id: number;
  agente_atual: string;
  status: AtendimentoStatus;
  assigned_to_user_id: string | null;
  last_message_at: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  cliente_nome: string | null;
  cliente_telefone: string | null;
}

export interface AtendimentosResponse {
  atendimentos: Atendimento[];
}

export interface AtendimentoMensagem {
  id: number;
  agent_id: string;
  incoming_message: string;
  media_url: string | null;
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

export interface AtendimentoMensagensResponse {
  atendimento_id: number;
  mensagens: AtendimentoMensagem[];
}

// --- M4.b: Quick replies (modelo_mensagem) ---

export interface ModeloMensagem {
  id: number;
  empresa_id: number;
  titulo: string;
  conteudo: string;
  atalho: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModeloMensagemInput {
  titulo: string;
  conteudo: string;
  atalho?: string | null;
}

export interface ModelosMensagemResponse {
  modelos: ModeloMensagem[];
}

// --- M4.d: Webhooks (hook + hook_log) ---

export type HookEvento =
  | "mensagem.recebida"
  | "atendimento.aberto"
  | "atendimento.atendido"
  | "atendimento.fechado"
  | "atendimento.transferido";

export interface Hook {
  id: number;
  empresa_id: number;
  nome: string;
  evento: HookEvento;
  url: string;
  secret: string | null;
  ativo: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface HookInput {
  nome: string;
  evento: HookEvento;
  url: string;
  secret?: string | null;
  ativo?: boolean;
}

export interface HookLog {
  id: number;
  hook_id: number;
  evento: string;
  status_code: number | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface HooksResponse {
  hooks: Hook[];
}

export interface HookLogsResponse {
  logs: HookLog[];
}

// --- M5.b: AgenteIA Configurável ---

export interface AgenteIAConfig {
  empresa_id: number;
  agent_id: string;
  system_prompt_override: string | null;
  temperatura: number | null;
  ativo: boolean;
  updated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgenteIAConfigInput {
  system_prompt_override?: string | null;
  temperatura?: number | null;
  ativo?: boolean;
}

export interface AgenteIAConfigResponse {
  config: AgenteIAConfig | null;
  default_system_prompt: string;
}

// --- M5.c: Base de Conhecimento (RAG) ---

export interface DocumentoConhecimento {
  id: number;
  empresa_id: number;
  titulo: string;
  conteudo: string;
  tags: string[];
  ativo: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentoConhecimentoInput {
  titulo: string;
  conteudo: string;
  tags?: string[];
  ativo?: boolean;
}

export interface DocumentosConhecimentoResponse {
  documentos: DocumentoConhecimento[];
}

export interface BuscarDocumentoResultado {
  documento: DocumentoConhecimento;
  // M5.c.1: busca retorna chunk individual + reason do reranker
  chunk_idx: number;
  chunk_conteudo: string;
  score: number;
  reason: string | null;
}

export interface BuscarDocumentosResponse {
  resultados: BuscarDocumentoResultado[];
}

// --- M5.d: Variáveis de Ambiente ---

export interface VariavelAmbiente {
  id: number;
  empresa_id: number;
  nome: string;
  valor: string;
  descricao: string | null;
  ativo: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface VariavelAmbienteInput {
  nome: string;
  valor: string;
  descricao?: string | null;
  ativo?: boolean;
}

export interface VariaveisResponse {
  variaveis: VariavelAmbiente[];
}

// --- M6.a: Departamento + Horário + Feriado ---

export interface Departamento {
  id: number;
  empresa_id: number;
  nome: string;
  descricao: string | null;
  ativo: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DepartamentoInput {
  nome: string;
  descricao?: string | null;
  ativo?: boolean;
}

export interface DepartamentosResponse {
  departamentos: Departamento[];
}

export interface HorarioFuncionamento {
  id: number;
  empresa_id: number;
  dia_semana: number;
  hora_inicio: string;
  hora_fim: string;
  departamento_id: number | null;
  ativo: boolean;
  created_at: string;
}

export interface HorarioFuncionamentoInput {
  dia_semana: number;
  hora_inicio: string;
  hora_fim: string;
  departamento_id?: number | null;
  ativo?: boolean;
}

export interface HorariosResponse {
  horarios: HorarioFuncionamento[];
}

export interface Feriado {
  id: number;
  empresa_id: number;
  data: string;
  descricao: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface FeriadoInput {
  data: string;
  descricao?: string | null;
}

export interface FeriadosResponse {
  feriados: Feriado[];
}

// --- M5.a: Google Calendar ---

export interface GoogleCalendarConfig {
  empresa_id: number;
  google_email: string | null;
  calendar_id: string;
  timezone: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
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

export async function createEmpresa(body: EmpresaInput): Promise<Empresa> {
  return apiFetch<Empresa>("/api/empresas", { method: "POST", body });
}

export async function updateEmpresa(
  id: number,
  body: EmpresaUpdateInput
): Promise<Empresa> {
  return apiFetch<Empresa>(`/api/empresas/${id}`, { method: "PUT", body });
}

export async function getEmpresaMembers(
  empresaId: number
): Promise<EmpresaMembro[]> {
  return apiFetch<EmpresaMembro[]>(
    `/api/empresas/${empresaId}/membros`
  );
}

export async function addEmpresaMember(
  empresaId: number,
  body: { user_id: string; role: "admin" | "operator" | "viewer" }
): Promise<EmpresaMembro> {
  return apiFetch<EmpresaMembro>(`/api/empresas/${empresaId}/membros`, {
    method: "POST",
    body,
  });
}

export async function updateMemberRole(
  empresaId: number,
  userId: string,
  role: "admin" | "operator" | "viewer"
): Promise<EmpresaMembro> {
  return apiFetch<EmpresaMembro>(
    `/api/empresas/${empresaId}/membros/${encodeURIComponent(userId)}`,
    { method: "PUT", body: { role } }
  );
}

export async function removeEmpresaMember(
  empresaId: number,
  userId: string
): Promise<void> {
  await apiFetch<void>(
    `/api/empresas/${empresaId}/membros/${encodeURIComponent(userId)}`,
    { method: "DELETE" }
  );
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

// --- Clientes ---

export async function getClientes(params: {
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ClientesResponse> {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return apiFetch<ClientesResponse>(`/api/clientes${qs ? `?${qs}` : ""}`);
}

export async function getCliente(id: number): Promise<ClienteDetail> {
  return apiFetch<ClienteDetail>(`/api/clientes/${id}`);
}

export async function addClienteAnotacao(
  id: number,
  conteudo: string
): Promise<ClienteAnotacao> {
  return apiFetch<ClienteAnotacao>(`/api/clientes/${id}/anotacoes`, {
    method: "POST",
    body: { conteudo },
  });
}

export async function addClienteTag(id: number, tag: string): Promise<void> {
  await apiFetch<void>(`/api/clientes/${id}/tags`, {
    method: "POST",
    body: { tag },
  });
}

export async function removeClienteTag(
  id: number,
  tag: string
): Promise<void> {
  await apiFetch<void>(
    `/api/clientes/${id}/tags/${encodeURIComponent(tag)}`,
    { method: "DELETE" }
  );
}

// --- Atendimentos ---

export async function getAtendimentos(params: {
  tipo?: TipoVisualizacao;
  limit?: number;
  offset?: number;
} = {}): Promise<AtendimentosResponse> {
  const q = new URLSearchParams();
  if (params.tipo) q.set("tipo", params.tipo);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return apiFetch<AtendimentosResponse>(
    `/api/atendimentos${qs ? `?${qs}` : ""}`
  );
}

export async function getAtendimento(id: number): Promise<Atendimento> {
  return apiFetch<Atendimento>(`/api/atendimentos/${id}`);
}

export async function getAtendimentoMensagens(
  id: number,
  limit: number = 200
): Promise<AtendimentoMensagensResponse> {
  return apiFetch<AtendimentoMensagensResponse>(
    `/api/atendimentos/${id}/mensagens?limit=${limit}`
  );
}

export async function responderAtendimento(
  id: number,
  conteudo: string
): Promise<{ mensagem: AtendimentoMensagem }> {
  return apiFetch<{ mensagem: AtendimentoMensagem }>(
    `/api/atendimentos/${id}/responder`,
    { method: "POST", body: { conteudo } }
  );
}

// --- Modelos de mensagem (quick replies) ---

export async function getModelosMensagem(
  search?: string
): Promise<ModelosMensagemResponse> {
  const qs = search ? `?search=${encodeURIComponent(search)}` : "";
  return apiFetch<ModelosMensagemResponse>(`/api/modelos${qs}`);
}

export async function createModeloMensagem(
  body: ModeloMensagemInput
): Promise<ModeloMensagem> {
  return apiFetch<ModeloMensagem>(`/api/modelos`, { method: "POST", body });
}

export async function updateModeloMensagem(
  id: number,
  body: ModeloMensagemInput
): Promise<ModeloMensagem> {
  return apiFetch<ModeloMensagem>(`/api/modelos/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteModeloMensagem(id: number): Promise<void> {
  await apiFetch<void>(`/api/modelos/${id}`, { method: "DELETE" });
}

// --- Hooks (webhooks configuráveis) ---

export async function getHooks(evento?: HookEvento): Promise<HooksResponse> {
  const qs = evento ? `?evento=${encodeURIComponent(evento)}` : "";
  return apiFetch<HooksResponse>(`/api/hooks${qs}`);
}

export async function getHookEventos(): Promise<{ eventos: HookEvento[] }> {
  return apiFetch<{ eventos: HookEvento[] }>(`/api/hooks/eventos`);
}

export async function createHook(body: HookInput): Promise<Hook> {
  return apiFetch<Hook>(`/api/hooks`, { method: "POST", body });
}

export async function updateHook(id: number, body: HookInput): Promise<Hook> {
  return apiFetch<Hook>(`/api/hooks/${id}`, { method: "PUT", body });
}

export async function deleteHook(id: number): Promise<void> {
  await apiFetch<void>(`/api/hooks/${id}`, { method: "DELETE" });
}

export async function getHookLogs(
  id: number,
  limit: number = 20
): Promise<HookLogsResponse> {
  return apiFetch<HookLogsResponse>(
    `/api/hooks/${id}/logs?limit=${limit}`
  );
}

// --- Google Calendar ---

export async function getGoogleCalendarConfig(): Promise<GoogleCalendarConfig | null> {
  return apiFetch<GoogleCalendarConfig | null>("/api/google-calendar/config");
}

export async function getGoogleCalendarOAuthUrl(): Promise<{ authorize_url: string }> {
  return apiFetch<{ authorize_url: string }>("/api/google-calendar/oauth/init");
}

export async function disconnectGoogleCalendar(): Promise<void> {
  await apiFetch<void>("/api/google-calendar/config", { method: "DELETE" });
}

// --- AgenteIA configurável ---

export async function getAgenteIAConfig(
  agentId: string
): Promise<AgenteIAConfigResponse> {
  return apiFetch<AgenteIAConfigResponse>(
    `/api/agents/${encodeURIComponent(agentId)}/agente-ia-config`
  );
}

export async function updateAgenteIAConfig(
  agentId: string,
  body: AgenteIAConfigInput
): Promise<AgenteIAConfig> {
  return apiFetch<AgenteIAConfig>(
    `/api/agents/${encodeURIComponent(agentId)}/agente-ia-config`,
    { method: "PUT", body }
  );
}

export async function resetAgenteIAConfig(agentId: string): Promise<void> {
  await apiFetch<void>(
    `/api/agents/${encodeURIComponent(agentId)}/agente-ia-config`,
    { method: "DELETE" }
  );
}

export async function claimAtendimento(id: number): Promise<Atendimento> {
  return apiFetch<Atendimento>(`/api/atendimentos/${id}/claim`, {
    method: "POST",
  });
}

export async function closeAtendimento(
  id: number,
  status: "resolvido" | "abandonado" = "resolvido"
): Promise<Atendimento> {
  return apiFetch<Atendimento>(`/api/atendimentos/${id}/close`, {
    method: "POST",
    body: { status },
  });
}

export async function transferAtendimento(
  id: number,
  user_id: string
): Promise<Atendimento> {
  return apiFetch<Atendimento>(`/api/atendimentos/${id}/transfer`, {
    method: "POST",
    body: { user_id },
  });
}

// --- M5.c: Base de Conhecimento ---

export async function getDocumentosConhecimento(): Promise<DocumentosConhecimentoResponse> {
  return apiFetch<DocumentosConhecimentoResponse>(`/api/base-conhecimento`);
}

export async function createDocumentoConhecimento(
  body: DocumentoConhecimentoInput
): Promise<DocumentoConhecimento> {
  return apiFetch<DocumentoConhecimento>(`/api/base-conhecimento`, {
    method: "POST",
    body,
  });
}

export async function updateDocumentoConhecimento(
  id: number,
  body: DocumentoConhecimentoInput
): Promise<DocumentoConhecimento> {
  return apiFetch<DocumentoConhecimento>(`/api/base-conhecimento/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteDocumentoConhecimento(id: number): Promise<void> {
  await apiFetch<void>(`/api/base-conhecimento/${id}`, { method: "DELETE" });
}

export async function buscarDocumentosConhecimento(
  query: string,
  k: number = 3
): Promise<BuscarDocumentosResponse> {
  return apiFetch<BuscarDocumentosResponse>(`/api/base-conhecimento/buscar`, {
    method: "POST",
    body: { query, k },
  });
}

export async function uploadDocumentoConhecimento(
  arquivo: File,
  options: { titulo?: string; tags?: string[] } = {}
): Promise<DocumentoConhecimento> {
  ensureFrontendRuntimeConfig();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${SERVICE_TOKEN}`,
  };
  try {
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    if (session?.user?.id) headers["X-User-Id"] = session.user.id;
  } catch {
    /* sem sessão — backend devolve 401 */
  }
  try {
    const empresaCookie = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;
    if (empresaCookie) headers["X-Empresa-Id"] = empresaCookie;
  } catch {
    /* sem cookies — backend usa default */
  }

  const form = new FormData();
  form.append("arquivo", arquivo);
  if (options.titulo) form.append("titulo", options.titulo);
  if (options.tags?.length) form.append("tags", options.tags.join(","));

  const response = await fetch(`${API_URL}/api/base-conhecimento/upload`, {
    method: "POST",
    headers,
    body: form,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* response não é JSON */
    }
    throw new Error(`Upload falhou (${response.status}): ${detail}`);
  }
  return (await response.json()) as DocumentoConhecimento;
}

// --- M5.d: Variáveis de Ambiente ---

export async function getVariaveis(): Promise<VariaveisResponse> {
  return apiFetch<VariaveisResponse>(`/api/variaveis`);
}

export async function createVariavel(
  body: VariavelAmbienteInput
): Promise<VariavelAmbiente> {
  return apiFetch<VariavelAmbiente>(`/api/variaveis`, {
    method: "POST",
    body,
  });
}

export async function updateVariavel(
  id: number,
  body: VariavelAmbienteInput
): Promise<VariavelAmbiente> {
  return apiFetch<VariavelAmbiente>(`/api/variaveis/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteVariavel(id: number): Promise<void> {
  await apiFetch<void>(`/api/variaveis/${id}`, { method: "DELETE" });
}

// --- M6.a: Departamentos / Horários / Feriados ---

export async function getDepartamentos(): Promise<DepartamentosResponse> {
  return apiFetch<DepartamentosResponse>(`/api/departamentos`);
}

export async function createDepartamento(
  body: DepartamentoInput
): Promise<Departamento> {
  return apiFetch<Departamento>(`/api/departamentos`, {
    method: "POST",
    body,
  });
}

export async function updateDepartamento(
  id: number,
  body: DepartamentoInput
): Promise<Departamento> {
  return apiFetch<Departamento>(`/api/departamentos/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteDepartamento(id: number): Promise<void> {
  await apiFetch<void>(`/api/departamentos/${id}`, { method: "DELETE" });
}

export async function getHorarios(): Promise<HorariosResponse> {
  return apiFetch<HorariosResponse>(`/api/horarios`);
}

export async function createHorario(
  body: HorarioFuncionamentoInput
): Promise<HorarioFuncionamento> {
  return apiFetch<HorarioFuncionamento>(`/api/horarios`, {
    method: "POST",
    body,
  });
}

export async function deleteHorario(id: number): Promise<void> {
  await apiFetch<void>(`/api/horarios/${id}`, { method: "DELETE" });
}

export async function getHorariosStatus(): Promise<{ is_open: boolean }> {
  return apiFetch<{ is_open: boolean }>(`/api/horarios/status`);
}

export async function getFeriados(): Promise<FeriadosResponse> {
  return apiFetch<FeriadosResponse>(`/api/feriados`);
}

export async function createFeriado(
  body: FeriadoInput
): Promise<Feriado> {
  return apiFetch<Feriado>(`/api/feriados`, { method: "POST", body });
}

export async function deleteFeriado(id: number): Promise<void> {
  await apiFetch<void>(`/api/feriados/${id}`, { method: "DELETE" });
}

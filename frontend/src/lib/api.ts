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

export type UserStatus = "active" | "disabled";

export interface EmpresaMembro {
  empresa_id: number;
  user_id: string;
  role: "admin" | "operator" | "viewer";
  is_default: boolean;
  joined_at: string;
  /** Email do user (JOIN com auth.user em list_members). */
  email?: string | null;
  /** Status do user — "active" | "disabled". Pode ser undefined em
   * payloads antigos antes da migration 024. */
  status?: UserStatus | null;
}

export interface EmpresasResponse {
  empresas: Empresa[];
}

export type ConexaoProvider =
  | "twilio_sandbox"
  | "twilio_prod"
  | "waba"
  | "evolution";
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
  doc: string | null; // legacy
  status: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  tags: string[];
  // Fase 1.A enrich
  tipo_pessoa: "PF" | "PJ" | null;
  cpf: string | null;
  cnpj: string | null;
  rg: string | null;
  razao_social: string | null;
  nome_fantasia: string | null;
  data_nascimento: string | null;
  genero: string | null;
  cep: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  cidade: string | null;
  uf: string | null;
  pais: string;
  segmento: string | null;
  lifecycle_stage:
    | "lead"
    | "qualified"
    | "opportunity"
    | "customer"
    | "evangelist"
    | "churned"
    | null;
  score: number | null;
  source: string | null;
  responsavel_user_id: string | null;
  valor_estimado_brl: number | null;
  instagram: string | null;
  linkedin: string | null;
  facebook: string | null;
  website: string | null;
  email_alternativo: string | null;
  telefone_alternativo: string | null;
  locale: string;
  timezone: string;
  avatar_url: string | null;
  last_interaction_at: string | null;
  notes: string | null;
  // Sprint 3 paridade ZigChat (mig 046)
  whatsapp_state: string | null;
  numero_verificado: boolean;
  whatsapp_lid: string | null;
  remote_id: string | null;
  msg_apos_encerramento: string | null;
  field_1: string | null;
  field_2: string | null;
  field_3: string | null;
  field_4: string | null;
  field_5: string | null;
  ignora_inatividade: boolean;
  desconsidera_turno: boolean;
}

export type ClienteUpdateInput = Partial<
  Omit<
    Cliente,
    | "id"
    | "empresa_id"
    | "telefone"
    | "doc"
    | "status"
    | "config"
    | "created_at"
    | "updated_at"
    | "tags"
    | "last_interaction_at"
  >
>;

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
  // Sprint 3 paridade ZigChat (mig 047)
  protocolo: string | null;
  qtde_resposta_invalida: number;
  iniciado_cliente: boolean;
  finalizado_por_user_id: string | null;
  solicitou_encerramento: boolean;
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
  pasta_id: number | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentoConhecimentoInput {
  titulo: string;
  conteudo: string;
  tags?: string[];
  ativo?: boolean;
  pasta_id?: number | null;
}

export interface DocumentosConhecimentoResponse {
  documentos: DocumentoConhecimento[];
}

// E2.C M7: Pastas da base de conhecimento
export interface Pasta {
  id: number;
  empresa_id: number;
  nome: string;
  parent_id: number | null;
  descricao: string | null;
  created_by_user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  docs_count: number | null;
}

export interface PastasResponse {
  items: Pasta[];
}

export interface PastaInput {
  nome: string;
  parent_id?: number | null;
  descricao?: string | null;
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
  parent_id: number | null;
  users_count: number | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DepartamentoInput {
  nome: string;
  descricao?: string | null;
  ativo?: boolean;
  parent_id?: number | null;
}

export interface DepartamentosResponse {
  departamentos: Departamento[];
}

export interface DepartamentoUser {
  user_id: string;
  email: string | null;
  name: string | null;
  assigned_at: string | null;
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
  aprovador_telefone?: string | null;
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

export async function setMemberStatus(
  empresaId: number,
  userId: string,
  status: UserStatus
): Promise<{ user_id: string; status: UserStatus }> {
  return apiFetch<{ user_id: string; status: UserStatus }>(
    `/api/empresas/${empresaId}/membros/${encodeURIComponent(userId)}/status`,
    { method: "PUT", body: { status } }
  );
}

export async function getMemberStatus(
  userId: string
): Promise<{ user_id: string; status: UserStatus }> {
  return apiFetch<{ user_id: string; status: UserStatus }>(
    `/api/empresas/users/${encodeURIComponent(userId)}/status`
  );
}

export interface LoginEvent {
  id: number;
  user_id: string | null;
  email: string | null;
  event_type:
    | "login_success"
    | "login_failed"
    | "logout"
    | "password_reset_requested"
    | "password_changed"
    | "session_blocked_disabled";
  ip_address: string | null;
  user_agent: string | null;
  reason: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
}

export async function getLoginEvents(params?: {
  userId?: string;
  email?: string;
  eventType?: string;
  limit?: number;
}): Promise<{ events: LoginEvent[] }> {
  const qs = new URLSearchParams();
  if (params?.userId) qs.set("user_id", params.userId);
  if (params?.email) qs.set("email", params.email);
  if (params?.eventType) qs.set("event_type", params.eventType);
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<{ events: LoginEvent[] }>(
    `/api/security/login-events${suffix}`
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

export interface TestEvolutionResult {
  ok: boolean;
  state?: string | null;
  instance_name?: string | null;
  error?: string | null;
}

export async function testEvolutionConnection(body: {
  api_url: string;
  api_key: string;
  instance_name: string;
}): Promise<TestEvolutionResult> {
  return apiFetch<TestEvolutionResult>("/api/conexoes/test-evolution", {
    method: "POST",
    body,
  });
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

export async function updateCliente(
  id: number,
  body: ClienteUpdateInput
): Promise<Cliente> {
  return apiFetch<Cliente>(`/api/clientes/${id}`, {
    method: "PUT",
    body,
  });
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

export async function updateGoogleCalendarConfig(body: {
  aprovador_telefone?: string | null;
}): Promise<GoogleCalendarConfig> {
  return apiFetch<GoogleCalendarConfig>("/api/google-calendar/config", {
    method: "PUT",
    body,
  });
}

// --- Calendar Regras (S3) ---

export interface CalendarRegras {
  empresa_id: number;
  hora_inicio: string;
  hora_fim: string;
  antecedencia_minima_minutos: number;
  intervalo_entre_minutos: number;
  dias_semana_permitidos: number[];
  dias_bloqueados: string[];
  requer_aprovacao: boolean;
  created_at: string;
  updated_at: string;
}

export async function getCalendarRegras(): Promise<CalendarRegras> {
  return apiFetch<CalendarRegras>("/api/calendar/regras");
}

export async function updateCalendarRegras(body: {
  hora_inicio?: string;
  hora_fim?: string;
  antecedencia_minima_minutos?: number;
  intervalo_entre_minutos?: number;
  dias_semana_permitidos?: number[];
  dias_bloqueados?: string[];
  requer_aprovacao?: boolean;
}): Promise<CalendarRegras> {
  return apiFetch<CalendarRegras>("/api/calendar/regras", {
    method: "PUT",
    body,
  });
}

// --- Agendamentos (S2/S5) ---

export interface Agendamento {
  id: number;
  empresa_id: number;
  calendar_id: string;
  user_id_criador: string | null;
  cliente_id: number | null;
  evento_id_externo: string | null;
  summary: string;
  descricao: string | null;
  data_inicio: string;
  data_fim: string;
  status: "pendente" | "confirmado" | "cancelado";
  aprovado: boolean;
  gestor_notificado: boolean;
  payload_externo: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export async function getAgendamentos(params?: {
  inicio?: string;
  fim?: string;
  status?: string;
  cliente_id?: number;
  limit?: number;
}): Promise<{ items: Agendamento[] }> {
  const qs = new URLSearchParams();
  if (params?.inicio) qs.set("inicio", params.inicio);
  if (params?.fim) qs.set("fim", params.fim);
  if (params?.status) qs.set("status", params.status);
  if (params?.cliente_id) qs.set("cliente_id", String(params.cliente_id));
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<{ items: Agendamento[] }>(`/api/agendamentos${suffix}`);
}

export interface AgendamentoHistorico {
  id: number;
  action: string;
  actor_user_id: string | null;
  payload_diff: Record<string, unknown>;
  at: string | null;
}

export async function resetAtendimentoThread(
  atendimentoId: number
): Promise<{ ok: boolean; rows_deleted: number; thread_id: string }> {
  return apiFetch<{ ok: boolean; rows_deleted: number; thread_id: string }>(
    `/api/atendimentos/${atendimentoId}/reset-thread`,
    { method: "POST" }
  );
}

export async function getAgendamentoHistorico(
  id: number
): Promise<{ items: AgendamentoHistorico[] }> {
  return apiFetch<{ items: AgendamentoHistorico[] }>(
    `/api/agendamentos/${id}/historico`
  );
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

export async function getDocumentosConhecimento(opts?: {
  pastaId?: number | null;
  raiz?: boolean;
  incluirSubpastas?: boolean;
}): Promise<DocumentosConhecimentoResponse> {
  const params = new URLSearchParams();
  if (opts?.pastaId != null) params.set("pasta_id", String(opts.pastaId));
  if (opts?.raiz) params.set("raiz", "true");
  if (opts?.incluirSubpastas) params.set("incluir_subpastas", "true");
  const q = params.toString();
  return apiFetch<DocumentosConhecimentoResponse>(
    `/api/base-conhecimento${q ? "?" + q : ""}`
  );
}

// E2.D M6.b: Campanhas
export interface Campanha {
  id: number;
  empresa_id: number;
  nome: string;
  descricao: string | null;
  mensagem: string;
  conexao_id: number | null;
  status: "draft" | "running" | "done" | "partial" | "aborted";
  intervalo_ms: number;
  max_destinatarios: number;
  total_destinatarios: number;
  enviados: number;
  falhas: number;
  started_at: string | null;
  finished_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  // Sub-fase B+ paridade ZigChat (mig 051)
  modelo_mensagem_id: number | null;
  scheduled_at: string | null;
  tipo: "broadcast" | "transactional" | "reativacao";
  filtro_segmento: string | null;
  filtro_tags: string[] | null;
}

export interface CampanhaDestinatario {
  id: number;
  telefone: string;
  status: "pendente" | "enviado" | "falhou";
  mensagem_id_externo: string | null;
  erro: string | null;
  sent_at: string | null;
}

export interface CampanhaCreateInput {
  nome: string;
  descricao?: string | null;
  mensagem: string;
  conexao_id?: number | null;
  intervalo_ms?: number;
  max_destinatarios?: number;
  telefones: string[];
  // Sub-fase B+ paridade ZigChat (mig 051)
  modelo_mensagem_id?: number | null;
  scheduled_at?: string | null;
  tipo?: "broadcast" | "transactional" | "reativacao";
  filtro_segmento?: string | null;
  filtro_tags?: string[] | null;
}

export async function getCampanhas(): Promise<{ items: Campanha[] }> {
  return apiFetch<{ items: Campanha[] }>(`/api/campanhas`);
}

export async function getCampanha(id: number): Promise<Campanha> {
  return apiFetch<Campanha>(`/api/campanhas/${id}`);
}

export async function getCampanhaDestinatarios(
  id: number,
  limit = 200
): Promise<{ items: CampanhaDestinatario[] }> {
  return apiFetch<{ items: CampanhaDestinatario[] }>(
    `/api/campanhas/${id}/destinatarios?limit=${limit}`
  );
}

export async function createCampanha(
  body: CampanhaCreateInput
): Promise<Campanha> {
  return apiFetch<Campanha>(`/api/campanhas`, { method: "POST", body });
}

export async function dispatchCampanha(id: number): Promise<{
  ok: boolean;
  campanha_id: number;
  status: string;
}> {
  return apiFetch<{ ok: boolean; campanha_id: number; status: string }>(
    `/api/campanhas/${id}/dispatch`,
    { method: "POST" }
  );
}

export async function abortCampanha(id: number): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/campanhas/${id}/abort`, {
    method: "POST",
  });
}

// E2.C M7: Pastas
export async function getPastas(opts?: {
  comDocs?: boolean;
}): Promise<PastasResponse> {
  const q = opts?.comDocs ? "?com_docs=true" : "";
  return apiFetch<PastasResponse>(`/api/pastas${q}`);
}

export async function createPasta(body: PastaInput): Promise<Pasta> {
  return apiFetch<Pasta>(`/api/pastas`, { method: "POST", body });
}

export async function updatePasta(id: number, body: PastaInput): Promise<Pasta> {
  return apiFetch<Pasta>(`/api/pastas/${id}`, { method: "PUT", body });
}

export async function deletePasta(id: number): Promise<void> {
  await apiFetch<void>(`/api/pastas/${id}`, { method: "DELETE" });
}

export async function moveDocumentoToPasta(
  docId: number,
  pastaId: number | null
): Promise<{ ok: boolean; doc_id: number; pasta_id: number | null }> {
  // pasta_id=0 sinaliza "raiz" no endpoint backend
  const target = pastaId == null ? 0 : pastaId;
  return apiFetch(`/api/pastas/${target}/documentos/${docId}`, {
    method: "POST",
  });
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
  options: { titulo?: string; tags?: string[]; pastaId?: number | null } = {}
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
  if (options.pastaId != null) form.append("pasta_id", String(options.pastaId));

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

export async function getDepartamentos(opts?: {
  comUsers?: boolean;
}): Promise<DepartamentosResponse> {
  const q = opts?.comUsers ? "?com_users=true" : "";
  return apiFetch<DepartamentosResponse>(`/api/departamentos${q}`);
}

export async function getDepartamentoUsers(
  depId: number
): Promise<{ items: DepartamentoUser[] }> {
  return apiFetch<{ items: DepartamentoUser[] }>(
    `/api/departamentos/${depId}/users`
  );
}

export async function assignDepartamentoUser(
  depId: number,
  userId: string
): Promise<{ ok: boolean; inserted: boolean }> {
  return apiFetch<{ ok: boolean; inserted: boolean }>(
    `/api/departamentos/${depId}/users`,
    { method: "POST", body: { user_id: userId } }
  );
}

export async function unassignDepartamentoUser(
  depId: number,
  userId: string
): Promise<void> {
  await apiFetch<void>(`/api/departamentos/${depId}/users/${userId}`, {
    method: "DELETE",
  });
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

// ---------------- RBAC (E2.A) ----------------

export interface PermissaoCatalogo {
  codigo: string;
  descricao: string;
  modulo: string;
}

export interface PermissaoCatalogoResponse {
  items: PermissaoCatalogo[];
}

export interface PerfilAcesso {
  id: number;
  nome: string;
  descricao: string | null;
  is_system: boolean;
  created_at: string | null;
  updated_at: string | null;
  perms_count: number;
  users_count: number;
  permissoes?: string[];
}

export interface PerfisResponse {
  items: PerfilAcesso[];
}

export interface MyPermissionsResponse {
  permissoes: string[];
  perfis: { id: number; nome: string }[];
}

export async function getPermissoesCatalogo(): Promise<PermissaoCatalogoResponse> {
  return apiFetch<PermissaoCatalogoResponse>(`/api/permissoes`);
}

export async function getPerfis(): Promise<PerfisResponse> {
  return apiFetch<PerfisResponse>(`/api/perfis`);
}

export async function getPerfil(id: number): Promise<PerfilAcesso> {
  return apiFetch<PerfilAcesso>(`/api/perfis/${id}`);
}

export async function createPerfil(body: {
  nome: string;
  descricao?: string | null;
  permissoes: string[];
}): Promise<PerfilAcesso> {
  return apiFetch<PerfilAcesso>(`/api/perfis`, { method: "POST", body });
}

export async function updatePerfil(
  id: number,
  body: { permissoes: string[]; descricao?: string | null }
): Promise<PerfilAcesso> {
  return apiFetch<PerfilAcesso>(`/api/perfis/${id}`, { method: "PUT", body });
}

export async function deletePerfil(id: number): Promise<void> {
  await apiFetch<void>(`/api/perfis/${id}`, { method: "DELETE" });
}

export async function getMyPermissions(): Promise<MyPermissionsResponse> {
  return apiFetch<MyPermissionsResponse>(`/api/perfis/me`);
}

export async function assignPerfil(
  perfilId: number,
  userId: string
): Promise<void> {
  await apiFetch<void>(`/api/perfis/${perfilId}/users`, {
    method: "POST",
    body: { user_id: userId },
  });
}

export async function unassignPerfil(
  perfilId: number,
  userId: string
): Promise<void> {
  await apiFetch<void>(`/api/perfis/${perfilId}/users/${userId}`, {
    method: "DELETE",
  });
}

export async function migrateRBAC(empresaId: number): Promise<{
  converted: number;
  skipped: number;
  total_membros: number;
}> {
  return apiFetch<{
    converted: number;
    skipped: number;
    total_membros: number;
  }>(`/api/empresas/${empresaId}/migrate-rbac`, { method: "POST" });
}

// ---------------- Fase 0 enterprise — Audit log + Feature flags ----------------

export interface AuditLog {
  id: number;
  empresa_id: number;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  payload_diff: Record<string, unknown>;
  ip: string | null;
  user_agent: string | null;
  request_id: string | null;
  at: string;
}

export interface AuditLogResponse {
  items: AuditLog[];
  limit: number;
  offset: number;
}

export async function getAuditLog(opts?: {
  entityType?: string;
  entityId?: string;
  userId?: string;
  action?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditLogResponse> {
  const params = new URLSearchParams();
  if (opts?.entityType) params.set("entity_type", opts.entityType);
  if (opts?.entityId) params.set("entity_id", opts.entityId);
  if (opts?.userId) params.set("user_id", opts.userId);
  if (opts?.action) params.set("action", opts.action);
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const q = params.toString();
  return apiFetch<AuditLogResponse>(`/api/v1/audit${q ? "?" + q : ""}`);
}

export interface FeatureFlag {
  id: number;
  empresa_id: number;
  key: string;
  value: unknown;
  descricao: string | null;
  ativo: boolean;
  created_by_user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export async function getFeatureFlags(): Promise<{ items: FeatureFlag[] }> {
  return apiFetch<{ items: FeatureFlag[] }>(`/api/v1/feature-flags`);
}

export async function upsertFeatureFlag(
  key: string,
  body: {
    key: string;
    value: unknown;
    descricao?: string | null;
    ativo?: boolean;
  }
): Promise<FeatureFlag> {
  return apiFetch<FeatureFlag>(`/api/v1/feature-flags/${key}`, {
    method: "PUT",
    body,
  });
}

export async function deleteFeatureFlag(key: string): Promise<void> {
  await apiFetch<void>(`/api/v1/feature-flags/${key}`, { method: "DELETE" });
}

// ---------------- Sub-fase A: agente_ia cadastrável ----------------

export type EstiloResposta =
  | "preciso"
  | "equilibrado"
  | "criativo"
  | "muito_criativo";

export type LimiteCustoAcao =
  | "solicitar_humano"
  | "encerrar"
  | "continuar"
  | "bloquear";

export interface AgenteIA {
  id: number;
  empresa_id: number;
  slug: string;
  nome: string;
  descricao: string | null;
  template_catalog: string;
  prompt_override: string | null;
  modelo: string | null;
  estilo_resposta: EstiloResposta;
  temperatura_override: number | null;
  max_tokens: number | null;
  top_p_override: number | null;
  tools_enabled: string[];
  tools_config: Record<string, unknown>;
  aceita_imagem: boolean;
  aceita_audio: boolean;
  aceita_documento: boolean;
  base_conhecimento_ids: number[];
  variavel_ids: number[];
  mcp_server_ids: number[];
  limite_custo_acao: LimiteCustoAcao;
  ativo: boolean;
  is_default: boolean;
  created_by_user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  // Derivados (computados no backend baseado em estilo + override)
  temperatura_efetiva: number;
  top_p_efetivo: number;
  // Sprint 2 paridade ZigChat (mig 043)
  modelo_provedor: string | null;
  modelo_nome: string | null;
  tipo_memoria: string;
  janela_memoria: number | null;
  timeout_minutos: number | null;
  acao_limite_menu_id: number | null;
}

export interface AgenteIACreateInput {
  slug: string;
  nome: string;
  descricao?: string | null;
  template_catalog?: string;
}

export type AgenteIAUpdateInput = Partial<
  Omit<
    AgenteIA,
    | "id"
    | "empresa_id"
    | "slug"
    | "created_by_user_id"
    | "created_at"
    | "updated_at"
    | "temperatura_efetiva"
    | "top_p_efetivo"
  >
>;

export async function getAgentesIA(opts?: {
  onlyActive?: boolean;
}): Promise<{ items: AgenteIA[] }> {
  const q = opts?.onlyActive ? "?only_active=true" : "";
  return apiFetch<{ items: AgenteIA[] }>(`/api/v1/agentes${q}`);
}

export async function getAgenteIA(slug: string): Promise<AgenteIA> {
  return apiFetch<AgenteIA>(`/api/v1/agentes/${slug}`);
}

export async function createAgenteIA(
  body: AgenteIACreateInput
): Promise<AgenteIA> {
  return apiFetch<AgenteIA>(`/api/v1/agentes`, { method: "POST", body });
}

export async function updateAgenteIA(
  slug: string,
  body: AgenteIAUpdateInput
): Promise<AgenteIA> {
  return apiFetch<AgenteIA>(`/api/v1/agentes/${slug}`, {
    method: "PUT",
    body,
  });
}

export async function deleteAgenteIA(slug: string): Promise<void> {
  await apiFetch<void>(`/api/v1/agentes/${slug}`, { method: "DELETE" });
}

export async function setDefaultAgenteIA(
  slug: string
): Promise<{ ok: boolean; slug: string }> {
  return apiFetch<{ ok: boolean; slug: string }>(
    `/api/v1/agentes/${slug}/set-default`,
    { method: "POST" }
  );
}

// Templates do catálogo Python (vsa_tech, atendimento_completo, ...) — usado
// nos dropdowns de criar/editar agente DB.
export interface AgenteTemplate {
  slug: string;
  label: string;
  descricao: string;
}

export async function getAgenteTemplates(): Promise<{ items: AgenteTemplate[] }> {
  return apiFetch<{ items: AgenteTemplate[] }>(`/api/v1/agentes/templates`);
}

// =====================================================================
// Menu chatbot (Sub-fase B + B+ paridade ZigChat)
// =====================================================================

export interface MenuChatbot {
  id: number;
  empresa_id: number;
  conexao_id: number | null;
  nome: string;
  ativo: boolean;
  mensagem_boas_vindas: string;
  trigger_keywords: string[];
  mensagem_opcao_invalida: string;
  created_at: string | null;
  updated_at: string | null;
  created_by_user_id: string | null;
  // B+ paridade ZigChat (mig 041)
  atalho: string | null;
  solicitar_nome: boolean;
  menu_moderno: boolean;
  auto_navegar_para_item_id: number | null;
  qtde_acesso: number;
  arquivo_url: string | null;
  mensagem_coleta: string | null;
  mensagem_confirmar_coleta: string | null;
  mensagem_final_coleta: string | null;
  resposta_confidencial: boolean;
  // Apenas no list_menus_endpoint (não no get_menu_by_id) — count agregado.
  qtde_items?: number;
}

export type MenuItemAcaoTipo =
  | "submenu"
  | "transferir_dep"
  | "chamar_agente"
  | "enviar_msg"
  | "fechar"
  | "transferir_atendente"
  | "enviar_template"
  | "chamar_webhook"
  | "enviar_link"
  | "pesquisa_csat"
  | "mudar_manual"
  | "setar_nome";

export interface MenuItem {
  id: number;
  menu_id: number;
  parent_id: number | null;
  ordem: number;
  label: string;
  acao_tipo: MenuItemAcaoTipo;
  acao_payload: Record<string, unknown>;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
  // B+ (mig 042)
  comando: string | null;
  acao_atendente_id: string | null;
  acao_modelo_mensagem_id: number | null;
  webhook_url: string | null;
  hook_id: number | null;
  link_url: string | null;
  nota_min: number | null;
  nota_max: number | null;
  nota_pergunta: string | null;
  grupo: string | null;
}

export interface MenuChatbotCreateInput {
  nome: string;
  mensagem_boas_vindas: string;
  conexao_id?: number | null;
  trigger_keywords?: string[];
  mensagem_opcao_invalida?: string;
}

export type MenuChatbotUpdateInput = Partial<
  Pick<
    MenuChatbot,
    | "nome"
    | "mensagem_boas_vindas"
    | "conexao_id"
    | "trigger_keywords"
    | "mensagem_opcao_invalida"
    | "ativo"
    | "atalho"
    | "solicitar_nome"
    | "menu_moderno"
    | "auto_navegar_para_item_id"
    | "arquivo_url"
    | "mensagem_coleta"
    | "mensagem_confirmar_coleta"
    | "mensagem_final_coleta"
    | "resposta_confidencial"
  >
>;

export interface MenuItemCreateInput {
  label: string;
  acao_tipo: MenuItemAcaoTipo;
  acao_payload?: Record<string, unknown>;
  parent_id?: number | null;
  ordem?: number;
}

export type MenuItemUpdateInput = Partial<
  Pick<
    MenuItem,
    | "label"
    | "acao_tipo"
    | "acao_payload"
    | "ordem"
    | "ativo"
    | "comando"
    | "acao_atendente_id"
    | "acao_modelo_mensagem_id"
    | "webhook_url"
    | "hook_id"
    | "link_url"
    | "nota_min"
    | "nota_max"
    | "nota_pergunta"
    | "grupo"
  >
>;

export async function getMenus(opts?: {
  onlyActive?: boolean;
}): Promise<{ items: MenuChatbot[] }> {
  const q = opts?.onlyActive ? "?only_active=true" : "";
  return apiFetch<{ items: MenuChatbot[] }>(`/api/v1/menus${q}`);
}

export async function getMenu(id: number): Promise<MenuChatbot> {
  return apiFetch<MenuChatbot>(`/api/v1/menus/${id}`);
}

export async function createMenu(
  body: MenuChatbotCreateInput
): Promise<MenuChatbot> {
  return apiFetch<MenuChatbot>(`/api/v1/menus`, { method: "POST", body });
}

export async function updateMenu(
  id: number,
  body: MenuChatbotUpdateInput
): Promise<MenuChatbot> {
  return apiFetch<MenuChatbot>(`/api/v1/menus/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteMenu(id: number): Promise<void> {
  await apiFetch<void>(`/api/v1/menus/${id}`, { method: "DELETE" });
}

export async function getMenuItems(
  menuId: number,
  opts?: { parentId?: number | null; onlyActive?: boolean }
): Promise<{ items: MenuItem[] }> {
  const params = new URLSearchParams();
  if (opts?.parentId !== undefined && opts.parentId !== null) {
    params.set("parent_id", String(opts.parentId));
  }
  if (opts?.onlyActive === false) {
    params.set("only_active", "false");
  }
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<{ items: MenuItem[] }>(`/api/v1/menus/${menuId}/itens${qs}`);
}

export async function createMenuItem(
  menuId: number,
  body: MenuItemCreateInput
): Promise<MenuItem> {
  return apiFetch<MenuItem>(`/api/v1/menus/${menuId}/itens`, {
    method: "POST",
    body,
  });
}

export async function updateMenuItem(
  menuId: number,
  itemId: number,
  body: MenuItemUpdateInput
): Promise<MenuItem> {
  return apiFetch<MenuItem>(`/api/v1/menus/${menuId}/itens/${itemId}`, {
    method: "PUT",
    body,
  });
}

export async function deleteMenuItem(
  menuId: number,
  itemId: number
): Promise<void> {
  await apiFetch<void>(`/api/v1/menus/${menuId}/itens/${itemId}`, {
    method: "DELETE",
  });
}

export async function reorderMenuItems(
  menuId: number,
  body: { parent_id: number | null; ordered_ids: number[] }
): Promise<{ ok: boolean; ordered_ids: number[] }> {
  return apiFetch<{ ok: boolean; ordered_ids: number[] }>(
    `/api/v1/menus/${menuId}/itens/reorder`,
    { method: "POST", body }
  );
}

export async function seedMenuFromAgentes(
  menuId: number
): Promise<{ items: MenuItem[]; qtde_criados: number }> {
  return apiFetch<{ items: MenuItem[]; qtde_criados: number }>(
    `/api/v1/menus/${menuId}/itens/seed-from-agentes`,
    { method: "POST" }
  );
}

// =====================================================================
// Catálogo modelo_llm (Sprint 1+ paridade ZigChat)
// =====================================================================

export interface ModeloLLM {
  id: number;
  empresa_id: number | null;  // NULL = global
  provedor: string;
  nome: string;
  descricao: string | null;
  tipo: "chat" | "embedding" | "midia" | "audio" | "imagem";
  custo_input_mtok: number | null;
  custo_output_mtok: number | null;
  janela_contexto: number | null;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export async function getModelosLLM(opts?: {
  tipo?: string;
  onlyActive?: boolean;
}): Promise<{ items: ModeloLLM[] }> {
  const params = new URLSearchParams();
  if (opts?.tipo) params.set("tipo", opts.tipo);
  if (opts?.onlyActive === false) params.set("only_active", "false");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<{ items: ModeloLLM[] }>(`/api/v1/modelos-llm${qs}`);
}

export async function getModeloLLM(id: number): Promise<ModeloLLM> {
  return apiFetch<ModeloLLM>(`/api/v1/modelos-llm/${id}`);
}

export interface ModeloLLMCreateInput {
  provedor: string;
  nome: string;
  tipo: ModeloLLM["tipo"];
  descricao?: string | null;
  custo_input_mtok?: number | null;
  custo_output_mtok?: number | null;
  janela_contexto?: number | null;
}

export type ModeloLLMUpdateInput = Partial<
  Pick<
    ModeloLLM,
    "nome" | "descricao" | "custo_input_mtok" | "custo_output_mtok"
    | "janela_contexto" | "ativo"
  >
>;

export async function createModeloLLM(
  body: ModeloLLMCreateInput
): Promise<ModeloLLM> {
  return apiFetch<ModeloLLM>(`/api/v1/modelos-llm`, { method: "POST", body });
}

export async function updateModeloLLM(
  id: number,
  body: ModeloLLMUpdateInput
): Promise<ModeloLLM> {
  return apiFetch<ModeloLLM>(`/api/v1/modelos-llm/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteModeloLLM(id: number): Promise<void> {
  await apiFetch<void>(`/api/v1/modelos-llm/${id}`, { method: "DELETE" });
}

// MCP Server (Sprint 1+ paridade ZigChat)

export interface McpServer {
  id: number;
  empresa_id: number;
  nome: string;
  descricao: string | null;
  tipo_conexao: "stdio" | "sse" | "http" | "websocket";
  url: string | null;
  comando: string | null;
  args: string | null;
  headers: Record<string, unknown>;
  status: "active" | "inactive" | "error" | "testing";
  ultimo_teste_at: string | null;
  ultimo_erro: string | null;
  ativo: boolean;
  created_by_user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface McpServerCreateInput {
  nome: string;
  tipo_conexao: McpServer["tipo_conexao"];
  descricao?: string | null;
  url?: string | null;
  comando?: string | null;
  args?: string | null;
  headers?: Record<string, unknown> | null;
}

export type McpServerUpdateInput = Partial<
  Pick<
    McpServer,
    "nome" | "descricao" | "tipo_conexao" | "url" | "comando" | "args"
    | "headers" | "ativo"
  >
>;

export async function getMcpServers(opts?: {
  onlyActive?: boolean;
}): Promise<{ items: McpServer[] }> {
  const q = opts?.onlyActive ? "?only_active=true" : "";
  return apiFetch<{ items: McpServer[] }>(`/api/v1/mcp-servers${q}`);
}

export async function getMcpServer(id: number): Promise<McpServer> {
  return apiFetch<McpServer>(`/api/v1/mcp-servers/${id}`);
}

export async function createMcpServer(
  body: McpServerCreateInput
): Promise<McpServer> {
  return apiFetch<McpServer>(`/api/v1/mcp-servers`, { method: "POST", body });
}

export async function updateMcpServer(
  id: number,
  body: McpServerUpdateInput
): Promise<McpServer> {
  return apiFetch<McpServer>(`/api/v1/mcp-servers/${id}`, {
    method: "PUT",
    body,
  });
}

export async function deleteMcpServer(id: number): Promise<void> {
  await apiFetch<void>(`/api/v1/mcp-servers/${id}`, { method: "DELETE" });
}

export interface McpTestResult {
  ok: boolean;
  status: string;
  erro: string | null;
  tested_at: string;
}

export async function testMcpServer(id: number): Promise<McpTestResult> {
  return apiFetch<McpTestResult>(`/api/v1/mcp-servers/${id}/test`, {
    method: "POST",
  });
}

// =====================================================================
// Dashboard IA (Sprint 7 paridade ZigChat)
// =====================================================================

export interface DashboardIa {
  periodo_dias: number;
  resumo: {
    total_calls: number;
    total_tokens_input: number;
    total_tokens_output: number;
    custo_periodo_usd: number;
    custo_mes_atual_usd: number;
  };
  serie_diaria: { dia: string; calls: number; custo: number }[];
  top_modelos: {
    provedor: string;
    nome: string;
    calls: number;
    custo: number;
    tokens_input: number;
    tokens_output: number;
  }[];
  top_agentes: {
    id: number;
    slug: string;
    nome: string;
    calls: number;
    custo: number;
  }[];
  budget_atual: {
    limite_usd: number;
    consumo_usd: number;
    acao_estouro: string;
    alerta_pct: number;
    pct_consumo: number;
    estourado: boolean;
  } | null;
}

export async function getDashboardIa(days = 30): Promise<DashboardIa> {
  return apiFetch<DashboardIa>(`/api/v1/dashboard/ia?days=${days}`);
}

export interface IaBudget {
  exists: boolean;
  id?: number;
  empresa_id?: number;
  ano_mes: string;
  limite_usd?: number;
  consumo_usd?: number;
  acao_estouro?: string;
  alerta_pct?: number;
  estourado_em?: string | null;
  alertado_em?: string | null;
  pct_consumo?: number;
}

export interface IaBudgetUpsertInput {
  limite_usd: number;
  acao_estouro?: "alertar" | "bloquear" | "redirecionar_menu";
  alerta_pct?: number;
  ano_mes?: string;
}

export async function getIaBudget(anoMes?: string): Promise<IaBudget> {
  const q = anoMes ? `?ano_mes=${anoMes}` : "";
  return apiFetch<IaBudget>(`/api/v1/ia-budget${q}`);
}

export async function upsertIaBudget(
  body: IaBudgetUpsertInput
): Promise<IaBudget> {
  return apiFetch<IaBudget>(`/api/v1/ia-budget`, { method: "PUT", body });
}

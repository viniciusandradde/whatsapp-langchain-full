/**
 * Tipos + chamadas de Test Runner pra USAR EM CLIENT COMPONENTS (Sprint L).
 *
 * Não importa "server-only" — usa fetch() do browser contra os proxies em
 * /api/proxy/admin-tests/*. Os proxies injetam Better Auth + service token.
 *
 * Server components devem continuar usando getTestRuns/isMyAdmin de @/lib/api.
 */

export type TestRunStatus = "queued" | "running" | "passed" | "failed" | "error";
// Sprint Eval-UI (mig 075): roteia subprocess pytest entre tests/e2e/ e tests/eval/.
export type TestRunModo = "e2e" | "eval-online" | "eval-offline";

export interface TestRun {
  id: number;
  started_by_user_id: string | null;
  started_by_name: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: TestRunStatus;
  modo?: TestRunModo;
  filtro: string | null;
  total: number | null;
  passed: number | null;
  failed: number | null;
  duration_seconds: number | null;
  pid: number | null;
  storage_path: string;
  log_size_bytes: number;
  error_message: string | null;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    credentials: "include",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail || body?.message || detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function getTestRunsClient(): Promise<{ items: TestRun[] }> {
  return jsonFetch<{ items: TestRun[] }>("/api/proxy/admin-tests/runs");
}

export async function getTestRunClient(id: number): Promise<TestRun> {
  return jsonFetch<TestRun>(`/api/proxy/admin-tests/runs/${id}`);
}

export async function startTestRunClient(
  filtro?: string,
  modo: TestRunModo = "e2e"
): Promise<TestRun> {
  return jsonFetch<TestRun>("/api/proxy/admin-tests/run", {
    method: "POST",
    body: JSON.stringify({ filtro: filtro || null, modo }),
  });
}

export async function killTestRunClient(id: number): Promise<void> {
  await jsonFetch<unknown>(`/api/proxy/admin-tests/runs/${id}/kill`, {
    method: "POST",
  });
}

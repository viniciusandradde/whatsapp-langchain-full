import Link from "next/link";
import { Activity, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { getTraces } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

interface TracesPageProps {
  searchParams: Promise<{ thread_id?: string }>;
}

/**
 * Página /traces — lista enxuta de runs do LangSmith com link pra UI completa.
 *
 * Server Component que consulta `/api/traces` (proxy LangSmith) e renderiza
 * uma tabela com nome, status, latência, tokens, thread e link "Abrir →"
 * direto pra smith.langchain.com.
 *
 * Filtragem opcional por thread_id via querystring (?thread_id=...) — útil
 * pra rastrear todas as runs de uma conversa específica.
 */
export default async function TracesPage({ searchParams }: TracesPageProps) {
  await requireSession();
  const sp = await searchParams;

  let traces: Awaited<ReturnType<typeof getTraces>>["traces"] = [];
  let error: string | null = null;

  try {
    const data = await getTraces({ limit: 50, thread_id: sp.thread_id });
    traces = data.traces;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro desconhecido ao buscar traces.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-6 w-6" />
          <h1 className="text-2xl font-semibold">Traces — LangSmith</h1>
        </div>
        <span className="text-sm text-muted-foreground">
          {traces.length} runs
          {sp.thread_id ? (
            <>
              {" · thread "}
              <span className="font-mono">{sp.thread_id}</span>
            </>
          ) : null}
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar os traces</p>
          <p className="mt-1 text-destructive/80">{error}</p>
          <p className="mt-2 text-xs text-destructive/80">
            Verifique se LANGCHAIN_API_KEY e LANGCHAIN_PROJECT estão
            configurados na API.
          </p>
        </div>
      )}

      {!error && traces.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <Activity className="mx-auto h-10 w-10 mb-3 opacity-50" />
          <p className="font-medium">Nenhum trace encontrado</p>
          <p className="mt-1 text-sm">
            As runs aparecem aqui depois que o agente processa uma mensagem.
          </p>
        </div>
      )}

      {traces.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Nome</th>
                <th className="px-3 py-2 font-medium">Thread</th>
                <th className="px-3 py-2 font-medium">Latência</th>
                <th className="px-3 py-2 font-medium">Tokens</th>
                <th className="px-3 py-2 font-medium">Início</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => {
                const variant =
                  t.status === "success"
                    ? "secondary"
                    : t.status === "error"
                      ? "destructive"
                      : "outline";
                return (
                  <tr key={t.run_id} className="border-t">
                    <td className="px-3 py-2">
                      <Badge variant={variant}>{t.status ?? "—"}</Badge>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{t.name ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {t.thread_id ?? "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {t.latency_ms !== null ? `${t.latency_ms}ms` : "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{t.total_tokens ?? "—"}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {t.start_time?.slice(0, 19).replace("T", " ") ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Link
                        href={t.smith_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        Abrir
                        <ExternalLink className="h-3.5 w-3.5" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

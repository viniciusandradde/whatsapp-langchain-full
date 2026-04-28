import {
  LayoutDashboard,
  MessageSquare,
  AlertTriangle,
  Clock,
  ListOrdered,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getMetrics } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Página principal do painel administrativo.
 *
 * Server Component que busca métricas da API e exibe em cards.
 * Se a API estiver fora do ar, mostra uma mensagem amigável de erro.
 */
export default async function DashboardPage() {
  await requireSession();

  // Tenta buscar métricas — a API pode não estar rodando em dev
  let metrics = null;
  let error = null;

  try {
    metrics = await getMetrics();
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro desconhecido ao buscar métricas";
  }

  return (
    <div className="space-y-6">
      {/* Cabeçalho da página */}
      <div className="flex items-center gap-2">
        <LayoutDashboard className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Dashboard</h1>
      </div>

      {/* Estado de erro — API indisponível */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar as métricas</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {/* Grid de métricas — 2 colunas no mobile, 4 no desktop */}
      {metrics && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {/* Total de mensagens hoje */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-muted-foreground">
                  Mensagens hoje
                </CardTitle>
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold">{metrics.total_today}</p>
            </CardContent>
          </Card>

          {/* Falhas hoje — destaque vermelho se houver falhas */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-muted-foreground">
                  Falhas hoje
                </CardTitle>
                <AlertTriangle
                  className={`h-4 w-4 ${
                    metrics.failures_today > 0
                      ? "text-destructive"
                      : "text-muted-foreground"
                  }`}
                />
              </div>
            </CardHeader>
            <CardContent>
              <p
                className={`text-3xl font-bold ${
                  metrics.failures_today > 0 ? "text-destructive" : ""
                }`}
              >
                {metrics.failures_today}
              </p>
            </CardContent>
          </Card>

          {/* Tempo médio de processamento */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-muted-foreground">
                  Tempo médio
                </CardTitle>
                <Clock className="h-4 w-4 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold">
                {typeof metrics.avg_processing_time_seconds === "number"
                  ? `${metrics.avg_processing_time_seconds.toFixed(1)}s`
                  : "N/A"}
              </p>
            </CardContent>
          </Card>

          {/* Mensagens na fila */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-muted-foreground">
                  Na fila
                </CardTitle>
                <ListOrdered className="h-4 w-4 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold">{metrics.queue_size}</p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

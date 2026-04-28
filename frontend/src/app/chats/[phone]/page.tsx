import Link from "next/link";
import { ArrowLeft, MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { getChatMessages } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Mapa de variantes do Badge para cada status de mensagem.
 *
 * Facilita a leitura e evita um switch/if-else grande no JSX.
 */
const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  queued: "outline",
  processing: "secondary",
  done: "default",
  failed: "destructive",
};

/**
 * Rótulos em português para cada status.
 */
const STATUS_LABEL: Record<string, string> = {
  queued: "Na fila",
  processing: "Processando",
  done: "Concluído",
  failed: "Falhou",
};

/**
 * Formata uma data ISO como string legível em português.
 */
function formatDate(dateString: string | null): string {
  if (!dateString) return "—";

  const date = new Date(dateString);
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Página de detalhe de uma conversa.
 *
 * Server Component que recebe o telefone via params dinâmicos,
 * busca as mensagens da API e exibe em layout sequencial (pergunta/resposta).
 */
export default async function ChatDetailPage({
  params,
}: {
  params: Promise<{ phone: string }>;
}) {
  await requireSession();

  const { phone } = await params;
  // O Next.js codifica o parâmetro na URL — decodificamos para usar na API
  const decodedPhone = decodeURIComponent(phone).trim();

  // Tenta buscar mensagens — a API pode não estar rodando em dev
  let data = null;
  let error = null;

  try {
    data = await getChatMessages(decodedPhone);
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro desconhecido ao buscar mensagens";
  }

  return (
    <div className="space-y-6">
      {/* Cabeçalho com botão de voltar e número do telefone */}
      <div className="flex items-center gap-3">
        <Link
          href="/chats"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <MessageSquare className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">{decodedPhone}</h1>
      </div>

      {/* Estado de erro — API indisponível */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar as mensagens</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {/* Estado vazio — nenhuma mensagem encontrada */}
      {data && data.messages.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <MessageSquare className="mx-auto mb-2 h-8 w-8" />
          <p>Nenhuma mensagem encontrada</p>
        </div>
      )}

      {/* Lista de mensagens em formato sequencial */}
      {data && data.messages.length > 0 && (
        <div className="space-y-4">
          {data.messages.map((message) => (
            <Card key={message.id}>
              <CardContent className="space-y-3">
                {/* Cabeçalho da mensagem: status, mídia, data */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant={STATUS_VARIANT[message.status] ?? "outline"}>
                    {STATUS_LABEL[message.status] ?? message.status}
                  </Badge>
                  {message.media_type && (
                    <Badge variant="secondary">{message.media_type}</Badge>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {formatDate(message.created_at)}
                  </span>
                </div>

                {/* Mensagem do usuário */}
                <div className="rounded-lg bg-muted p-3">
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Usuário
                  </p>
                  <p className="text-sm whitespace-pre-wrap">
                    {message.incoming_message}
                  </p>
                </div>

                {/* Resposta da IA — só exibe se existir */}
                {message.response && (
                  <div className="rounded-lg bg-primary/5 border border-primary/10 p-3">
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      Assistente
                    </p>
                    <p className="text-sm whitespace-pre-wrap">
                      {message.response}
                    </p>
                  </div>
                )}

                {/* Erro — só exibe se o status for failed */}
                {message.status === "failed" && message.error && (
                  <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3">
                    <p className="text-xs font-medium text-destructive mb-1">
                      Erro
                    </p>
                    <p className="text-sm text-destructive/80">
                      {message.error}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

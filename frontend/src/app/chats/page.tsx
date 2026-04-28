import Link from "next/link";
import { MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getChats } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Formata uma data ISO como string legível em português.
 *
 * Usa tempo relativo para datas recentes (hoje/ontem) e formato
 * locale para datas mais antigas — mantém simples sem libs externas.
 */
function formatDate(dateString: string | null): string {
  if (!dateString) return "—";

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);

  // Tempo relativo para datas recentes
  if (diffMinutes < 1) return "agora";
  if (diffMinutes < 60) return `${diffMinutes}min atrás`;
  if (diffHours < 24) return `${diffHours}h atrás`;

  // Formato locale para datas mais antigas
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Trunca texto longo adicionando reticências.
 */
function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}

function formatPhone(phone: string): string {
  if (phone.length > 4) {
    return `***${phone.slice(-4)}`;
  }

  return phone;
}

/**
 * Página de listagem de conversas.
 *
 * Server Component que busca a lista de chats da API e exibe em tabela.
 * Cada linha é clicável e leva à página de detalhe da conversa.
 */
export default async function ChatsPage() {
  await requireSession();

  // Tenta buscar conversas — a API pode não estar rodando em dev
  let data = null;
  let error = null;

  try {
    data = await getChats();
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro desconhecido ao buscar conversas";
  }

  return (
    <div className="space-y-6">
      {/* Cabeçalho da página */}
      <div className="flex items-center gap-2">
        <MessageSquare className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Conversas</h1>
        {data && (
          <Badge variant="secondary">{data.total}</Badge>
        )}
      </div>

      {/* Estado de erro — API indisponível */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar as conversas</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {/* Estado vazio — nenhuma conversa encontrada */}
      {data && data.chats.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <MessageSquare className="mx-auto mb-2 h-8 w-8" />
          <p>Nenhuma conversa encontrada</p>
        </div>
      )}

      {/* Tabela de conversas */}
      {data && data.chats.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Telefone</TableHead>
              <TableHead>Agente</TableHead>
              <TableHead className="hidden md:table-cell">Última mensagem</TableHead>
              <TableHead className="text-center">Mensagens</TableHead>
              <TableHead className="text-right">Última atividade</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.chats.map((chat) => (
              <TableRow key={chat.phone_number}>
                <TableCell>
                  <Link
                    href={`/chats/${encodeURIComponent(chat.phone_number)}`}
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {formatPhone(chat.phone_number)}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{chat.agent_id}</Badge>
                </TableCell>
                <TableCell className="hidden md:table-cell text-muted-foreground">
                  {truncate(chat.last_message, 50)}
                </TableCell>
                <TableCell className="text-center">
                  {chat.message_count}
                </TableCell>
                <TableCell className="text-right text-muted-foreground">
                  {formatDate(chat.last_message_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

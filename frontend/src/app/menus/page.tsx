import Link from "next/link";
import { ListTree, Plus, MessageSquare, Hash } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getMenus } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Página /menus — lista de menus chatbot árvore (Sub-fase B + B+).
 *
 * Cada menu vincula a uma conexão (ou "todas"); workflow do worker:
 * cliente novo → boas-vindas → escolha "1, 2, 3" → ação (12 tipos).
 */
export default async function MenusPage() {
  await requireSession();

  let menus: Awaited<ReturnType<typeof getMenus>>["items"] = [];
  let error: string | null = null;

  try {
    const r = await getMenus();
    menus = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao listar menus.";
  }

  return (
    <div className="space-y-8">
      <PageHeader
        titulo="Menu chatbot"
        descricao="As opções numeradas que o cliente recebe ao chamar — servem pra descobrir o assunto antes de entregar a conversa ao agente ou a uma pessoa."
        icon={ListTree}
        acoes={
          <ButtonLink href="/menus/new">
            <Plus className="size-4" />
            Novo menu
          </ButtonLink>
        }
      />

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {menus.length === 0 && !error ? (
        <Card className="border-dashed">
          <CardContent className="py-10 text-center">
            <ListTree className="mx-auto mb-3 size-8 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              Nenhum menu cadastrado. Crie o primeiro pra começar a triar
              clientes antes do agente IA.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {menus.map((m) => (
            <Card key={m.id} className="flex flex-col">
              <CardHeader className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base">{m.nome}</CardTitle>
                  <div className="flex flex-wrap gap-1">
                    {m.qtde_items === 0 && (
                      <Badge variant="destructive" className="text-xs">
                        vazio
                      </Badge>
                    )}
                    {m.ativo ? (
                      <Badge variant="outline" className="text-xs">
                        ativo
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="text-xs">
                        inativo
                      </Badge>
                    )}
                    {m.menu_moderno && (
                      <Badge variant="outline" className="text-xs">
                        moderno
                      </Badge>
                    )}
                    {m.solicitar_nome && (
                      <Badge variant="outline" className="text-xs">
                        coleta nome
                      </Badge>
                    )}
                  </div>
                </div>
                <p className="line-clamp-2 text-xs text-muted-foreground">
                  {m.mensagem_boas_vindas}
                </p>
              </CardHeader>
              <CardContent className="flex-1 space-y-2 text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <MessageSquare className="size-3.5" />
                  <span>
                    Conexão:{" "}
                    {m.conexao_id ? `#${m.conexao_id}` : "todas as conexões"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Hash className="size-3.5" />
                  <span>
                    Triggers:{" "}
                    {m.trigger_keywords.length > 0
                      ? m.trigger_keywords.join(", ")
                      : "(nenhum)"}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground/70">
                  <span>{m.qtde_items ?? 0} opções</span>
                  {m.qtde_acesso > 0 && <span>{m.qtde_acesso} acessos</span>}
                </div>
              </CardContent>
              <CardFooter>
                <Link
                  href={`/menus/${m.id}/edit`}
                  className="inline-flex w-full"
                >
                  <Button variant="outline" className="w-full" size="sm">
                    Editar
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

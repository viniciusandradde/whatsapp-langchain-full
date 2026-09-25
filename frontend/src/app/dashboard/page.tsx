import { redirect } from "next/navigation";

/**
 * `/dashboard` puro não tem conteúdo próprio — as páginas são
 * `/dashboard/atendimento`, `/ia`, `/qualidade`, `/rag`. Sem esta rota, a raiz
 * dava 404 (achado da bateria de 24/09/2026). Manda para o painel de
 * atendimento, que é a visão inicial.
 */
export default function DashboardIndex() {
  redirect("/dashboard/atendimento");
}

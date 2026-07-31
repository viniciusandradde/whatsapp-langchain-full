import { Tag as TagIcon } from "lucide-react";

import { PageHeader } from "@/components/page-header";

import { getTags, type Tag } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { TagsAdmin } from "./tags-admin";

export const dynamic = "force-dynamic";

export default async function TagsAdminPage() {
  await requireSession();

  let tags: Tag[] = [];
  let error: string | null = null;
  try {
    const r = await getTags(false); // inclui inativas pra admin
    tags = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar tags.";
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Tags"
        descricao="Etiquetas para classificar atendimentos. O atendente aplica na conversa, e o agente também aplica sozinho quando reconhece o assunto."
        icon={TagIcon}
      />
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
      <TagsAdmin initialTags={tags} />
    </div>
  );
}

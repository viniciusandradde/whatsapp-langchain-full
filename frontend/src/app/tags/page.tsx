import { Tag as TagIcon } from "lucide-react";

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
      <div className="flex items-center gap-2">
        <TagIcon className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Tags</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Tags da empresa pra classificar atendimentos. Aplicadas manualmente
        no drawer ou automaticamente pela triagem IA.
      </p>
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
      <TagsAdmin initialTags={tags} />
    </div>
  );
}

import { notFound } from "next/navigation";

import { getMcpServer } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { McpEditor } from "./mcp-editor";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string }>;
}

export default async function EditMcpPage({ params, searchParams }: PageProps) {
  await requireSession();
  const { id } = await params;
  const idNum = Number(id);
  if (!Number.isFinite(idNum)) notFound();

  let mcpMaybe: Awaited<ReturnType<typeof getMcpServer>> | null = null;
  try {
    mcpMaybe = await getMcpServer(idNum);
  } catch {
    notFound();
  }
  if (!mcpMaybe) notFound();

  const errorMsg = (await searchParams).error ?? null;
  return <McpEditor mcp={mcpMaybe!} initialError={errorMsg} />;
}

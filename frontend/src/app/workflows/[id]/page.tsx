import { notFound } from "next/navigation";

import { getWorkflowDetail } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { WorkflowEditor } from "./editor";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditWorkflowPage({ params }: PageProps) {
  await requireSession();
  const { id } = await params;
  const workflowId = Number(id);
  if (!Number.isFinite(workflowId)) notFound();

  let workflow;
  try {
    workflow = await getWorkflowDetail(workflowId);
  } catch {
    notFound();
  }

  return <WorkflowEditor workflow={workflow} />;
}

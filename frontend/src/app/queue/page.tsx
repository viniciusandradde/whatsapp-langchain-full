import { QueuePageClient } from "@/components/queue-page-client";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function QueuePage() {
  await requireSession();

  return <QueuePageClient />;
}

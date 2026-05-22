import { BillingPageClient } from "./billing-page-client";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function BillingPage() {
  await requireSession();
  return <BillingPageClient />;
}

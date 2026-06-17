import { listApiKeys, type DisparadorApiKey } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ApiKeysClient } from "./api-keys-client";

export const dynamic = "force-dynamic";
export const metadata = { title: "Disparador · API keys" };

export default async function ApiKeysPage() {
  await requireSession();
  let initial: DisparadorApiKey[] = [];
  try {
    initial = (await listApiKeys()).items;
  } catch {
    initial = [];
  }
  return <ApiKeysClient initial={initial} />;
}

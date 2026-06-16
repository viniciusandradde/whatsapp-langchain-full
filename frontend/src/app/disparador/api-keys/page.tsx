import { listApiKeys, type DisparadorApiKey } from "@/lib/api";

import { ApiKeysClient } from "./api-keys-client";

export const metadata = { title: "Disparador · API keys" };

export default async function ApiKeysPage() {
  let initial: DisparadorApiKey[] = [];
  try {
    initial = (await listApiKeys()).items;
  } catch {
    initial = [];
  }
  return <ApiKeysClient initial={initial} />;
}

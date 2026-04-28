import "server-only";

import { ensureBootstrapAdmin } from "@/lib/bootstrap-admin-core";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

export async function ensureDefaultAdmin() {
  ensureFrontendRuntimeConfig();
  return ensureBootstrapAdmin();
}

import { UsuariosPageClient } from "./usuarios-page-client";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function UsuariosPage() {
  await requireSession();
  return <UsuariosPageClient />;
}

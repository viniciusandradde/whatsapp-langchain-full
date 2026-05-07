import { notFound } from "next/navigation";

import {
  getAgentesIA,
  getDepartamentos,
  getHooks,
  getMenu,
  getMenuItems,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { MenuEditor } from "./editor";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditMenuPage({ params }: PageProps) {
  await requireSession();
  const { id } = await params;
  const menuId = Number(id);
  if (!Number.isFinite(menuId)) notFound();

  let menu;
  try {
    menu = await getMenu(menuId);
  } catch {
    notFound();
  }

  const [itemsResp, agentesResp, depsResp, hooksResp] = await Promise.all([
    getMenuItems(menuId, { onlyActive: false }),
    getAgentesIA({ onlyActive: true }).catch(() => ({ items: [] })),
    getDepartamentos().catch(() => ({ departamentos: [] })),
    getHooks().catch(() => ({ hooks: [] })),
  ]);

  return (
    <MenuEditor
      menu={menu}
      items={itemsResp.items}
      agentes={agentesResp.items}
      departamentos={depsResp.departamentos}
      hooks={hooksResp.hooks}
    />
  );
}

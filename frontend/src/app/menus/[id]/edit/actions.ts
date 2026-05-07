"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  createMenuItem,
  deleteMenu,
  deleteMenuItem,
  reorderMenuItems,
  seedMenuFromAgentes,
  updateMenu,
  updateMenuItem,
  type MenuChatbotUpdateInput,
  type MenuItemAcaoTipo,
  type MenuItemCreateInput,
  type MenuItemUpdateInput,
} from "@/lib/api";

export async function updateMenuAction(
  menuId: number,
  body: MenuChatbotUpdateInput
): Promise<{ ok: boolean; error?: string }> {
  try {
    await updateMenu(menuId, body);
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar menu.",
    };
  }
  revalidatePath(`/menus/${menuId}/edit`);
  revalidatePath("/menus");
  return { ok: true };
}

export async function createItemAction(
  menuId: number,
  body: MenuItemCreateInput
): Promise<{ ok: boolean; error?: string; id?: number }> {
  try {
    const created = await createMenuItem(menuId, body);
    revalidatePath(`/menus/${menuId}/edit`);
    return { ok: true, id: created.id };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao criar item.",
    };
  }
}

export async function updateItemAction(
  menuId: number,
  itemId: number,
  body: MenuItemUpdateInput
): Promise<{ ok: boolean; error?: string }> {
  try {
    await updateMenuItem(menuId, itemId, body);
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar item.",
    };
  }
  revalidatePath(`/menus/${menuId}/edit`);
  return { ok: true };
}

export async function deleteItemAction(
  menuId: number,
  itemId: number
): Promise<{ ok: boolean; error?: string }> {
  try {
    await deleteMenuItem(menuId, itemId);
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao deletar item.",
    };
  }
  revalidatePath(`/menus/${menuId}/edit`);
  return { ok: true };
}

export async function reorderAction(
  menuId: number,
  parentId: number | null,
  orderedIds: number[]
): Promise<{ ok: boolean; error?: string }> {
  try {
    await reorderMenuItems(menuId, {
      parent_id: parentId,
      ordered_ids: orderedIds,
    });
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao reordenar.",
    };
  }
  revalidatePath(`/menus/${menuId}/edit`);
  return { ok: true };
}

export async function seedFromAgentesAction(
  menuId: number
): Promise<{ ok: boolean; error?: string; qtde_criados?: number }> {
  try {
    const r = await seedMenuFromAgentes(menuId);
    revalidatePath(`/menus/${menuId}/edit`);
    revalidatePath("/menus");
    return { ok: true, qtde_criados: r.qtde_criados };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao gerar menu.",
    };
  }
}

export async function deleteMenuAction(menuId: number): Promise<void> {
  try {
    await deleteMenu(menuId);
  } catch (e) {
    redirect(
      `/menus/${menuId}/edit?error=` +
        encodeURIComponent(e instanceof Error ? e.message : "Erro ao deletar.")
    );
  }
  revalidatePath("/menus");
  redirect("/menus");
}

// Re-exports pra clientes não precisarem importar o type direto
export type { MenuItemAcaoTipo };

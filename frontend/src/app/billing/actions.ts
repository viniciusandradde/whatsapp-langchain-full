"use server";

import { revalidatePath } from "next/cache";

import {
  billingCancel,
  billingCheckout,
  billingHistorico,
  billingStatus,
  type BillingStatus,
  type BillingTransacao,
  type CheckoutResult,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function _err(e: unknown): string {
  if (e instanceof Error) return e.message;
  return "Erro desconhecido";
}

export async function loadBillingStatusAction(): Promise<Result<BillingStatus>> {
  try {
    return { ok: true, data: await billingStatus() };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadBillingHistoricoAction(): Promise<
  Result<BillingTransacao[]>
> {
  try {
    const r = await billingHistorico();
    return { ok: true, data: r.items };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function checkoutAction(
  plano: string
): Promise<Result<CheckoutResult>> {
  try {
    const r = await billingCheckout(plano);
    revalidatePath("/billing");
    return { ok: true, data: r };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadPlanosCatalogoAction(): Promise<
  Result<import("@/lib/api").PlanoCatalogo[]>
> {
  try {
    const { getPlanosCatalogo } = await import("@/lib/api");
    const { items } = await getPlanosCatalogo();
    return { ok: true, data: items };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function cancelSubscriptionAction(): Promise<Result<{ status: string }>> {
  try {
    const r = await billingCancel();
    revalidatePath("/billing");
    return { ok: true, data: r };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

/** Superadmin cola os links dos planos hospedados (leva F). */
export async function setPlanoLinksAction(
  slug: string,
  body: { link_infinitepay: string | null; link_mercadopago: string | null }
): Promise<Result<{ slug: string }>> {
  try {
    const { setPlanoLinks } = await import("@/lib/api");
    const r = await setPlanoLinks(slug, body);
    revalidatePath("/billing");
    return { ok: true, data: r };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

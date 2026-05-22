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
  plano: "pro" | "enterprise"
): Promise<Result<CheckoutResult>> {
  try {
    const r = await billingCheckout(plano);
    revalidatePath("/billing");
    return { ok: true, data: r };
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

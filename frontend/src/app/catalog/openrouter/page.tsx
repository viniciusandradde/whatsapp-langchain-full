import { Globe } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ApiError } from "@/components/ui/api-error";
import {
  getOpenRouterAlertas,
  getOpenRouterEventos,
  getOpenRouterModelos,
  getOpenRouterRankings,
  getOpenRouterSaude,
  getOpenRouterProvedores,
  getOpenRouterStatus,
  isMyAdmin,
  type OpenRouterModelo,
  type OpenRouterProvedor,
  type OpenRouterStatus,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { CatalogoClient } from "./catalogo-client";

export const dynamic = "force-dynamic";

/**
 * /catalog/openrouter — o catálogo COMPLETO do OpenRouter dentro do Nexus
 * (mig 178, módulo Saúde de IA). Observabilidade, não cardápio: as empresas
 * seguem escolhendo só entre os curados; daqui um modelo chega lá pela ação
 * "Promover" — nunca sozinho.
 *
 * Superadmin-only: o guard real é do backend; a page repete a checagem pra
 * não renderizar uma tela de erros a quem não deve vê-la (padrão
 * /relatorios/uso).
 */
export default async function CatalogoOpenRouterPage() {
  await requireSession();

  let isAdmin = false;
  try {
    isAdmin = (await isMyAdmin()).is_superadmin;
  } catch {
    isAdmin = false;
  }
  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <PageHeader
          titulo="Catálogo OpenRouter"
          descricao="Modelos e provedores disponíveis no OpenRouter."
          icon={Globe}
        />
        <p className="text-sm text-muted-foreground">
          Acesso restrito à administração da plataforma.
        </p>
      </div>
    );
  }

  let status: OpenRouterStatus | null = null;
  let modelos: OpenRouterModelo[] = [];
  let provedores: OpenRouterProvedor[] = [];
  let saude: Awaited<ReturnType<typeof getOpenRouterSaude>> | null = null;
  let rankings: Awaited<ReturnType<typeof getOpenRouterRankings>> | null = null;
  let alertas: Awaited<ReturnType<typeof getOpenRouterAlertas>> | null = null;
  let eventos: Awaited<ReturnType<typeof getOpenRouterEventos>> | null = null;
  let error: unknown = null;
  try {
    const [s, m, p, sa, rk, al, ev] = await Promise.all([
      getOpenRouterStatus(),
      getOpenRouterModelos(),
      getOpenRouterProvedores(),
      getOpenRouterSaude(),
      getOpenRouterRankings(),
      getOpenRouterAlertas(),
      getOpenRouterEventos(),
    ]);
    status = s;
    modelos = m.items;
    provedores = p.items;
    saude = sa;
    rankings = rk;
    alertas = al;
    eventos = ev;
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Catálogo OpenRouter"
        descricao="Todos os modelos e provedores do OpenRouter, sincronizados para observabilidade. A seleção das empresas continua na lista curada."
        icon={Globe}
      />
      {error ? (
        <ApiError variant="card" error={error} />
      ) : (
        <CatalogoClient
          status={status}
          modelosIniciais={modelos}
          provedores={provedores}
          saude={saude}
          rankings={rankings}
          alertas={alertas}
          eventos={eventos?.items ?? []}
        />
      )}
    </div>
  );
}

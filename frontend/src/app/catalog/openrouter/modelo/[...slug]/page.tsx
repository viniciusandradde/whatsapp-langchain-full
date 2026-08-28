import Link from "next/link";
import { ArrowLeft, Globe } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ApiError } from "@/components/ui/api-error";
import {
  getOpenRouterAnalise,
  getOpenRouterHistorico,
  isMyAdmin,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ModeloDetalhe } from "./modelo-detalhe";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ slug: string[] }>;
}

/**
 * Análise profunda de UM modelo — a página que faz o hub ser hub: ficha
 * completa (preço/benchmark/provedores), série histórica de saúde da NOSSA
 * coleta, trajetória no ranking do mercado e as novidades do modelo.
 * Rota catch-all porque o slug tem "/" (author/model).
 */
export default async function ModeloOpenRouterPage({ params }: Props) {
  await requireSession();
  const { slug } = await params;
  const modeloSlug = slug.join("/");

  let isAdmin = false;
  try {
    isAdmin = (await isMyAdmin()).is_superadmin;
  } catch {
    isAdmin = false;
  }
  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <PageHeader titulo={modeloSlug} icon={Globe} />
        <p className="text-sm text-muted-foreground">
          Acesso restrito à administração da plataforma.
        </p>
      </div>
    );
  }

  let analise: Awaited<ReturnType<typeof getOpenRouterAnalise>> | null = null;
  let historico: Awaited<ReturnType<typeof getOpenRouterHistorico>> | null =
    null;
  let error: unknown = null;
  try {
    [analise, historico] = await Promise.all([
      getOpenRouterAnalise(modeloSlug),
      getOpenRouterHistorico(modeloSlug),
    ]);
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/catalog/openrouter"
          className="text-muted-foreground transition-colors hover:text-foreground"
          aria-label="Voltar ao catálogo"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <PageHeader
          titulo={modeloSlug}
          descricao="Análise do modelo: preços, benchmarks, saúde por provedor, trajetória no mercado e novidades."
          icon={Globe}
        />
      </div>
      {error || !analise || !historico ? (
        <ApiError
          variant="card"
          error={error ?? new Error("Modelo não encontrado no catálogo.")}
        />
      ) : (
        <ModeloDetalhe analise={analise} historico={historico} />
      )}
    </div>
  );
}

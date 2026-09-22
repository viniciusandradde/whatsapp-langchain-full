import Link from "next/link";
import {
  Bot,
  BookX,
  CircleCheck,
  CirclePause,
  CpuIcon,
  Plus,
  SlidersHorizontal,
  Star,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAgentesIA } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { DeactivateAllAgentesButton } from "./deactivate-all-button";

export const dynamic = "force-dynamic";

/** Um problema que impede o agente de atender, ou o degrada. */
interface Pendencia {
  icon: typeof CirclePause;
  texto: string;
  grave: boolean;
}

/**
 * O que há de errado com o agente, do mais grave pro menos.
 *
 * O card mostra ISTO, não `temp 0.50 · top_p 0.85`. A régua veio da auditoria
 * (item U2): abrir /agents e responder "qual agente está quebrado?" em menos de
 * 3 segundos, sem clicar. Hiperparâmetro é assunto de quem já entrou no editor.
 */
function diagnosticar(a: {
  ativo: boolean;
  modelo_efetivo: string | null;
  base_conhecimento_ids: number[];
}): Pendencia[] {
  const out: Pendencia[] = [];
  if (!a.ativo) {
    out.push({
      icon: CirclePause,
      texto: "Inativo — não responde a ninguém",
      grave: true,
    });
  }
  // `modelo_efetivo`, não `modelo`: a legada parou em 22/08 e dizia que o
  // agente da VSA rodava um modelo que nenhum turno usava.
  if (!a.modelo_efetivo) {
    out.push({
      icon: CpuIcon,
      texto: "Sem modelo de IA definido",
      grave: true,
    });
  }
  if (a.base_conhecimento_ids.length === 0) {
    out.push({
      icon: BookX,
      texto: "Sem base de conhecimento",
      grave: false,
    });
  }
  return out;
}

/**
 * Página /agents — lista híbrida pós Sub-fase A.
 *
 * Lista os agentes da empresa. Até a mig 156 esta tela tinha uma segunda
 * seção, "Templates do catálogo", que exibia o caminho do diretório Python
 * de cada template — conceito interno numa tela de cliente. Os templates
 * viraram topologia (dois valores) e deixaram de ser algo a escolher aqui.
 */
export default async function AgentsPage() {
  await requireSession();

  let agentesDb: Awaited<ReturnType<typeof getAgentesIA>>["items"] = [];
  let dbError: string | null = null;

  try {
    const r = await getAgentesIA();
    agentesDb = r.items;
  } catch (e) {
    dbError = e instanceof Error ? e.message : "Erro ao listar agentes DB.";
  }

  const respondendo = agentesDb.filter((a) => a.ativo).length;
  const comPendencia = agentesDb.filter(
    (a) => diagnosticar(a).length > 0,
  ).length;

  return (
    <div className="space-y-8">
      <PageHeader
        titulo="Agentes"
        descricao="Quem responde pelo WhatsApp no seu lugar. Cada agente tem instruções, base de conhecimento e modelo próprios."
        icon={Bot}
        acoes={
          <>
            <DeactivateAllAgentesButton
              ativosCount={agentesDb.filter((a) => a.ativo).length}
            />
            <ButtonLink href="/agents/new">
              <Plus className="size-4" />
              Novo agente
            </ButtonLink>
          </>
        }
      />

      {/* ---- Agentes DB (cadastrados via UI) ---- */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Cadastrados ({agentesDb.length})
          </h2>
          {/* O placar responde "está tudo bem?" antes de a pessoa ler card
              nenhum. Sem ele, 8 de 9 inativos passavam como contorno cinza. */}
          {agentesDb.length > 0 && (
            <>
              <Badge variant={respondendo > 0 ? "success" : "warning"}>
                {respondendo} respondendo
              </Badge>
              {comPendencia > 0 && (
                <Badge variant="warning">
                  {comPendencia}{" "}
                  {comPendencia === 1 ? "com pendência" : "com pendências"}
                </Badge>
              )}
            </>
          )}
        </div>
        {dbError && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {dbError}
          </p>
        )}
        {!dbError && agentesDb.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center">
              <Bot className="mx-auto mb-2 size-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                Nenhum agente cadastrado ainda. Use{" "}
                <Link
                  href="/agents/new"
                  className="text-brand-primary underline"
                >
                  Novo agente
                </Link>{" "}
                pra criar o primeiro.
              </p>
            </CardContent>
          </Card>
        )}
        {agentesDb.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {agentesDb.map((a) => {
              const pendencias = diagnosticar(a);
              return (
                <Card key={a.id}>
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="flex items-center gap-2 text-base">
                        {a.nome}
                        {a.is_default && (
                          <Star className="size-3.5 fill-brand-primary text-brand-primary" />
                        )}
                      </CardTitle>
                      <Badge variant={a.ativo ? "success" : "warning"}>
                        {a.ativo ? "Respondendo" : "Inativo"}
                      </Badge>
                    </div>
                    <p className="font-mono text-[11px] text-muted-foreground">
                      {a.slug}
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    {pendencias.length > 0 ? (
                      <ul className="space-y-1">
                        {pendencias.map((p) => (
                          <li
                            key={p.texto}
                            className={
                              p.grave
                                ? "flex items-center gap-1.5 text-warning"
                                : "flex items-center gap-1.5 text-muted-foreground"
                            }
                          >
                            <p.icon className="size-3.5 shrink-0" />
                            {p.texto}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="flex items-center gap-1.5 text-success">
                        <CircleCheck className="size-3.5 shrink-0" />
                        Pronto para atender
                      </p>
                    )}
                    <p className="text-muted-foreground">
                      {a.modelo_efetivo ?? "sem modelo"}
                    </p>
                  </CardContent>
                  <CardFooter className="gap-2">
                    {/* `outline`, não `default`: com 9 agentes a tela tinha 9
                      botões na cor primária, e a ação primária de verdade
                      ("Novo agente") sumia no meio. Uma por tela (ADR-014). */}
                    <ButtonLink
                      href={`/agents/db/${a.slug}`}
                      variant="outline"
                      size="sm"
                      className="w-full flex-1"
                    >
                      <SlidersHorizontal className="size-3.5" />
                      Editar
                    </ButtonLink>
                  </CardFooter>
                </Card>
              );
            })}
          </div>
        )}
      </section>

    </div>
  );
}

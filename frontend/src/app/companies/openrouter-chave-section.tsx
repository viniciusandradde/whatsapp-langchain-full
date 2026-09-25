"use client";

import { useState, useTransition } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Empresa, OpenRouterChaveStatus } from "@/lib/api";
import { dataHora } from "@/lib/formato";

import {
  loadOpenRouterChaveAction,
  provisionarOpenRouterChaveAction,
  removerOpenRouterChaveAction,
  setLimiteOpenRouterChaveAction,
  setOpenRouterChaveAction,
} from "./actions";

function usd(v: number | null | undefined): string {
  if (v == null) return "—";
  return `US$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function limiteDoCampo(texto: string): number | null | undefined {
  const t = texto.trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0) return undefined;
  return n;
}

/**
 * Chave da OpenRouter por empresa (ADR-007, mig 204).
 *
 * Por padrão a inteligência artificial da empresa sai pela chave da
 * plataforma. Aqui o admin pode trazer a própria chave (o consumo passa a
 * sair da conta dele na OpenRouter) e o superadmin pode criar uma chave
 * exclusiva pela plataforma, com limite de crédito. A chave nunca volta da
 * API: a tela mostra só o começo dela.
 */
export function OpenRouterChaveSection({
  empresa,
  superadmin,
}: {
  empresa: Empresa;
  superadmin: boolean;
}) {
  const queryClient = useQueryClient();
  const chaveKey = ["openrouter-chave", empresa.id] as const;
  const status = useQuery({
    queryKey: chaveKey,
    queryFn: async () => {
      const r = await loadOpenRouterChaveAction(empresa.id);
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 30_000,
  });

  const [chave, setChave] = useState("");
  const [limite, setLimite] = useState("");
  const [confirmarRemocao, setConfirmarRemocao] = useState(false);
  const [confirmarTroca, setConfirmarTroca] = useState(false);
  const [ocupado, startOcupado] = useTransition();

  function aplicar(novo: OpenRouterChaveStatus) {
    queryClient.setQueryData(chaveKey, novo);
  }

  function salvarChave() {
    if (!chave.trim()) {
      toast.error("Cole a chave da OpenRouter.");
      return;
    }
    startOcupado(async () => {
      const r = await setOpenRouterChaveAction(empresa.id, chave);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      setChave("");
      aplicar(r.data);
      toast.success("Chave própria salva. As próximas respostas da IA saem por ela.");
    });
  }

  function remover() {
    startOcupado(async () => {
      const r = await removerOpenRouterChaveAction(empresa.id);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      aplicar(r.data);
      if (r.data.apagada_na_openrouter === false) {
        toast.warning(
          "A chave saiu daqui, mas a OpenRouter não confirmou a exclusão. Confira no painel dela."
        );
      } else {
        toast.success("A empresa voltou a usar a chave da plataforma.");
      }
    });
  }

  function provisionar() {
    const valor = limiteDoCampo(limite);
    if (valor === undefined) {
      toast.error("Informe um limite válido em dólares, ou deixe vazio para sem limite.");
      return;
    }
    startOcupado(async () => {
      const r = await provisionarOpenRouterChaveAction(empresa.id, valor);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      aplicar(r.data);
      toast.success(
        valor == null
          ? "Chave exclusiva criada, sem limite de crédito."
          : `Chave exclusiva criada com limite de ${usd(valor)}.`
      );
    });
  }

  function alterarLimite() {
    const valor = limiteDoCampo(limite);
    if (valor === undefined) {
      toast.error("Informe um limite válido em dólares, ou deixe vazio para sem limite.");
      return;
    }
    startOcupado(async () => {
      const r = await setLimiteOpenRouterChaveAction(empresa.id, valor);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      aplicar(r.data);
      toast.success(valor == null ? "Chave sem limite de crédito." : `Limite ajustado para ${usd(valor)}.`);
    });
  }

  const s = status.data;
  const provisionada = s?.origem === "provisionada";
  const podeRemover = !!s?.definida && (!provisionada || superadmin);

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4" />
          Chave da OpenRouter
        </CardTitle>
        <CardDescription>
          Por padrão a inteligência artificial desta empresa usa a chave da plataforma e o gasto é
          somado ao consumo dela aqui no painel. Com uma chave própria, o consumo sai da conta da
          empresa na OpenRouter. A chave fica guardada de forma cifrada e nunca é mostrada de
          novo: só o começo dela.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {status.isPending ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : status.isError ? (
          <p className="text-sm text-destructive">{status.error.message}</p>
        ) : s ? (
          <>
            <div className="space-y-1 text-sm">
              <p>
                Hoje:{" "}
                <span className="font-medium text-foreground">
                  {!s.definida
                    ? "chave da plataforma"
                    : provisionada
                      ? "chave exclusiva criada pela plataforma"
                      : "chave própria da empresa"}
                </span>
                {s.prefixo ? (
                  <>
                    {" "}
                    · <span className="font-mono text-xs">{s.prefixo}</span>
                  </>
                ) : null}
                {s.definida_em ? (
                  <span className="text-muted-foreground"> · definida em {dataHora(s.definida_em)}</span>
                ) : null}
              </p>
              {s.uso ? (
                <p className="text-muted-foreground">
                  Na OpenRouter: usado {usd(s.uso.uso_usd)}
                  {s.uso.uso_mes_usd != null ? ` (este mês ${usd(s.uso.uso_mes_usd)})` : ""}
                  {s.uso.limite_usd != null
                    ? ` · limite ${usd(s.uso.limite_usd)} · restam ${usd(s.uso.limite_restante_usd)}`
                    : " · sem limite de crédito"}
                  {s.uso.desativada ? " · desativada na OpenRouter" : ""}
                </p>
              ) : s.uso_erro ? (
                <p className="text-warning text-xs">{s.uso_erro}</p>
              ) : null}
            </div>

            <div className="space-y-2 rounded-md border border-border p-3">
              <Label htmlFor={`or-chave-${empresa.id}`}>
                {s.definida && !provisionada ? "Trocar a chave própria" : "Usar uma chave própria"}
              </Label>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  id={`or-chave-${empresa.id}`}
                  type="password"
                  autoComplete="off"
                  value={chave}
                  onChange={(e) => setChave(e.target.value)}
                  placeholder="cole a chave da conta da empresa na OpenRouter"
                  disabled={ocupado}
                  className="min-w-0 flex-1 font-mono"
                  maxLength={200}
                />
                <Button type="button" onClick={salvarChave} disabled={ocupado || !chave.trim()}>
                  {ocupado ? <Loader2 className="size-4 animate-spin" /> : <KeyRound className="size-4" />}
                  Salvar chave
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                A chave é conferida na OpenRouter antes de ser guardada. Se ela ficar sem crédito,
                a inteligência artificial desta empresa para de responder até a chave ser trocada
                ou removida.
              </p>
            </div>

            {superadmin ? (
              <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
                <p className="text-sm font-medium">Chave exclusiva criada pela plataforma</p>
                <p className="text-xs text-muted-foreground">
                  A plataforma cria na conta dela uma chave só para esta empresa, com limite de
                  crédito. O gasto continua sendo da plataforma, mas fica separado por chave e o
                  limite de uso de um cliente não atrapalha os outros. Só o superadmin vê este
                  bloco.
                </p>
                {!s.provisionamento_disponivel ? (
                  <p className="text-xs text-warning">
                    A plataforma ainda não tem a chave de gestão da OpenRouter configurada. Peça a
                    quem cuida do servidor.
                  </p>
                ) : null}
                <div className="flex flex-wrap items-end gap-2">
                  <div className="space-y-1">
                    <Label htmlFor={`or-limite-${empresa.id}`}>Limite de crédito (US$)</Label>
                    <Input
                      id={`or-limite-${empresa.id}`}
                      inputMode="decimal"
                      value={limite}
                      onChange={(e) => setLimite(e.target.value)}
                      placeholder={s.limite_usd != null ? String(s.limite_usd) : "sem limite"}
                      disabled={ocupado || !s.provisionamento_disponivel}
                      className="w-40"
                    />
                  </div>
                  {provisionada ? (
                    <>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={alterarLimite}
                        disabled={ocupado || !s.provisionamento_disponivel}
                      >
                        Alterar limite
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setConfirmarTroca(true)}
                        disabled={ocupado || !s.provisionamento_disponivel}
                      >
                        <RefreshCw className="size-4" />
                        Trocar por uma chave nova
                      </Button>
                    </>
                  ) : (
                    <Button
                      type="button"
                      onClick={provisionar}
                      disabled={ocupado || !s.provisionamento_disponivel}
                    >
                      {ocupado ? <Loader2 className="size-4 animate-spin" /> : <KeyRound className="size-4" />}
                      Criar chave exclusiva
                    </Button>
                  )}
                </div>
              </div>
            ) : null}

            {s.definida ? (
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setConfirmarRemocao(true)}
                  disabled={ocupado || !podeRemover}
                >
                  <Trash2 className="size-4" />
                  Voltar para a chave da plataforma
                </Button>
                {!podeRemover ? (
                  <span className="text-xs text-muted-foreground">
                    Só o superadmin remove uma chave criada pela plataforma.
                  </span>
                ) : null}
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>

      <ConfirmDestrutivo
        aberto={confirmarRemocao}
        onAbertoChange={setConfirmarRemocao}
        titulo="Voltar para a chave da plataforma?"
        objeto={`a chave ${s?.prefixo ?? ""} de ${empresa.nome}`}
        descricao={
          <p>
            As próximas respostas da inteligência artificial desta empresa sairão pela chave da
            plataforma
            {provisionada ? ", e a chave exclusiva será apagada na OpenRouter" : ""}.
          </p>
        }
        rotuloAcao="Remover chave"
        onConfirmar={remover}
      />
      <ConfirmDestrutivo
        aberto={confirmarTroca}
        onAbertoChange={setConfirmarTroca}
        titulo="Trocar por uma chave nova?"
        objeto={`a chave ${s?.prefixo ?? ""} de ${empresa.nome}`}
        descricao={
          <p>
            Uma chave nova é criada na OpenRouter com o limite informado e entra no lugar da atual,
            que é apagada em seguida. Não há pausa no atendimento.
          </p>
        }
        rotuloAcao="Trocar chave"
        tom="serio"
        onConfirmar={provisionar}
      />
    </Card>
  );
}

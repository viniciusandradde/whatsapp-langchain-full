"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff } from "lucide-react";

import { Button } from "@/components/ui/button";

const SOM_STORAGE_KEY = "atd-som-notificacao";
const SOM_EVENTO = "atd-som-changed";

// Circuit breaker do refresh. Cada router.refresh() re-executa os 4 fetches
// da página; uma rajada de eventos SSE (ou várias abas do mesmo operador)
// pode estourar o rate limit e travar a fila. Teto por janela + backoff.
const DEBOUNCE_MS = 2000;
const JANELA_MS = 60_000;
const TETO_REFRESH_JANELA = 15; // máx. refreshes por 60s por aba (≈60 req)
const PAUSA_MS = 60_000; // recuo ao estourar o teto ou carregar em erro

/** try/catch: o acessor de localStorage pode lançar (site data bloqueado). */
function lerSomLigado(): boolean {
  try {
    return localStorage.getItem(SOM_STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

function assinarSom(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(SOM_EVENTO, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SOM_EVENTO, onChange);
  };
}

/**
 * Mantém a fila viva sem o operador recarregar (leva fila 2026-08).
 *
 * A lista é server component `force-dynamic`: antes disto, conversa nova só
 * aparecia em navegação — os únicos polls eram os contadores da sidebar.
 * Este componente abre UM EventSource no stream da empresa (mig 145, o
 * mesmo que o app Android usa) e, a cada evento `mensagem`/`status_changed`,
 * faz `router.refresh()` com debounce de 2s — o servidor re-renderiza a
 * lista e o estado client (conversa aberta, composer) sobrevive.
 *
 * O payload `kind=inbound` com atendimento fora dos já vistos é o sinal de
 * conversa nova: beep curto (WebAudio, sem asset) + Notification quando
 * permitida. O sino liga/desliga o som (localStorage) e pede a permissão de
 * notificação — que o navegador só concede em resposta a um clique.
 *
 * Fallback: se o stream nunca abrir (401/500), poll de 30s com a aba
 * visível — espelho do safety net do drawer.
 */
export function FilaLive({
  idsVisiveis,
  erroCarregamento = false,
}: {
  idsVisiveis: number[];
  /** A página carregou em erro (ex.: a caixa tomou 429). Faz a fila recuar
   *  por PAUSA_MS em vez de seguir refrescando — quebra o loop. */
  erroCarregamento?: boolean;
}) {
  const queryClient = useQueryClient();
  // Preferência do som via useSyncExternalStore: localStorage é a fonte,
  // snapshot do servidor é "ligado" — sem setState síncrono em effect (o
  // React Compiler reprova) e sem mismatch de hidratação.
  const somLigado = useSyncExternalStore(assinarSom, lerSomLigado, () => true);
  const vistos = useRef<Set<number>>(new Set(idsVisiveis));
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Circuit breaker: instante até quando os refreshes ficam pausados +
  // histórico de refreshes na janela deslizante (nível do componente pra
  // sobreviver a re-render e ser visto pelo effect de erroCarregamento).
  const pausadoAte = useRef(0);
  const refreshHist = useRef<number[]>([]);

  // Cada render do server traz os ids da página — acumula, não substitui:
  // conversa que já beepou uma vez não beepa de novo após o refresh.
  useEffect(() => {
    for (const id of idsVisiveis) vistos.current.add(id);
  }, [idsVisiveis]);

  // Página carregou em erro → recua PAUSA_MS. Se a caixa está tomando 429,
  // continuar refrescando só realimenta o estouro (a janela do rate limit é
  // fixa por minuto e não se recupera enquanto o cliente martelar).
  useEffect(() => {
    if (erroCarregamento) pausadoAte.current = Date.now() + PAUSA_MS;
  }, [erroCarregamento]);

  useEffect(() => {
    let es: EventSource | null = null;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;
    let openedOk = false;
    let vivo = true;

    function podeRefrescar(): boolean {
      const agora = Date.now();
      if (agora < pausadoAte.current) return false;
      refreshHist.current = refreshHist.current.filter(
        (t) => agora - t < JANELA_MS
      );
      if (refreshHist.current.length >= TETO_REFRESH_JANELA) {
        // Rajada anormal (loop, muitas abas): recua e para de martelar.
        pausadoAte.current = agora + PAUSA_MS;
        if (process.env.NODE_ENV !== "production") {
          console.warn("[fila-live] teto de refresh atingido — pausando 60s");
        }
        return false;
      }
      return true;
    }

    function agendarRefresh() {
      // Debounce: rajada de eventos (várias mensagens num burst) vira UM
      // refresh — cada refresh re-executa os fetches da página no servidor.
      if (refreshTimer.current) return;
      if (Date.now() < pausadoAte.current) return;
      refreshTimer.current = setTimeout(() => {
        refreshTimer.current = null;
        if (!vivo || document.visibilityState !== "visible") return;
        if (!podeRefrescar()) return;
        refreshHist.current.push(Date.now());
        // Invalida SÓ a fila — antes era `router.refresh()`, que re-executava
        // os quatro fetches da página a cada evento. O circuit breaker acima
        // continua como defesa, mas o custo por evento caiu para 1 request.
        queryClient.invalidateQueries({ queryKey: ["atendimentos"] });
        // Badges da barra lateral seguem o mesmo evento — contagem e lista
        // têm que concordar (gotcha_contagem_por_endpoint_permissao).
        queryClient.invalidateQueries({ queryKey: ["contadores"] });
      }, DEBOUNCE_MS);
    }

    function notificarConversaNova(atendimentoId: number) {
      if (vistos.current.has(atendimentoId)) return;
      vistos.current.add(atendimentoId);
      // Lê a preferência na hora do evento — sempre fresca, sem ref.
      if (lerSomLigado()) tocarBeep();
      try {
        if (
          typeof Notification !== "undefined" &&
          Notification.permission === "granted" &&
          document.visibilityState !== "visible"
        ) {
          new Notification("Nova conversa na fila", {
            body: "Um cliente está aguardando atendimento.",
            tag: `atd-nova-${atendimentoId}`,
          });
        }
      } catch {
        // Notification pode lançar em contexto sem suporte — só o beep basta.
      }
    }

    function startFallbackPolling() {
      if (fallbackTimer) return;
      // Passa pelo mesmo circuit breaker (agendarRefresh), não router.refresh
      // direto — senão o fallback ignoraria a pausa e o teto.
      fallbackTimer = setInterval(agendarRefresh, 30_000);
    }

    function connect() {
      es = new EventSource("/api/sse/empresa");
      es.addEventListener("connected", () => {
        // Chega no início do stream E quando o NotifyHub da API reconecta
        // ao Postgres — nesse caso pode ter perdido evento: ressincroniza.
        if (openedOk) agendarRefresh();
        openedOk = true;
        if (fallbackTimer) {
          clearInterval(fallbackTimer);
          fallbackTimer = null;
        }
      });
      es.addEventListener("mensagem", (ev) => {
        try {
          const payload = JSON.parse((ev as MessageEvent).data) as {
            atendimento_id?: number;
            kind?: string;
          };
          if (payload.kind === "inbound" && payload.atendimento_id) {
            notificarConversaNova(payload.atendimento_id);
          }
        } catch {
          // Payload ilegível não impede o refresh.
        }
        agendarRefresh();
      });
      es.addEventListener("status_changed", agendarRefresh);
      es.onerror = () => {
        // EventSource auto-reconecta; se nunca abriu (401/500), o loop de
        // reconexão não resolve — cai pro poll de 30s.
        if (!openedOk) startFallbackPolling();
      };
    }

    connect();
    return () => {
      vivo = false;
      es?.close();
      if (fallbackTimer) clearInterval(fallbackTimer);
      if (refreshTimer.current) {
        clearTimeout(refreshTimer.current);
        refreshTimer.current = null;
      }
    };
  }, [queryClient]);

  function alternarSom() {
    const ligar = !somLigado;
    try {
      localStorage.setItem(SOM_STORAGE_KEY, ligar ? "on" : "off");
    } catch {
      // Sem storage a preferência não persiste nem re-renderiza — aceitável.
    }
    window.dispatchEvent(new Event(SOM_EVENTO));
    if (ligar) {
      // O clique é o único momento em que o navegador deixa pedir permissão
      // de notificação — e também destrava o AudioContext pro beep.
      try {
        if (
          typeof Notification !== "undefined" &&
          Notification.permission === "default"
        ) {
          void Notification.requestPermission();
        }
      } catch {
        // Sem suporte a Notification: segue só com o beep.
      }
      tocarBeep();
    }
  }

  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={alternarSom}
      aria-label={
        somLigado
          ? "Desligar som de conversa nova"
          : "Ligar som de conversa nova"
      }
      title={
        somLigado
          ? "Som de conversa nova ligado — clique pra desligar"
          : "Som de conversa nova desligado — clique pra ligar"
      }
    >
      {somLigado ? (
        <Bell className="size-4" />
      ) : (
        <BellOff className="size-4 text-muted-foreground" />
      )}
    </Button>
  );
}

/**
 * Beep curto de dois tons via WebAudio — sem asset binário no bundle.
 * Navegador bloqueia áudio antes do primeiro gesto do usuário; o try/catch
 * engole o `NotAllowedError` e a notificação visual segue valendo.
 */
function tocarBeep() {
  try {
    type JanelaComWebkit = Window & { webkitAudioContext?: typeof AudioContext };
    const Ctx =
      window.AudioContext ?? (window as JanelaComWebkit).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const ganho = ctx.createGain();
    ganho.gain.value = 0.04;
    ganho.connect(ctx.destination);
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1174, ctx.currentTime + 0.12);
    osc.connect(ganho);
    osc.start();
    osc.stop(ctx.currentTime + 0.24);
    osc.onended = () => void ctx.close().catch(() => {});
  } catch {
    // Sem áudio (autoplay bloqueado, contexto sem suporte) — silêncio.
  }
}

# Disparo em massa (Evolution/Baileys) — melhores práticas anti-ban

> Consolidado de pesquisa multi-fonte (deep-research, run `wf_e3a8c3d8-71e`,
> 2026-06-17). 12 claims verificados adversarialmente (2/3+ votos). A síntese
> automática foi cortada por limite de sessão; este doc é a consolidação manual.
> **Contexto que originou:** campanha de 147 com foto via Evolution caiu com ~23%
> "Connection Closed 500", a sessão `vsa-tecnologia` foi **desvinculada
> (device_removed/401)** e o número **restringido pela Meta**.

## 1. Por que "Connection Closed 500"
- É um **"Timed Out" do Baileys** (`node_modules/baileys/lib/Utils/generics.js`)
  quando o **socket WhatsApp cai** durante validação `onWhatsApp` / `sendText`.
  Instância vai pra `connecting` e os envios na janela falham; depois normaliza.
  Fontes: EvolutionAPI issues [#1286](https://github.com/EvolutionAPI/evolution-api/issues/1286),
  [#1772](https://github.com/EvolutionAPI/evolution-api/issues/1772). (3-0 / 2-1)
- **Fix de servidor reportado:** setar env **`CONFIG_SESSION_PHONE_VERSION`** no
  Evolution pra uma versão atual do WhatsApp Web resolveu pra outros usuários. [#1286] (2-1)

## 2. Mídia é mais frágil (confirmado)
Envio de mídia no Evolution falha 500 ("Media upload failed on all hosts") de forma
**não-determinística mesmo em volume baixo** — instabilidade do próprio Evolution,
não só ritmo. [EvolutionAPI #1703] (2-1) → **mídia em massa por Baileys é intrinsecamente arriscada.**

## 3. Aquecimento de número (números verificados)
- Ramp baileys-antiban: **Dia 1 = 20 msgs**, Dia 2 ≈ 36, **~1.8x/dia**, capacidade
  plena **Dia 8+**. [github.com/kobie3717/baileys-antiban] (3-0)
- Conservador: **5–10 msgs/dia** pra contatos que respondem, subindo em **14 dias**. [wasenderapi] (3-0)
- Semana 1 = uso manual; semana 2 = 10–20/dia engajados; semana 3 = +20% a cada poucos dias. [wasenderapi] (2-1)
- Princípio geral: começar com tráfego "quente"/user-initiated, subir gradual, **sem picos**. [whapi.cloud] (3-0)

## 4. Volume seguro / descanso
- **< 30 msgs/hora = seguro · 30–60 = alerta · > 60 = perigo** (obs. de fornecedor, não Meta). [achiya-automation] (2-1)
- **A cada 50 enviados → pausa de 10–15 min.** [wasenderapi] (3-0)
- ⚠️ Números de **intervalo entre msgs** (15–45s, 30–90s) saíram **refutados/incertos** na verificação.
  Não fixar número exato; princípio = lento + aleatório + lotes pequenos.

## 5. Volume real → WABA oficial
Cloud API tiers: **250/24h** (não-verificado) → 1k → 10k → 100k → ilimitado; ~80 msg/s
(tiers 0-3). [chatarmin] (2-1). Único caminho sem risco de desvínculo/ban pra volume.

## 6. Retry
"Connection Closed" é **transitória** (sessão volta) → o disparador deve **re-tentar**
(backoff), não marcar `falhou` na hora.

## Guard-rails a implementar no disparador (TODO)
1. **Trava de saúde da sessão**: checar `connectionState` antes de cada lote; se ≠ `open`, pausar.
2. **Retry com backoff** em erro transitório (Connection Closed) antes de `falhou`.
3. **Teto diário por conexão + aquecimento** (ramp ~1.8x/dia, começa ~20).
4. **Pausa 10–15 min a cada 50** enviados.
5. **Intervalo mínimo forçado pra mídia** (>> texto) + nudge pra WABA.
6. Server Evolution: avaliar `CONFIG_SESSION_PHONE_VERSION` atual.

## Refutados (NÃO citar como fato)
Intervalos 15-45s/30-90s; limites exatos do baileys-antiban (8/min,200/h,1500/dia);
vários números de warm-up específicos; "ban rate 15-30%". Votação não confirmou.

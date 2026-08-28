# ADR-001 — Roteamento de provedores no OpenRouter

- **Status:** aceita — 2026-08-25
- **Decisores:** Vinicius (dono) + análise de produção
- **Código:** `shared/llm.py::provider_preferences` (fonte única), aplicada em
  `create_chat_model` (agente) e `shared/midia_processing.py::chat_completion_media`
  (visão, transcrição, OCR, módulo Testar)

## Contexto

Recomendação corrente para uso profissional do OpenRouter (blog
[reliability/failover](https://openrouter.ai/blog/insights/reliability-failover/)
e vídeo do Ronnald Hawk): não deixar a plataforma escolher sozinha — montar um
**pool de ≥3 provedores aprovados** por estudo (quantização, latência, política
de retenção), travar com `provider.only` + ordem de preferência, e documentar a
escolha em ADR.

Antes de aplicar, confrontamos o conselho com a nossa produção.

## O que a produção mostra (30 dias de `ia_execucao`, 2026-08-25)

| modelo | chamadas | provedores no OpenRouter |
|---|---|---|
| google/gemini-3.1-flash-lite | 914 | **2** — Google AI Studio + Vertex (ambos a própria Google) |
| google/gemini-3-flash-preview | 168 | 2 — idem |
| google/gemini-2.5-flash[-lite] | 93 | 2 — idem |
| openai/gpt-audio-mini (voz) | 12 | **1** — OpenAI |
| openai/text-embedding-3-small | — | 2 — OpenAI + Azure |

**95%+ do tráfego roda em modelo proprietário.** Para esses modelos não existe
host terceiro nem quantização degradada — os endpoints são 1st-party. O risco
que o pool resolve não existe nesse tráfego, um pool de 3 é insatisfazível com
2 provedores, e `order`/`only` **desligam** o load balancing do OpenRouter,
que hoje já faz o failover entre os endpoints da Google sozinho.

## Onde o conselho SE aplica: o catálogo curado

O painel (`CURATED_MODELS`, mig 138) oferece modelos de peso aberto que
qualquer empresa pode escolher:

| modelo | provedores | quantizações servidas |
|---|---|---|
| deepseek/deepseek-v3.2 | **14** | **fp4**, fp8, unknown |
| meta-llama/llama-3.3-70b-instruct | **12** | fp8, bf16, fp16, unknown |
| z-ai/glm-4.7-flash | 4 | fp8, bf16, unknown |

Nenhum agente ativo usa esses modelos hoje (todos em Gemini) — mas no dia em
que um cliente escolher DeepSeek, a request dele não pode cair calada num host
fp4 escolhido por preço.

## Decisões

1. **Piso de quantização, não lista nominal de provedores.** Modelos de peso
   aberto recebem `provider.quantizations: ["fp8","bf16","fp16","fp32"]`.
   Bloqueia o risco real (host degradado, incl. `unknown`) sem manter uma
   lista de 14 slugs que envelhece. Um `only` nominal exige estudo com
   tráfego real (regra da casa: *validar regra contra produção*) — e não há
   tráfego nesses modelos ainda.
   **Gatilho de revisão:** primeiro cliente em modelo aberto → medir 1 semana
   de produção (provedores efetivos, latência, erros) → congelar o pool
   nominal com `only` + `order` nesta ADR.
2. **Modelos proprietários (`google/`, `openai/`, `anthropic/`, `x-ai/`) não
   recebem bloco `provider`.** O default do OpenRouter (load balance por
   preço + failover em 5xx/rate-limit) já é o ótimo para endpoints 1st-party;
   qualquer preferência explícita o desliga.
3. **Sem `data_collection: "deny"` por request.** A política de privacidade é
   da CONTA (gotcha conhecido: o 404 "No endpoints matching… data policy" do
   incidente do TTS/mig 140 se resolve em openrouter.ai/settings/privacy, não
   na chave nem na request). Um deny por request re-quebraria a voz e o
   `-preview`.
4. **Fallback de MODELO (`models: [...]`) fica fora desta leva.** É a alavanca
   de redundância certa quando o vendor é único — mas trocar o modelo troca o
   comportamento do agente (medido no golden dataset: gemini-3.1-flash-lite
   6/6; deepseek 2/5). Só entra gateado por eval do golden, como decisão de
   produto, nunca como config silenciosa de infra.
5. **Erro dentro de `choices[0].error` é recusa, não resposta.** A API
   reference documenta que o erro pode vir dentro do choice num HTTP 200 —
   variante do gotcha do envelope no topo. `chat_completion_media` passou a
   checar os dois; sem isso o erro viraria content vazio silencioso (destino
   do atendimento 574).

## Prova viva (2026-08-25)

Request real a `deepseek/deepseek-v3.2` com o piso: HTTP 200, servida por
**AtlasCloud**, que segundo `/models/…/endpoints` serve **fp8** — dentro do
piso. Custo US$0,0000043. O bloco `provider` passou no payload e o roteador
respeitou.

## Consequências

- Tráfego atual (Gemini/GPT): **payload idêntico ao de antes** — zero mudança
  de comportamento no caminho quente.
- Modelos abertos do catálogo: só hosts ≥fp8; se todos os hosts elegíveis de
  um modelo caírem, o OpenRouter devolve erro e o caminho normal de retry da
  fila assume (contrato mig 164).
- A política mora num único lugar; quem adicionar modelo ao catálogo herda a
  regra sem pensar nela.

## Adendo — eval do modelo de texto (2026-08-28)

Candidato `deepseek/deepseek-v4-flash` (US$0,087/0,174 por Mtok, ~62% mais
barato) contra o titular `google/gemini-3.1-flash-lite`, no dev:

| | gemini-3.1 | v4-flash |
|---|---|---|
| golden (50 conversas reais, mesmo judge) | **10/50** | **1/50** |
| bateria (12 cenários + injection) | 0 erros, 0 vazamentos | 0 erros, 0 vazamentos |
| latência mediana/turno | 5,2s | 11,4s |

**Veredito do dono: gemini mantido.** A falha do candidato não é segurança
nem pt-BR — é obediência ao comportamento canônico do prompt (encaminhar em
vez de interrogar, saudação padrão), a mesma família do deepseek-v3.2.
Economia recusada: US$0,96/mês. Procedimento reproduzível:
`scripts/eval_langsmith.py --model <slug> --dataset luis-fernando-gold-prod
--empresa-id 1018` + bateria da aba Testar. A alavanca de custo que resta é
o prompt (~5k tokens/mensagem; workload 99,5% input).

---
title: ADR-004 — OpenRouter como provider único (LLM + embeddings + audio)
type: adr
status: aceito
priority: media
created: 2026-04-15
updated: 2026-05-17
tags: [adr, openrouter, llm, custo]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area:
projeto_pai:
relacionados: [Stack-Tecnico]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-004 — OpenRouter como provider único

## Status

Aceito.

## Contexto

LLMs vêm de muitos providers (OpenAI, Anthropic, Google, Mistral, Groq, etc.). Cada um com API key + SDK próprios. Plus precisamos de embeddings (RAG) e audio transcription (mensagens de voz WhatsApp).

Tradicional: 1 key OpenAI + 1 key Anthropic + 1 Whisper (OpenAI) + 1 embedding provider. **4 keys, 4 billing, 4 lugares pra trocar modelo.**

## Decisão

**Única API key OpenRouter** (`OPENROUTER_API_KEY`) cobre:
- Chat completions (qualquer modelo Anthropic/OpenAI/Google/Mistral/etc.)
- Embeddings (text-embedding-3-large, etc.)
- Audio transcription (Whisper via OpenAI passthrough)

## Consequências

### Positivas
- **1 billing** — fatura única, simples pra cliente final ver custo
- **Trocar modelo é trocar string** — sem mudar key/SDK
- **OpenRouter faz fallback** — se Anthropic down, mesma chamada pode rotear pra outro
- **Catalog automático** — `/catalog/models` mostra lista atual via API OpenRouter

### Negativas
- **+5-10% markup OpenRouter** — vs API direto provider
- **Latency adicional** (~50-100ms) — proxy
- **Single point of failure** — OpenRouter down = tudo down. Risco aceitável pelo perfil de uptime atual
- **Rate limit compartilhado** — uma key pra todos modelos. Mitigado com `shared/llm.py` que tem ratelimit local

## Implementação

- `src/whatsapp_langchain/shared/llm.create_chat_model()` — factory ratelimited
- `src/whatsapp_langchain/shared/embeddings.py` — embeddings via OpenRouter
- Audio: `shared/audio.py` chama Whisper via OpenRouter

## Alternativas consideradas

- LiteLLM (lib) — fornece a mesma abstração mas keys ficam pra usuário gerenciar
- Configuração híbrida (Anthropic direto + OpenRouter pra fallback) — descartado pra simplicidade

## Relacionados

- [[03-Resources/Stack-Tecnico]]
- `.env.example` (variável OPENROUTER_API_KEY)

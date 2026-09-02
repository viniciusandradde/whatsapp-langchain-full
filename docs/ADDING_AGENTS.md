# Criando Agentes

Este guia define o contrato padrão para novos agentes neste template.

> O catálogo atual (`langgraph.json`) registra 4 grafos: `vsa_tech`,
> `atendimento_completo`, `atendimento_router` e `agendamentos`. Os exemplos
> abaixo usam `vsa_tech` como referência. Stack: LangGraph 1.1 / LangChain 1.2.

## Contrato do Agente

Cada agente deve viver em:

```text
src/whatsapp_langchain/agents/catalog/<agent_id>/
├── __init__.py
├── agent.py
├── graph.py
└── prompts.py
```

### Regras

- `agent.py` deve expor `build_graph(checkpointer=None, store=None, chat_model=None)`
- `graph.py` deve exportar variável `graph` para `langgraph dev`
- `prompts.py` deve conter `SYSTEM_PROMPT`
- não importar módulos de `server/` ou `worker/` dentro do agente
- `chat_model` é opcional: `None` mantém o default do `.env`
  (`OPENROUTER_MODEL`); o painel `/models` envia o override resolvido pelo
  loader a partir da tabela `agent_llm_config`

## Passo a passo

### 1. Criar estrutura

```bash
mkdir -p src/whatsapp_langchain/agents/catalog/meu_agente
touch src/whatsapp_langchain/agents/catalog/meu_agente/__init__.py
```

### 2. Criar prompt

```python
# prompts.py
SYSTEM_PROMPT = """Você é um assistente especializado em onboarding.
Responda em português brasileiro, de forma objetiva e útil."""
```

### 3. Implementar `build_graph`

Use a factory central de LLM (`shared.llm.create_chat_model`) e middleware centralizado de contexto.

```python
# agent.py
from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from whatsapp_langchain.agents.middleware import get_context_middleware
from whatsapp_langchain.agents.tools import read_memory, save_memory
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import SYSTEM_PROMPT


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    chat_model: str | None = None,
):
    # chat_model=None faz fallback pra settings.openrouter_model.
    # O loader resolve o valor por agente via tabela agent_llm_config.
    model = create_chat_model(model=chat_model)
    middleware = get_context_middleware()
    tools = [save_memory, read_memory] if store else []

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
        checkpointer=checkpointer,
        store=store,
    )
```

### 4. Exportar grafo para Studio

Há dois padrões válidos para o `graph.py` (ambos em uso no catálogo):

**Opção A — store em memória (variável `graph` no nível do módulo):**

```python
# graph.py
from langgraph.store.memory import InMemoryStore

from .agent import build_graph

store = InMemoryStore()
graph = build_graph(store=store)
```

**Opção B — factory que recebe o `runtime` do LangGraph** (usada por
`vsa_tech`; o runtime injeta store/checkpointer automaticamente):

```python
# graph.py
from __future__ import annotations

from typing import TYPE_CHECKING

from .agent import build_graph

if TYPE_CHECKING:
    from langgraph_sdk.runtime import ServerRuntime


def graph(runtime: ServerRuntime):
    return build_graph(store=runtime.store)
```

Em ambos os casos, o `langgraph.json` aponta para `graph.py:graph`.

### 5. Registrar no `langgraph.json`

```json
{
  "dependencies": ["."],
  "graphs": {
    "vsa_tech": "./src/whatsapp_langchain/agents/catalog/vsa_tech/graph.py:graph",
    "atendimento_completo": "./src/whatsapp_langchain/agents/catalog/atendimento_completo/graph.py:graph",
    "atendimento_router": "./src/whatsapp_langchain/agents/catalog/atendimento_router/graph.py:graph",
    "agendamentos": "./src/whatsapp_langchain/agents/catalog/agendamentos/graph.py:graph",
    "meu_agente": "./src/whatsapp_langchain/agents/catalog/meu_agente/graph.py:graph"
  },
  "env": ".env"
}
```

> O `langgraph.json` só importa para o Studio (`langgraph dev`). Em produção,
> o `loader.py` descobre o diretório do agente no catálogo automaticamente.

## Contexto e memória

### Contexto de conversa

`get_context_middleware()` aplica estratégia configurada via `.env`:
- `trim`
- `summarize`
- `none`

### Memória cross-thread

Quando `store` é fornecido:
- tool `save_memory` persiste fatos relevantes do usuário
- tool `read_memory` recupera memórias relevantes por busca semântica

Para funcionar corretamente, o runtime precisa receber:
- `thread_id` (conversa)
- `user_id` (identidade do usuário; neste projeto vem do telefone no payload do webhook)

Exemplo de `config` em invoke:

```python
config={
  "configurable": {
    "thread_id": "+5511999999999:meu_agente",
    "user_id": "+5511999999999"
  }
}
```

## Boas práticas

- mantenha prompts e regras de domínio em `prompts.py`
- use tools apenas para efeitos externos/estado durável
- evite lógica de infraestrutura dentro do agente
- prefira middleware para políticas transversais de contexto
- para memória semântica, use tools explícitas (`save_memory`/`read_memory`)
- teste no Studio primeiro, depois no fluxo assíncrono API/Worker

## Checklist de revisão

- `build_graph` aceita `checkpointer` e `store`
- agente carrega com `load_graph("meu_agente")`
- contexto funciona com `CONTEXT_STRATEGY` escolhido
- memória save/recall via tools funciona com `MEMORY_ENABLED=true`
- testes mínimos cobrindo criação e execução básica do agente

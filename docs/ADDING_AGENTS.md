# Criando Agentes

Este guia define o contrato padrão para novos agentes neste template.

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

- `agent.py` deve expor `build_graph(checkpointer=None, store=None)`
- `graph.py` deve exportar variável `graph` para `langgraph dev`
- `prompts.py` deve conter `SYSTEM_PROMPT`
- não importar módulos de `server/` ou `worker/` dentro do agente

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
):
    model = create_chat_model()
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

```python
# graph.py
from langgraph.store.memory import InMemoryStore

from whatsapp_langchain.agents.catalog.meu_agente.agent import build_graph

store = InMemoryStore()
graph = build_graph(store=store)
```

### 5. Registrar no `langgraph.json`

```json
{
  "dependencies": ["."],
  "graphs": {
    "rhawk_assistant": "./src/whatsapp_langchain/agents/catalog/rhawk_assistant/graph.py:graph",
    "meu_agente": "./src/whatsapp_langchain/agents/catalog/meu_agente/graph.py:graph"
  },
  "env": ".env"
}
```

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
- `user_id` (identidade do usuário; neste projeto vem do telefone no payload do Twilio)

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

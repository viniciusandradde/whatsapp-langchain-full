"""Middleware de Trim para gerenciamento de contexto.

O trim é a estratégia mais simples e barata para gerenciar contexto:
remove turnos antigos e mantém apenas os N mais recentes.

Um **turno** começa em cada HumanMessage e inclui tudo até o próximo
HumanMessage (respostas do AI, tool calls, tool results, etc).
Isso garante que ``keep_turns=3`` sempre mantém 3 trocas completas,
independente de quantas tool_calls existam em cada turno.

Trade-offs:
    - Custo: Zero (não faz chamada LLM extra)
    - Contexto: Perdido (turnos antigos são descartados)
    - Latência: Nenhuma

Quando usar:
    - Chatbots simples onde histórico antigo não importa
    - Testes e desenvolvimento
    - Quando custo é prioridade sobre contexto

Exemplo:
    from whatsapp_langchain.agents.middleware import create_trim_middleware

    trim = create_trim_middleware(keep_turns=5)
    agent = create_agent(model=model, middleware=[trim], ...)
"""

from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import before_model
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.runtime import Runtime


def create_trim_middleware(keep_turns: int = 5):
    """Cria middleware que mantém apenas os N turnos mais recentes.

    Um turno = 1 HumanMessage + todas as respostas até o próximo HumanMessage.
    Isso inclui AIMessage, ToolMessage, etc. Turnos são a unidade atômica —
    nunca cortamos no meio de um turno.

    O system prompt não precisa de tratamento — o ``create_agent()`` o injeta
    automaticamente via ``ModelRequest.system_message`` a cada chamada.

    Args:
        keep_turns: Número de turnos recentes a manter. Default: 5.

    Returns:
        Função middleware decorada com @before_model.

    Exemplo:
        Conversa com 4 turnos, keep_turns=2:

        Antes:  [h1 a1] [h2 a2 tool1 a2b] [h3 a3] [h4 a4]
        Depois: [h3 a3] [h4 a4]

        Note que o turno 2 tinha tool_calls (4 msgs) mas conta como 1 turno.

    Importante:
        O reducer ``add_messages`` faz merge, não replace — retornar uma lista
        menor NÃO remove mensagens. Usamos RemoveMessage para cada mensagem
        que deve sair do estado.
    """

    @before_model
    def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state["messages"]

        # Encontra os índices onde cada turno começa (cada HumanMessage)
        boundaries = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]

        # Se temos poucos turnos, não precisa fazer trim
        if len(boundaries) <= keep_turns:
            return None

        # O ponto de corte é o início do turno N contando de trás pra frente
        cutoff = boundaries[-keep_turns]

        # Remove tudo antes do ponto de corte
        messages_to_remove = messages[:cutoff]

        return {
            "messages": [
                RemoveMessage(id=m.id) for m in messages_to_remove if m.id is not None
            ]
        }

    return trim_messages

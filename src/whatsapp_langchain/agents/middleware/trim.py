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

Além dos turnos, aceita um teto em **caracteres** (`max_chars`, ADR-004):
é o "Tamanho do Contexto" que o painel oferece por agente (Lite 6k …
Extended 300k). Os dois limites se somam — o menor vence — e o turno mais
recente entra sempre, mesmo que sozinho passe do teto.

Exemplo:
    from whatsapp_langchain.agents.middleware import create_trim_middleware

    trim = create_trim_middleware(keep_turns=5, max_chars=15_000)
    agent = create_agent(model=model, middleware=[trim], ...)
"""

from typing import Any

import structlog
from langchain.agents import AgentState
from langchain.agents.middleware import before_model
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.runtime import Runtime

logger = structlog.get_logger()


def _tamanho(m: Any) -> int:
    """Caracteres de uma mensagem — aproximação de tokens (÷4) do ADR-004."""
    return len(str(m.content))


def create_trim_middleware(keep_turns: int = 5, max_chars: int | None = None):
    """Cria middleware que mantém apenas os N turnos mais recentes.

    Um turno = 1 HumanMessage + todas as respostas até o próximo HumanMessage.
    Isso inclui AIMessage, ToolMessage, etc. Turnos são a unidade atômica —
    nunca cortamos no meio de um turno.

    O system prompt não precisa de tratamento — o ``create_agent()`` o injeta
    automaticamente via ``ModelRequest.system_message`` a cada chamada.

    Args:
        keep_turns: Número de turnos recentes a manter. Default: 5.
        max_chars: Teto de caracteres do histórico (ADR-004). Aplicado DEPOIS
            do corte por turnos, do turno mais recente ao mais antigo: o
            primeiro turno que estoura o teto sai, e todos os anteriores com
            ele. O mais recente nunca sai. None = só o corte por turnos.

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

        # O ponto de corte é o início do turno N contando de trás pra frente.
        # Com poucos turnos não há corte (cutoff 0).
        cutoff = boundaries[-keep_turns] if len(boundaries) > keep_turns else 0

        # Teto em caracteres (ADR-004): soma turno a turno, do mais recente
        # ao mais antigo, e para no primeiro que estoura. O turno mais
        # recente entra sempre — sem ele o agente responderia no vazio.
        if max_chars is not None:
            inicios = [b for b in boundaries if b >= cutoff]
            fins = inicios[1:] + [len(messages)]
            acumulado = 0
            for inicio, fim in zip(reversed(inicios), reversed(fins), strict=True):
                acumulado += sum(_tamanho(m) for m in messages[inicio:fim])
                if acumulado > max_chars and inicio != inicios[-1]:
                    cutoff = fim
                    break

        if cutoff == 0:
            return None

        # Remove tudo antes do ponto de corte
        messages_to_remove = messages[:cutoff]
        logger.info(
            "contexto_trim",
            removidas=len(messages_to_remove),
            mantidas=len(messages) - cutoff,
            chars_mantidos=sum(_tamanho(m) for m in messages[cutoff:]),
            keep_turns=keep_turns,
            max_chars=max_chars,
        )

        return {
            "messages": [
                RemoveMessage(id=m.id) for m in messages_to_remove if m.id is not None
            ]
        }

    return trim_messages

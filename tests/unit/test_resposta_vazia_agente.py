"""O cliente parava de receber qualquer coisa quando o agente transferia.

Incidente medido em produção, empresa 1018 — 16 mensagens em 5 dias, 13
clientes distintos, todas terminando sem nenhum envio. O sintoma visível era
outro: `evolution_send_failed` 400 "Text is required".

O `ia_execucao` do atendimento 661 mostra o turno inteiro:

    18:53:03  chamada 1  106 tokens de saída, nenhuma tool registrada
    18:53:05  chamada 2    0 tokens de saída, {classificar_atendimento,
                                               transfer_to_human}

O callback registra as tools na chamada SEGUINTE à que as pediu. Ou seja: a
1ª chamada gastou seus tokens montando os argumentos das duas tools, elas
rodaram, e a 2ª — o turno da resposta final — devolveu zero. O worker lia
`messages[-1].content`, virava string vazia, e mandava assim mesmo.

Duas causas, e a segunda é a que torna a correção só-de-prompt insuficiente:

1. A descrição da `transfer_to_human` dizia ao modelo que o sistema anuncia a
   transferência sozinho. Os dois agentes que transferem têm
   `anuncia_transferencia = false` (mig 143) e o sistema NÃO anuncia.
2. Mesmo que o modelo escrevesse a frase de transição, ela viria na MESMA
   mensagem em que a tool é chamada — e `messages[-1]` já é a mensagem
   seguinte. O texto era descartado antes de chegar no cliente.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from whatsapp_langchain.shared.atendimento import MARKERS_REPROCESSAVEIS
from whatsapp_langchain.worker.processor import (
    RESPOSTA_VAZIA_MARKER,
    extrair_resposta_do_turno,
)


def _tool_call(nome: str = "transfer_to_human") -> dict:
    return {"name": nome, "args": {}, "id": f"call_{nome}", "type": "tool_call"}


class TestExtracao:
    def test_caso_normal_pega_a_ultima_mensagem(self) -> None:
        """O caminho de sempre não pode mudar de comportamento."""
        msgs = [
            HumanMessage(content="qual o horário?"),
            AIMessage(content="Funcionamos das 8h às 18h."),
        ]
        assert extrair_resposta_do_turno(msgs) == "Funcionamos das 8h às 18h."

    def test_recupera_o_texto_escrito_junto_com_a_tool_call(self) -> None:
        """O incidente. O modelo se despede e chama a tool na MESMA mensagem;
        depois das tools ele não tem mais nada a dizer e devolve vazio."""
        msgs = [
            HumanMessage(content="preciso falar com o professor"),
            AIMessage(
                content="Entendi. Vou encaminhar agora ao Luis Fernando.",
                tool_calls=[_tool_call()],
            ),
            ToolMessage(content="Transferido.", tool_call_id="call_transfer_to_human"),
            AIMessage(content=""),
        ]
        assert (
            extrair_resposta_do_turno(msgs)
            == "Entendi. Vou encaminhar agora ao Luis Fernando."
        )

    def test_para_na_mensagem_do_cliente(self) -> None:
        """A regressão cara: `result["messages"]` traz o histórico INTEIRO do
        checkpointer. Sem a barreira, um turno mudo reenviaria a resposta do
        turno anterior — o cliente leria de novo algo que já recebeu."""
        msgs = [
            HumanMessage(content="qual o horário?"),
            AIMessage(content="Funcionamos das 8h às 18h."),
            HumanMessage(content="obrigado"),
            AIMessage(content="", tool_calls=[_tool_call()]),
            ToolMessage(content="ok", tool_call_id="call_transfer_to_human"),
            AIMessage(content=""),
        ]
        assert extrair_resposta_do_turno(msgs) == ""

    def test_turno_totalmente_mudo_devolve_vazio(self) -> None:
        """Aí quem chama marca a linha em vez de enviar."""
        msgs = [
            HumanMessage(content="oi"),
            AIMessage(content="", tool_calls=[_tool_call()]),
            ToolMessage(content="Transferido.", tool_call_id="call_transfer_to_human"),
            AIMessage(content=""),
        ]
        assert extrair_resposta_do_turno(msgs) == ""

    def test_nunca_devolve_o_retorno_da_tool(self) -> None:
        """`ToolMessage` é conversa interna do agente. Se ela vazasse, o
        cliente leria "Transferido para o departamento X (id 999011)"."""
        msgs = [
            HumanMessage(content="oi"),
            AIMessage(content="", tool_calls=[_tool_call()]),
            ToolMessage(
                content="Transferido para Atendimento (id 999011).",
                tool_call_id="call_transfer_to_human",
            ),
        ]
        assert extrair_resposta_do_turno(msgs) == ""

    def test_conteudo_multimodal_em_blocos(self) -> None:
        """Conteúdo vem como lista quando o modelo responde em blocos — o
        código já trata isso com `isinstance(..., str)` mais adiante."""
        msgs = [
            HumanMessage(content="oi"),
            AIMessage(
                content=[
                    {"type": "text", "text": "Bom dia!"},
                    {"type": "text", "text": "Como posso ajudar?"},
                ]
            ),
        ]
        assert extrair_resposta_do_turno(msgs) == "Bom dia!\nComo posso ajudar?"

    def test_so_espaco_em_branco_conta_como_vazio(self) -> None:
        """Espaço em branco chega no provedor como "Text is required" igual."""
        msgs = [
            HumanMessage(content="oi"),
            AIMessage(content="Claro, um instante."),
            ToolMessage(content="ok", tool_call_id="x"),
            AIMessage(content="   \n  "),
        ]
        assert extrair_resposta_do_turno(msgs) == "Claro, um instante."

    def test_system_prompt_nao_e_barreira_nem_resposta(self) -> None:
        msgs = [
            SystemMessage(content="Você é um assistente."),
            HumanMessage(content="oi"),
            AIMessage(content="Olá!"),
        ]
        assert extrair_resposta_do_turno(msgs) == "Olá!"

    def test_lista_vazia(self) -> None:
        assert extrair_resposta_do_turno([]) == ""

    def test_mensagem_de_tipo_desconhecido_ainda_conta(self) -> None:
        """A regra é por exclusão de propósito.

        Exigir `type == "ai"` deixaria de fora qualquer mensagem fora do
        padrão e mudaria o comportamento de quem antes lia `[-1].content` sem
        perguntar nada — inclusive quebrando os dublês de `test_processor_twilio`.
        """

        class MensagemEstranha:
            type = None
            content = "Resposta do agente"

        assert extrair_resposta_do_turno([MensagemEstranha()]) == "Resposta do agente"


class TestMarcador:
    def test_nao_e_reprocessavel(self) -> None:
        """Quando a guarda age, a transferência JÁ rodou. Reenfileirar cairia
        no gate da fila do departamento e não produziria nada — diferente de
        `[modo manual` e `[whitelist`, onde a IA nunca chegou a rodar."""
        assert not any(
            RESPOSTA_VAZIA_MARKER.startswith(m) for m in MARKERS_REPROCESSAVEIS
        )

    def test_segue_a_convencao_dos_vizinhos(self) -> None:
        assert RESPOSTA_VAZIA_MARKER.startswith("[")
        assert RESPOSTA_VAZIA_MARKER.endswith("]")


class TestDescricaoDaTool:
    def test_nao_promete_mais_que_o_sistema_anuncia(self) -> None:
        """Era a promessa que fazia o modelo calar: ele lia que o sistema
        avisaria o cliente, e com `anuncia_transferencia=false` ninguém avisava.
        """
        from whatsapp_langchain.agents.tools.cliente_atendimento import (
            transfer_to_human,
        )

        desc = (transfer_to_human.description or "").lower()
        assert "sistema envia mensagem oficial" not in desc
        assert "sistema cuida do anúncio formal" not in desc

    def test_exige_despedida_na_mesma_mensagem(self) -> None:
        """A frase precisa vir junto com a tool call: depois dela o modelo
        costuma não ter mais turno de fala."""
        from whatsapp_langchain.agents.tools.cliente_atendimento import (
            transfer_to_human,
        )

        desc = (transfer_to_human.description or "").lower()
        assert "mesma mensagem" in desc
        assert "sempre" in desc

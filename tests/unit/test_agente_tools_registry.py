"""Os checkboxes de ferramenta do painel precisam valer alguma coisa.

Até 2026-07-27 o editor de agente mostrava "Ferramentas (11/19)" com
checkboxes, gravava em `agente_ia.tools_enabled` — e **nada lia esse campo em
runtime**. A lista era hardcoded no `build_graph`, então todo agente recebia o
mesmo conjunto, marcado ou não. O painel prometia um controle inexistente.

O caso que motivou: o agente do Luis Fernando precisa triar e transferir pro
departamento, e não dava pra confiar que `transferir_dep` estivesse ativo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from whatsapp_langchain.agents.tools.cliente_atendimento import (
    close_atendimento,
    transfer_to_human,
)
from whatsapp_langchain.agents.tools.knowledge import search_knowledge_base
from whatsapp_langchain.agents.tools.registry import (
    BACKLOG_SLUGS,
    SLUG_ALIASES,
    TOOL_SLUGS,
    normalizar_slug,
    resolve_tools,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EDITOR_TSX = REPO_ROOT / "frontend/src/app/agents/db/[slug]/agente-editor.tsx"


class TestTransferirDep:
    """O caso concreto que originou a correção."""

    def test_marcado_entrega_a_tool_de_transferencia(self) -> None:
        tools = resolve_tools(["transferir_dep"])

        assert transfer_to_human in tools

    def test_nao_marcado_nao_entrega(self) -> None:
        """Se o checkbox não vale nada, este teste falha."""
        tools = resolve_tools(["tag_cliente"])

        assert transfer_to_human not in tools
        assert len(tools) >= 1

    def test_solicitar_humano_e_a_mesma_tool(self) -> None:
        """Destino é determinístico (departamento_default_id) — um só caminho."""
        assert resolve_tools(["solicitar_humano"]) == resolve_tools(["transferir_dep"])


class TestFallback:
    """Agente sem ferramenta nenhuma não consegue nem pedir ajuda humana."""

    def test_lista_vazia_entrega_tudo(self) -> None:
        assert len(resolve_tools([])) == len(resolve_tools(None))
        assert transfer_to_human in resolve_tools([])

    def test_none_entrega_tudo(self) -> None:
        """Modo legacy (sem linha em `agente_ia`) não pode regredir."""
        assert transfer_to_human in resolve_tools(None)

    def test_so_slug_desconhecido_cai_no_conjunto_completo(self) -> None:
        """Preferimos ferramenta demais a agente mudo."""
        tools = resolve_tools(["coisa_que_nao_existe", "outra_invencao"])

        assert transfer_to_human in tools
        assert len(tools) == len(resolve_tools(None))

    def test_so_backlog_tambem_cai_no_completo(self) -> None:
        """Agente 80 tem `buscar_arquivos` marcado; não pode ficar sem nada."""
        tools = resolve_tools(["buscar_arquivos", "abrir_menu"])

        assert transfer_to_human in tools


class TestAliasLegado:
    """O agente 1 foi gravado com o vocabulário antigo."""

    def test_slug_antigo_resolve(self) -> None:
        assert normalizar_slug("transferir_para_departamento") == "transferir_dep"
        assert transfer_to_human in resolve_tools(["transferir_para_departamento"])

    def test_alias_nao_dispara_fallback(self) -> None:
        """Alias tem que ser reconhecido, não cair no 'devolve tudo'."""
        tools = resolve_tools(["transferir_para_departamento"])

        assert len(tools) < len(resolve_tools(None))

    def test_caixa_e_espaco_nao_quebram(self) -> None:
        assert transfer_to_human in resolve_tools(["  TRANSFERIR_DEP "])


class TestBacklogIgnorado:
    def test_backlog_nao_quebra_e_nao_apaga_o_resto(self) -> None:
        tools = resolve_tools(["transferir_dep", "buscar_arquivos"])

        assert transfer_to_human in tools

    def test_backlog_nao_tem_implementacao(self) -> None:
        """Se alguém implementar um, tem que sair do BACKLOG_SLUGS junto."""
        assert not (BACKLOG_SLUGS & TOOL_SLUGS.keys())


class TestGatesDeIntegracao:
    """Marcar o slug é necessário, não suficiente."""

    def test_calendario_marcado_mas_integracao_desligada(self) -> None:
        tools = resolve_tools(["calendar.create"], calendar_enabled=False)

        assert tools == []

    def test_calendario_marcado_com_integracao_ligada(self) -> None:
        tools = resolve_tools(["calendar.create"], calendar_enabled=True)

        assert len(tools) > 0

    def test_rag_marcado_mas_sem_documento(self) -> None:
        tools = resolve_tools(["search_knowledge_base"], knowledge_enabled=False)

        assert search_knowledge_base not in tools

    def test_rag_com_documento(self) -> None:
        tools = resolve_tools(["search_knowledge_base"], knowledge_enabled=True)

        assert search_knowledge_base in tools


class TestSelecaoMultipla:
    def test_combina_sem_duplicar(self) -> None:
        tools = resolve_tools(
            ["transferir_dep", "solicitar_humano", "encerrar_atendimento"]
        )

        assert tools.count(transfer_to_human) == 1
        assert close_atendimento in tools

    def test_ordem_independe_de_como_o_admin_marcou(self) -> None:
        """Ordem estável deixa o diff de log legível."""
        a = resolve_tools(["encerrar_atendimento", "transferir_dep"])
        b = resolve_tools(["transferir_dep", "encerrar_atendimento"])

        assert a == b


class TestParidadeComOFrontend:
    """A divergência UI × backend foi a causa raiz — trava ela aqui.

    Sem isto, alguém adiciona um checkbox no editor, o backend nunca resolve,
    e o sintoma reaparece: marcar não faz nada e ninguém liga uma coisa à
    outra.
    """

    @staticmethod
    def _slugs_do_frontend() -> set[str]:
        if not EDITOR_TSX.is_file():
            pytest.skip(f"editor não encontrado em {EDITOR_TSX}")
        texto = EDITOR_TSX.read_text(encoding="utf-8")
        bloco = texto.split("TOOLS_DISPONIVEIS")[1].split("];")[0]
        return set(re.findall(r'slug:\s*"([^"]+)"', bloco))

    def test_todo_slug_da_ui_e_conhecido_pelo_backend(self) -> None:
        da_ui = self._slugs_do_frontend()
        conhecidos = TOOL_SLUGS.keys() | BACKLOG_SLUGS | SLUG_ALIASES.keys()

        orfaos = da_ui - conhecidos
        assert not orfaos, (
            f"slugs na UI que o backend ignora silenciosamente: {sorted(orfaos)}. "
            "Adicione em TOOL_SLUGS (com implementação) ou em BACKLOG_SLUGS."
        )

    def test_coletor_realmente_le_a_ui(self) -> None:
        """Guarda que para de enxergar aprova tudo em silêncio."""
        assert len(self._slugs_do_frontend()) > 10

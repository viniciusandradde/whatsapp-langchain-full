"""Tests pra shared/menu_chatbot — helpers puros (Sub-fase B).

Cobre:
- ACAO_TIPOS (5 ações suportadas no MVP)
- parse_numero_opcao (regex de número de opção)
- is_trigger_keyword (case-insensitive trim)
- format_menu_message (formatação WhatsApp-like)
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from whatsapp_langchain.shared.menu_chatbot import (
    ACAO_TIPOS,
    format_menu_message,
    is_trigger_keyword,
    parse_numero_opcao,
)


# Stub leve do MenuItem só pra testes de formatação (evita conflitar com
# datetime real do dataclass importado).
@dataclass
class _ItemStub:
    id: int
    menu_id: int
    parent_id: int | None
    ordem: int
    label: str
    acao_tipo: str = "submenu"
    acao_payload: dict | None = None
    ativo: bool = True
    created_at: object = None
    updated_at: object = None


class TestAcaoTipos:
    def test_12_tipos_acoes(self):
        """Sub-fase B+ (mig 042) expandiu de 5 → 12 ações."""
        assert set(ACAO_TIPOS) == {
            # MVP (mig 040)
            "submenu",
            "transferir_dep",
            "chamar_agente",
            "enviar_msg",
            "fechar",
            # Sub-fase B+ (padrão profissional) (mig 042)
            "transferir_atendente",
            "enviar_template",
            "chamar_webhook",
            "enviar_link",
            "pesquisa_csat",
            "mudar_manual",
            "setar_nome",
        }

    def test_total_de_acoes(self):
        assert len(ACAO_TIPOS) == 12

    def test_acoes_mvp_continuam_presentes(self):
        """Garantia de não-regressão: ações MVP não foram removidas."""
        mvp = {"submenu", "transferir_dep", "chamar_agente", "enviar_msg", "fechar"}
        assert mvp.issubset(set(ACAO_TIPOS))


class TestParseNumeroOpcao:
    @pytest.mark.parametrize("entrada,esperado", [
        ("1", 1),
        ("2", 2),
        ("9", 9),
        ("10", 10),
        ("99", 99),
        (" 1 ", 1),
        ("01", 1),
        ("  3  ", 3),
    ])
    def test_aceita_numeros_validos(self, entrada, esperado):
        assert parse_numero_opcao(entrada) == esperado

    @pytest.mark.parametrize("entrada", [
        "",
        "abc",
        "0",       # 0 não é opção válida
        "100",     # mais de 2 dígitos
        "1 2",     # múltiplos números
        "1.",      # com pontuação
        "x",
        "menu",
        "1 hora",  # número embarcado em texto
    ])
    def test_rejeita_invalidos(self, entrada):
        assert parse_numero_opcao(entrada) is None


class TestIsTriggerKeyword:
    def test_match_exato(self):
        assert is_trigger_keyword("menu", ["menu", "opcoes", "inicio"]) is True

    def test_case_insensitive(self):
        assert is_trigger_keyword("MENU", ["menu"]) is True
        assert is_trigger_keyword("Menu", ["menu"]) is True

    def test_trim_whitespace(self):
        assert is_trigger_keyword("  menu  ", ["menu"]) is True

    def test_nao_match_quando_palavra_diferente(self):
        assert is_trigger_keyword("oi", ["menu"]) is False

    def test_nao_match_quando_palavra_em_frase(self):
        # 'menu' embarcado em frase NÃO conta — só match exato
        assert is_trigger_keyword("eu quero o menu", ["menu"]) is False

    def test_lista_vazia_de_keywords_nao_match_nada(self):
        assert is_trigger_keyword("menu", []) is False

    def test_keywords_vazias_ignoradas(self):
        # Lista com strings vazias não match
        assert is_trigger_keyword("", ["menu", ""]) is False

    def test_text_none_nao_explode(self):
        assert is_trigger_keyword("", ["menu"]) is False


class TestFormatMenuMessage:
    def test_lista_numerada_com_boas_vindas(self):
        items = [
            _ItemStub(1, 1, None, 1, "Vendas"),
            _ItemStub(2, 1, None, 2, "Suporte"),
        ]
        msg = format_menu_message("Olá! Como posso ajudar?", items)
        assert "Olá! Como posso ajudar?" in msg
        assert "1. Vendas" in msg
        assert "2. Suporte" in msg
        assert "Digite o número" in msg

    def test_sem_boas_vindas(self):
        items = [_ItemStub(1, 1, None, 1, "Opção A")]
        msg = format_menu_message(None, items)
        assert msg.startswith("1. Opção A")

    def test_sem_items_so_boas_vindas(self):
        msg = format_menu_message("Ei!", [])
        assert "Ei!" in msg
        # Sem dica de "digite número" quando não há opções
        assert "Digite o número" not in msg

    def test_ordem_respeitada(self):
        items = [
            _ItemStub(1, 1, None, 3, "Terceira"),
            _ItemStub(2, 1, None, 5, "Quinta"),
        ]
        msg = format_menu_message(None, items)
        # Usa ordem do item, não posição na lista
        assert "3. Terceira" in msg
        assert "5. Quinta" in msg

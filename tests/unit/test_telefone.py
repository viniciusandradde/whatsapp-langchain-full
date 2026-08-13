"""`normalizar_br` — telefone de usuário exige país + DDD.

O teste de regressão que importa: `+55996460034` (o telefone real da empresa
1, 11 dígitos SEM DDD) passava no `normalize_phone` de campanha e derrubou o
relatório mensal com `exists: false` no provedor, cinco tentativas, um mês
perdido. Aqui ele TEM que ser recusado.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.telefone import normalizar_br


class TestAceita:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            # E.164 completo, celular MS
            ("+5567996460034", "+5567996460034"),
            # Sem o +
            ("5567996460034", "+5567996460034"),
            # DDD + celular, sem país → assume BR
            ("67996460034", "+5567996460034"),
            # DDD + fixo (8 dígitos)
            ("6733214455", "+556733214455"),
            # Formatação humana
            ("(67) 99646-0034", "+5567996460034"),
            ("+55 67 99646-0034", "+5567996460034"),
            # Fixo completo com país (12 dígitos)
            ("556733214455", "+556733214455"),
            # SEM o +, "55" aqui é DDD (Santa Maria-RS), não país — celular
            # legítimo. É o gêmeo ambíguo do caso real recusado abaixo.
            ("55996460034", "+5555996460034"),
        ],
    )
    def test_formas_validas(self, entrada: str, esperado: str) -> None:
        assert normalizar_br(entrada) == esperado


class TestRecusa:
    @pytest.mark.parametrize(
        "entrada",
        [
            # O caso real da empresa 1: o + declara que "55" é o PAÍS, e os
            # 9 dígitos restantes não formam DDD + linha. Faltou o DDD.
            "+55996460034",
            # Curto demais
            "996460034",
            "4455",
            "",
            "   ",
            # Longo demais
            "+55679964600345",
            # País errado (EUA)
            "+15551234567",
            # DDD inexistente no plano BR
            "+5520996460034",
            # Celular de 9 dígitos que não começa com 9
            "+5567896460034",
            # Lixo
            "abc",
            "telefone",
        ],
    )
    def test_formas_invalidas(self, entrada: str) -> None:
        assert normalizar_br(entrada) is None

    def test_none(self) -> None:
        assert normalizar_br(None) is None

    def test_o_normalize_phone_de_campanha_deixaria_passar(self) -> None:
        """A razão de este módulo existir: o validador antigo aceita o número
        quebrado. Se um dia os dois convergirem, este teste documenta o
        contrato diferente."""
        from whatsapp_langchain.shared.campanha import normalize_phone

        assert normalize_phone("+55996460034") == "+55996460034"  # aceita!
        assert normalizar_br("+55996460034") is None  # nós, não


class TestCasoReal:
    def test_o_numero_da_empresa_1_sem_ddd_e_recusado(self) -> None:
        assert normalizar_br("+55996460034") is None

    def test_o_mesmo_numero_com_ddd_e_aceito(self) -> None:
        assert normalizar_br("+5567996460034") == "+5567996460034"

"""Testes da whitelist de números (mig 133) — normalização/candidatos.

O gate do worker é coberto em `test_processor_twilio.py::TestWhitelist`;
aqui fica a lógica pura de `candidatos_lookup` (variantes do nono dígito BR).
"""

from whatsapp_langchain.shared.whitelist import candidatos_lookup


class TestCandidatosLookup:
    def test_br_mobile_com_nono_digito_gera_variante_sem(self):
        assert candidatos_lookup("+5511988887777") == [
            "+5511988887777",
            "+551188887777",
        ]

    def test_br_mobile_sem_nono_digito_gera_variante_com(self):
        assert candidatos_lookup("+551188887777") == [
            "+551188887777",
            "+5511988887777",
        ]

    def test_normaliza_formatacao_antes_de_gerar(self):
        # Espaços/traços/parênteses são removidos pelo normalize_phone
        assert candidatos_lookup("55 (11) 98888-7777") == [
            "+5511988887777",
            "+551188887777",
        ]

    def test_br_13_digitos_sem_9_na_posicao_nao_gera_variante(self):
        # 11 dígitos após o 55 mas o 3º não é '9' — não é padrão mobile,
        # match exato apenas (sem variante espúria).
        assert candidatos_lookup("+5511788887777") == ["+5511788887777"]

    def test_nao_br_match_exato(self):
        assert candidatos_lookup("+14155552671") == ["+14155552671"]

    def test_invalido_retorna_vazio(self):
        assert candidatos_lookup("abc") == []
        assert candidatos_lookup("") == []
